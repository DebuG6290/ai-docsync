from __future__ import annotations

import json
from pathlib import Path

from docsync.errors import MappingError, ModelError
from docsync.models import (
    Decision,
    ImpactResponse,
    MappingSuggestionResponse,
    RevisionResponse,
)
from docsync.repository.git_reader import changed_python_symbols, read_file, resolve_commit
from docsync.repository.markdown_sections import parse_sections, to_doc_section
from docsync.sarvam import ModelClient, SarvamClient
from docsync.store import Store

IMPACT_SYSTEM = """You review whether a code change requires documentation changes. You own the semantic decision for each supplied documentation section. Approved mappings identify candidates only; they do not imply impact. Compare old and new code, the Git diff, and the current text. Return exactly one result for every supplied section_id, with no duplicates or other IDs. Do not return an independent case-level decision; the application derives the workflow state from the section decisions.

Choose UPDATE when the current section contains a statement that should change based on the supplied evidence and at least one useful replacement can be written without inventing facts. The complete downstream or runtime behavior does not need to be known. A bounded statement about a directly visible configuration source or delegated call may be useful when its runtime value or implementation is unavailable.

Choose NO_CHANGE only when the supplied evidence supports that the current section remains accurate and no useful change is needed. Choose UNCERTAIN when the evidence cannot establish whether the current section remains accurate, or when no useful replacement can be written without unsupported claims. Unknown downstream detail alone is not a reason to choose UNCERTAIN if a useful, directly supported update is available.

For each section, classify evidence_completeness independently of the decision: COMPLETE means the relevant behavior needed for this section is established; PARTIAL means some relevant value or downstream behavior is unknown but a safe decision or bounded update may still be possible; INSUFFICIENT means the evidence cannot establish whether the current section is accurate or support a useful replacement. List specific missing_information. List concise, atomic safe_claims supported by the supplied code/evidence, and plausible but unsupported_claims that must not be asserted. Every factual statement in proposed_text must be supported by one or more safe_claims. For UPDATE, make the smallest useful edit, preserve correct details and style, and cite concrete code_evidence. For NO_CHANGE and UNCERTAIN, proposed_text must be null. Do not fabricate behavior for unavailable functions, services, configuration, runtime policies, or dependencies."""

REVISION_SYSTEM = """Revise only the named proposal in response to the reviewer's rejection. Use the supplied section evidence assessment: every factual statement in revised text must be supported by safe_claims, and do not assert unsupported_claims. The reviewer request does not establish a fact that is absent from the supplied code. Preserve accurate current documentation, keep the smallest useful change, and do not alter any other section. Return the revised text, reason, code evidence, evidence_completeness, missing_information, safe_claims, and unsupported_claims for the revised proposal."""

MAPPING_SYSTEM = """Suggest candidate links between code symbols and documentation sections. This is only candidate selection, not a decision that documentation is impacted. Return only plausible pairs supported by the supplied text, with a short reason. A human must confirm each suggestion before analysis can use it."""

MAPPING_PROMPT_VERSION = "mapping.v2"
IMPACT_PROMPT_VERSION = "impact.v4"
REVISION_PROMPT_VERSION = "revision.v3"

# Bound output scope, not semantic reasoning. Full input context remains available.
IMPACT_MAX_SECTIONS_PER_CALL = 1
IMPACT_BATCH_SCOPE = "\n\nAssess exactly the sections in the sections array. related_documentation_sections is read-only context; do not return assessments for those sections."


def suggest_mappings(
    client: ModelClient,
    code_symbols: list[dict],
    sections: list[dict],
    store: Store | None = None,
) -> list[dict]:
    user = json.dumps({"code_symbols": code_symbols, "documentation_sections": sections}, ensure_ascii=False)
    valid_code = {item["code_id"] for item in code_symbols}
    valid_sections = {item["section_id"] for item in sections}

    def validate(result: MappingSuggestionResponse) -> str | None:
        seen: set[tuple[str, str]] = set()
        for suggestion in result.suggestions:
            pair = (suggestion.code_id, suggestion.section_id)
            if suggestion.code_id not in valid_code or suggestion.section_id not in valid_sections:
                return "Sarvam mapping suggestion referenced an identity outside the supplied candidates"
            if pair in seen:
                return "Sarvam mapping suggestions contained a duplicate candidate pair"
            if not suggestion.reason.strip():
                return "Sarvam returned a mapping suggestion without a reason"
            seen.add(pair)
        return None

    result = client.structured(
        MAPPING_SYSTEM,
        user,
        MappingSuggestionResponse,
        "mapping_suggestions",
        operation="mapping",
        prompt_version=MAPPING_PROMPT_VERSION,
        candidate_section_ids=sorted(valid_sections),
        diagnostic_sink=(lambda entry: store.event("sarvam_call", entry)) if store else None,
        contract_validator=validate,
    )
    return [item.model_dump() for item in result.suggestions]


def _section_context(repo: Path, new_sha: str, section_id: str) -> dict:
    path, _, _slug = section_id.partition("::")
    doc_text = read_file(repo, new_sha, path)
    if doc_text is None:
        raise MappingError(f"Mapped documentation file {path} does not exist at {new_sha}")
    sections = parse_sections(path, doc_text)
    found = next((s for s in sections if s.section_id == section_id), None)
    if found is None:
        raise MappingError(f"Mapped section {section_id} not found at {new_sha}")
    return {**to_doc_section(found).model_dump(), "start_line": found.start_line, "end_line": found.end_line}


def aggregate_case_decision(sections: list) -> Decision:
    """Derive the workflow decision from section outcomes; this is not semantic reasoning."""
    decisions = {
        Decision(section.decision if hasattr(section, "decision") else section)
        for section in sections
    }
    if Decision.UPDATE in decisions:
        return Decision.UPDATE
    if Decision.UNCERTAIN in decisions:
        return Decision.UNCERTAIN
    return Decision.NO_CHANGE


def analyze(repo: Path, old_rev: str, new_rev: str, store: Store, client: ModelClient | None = None, *,
            max_sections_per_call: int = IMPACT_MAX_SECTIONS_PER_CALL) -> tuple[str, Decision]:
    if type(max_sections_per_call) is not int or max_sections_per_call < 1:
        raise ValueError("max_sections_per_call must be a positive integer")
    repo = repo.resolve()
    old_sha = resolve_commit(repo, old_rev)
    new_sha = resolve_commit(repo, new_rev)
    client = client or SarvamClient()
    changes = changed_python_symbols(repo, old_sha, new_sha)
    maps = store.mappings_for({c.code_id for c in changes})
    if not maps:
        raise MappingError("No approved mappings match the changed Python symbols; suggest and confirm mappings first")
    mapped_ids = {m["section_id"] for m in maps}
    sections = [_section_context(repo, new_sha, sid) for sid in sorted(mapped_ids)]
    case_data = {
        "repo_root": str(repo),
        "old_sha": old_sha,
        "new_sha": new_sha,
        "changes": [item.model_dump() for item in changes],
        "mappings": [dict(m) for m in maps],
        "sections": sections,
    }
    case_id = store.create_case(case_data)
    try:
        expected = {s["section_id"] for s in sections}

        def validate(result: ImpactResponse, required: set[str]) -> str | None:
            if not result.summary.strip():
                return "Sarvam returned an empty impact summary"
            observed = [s.section_id for s in result.sections]
            if set(observed) != required or len(observed) != len(required):
                missing = sorted(required - set(observed))
                unknown = sorted(set(observed) - required)
                duplicates = sorted({sid for sid in observed if observed.count(sid) > 1})
                return (
                    "Impact response section_id contract failed: "
                    f"expected exactly {sorted(required)}, observed {observed}, "
                    f"missing={missing}, unknown={unknown}, duplicates={duplicates}"
                )
            for item in result.sections:
                if not item.reason.strip():
                    return f"Sarvam omitted the reason for {item.section_id}"
                if item.decision == Decision.UPDATE:
                    if item.proposed_text is None:
                        return f"Sarvam marked {item.section_id} UPDATE without proposed_text"
                    if not item.code_evidence:
                        return f"Sarvam marked {item.section_id} UPDATE without code evidence"
                    if not item.safe_claims:
                        return f"Sarvam marked {item.section_id} UPDATE without safe_claims"
                elif item.proposed_text is not None:
                    return f"Sarvam proposed text for non-UPDATE section {item.section_id}"
                if item.decision == Decision.UNCERTAIN and not item.missing_information:
                    return f"Sarvam marked {item.section_id} UNCERTAIN without identifying missing information"
            return None

        batches = [sections[i:i + max_sections_per_call] for i in range(0, len(sections), max_sections_per_call)]
        store.event("impact_batch_plan", {"total_candidate_sections": len(sections), "batch_count": len(batches),
            "max_sections_per_call": max_sections_per_call,
            "batches": [{"batch_number": i, "section_ids": [s['section_id'] for s in batch]}
                for i, batch in enumerate(batches, 1)]}, case_id)
        outcomes = []
        summaries = []
        for number, batch in enumerate(batches, 1):
            required = {s['section_id'] for s in batch}
            metadata = {"total_candidate_sections": len(sections), "batch_count": len(batches),
                "batch_number": number, "batch_section_ids": sorted(required), "batch_scope_version": "sections.v1"}
            context = {**case_data, "sections": batch}
            if len(batches) > 1:
                context['related_documentation_sections'] = [s for s in sections if s['section_id'] not in required]
            store.event("impact_batch_started", metadata, case_id)
            try:
                response = client.structured(
                    IMPACT_SYSTEM + (IMPACT_BATCH_SCOPE if len(batches) > 1 else ""),
                    json.dumps(context, ensure_ascii=False), ImpactResponse, "impact_analysis",
                    operation="impact", prompt_version=IMPACT_PROMPT_VERSION,
                    candidate_section_ids=sorted(required),
                    diagnostic_sink=lambda entry: store.event("sarvam_call", {**entry, **metadata,
                        "attempt_count": entry['retry_count'] + 1}, case_id),
                    contract_validator=lambda response: validate(response, required),
                )
            except Exception as exc:
                store.event("impact_batch_failed", {**metadata, "error_type": type(exc).__name__}, case_id)
                raise
            outcomes.extend(response.sections)
            summaries.append(response.summary)
            store.event("impact_batch_completed", metadata, case_id)
        # No proposals or review assessments are persisted until every batch passes.
        result = ImpactResponse(summary="\n\n".join(summaries), sections=outcomes)
        contract_error = validate(result, expected)
        if contract_error:
            raise ModelError(contract_error)
        case_decision = aggregate_case_decision(result.sections)
        store.event(
            "case_workflow_aggregation",
            {
                "section_decisions": {item.section_id: item.decision.value for item in result.sections},
                "derived_workflow_state": case_decision.value,
            },
            case_id,
        )
        store.event("sarvam_response_metadata", {"model": getattr(client, "model", type(client).__name__), "endpoint": "https://api.sarvam.ai/v1/chat/completions"}, case_id)
        for section_result in result.sections:
            if section_result.decision == Decision.UPDATE:
                store.add_proposal(case_id, section_result.section_id, section_result.proposed_text or "", section_result.reason, section_result.code_evidence)
            store.event("section_decision", section_result.model_dump(mode="json"), case_id)
        store.set_case_result(case_id, case_decision.value, result.summary, "READY")
        return case_id, case_decision
    except ModelError as exc:
        store.set_case_error(case_id, str(exc))
        store.event("model_error", {"error": str(exc), "error_category": exc.category}, case_id)
        raise
    except Exception as exc:
        store.set_case_error(case_id, f"{type(exc).__name__}: {exc}")
        store.event("analysis_system_error", {"error_type": type(exc).__name__}, case_id)
        raise


def revise_rejected(store: Store, proposal_id: str, reason: str, client: ModelClient | None = None) -> str:
    context = store.proposal_context(proposal_id)
    proposal = context["proposal"]
    if proposal["status"] in {"ACCEPTED", "APPLIED"}:
        raise ValueError("An accepted/applied proposal cannot be revised")
    client = client or SarvamClient()
    versions = [dict(v) for v in context["versions"]]
    user_context = {
        "code_context": context["case"]["changes"],
        "git_diff": [c["diff"] for c in context["case"]["changes"]],
        "current_approved_documentation": context["section"],
        "target_section_id": proposal["section_id"],
        "previous_proposals_and_revision_history": versions,
        "reviewer_rejection_reason": reason,
        "section_evidence_assessment": _latest_section_assessment(
            store, proposal["case_id"], proposal["section_id"], proposal_id
        ),
    }
    try:
        def validate(result: RevisionResponse) -> str | None:
            if result.section_id != proposal["section_id"]:
                return "Sarvam revision referenced a different section; preserving current proposal"
            if not result.reason.strip() or not result.code_evidence or not result.safe_claims:
                return "Sarvam revision omitted its reason, code evidence, or safe claims; preserving prior proposal"
            return None

        revised = client.structured(
            REVISION_SYSTEM,
            json.dumps(user_context, ensure_ascii=False),
            RevisionResponse,
            "proposal_revision",
            operation="revision",
            prompt_version=REVISION_PROMPT_VERSION,
            candidate_section_ids=[proposal["section_id"]],
            diagnostic_sink=lambda entry: store.event("sarvam_call", entry, proposal["case_id"]),
            contract_validator=validate,
        )
    except ModelError as exc:
        store.event(
            "model_revision_error",
            {"proposal_id": proposal_id, "error": str(exc), "error_category": exc.category},
            proposal["case_id"],
        )
        store.set_proposal_status(proposal_id, "REVISION_ERROR")
        raise
    version_id = store.add_version(proposal_id, revised.proposed_text, revised.reason, revised.code_evidence, "sarvam")
    store.event(
        "proposal_revision_assessment",
        {
            "proposal_id": proposal_id,
            "section_id": proposal["section_id"],
            "version_id": version_id,
            "evidence_completeness": revised.evidence_completeness.value,
            "missing_information": revised.missing_information,
            "safe_claims": revised.safe_claims,
            "unsupported_claims": revised.unsupported_claims,
        },
        proposal["case_id"],
    )
    store.event("sarvam_revision_metadata", {"proposal_id": proposal_id, "model": getattr(client, "model", type(client).__name__)}, proposal["case_id"])
    return version_id


def _latest_section_assessment(
    store: Store,
    case_id: str,
    section_id: str,
    proposal_id: str,
) -> dict | None:
    latest = None
    for row in store.audit(case_id):
        payload = json.loads(row["payload_json"])
        if row["kind"] == "section_decision" and payload.get("section_id") == section_id:
            latest = payload
        elif (
            row["kind"] == "proposal_revision_assessment"
            and payload.get("proposal_id") == proposal_id
        ):
            latest = payload
    return latest

