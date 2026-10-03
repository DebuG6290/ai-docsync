from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_RESULTS = {"PASS", "SEMANTIC_FAIL"}
INFRASTRUCTURE_RESULTS = {"API_ERROR", "MODEL_CONTRACT_ERROR", "SYSTEM_ERROR"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require_hash(path: Path, digest: str, label: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        raise SystemExit(f"{label} differs from the pre-call frozen input")


def status_from_checks(checks: dict[str, bool], infrastructure: str | None = None) -> str:
    if infrastructure:
        return infrastructure
    return "PASS" if all(checks.values()) else "SEMANTIC_FAIL"


def review_checks(review: dict[str, Any] | None, prefix: str) -> dict[str, bool]:
    if not review:
        return {
            f"{prefix}: safe claims are supported by supplied evidence": False,
            f"{prefix}: proposed facts are supported by safe_claims": False,
            f"{prefix}: no unsupported claim is asserted": False,
            f"{prefix}: frozen claim rubric is satisfied": False,
        }
    checks = {
        f"{prefix}: safe claims are supported by supplied evidence": review.get("safe_claims_supported") is True,
        f"{prefix}: proposed facts are supported by safe_claims": review.get("proposal_factual_support") is True,
        f"{prefix}: no unsupported claim is asserted": review.get("unsupported_claim_violation") is False,
        f"{prefix}: frozen claim rubric is satisfied": review.get("rubric_satisfied") is True,
    }
    if "missing_information_adequate" in review:
        checks[f"{prefix}: missing information covers frozen evidence gaps"] = review.get("missing_information_adequate") is True
    return checks


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 1.1 Validation Results",
        "",
        f"Generated: {report['generated_at']}",
        f"Impact reasoning contract: `{report['reasoning_contract']}`",
        "The original-six expectations were hash-checked before their rerun. Held-out labels, rationales, and fixture commit IDs were hash-checked before the held-out calls; none changed after held-out output. Proposal reviews were completed against those frozen rubrics.",
        "",
        "Run notes:",
        *[f"- {value}" for value in report["run_notes"]],
        "",
        "## Original benchmark",
        "",
        "| Scenario | Previous Phase 1.1 result | Previous decision | New result | New decision | Regression vs accepted Phase 1 baseline? |",
        "|---:|---|---|---|---|---|",
    ]
    for item in report["original_benchmark"]:
        regressed = item.get("behavior_regressed_vs_accepted_baseline")
        display_regressed = "Not comparable" if regressed is None else ("Yes" if regressed else "No")
        lines.append(
            f"| {item['scenario']} | {item['previous_result']} | {item['previous_decision']} | "
            f"{item['new_result']} | {item['new_decision']} | {display_regressed} |"
        )
    lines += [
        "",
        "Previous Phase 1.1 failures for Scenarios 1 and 5 are diagnosed explicitly below. Scenario 4's expected result changed from UNCERTAIN to UPDATE/PARTIAL under the frozen new definition, so its old and new pass labels are not directly comparable.",
        "",
    ]
    for item in report["original_benchmark"]:
        lines += [
            f"### Scenario {item['scenario']}: {item['description']}",
            "",
            f"Previous: **{item['previous_result']} / {item['previous_decision']}**; accepted Phase 1 baseline: **{item['accepted_phase1_baseline_result']}**; new: **{item['new_result']} / {item['new_decision']}**.",
            f"Regression: **{item.get('behavior_regressed_vs_accepted_baseline')}**.",
        ]
        if item.get("label_rationale"):
            lines.append(f"Frozen label rationale: {item['label_rationale']}")
        if item.get("prior_failure_diagnosis"):
            lines += ["", "Previous failed-check diagnosis:", *[f"- {value}" for value in item["prior_failure_diagnosis"]]]
        if item.get("sections"):
            lines += ["", "Sections:"]
            for section in item["sections"]:
                lines += [
                    f"- `{section.get('section_id')}` — expected **{section.get('expected_decision', 'n/a')} / {section.get('expected_evidence_completeness', 'n/a')}**, actual **{section.get('decision', 'n/a')} / {section.get('evidence_completeness', 'n/a')}**.",
                    f"  Reason: {section.get('reason', '')}",
                    f"  Missing information: {json.dumps(section.get('missing_information', []), ensure_ascii=False)}",
                    f"  Safe claims: {json.dumps(section.get('safe_claims', []), ensure_ascii=False)}",
                    f"  Unsupported claims: {json.dumps(section.get('unsupported_claims', []), ensure_ascii=False)}",
                ]
                if section.get("proposed_text") is not None:
                    lines += ["", "  Proposed text:", "", "  ```markdown", *["  " + s for s in section["proposed_text"].rstrip().splitlines()], "  ```"]
                if section.get("proposal_review", {}).get("review_note"):
                    lines.append(f"  Proposal review: {section['proposal_review']['review_note']}")
        if item.get("checks"):
            lines += ["", "Checks:", *[f"- {'PASS' if value else 'FAIL'}: {name}" for name, value in item["checks"].items()]]
        if item.get("failed_checks"):
            lines += [f"", f"Failed checks: {', '.join(item['failed_checks'])}"]
        if item.get("revision_checks"):
            lines += ["", "Scenario 5 HITL checks:", *[f"- {'PASS' if value else 'FAIL'}: {name}" for name, value in item["revision_checks"].items()]]
            assessment = item.get("revision_evidence_assessment")
            if assessment:
                lines += [
                    "",
                    f"Revision evidence completeness: **{assessment.get('evidence_completeness', 'n/a')}**",
                    f"Revision safe claims: {json.dumps(assessment.get('safe_claims', []), ensure_ascii=False)}",
                    f"Revision unsupported claims: {json.dumps(assessment.get('unsupported_claims', []), ensure_ascii=False)}",
                ]
            if item.get("revision_proposal_review", {}).get("review_note"):
                lines.append(f"Manual proposal review: {item['revision_proposal_review']['review_note']}")
        if item.get("apply_checks"):
            lines += ["", "Scenario 6 HITL/apply checks:", *[f"- {'PASS' if value else 'FAIL'}: {name}" for name, value in item["apply_checks"].items()]]
        if item.get("error"):
            lines += ["", f"Infrastructure/model error: `{item['error']}`"]
        lines.append("")

    lines += [
        "## Held-out uncertainty benchmark",
        "",
        "A case is a semantic failure if its frozen section decision, completeness classification, aggregation, claim boundary, proposal safety, or relevant missing-information check fails. Infrastructure errors are listed separately and excluded from semantic accuracy.",
        "",
    ]
    for item in report["heldout_cases"]:
        lines += [
            f"### {item['scenario_id']}: {item['description']}",
            "",
            f"Result: **{item['status']}**",
            f"Expected decision/completeness: **{item['expected_decision']} / {item['expected_evidence_completeness']}**; actual: **{item.get('actual_decision', 'n/a')} / {item.get('actual_evidence_completeness', 'n/a')}**.",
            f"Expected missing information: {json.dumps(item.get('expected_missing_information', []), ensure_ascii=False)}",
            f"Model-identified missing information: {json.dumps(item.get('actual_missing_information', []), ensure_ascii=False)}",
            "",
            "Available evidence:",
            *[f"- {value}" for value in item["available_evidence"]],
            "",
            "Intentionally unavailable evidence:",
            *([f"- {value}" for value in item["intentionally_unavailable_evidence"]] or ["- None specified"]),
            "",
            f"Adjudication: {item['adjudication']}",
            f"Model explanation: {(item.get('actual_section') or {}).get('reason', item.get('error', 'No valid result'))}",
            f"Safe claims: {json.dumps(item.get('actual_safe_claims', []), ensure_ascii=False)}",
            f"Unsupported claims: {json.dumps(item.get('actual_unsupported_claims', []), ensure_ascii=False)}",
        ]
        if item.get("actual_proposed_text") is not None:
            lines += ["", "Proposed text:", "", "```markdown", *item["actual_proposed_text"].rstrip().splitlines(), "```"]
        if item.get("proposal_review", {}).get("review_note"):
            lines.append(f"Proposal review: {item['proposal_review']['review_note']}")
        lines += ["", "Checks:", *[f"- {'PASS' if value else 'FAIL'}: {name}" for name, value in item.get("checks", {}).items()]]
        if item.get("failed_checks"):
            lines.append(f"Failed checks: {', '.join(item['failed_checks'])}")
        if item.get("error"):
            lines.append(f"Infrastructure/model error: `{item['error']}`")
        lines.append("")

    lines += [
        "## Scorecard and exit decision",
        "",
        "| Expected decision | Correct | Scored | Accuracy | Infrastructure errors |",
        "|---|---:|---:|---:|---:|",
    ]
    for decision, count in report["decision_accuracy"].items():
        rate = "n/a" if count["accuracy"] is None else f"{count['accuracy']:.0%}"
        lines.append(f"| {decision} | {count['correct']} | {count['scored']} | {rate} | {count['infrastructure_errors']} |")
    lines += [
        "",
        f"Evidence-completeness accuracy: {report['evidence_completeness_accuracy']['correct']}/{report['evidence_completeness_accuracy']['scored']} ({report['evidence_completeness_accuracy']['accuracy']:.0%}) among valid model outputs.",
        f"Proposal factual support: {report['proposal_safety']['supported']}/{report['proposal_safety']['reviewed']} proposals supported by their safe_claims and frozen rubric.",
        f"Unsupported-claim violations: {report['proposal_safety']['unsupported_claim_violations']}.",
        f"Section-to-case aggregation: {report['aggregation_accuracy']['correct']}/{report['aggregation_accuracy']['scored']}.",
        f"HITL checks: Scenario 5 {report['hitl']['scenario_5']}; Scenario 6 {report['hitl']['scenario_6']}.",
        f"Original behavior regressions vs accepted Phase 1 baseline: {', '.join(map(str, report['regressions'])) or 'none'}.",
        f"Phase 1 decision: **{report['phase1_freeze_decision']}**",
        "",
        "Limitations:",
        *[f"- {value}" for value in report["limitations"]],
        "",
        "## Recommended Phase 2 plan (not implemented)",
        "",
        "1. **GitHub trigger:** add a least-privilege GitHub App/webhook that queues relevant pull-request or commit changes and deduplicates delivery IDs.",
        "2. **Persistent online case state:** move cases, mappings, evidence assessments, model calls, and review events from local SQLite to a durable database with authenticated repository ownership.",
        "3. **Review surface:** show changed symbols, mapped sections, evidence completeness, missing information, safe and unsupported claims, proposed edits, and explicit human approve/reject/modify actions.",
        "4. **Approved documentation commit:** create a narrowly scoped branch or pull request only after approval, with conflict checks and an audit link to the approved proposal.",
        "5. **Approved-only indexing:** ingest only from approved documentation commits and record their source revisions; keep pending or rejected text out of the index.",
        "6. **Chat:** answer from the approved index with citations to documentation revisions and preserve the review trail for corrections.",
        "",
    ]
    return "\n".join(lines)


def finalize(args: argparse.Namespace) -> dict[str, Any]:
    manifest_hash = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    adjudication_hash = hashlib.sha256(args.adjudication.read_bytes()).hexdigest()
    expectations_hash = hashlib.sha256(args.original_expectations.read_bytes()).hexdigest()
    require_hash(args.manifest, args.manifest_sha256.read_text(encoding="utf-8").strip().split()[0], "Held-out manifest")
    require_hash(args.adjudication, args.adjudication_sha256.read_text(encoding="utf-8").strip().split()[0], "Held-out adjudication")
    require_hash(args.original_expectations, args.original_expectations_sha256.read_text(encoding="utf-8").strip().split()[0], "Original expectations")
    raw_heldout = load_json(args.heldout_results)
    fixture_hash = hashlib.sha256(args.generated_manifest.read_bytes()).hexdigest()
    require_hash(args.generated_manifest, args.generated_manifest_sha256.read_text(encoding="utf-8").strip().split()[0], "Held-out fixture commits")
    original = load_json(args.original_results)
    previous = load_json(args.previous_original)
    baseline = load_json(args.accepted_baseline)
    reviews = load_json(args.claim_reviews)
    if raw_heldout.get("heldout_expectation_sha256") != manifest_hash or raw_heldout.get("heldout_adjudication_sha256") != adjudication_hash or raw_heldout.get("heldout_fixture_manifest_sha256") != fixture_hash:
        raise SystemExit("Held-out model output does not match the frozen label inputs")
    if original.get("expectations_sha256") != expectations_hash:
        raise SystemExit("Original model output does not match its frozen expectation input")

    heldout_cases = raw_heldout["cases"]
    heldout_review = reviews.get("heldout", {})
    for item in heldout_cases:
        checks = dict(item.get("checks", {}))
        actual_section = item.get("actual_section") or {}
        actual_proposed_text = item.get("actual_proposed_text")
        checks["proposed text exists only for UPDATE"] = (
            (actual_section.get("decision") == "UPDATE" and isinstance(actual_proposed_text, str) and bool(actual_proposed_text.strip()))
            or (actual_section.get("decision") != "UPDATE" and actual_proposed_text is None)
        )
        if item.get("actual_decision") == "UPDATE" and item.get("actual_proposed_text") is not None:
            review = heldout_review.get(item["scenario_id"])
            claim_checks = review_checks(review, "proposal review")
            checks.update(claim_checks)
            item["proposal_review"] = review
        elif item.get("actual_proposed_text") is not None:
            checks["no proposal for non-UPDATE section"] = False
        item["checks"] = checks
        item["failed_checks"] = [name for name, passed in checks.items() if not passed]
        item["status"] = status_from_checks(checks, item.get("status") if item.get("status") in INFRASTRUCTURE_RESULTS else None)

    old_by_scenario = {int(row["scenario"]): row for row in previous.get("scenarios", [])}
    baseline_by_scenario = {int(row["scenario"]): row for row in baseline.get("scenarios", [])}
    expectation_by_scenario = {int(row["scenario"]): row for row in load_json(args.original_expectations)["scenarios"] if "scenario" in row}
    section_reviews = reviews.get("original_sections", {})
    original_benchmark = []
    for item in original["scenarios"]:
        scenario = int(item["scenario"])
        original_checks = dict(item.get("checks", {}))
        for name in ("revision_checks", "apply_checks"):
            original_checks.update({f"{name}: {key}": value for key, value in item.get(name, {}).items()})
        if scenario not in {5, 6}:
            for section in item.get("sections", []):
                if section.get("decision") == "UPDATE" and section.get("proposed_text") is not None:
                    key = f"{scenario}|{section['section_id']}"
                    review = section_reviews.get(key)
                    section["proposal_review"] = review
                    original_checks.update(review_checks(review, f"proposal review {key}"))
        if scenario == 5 and item.get("revision_checks"):
            revision_review = reviews.get("scenario_5_revision")
            if revision_review:
                item["revision_proposal_review"] = revision_review
                original_checks.update(review_checks(revision_review, "Scenario 5 revised proposal"))
            else:
                original_checks["Scenario 5 revised proposal: manual claim review present"] = False
        if item.get("status") == "PASS" and not all(original_checks.values()):
            item["status"] = "SEMANTIC_FAIL"
        if item.get("status") == "SEMANTIC_FAIL" and all(original_checks.values()):
            item["status"] = "PASS"
        item["checks"] = original_checks
        item["failed_checks"] = [name for name, passed in original_checks.items() if not passed]
        old = old_by_scenario.get(scenario, {})
        prior_baseline = baseline_by_scenario.get(scenario, {})
        revised_label = scenario == 4
        if item.get("status") in INFRASTRUCTURE_RESULTS or revised_label:
            regressed = None
        elif scenario == 5:
            regressed = prior_baseline.get("status") == "PASS" and not all(item.get("revision_checks", {}).values())
        else:
            regressed = prior_baseline.get("status") == "PASS" and item.get("status") != "PASS"
        prior_diagnosis: list[str] = []
        if scenario == 1:
            prior_diagnosis = [
                "The prior Phase 1.1 response returned UPDATE at case level, but its client-default section was NO_CHANGE and its QuickStart section was NO_CHANGE; both section checks failed.",
            ]
        elif scenario == 5:
            prior_diagnosis = [
                "The prior V2 text stated that the timeout does not represent an overall deadline for the complete HTTP request; the old phrase detector omitted 'does not represent', so only the 'requested feedback appears in V2' check failed.",
            ]
        item["prior_failure_diagnosis"] = prior_diagnosis
        original_benchmark.append({
            **item,
            "previous_result": old.get("status", "NOT_RECORDED"),
            "previous_decision": old.get("actual_decision", "NOT_RECORDED"),
            "new_result": item.get("status", "SYSTEM_ERROR"),
            "new_decision": item.get("actual_decision", "ERROR"),
            "accepted_phase1_baseline_result": prior_baseline.get("status", "NOT_RECORDED"),
            "behavior_regressed_vs_accepted_baseline": regressed,
            "label_revised": revised_label,
            "label_rationale": expectation_by_scenario.get(scenario, {}).get("label_rationale"),
        })

    decision_accuracy = {}
    semantic_heldout = [item for item in heldout_cases if item.get("status") in SEMANTIC_RESULTS]
    infra_heldout = [item for item in heldout_cases if item.get("status") in INFRASTRUCTURE_RESULTS]
    for decision in ("UPDATE", "NO_CHANGE", "UNCERTAIN"):
        group = [item for item in heldout_cases if item["expected_decision"] == decision]
        scored = [item for item in group if item.get("status") in SEMANTIC_RESULTS]
        correct = sum(item.get("actual_decision") == decision for item in scored)
        decision_accuracy[decision] = {
            "correct": correct,
            "scored": len(scored),
            "infrastructure_errors": sum(item.get("status") in INFRASTRUCTURE_RESULTS for item in group),
            "accuracy": correct / len(scored) if scored else None,
        }
    complete_scored = [item for item in semantic_heldout if item.get("actual_evidence_completeness") in {"COMPLETE", "PARTIAL", "INSUFFICIENT"}]
    complete_correct = sum(item["actual_evidence_completeness"] == item["expected_evidence_completeness"] for item in complete_scored)
    reviewed_proposals = [item for item in heldout_cases if item.get("actual_decision") == "UPDATE" and item.get("actual_proposed_text") is not None]
    proposal_reviews = [heldout_review.get(item["scenario_id"], {}) for item in reviewed_proposals]
    original_review_map = section_reviews
    scenarios_by_id = {int(item["scenario"]): item for item in original_benchmark}
    all_reviewed = proposal_reviews + [
        original_review_map.get(f"{item['scenario']}|{section['section_id']}", {})
        for item in original_benchmark
        if int(item["scenario"]) not in {5, 6}
        for section in item.get("sections", [])
        if section.get("decision") == "UPDATE" and section.get("proposed_text") is not None
    ]
    if scenarios_by_id.get(5, {}).get("revision_checks"):
        all_reviewed.append(reviews.get("scenario_5_revision", {}))
    if any(not review for review in all_reviewed):
        raise SystemExit("Claim review is missing for one or more proposed updates")
    proposal_safety = {
        "reviewed": len(all_reviewed),
        "supported": sum(
            review.get("proposal_factual_support") is True
            and review.get("safe_claims_supported") is True
            and review.get("unsupported_claim_violation") is False
            and review.get("rubric_satisfied") is True
            for review in all_reviewed
        ),
        "unsupported_claim_violations": sum(review.get("unsupported_claim_violation") is True for review in all_reviewed),
    }
    aggregation_checks = [item for item in heldout_cases if item.get("status") in SEMANTIC_RESULTS]
    aggregation_accuracy = {
        "correct": sum(item.get("checks", {}).get("application aggregation matches returned section decisions") is True for item in aggregation_checks),
        "scored": len(aggregation_checks),
    }
    hitl = {
        "scenario_5": "PASS" if all(scenarios_by_id.get(5, {}).get("revision_checks", {}).values()) else "SEMANTIC_FAIL",
        "scenario_6": "PASS" if all(scenarios_by_id.get(6, {}).get("revision_checks", {}).values()) and all(scenarios_by_id.get(6, {}).get("apply_checks", {}).values()) else "SEMANTIC_FAIL",
    }
    regressions = [item["scenario"] for item in original_benchmark if item.get("behavior_regressed_vs_accepted_baseline") is True]
    uncertainty = decision_accuracy["UNCERTAIN"]
    all_original_pass = all(item.get("status") == "PASS" for item in original_benchmark)
    no_claim_violations = proposal_safety["unsupported_claim_violations"] == 0
    if uncertainty["scored"] and uncertainty["accuracy"] == 1 and all_original_pass and no_claim_violations:
        freeze_decision = "Freeze Phase 1.1 reasoning contract and Phase 1; the genuine uncertainty case is recognized, partial-evidence updates are bounded, all original scenarios pass, and no proposal violated its frozen claim boundaries."
    else:
        freeze_decision = "Do not freeze the reasoning contract as calibrated; report the observed decision, completeness, claim-safety, and original-benchmark failures, then make any next change only as a separately scoped evaluation round."
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reasoning_contract": "impact.v4 / revision.v3",
        "heldout_expectation_sha256": manifest_hash,
        "heldout_adjudication_sha256": adjudication_hash,
        "heldout_fixture_manifest_sha256": fixture_hash,
        "original_expectations_sha256": expectations_hash,
        "heldout_expectations_frozen_before_calls": True,
        "run_notes": [
            "The original six were run once against original_expectations.json; the independent held-out manifest did not enter their model prompts.",
            "All 11 held-out cases were called once after the final labels and fixture commits passed SHA-256 preflight. H5-H11 labels were not revised after this run.",
            "Scenario 5's saved V2 text was re-scored offline after replacing a phrase-only deadline check with a generic negated-total-duration check; no Sarvam call was repeated.",
            "The proposal-presence check is evaluated against the model's actual section decision, while expected-decision correctness is scored separately.",
        ],
        "original_benchmark": original_benchmark,
        "heldout_cases": heldout_cases,
        "decision_accuracy": decision_accuracy,
        "evidence_completeness_accuracy": {
            "correct": complete_correct,
            "scored": len(complete_scored),
            "accuracy": complete_correct / len(complete_scored) if complete_scored else 0.0,
            "infrastructure_errors": len(infra_heldout),
        },
        "proposal_safety": proposal_safety,
        "aggregation_accuracy": aggregation_accuracy,
        "hitl": hitl,
        "regressions": regressions,
        "phase1_freeze_decision": freeze_decision,
        "limitations": [
            "The held-out set has 11 controlled cases and four genuine UNCERTAIN cases. This remains a small synthetic evaluation and does not establish a calibrated error rate.",
            "The evaluation uses one Sarvam model and one repository-shaped fixture set; it does not establish performance across projects, languages, dependency graphs, or runtime environments.",
            "Claim support is a documented manual review against the pre-call frozen claims and proposal rubrics.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine frozen Phase 1.1 labels, live results, and post-call claim reviews")
    parser.add_argument("--manifest", type=Path, default=ROOT / "evals" / "phase1_1" / "heldout_manifest.json")
    parser.add_argument("--manifest-sha256", type=Path, default=ROOT / "evals" / "phase1_1" / "heldout_manifest.sha256")
    parser.add_argument("--adjudication", type=Path, default=ROOT / "evals" / "phase1_1" / "heldout_adjudication.md")
    parser.add_argument("--adjudication-sha256", type=Path, default=ROOT / "evals" / "phase1_1" / "heldout_adjudication.sha256")
    parser.add_argument("--generated-manifest", type=Path, default=ROOT / "evals" / "phase1_1" / "fixture_commits.json")
    parser.add_argument("--generated-manifest-sha256", type=Path, default=ROOT / "evals" / "phase1_1" / "fixture_commits.sha256")
    parser.add_argument("--original-expectations", type=Path, default=ROOT / "evals" / "phase1_1" / "original_expectations.json")
    parser.add_argument("--original-expectations-sha256", type=Path, default=ROOT / "evals" / "phase1_1" / "original_expectations.sha256")
    parser.add_argument("--heldout-results", type=Path, default=ROOT / "evals" / "phase1_1" / "heldout-results-v2.json")
    parser.add_argument("--original-results", type=Path, default=ROOT / "evals" / "phase1_1" / "original-benchmark-v2.json")
    parser.add_argument("--previous-original", type=Path, default=ROOT / "evals" / "phase1_1" / "original-benchmark.json")
    parser.add_argument("--accepted-baseline", type=Path, default=ROOT / "evals" / "httpx" / "phase1-live-report.json")
    parser.add_argument("--claim-reviews", type=Path, default=ROOT / "evals" / "phase1_1" / "claim-reviews-v2.json")
    parser.add_argument("--out", type=Path, default=ROOT / "evals" / "phase1_1" / "report-v2.md")
    args = parser.parse_args()
    report = finalize(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    args.out.write_text(markdown(report), encoding="utf-8")
    print(f"Markdown report: {args.out}")
    print(f"JSON report: {args.out.with_suffix('.json')}")


if __name__ == "__main__":
    main()
