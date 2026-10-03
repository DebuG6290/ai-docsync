from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docsync.engine import aggregate_case_decision, analyze  # noqa: E402
from docsync.errors import ModelError  # noqa: E402
from docsync.repository.git_reader import changed_python_symbols, read_file  # noqa: E402
from docsync.repository.markdown_sections import parse_sections  # noqa: E402
from docsync.store import Store  # noqa: E402

INFRASTRUCTURE_RESULTS = {"API_ERROR", "MODEL_CONTRACT_ERROR", "SYSTEM_ERROR"}


def verify_frozen(path: Path, checksum_path: Path, label: str) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = checksum_path.read_text(encoding="utf-8").strip().split()[0]
    if digest != expected:
        raise SystemExit(f"{label} hash mismatch; no Sarvam calls were made")
    return digest


def audit_payloads(store: Store, case_id: str, kind: str | None = None) -> list[dict[str, Any]]:
    result = []
    for row in store.audit(case_id):
        if kind is None or row["kind"] == kind:
            result.append({"kind": row["kind"], **json.loads(row["payload_json"])})
    return result


def latest_case_id(store: Store, repo: Path, old_sha: str, new_sha: str) -> str | None:
    row = store.db.execute(
        "SELECT id FROM cases WHERE repo_root=? AND old_sha=? AND new_sha=? ORDER BY created_at DESC LIMIT 1",
        (str(repo.resolve()), old_sha, new_sha),
    ).fetchone()
    return row["id"] if row else None


def validate_fixture(manifest: dict[str, Any], generated: dict[str, dict[str, str]]) -> None:
    cases = manifest.get("cases", [])
    counts = {
        decision: sum(item.get("expected_decision") == decision for item in cases)
        for decision in ("UPDATE", "NO_CHANGE", "UNCERTAIN")
    }
    if len(cases) < 8 or counts["UPDATE"] < 2 or counts["NO_CHANGE"] < 2 or counts["UNCERTAIN"] < 4:
        raise SystemExit(f"Held-out set does not meet its frozen category minimums: cases={len(cases)}, {counts}")
    if len({item["scenario_id"] for item in cases}) != len(cases):
        raise SystemExit("Held-out manifest contains duplicate scenario IDs")
    for item in cases:
        if item.get("expected_evidence_completeness") not in {"COMPLETE", "PARTIAL", "INSUFFICIENT"}:
            raise SystemExit(f"Invalid evidence completeness label for {item['scenario_id']}")
        if not item.get("adjudication") or "proposal_rubric" not in item:
            raise SystemExit(f"Missing pre-call adjudication or proposal rubric for {item['scenario_id']}")
        refs = generated.get(item["scenario_id"])
        if not refs:
            raise SystemExit(f"No prepared repository for {item['scenario_id']}")
        repo = Path(refs["repo"])
        if not repo.is_absolute():
            repo = ROOT / repo
        changes = changed_python_symbols(repo, refs["old_sha"], refs["new_sha"])
        if item["code_id"] not in {change.code_id for change in changes}:
            raise SystemExit(f"Expected changed symbol {item['code_id']} is absent for {item['scenario_id']}")
        path = item["section_id"].partition("::")[0]
        docs = read_file(repo, refs["new_sha"], path)
        if docs is None or item["section_id"] not in {section.section_id for section in parse_sections(path, docs)}:
            raise SystemExit(f"Expected documentation section {item['section_id']} is absent for {item['scenario_id']}")


def heldout_entry(store: Store, item: dict[str, Any], generated: dict[str, str]) -> dict[str, Any]:
    repo = Path(generated["repo"])
    if not repo.is_absolute():
        repo = ROOT / repo
    old_sha = generated["old_sha"]
    new_sha = generated["new_sha"]
    entry: dict[str, Any] = {
        "scenario_id": item["scenario_id"],
        "description": item["description"],
        "code_id": item["code_id"],
        "section_id": item["section_id"],
        "documentation": item["documentation"],
        "available_evidence": item["available_evidence"],
        "intentionally_unavailable_evidence": item["intentionally_unavailable_evidence"],
        "expected_decision": item["expected_decision"],
        "expected_evidence_completeness": item["expected_evidence_completeness"],
        "expected_missing_information": item["expected_missing_information"],
        "expected_safe_claims": item["expected_safe_claims"],
        "expected_unsupported_claims": item["expected_unsupported_claims"],
        "proposal_rubric": item["proposal_rubric"],
        "adjudication": item["adjudication"],
        "actual_decision": None,
        "actual_evidence_completeness": None,
        "actual_missing_information": [],
        "actual_safe_claims": [],
        "actual_unsupported_claims": [],
        "actual_section": None,
        "actual_proposed_text": None,
        "status": None,
        "checks": {},
        "failed_checks": [],
        "sarvam_calls": [],
    }
    try:
        case_id, decision = analyze(repo, old_sha, new_sha, store)
        payloads = audit_payloads(store, case_id)
        section_events = [event for event in payloads if event["kind"] == "section_decision"]
        aggregation_events = [event for event in payloads if event["kind"] == "case_workflow_aggregation"]
        calls = [event for event in payloads if event["kind"] == "sarvam_call"]
        observed = section_events[-1] if len(section_events) == 1 else None
        actual_completeness = (observed or {}).get("evidence_completeness")
        missing = (observed or {}).get("missing_information", [])
        safe_claims = (observed or {}).get("safe_claims", [])
        unsupported_claims = (observed or {}).get("unsupported_claims", [])
        proposed_text = (observed or {}).get("proposed_text")
        expected_decision = item["expected_decision"]
        expected_completeness = item["expected_evidence_completeness"]
        actual_section_decision = (observed or {}).get("decision")
        aggregated = aggregate_case_decision([event.get("decision") for event in section_events]).value if section_events else None
        aggregate_event = aggregation_events[-1] if aggregation_events else None
        checks = {
            "section decision matches frozen label": (observed or {}).get("decision") == expected_decision,
            "evidence completeness matches frozen label": actual_completeness == expected_completeness,
            "missing information agrees with completeness": bool(observed) and (
                (actual_completeness == "COMPLETE" and not missing)
                or (actual_completeness in {"PARTIAL", "INSUFFICIENT"} and bool(missing))
            ),
            "safe claims supplied for UPDATE": actual_section_decision != "UPDATE" or bool(safe_claims),
            "proposed text exists only for UPDATE": (
                (actual_section_decision == "UPDATE" and isinstance(proposed_text, str) and bool(proposed_text.strip()))
                or (actual_section_decision != "UPDATE" and proposed_text is None)
            ),
            "section result contains the requested section exactly once": (
                len(section_events) == 1 and observed.get("section_id") == item["section_id"]
            ),
            "application aggregation matches returned section decisions": bool(aggregate_event)
            and aggregated == decision.value == aggregate_event.get("derived_workflow_state"),
            "workflow state matches the frozen section label": decision.value == expected_decision,
        }
        failed_checks = [name for name, passed in checks.items() if not passed]
        entry.update(
            case_id=case_id,
            actual_decision=decision.value,
            actual_evidence_completeness=actual_completeness,
            actual_missing_information=missing,
            actual_safe_claims=safe_claims,
            actual_unsupported_claims=unsupported_claims,
            actual_section=observed,
            actual_proposed_text=proposed_text,
            sarvam_calls=[{key: value for key, value in event.items() if key != "kind"} for event in calls],
            checks=checks,
            failed_checks=failed_checks,
            status="PASS" if not failed_checks else "SEMANTIC_FAIL",
        )
    except Exception as exc:
        case_id = latest_case_id(store, repo, old_sha, new_sha)
        category = exc.category if isinstance(exc, ModelError) else "SYSTEM_ERROR"
        entry.update(
            case_id=case_id,
            status=category if category in INFRASTRUCTURE_RESULTS else "SYSTEM_ERROR",
            actual_decision="ERROR",
            error=f"{type(exc).__name__}: {exc}",
        )
        if case_id:
            entry["sarvam_calls"] = [
                {key: value for key, value in event.items() if key != "kind"}
                for event in audit_payloads(store, case_id, "sarvam_call")
            ]
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen Phase 1.1 held-out set against live Sarvam")
    parser.add_argument("--manifest", type=Path, default=ROOT / "evals" / "phase1_1" / "heldout_manifest.json")
    parser.add_argument("--manifest-sha256", type=Path, default=ROOT / "evals" / "phase1_1" / "heldout_manifest.sha256")
    parser.add_argument("--adjudication", type=Path, default=ROOT / "evals" / "phase1_1" / "heldout_adjudication.md")
    parser.add_argument("--adjudication-sha256", type=Path, default=ROOT / "evals" / "phase1_1" / "heldout_adjudication.sha256")
    parser.add_argument("--generated-manifest", type=Path, default=ROOT / "evals" / "phase1_1" / "fixture_commits.json")
    parser.add_argument("--generated-manifest-sha256", type=Path, default=ROOT / "evals" / "phase1_1" / "fixture_commits.sha256")
    parser.add_argument("--db", type=Path, default=ROOT / ".docsync-state" / "phase1-1-v2.sqlite3")
    parser.add_argument("--out", type=Path, default=ROOT / "evals" / "phase1_1" / "heldout-results-v2.json")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    manifest_hash = verify_frozen(args.manifest, args.manifest_sha256, "Held-out label manifest")
    adjudication_hash = verify_frozen(args.adjudication, args.adjudication_sha256, "Held-out adjudication")
    generated_hash = verify_frozen(args.generated_manifest, args.generated_manifest_sha256, "Held-out fixture commits")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    generated = json.loads(args.generated_manifest.read_text(encoding="utf-8"))
    validate_fixture(manifest, generated)
    if args.preflight_only:
        print(f"Preflight passed: {len(manifest['cases'])} frozen held-out cases; no Sarvam calls were made")
        return
    if not os.environ.get("SARVAM_API_KEY"):
        raise SystemExit("SARVAM_API_KEY is not available in this process; no held-out calls were made")

    store = Store(args.db)
    for item in manifest["cases"]:
        store.add_confirmed_mapping(
            item["code_id"], item["section_id"], "Controlled evaluation mapping frozen before the model run."
        )
    results = [heldout_entry(store, item, generated[item["scenario_id"]]) for item in manifest["cases"]]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reasoning_contract": "impact.v4",
        "heldout_expectation_sha256": manifest_hash,
        "heldout_adjudication_sha256": adjudication_hash,
        "heldout_fixture_manifest_sha256": generated_hash,
        "heldout_expectations_frozen_before_calls": True,
        "category_counts": {
            decision: sum(item["expected_decision"] == decision for item in results)
            for decision in ("UPDATE", "NO_CHANGE", "UNCERTAIN")
        },
        "cases": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Held-out model results: {args.out}")
    for item in results:
        print(f"{item['scenario_id']}: {item.get('actual_decision', 'ERROR')} — {item['status']}")


if __name__ == "__main__":
    main()
