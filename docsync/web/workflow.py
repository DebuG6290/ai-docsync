from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from docsync.store import Store
from docsync.web.models import (
    AuditEvent,
    ChangeCase,
    CodeDocMapping,
    GitHubDelivery,
    Proposal,
    ProposalVersion,
    Repository,
    ReviewAction,
    SarvamCall,
    SectionAssessment,
    uid,
)
from docsync.web.repository import enqueue


def audit(session: Session, kind: str, payload: dict, case_id: str | None = None) -> None:
    session.add(AuditEvent(case_id=case_id, kind=kind, payload=payload))


def approved_mappings(session: Session, repo_id: str) -> list[dict]:
    rows = session.scalars(
        select(CodeDocMapping)
        .where(CodeDocMapping.repo_id == repo_id, CodeDocMapping.status == "APPROVED")
        .order_by(CodeDocMapping.code_id, CodeDocMapping.section_id, CodeDocMapping.version.desc())
    ).all()
    latest: dict[tuple[str, str], CodeDocMapping] = {}
    for row in rows:
        latest.setdefault((row.code_id, row.section_id), row)
    return [
        {"code_id": row.code_id, "section_id": row.section_id, "reason": row.reason}
        for row in latest.values()
    ]


def start_case(session: Session, repo: Repository, delivery_id: str, before: str, after: str) -> ChangeCase:
    existing = session.scalar(
        select(ChangeCase).where(
            (ChangeCase.delivery_id == delivery_id)
            | ((ChangeCase.repo_id == repo.id) & (ChangeCase.before_sha == before) & (ChangeCase.after_sha == after))
        )
    )
    if existing is not None:
        return existing
    case = ChangeCase(
        repo_id=repo.id,
        delivery_id=delivery_id,
        before_sha=before,
        after_sha=after,
        status="ANALYZING",
        case_data={"repo_root": "", "old_sha": before, "new_sha": after, "changes": [], "mappings": [], "sections": []},
    )
    session.add(case)
    session.flush()
    audit(session, "github_commit_received", {"before_sha": before, "after_sha": after, "repository": repo.full_name}, case.id)
    audit(session, "analysis_started", {"source": "github_push"}, case.id)
    session.commit()
    return case


def _plain(value):
    if isinstance(value, dict):
        return {
            key: _plain(item)
            for key, item in value.items()
            if not any(word in key.casefold() for word in ("api_key", "authorization", "secret", "private_key"))
        }
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def persist_analysis(
    session: Session,
    case_id: str,
    delivery_id: str,
    local: Store,
    local_case_id: str,
) -> None:
    online = session.get(ChangeCase, case_id)
    source = local.case(local_case_id)
    if online is None or source is None:
        raise ValueError("The analysis case disappeared before persistence")
    snapshot = local.case_snapshot(local_case_id)
    snapshot['context_provenance'] = online.case_data.get('context_provenance', {})
    snapshot["repo_root"] = ""
    online.case_data = snapshot
    online.decision = source["decision"]
    online.summary = source["summary"]
    online.status = "NEEDS_TRIAGE" if source["decision"] == "UNCERTAIN" else (
        "NO_CHANGE" if source["decision"] == "NO_CHANGE" else "READY_FOR_REVIEW"
    )

    assessments: dict[str, dict] = {}
    local_events = local.audit(local_case_id)
    for event in local_events:
        payload = json.loads(event["payload_json"])
        if event["kind"] == "section_decision":
            assessments[payload["section_id"]] = payload
    sections_by_id = {section["section_id"]: section for section in snapshot["sections"]}
    for section_id, result in assessments.items():
        section = sections_by_id[section_id]
        session.add(
            SectionAssessment(
                case_id=case_id,
                section_id=section_id,
                path=section["path"],
                heading=section["heading"],
                current_text=section["text"],
                base_sha256=section["sha256"],
                start_line=section["start_line"],
                end_line=section["end_line"],
                decision=result["decision"],
                rationale=result["reason"],
                evidence_completeness=result["evidence_completeness"],
                code_evidence=result["code_evidence"],
                missing_information=result["missing_information"],
                safe_claims=result["safe_claims"],
                unsupported_claims=result["unsupported_claims"],
                proposed_text=result["proposed_text"],
            )
        )

    proposals = local.proposals(local_case_id)
    for old_proposal in proposals:
        proposal = Proposal(case_id=case_id, section_id=old_proposal["section_id"], status="PENDING")
        session.add(proposal)
        session.flush()
        assessment = assessments.get(old_proposal["section_id"], {})
        for version in local.versions(old_proposal["id"]):
            evidence = json.loads(version["code_evidence_json"])
            session.add(
                ProposalVersion(
                    proposal_id=proposal.id,
                    version=version["version"],
                    author=version["author"],
                    proposed_text=version["proposed_text"],
                    reason=version["reason"],
                    code_evidence=evidence,
                    evidence_completeness=assessment.get("evidence_completeness"),
                    missing_information=assessment.get("missing_information", []),
                    safe_claims=assessment.get("safe_claims", []),
                    unsupported_claims=assessment.get("unsupported_claims", []),
                )
            )

    for event in local_events:
        payload = _plain(json.loads(event["payload_json"]))
        kind = event["kind"]
        if kind == "sarvam_call":
            session.add(
                SarvamCall(
                    case_id=case_id,
                    operation=payload.get("operation", "impact"),
                    metadata_json=payload,
                )
            )
        if kind in {
            "mapping_imported_as_confirmed", "case_created", "sarvam_call", "impact_decision",
            "case_workflow_aggregation", "sarvam_response_metadata", "proposal_created",
            "proposal_version_created", "section_decision", "proposal_revision_assessment",
        }:
            audit(session, kind, payload, case_id)
    delivery = session.get(GitHubDelivery, delivery_id)
    if delivery is not None:
        delivery.status = "PROCESSED"
    audit(
        session,
        "analysis_completed",
        {"decision": online.decision, "section_count": len(assessments), "proposal_count": len(proposals)},
        case_id,
    )
    session.commit()


def persist_analysis_error(
    session: Session,
    case_id: str,
    delivery_id: str,
    error: Exception,
    local: Store | None = None,
    local_case_id: str | None = None,
) -> None:
    case = session.get(ChangeCase, case_id)
    if case is not None:
        case.status = "ERROR"
        case.error = f"{type(error).__name__}: {str(error)[:1000]}"
        audit(session, "analysis_error", {"error_type": type(error).__name__, "message": str(error)[:500]}, case_id)
        if local is not None:
            if local_case_id is None:
                row = local.db.execute("SELECT id FROM cases ORDER BY created_at DESC LIMIT 1").fetchone()
                local_case_id = row["id"] if row else None
            if local_case_id:
                for event in local.audit(local_case_id):
                    if event["kind"] == "sarvam_call":
                        payload = _plain(json.loads(event["payload_json"]))
                        session.add(SarvamCall(case_id=case_id, operation=payload.get("operation", "impact"), metadata_json=payload))
                        audit(session, "sarvam_call", payload, case_id)
    delivery = session.get(GitHubDelivery, delivery_id)
    if delivery is not None:
        delivery.status = "ERROR"
    session.commit()


def _latest(session: Session, proposal_id: str) -> ProposalVersion:
    value = session.scalar(
        select(ProposalVersion)
        .where(ProposalVersion.proposal_id == proposal_id)
        .order_by(ProposalVersion.version.desc())
        .limit(1)
    )
    if value is None:
        raise ValueError("Proposal has no stored version")
    return value


def _maybe_queue_publication(session: Session, case: ChangeCase) -> None:
    proposals = session.scalars(select(Proposal).where(Proposal.case_id == case.id)).all()
    unresolved = session.scalar(
        select(SectionAssessment.id).where(
            SectionAssessment.case_id == case.id,
            SectionAssessment.decision == "UNCERTAIN",
            SectionAssessment.human_resolution.is_(None),
        ).limit(1)
    )
    if unresolved:
        case.status = "NEEDS_TRIAGE"
        return
    if proposals and all(item.status == "ACCEPTED" for item in proposals):
        if case.status not in {"PUBLISH_QUEUED", "PUBLISHING", "WAITING_MERGE", "INDEXED"}:
            repo = session.get(Repository, case.repo_id)
            enqueue(session, repo.id, "publish_docs", {"case_id": case.id})
            case.status = "PUBLISH_QUEUED"
            audit(session, "approval_complete", {"proposal_count": len(proposals)}, case.id)
    elif not proposals:
        case.status = "REVIEWED" if case.decision == "NO_CHANGE" else "NEEDS_TRIAGE"
    else:
        case.status = "READY_FOR_REVIEW"


def _review_target(session, proposal_id, expected_version_id=None):
    proposal = session.scalar(select(Proposal).where(Proposal.id == proposal_id).with_for_update())
    if proposal is None:
        raise ValueError("Unknown proposal")
    session.scalar(select(ChangeCase).where(ChangeCase.id == proposal.case_id).with_for_update())
    latest = _latest(session, proposal_id)
    if expected_version_id and latest.id != expected_version_id:
        raise ValueError("Proposal changed since it was displayed; refresh before reviewing")
    if proposal.status == "REVISING":
        raise ValueError("Revision is already in progress")
    return proposal


def accept_proposal(session: Session, proposal_id: str, expected_version_id: str | None = None) -> None:
    proposal = _review_target(session, proposal_id, expected_version_id)
    if proposal is None:
        raise ValueError("Unknown proposal")
    latest = _latest(session, proposal_id)
    if proposal.status == "ACCEPTED":
        raise ValueError("This proposal version has already been accepted")
    proposal.status = "ACCEPTED"
    proposal.accepted_version_id = latest.id
    session.add(ReviewAction(proposal_id=proposal.id, action="ACCEPT", version_id=latest.id))
    audit(session, "review_accept", {"proposal_id": proposal.id, "version_id": latest.id, "version": latest.version}, proposal.case_id)
    case = session.get(ChangeCase, proposal.case_id)
    _maybe_queue_publication(session, case)
    session.commit()


def modify_proposal(session: Session, proposal_id: str, content: str, expected_version_id: str | None = None) -> ProposalVersion:
    proposal = _review_target(session, proposal_id, expected_version_id)
    if not content.strip():
        raise ValueError("Documentation text is required")
    if proposal is None:
        raise ValueError("Unknown proposal")
    if proposal.status in {"ACCEPTED", "APPLIED"}:
        raise ValueError("An accepted proposal cannot be modified")
    latest = _latest(session, proposal_id)
    version = ProposalVersion(
        proposal_id=proposal.id,
        version=latest.version + 1,
        author="human",
        human_modified=True,
        proposed_text=content,
        reason="Human-authored modification",
        code_evidence=[],
        evidence_completeness=None,
        missing_information=[],
        safe_claims=[],
        unsupported_claims=[],
    )
    session.add(version)
    session.flush()
    proposal.status = "PENDING"
    proposal.accepted_version_id = None
    session.add(ReviewAction(proposal_id=proposal.id, action="MODIFY", version_id=version.id, content=content))
    audit(session, "review_modify", {"proposal_id": proposal.id, "version_id": version.id, "version": version.version, "author": "human"}, proposal.case_id)
    case = session.get(ChangeCase, proposal.case_id)
    case.status = "READY_FOR_REVIEW"
    session.commit()
    return version


def reject_proposal(session: Session, proposal_id: str, reason: str, expected_version_id: str | None = None) -> None:
    proposal = _review_target(session, proposal_id, expected_version_id)
    if proposal is None:
        raise ValueError("Unknown proposal")
    if not reason.strip():
        raise ValueError("A rejection reason is required")
    if proposal.status in {"ACCEPTED", "APPLIED"}:
        raise ValueError("An accepted proposal cannot be rejected")
    latest = _latest(session, proposal_id)
    session.add(ReviewAction(proposal_id=proposal.id, action="REJECT", version_id=latest.id, reason=reason))
    proposal.status = "REVISING"
    proposal.accepted_version_id = None
    repo = session.get(Repository, session.get(ChangeCase, proposal.case_id).repo_id)
    enqueue(session, repo.id, "revise_proposal", {"proposal_id": proposal.id, "reason": reason, "source_version_id": latest.id})
    audit(session, "review_reject", {"proposal_id": proposal.id, "version_id": latest.id, "reason": reason}, proposal.case_id)
    session.commit()


def triage_section(session: Session, section_id: str, resolution: str, reason: str, content: str = "") -> None:
    section = session.scalar(select(SectionAssessment).where(SectionAssessment.id == section_id).with_for_update())
    if section is None or section.decision != "UNCERTAIN":
        raise ValueError("This section is not awaiting uncertainty triage")
    if section.human_resolution:
        raise ValueError("This uncertainty has already been resolved")
    if not reason.strip():
        raise ValueError("A triage reason is required")
    if resolution not in {"NO_CHANGE", "HUMAN_UPDATE"}:
        raise ValueError("Choose NO_CHANGE or HUMAN_UPDATE")
    case = session.scalar(select(ChangeCase).where(ChangeCase.id == section.case_id).with_for_update())
    section.human_resolution = resolution
    section.triage_reason = reason
    if resolution == "HUMAN_UPDATE":
        if not content.strip():
            raise ValueError("Human documentation text is required for HUMAN_UPDATE")
        existing = session.scalar(
            select(Proposal).where(Proposal.case_id == case.id, Proposal.section_id == section.section_id)
        )
        if existing is not None:
            raise ValueError("A proposal already exists for this section")
        proposal = Proposal(case_id=case.id, section_id=section.section_id, status="PENDING")
        session.add(proposal)
        session.flush()
        version = ProposalVersion(
            proposal_id=proposal.id,
            version=1,
            author="human",
            human_modified=True,
            proposed_text=content,
            reason=reason,
            code_evidence=[],
            evidence_completeness=None,
            missing_information=section.missing_information,
            safe_claims=[],
            unsupported_claims=[],
        )
        session.add(version)
        session.flush()
        audit(session, "uncertainty_triaged_to_human_update", {"section_id": section.section_id, "proposal_id": proposal.id, "version_id": version.id, "reason": reason}, case.id)
    else:
        audit(session, "uncertainty_triaged_no_change", {"section_id": section.section_id, "reason": reason}, case.id)
    _maybe_queue_publication(session, case)
    session.commit()


def local_store_from_online(session: Session, case: ChangeCase, root: Path) -> tuple[Store, str, dict[str, str]]:
    """Rehydrate the accepted online versions into the proven Phase 1 apply/revision store."""
    snapshot = dict(case.case_data)
    snapshot["repo_root"] = str(root)
    store = Store(root / ".docsync-phase1-bridge.sqlite3")
    local_case_id = store.create_case(snapshot)
    store.set_case_result(local_case_id, case.decision or "UPDATE", case.summary or "", case.status)
    for assessment in session.scalars(
        select(SectionAssessment).where(SectionAssessment.case_id == case.id)
    ).all():
        payload = {
            "section_id": assessment.section_id,
            "decision": assessment.decision,
            "proposed_text": assessment.proposed_text,
            "reason": assessment.rationale,
            "code_evidence": assessment.code_evidence,
            "evidence_completeness": assessment.evidence_completeness,
            "missing_information": assessment.missing_information,
            "safe_claims": assessment.safe_claims,
            "unsupported_claims": assessment.unsupported_claims,
        }
        store.event("section_decision", payload, local_case_id)
    local_ids: dict[str, str] = {}
    for proposal in session.scalars(select(Proposal).where(Proposal.case_id == case.id)).all():
        versions = session.scalars(
            select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id).order_by(ProposalVersion.version)
        ).all()
        if not versions:
            continue
        first, *rest = versions
        local_proposal_id = store.add_proposal(
            local_case_id, proposal.section_id, first.proposed_text, first.reason,
            first.code_evidence, author=first.author,
        )
        for version in rest:
            store.add_version(local_proposal_id, version.proposed_text, version.reason, version.code_evidence, version.author)
        local_ids[proposal.id] = local_proposal_id
    return store, local_case_id, local_ids
