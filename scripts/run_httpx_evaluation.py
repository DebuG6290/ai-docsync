from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docsync.engine import aggregate_case_decision, analyze  # noqa: E402
from docsync.errors import ModelError  # noqa: E402
from docsync.models import Decision  # noqa: E402
from docsync.repository.markdown_sections import parse_sections  # noqa: E402
from docsync.store import Store  # noqa: E402

RESULTS = {"PASS", "SEMANTIC_FAIL", "MODEL_CONTRACT_ERROR", "API_ERROR", "SYSTEM_ERROR"}


def audit_payloads(store: Store, case_id: str, kind: str | None = None) -> list[dict[str, Any]]:
    result = []
    for row in store.audit(case_id):
        if kind is None or row["kind"] == kind:
            result.append({"kind": row["kind"], **json.loads(row["payload_json"])})
    return result


def call_diagnostics(store: Store, case_id: str) -> list[dict[str, Any]]:
    return audit_payloads(store, case_id, "sarvam_call")


def fail_status(exc: Exception) -> str:
    if isinstance(exc, ModelError) and exc.category in {"API_ERROR", "MODEL_CONTRACT_ERROR"}:
        return exc.category
    return "SYSTEM_ERROR"


def semantic_status(expected: str, actual: str, additional_check: bool = True) -> str:
    return "PASS" if expected == actual and additional_check else "SEMANTIC_FAIL"


def root_cause_from_previous(error: str) -> str:
    lower = error.lower()
    if "omitted, duplicated, or introduced candidate section ids" in lower:
        return (
            "Sarvam's parsed impact output failed exact candidate-ID set equality. The old code reported the "
            "combined failure but did not retain which IDs were missing, duplicated, or unknown."
        )
    if "response content was not text" in lower:
        return (
            "The adapter assumed choices[0].message.content must already be a string and rejected the response. "
            "The original run stored no content type, finish reason, or message metadata, so the exact provider "
            "shape cannot be reconstructed from that report."
        )
    if "eof" in lower or "invalid json" in lower:
        return (
            "Pydantic received an incomplete JSON string and reported EOF. The old adapter did not inspect "
            "finish_reason or token usage, so the report cannot establish whether Sarvam hit its output limit "
            "or returned malformed JSON for another reason."
        )
    return "The prior report did not retain enough structured diagnostics to identify a more specific cause."


def previous_failures(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    failures = []
    for item in previous.get("scenarios", []):
        error = item.get("error")
        if error:
            failures.append(
                {
                    "scenario": item.get("scenario"),
                    "previous_result": item.get("actual_decision", "ERROR"),
                    "error": error,
                    "identified_root_cause": root_cause_from_previous(error),
                }
            )
    return failures


def revision_addresses_feedback(text: str) -> bool:
    normalized = " ".join(text.lower().replace("-", " ").split())
    has_inactivity_scope = "network inactivity" in normalized or "no data is being transmitted" in normalized
    has_request_scope = "request" in normalized
    denies_total_duration = bool(
        re.search(
            r"\b(?:not|does not|doesn't|is not|isn't)\b.{0,45}\b(?:overall deadline|total duration|total time|request duration)\b",
            normalized,
        )
    )
    return has_inactivity_scope and has_request_scope and denies_total_duration


def markdown(report: dict[str, Any]) -> str:
    out = [
        "# HTTPX Phase 1 Live Evaluation",
        "",
        f"Generated: {report['generated_at']}",
        f"Pinned base: `{report['pinned_base']}`",
        "",
        "## Original run errors",
        "",
    ]
    if report.get("original_run_errors"):
        for item in report["original_run_errors"]:
            out += [
                f"### Scenario {item['scenario']}: {item['previous_result']}",
                "",
                f"Observed: `{item['error']}`",
                "",
                item["identified_root_cause"],
                "",
            ]
    else:
        out += ["No prior report with recorded errors was provided.", ""]

    if report.get("legacy_replay_probes"):
        out += ["## Legacy request shape replays", ""]
        for probe in report["legacy_replay_probes"]:
            out += [
                f"### Scenario {probe['scenario']}: {probe['outcome']}",
                "",
                f"Request: model={probe.get('request_model')}, legacy_max_tokens={probe.get('max_tokens')}, "
                f"response_model={probe.get('response_model')}, response_id={probe.get('response_id')}",
                f"Response: envelope={probe.get('response_type')}/{probe.get('response_object')}, "
                f"choices={probe.get('choices_count')}, finish={probe.get('finish_reason')}, "
                f"message={probe.get('message_type')}, content={probe.get('content_type')}, "
                f"content_length={probe.get('content_length')}, input/output/total tokens="
                f"{probe.get('input_tokens')}/{probe.get('output_tokens')}/{probe.get('total_tokens')}",
                f"reasoning_field={probe.get('reasoning_content_present')} "
                f"(nonempty={probe.get('reasoning_content_nonempty')}), "
                f"tool_calls_field={probe.get('tool_calls_present')} "
                f"(nonempty={probe.get('tool_calls_nonempty')})",
                "",
                probe.get("interpretation", ""),
                "",
            ]

    out += ["## New scenario results", ""]
    if report.get("comparisons"):
        out += [
            "| Scenario | Previous Phase 1.1 result | New result | Regressed vs prior pass? | Accepted baseline |",
            "|---:|---|---|---|---|",
        ]
        for comparison in report["comparisons"]:
            out.append(
                f"| {comparison['scenario']} | {comparison['previous_result']} | {comparison['new_result']} | "
                f"{'Yes' if comparison['regressed'] else 'No'} | {comparison['accepted_phase1_baseline_result']} |"
            )
        out.append("")
    for item in report["scenarios"]:
        out += [
            f"### Scenario {item['scenario']}: {item['description']}",
            "",
            f"Result: **{item['status']}**  ",
            f"Expected: **{item.get('expected_decision', 'n/a')}**  ",
            f"Actual: **{item.get('actual_decision', 'n/a')}**  ",
        ]
        if item.get("error"):
            out += [f"Error: {item['error']}  "]
        if item.get("case_id"):
            out += [f"Case: `{item['case_id']}`  "]
        out += ["", "Mapped candidate sections:"]
        out += [f"- `{sid}`" for sid in item.get("mapped_sections", [])] or ["- none"]
        out += ["", "Sarvam section decisions:"]
        for section in item.get("sections", []):
            out += [
                f"- `{section.get('section_id')}`: **{section.get('decision', 'n/a')}** — {section.get('reason', '')}"
            ]
            out += [
                f"  Evidence completeness: **{section.get('evidence_completeness', 'n/a')}**; "
                f"safe claims: {json.dumps(section.get('safe_claims', []), ensure_ascii=False)}; "
                f"unsupported claims: {json.dumps(section.get('unsupported_claims', []), ensure_ascii=False)}"
            ]
            if section.get("code_evidence"):
                out += ["  Code evidence:", *[f"  - {claim}" for claim in section["code_evidence"]]]
            if section.get("proposed_text") is not None:
                out += ["", "  Proposed text:", "", "  ```markdown"]
                out += ["  " + line for line in section["proposed_text"].rstrip("\n").splitlines()]
                out += ["  ```"]
            if section.get("missing_information"):
                out += ["", "  Missing information:"]
                out += [f"  - {value}" for value in section["missing_information"]]
        if item.get("checks"):
            out += ["", "Checks:"]
            out += [f"- {'PASS' if passed else 'FAIL'}: {name}" for name, passed in item["checks"].items()]
        if item.get("failed_checks"):
            out += [f"", f"Failed checks: {', '.join(item['failed_checks'])}"]
        out += ["", "Sarvam call diagnostics:"]
        for index, call in enumerate(item.get("sarvam_calls", []), 1):
            out += [
                f"- Call {index}: operation={call.get('operation')}, model={call.get('model')}, "
                f"prompt={call.get('prompt_version')}, schema={call.get('schema_name')}, "
                f"candidates={','.join(call.get('candidate_section_ids') or [])}, "
                f"max_tokens={call.get('max_tokens')}, retry={call.get('retry_count')}, "
                f"finish={call.get('finish_reason')}, tokens={call.get('input_tokens')}/"
                f"{call.get('output_tokens')}/{call.get('total_tokens')}, "
                f"validation={call.get('response_contract_validation')}, "
                f"latency_ms={call.get('latency_ms')}, error={call.get('error_category')}",
                f"  response: type={call.get('response_type')}, choices={call.get('choices_count')}, "
                f"message={call.get('message_type')}, content={call.get('content_type')}, "
                f"reasoning_present={call.get('reasoning_content_present')} "
                f"(nonempty={call.get('reasoning_content_nonempty')}), "
                f"tool_calls_present={call.get('tool_calls_present')} "
                f"(nonempty={call.get('tool_calls_nonempty')}), "
                f"request_model={call.get('request_model')}, response_model={call.get('response_model')}, "
                f"response_id={call.get('response_id')}",
            ]
        if item.get("human_actions"):
            out += ["", f"Human actions: `{json.dumps(item['human_actions'], ensure_ascii=False)}`"]
        if item.get("revision_checks"):
            out += ["", "Revision checks:"]
            out += [f"- {key}: `{value}`" for key, value in item["revision_checks"].items()]
        if item.get("requested_feedback"):
            out += ["", f"Reviewer feedback: {item['requested_feedback']}"]
        if item.get("revision_versions"):
            out += ["", "Rejected proposal versions:"]
            for version in item["revision_versions"]:
                out += [
                    f"- V{version['version']} ({version['author']}, sha256 `{version['sha256']}`):",
                    "",
                    "  ```markdown",
                    *["  " + line for line in version["proposed_text"].rstrip("\n").splitlines()],
                    "  ```",
                ]
        if item.get("apply_checks"):
            out += ["", "Apply checks:"]
            out += [f"- {key}: `{value}`" for key, value in item["apply_checks"].items()]
        if item.get("final_text"):
            out += ["", "Final applied text:", "", "```markdown"]
            out += item["final_text"].rstrip("\n").splitlines()
            out += ["```"]
        out.append("")

    out += ["## Summary", ""]
    for status in sorted(RESULTS):
        out.append(f"- {status}: {report['summary'].get(status, 0)}")
    out.append("")
    return "\n".join(out)


def run_cli(db: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "docsync", "--db", str(db), *args],
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )


def _section_results(store: Store, case_id: str) -> list[dict[str, Any]]:
    return [json.loads(e["payload_json"]) for e in store.audit(case_id) if e["kind"] == "section_decision"]


def _latest_case_id(store: Store, repo: Path, old_sha: str, new_sha: str) -> str | None:
    resolved = str(repo.resolve())
    row = store.db.execute(
        "SELECT id FROM cases WHERE repo_root=? AND old_sha=? AND new_sha=? ORDER BY created_at DESC LIMIT 1",
        (resolved, old_sha, new_sha),
    ).fetchone()
    return row["id"] if row else None


def _case_entry(
    store: Store,
    item: dict[str, Any],
    expectation: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    expected_sections = {section["section_id"]: section for section in expectation["sections"]}
    entry: dict[str, Any] = {
        "scenario": item["scenario"],
        "description": item["description"],
        "expected_decision": expectation["expected_workflow_state"],
        "mapped_sections": item["section_ids"],
        "label_rationale": expectation["label_rationale"],
        "human_actions": [],
        "sarvam_calls": [],
        "sections": [],
        "checks": {},
    }
    try:
        case_id, decision = analyze(Path(item["repo"]), item["old_sha"], item["new_sha"], store)
        sections = _section_results(store, case_id)
        expected_ids = set(expected_sections)
        actual_ids = {section["section_id"] for section in sections}
        actual_by_id = {section["section_id"]: section for section in sections}
        for section in sections:
            expected_section = expected_sections.get(section["section_id"], {})
            section["expected_decision"] = expected_section.get("decision")
            section["expected_evidence_completeness"] = expected_section.get("evidence_completeness")
            section["expected_supported_claims"] = expected_section.get("supported_claims", [])
        checks: dict[str, bool] = {
            "returned exactly the mapped section IDs": actual_ids == expected_ids and len(sections) == len(expected_ids),
            "case workflow state matches frozen expected aggregation": decision.value == expectation["expected_workflow_state"],
            "application workflow state matches section decisions": aggregate_case_decision(
                [section.get("decision") for section in sections]
            ).value == decision.value,
        }
        for section_id, expected_section in expected_sections.items():
            actual_section = actual_by_id.get(section_id)
            checks[f"section decision correct: {section_id}"] = bool(
                actual_section and actual_section.get("decision") == expected_section["decision"]
            )
            checks[f"evidence completeness correct: {section_id}"] = bool(
                actual_section
                and actual_section.get("evidence_completeness") == expected_section["evidence_completeness"]
            )
        update_ids = {
            section["section_id"] for section in sections if section.get("decision") == "UPDATE"
        }
        proposal_ids = {proposal["section_id"] for proposal in store.proposals(case_id)}
        checks["proposals exist exactly for UPDATE sections"] = proposal_ids == update_ids
        if item["scenario"] == 3:
            checks["proposal documents is_disabled"] = any(
                section.get("decision") == "UPDATE"
                and "is_disabled" in (section.get("proposed_text") or "")
                for section in sections
            )
        failed_checks = [name for name, passed in checks.items() if not passed]
        entry.update(
            case_id=case_id,
            actual_decision=decision.value,
            sections=sections,
            sarvam_calls=call_diagnostics(store, case_id),
            checks=checks,
            failed_checks=failed_checks,
        )
        entry["status"] = "PASS" if not failed_checks else "SEMANTIC_FAIL"
        return entry, case_id
    except Exception as exc:
        case_id = _latest_case_id(store, Path(item["repo"]), item["old_sha"], item["new_sha"])
        entry.update(
            case_id=case_id,
            actual_decision="ERROR",
            status=fail_status(exc),
            error=f"{type(exc).__name__}: {exc}",
        )
        if case_id:
            entry["sarvam_calls"] = call_diagnostics(store, case_id)
        return entry, case_id


def _version_signature(store: Store, proposal_id: str) -> list[tuple[Any, ...]]:
    return [
        (v["id"], v["version"], v["author"], v["proposed_text"], v["reason"], v["code_evidence_json"])
        for v in store.versions(proposal_id)
    ]


def _scenario_5(store: Store, args, source_case_id: str | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "scenario": 5,
        "description": "Reject a proposal, require an observable scope clarification, then accept V2",
        "expected_decision": "UPDATE",
        "mapped_sections": [],
        "human_actions": [],
        "sarvam_calls": [],
    }
    if not source_case_id:
        entry.update(status="SYSTEM_ERROR", actual_decision="NOT_RUN", error="No persisted Scenario 1 case is available")
        return entry
    try:
        proposals = store.proposals(source_case_id)
        intro = next((p for p in proposals if p["section_id"] == "docs/advanced/timeouts.md::__intro__"), None)
        if intro is None:
            raise RuntimeError("The successful timeout case has no introductory proposal")
        snapshot = store.case_snapshot(source_case_id)
        entry.update(case_id=source_case_id, mapped_sections=sorted({m["section_id"] for m in snapshot["mappings"]}))
        v1_before = dict(store.latest_version(intro["id"]))
        proposal_ids = {p["id"] for p in proposals}
        others_before = {pid: _version_signature(store, pid) for pid in proposal_ids if pid != intro["id"]}
        calls_before = call_diagnostics(store, source_case_id)
        feedback = (
            "The value change is correct, but explicitly clarify that this is a network-inactivity timeout "
            "and not an overall deadline for the complete HTTP request."
        )
        interactive = "R\n" + feedback + "\n" + "A\n" * len(proposals)
        proc = run_cli(args.db, "review", source_case_id, stdin=interactive)
        versions = store.versions(intro["id"])
        review_events = [
            dict(row)
            for row in store.db.execute(
                "SELECT action, version_id, reason FROM review_events WHERE proposal_id=? ORDER BY created_at, rowid",
                (intro["id"],),
            )
        ]
        proposal_after = store.proposal(intro["id"])
        v2 = versions[1] if len(versions) > 1 else None
        others_after = {pid: _version_signature(store, pid) for pid in proposal_ids if pid != intro["id"]}
        calls = call_diagnostics(store, source_case_id)
        calls_this_scenario = calls[len(calls_before) :]
        entry["sarvam_calls"] = calls_this_scenario
        revision_calls = [call for call in calls_this_scenario if call.get("operation") == "revision"]
        revision_category = revision_calls[-1].get("error_category") if revision_calls else None
        if proc.returncode != 0:
            entry.update(status="SYSTEM_ERROR", actual_decision="ERROR", error=proc.stderr.strip() or "Review command failed")
            return entry
        if revision_category:
            entry.update(status=revision_category, actual_decision="ERROR", error="Sarvam revision call failed; see call diagnostics")
            return entry

        feedback_in_v2 = bool(v2 and revision_addresses_feedback(v2["proposed_text"]))
        revision_assessments = [
            event for event in audit_payloads(store, source_case_id, "proposal_revision_assessment")
            if event.get("proposal_id") == intro["id"]
        ]
        v1_preserved = bool(versions and dict(versions[0]) == v1_before)
        rejection_preserved = bool(
            review_events
            and review_events[0]["action"] == "REJECT"
            and review_events[0]["version_id"] == v1_before["id"]
            and review_events[0]["reason"] == feedback
        )
        v2_accepted = bool(
            proposal_after
            and proposal_after["status"] == "ACCEPTED"
            and v2
            and proposal_after["accepted_version_id"] == v2["id"]
            and any(e["action"] == "ACCEPT" and e["version_id"] == v2["id"] for e in review_events)
        )
        v2_differs = bool(v2 and v2["proposed_text"] != v1_before["proposed_text"])
        others_unchanged = others_before == others_after
        checks = {
            "V1 preserved": v1_preserved,
            "rejection event and exact reason preserved": rejection_preserved,
            "V2 differs from V1": v2_differs,
            "requested feedback appears in V2": feedback_in_v2,
            "only rejected proposal gained a version": others_unchanged and len(versions) == 2,
            "V2 explicitly accepted": v2_accepted,
        }
        entry.update(
            actual_decision="UPDATE",
            human_actions=review_events,
            requested_feedback=feedback,
            revision_checks=checks,
            revision_evidence_assessment=revision_assessments[-1] if revision_assessments else None,
            revision_versions=[
                {
                    "version": row["version"],
                    "author": row["author"],
                    "sha256": hashlib.sha256(row["proposed_text"].encode("utf-8")).hexdigest(),
                    "proposed_text": row["proposed_text"],
                }
                for row in versions
            ],
            sections=[
                {
                    "section_id": intro["section_id"],
                    "decision": "UPDATE",
                    "reason": v2["reason"] if v2 else "",
                    "proposed_text": v2["proposed_text"] if v2 else None,
                }
            ],
        )
        entry["status"] = "PASS" if all(checks.values()) and revision_calls else "SEMANTIC_FAIL"
        return entry
    except Exception as exc:
        entry.update(status=fail_status(exc), actual_decision="ERROR", error=f"{type(exc).__name__}: {exc}")
        return entry


def _clone_repo(source: Path, parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / f"scenario6-httpx-{uuid4().hex[:10]}"
    result = subprocess.run(
        ["git", "clone", "--quiet", "--local", str(source.resolve()), str(target)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Could not create isolated Scenario 6 repository")
    return target


def _scenario_6(store: Store, args, source_case_id: str | None, source_repo: Path | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "scenario": 6,
        "description": "Human-modify a persisted UPDATE, accept it, and apply it without a Sarvam rewrite",
        "expected_decision": "UPDATE",
        "mapped_sections": [],
        "human_actions": [],
        "sarvam_calls": [],
    }
    if not source_case_id or source_repo is None:
        entry.update(status="SYSTEM_ERROR", actual_decision="NOT_RUN", error="No persisted Scenario 1 UPDATE proposal is available")
        return entry
    try:
        source_snapshot = store.case_snapshot(source_case_id)
        source_proposals = store.proposals(source_case_id)
        if not source_proposals:
            raise RuntimeError("The successful Scenario 1 case contains no UPDATE proposal")
        isolated_repo = _clone_repo(source_repo, args.db.parent)
        cloned_snapshot = {**source_snapshot, "repo_root": str(isolated_repo)}
        case_id = store.create_case(cloned_snapshot)
        source_case = store.case(source_case_id)
        store.set_case_result(case_id, source_case["decision"], source_case["summary"] or "", "READY")
        target_intro_id = "docs/advanced/timeouts.md::__intro__"
        intro_id = None
        for proposal in source_proposals:
            v1 = store.versions(proposal["id"])[0]
            cloned_id = store.add_proposal(
                case_id,
                proposal["section_id"],
                v1["proposed_text"],
                v1["reason"],
                json.loads(v1["code_evidence_json"]),
            )
            if proposal["section_id"] == target_intro_id:
                intro_id = cloned_id
        if intro_id is None:
            raise RuntimeError("Persisted UPDATE case has no introductory proposal to modify")

        human_text = (
            "The default timeout is 8 seconds of network inactivity.\n\n"
            "This setting does not impose an overall deadline for the complete HTTP request.\n"
        )
        proposal_count = len(store.proposals(case_id))
        interactive = "M\n" + "\n".join(human_text.rstrip("\n").splitlines()) + "\n.\n" + "A\n" * proposal_count
        calls_before = len(call_diagnostics(store, case_id))
        proc = run_cli(args.db, "review", case_id, stdin=interactive)
        versions = store.versions(intro_id)
        human_version = versions[-1] if versions else None
        events = [
            dict(row)
            for row in store.db.execute(
                "SELECT action, version_id, content FROM review_events WHERE proposal_id=? ORDER BY created_at, rowid",
                (intro_id,),
            )
        ]
        proposal = store.proposal(intro_id)
        calls_after_review = call_diagnostics(store, case_id)
        if proc.returncode != 0:
            entry.update(status="SYSTEM_ERROR", actual_decision="ERROR", error=proc.stderr.strip() or "Review command failed")
            return entry
        if not human_version or human_version["author"] != "human" or human_version["proposed_text"] != human_text:
            entry.update(status="SYSTEM_ERROR", actual_decision="ERROR", error="Human-authored version was not stored exactly as entered")
            return entry
        if calls_before != len(calls_after_review) or calls_after_review:
            entry.update(status="SYSTEM_ERROR", actual_decision="ERROR", error="Sarvam was called during the human MODIFY/ACCEPT flow")
            return entry
        if proposal["status"] != "ACCEPTED" or proposal["accepted_version_id"] != human_version["id"]:
            entry.update(status="SYSTEM_ERROR", actual_decision="ERROR", error="Human version was not explicitly accepted")
            return entry
        if [e["action"] for e in events] != ["MODIFY", "ACCEPT"] or events[0]["content"] != human_text:
            entry.update(status="SYSTEM_ERROR", actual_decision="ERROR", error="Human MODIFY/ACCEPT events were not preserved")
            return entry

        apply_proc = run_cli(args.db, "apply", case_id)
        target_file = isolated_repo / "docs/advanced/timeouts.md"
        file_text = target_file.read_text(encoding="utf-8")
        final_section = next(
            (section.text for section in parse_sections("docs/advanced/timeouts.md", file_text) if section.section_id == target_intro_id),
            "",
        )
        applied_row = store.proposal(intro_id)
        audit = audit_payloads(store, case_id)
        patch_event = next((item for item in audit if item["kind"] == "patch_applied"), None)
        # Hash the on-disk bytes; Path.read_text() normalizes Windows CRLF newlines.
        file_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()
        section_hash = hashlib.sha256(human_text.encode("utf-8")).hexdigest()
        apply_checks = {
            "apply command succeeded": apply_proc.returncode == 0,
            "exact human text appears in documentation": final_section == human_text,
            "applied version is the human version": bool(applied_row and applied_row["accepted_version_id"] == human_version["id"] and applied_row["status"] == "APPLIED"),
            "section hash recorded": bool(applied_row and applied_row["applied_sha256"] == section_hash),
            "file hash recorded": bool(patch_event and any(result.get("file_sha256") == file_hash for result in patch_event.get("results", []))),
            "no Sarvam calls for human edit": not call_diagnostics(store, case_id),
        }
        store.event(
            "scenario_6_human_modify_verified",
            {
                "version_id": human_version["id"],
                "section_sha256": section_hash,
                "file_sha256": file_hash,
                "sarvam_call_count": len(call_diagnostics(store, case_id)),
            },
            case_id,
        )
        entry.update(
            case_id=case_id,
            mapped_sections=[p["section_id"] for p in source_proposals],
            actual_decision="UPDATE",
            human_actions=events,
            sarvam_calls=call_diagnostics(store, case_id),
            revision_checks={
                "human-authored version stored exactly": human_version["proposed_text"] == human_text,
                "no Sarvam rewrite during review": not calls_after_review,
                "human version explicitly accepted": proposal["accepted_version_id"] == human_version["id"],
            },
            apply_checks=apply_checks,
            sections=[{"section_id": target_intro_id, "decision": "UPDATE", "proposed_text": human_version["proposed_text"]}],
            final_text=final_section,
        )
        entry["status"] = "PASS" if all(apply_checks.values()) else "SYSTEM_ERROR"
        return entry
    except Exception as exc:
        entry.update(status=fail_status(exc), actual_decision="ERROR", error=f"{type(exc).__name__}: {exc}")
        return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all Phase 1 live Sarvam scenarios against controlled HTTPX commits")
    parser.add_argument("--manifest", type=Path, default=ROOT / ".httpx-scenarios" / "manifest.json")
    parser.add_argument("--expectations", type=Path, default=ROOT / "evals" / "phase1_1" / "original_expectations.json")
    parser.add_argument("--expectations-sha256", type=Path, default=ROOT / "evals" / "phase1_1" / "original_expectations.sha256")
    parser.add_argument("--db", type=Path, default=ROOT / ".docsync-state" / "httpx-eval.sqlite3")
    parser.add_argument("--out", type=Path, default=ROOT / "evals" / "phase1_1" / "original-benchmark-v2.md")
    parser.add_argument("--previous-report", type=Path, default=ROOT / "evals" / "phase1_1" / "original-benchmark.json")
    parser.add_argument("--accepted-baseline", type=Path, default=ROOT / "evals" / "httpx" / "phase1-live-report.json")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--reconcile-existing", action="store_true", help="Re-evaluate recorded HITL text with the semantic feedback rubric; makes no Sarvam calls")
    args = parser.parse_args()

    if args.reconcile_existing:
        json_path = args.out.with_suffix(".json")
        report = json.loads(json_path.read_text(encoding="utf-8"))
        scenario5 = next(item for item in report["scenarios"] if int(item["scenario"]) == 5)
        v2_text = scenario5.get("revision_versions", [])[-1]["proposed_text"] if len(scenario5.get("revision_versions", [])) > 1 else ""
        scenario5.setdefault("revision_checks", {})["requested feedback appears in V2"] = revision_addresses_feedback(v2_text)
        scenario5["failed_checks"] = [name for name, passed in scenario5["revision_checks"].items() if not passed]
        has_revision_call = any(call.get("operation") == "revision" and not call.get("error_category") for call in scenario5.get("sarvam_calls", []))
        scenario5["status"] = "PASS" if not scenario5["failed_checks"] and has_revision_call else "SEMANTIC_FAIL"
        scenario5["pass"] = scenario5["status"] == "PASS"
        report["summary"] = {}
        for item in report["scenarios"]:
            report["summary"][item["status"]] = report["summary"].get(item["status"], 0) + 1
        for comparison in report.get("comparisons", []):
            if int(comparison["scenario"]) == 5:
                comparison["new_result"] = scenario5["status"]
                comparison["new_failure_checks"] = scenario5["failed_checks"]
                comparison["regressed"] = comparison["previous_result"] == "PASS" and scenario5["status"] != "PASS"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        args.out.write_text(markdown(report), encoding="utf-8")
        print("Reconciled Scenario 5 feedback semantics from recorded V2 text; no Sarvam calls were made")
        return

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expectation_bytes = args.expectations.read_bytes()
    actual_expectations_hash = hashlib.sha256(expectation_bytes).hexdigest()
    locked_expectations_hash = args.expectations_sha256.read_text(encoding="utf-8").strip().split()[0]
    if actual_expectations_hash != locked_expectations_hash:
        raise SystemExit("Original expectation hash mismatch; no Sarvam calls were made")
    expectations = json.loads(expectation_bytes)
    expected_by_scenario = {str(row["scenario"]): row for row in expectations["scenarios"] if "scenario" in row}
    for item in manifest["scenarios"]:
        scenario = str(item["scenario"])
        expectation = expected_by_scenario.get(scenario)
        if expectation is None or set(item["section_ids"]) != {section["section_id"] for section in expectation["sections"]}:
            raise SystemExit(f"Frozen original expectations do not cover Scenario {scenario}'s exact mapped sections")
    if args.preflight_only:
        print(f"Preflight passed: {len(manifest['scenarios'])} original scenarios; no Sarvam calls were made")
        return
    if not os.environ.get("SARVAM_API_KEY"):
        raise SystemExit("SARVAM_API_KEY is not available in this process; no evaluation calls were made")

    store = Store(args.db)
    controlled_reason = "Operator-confirmed candidate mapping for the controlled HTTPX evaluation baseline."
    for item in manifest["scenarios"]:
        for section_id in item["section_ids"]:
            store.add_confirmed_mapping(item["code_id"], section_id, controlled_reason)

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pinned_base": manifest["pinned_base"],
        "original_run_errors": previous_failures(args.previous_report),
        "expectations_sha256": actual_expectations_hash,
        "expectations_frozen_before_calls": True,
        "relabel_note": "Scenario 4 is assessed as UPDATE/PARTIAL under the frozen section-level definition. Its prior expected label was UNCERTAIN; compare its previous and new result with that label change in view.",
        "scenarios": [],
        "summary": {},
    }
    source_case_id: str | None = None
    source_repo: Path | None = None
    for item in manifest["scenarios"]:
        expectation = expected_by_scenario[str(item["scenario"])]
        entry, case_id = _case_entry(store, item, expectation)
        report["scenarios"].append(entry)
        if (
            item["scenario"] == 1
            and case_id
            and entry.get("status") in {"PASS", "SEMANTIC_FAIL"}
            and entry.get("actual_decision") == "UPDATE"
            and any(p["section_id"] == "docs/advanced/timeouts.md::__intro__" for p in store.proposals(case_id))
        ):
            source_case_id = case_id
            source_repo = Path(item["repo"])

    scenario5 = _scenario_5(store, args, source_case_id)
    report["scenarios"].append(scenario5)
    scenario6 = _scenario_6(store, args, source_case_id, source_repo)
    report["scenarios"].append(scenario6)

    for item in report["scenarios"]:
        if item["status"] not in RESULTS:
            item["status"] = "SYSTEM_ERROR"
            item["error"] = f"Unknown evaluation result status: {item['status']}"
        item["pass"] = item["status"] == "PASS"
        report["summary"][item["status"]] = report["summary"].get(item["status"], 0) + 1

    previous_report = json.loads(args.previous_report.read_text(encoding="utf-8")) if args.previous_report.exists() else {}
    accepted_baseline = json.loads(args.accepted_baseline.read_text(encoding="utf-8")) if args.accepted_baseline.exists() else {}
    previous_by_id = {int(row["scenario"]): row for row in previous_report.get("scenarios", [])}
    baseline_by_id = {int(row["scenario"]): row for row in accepted_baseline.get("scenarios", [])}
    report["comparisons"] = []
    for item in report["scenarios"]:
        scenario = int(item["scenario"])
        previous = previous_by_id.get(scenario, {})
        baseline = baseline_by_id.get(scenario, {})
        report["comparisons"].append({
            "scenario": scenario,
            "description": item["description"],
            "previous_result": previous.get("status", "NOT_RECORDED"),
            "previous_decision": previous.get("actual_decision", "NOT_RECORDED"),
            "new_result": item.get("status", "SYSTEM_ERROR"),
            "new_decision": item.get("actual_decision", "ERROR"),
            "regressed": previous.get("status") == "PASS" and item.get("status") != "PASS",
            "accepted_phase1_baseline_result": baseline.get("status", "NOT_RECORDED"),
            "previous_failure_checks": previous.get("failed_checks") or previous.get("checks") or previous.get("revision_checks"),
            "new_failure_checks": item.get("failed_checks") or item.get("revision_checks") or item.get("apply_checks"),
            "label_revised": scenario == 4,
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    json_path = args.out.with_suffix(".json")
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    args.out.write_text(markdown(report), encoding="utf-8")
    print(f"Markdown report: {args.out}")
    print(f"JSON report: {json_path}")
    for item in report["scenarios"]:
        print(f"Scenario {item['scenario']}: {item.get('actual_decision', 'ERROR')} — {item['status']}")


if __name__ == "__main__":
    main()
