"""Finite operation handlers. Polling main is legacy local compatibility only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from docsync.apply import apply_case
from docsync.engine import analyze, revise_rejected
from docsync.errors import ConflictError
from docsync.repository.markdown_sections import parse_sections, section_sha256
from docsync.sarvam import SarvamClient
from docsync.store import Store
from docsync.web.config import Settings, get_settings
from docsync.web.database import initialize_database, make_engine, session_factory
from docsync.web.embeddings import SentenceEmbedder
from docsync.web.github import GitHubClient, GitHubError, cloned_repository
from docsync.web.indexing import IndexInput, replace_approved_sections, prepared_embeddings
from docsync.web.models import (
    AuditEvent,
    ChangeCase,
    DocumentationRelease,
    GitHubDelivery,
    IndexedSection,
    KnowledgeVersion,
    Job,
    Proposal,
    ProposalVersion,
    ReleaseSection,
    Repository,
    ReviewAction,
    SarvamCall,
    SectionAssessment,
    utcnow,
)
from docsync.web.workflow import (
    audit,
    approved_mappings,
    local_store_from_online,
    persist_analysis,
    persist_analysis_error,
    start_case,
)


def _token(github: GitHubClient, repo: Repository) -> str:
    if github.settings.github_token:
        return github.settings.github_token
    if repo.installation_id is None:
        raise GitHubError("GitHub installation ID has not been recorded; set GITHUB_INSTALLATION_ID")
    return github.installation_token(repo.installation_id)


def _process_analysis(engine, settings: Settings, job: Job) -> None:
    factory = session_factory(engine)
    with factory() as session:
        delivery = session.get(GitHubDelivery, job.delivery_id)
        repo = session.get(Repository, job.repo_id)
        if delivery is None or repo is None:
            raise ValueError("GitHub delivery or repository record is missing")
        before, after = job.payload["before_sha"], job.payload["after_sha"]
        case = start_case(session, repo, delivery.delivery_id, before, after)
        case_id = case.id
        case.case_data = {**case.case_data, 'context_provenance': job.payload.get('approved_documentation_commits', {})}
        session.commit()
        mappings = approved_mappings(session, repo.id)
    github = GitHubClient(settings)
    local = None
    local_case_id = None
    error_persisted = False
    try:
        token = _token(github, repo)
        with cloned_repository(repo.full_name, token, before, after) as (root, _git, _env):
            local_path = root.parent / f"phase1-{case_id}.sqlite3"
            local = Store(local_path)
            try:
                for mapping in mappings:
                    local.add_confirmed_mapping(mapping["code_id"], mapping["section_id"], mapping["reason"])
                local_case_id, _decision = analyze(
                    root, before, after, local, SarvamClient(settings.sarvam_model)
                )
                with factory() as persist_session:
                    persist_analysis(persist_session, case_id, delivery.delivery_id, local, local_case_id)
            except Exception as exc:
                with factory() as error_session:
                    persist_analysis_error(error_session, case_id, delivery.delivery_id, exc, local, local_case_id)
                error_persisted = True
                raise
            finally:
                local.db.close()
                local = None
    except Exception as exc:
        if not error_persisted:
            with factory() as error_session:
                persist_analysis_error(error_session, case_id, delivery.delivery_id, exc)
        raise
    finally:
        github.close()


def _assessment_payload(assessment: SectionAssessment) -> dict:
    return {
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


def _process_revision(engine, settings: Settings, job: Job) -> None:
    factory = session_factory(engine)
    with factory() as session:
        proposal = session.get(Proposal, job.payload["proposal_id"])
        if proposal is None:
            raise ValueError("Proposal for revision no longer exists")
        case = session.get(ChangeCase, proposal.case_id)
        reason = job.payload["reason"]
        proposal.status = "REVISING"
        session.commit()
        with tempfile.TemporaryDirectory(prefix="docsync-revision-") as directory:
            local, local_case_id, proposal_ids = local_store_from_online(session, case, Path(directory))
            local_proposal_id = proposal_ids.get(proposal.id)
            if not local_proposal_id:
                raise ValueError("Could not rehydrate the target proposal for revision")
            session.commit()
            try:
                version_id = revise_rejected(local, local_proposal_id, reason, SarvamClient(settings.sarvam_model))
                local_version = local.db.execute(
                    "SELECT * FROM proposal_versions WHERE id=?", (version_id,)
                ).fetchone()
                assessment = None
                for row in local.audit(local_case_id):
                    if row["kind"] == "proposal_revision_assessment":
                        payload = json.loads(row["payload_json"])
                        if payload.get("proposal_id") == local_proposal_id and payload.get("version_id") == version_id:
                            assessment = payload
                    elif row["kind"] == "sarvam_call":
                        metadata = json.loads(row["payload_json"])
                        session.add(SarvamCall(case_id=case.id, operation="revision", metadata_json=metadata))
                latest = session.scalar(
                    select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id)
                    .order_by(ProposalVersion.version.desc()).limit(1)
                )
                new_version = ProposalVersion(
                    proposal_id=proposal.id,
                    version=(latest.version + 1) if latest else 1,
                    author="sarvam",
                    proposed_text=local_version["proposed_text"],
                    reason=local_version["reason"],
                    code_evidence=json.loads(local_version["code_evidence_json"]),
                    evidence_completeness=(assessment or {}).get("evidence_completeness"),
                    missing_information=(assessment or {}).get("missing_information", []),
                    safe_claims=(assessment or {}).get("safe_claims", []),
                    unsupported_claims=(assessment or {}).get("unsupported_claims", []),
                )
                session.add(new_version)
                proposal.status = "PENDING"
                proposal.accepted_version_id = None
                session.flush()
                case.status = "READY_FOR_REVIEW"
                audit(
                    session, "proposal_revision_completed",
                    {"proposal_id": proposal.id, "version": new_version.version, "version_id": new_version.id}, case.id,
                )
                if assessment:
                    audit(session, "proposal_revision_assessment", {**assessment, "proposal_id": proposal.id, "version_id": new_version.id}, case.id)
                for row in local.audit(local_case_id):
                    if row["kind"] == "sarvam_call":
                        audit(session, "sarvam_call", json.loads(row["payload_json"]), case.id)
                session.commit()
            except Exception:
                for row in local.audit(local_case_id):
                    if row["kind"] == "sarvam_call":
                        metadata = json.loads(row["payload_json"])
                        session.add(SarvamCall(case_id=case.id, operation="revision", metadata_json=metadata))
                        audit(session, "sarvam_call", metadata, case.id)
                session.commit()
                raise
            finally:
                if local.db:
                    local.db.close()


def _git_file(git, commit: str, path: str) -> str:
    return git("show", f"{commit}:{path}")


def _process_publish(engine, settings: Settings, job: Job) -> None:
    from docsync.online.publish import publish
    publish(engine, settings, job.payload["case_id"])


def _activate_release(engine, settings: Settings, job: Job) -> None:
    factory = session_factory(engine)
    with factory() as session:
        repo = session.get(Repository, job.repo_id)
        release = session.scalar(
            select(DocumentationRelease).where(
                DocumentationRelease.repo_id == repo.id,
                DocumentationRelease.pr_number == int(job.payload["pr_number"]),
            )
        )
        if release is None:
            return
        if release.status == "INDEXED":
            return
        case = session.get(ChangeCase, release.case_id)
        sections = session.scalars(select(ReleaseSection).where(ReleaseSection.release_id == release.id)).all()
        merge_sha = job.payload.get("merge_sha")
        if not merge_sha:
            release.status = "INDEX_ERROR"
            audit(session, "index_refresh_error", {"error": "GitHub did not include the merged commit SHA"}, case.id)
            session.commit()
            return
        repo_name = repo.full_name
        installation_id = repo.installation_id
        active = session.get(KnowledgeVersion, repo.active_index_version_id) if repo.active_index_version_id else None
        active_commit = active.source_commit if active else None
    github = GitHubClient(settings)
    try:
        token = _token(github, repo)
        if active_commit and active_commit != merge_sha:
            comparison = github.request('GET', f'/repos/{repo_name}/compare/{active_commit}...{merge_sha}', token).json()
            if comparison.get('status') != 'ahead':
                raise ConflictError('Merged release is not newer than the active approved snapshot')
        pr = github.request("GET", f"/repos/{repo_name}/pulls/{release.pr_number}", token).json()
        if (not pr.get("merged") or pr.get("merge_commit_sha") != merge_sha
            or pr.get("head", {}).get("sha") != release.commit_sha
            or pr.get("base", {}).get("ref") != repo.monitored_branch
            or pr.get("head", {}).get("repo", {}).get("full_name") != repo_name):
            raise ConflictError("Merged PR does not match the durable approved release")
        with factory() as session:
            stored = session.get(DocumentationRelease, release.id)
            stored.merged_sha = merge_sha
            stored.merged_at = stored.merged_at or utcnow()
            stored.status_checked_at = utcnow()
            stored.status = 'VERIFYING'
            audit(session, 'documentation_merge_verified', {'pr_number': stored.pr_number, 'merged_sha': merge_sha}, stored.case_id)
            session.commit()
        file_contents = {path: github.file_at(repo_name, path, merge_sha, token) for path in sorted({s.path for s in sections})}
        for path, text in file_contents.items():
            if text != github.file_at(repo_name, path, release.commit_sha, token):
                raise ConflictError("Merged documentation file differs from the approved commit")
        approved: list[IndexInput] = []
        mismatches: list[str] = []
        for expected in sections:
            parsed = parse_sections(expected.path, file_contents[expected.path])
            current = next((item for item in parsed if item.section_id == expected.section_id), None)
            if current is None or section_sha256(current.text) != expected.sha256:
                mismatches.append(expected.section_id)
                continue
            approved.append(IndexInput(current.section_id, current.path, current.heading, current.text, merge_sha))
        if mismatches:
            with factory() as session:
                release = session.get(DocumentationRelease, release.id)
                release.status = "INDEX_CONFLICT"
                case = session.get(ChangeCase, release.case_id)
                case.status = "INDEX_CONFLICT"
                audit(session, "index_refresh_conflict", {"sections": mismatches, "merged_sha": merge_sha}, case.id)
                session.commit()
            return
        embedder = SentenceEmbedder(settings.embedding_model, settings.embedding_cache)
        with factory() as session:
            stored = session.get(DocumentationRelease, release.id)
            stored.status = 'INDEXING'
            stored.index_started_at = utcnow()
            audit(session, 'knowledge_refresh_started', {'release_id': stored.id, 'merged_sha': merge_sha}, stored.case_id)
            session.commit()
        embedder = prepared_embeddings(approved, embedder)
        with factory() as session:
            repo = session.get(Repository, repo.id)
            release = session.get(DocumentationRelease, release.id)
            case = session.get(ChangeCase, release.case_id)
            version = replace_approved_sections(
                session, repo, merge_sha, approved, embedder, case=case, release=release
            )
            audit(session, "knowledge_index_activated", {"version_id": version.id, "merged_sha": merge_sha, "section_count": len(approved)}, case.id)
            session.commit()
    finally:
        github.close()


def _baseline_index(engine, settings: Settings, job: Job) -> None:
    factory = session_factory(engine)
    with factory() as session:
        repo = session.get(Repository, job.repo_id)
        if repo.active_index_version_id:
            return
        branch = repo.monitored_branch
        repository_name = repo.full_name
    github = GitHubClient(settings)
    try:
        token = _token(github, repo)
        baseline_sha = job.payload.get("baseline_sha")
        if not baseline_sha:
            raise ValueError("An explicit approved baseline SHA is required")
        with cloned_repository(repository_name, token, baseline_sha, baseline_sha) as (root, git, _env):
            git("checkout", "--detach", baseline_sha)
            docs = root / "docs"
            if not docs.is_dir():
                raise ValueError("The configured repository does not contain a docs/ directory")
            sections: list[IndexInput] = []
            for path in sorted(docs.rglob("*.md")):
                relative = path.relative_to(root).as_posix()
                for section in parse_sections(relative, path.read_text(encoding="utf-8")):
                    sections.append(IndexInput(section.section_id, section.path, section.heading, section.text, baseline_sha))
            if not sections:
                raise ValueError("The configured repository has no Markdown sections under docs/")
            embedder = SentenceEmbedder(settings.embedding_model, settings.embedding_cache)
            embedder = prepared_embeddings(sections, embedder)
            with factory() as session:
                repo = session.get(Repository, repo.id)
                if repo.active_index_version_id:
                    return
                version = replace_approved_sections(session, repo, baseline_sha, sections, embedder)
                audit(session, "approved_baseline_indexed", {"source_commit": baseline_sha, "section_count": len(sections), "version_id": version.id})
                session.commit()
    finally:
        github.close()


def _process_job(engine, settings: Settings, job: Job) -> None:
    if job.kind == "analyze_push":
        _process_analysis(engine, settings, job)
    elif job.kind == "revise_proposal":
        _process_revision(engine, settings, job)
    elif job.kind == "publish_docs":
        _process_publish(engine, settings, job)
    elif job.kind == "activate_release":
        _activate_release(engine, settings, job)
    elif job.kind == "index_baseline":
        _baseline_index(engine, settings, job)
    else:
        raise ValueError(f"Unknown background job kind: {job.kind}")


def run_once(engine, settings: Settings) -> bool:
    factory = session_factory(engine)
    with factory() as session:
        statement = select(Job).where(Job.status == "PENDING").order_by(Job.created_at).limit(1)
        if engine.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        job = session.scalar(statement)
        if job is None:
            return False
        job.status = "PROCESSING"
        job.attempts += 1
        job_id = job.id
        session.commit()
    with factory() as session:
        job = session.get(Job, job_id)
        detached = Job(
            id=job.id, delivery_id=job.delivery_id, repo_id=job.repo_id,
            kind=job.kind, payload=dict(job.payload), status=job.status, attempts=job.attempts,
        )
    try:
        _process_job(engine, settings, detached)
        with factory() as session:
            completed = session.get(Job, job_id)
            completed.status = "COMPLETED"
            if completed.delivery_id:
                delivery = session.get(GitHubDelivery, completed.delivery_id)
                if delivery is not None:
                    delivery.status = "PROCESSED"
            session.commit()
    except Exception as exc:
        with factory() as session:
            stored_job = session.get(Job, job_id)
            stored_job.status = "ERROR"
            if stored_job.delivery_id:
                delivery = session.get(GitHubDelivery, stored_job.delivery_id)
                if delivery and delivery.status == "QUEUED":
                    delivery.status = "ERROR"
            if stored_job.kind == "publish_docs":
                case = session.get(ChangeCase, stored_job.payload.get("case_id"))
                if case and case.status == "PUBLISHING":
                    case.status = "PUBLISH_ERROR"
                    audit(session, "documentation_publish_error", {"error_type": type(exc).__name__, "message": str(exc)[:500]}, case.id)
            elif stored_job.kind == "revise_proposal":
                proposal = session.get(Proposal, stored_job.payload.get("proposal_id"))
                if proposal and proposal.status == "REVISING":
                    proposal.status = "REVISION_ERROR"
                    case = session.get(ChangeCase, proposal.case_id)
                    case.status = "READY_FOR_REVIEW"
                    audit(session, "proposal_revision_error", {"error_type": type(exc).__name__, "message": str(exc)[:500]}, case.id)
            session.commit()
        print(f"DocSync job {job_id} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return True


def main() -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    initialize_database(engine)
    print("DocSync worker started", flush=True)
    while True:
        if not run_once(engine, settings):
            time.sleep(2)


if __name__ == "__main__":
    main()
