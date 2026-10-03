from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import select, func

from test_online_phase2 import system, make_case
from docsync.online.actions import event_input, register, sha
from docsync.online.operations import execute
from docsync.web.database import session_factory
from docsync.web.indexing import IndexInput, replace_approved_sections
from docsync.web.models import Job, Proposal, ProposalVersion, Repository, KnowledgeVersion, IndexedSection, AuditEvent, utcnow
from docsync.web.workflow import modify_proposal, accept_proposal, reject_proposal


def push(settings, **kwargs):
    return {'repository': {'full_name': settings.repository}, 'ref': 'refs/heads/master',
        'before': 'a' * 40, 'after': 'b' * 40, **kwargs}


def test_push_event_contract(system):
    settings, *_ = system
    kind, data = event_input(settings, 'push', push(settings))
    assert kind == 'analyze_push'
    assert data == {'before_sha': 'a' * 40, 'after_sha': 'b' * 40}
    assert event_input(settings, 'push', push(settings, ref='refs/heads/unmonitored')) is None
    assert event_input(settings, 'push', push(settings, deleted=True)) is None
    with pytest.raises(PermissionError):
        event_input(settings, 'push', push(settings, repository={'full_name': 'attacker/repo'}))


@pytest.mark.parametrize('value', ['HEAD', '-x', '0' * 40, 'a' * 39, None, 'a' * 40 + ';echo bad'])
def test_commit_validation(value):
    with pytest.raises(ValueError):
        sha(value)


def test_merge_event_is_not_branch_name_approval(system):
    settings, *_ = system
    payload = {'repository': {'full_name': settings.repository}, 'action': 'closed',
        'pull_request': {'number': 4, 'merged': True, 'base': {'ref': 'master'}, 'head': {'ref': 'anything'}, 'merge_commit_sha': 'c' * 40}}
    assert event_input(settings, 'pull_request', payload)[0] == 'activate_release'
    payload['pull_request']['merged'] = False
    assert event_input(settings, 'pull_request', payload) is None


def test_replayed_actions_deduplicate_across_run_ids(system):
    settings, engine, factory, _ = system
    data = {'before_sha': 'a' * 40, 'after_sha': 'b' * 40}
    first = register(engine, settings, 'analyze_push', data, run_id='1', run_url='https://example/run/1')
    second = register(engine, settings, 'analyze_push', data, run_id='2')
    assert first == second
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        event = session.scalar(select(AuditEvent).where(AuditEvent.kind == 'action_received'))
        assert event.payload['run_url'] == 'https://example/run/1'


def test_unregistered_pr_cannot_index(system):
    settings, engine, factory, _ = system
    assert register(engine, settings, 'activate_release', {'pr_number': 4, 'merge_sha': 'c' * 40}) is None
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_finite_operation_completes_once(system, monkeypatch):
    settings, engine, factory, repo_id = system
    with factory() as session:
        job = Job(repo_id=repo_id, kind='index_baseline', payload={})
        session.add(job); session.commit(); job_id = job.id
    calls = []
    monkeypatch.setattr('docsync.online.operations._process_job', lambda *args: calls.append(args))
    assert execute(engine, settings, job_id, run_url='https://example/run') is True
    assert execute(engine, settings, job_id) is False
    assert len(calls) == 1
    with factory() as session:
        assert session.get(Job, job_id).claimed_at is not None
        assert session.get(Job, job_id).attempts == 1


def test_error_and_interrupted_lease_require_explicit_retry(system, monkeypatch):
    settings, engine, factory, repo_id = system
    with factory() as session:
        job = Job(repo_id=repo_id, kind='index_baseline', payload={}, status='PROCESSING', claimed_at=utcnow())
        session.add(job); session.commit(); job_id = job.id
    with pytest.raises(ValueError, match='already running'):
        execute(engine, settings, job_id, retry=True)
    with factory() as session:
        session.get(Job, job_id).claimed_at = utcnow() - timedelta(hours=1); session.commit()
    with pytest.raises(ValueError, match='explicit retry'):
        execute(engine, settings, job_id)
    monkeypatch.setattr('docsync.online.operations._process_job', lambda *args: (_ for _ in ()).throw(RuntimeError('failed')))
    with pytest.raises(RuntimeError):
        execute(engine, settings, job_id, retry=True)
    with factory() as session:
        assert session.get(Job, job_id).status == 'ERROR'
    with pytest.raises(ValueError, match='explicit retry'):
        execute(engine, settings, job_id)


def test_stale_displayed_version_cannot_be_reviewed(system):
    settings, engine, factory, repo_id = system
    with factory() as session:
        case, assessment, proposal, original = make_case(session, repo_id)
        session.commit()
        human = modify_proposal(session, proposal.id, '## Default timeout\nExact human text.\n', original.id)
        assert human.human_modified is True
        with pytest.raises(ValueError, match='refresh'):
            accept_proposal(session, proposal.id, original.id)
        session.rollback()
        with pytest.raises(ValueError, match='refresh'):
            reject_proposal(session, proposal.id, 'Reason', original.id)
        session.rollback()
        accept_proposal(session, proposal.id, human.id)
        assert session.get(Proposal, proposal.id).accepted_version_id == human.id


def test_incremental_index_reuses_vectors_and_activation_can_rollback(system):
    settings, engine, factory, repo_id = system
    class Embedder:
        def __init__(self): self.calls = []
        def embed(self, text): self.calls.append(text); return [1.0] + [0.0] * 383
    embedding = Embedder()
    with factory() as session:
        repo = session.get(Repository, repo_id)
        initial = replace_approved_sections(session, repo, 'a' * 40,
            [IndexInput('one', 'docs/a.md', 'A', 'A', 'a' * 40), IndexInput('two', 'docs/b.md', 'B', 'B', 'a' * 40)], embedding)
        session.commit(); initial_id = initial.id
        replacement = replace_approved_sections(session, repo, 'b' * 40,
            [IndexInput('one', 'docs/a.md', 'A', 'A2', 'b' * 40)], embedding)
        assert embedding.calls == ['A', 'B', 'A2']
        unchanged = session.scalar(select(IndexedSection).where(IndexedSection.version_id == replacement.id, IndexedSection.section_id == 'two'))
        assert unchanged.source_commit == 'a' * 40
        assert list(unchanged.embedding) == [1.0] + [0.0] * 383
        session.rollback()
    with factory() as session:
        assert session.get(Repository, repo_id).active_index_version_id == initial_id
        assert session.scalar(select(func.count()).select_from(KnowledgeVersion)) == 1


def test_schema_migration_is_idempotent_and_preserves_human_provenance(system, monkeypatch):
    from alembic import command
    from alembic.config import Config
    settings, engine, factory, repo_id = system
    monkeypatch.setenv('DATABASE_URL', settings.database_url)
    with factory() as session:
        case, assessment, proposal, version = make_case(session, repo_id)
        version.author = 'human'
        session.commit(); version_id = version.id
    command.upgrade(Config('alembic.ini'), 'head')
    command.upgrade(Config('alembic.ini'), 'head')
    with factory() as session:
        assert session.get(ProposalVersion, version_id).human_modified is True


@pytest.mark.parametrize('change', ['code', 'documentation', 'unapproved_drift'])
def test_complete_git_snapshot_preparation(system, tmp_path, monkeypatch, change):
    from contextlib import contextmanager
    from test_online_phase2 import _git
    from docsync.online.actions import prepare_push
    from docsync.repository.markdown_sections import parse_sections
    settings, engine, factory, repo_id = system
    root = tmp_path / 'snapshot'
    root.mkdir()
    _git('init', '--initial-branch=master', cwd=root)
    _git('config', 'user.name', 'Test', cwd=root)
    _git('config', 'user.email', 'test@example.invalid', cwd=root)
    (root / 'docs').mkdir()
    document = root / 'docs' / 'settings.md'
    document.write_text('## Settings\nThe visible value is four.\n', encoding='utf-8')
    code = root / 'service.py'
    code.write_text('def value():\n    return 4\n', encoding='utf-8')
    _git('add', '.', cwd=root); _git('commit', '-m', 'approved baseline', cwd=root)
    before = _git('rev-parse', 'HEAD', cwd=root)
    section = parse_sections('docs/settings.md', document.read_text(encoding='utf-8'))[0]
    class Embedder:
        def embed(self, text): return [1.0] + [0.0] * 383
    with factory() as session:
        replace_approved_sections(session, session.get(Repository, repo_id), before,
            [IndexInput(section.section_id, section.path, section.heading, section.text, before)], Embedder())
        session.commit()
    if change != 'documentation':
        code.write_text('def value():\n    return 6\n', encoding='utf-8')
    if change != 'code':
        document.write_text('## Settings\nUnapproved altered text.\n', encoding='utf-8')
    _git('add', '.', cwd=root); _git('commit', '-m', 'changed snapshot', cwd=root)
    after = _git('rev-parse', 'HEAD', cwd=root)
    @contextmanager
    def clone(*args):
        yield root, lambda *args: _git(*args, cwd=root), {}
    monkeypatch.setattr('docsync.online.actions.cloned_repository', clone)
    monkeypatch.setattr('docsync.online.actions.approved_mappings', lambda *args:
        [{'code_id': 'service.py::value', 'section_id': section.section_id, 'reason': 'approved'}])
    data = {'before_sha': before, 'after_sha': after}
    if change == 'unapproved_drift':
        with pytest.raises(ValueError, match='differs'):
            prepare_push(engine, settings, data)
    else:
        assert prepare_push(engine, settings, data) is (change == 'code')
        assert 'changed snapshot' in data['commits']
        if change == 'code':
            assert data['changed_paths'] == ['service.py']
            assert data['approved_documentation_commits'][section.section_id] == before
