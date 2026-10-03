import json
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from docsync.errors import ConflictError, ModelError
from docsync.sarvam import ModelClient
from docsync.knowledge.conflicts import candidate_pairs
from docsync.knowledge.gate import (stage_scan, scan_pending, prepare_gate, resolve,
    KnowledgeReviewPending, rows, unresolved)
from docsync.web.indexing import IndexInput, replace_approved_sections, retrieve
from docsync.web.models import (Repository, KnowledgeScan, KnowledgeConflict, ConflictResolution,
    KnowledgeVersion, IndexedSection, SarvamCall, Job, utcnow)
from test_online_phase2 import system, _git


class Embedder:
    def __init__(self): self.calls = []
    def embed(self, text): self.calls.append(text); return [1.] + [0.] * 383


class Client(ModelClient):
    def __init__(self, classification='HARD_CONFLICT', *, uncertain=False, fail=None):
        self.classification, self.uncertain, self.fail = classification, uncertain, fail
        self.requests = []
    def complete(self, system, user, schema_name, schema):
        data = json.loads(user.split('\n\n')[0])
        self.requests.append(data)
        if self.fail == 'transport':
            raise ModelError('Unavailable', category='API_ERROR')
        left, right = data['left'], data['right']
        return json.dumps({'left_id': left['section_id'] if self.fail != 'identity' else 'foreign::id',
            'right_id': right['section_id'], 'classification': self.classification,
            'reason': 'Same capability has incompatible lifecycle descriptions.',
            'left_claims': [left['content'] if self.fail != 'quote' else 'Invented quote'],
            'right_claims': [right['content']], 'uncertain': self.uncertain,
            'missing_information': ['Source scopes need a human check.'] if self.uncertain else []})


def inputs(commit='a' * 40):
    return [IndexInput('docs/guide.md::report-export', 'docs/guide.md', 'Report export',
                'Report export is available to users.', commit),
        IndexInput('docs/roadmap.md::report-export', 'docs/roadmap.md', 'Report export',
                'Report export is planned and unavailable.', commit),
        IndexInput('docs/auth.md::tokens', 'docs/auth.md', 'Tokens', 'Credentials expire hourly.', commit)]


def staged(factory, repo_id, changed=None, commit='a' * 40):
    with factory() as session:
        scan = stage_scan(session, session.get(Repository, repo_id), commit, changed or inputs(commit))
        session.commit()
        return scan.id


def test_narrowing_is_generic_and_incremental_pair_selection_is_complete():
    data = [vars(s) for s in inputs()]
    pairs = candidate_pairs(data)
    assert [(a, b) for a, b, _ in pairs] == [('docs/guide.md::report-export', 'docs/roadmap.md::report-export')]
    assert not candidate_pairs(data, {'docs/auth.md::tokens'})
    assert candidate_pairs(data, {'docs/roadmap.md::report-export'}) == pairs


def test_openbull_derived_overlap_is_selected_without_inventing_a_quality_label():
    from pathlib import Path
    fixture = json.loads((Path(__file__).resolve().parents[1] / 'evals/openbull/conflict-candidate.json').read_text(encoding='utf-8'))
    assert len(candidate_pairs(fixture['sections'])) == 1
    assert fixture['classification_label'] is None and fixture['human_label_source'] is None


@pytest.mark.parametrize('classification,uncertain,blocked', [('NO_CONFLICT', False, False),
    ('SCOPE_DIFFERENCE', False, False), ('VERSION_DRIFT', False, True), ('HARD_CONFLICT', False, True),
    ('NO_CONFLICT', True, True)])
def test_semantic_classes_and_uncertainty_control_activation(system, classification, uncertain, blocked):
    _, engine, factory, repo_id = system
    scan_id = staged(factory, repo_id)
    client = Client(classification, uncertain=uncertain)
    assert scan_pending(engine, repo_id, scan_id, client) == ('REVIEW_REQUIRED' if blocked else 'READY')
    with factory() as session:
        repo = session.get(Repository, repo_id)
        if blocked:
            with pytest.raises(KnowledgeReviewPending):
                replace_approved_sections(session, repo, 'a'*40, inputs(), Embedder(), conflict_scan_id=scan_id)
            assert not repo.active_index_version_id
        else:
            version = replace_approved_sections(session, repo, 'a'*40, inputs(), Embedder(), conflict_scan_id=scan_id)
            session.commit()
            assert version.active


def test_direct_activation_cannot_bypass_scan(system):
    _, _, factory, repo_id = system
    embedding = Embedder()
    with factory() as session:
        with pytest.raises(KnowledgeReviewPending):
            replace_approved_sections(session, session.get(Repository, repo_id), 'a'*40, inputs(), embedding)
        assert not embedding.calls
        assert session.scalar(select(func.count()).select_from(KnowledgeVersion)) == 0


@pytest.mark.parametrize('action,excluded', [('PREFER_A', {'docs/roadmap.md::report-export'}),
    ('PREFER_B', {'docs/guide.md::report-export'}), ('DIFFERENT_SCOPES', set()),
    ('EXCLUDE_A', {'docs/guide.md::report-export'}), ('EXCLUDE_B', {'docs/roadmap.md::report-export'}),
    ('EXCLUDE_BOTH', {'docs/guide.md::report-export', 'docs/roadmap.md::report-export'})])
def test_human_resolution_is_durable_idempotent_and_excludes_retrieval(system, action, excluded):
    _, engine, factory, repo_id = system
    scan_id = staged(factory, repo_id)
    client = Client()
    scan_pending(engine, repo_id, scan_id, client)
    with factory() as session:
        scan = session.get(KnowledgeScan, scan_id)
        pair = rows(session, scan)[0]
        resolution = resolve(session, repo_id, pair.id, action, 'Reviewed source and scope evidence.', 'human-test')
        session.commit()
        assert resolve(session, repo_id, pair.id, action, resolution.rationale, 'human-test').id == resolution.id
        assert session.scalar(select(func.count()).select_from(ConflictResolution)) == 1
        assert session.get(KnowledgeScan, scan_id).state == 'READY'
        with pytest.raises(ValueError, match='already recorded'):
            resolve(session, repo_id, pair.id, 'EXCLUDE_A' if action != 'EXCLUDE_A' else 'EXCLUDE_B', 'Different.', 'human-test')
        session.rollback()
        repo = session.get(Repository, repo_id)
        replace_approved_sections(session, repo, 'a'*40, inputs(), Embedder(), conflict_scan_id=scan_id)
        session.commit()
        _, chunks = retrieve(session, repo, Embedder().embed('query'), 20)
        assert {r.section_id for r in chunks} == {s.section_id for s in inputs()} - excluded
        assert scan_pending(engine, repo_id, scan_id, client) == 'ACTIVATED'
        assert len(client.requests) == 1


@pytest.mark.parametrize('fail,attempts', [('transport', 1), ('identity', 2), ('quote', 2)])
def test_failed_assessments_remain_retryable_and_never_activate(system, fail, attempts):
    _, engine, factory, repo_id = system
    scan_id = staged(factory, repo_id)
    with pytest.raises(ModelError):
        scan_pending(engine, repo_id, scan_id, Client(fail=fail))
    with factory() as session:
        assert session.get(KnowledgeScan, scan_id).state == 'ERROR'
        calls = session.scalars(select(SarvamCall).where(SarvamCall.operation == 'conflict')).all()
        assert len(calls) == attempts and all(c.metadata_json['repo_id'] == repo_id for c in calls)
        assert not session.get(Repository, repo_id).active_index_version_id
    assert scan_pending(engine, repo_id, scan_id, Client('SCOPE_DIFFERENCE')) == 'READY'


def test_scan_deduplication_is_bound_to_parent_and_full_input_hash(system):
    _, engine, factory, repo_id = system
    first = staged(factory, repo_id)
    assert staged(factory, repo_id) == first
    altered = inputs(); altered[0] = IndexInput(altered[0].section_id, altered[0].path, altered[0].heading,
        'Report export is available only in sandbox.', 'a'*40)
    second = staged(factory, repo_id, altered)
    assert second != first
    scan_pending(engine, repo_id, first, Client('SCOPE_DIFFERENCE'))
    with factory() as session:
        with pytest.raises(ConflictError, match='does not match'):
            replace_approved_sections(session, session.get(Repository, repo_id), 'a'*40,
                altered, Embedder(), conflict_scan_id=first)


def test_incremental_conflict_preserves_old_version_and_unchanged_vectors(system):
    _, engine, factory, repo_id = system
    baseline = [inputs()[0], inputs()[2]]
    embedder = Embedder()
    with factory() as session:
        repo = session.get(Repository, repo_id)
        initial = replace_approved_sections(session, repo, 'a'*40, baseline, embedder)
        session.commit(); parent = initial.id
    changed = [inputs('b'*40)[1]]
    with pytest.raises(KnowledgeReviewPending):
        prepare_gate(engine, repo_id, 'b'*40, changed, parent_id=parent, client=Client('VERSION_DRIFT'))
    with factory() as session:
        repo = session.get(Repository, repo_id)
        assert repo.active_index_version_id == parent
        scan = session.scalar(select(KnowledgeScan).where(KnowledgeScan.source_commit == 'b'*40))
        pair = rows(session, scan)[0]
        resolve(session, repo_id, pair.id, 'PREFER_B', 'Reviewed revised source.', 'human-test')
        session.commit(); scan_id = scan.id
    assert prepare_gate(engine, repo_id, 'b'*40, changed, parent_id=parent, client=Client()) == scan_id
    with factory() as session:
        repo = session.get(Repository, repo_id)
        version = replace_approved_sections(session, repo, 'b'*40, changed, embedder, conflict_scan_id=scan_id)
        session.commit()
        assert embedder.calls == [s.content for s in baseline] + [changed[0].content]
        _, chunks = retrieve(session, repo, Embedder().embed('query'), 20)
        assert {s.section_id for s in chunks} == {'docs/roadmap.md::report-export', 'docs/auth.md::tokens'}
        old = session.scalars(select(IndexedSection).where(IndexedSection.version_id == parent)).all()
        assert len(old) == 2 and not session.get(KnowledgeVersion, parent).active
        unchanged = next(r for r in chunks if r.section_id == 'docs/auth.md::tokens')
        assert unchanged.source_commit == 'a'*40
        assert session.get(KnowledgeScan, scan_id).activated_version_id == version.id


def test_foreign_scan_resolution_and_stale_parent_cannot_activate(system):
    _, engine, factory, repo_id = system
    scan_id = staged(factory, repo_id)
    with factory() as session:
        other = Repository(full_name='other/project', monitored_branch='main')
        session.add(other); session.commit(); other_id = other.id
        pair = rows(session, session.get(KnowledgeScan, scan_id))[0]
        with pytest.raises(ValueError, match='another repository'):
            resolve(session, other_id, pair.id, 'PREFER_A', 'Reason', 'human')
        with pytest.raises(ValueError, match='another repository'):
            replace_approved_sections(session, other, 'a'*40, inputs(), Embedder(), conflict_scan_id=scan_id)
        replace_approved_sections(session, session.get(Repository, repo_id), 'z'*40, [inputs()[2]], Embedder())
        session.commit()
    with pytest.raises(ConflictError, match='stale'):
        scan_pending(engine, repo_id, scan_id, Client())


def test_active_lease_cannot_be_taken_over(system):
    _, engine, factory, repo_id = system
    scan_id = staged(factory, repo_id)
    with factory() as session:
        scan = session.get(KnowledgeScan, scan_id)
        scan.state, scan.claimed_at = 'SCANNING', utcnow()
        session.commit()
    with pytest.raises(ValueError, match='already running'):
        scan_pending(engine, repo_id, scan_id, Client())
    with factory() as session:
        session.get(KnowledgeScan, scan_id).claimed_at = utcnow() - timedelta(hours=1)
        session.commit()
    assert scan_pending(engine, repo_id, scan_id, Client()) == 'REVIEW_REQUIRED'


def test_waiting_review_is_an_expected_durable_job_boundary(system, monkeypatch):
    from docsync.online.operations import execute
    _, engine, factory, repo_id = system
    with factory() as session:
        job = Job(repo_id=repo_id, kind='index_baseline', payload={'baseline_sha': 'a'*40})
        session.add(job); session.commit(); job_id = job.id
    monkeypatch.setattr('docsync.online.operations._process_job', lambda *args:
        prepare_gate(engine, repo_id, 'a'*40, inputs(), parent_id=None))
    assert execute(engine, system[0], job_id) is False
    with factory() as session:
        assert session.get(Job, job_id).status == 'WAITING_REVIEW'
        assert session.scalar(select(func.count()).select_from(KnowledgeScan)) == 1
        assert not session.get(Repository, repo_id).active_index_version_id


def test_audit_of_existing_knowledge_changes_only_human_exclusions(system):
    from docsync.knowledge.gate import audit_current, activate_audit
    _, engine, factory, repo_id = system
    scan_id = staged(factory, repo_id)
    scan_pending(engine, repo_id, scan_id, Client('SCOPE_DIFFERENCE'))
    with factory() as session:
        repo = session.get(Repository, repo_id)
        version = replace_approved_sections(session, repo, 'a'*40, inputs(), Embedder(), conflict_scan_id=scan_id)
        session.commit(); original = version.id
    audit_id = audit_current(engine, repo_id)
    assert audit_current(engine, repo_id) == audit_id
    scan_pending(engine, repo_id, audit_id, Client('VERSION_DRIFT'))
    with factory() as session:
        pair = rows(session, session.get(KnowledgeScan, audit_id))[0]
        resolve(session, repo_id, pair.id, 'PREFER_A', 'Human confirms shipped source is current.', 'human-test')
        session.commit()
    activated = activate_audit(engine, repo_id, audit_id)
    assert activate_audit(engine, repo_id, audit_id) == activated
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(IndexedSection).where(IndexedSection.version_id == original)) == 3
        new = session.scalars(select(IndexedSection).where(IndexedSection.version_id == activated)).all()
        assert {s.section_id for s in new} == {'docs/guide.md::report-export', 'docs/auth.md::tokens'}
        assert all(s.source_commit == 'a'*40 and list(s.embedding) == [1.] + [0.] * 383 for s in new)


def test_migration_from_prior_schema_preserves_history(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from docsync.web.database import make_engine, session_factory
    from docsync.web.models import Base, AuditEvent
    from sqlalchemy import inspect
    url = 'sqlite:///' + str(tmp_path / 'old.sqlite3')
    engine = make_engine(url)
    excluded = {'knowledge_scans', 'knowledge_conflicts', 'conflict_resolutions'}
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in excluded])
    with session_factory(engine)() as session:
        session.add(AuditEvent(id='durable-history', kind='human_review', payload={'preserved': True}))
        session.commit()
    assert not excluded & set(inspect(engine).get_table_names())
    monkeypatch.setenv('DATABASE_URL', url)
    command.stamp(Config('alembic.ini'), '003_lifecycle')
    command.upgrade(Config('alembic.ini'), 'head')
    command.upgrade(Config('alembic.ini'), 'head')
    assert excluded <= set(inspect(engine).get_table_names())
    with session_factory(engine)() as session:
        assert session.get(AuditEvent, 'durable-history').payload == {'preserved': True}
    engine.dispose()


def test_conflict_repository_ownership_is_enforced_by_foreign_key(system):
    from sqlalchemy.exc import IntegrityError
    _, _, factory, repo_id = system
    scan_id = staged(factory, repo_id)
    with factory() as session:
        session.connection().exec_driver_sql('PRAGMA foreign_keys=ON')
        other = Repository(full_name='foreign/owner', monitored_branch='main')
        session.add(other); session.commit()
        session.add(KnowledgeConflict(repo_id=other.id, scan_id=scan_id, left_id='x', right_id='y'))
        with pytest.raises(IntegrityError):
            session.commit()


def test_baseline_waits_for_human_ui_review_then_resumes_once(system, tmp_path, monkeypatch):
    from contextlib import contextmanager
    from docsync.online.operations import execute
    from test_multi_repository import launch
    settings, engine, factory, repo_id = system
    root = tmp_path / 'source'; root.mkdir()
    _git('init', '--initial-branch=master', cwd=root)
    _git('config', 'user.name', 'QA', cwd=root)
    _git('config', 'user.email', 'qa@example.invalid', cwd=root)
    (root / 'docs').mkdir()
    for section in inputs():
        (root / section.path).write_text('## ' + section.heading + '\n' + section.content + '\n', encoding='utf-8')
    _git('add', '.', cwd=root); _git('commit', '-m', 'Reviewed source', cwd=root)
    commit = _git('rev-parse', 'HEAD', cwd=root)
    @contextmanager
    def clone(*args):
        yield root, lambda *args: _git(*args, cwd=root), {}
    class GitHub:
        def __init__(self, settings): self.settings = settings
        def installation_token(self, *args): return 'test-token'
        def close(self): pass
    monkeypatch.setattr('docsync.web.worker.GitHubClient', GitHub)
    monkeypatch.setattr('docsync.web.worker.cloned_repository', clone)
    monkeypatch.setattr('docsync.web.worker.approved_mappings', lambda *args: [])
    monkeypatch.setattr('docsync.web.worker.SentenceEmbedder', lambda *args: Embedder())
    monkeypatch.delenv('SARVAM_API_KEY', raising=False)
    with factory() as session:
        job = Job(repo_id=repo_id, kind='index_baseline', payload={'baseline_sha': commit})
        session.add(job); session.commit(); job_id = job.id
    assert execute(engine, settings, job_id) is False
    client = Client('VERSION_DRIFT')
    monkeypatch.setattr('docsync.ui.conflicts.SarvamClient', lambda *args: client)
    app = launch(settings, monkeypatch)
    app.sidebar.radio[0].set_value('Knowledge').run(timeout=20)
    next(b for b in app.button if b.label == 'Run / resume semantic conflict scan').click().run(timeout=20)
    assert not app.exception and not app.error
    next(t for t in app.text_area if t.label == 'Rationale and scope evidence').set_value('Human confirms available source reflects shipped capability.')
    next(b for b in app.button if b.label == 'Record human resolution').click().run(timeout=20)
    assert not app.exception and not app.error
    with factory() as session:
        assert not session.get(Repository, repo_id).active_index_version_id
    next(b for b in app.button if b.label == 'Resume verified knowledge activation').click().run(timeout=20)
    assert not app.exception and not app.error
    with factory() as session:
        assert session.get(Job, job_id).status == 'COMPLETED'
        repo = session.get(Repository, repo_id)
        assert repo.active_index_version_id
        _, chunks = retrieve(session, repo, Embedder().embed('query'), 20)
        assert {s.section_id for s in chunks} == {'docs/guide.md::report-export', 'docs/auth.md::tokens'}
    assert len(client.requests) == 1
    assert execute(engine, settings, job_id) is False


def test_partial_scan_batches_resume_without_repeating_completed_pairs(system):
    _, engine, factory, repo_id = system
    sections = [IndexInput(f'docs/{i}.md::export', f'docs/{i}.md', 'Report export',
        'Report export remains available.', 'a'*40) for i in range(4)]
    scan_id = staged(factory, repo_id, sections)
    client = Client('NO_CONFLICT')
    assert scan_pending(engine, repo_id, scan_id, client) == 'PENDING'
    assert len(client.requests) == 4
    assert scan_pending(engine, repo_id, scan_id, client) == 'READY'
    assert len(client.requests) == 6
    assert len({(r['left']['section_id'], r['right']['section_id']) for r in client.requests}) == 6


def test_human_resolution_during_partial_scan_keeps_remaining_pairs_scannable(system):
    _, engine, factory, repo_id = system
    sections = [IndexInput(f'docs/{i}.md::export', f'docs/{i}.md', 'Report export',
        'Report export remains available.', 'a'*40) for i in range(4)]
    scan_id = staged(factory, repo_id, sections)
    assert scan_pending(engine, repo_id, scan_id, Client('VERSION_DRIFT')) == 'PENDING'
    with factory() as session:
        scan = session.get(KnowledgeScan, scan_id)
        pair = next(p for p in rows(session, scan) if p.classification)
        resolve(session, repo_id, pair.id, 'DIFFERENT_SCOPES', 'Human confirms distinct configurations.', 'human-test')
        session.commit()
        assert scan.state == 'PENDING'
    client = Client('NO_CONFLICT')
    assert scan_pending(engine, repo_id, scan_id, client) == 'REVIEW_REQUIRED'
    assert len(client.requests) == 2


def test_verified_incremental_release_waits_then_resumes_without_reanalysis(system, monkeypatch):
    from types import SimpleNamespace
    from test_online_phase2 import make_case
    from docsync.online.operations import execute
    from docsync.web.models import DocumentationRelease, ReleaseSection
    from docsync.repository.markdown_sections import parse_sections, section_sha256
    settings, engine, factory, repo_id = system
    baseline = [inputs()[1], inputs()[2]]
    content = '## Report export\nReport export is available to users.\n'
    parsed = parse_sections('docs/guide.md', content)[0]
    with factory() as session:
        replace_approved_sections(session, session.get(Repository, repo_id), 'a'*40, baseline, Embedder())
        case, *_ = make_case(session, repo_id, accepted=True)
        release = DocumentationRelease(repo_id=repo_id, case_id=case.id, branch='codex/review',
            commit_sha='d'*40, pr_number=44, pr_url='https://example/44')
        session.add(release); session.flush()
        session.add(ReleaseSection(release_id=release.id, section_id=parsed.section_id,
            path=parsed.path, text=parsed.text, sha256=section_sha256(parsed.text)))
        job = Job(repo_id=repo_id, kind='activate_release', payload={'pr_number': 44, 'merge_sha': 'b'*40})
        session.add(job); session.commit()
        parent = session.get(Repository, repo_id).active_index_version_id
        release_id, job_id = release.id, job.id
    class GitHub:
        def __init__(self, settings): self.settings = settings
        def installation_token(self, *args): return 'test-token'
        def request(self, method, path, token):
            if '/compare/' in path: return SimpleNamespace(json=lambda: {'status': 'ahead'})
            return SimpleNamespace(json=lambda: {'merged': True, 'merge_commit_sha': 'b'*40,
                'head': {'sha': 'd'*40, 'repo': {'full_name': settings.repository}}, 'base': {'ref': settings.monitored_branch}})
        def file_at(self, *args): return content
        def close(self): pass
    monkeypatch.setattr('docsync.web.worker.GitHubClient', GitHub)
    monkeypatch.setattr('docsync.web.worker.SentenceEmbedder', lambda *args: Embedder())
    monkeypatch.delenv('SARVAM_API_KEY', raising=False)
    assert execute(engine, settings, job_id) is False
    with factory() as session:
        assert session.get(DocumentationRelease, release_id).status == 'KNOWLEDGE_REVIEW'
        assert session.get(Repository, repo_id).active_index_version_id == parent
        scan = session.scalar(select(KnowledgeScan).where(KnowledgeScan.source_commit == 'b'*40))
        scan_id = scan.id
    client = Client('VERSION_DRIFT')
    scan_pending(engine, repo_id, scan_id, client)
    with factory() as session:
        pair = rows(session, session.get(KnowledgeScan, scan_id))[0]
        resolve(session, repo_id, pair.id, 'PREFER_A', 'Human confirms reviewed release is current.', 'human')
        session.commit()
    assert execute(engine, settings, job_id) is True
    with factory() as session:
        release = session.get(DocumentationRelease, release_id)
        assert release.status == 'INDEXED' and release.activated_at
        assert session.get(Repository, repo_id).active_index_version_id != parent
        _, chunks = retrieve(session, session.get(Repository, repo_id), Embedder().embed('query'), 20)
        assert {s.section_id for s in chunks} == {'docs/guide.md::report-export', 'docs/auth.md::tokens'}
    assert len(client.requests) == 1
