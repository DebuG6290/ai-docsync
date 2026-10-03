from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from docsync.apply import apply_case
from docsync.engine import analyze, revise_rejected, suggest_mappings
from docsync.errors import DocSyncError, ModelError
from docsync.models import Decision
from docsync.repository.git_reader import read_file, resolve_commit
from docsync.repository.markdown_sections import parse_sections
from docsync.repository.python_symbols import extract_symbols
from docsync.sarvam import SarvamClient
from docsync.store import Store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="docsync", description="Audited local documentation synchronization")
    parser.add_argument("--db", type=Path, default=Path(".docsync-state/docsync.sqlite3"), help="SQLite audit database")
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("analyze", help="Analyze a Git change with Sarvam")
    command.add_argument("--repo", type=Path, required=True)
    command.add_argument("--old", required=True, help="old commit SHA/ref")
    command.add_argument("--new", required=True, help="new commit SHA/ref")
    command.add_argument("--model", default="sarvam-105b")

    mapping = commands.add_parser("map", help="Manage human-approved code to documentation mappings")
    subs = mapping.add_subparsers(dest="map_command", required=True)
    suggest = subs.add_parser("suggest", help="Ask Sarvam to suggest mapping candidates")
    suggest.add_argument("--repo", type=Path, required=True)
    suggest.add_argument("--rev", required=True)
    suggest.add_argument("--code-path", action="append", required=True)
    suggest.add_argument("--docs", nargs="+", required=True)
    suggest.add_argument("--model", default="sarvam-105b")
    subs.add_parser("pending", help="List mapping suggestions awaiting human review")
    confirm = subs.add_parser("confirm", help="Human-confirm a mapping suggestion")
    confirm.add_argument("suggestion_id")
    reject = subs.add_parser("reject", help="Reject a mapping suggestion")
    reject.add_argument("suggestion_id")
    add = subs.add_parser("add", help="Add a mapping explicitly confirmed by the human operator")
    add.add_argument("--code-id", required=True)
    add.add_argument("--section-id", required=True)
    add.add_argument("--reason", required=True)
    add.add_argument("--repo", type=Path, required=True)
    add.add_argument("--rev", required=True)
    subs.add_parser("list", help="List approved mappings")

    review = commands.add_parser("review", help="Review proposals for a case")
    review.add_argument("case_id")
    review.add_argument("--model", default="sarvam-105b")

    apply = commands.add_parser("apply", help="Apply accepted proposals after stale-text checks")
    apply.add_argument("case_id")

    audit = commands.add_parser("audit", help="Show the append-only case event history")
    audit.add_argument("case_id")
    return parser


def _seed_mapping(args, store: Store) -> None:
    repo = args.repo.resolve()
    sha = resolve_commit(repo, args.rev)
    code_path, sep, symbol_name = args.code_id.partition("::")
    if not sep:
        raise ValueError("code-id must have the form path::qualified_symbol")
    source = read_file(repo, sha, code_path)
    if source is None or args.code_id not in extract_symbols(code_path, source):
        raise ValueError(f"Code identity {args.code_id} does not exist at {sha}")
    section_path, sep, _ = args.section_id.partition("::")
    if not sep:
        raise ValueError("section-id must have the form path::heading-slug")
    markdown = read_file(repo, sha, section_path)
    if markdown is None or args.section_id not in {s.section_id for s in parse_sections(section_path, markdown)}:
        raise ValueError(f"Documentation section {args.section_id} does not exist at {sha}")
    store.add_confirmed_mapping(args.code_id, args.section_id, args.reason)
    print(f"Approved mapping saved: {args.code_id} <-> {args.section_id}")


def _review(store: Store, case_id: str, model: str) -> None:
    case = store.case(case_id)
    if case is None:
        raise ValueError(f"Unknown case {case_id}")
    snapshot = store.case_snapshot(case_id)
    print(f"Case {case_id} | {case['decision']} | {case['summary'] or ''}")
    assessments: dict[str, dict] = {}
    for row in store.audit(case_id):
        payload = json.loads(row["payload_json"])
        if row["kind"] == "section_decision":
            assessments[payload["section_id"]] = payload
        elif row["kind"] == "proposal_revision_assessment" and payload.get("section_id"):
            assessments[payload["section_id"]] = payload

    if case["decision"] == Decision.UNCERTAIN.value:
        print("Human triage required. These sections could not be resolved from the supplied evidence:")
        for section_id, assessment in assessments.items():
            if assessment.get("decision") != Decision.UNCERTAIN.value:
                continue
            print(f"\nSECTION {section_id}")
            print(f"Evidence completeness: {assessment.get('evidence_completeness', 'n/a')}")
            print(f"Reason: {assessment.get('reason', '')}")
            for name in ("missing_information", "safe_claims", "unsupported_claims"):
                print(f"{name.replace('_', ' ').title()}: " + ("; ".join(assessment.get(name, [])) or "none"))
        print("No proposal was generated for an uncertain section.")
        return
    if not store.proposals(case_id):
        print("All candidate sections are NO_CHANGE; no documentation proposals are available.")
        return
    input_fn = input
    for proposal in store.proposals(case_id):
        while True:
            proposal = store.proposal(proposal["id"])
            if proposal["status"] in {"ACCEPTED", "APPLIED"}:
                break
            context = store.proposal_context(proposal["id"])
            section = context["section"]
            latest = store.latest_version(proposal["id"])
            print("\n" + "=" * 78)
            print(f"SECTION {proposal['section_id']} | proposal version V{latest['version']} by {latest['author']}")
            print("\nCODE CHANGE / EVIDENCE\n")
            linked_code_ids = [m["code_id"] for m in snapshot["mappings"] if m["section_id"] == proposal["section_id"]]
            for change in snapshot["changes"]:
                if change["code_id"] in linked_code_ids:
                    print(f"{change['code_id']} ({change['change_kind']})\n{change['diff']}")
            print("Sarvam evidence: " + ("; ".join(json.loads(latest["code_evidence_json"])) or "none supplied"))
            assessment = assessments.get(proposal["section_id"], {})
            print(f"Evidence completeness: {assessment.get('evidence_completeness', 'n/a')}")
            for name in ("safe_claims", "unsupported_claims", "missing_information"):
                print(f"{name.replace('_', ' ').title()}: " + ("; ".join(assessment.get(name, [])) or "none"))
            print("\nCURRENT DOCUMENTATION\n")
            print(section["text"], end="" if section["text"].endswith("\n") else "\n")
            print("\nPROPOSED DOCUMENTATION\n")
            print(latest["proposed_text"], end="" if latest["proposed_text"].endswith("\n") else "\n")
            print("\nWHY THIS CHANGE IS PROPOSED\n")
            print(latest["reason"])
            print("\n[A] Accept  [M] Modify  [R] Reject  [C] Close")
            action = input_fn("Choice: ").strip().upper()
            if action == "A":
                store.review_event(proposal["id"], "ACCEPT", latest["id"])
                store.set_proposal_status(proposal["id"], "ACCEPTED", accepted_version_id=latest["id"])
                print(f"Accepted proposal version V{latest['version']}.")
                break
            if action == "M":
                print("Enter replacement documentation, then a single period (.) on its own line:")
                lines: list[str] = []
                while True:
                    line = input_fn()
                    if line == ".":
                        break
                    lines.append(line)
                replacement = "\n".join(lines)
                if latest["proposed_text"].endswith("\n") and replacement and not replacement.endswith("\n"):
                    replacement += "\n"
                new_id = store.add_version(proposal["id"], replacement, "Human-authored modification", [], "human")
                store.review_event(proposal["id"], "MODIFY", new_id, content=replacement)
                store.set_proposal_status(proposal["id"], "MODIFIED")
                print("Human-authored version stored. Accept it explicitly with [A] to make it eligible for apply.")
                continue
            if action == "R":
                reason = input_fn("Required rejection reason: ").strip()
                if not reason:
                    print("A non-empty rejection reason is required.")
                    continue
                store.review_event(proposal["id"], "REJECT", latest["id"], reason=reason)
                store.set_proposal_status(proposal["id"], "PENDING")
                try:
                    new_id = revise_rejected(store, proposal["id"], reason, SarvamClient(model))
                    new_version = store.latest_version(proposal["id"])
                    print(f"Sarvam created V{new_version['version']} ({new_id}); only this section was revised.")
                except (ModelError, ValueError) as exc:
                    print(f"Revision failed; rejection remains audited and the previous version is preserved: {exc}")
                    break
                continue
            if action == "C":
                print("Review closed; remaining proposals are unchanged.")
                return
            print("Choose A, M, R, or C.")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = _parser().parse_args()
    store = Store(args.db)
    try:
        if args.command == "analyze":
            case_id, decision = analyze(args.repo, args.old, args.new, store, SarvamClient(args.model))
            outcome = {
                Decision.UPDATE: "Proposed updates are ready for review.",
                Decision.UNCERTAIN: "Human triage is required; inspect the uncertain sections.",
                Decision.NO_CHANGE: "All candidate sections are NO_CHANGE.",
            }[decision]
            print(f"Case: {case_id}\nWorkflow state: {decision.value}\n{outcome}")
            print(f"Review proposals with: docsync --db {args.db} review {case_id}")
        elif args.command == "map":
            if args.map_command == "suggest":
                repo = args.repo.resolve()
                rev = resolve_commit(repo, args.rev)
                symbols: list[dict] = []
                for path in args.code_path:
                    source = read_file(repo, rev, path)
                    if source is None:
                        raise ValueError(f"Code file {path} not found at {rev}")
                    symbols.extend({"code_id": x.code_id, "path": x.path, "name": x.name, "kind": x.kind, "source": x.source} for x in extract_symbols(path, source).values())
                sections: list[dict] = []
                for path in args.docs:
                    text = read_file(repo, rev, path)
                    if text is None:
                        raise ValueError(f"Documentation file {path} not found at {rev}")
                    sections.extend({"section_id": s.section_id, "path": s.path, "heading": s.heading, "text": s.text} for s in parse_sections(path, text))
                suggestions = suggest_mappings(SarvamClient(args.model), symbols, sections, store)
                for item in suggestions:
                    sid = store.add_mapping_suggestion(item["code_id"], item["section_id"], item["reason"])
                    print(f"{sid}  {item['code_id']} <-> {item['section_id']}  {item['reason']}")
                print("Confirm individually with: docsync map confirm SUGGESTION_ID")
            elif args.map_command == "pending":
                rows = store.suggestions()
                for row in rows:
                    print(f"{row['id']}  {row['code_id']} ↔ {row['section_id']}  {row['reason']}")
                if not rows:
                    print("No pending mapping suggestions.")
            elif args.map_command in {"confirm", "reject"}:
                store.confirm_suggestion(args.suggestion_id, args.map_command == "confirm")
                print(f"Mapping suggestion {args.map_command}ed.")
            elif args.map_command == "add":
                _seed_mapping(args, store)
            elif args.map_command == "list":
                rows = store.db.execute("SELECT * FROM mappings WHERE status='APPROVED' ORDER BY code_id, section_id")
                for row in rows:
                    print(f"{row['code_id']} <-> {row['section_id']}  ({row['reason']})")
        elif args.command == "review":
            _review(store, args.case_id, args.model)
        elif args.command == "apply":
            results = apply_case(store, args.case_id)
            for item in results:
                print(f"Applied {item['section_id']} => {item['path']} (section sha256 {item['section_sha256']})")
        elif args.command == "audit":
            for event in store.audit(args.case_id):
                print(f"{event['created_at']}  {event['kind']}  {event['payload_json']}")
    except (DocSyncError, ValueError, OSError) as exc:
        print(f"docsync: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()

