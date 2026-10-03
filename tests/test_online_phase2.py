from __future__ import annotations

import hashlib
import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from docsync.errors import ConflictError
from docsync.repository.markdown_sections import parse_sections, section_sha256, to_doc_section
from docsync.sarvam import ModelClient
from docsync.store import Store
from docsync.web.app import create_app
from docsync.web.config import Settings
from docsync.web.database import initialize_database, make_engine, session_factory
from docsync.web.indexing import IndexInput
from docsync.web.models import (
    AuditEvent,
    ChangeCase,
    DocumentationRelease,
    GitHubDelivery,
    IndexedSection,
    Job,
    KnowledgeVersion,
    Proposal,
    ProposalVersion,
    ReleaseSection,
    Repository,
    ReviewAction,
    SectionAssessment,
    uid,
)
from docsync.web.repository import ensure_repository
from docsync.web.workflow import (
    accept_proposal,
    approved_mappings,
    local_store_from_online,
    modify_proposal,
    persist_analysis,
    reject_proposal,
    start_case,
)


def settings_for(tmp_path: Path, **overrides) -> Settings:
    values = {
        "database_url": f"sqlite:///{tmp_path / 'online.sqlite3'}",
        "sarvam_api_key": "test-sarvam-key-never-persist",
        "sarvam_model": "sarvam-105b",
        "github_app_id": "1234",
        "github_private_key": "",
        "github_webhook_secret": "test-webhook-secret",
        "github_installation_id": 77,
        "repository": "demo-owner/httpx",
        "monitored_branch": "master",
        "review_username": "reviewer",
        "review_password": "a-long-test-password",
        "base_url": "https://docsync.example.test",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_cache": str(tmp_path / "models"),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def system(tmp_path):
    settings = settings_for(tmp_path)
    engine = make_engine(settings.database_url)
    initialize_database(engine)
    factory = session_factory(engine)
    with factory() as session:
        repo = ensure_repository(session, settings, settings.github_installation_id)
        session.commit()
        repo_id = repo.id
    yield settings, engine, factory, repo_id
    engine.dispose()


def make_case(session, repo_id: str, *, decision="UPDATE", with_proposal=True, accepted=False):
    path = "docs/advanced/timeouts.md"
    original = "## Default timeout\nThe default timeout is five seconds.\n"
    parsed = parse_sections(path, original)[0]
    section = {
        **to_doc_section(parsed).model_dump(),
        "start_line": parsed.start_line,
        "end_line": parsed.end_line,
    }
    case_data = {
        "repo_root": "",
        "old_sha": "a" * 40,
        "new_sha": "b" * 40,
        "changes": [{
            "code_id": "httpx/_config.py::DEFAULT_TIMEOUT_CONFIG",
            "path": "httpx/_config.py",
            "name": "DEFAULT_TIMEOUT_CONFIG",
            "kind": "assignment",
            "old_code": "DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)",
            "new_code": "DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=8.0)",
            "diff": "-DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)\n+DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=8.0)",
            "change_kind": "modified",
        }],
        "mappings": [{
            "code_id": "httpx/_config.py::DEFAULT_TIMEOUT_CONFIG",
            "section_id": section["section_id"],
            "reason": "approved mapping",
        }],
        "sections": [section],
    }
    case = ChangeCase(
        repo_id=repo_id,
        before_sha="a" * 40,
        after_sha="b" * 40,
        status="READY_FOR_REVIEW",
        decision=decision,
        summary="The default timeout changed.",
        case_data=case_data,
    )
    session.add(case)
    session.flush()
    assessment = SectionAssessment(
        case_id=case.id,
        section_id=section["section_id"],
        path=path,
        heading=section["heading"],
        current_text=section["text"],
        base_sha256=section["sha256"],
        start_line=section["start_line"],
        end_line=section["end_line"],
        decision=decision,
        rationale="The supplied assignment sets the new numeric default.",
        evidence_completeness="COMPLETE",
        code_evidence=["DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=8.0)"],
        missing_information=[],
        safe_claims=["The default timeout is configured as eight seconds."],
        unsupported_claims=["The timeout applies to every possible runtime path."],
        proposed_text="## Default timeout\nThe default timeout is eight seconds.\n" if decision == "UPDATE" else None,
    )
    session.add(assessment)
    proposal = None
    version = None
    if with_proposal:
        proposal = Proposal(case_id=case.id, section_id=section["section_id"], status="PENDING")
        session.add(proposal)
        session.flush()
        version = ProposalVersion(
            proposal_id=proposal.id,
            version=1,
            author="sarvam",
            proposed_text="## Default timeout\nThe default timeout is eight seconds.\n",
            reason="The code sets the new value.",
            code_evidence=["DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=8.0)"],
            evidence_completeness="COMPLETE",
            missing_information=[],
            safe_claims=["The default timeout is configured as eight seconds."],
            unsupported_claims=["The timeout applies to every possible runtime path."],
        )
        session.add(version)
        session.flush()
        if accepted:
            proposal.status = "ACCEPTED"
            proposal.accepted_version_id = version.id
    session.flush()
    return case, assessment, proposal, version


def sign(secret: str, body: bytes) -> str:
    import hmac

    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def push_payload():
    return {
        "repository": {"full_name": "demo-owner/httpx"},
        "installation": {"id": 77},
        "ref": "refs/heads/master",
        "before": "a" * 40,
        "after": "b" * 40,
        "commits": [{"added": [], "modified": ["httpx/_config.py"], "removed": [], "message": "Change timeout"}],
    }


def test_invalid_signature_and_duplicate_webhook_are_rejected_or_idempotent(tmp_path):
    settings = settings_for(tmp_path)
    engine = make_engine(settings.database_url)
    app = create_app(settings, engine)
    payload = json.dumps(push_payload()).encode()
    with TestClient(app) as client:
        bad = client.post("/webhooks/github", content=payload, headers={
            "X-GitHub-Event": "push", "X-GitHub-Delivery": "delivery-1", "X-Hub-Signature-256": "sha256=bad",
        })
        assert bad.status_code == 401
        headers = {
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": "delivery-1",
            "X-Hub-Signature-256": sign(settings.github_webhook_secret, payload),
            "Content-Type": "application/json",
        }
        first = client.post("/webhooks/github", content=payload, headers=headers)
        duplicate = client.post("/webhooks/github", content=payload, headers=headers)
        assert first.status_code == 202 and first.json()["duplicate"] is False
        assert duplicate.status_code == 200 and duplicate.json()["duplicate"] is True
        second_delivery = {**headers, "X-GitHub-Delivery": "delivery-2"}
        same_commit = client.post("/webhooks/github", content=payload, headers=second_delivery)
        assert same_commit.status_code == 202 and same_commit.json()["status"] == "DUPLICATE_CHANGE"
    factory = session_factory(engine)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(GitHubDelivery)) == 2
        assert session.scalar(select(func.count()).select_from(Job)) == 1
    engine.dispose()


def test_outside_repository_webhook_is_not_accepted(tmp_path):
    settings = settings_for(tmp_path)
    engine = make_engine(settings.database_url)
    app = create_app(settings, engine)
    payload_dict = push_payload()
    payload_dict["repository"]["full_name"] = "attacker/httpx"
    body = json.dumps(payload_dict).encode()
    with TestClient(app) as client:
        response = client.post("/webhooks/github", content=body, headers={
            "X-GitHub-Event": "push", "X-GitHub-Delivery": "outside", "X-Hub-Signature-256": sign(settings.github_webhook_secret, body),
        })
        assert response.status_code == 404
    with session_factory(engine)() as session:
        assert session.scalar(select(func.count()).select_from(GitHubDelivery)) == 0
    engine.dispose()


def test_case_creation_and_approved_timeout_mapping_retrieval(system):
    _settings, engine, factory, repo_id = system
    with factory() as session:
        mappings = approved_mappings(session, repo_id)
        timeout_sections = {item["section_id"] for item in mappings if item["code_id"].endswith("DEFAULT_TIMEOUT_CONFIG")}
        assert "docs/advanced/timeouts.md::__intro__" in timeout_sections
        assert "docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client" in timeout_sections
        assert "docs/quickstart.md::timeouts" in timeout_sections
        repo = session.get(Repository, repo_id)
        delivery = GitHubDelivery(delivery_id="case-delivery", repo_id=repo.id, event_name="push", status="QUEUED")
        session.add(delivery)
        session.commit()
        case = start_case(session, repo, delivery.delivery_id, "a" * 40, "b" * 40)
        same = start_case(session, repo, delivery.delivery_id, "a" * 40, "b" * 40)
        assert case.id == same.id
        assert case.before_sha == "a" * 40 and case.after_sha == "b" * 40


def test_authenticated_review_surface_shows_evidence_and_escapes_repository_text(system):
    settings, engine, factory, repo_id = system
    with factory() as session:
        case, assessment, _proposal, _version = make_case(session, repo_id)
        assessment.unsupported_claims = ["<script>alert('repo text')</script>"]
        session.commit()
        case_id = case.id
    app = create_app(settings, engine)
    with TestClient(app) as client:
        denied = client.get(f"/cases/{case_id}")
        assert denied.status_code == 401
        page = client.get(f"/cases/{case_id}", auth=(settings.review_username, settings.review_password))
        assert page.status_code == 200
        assert "Code evidence" in page.text and "Evidence assessment" in page.text
        assert "&lt;script&gt;" in page.text
        assert "<script>alert('repo text')</script>" not in page.text
        csrf = client.cookies.get("docsync_csrf")
        missing_csrf = client.post(f"/proposals/{session_scalar_proposal(factory, case_id)}/reject", data={"reason": "No token"}, auth=(settings.review_username, settings.review_password))
        assert missing_csrf.status_code == 422
        rejected = client.post(
            f"/proposals/{session_scalar_proposal(factory, case_id)}/reject",
            data={"reason": "Tighten the evidence wording.", "csrf_token": csrf},
            auth=(settings.review_username, settings.review_password),
            follow_redirects=False,
        )
        assert rejected.status_code == 303


def session_scalar_proposal(factory, case_id: str) -> str:
    with factory() as session:
        return session.scalar(select(Proposal).where(Proposal.case_id == case_id)).id


def test_phase1_analysis_persists_section_evidence_and_proposal_versions(system, tmp_path):
    _settings, engine, factory, repo_id = system
    with factory() as session:
        repo = session.get(Repository, repo_id)
        delivery = GitHubDelivery(delivery_id="analysis-delivery", repo_id=repo.id, event_name="push", status="QUEUED")
        session.add(delivery)
        online = start_case(session, repo, delivery.delivery_id, "a" * 40, "b" * 40)
        online_id = online.id

    markdown = "## Default timeout\nThe default timeout is five seconds.\n"
    section_obj = parse_sections("docs/advanced/timeouts.md", markdown)[0]
    section = {
        **to_doc_section(section_obj).model_dump(),
        "start_line": section_obj.start_line,
        "end_line": section_obj.end_line,
    }
    local = Store(tmp_path / "phase1.sqlite3")
    local.add_confirmed_mapping("httpx/_config.py::DEFAULT_TIMEOUT_CONFIG", section["section_id"], "confirmed")
    local_case_id = local.create_case({
        "repo_root": str(tmp_path), "old_sha": "a" * 40, "new_sha": "b" * 40,
        "changes": [{"code_id": "httpx/_config.py::DEFAULT_TIMEOUT_CONFIG", "path": "httpx/_config.py", "name": "DEFAULT_TIMEOUT_CONFIG", "kind": "assignment", "old_code": "5", "new_code": "8", "diff": "-5\n+8", "change_kind": "modified"}],
        "mappings": [{"code_id": "httpx/_config.py::DEFAULT_TIMEOUT_CONFIG", "section_id": section["section_id"], "reason": "confirmed"}],
        "sections": [section],
    })
    local.set_case_result(local_case_id, "UPDATE", "Default changed", "READY")
    local.add_proposal(local_case_id, section["section_id"], "## Default timeout\nThe default timeout is eight seconds.\n", "The code sets eight seconds.", ["DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=8.0)"])
    local.event("section_decision", {
        "section_id": section["section_id"], "decision": "UPDATE", "proposed_text": "## Default timeout\nThe default timeout is eight seconds.\n",
        "reason": "Direct assignment evidence.", "code_evidence": ["DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=8.0)"],
        "evidence_completeness": "COMPLETE", "missing_information": [], "safe_claims": ["Default configured to eight seconds."],
        "unsupported_claims": ["Applies to all runtime modes."],
    }, local_case_id)
    with factory() as session:
        persist_analysis(session, online_id, "analysis-delivery", local, local_case_id)
        assessment = session.scalar(select(SectionAssessment).where(SectionAssessment.case_id == online_id))
        proposal = session.scalar(select(Proposal).where(Proposal.case_id == online_id))
        version = session.scalar(select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id))
        assert assessment.decision == "UPDATE"
        assert assessment.unsupported_claims == ["Applies to all runtime modes."]
        assert version.version == 1 and version.author == "sarvam"
        assert version.proposed_text.endswith("eight seconds.\n")
    local.db.close()


def test_rejection_queues_targeted_revision_and_preserves_versions(system, monkeypatch, tmp_path):
    _settings, engine, factory, repo_id = system
    with factory() as session:
        case, _assessment, proposal, first = make_case(session, repo_id)
        session.commit()
        proposal_id, case_id = proposal.id, case.id
        reject_proposal(session, proposal.id, "Keep the inactivity wording precise.")
        assert session.get(Proposal, proposal_id).status == "REVISING"
        assert session.scalar(select(ReviewAction).where(ReviewAction.proposal_id == proposal_id)).reason == "Keep the inactivity wording precise."
        job = session.scalar(select(Job).where(Job.kind == "revise_proposal"))
        assert job.payload["proposal_id"] == proposal_id

    def fake_revision(local_store, local_proposal_id, reason, _client):
        assert reason == "Keep the inactivity wording precise."
        return local_store.add_version(local_proposal_id, "## Default timeout\nThe default timeout is eight seconds of inactivity.\n", "Preserves inactivity wording.", ["DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=8.0)"], "sarvam")

    monkeypatch.setattr("docsync.web.worker.revise_rejected", fake_revision)
    from docsync.web.worker import _process_revision

    with factory() as session:
        job = session.scalar(select(Job).where(Job.kind == "revise_proposal"))
        detached = Job(id=job.id, repo_id=job.repo_id, kind=job.kind, payload=job.payload, status=job.status)
    _process_revision(engine, _settings, detached)
    with factory() as session:
        versions = session.scalars(select(ProposalVersion).where(ProposalVersion.proposal_id == proposal_id).order_by(ProposalVersion.version)).all()
        assert [item.version for item in versions] == [1, 2]
        assert versions[0].id != versions[1].id
        assert "inactivity" in versions[1].proposed_text
        assert session.get(Proposal, proposal_id).status == "PENDING"
        assert session.get(ChangeCase, case_id).status == "READY_FOR_REVIEW"


def test_human_modification_is_an_append_only_authoritative_version(system):
    _settings, _engine, factory, repo_id = system
    human_text = "## Default timeout\nHuman-approved exact wording.\n"
    with factory() as session:
        _case, _assessment, proposal, first = make_case(session, repo_id)
        session.commit()
        changed = modify_proposal(session, proposal.id, human_text)
        assert changed.author == "human" and changed.proposed_text == human_text
        assert changed.version == 2
        assert session.get(Proposal, proposal.id).status == "PENDING"
        assert session.scalar(select(func.count()).select_from(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id)) == 2
        assert session.scalar(select(ReviewAction).where(ReviewAction.proposal_id == proposal.id)).action == "MODIFY"


def test_stale_base_hash_blocks_phase1_patch_application(system, tmp_path):
    _settings, _engine, factory, repo_id = system
    root = tmp_path / "worktree"
    root.mkdir()
    current = "## Default timeout\nThe default timeout is five seconds.\n"
    target = root / "docs" / "advanced" / "timeouts.md"
    target.parent.mkdir(parents=True)
    target.write_text(current, encoding="utf-8")
    with factory() as session:
        case, assessment, proposal, version = make_case(session, repo_id, accepted=True)
        case.case_data["repo_root"] = str(root)
        session.commit()
        local, local_case_id, ids = local_store_from_online(session, case, root)
        local_id = ids[proposal.id]
        local_version = local.latest_version(local_id)
        local.set_proposal_status(local_id, "ACCEPTED", accepted_version_id=local_version["id"])
    target.write_text(current.replace("five", "six"), encoding="utf-8")
    with pytest.raises(ConflictError, match="changed since analysis"):
        from docsync.apply import apply_case

        apply_case(local, local_case_id)
    assert "six seconds" in target.read_text(encoding="utf-8")
    local.db.close()


def _git(*args, cwd: Path):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def test_accepted_patch_creates_docs_only_branch_commit_and_pr(system, tmp_path, monkeypatch):
    _settings, engine, factory, repo_id = system
    bare = tmp_path / "httpx.git"
    bare.mkdir()
    _git("init", "--bare", str(bare), cwd=tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    _git("init", "--initial-branch=master", cwd=source)
    _git("config", "user.name", "Test", cwd=source)
    _git("config", "user.email", "test@example.invalid", cwd=source)
    path = source / "docs" / "advanced" / "timeouts.md"
    path.parent.mkdir(parents=True)
    path.write_text("## Default timeout\nThe default timeout is five seconds.\n", encoding="utf-8")
    _git("add", "docs/advanced/timeouts.md", cwd=source)
    _git("commit", "-m", "baseline", cwd=source)
    base_sha = _git("rev-parse", "HEAD", cwd=source)
    _git("remote", "add", "origin", str(bare), cwd=source)
    _git("push", "origin", "master", cwd=source)
    with factory() as session:
        repo = session.get(Repository, repo_id)
        repo.installation_id = 77
        case, assessment, proposal, version = make_case(session, repo_id, accepted=True)
        case.after_sha = base_sha
        case.before_sha = base_sha
        case.case_data["new_sha"] = base_sha
        case.case_data["old_sha"] = base_sha
        case.case_data["sections"][0]["sha256"] = section_sha256("## Default timeout\nThe default timeout is five seconds.\n")
        case.case_data["sections"][0]["text"] = "## Default timeout\nThe default timeout is five seconds.\n"
        assessment.base_sha256 = section_sha256("## Default timeout\nThe default timeout is five seconds.\n")
        assessment.current_text = "## Default timeout\nThe default timeout is five seconds.\n"
        job = Job(id=uid(), repo_id=repo_id, kind="publish_docs", payload={"case_id": case.id})
        session.add(job)
        session.commit()
        case_id = case.id

    class FakeGitHub:
        def __init__(self, _settings):
            pass
        def installation_token(self, _installation_id):
            return "not-a-real-token"
        def branch_sha(self, _repository, _branch, _token):
            return base_sha
        def create_pull_request(self, _repository, branch, _base, _case, _token):
            return 42, f"https://github.com/demo-owner/httpx/pull/42"
        def close(self):
            pass

    @contextmanager
    def local_clone(_repository, _token, _before, _after):
        clone = tmp_path / "worker-clone"
        _git("clone", str(bare), str(clone), cwd=tmp_path)
        env = os.environ.copy()
        def git(*args):
            result = subprocess.run(["git", *args], cwd=clone, env=env, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr)
            return result.stdout.strip()
        yield clone, git, env

    monkeypatch.setattr("docsync.web.worker.GitHubClient", FakeGitHub)
    monkeypatch.setattr("docsync.web.worker.cloned_repository", local_clone)
    from docsync.web.worker import _process_publish

    with factory() as session:
        job_row = session.scalar(select(Job).where(Job.kind == "publish_docs"))
        detached = Job(id=job_row.id, repo_id=job_row.repo_id, kind=job_row.kind, payload=job_row.payload)
    _process_publish(engine, _settings, detached)

    with factory() as session:
        case = session.get(ChangeCase, case_id)
        release = session.scalar(select(DocumentationRelease).where(DocumentationRelease.case_id == case_id))
        assert case.status == "WAITING_MERGE"
        assert case.documentation_pr_number == 42
        assert release.commit_sha != base_sha
        assert release.status == "PENDING_MERGE"
    remote_sha = _git("rev-parse", "refs/heads/docsync/case-" + case_id[:8], cwd=bare)
    assert remote_sha == release.commit_sha
    merged_docs = subprocess.run(["git", "show", f"{remote_sha}:docs/advanced/timeouts.md"], cwd=bare, check=True, capture_output=True, text=True).stdout
    assert "eight seconds" in merged_docs


def test_pending_and_rejected_proposals_have_no_index_release(system, monkeypatch):
    settings, engine, factory, repo_id = system
    with factory() as session:
        case, _assessment, proposal, _version = make_case(session, repo_id)
        proposal.status = "REJECTED"
        job = Job(id=uid(), repo_id=repo_id, kind="activate_release", payload={"pr_number": 33, "merge_sha": "c" * 40})
        session.add(job)
        session.commit()
        case_id = case.id
    from docsync.web.worker import _activate_release
    with factory() as session:
        job_row = session.scalar(select(Job).where(Job.kind == "activate_release"))
        detached = Job(id=job_row.id, repo_id=job_row.repo_id, kind=job_row.kind, payload=job_row.payload)
    _activate_release(engine, settings, detached)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeVersion)) == 0
        assert session.get(ChangeCase, case_id).decision == "UPDATE"


def test_merged_approved_section_enters_index_and_chat_cites_merged_version(system, monkeypatch):
    settings, engine, factory, repo_id = system
    merged_sha = "c" * 40
    updated_doc = "## Default timeout\nThe default timeout is eight seconds.\n"
    section = parse_sections("docs/advanced/timeouts.md", updated_doc)[0]
    with factory() as session:
        repo = session.get(Repository, repo_id)
        repo.installation_id = 77
        case, _assessment, proposal, version = make_case(session, repo_id, accepted=True)
        release = DocumentationRelease(
            case_id=case.id, repo_id=repo_id, branch="docsync/case-demo", commit_sha="d" * 40,
            pr_number=51, pr_url="https://github.com/demo-owner/httpx/pull/51", status="PENDING_MERGE",
        )
        session.add(release)
        session.flush()
        session.add(ReleaseSection(
            release_id=release.id, section_id=section.section_id, path=section.path,
            text=section.text, sha256=section_sha256(section.text),
        ))
        job = Job(id=uid(), repo_id=repo_id, kind="activate_release", payload={"pr_number": 51, "merge_sha": merged_sha})
        session.add(job)
        session.commit()
        release_id, case_id = release.id, case.id

    class FakeGitHub:
        def __init__(self, _settings):
            pass
        def installation_token(self, _installation_id):
            return "token"
        def file_at(self, _repository, _path, _ref, _token):
            assert _ref == merged_sha
            return updated_doc
        def close(self):
            pass

    class FakeEmbedder:
        def __init__(self, *_args):
            pass
        def embed(self, _text):
            return [1.0] + [0.0] * 383

    monkeypatch.setattr("docsync.web.worker.GitHubClient", FakeGitHub)
    monkeypatch.setattr("docsync.web.worker.SentenceEmbedder", FakeEmbedder)
    from docsync.web.worker import _activate_release
    with factory() as session:
        row = session.scalar(select(Job).where(Job.kind == "activate_release"))
        detached = Job(id=row.id, repo_id=row.repo_id, kind=row.kind, payload=row.payload)
    _activate_release(engine, settings, detached)

    with factory() as session:
        repo = session.get(Repository, repo_id)
        version = session.get(KnowledgeVersion, repo.active_index_version_id)
        rows = session.scalars(select(IndexedSection).where(IndexedSection.version_id == version.id)).all()
        assert version.source_commit == merged_sha and version.active is True
        assert len(rows) == 1 and rows[0].section_id == section.section_id
        assert session.get(DocumentationRelease, release_id).status == "INDEXED"
        assert session.get(ChangeCase, case_id).status == "INDEXED"

        class FakeChat(ModelClient):
            def complete(self, system, user, schema_name, schema_json):
                prompt = json.loads(user)
                sid = prompt["approved_documentation_passages"][0]["source"]["section_id"]
                return json.dumps({"answer": "The default timeout is eight seconds.", "used_section_ids": [sid]})

        class QueryEmbedder:
            def embed(self, _question):
                return [1.0] + [0.0] * 383

        from docsync.web.chat import answer_question
        turn = answer_question(session, settings, repo, "What is the default timeout?", QueryEmbedder(), FakeChat())
        assert turn.citations == [{
            "section_id": section.section_id,
            "file": "docs/advanced/timeouts.md",
            "heading": "Default timeout",
            "approved_commit": merged_sha,
            "knowledge_version": version.id,
        }]
        assert turn.knowledge_version_id == version.id
