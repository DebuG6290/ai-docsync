from datetime import timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import select, func

from test_online_phase2 import system, make_case
from docsync.ui.state import release_status, case_status, load
from docsync.ui.components import Context
from docsync.web.models import DocumentationRelease, Proposal, ProposalVersion, SectionAssessment, ReviewAction, Job, AuditEvent, Repository, utcnow
from docsync.web.workflow import override_no_change, accept_proposal, triage_section
from docsync.online.status import reconcile_release


def test_no_change_override_preserves_assessment_and_requires_approval(system):
    settings, engine, factory, repo_id = system
    with factory() as session:
        case, section, _, _ = make_case(session, repo_id, decision='NO_CHANGE', with_proposal=False)
        session.commit()
        original = (section.rationale, section.current_text, section.decision)
        human = override_no_change(session, section.id, 'The example comment is stale.', '## Default timeout\nExact human text.\n')
        proposal = session.get(Proposal, human.proposal_id)
        assert human.author == 'human' and human.human_modified
        assert proposal.status == 'PENDING' and not proposal.accepted_version_id
        assert (section.rationale, section.current_text, section.decision) == original
        assert session.get(ReviewAction, session.scalar(select(ReviewAction.id))).reason == 'The example comment is stale.'
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.kind == 'no_change_overridden')) == 1
        accept_proposal(session, proposal.id, human.id)
        assert proposal.accepted_version_id == human.id
        assert case.status == 'PUBLISH_QUEUED'


@pytest.mark.parametrize('reason,text', [('', 'text'), ('reason', ''), (' ', 'text')])
def test_override_requires_reason_and_content(system, reason, text):
    _, _, factory, repo_id = system
    with factory() as session:
        case, section, _, _ = make_case(session, repo_id, decision='NO_CHANGE', with_proposal=False)
        session.commit()
        with pytest.raises(ValueError, match='required'):
            override_no_change(session, section.id, reason, text)
        session.rollback()
        assert session.scalar(select(func.count()).select_from(Proposal)) == 0


def test_override_is_blocked_after_publication_snapshot(system):
    _, _, factory, repo_id = system
    with factory() as session:
        case, section, _, _ = make_case(session, repo_id, decision='NO_CHANGE', with_proposal=False)
        session.add(DocumentationRelease(case_id=case.id, repo_id=repo_id, branch='codex/sample', commit_sha='c'*40, pr_number=0, pr_url='', status='PREPARED'))
        session.commit()
        with pytest.raises(ValueError, match='Publication has started'):
            override_no_change(session, section.id, 'reason', 'text')


def test_override_cancels_unpublished_queued_operation(system):
    _, _, factory, repo_id = system
    with factory() as session:
        case, section, _, _ = make_case(session, repo_id, decision='NO_CHANGE', with_proposal=False)
        job = Job(repo_id=repo_id, kind='publish_docs', payload={'case_id': case.id})
        session.add(job); session.commit()
        override_no_change(session, section.id, 'reason', 'text')
        assert job.status == 'CANCELLED'
        with pytest.raises(ValueError, match='existing version'):
            override_no_change(session, section.id, 'reason', 'different text')


@pytest.mark.parametrize('status,merged,expected', [
    ('PENDING_MERGE', None, 'Waiting for merge'), ('MERGED', 'c'*40, 'Documentation merged'),
    ('VERIFYING', 'c'*40, 'Verifying merged documentation'), ('INDEXING', 'c'*40, 'Updating knowledge'),
    ('INDEXED', 'c'*40, 'Knowledge updated'), ('INDEX_ERROR', 'c'*40, 'Refresh needs attention'),
    ('INDEX_CONFLICT', 'c'*40, 'Refresh needs attention'), ('CLOSED', None, 'PR closed without merging')])
def test_release_status_is_explicit(status, merged, expected):
    release = SimpleNamespace(status=status, merged_sha=merged, pr_number=5)
    state = release_status(release)
    assert state.label == expected
    if status in {'INDEXING', 'MERGED', 'INDEX_ERROR'}:
        assert 'previous' in state.message


def test_expired_refresh_is_interrupted_not_running():
    release = SimpleNamespace(status='INDEXING', merged_sha='c'*40, pr_number=5)
    job = SimpleNamespace(kind='activate_release', payload={'pr_number': 5}, status='PROCESSING',
        claimed_at=utcnow()-timedelta(hours=1), created_at=utcnow())
    assert release_status(release, [job]).label == 'Refresh interrupted'


def test_uncertainty_resolution_counts_as_completed_decision(system):
    settings, engine, factory, repo_id = system
    with factory() as session:
        case, section, _, _ = make_case(session, repo_id, decision='UNCERTAIN', with_proposal=False)
        session.commit()
        triage_section(session, section.id, 'NO_CHANGE', 'Reviewed available evidence.')
    state = load(Context(settings, engine, factory, repo_id))['cases'][0]
    assert state['required'] == state['approved'] == 1
    assert state['status'].label == 'Review complete'


@pytest.mark.parametrize('tamper', [False, True])
def test_public_merge_reconciliation_persists_no_index_activation(system, monkeypatch, tamper):
    settings, engine, factory, repo_id = system
    with factory() as session:
        case, section, proposal, version = make_case(session, repo_id, accepted=True)
        release = DocumentationRelease(case_id=case.id, repo_id=repo_id, branch='codex/sample', commit_sha='d'*40,
            pr_number=5, pr_url='https://example/pr/5', status='PENDING_MERGE')
        session.add(release); session.commit(); release_id = release.id
    pr = {'merged': True, 'merge_commit_sha': 'c'*40, 'base': {'ref':'master'},
        'head': {'sha': ('e' if tamper else 'd')*40, 'repo': {'full_name': settings.repository}}}
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: pr)
    monkeypatch.setattr('docsync.online.status.httpx.get', lambda *args, **kwargs: response)
    if tamper:
        with pytest.raises(ValueError, match='identity'):
            reconcile_release(factory, release_id)
    else:
        reconcile_release(factory, release_id)
        reconcile_release(factory, release_id)
    with factory() as session:
        release = session.get(DocumentationRelease, release_id)
        assert release.status == ('PENDING_MERGE' if tamper else 'MERGED')
        assert session.get(Repository, repo_id).active_index_version_id is None
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.kind == 'documentation_merge_confirmed')) == (0 if tamper else 1)
