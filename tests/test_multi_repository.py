from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from sqlalchemy import select, func
from streamlit.testing.v1 import AppTest

from test_online_phase2 import system, make_case, _git
from docsync.ui.components import Context, case_title, summary_preview
from docsync.ui.state import load
from docsync.ui.workspace import repositories, select_repository, switch_repository, scoped_settings
from docsync.ui.reviews import service
from docsync.ui.history import activity_rows
from docsync.online.onboarding import connect_repository, verify_access, discover, mapping_suggestions, confirm_mapping, workflow_files
from docsync.online.operations import execute
from docsync.web.repository import ensure_repository
from docsync.web.workflow import approved_mappings, accept_proposal
from docsync.web.models import (Repository, CodeDocMapping, AuditEvent, Job, KnowledgeVersion,
    DocumentationRelease, ChatTurn, Proposal)
from docsync.web.indexing import IndexInput, replace_approved_sections, retrieve
from docsync.web.chat import chat_history, answer_question


class Embedder:
    def embed(self, text):
        return [1.0] + [0.0] * 383


def second_repo(session):
    return connect_repository(session, {'name': 'AnotherOwner/project', 'branch': 'main', 'installation_id': 88})


def snapshot(repo_id):
    return {'repo_id': repo_id, 'sha': 'e'*40,
        'symbols': [{'code_id': 'src/auth.py::validate_token', 'source': 'def validate_token(): pass'}],
        'sections': [{'section_id': 'README.md::token-validation', 'text': '## Token validation\nTokens.'}]}


def test_bootstrap_is_httpx_only_and_two_repositories_coexist(system):
    settings, _, factory, first = system
    with factory() as session:
        original = session.get(Repository, first)
        mappings = approved_mappings(session, first)
        assert mappings
        second = ensure_repository(session, replace(settings, repository='AnotherOwner/project', monitored_branch='main', github_installation_id=None))
        session.commit()
        assert approved_mappings(session, second.id) == []
        assert approved_mappings(session, first) == mappings
        assert len(repositories(session)) == 2
        assert original.monitored_branch == 'master'
        assert original.installation_id == 77


def test_selection_uses_ids_and_repository_specific_context(system):
    settings, engine, factory, first = system
    with factory() as session:
        second = second_repo(session)
        rows = repositories(session)
    state = {}
    assert select_repository(rows, state, settings.repository).id == first
    state.update(case_id='old-case', editing='old-version', drafts={'old': 'unsaved'}, reask='old question',
        last_question='old', **{'editor-old': 'old', 'triage-choice-old': 'old', 'question': 'old', 'authenticated': True})
    switch_repository(state, second.id)
    assert set(state) == {'repository_id', 'authenticated'}
    assert select_repository(rows, state, settings.repository).id == second.id
    ctx = Context(scoped_settings(settings, second), engine, factory, second.id)
    assert ctx.repo_id == second.id and ctx.settings.repository == second.full_name
    assert ctx.settings.monitored_branch == 'main' and ctx.settings.github_installation_id == 88
    state['repository_id'] = 'missing'
    assert select_repository(rows, state, '').id == first


def test_all_read_models_and_baseline_history_are_isolated(system):
    settings, engine, factory, first = system
    with factory() as session:
        second = second_repo(session)
        for repo_id, char in [(first, 'a'), (second.id, 'b')]:
            case, *_ = make_case(session, repo_id)
            job = Job(repo_id=repo_id, kind='index_baseline', payload={})
            session.add(job)
            repo = session.get(Repository, repo_id)
            version = replace_approved_sections(session, repo, char*40,
                [IndexInput('shared', 'docs/a.md', 'A', f'Private to {repo_id}', char*40)], Embedder())
            session.add(DocumentationRelease(repo_id=repo_id, case_id=case.id, branch='docsync/case-'+case.id,
                commit_sha=char*40, pr_number=0, pr_url='', status='PREPARED'))
            session.add(ChatTurn(repo_id=repo_id, question=repo_id, answer='answer', citations=[], knowledge_version_id=version.id))
            session.add(AuditEvent(kind='approved_baseline_indexed', payload={'version_id': version.id}))  # legacy event
            session.add(AuditEvent(kind='repository_connected', payload={'repo_id': repo_id}))
            session.flush()
            session.add(AuditEvent(kind='operation_started', payload={'job_id': job.id}))
        session.commit()
    views = [load(Context(settings, engine, factory, r)) for r in [first, second.id]]
    assert views[0]['active'].id != views[1]['active'].id
    for view in views:
        repo_id = view['repo'].id
        assert len(view['cases']) == len(view['jobs']) == len(view['releases']) == len(view['versions']) == 1
        assert all(c['case'].repo_id == repo_id for c in view['cases'])
        assert all(r.repo_id == repo_id for r in view['releases'] + view['jobs'] + view['versions'])
        with factory() as session:
            version, rows = retrieve(session, session.get(Repository, repo_id), Embedder().embed('query'))
            assert version.id == view['active'].id
            assert [r.content for r in rows] == [f'Private to {repo_id}']
            assert [t.question for t in chat_history(session, repo_id)] == [repo_id]
            events = activity_rows(session, view)
            assert sum(e.kind == 'approved_baseline_indexed' for e in events) == 1
            assert all(e.case_id in {c['case'].id for c in view['cases']} or
                e.payload.get('repo_id') == repo_id or e.payload.get('version_id') == version.id or
                e.payload.get('job_id') in {j.id for j in view['jobs']} for e in events)


def test_wrong_active_pointer_cannot_retrieve_or_copy_other_knowledge(system):
    _, _, factory, first = system
    with factory() as session:
        second = second_repo(session)
        original = session.get(Repository, first)
        version = replace_approved_sections(session, original, 'a'*40,
            [IndexInput('private', 'docs/a.md', 'A', 'Private', 'a'*40)], Embedder())
        session.commit()
        second.active_index_version_id = version.id
        session.commit()
        with pytest.raises(ValueError, match='pointer'):
            retrieve(session, second, Embedder().embed('query'))
        with pytest.raises(ValueError, match='another repository'):
            replace_approved_sections(session, second, 'b'*40, [], Embedder())


def test_new_repository_chat_never_calls_model_before_baseline(system):
    settings, _, factory, _ = system
    with factory() as session:
        second = second_repo(session)
        class NoModel:
            def structured(self, *args, **kwargs):
                pytest.fail('No model call before approved baseline')
        with pytest.raises(ValueError, match='not been initialized'):
            answer_question(session, settings, second, 'question', Embedder(), NoModel())
        assert session.scalar(select(func.count()).select_from(ChatTurn)) == 0


def test_mapping_confirmation_scoped_audited_and_explicit(system):
    _, _, factory, first = system
    with factory() as session:
        second = second_repo(session)
        inspected = snapshot(second.id)
        count = len(approved_mappings(session, first))
        class Client:
            def structured(self, _system, _user, response, _name, **kwargs):
                return response.model_validate({'suggestions': [{'code_id': inspected['symbols'][0]['code_id'],
                    'section_id': inspected['sections'][0]['section_id'], 'reason': 'Describes validation'}]})
        suggestions = mapping_suggestions(session, second.id, inspected, Client())
        assert approved_mappings(session, second.id) == []
        item = suggestions[0]
        with pytest.raises(ValueError, match='another repository'):
            confirm_mapping(session, first, inspected, **item)
        with pytest.raises(ValueError, match='identities'):
            confirm_mapping(session, second.id, inspected, item['code_id'], 'missing', 'reason')
        row = confirm_mapping(session, second.id, inspected, **item)
        assert row.status == 'APPROVED' and row.repo_id == second.id
        assert len(approved_mappings(session, second.id)) == 1
        assert len(approved_mappings(session, first)) == count
        again = confirm_mapping(session, second.id, inspected, **item)
        assert again.id == row.id
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.kind == 'mapping_confirmed')) == 1


def test_review_mutations_and_jobs_reject_cross_repository_ids(system, monkeypatch):
    settings, engine, factory, first = system
    with factory() as session:
        second = second_repo(session)
        case, section, proposal, version = make_case(session, first)
        job = Job(repo_id=first, kind='index_baseline', payload={})
        forged = Job(repo_id=second.id, kind='revise_proposal', payload={'proposal_id': proposal.id})
        session.add_all([job, forged]); session.commit()
    ctx = Context(scoped_settings(settings, second), engine, factory, second.id)
    with pytest.raises(ValueError, match='selected repository'):
        service(ctx, accept_proposal, proposal.id, version.id)
    monkeypatch.setattr('docsync.online.operations._process_job', lambda *args: pytest.fail('Must not execute foreign job'))
    with pytest.raises(ValueError, match='another repository'):
        execute(engine, settings, job.id, repo_id=second.id)
    with pytest.raises(ValueError, match='another repository'):
        execute(engine, settings, forged.id, repo_id=second.id)
    with factory() as session:
        assert session.get(Proposal, proposal.id).accepted_version_id is None
        assert session.get(Job, job.id).status == 'PENDING'


def test_app_access_validation_no_remote_writes_or_pat(system, monkeypatch):
    settings, _, factory, _ = system
    calls = []
    class GitHub:
        def __init__(self, settings): pass
        def installation_token(self, installation, *, require_writes=False):
            assert installation == 88 and require_writes
            return 'ephemeral-app-token'
        def request(self, method, path, token):
            calls.append((method, path))
            return SimpleNamespace(json=lambda: {'full_name': 'AnotherOwner/project'})
        def branch_sha(self, name, branch, token):
            assert branch == 'main'
            return 'a'*40
        def close(self): pass
    monkeypatch.setattr('docsync.online.onboarding.GitHubClient', GitHub)
    verified = verify_access(settings, 'anotherowner/project', 'main', 88)
    assert calls == [('GET', '/repos/anotherowner/project')]
    with factory() as session:
        assert len(repositories(session)) == 1  # typing/verifying does not connect
        second = connect_repository(session, verified)
        assert second.installation_id == 88 and not second.active_index_version_id
        assert not approved_mappings(session, second.id)
        again = connect_repository(session, {**verified, 'name': verified['name'].upper(), 'branch': 'other'})
        assert again.id == second.id and again.monitored_branch == 'main'


def test_generated_callers_are_generic_and_pins_match():
    files = workflow_files('feature/docs', 'c'*40)
    assert set(files) == {'.github/workflows/docsync-analysis.yml', '.github/workflows/docsync-index.yml'}
    for value in files.values():
        assert '@' + 'c'*40 in value and 'application_ref: ' + 'c'*40 in value
        assert 'monitored_branch: "feature/docs"' in value
        assert 'b5addb64' not in value and 'branches: [master]' not in value
        assert 'contents: read' in value


def launch(settings, monkeypatch):
    values = {'DATABASE_URL': settings.database_url, 'DOCSYNC_REPOSITORY': settings.repository,
        'DOCSYNC_MONITORED_BRANCH': settings.monitored_branch, 'DOCSYNC_REVIEW_USERNAME': 'reviewer',
        'DOCSYNC_REVIEW_PASSWORD': 'test-long-password', 'DOCSYNC_HOSTED': 'false'}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'streamlit_app.py')
    app.secrets.update(values)
    app.run(timeout=20)
    app.text_input[0].set_value('reviewer')
    app.text_input[1].set_value('test-long-password')
    app.button[0].click().run(timeout=20)
    assert not app.exception and not app.error
    return app


def test_switcher_and_long_model_text_have_product_hierarchy(system, monkeypatch):
    settings, _, factory, first = system
    summary = 'UPDATE\n\n# Raw model heading docs/timeouts.md::__intro__ ' + 'Evidence chain. '*500
    with factory() as session:
        second = second_repo(session)
        case, _, proposal, version = make_case(session, first)
        case.summary = summary
        session.commit()
    app = launch(settings, monkeypatch)
    app.sidebar.radio[0].set_value('Reviews').run(timeout=20)
    card = [m.value for m in app.markdown]
    assert not any(m.startswith('### UPDATE') for m in card)
    assert not any(summary in m for m in card)
    next(b for b in app.button if b.label == 'Open review').click().run(timeout=20)
    h1 = [m.value for m in app.markdown if '<h1>' in m.value]
    assert len(h1) == 1 and summary not in h1[0] and '1 documentation section to review' in h1[0]
    assert any('ds-prose' in m.value and 'Raw model heading' in m.value for m in app.markdown)
    next(b for b in app.button if b.label == 'Edit suggestion').click().run(timeout=20)
    next(t for t in app.text_area if t.label == 'Documentation text').set_value('Unsaved first repo').run(timeout=20)
    app.sidebar.selectbox[0].set_value(second.id).run(timeout=20)
    assert not app.exception and not app.error
    assert app.session_state['repository_id'] == second.id
    assert 'case_id' not in app.session_state and 'drafts' not in app.session_state
    assert not any('Unsaved first repo' in m.value for m in app.markdown)
    for page in ['Home', 'Reviews', 'Knowledge', 'Chat', 'History', 'Settings']:
        app.sidebar.radio[0].set_value(page).run(timeout=20)
        assert not app.exception and not app.error
    assert any('0 approved mappings' in m.value for m in app.markdown)
    app.sidebar.radio[0].set_value('Chat').run(timeout=20)
    assert not app.chat_input
    app.sidebar.selectbox[0].set_value(first).run(timeout=20)
    app.sidebar.radio[0].set_value('Reviews').run(timeout=20)
    assert any(b.label == 'Open review' for b in app.button)


def test_titles_and_previews_are_bounded_without_model_calls():
    case = SimpleNamespace(summary='# Giant\n' + 'x'*10000, after_sha='b'*40)
    assert case_title(case) == 'Review code change bbbbbbb'
    assert len(case_title(case, 3)) < 60
    assert len(summary_preview(case.summary)) <= 180
    assert '\n' not in summary_preview(case.summary)


def test_connect_ui_verifies_before_persistence_and_selects_new_repo(system, monkeypatch):
    settings, _, factory, first = system
    monkeypatch.setattr('docsync.ui.onboarding.verify_access', lambda *args: {
        'name': 'AnotherOwner/project', 'branch': 'main', 'installation_id': 88, 'sha': 'e'*40})
    app = launch(settings, monkeypatch)
    next(b for b in app.button if b.label == '+ Connect repository').click().run(timeout=20)
    next(t for t in app.text_input if t.label == 'Repository').set_value('AnotherOwner/project')
    next(b for b in app.button if b.label == 'Verify GitHub App access').click().run(timeout=20)
    assert not app.exception and not app.error
    with factory() as session:
        assert len(repositories(session)) == 1
    next(b for b in app.button if b.label == 'Connect verified repository').click().run(timeout=20)
    assert not app.exception and not app.error
    with factory() as session:
        rows = repositories(session)
        assert len(rows) == 2
        new = next(r for r in rows if r.id != first)
        assert not new.active_index_version_id
    assert app.session_state['repository_id'] == new.id
    assert app.session_state['page'] == 'Settings'


@pytest.mark.parametrize('name', ['bad', 'owner/repo/extra', 'owner/..', 'owner/repo?token=secret'])
def test_invalid_repository_names_are_rejected(name):
    from docsync.online.onboarding import repository_name
    with pytest.raises(ValueError):
        repository_name(name)


def test_discovery_and_generic_baseline_use_immutable_git_text(system, tmp_path, monkeypatch):
    settings, engine, factory, _ = system
    with factory() as session:
        second = second_repo(session)
    root = tmp_path / 'source'
    root.mkdir()
    _git('init', '--initial-branch=main', cwd=root)
    _git('config', 'user.email', 'qa@example.test', cwd=root)
    _git('config', 'user.name', 'QA', cwd=root)
    (root / 'auth.py').write_text('def validate_token():\n    return True\n', encoding='utf-8')
    (root / 'README.md').write_text('## Token validation\nValidates tokens.\n', encoding='utf-8')
    _git('add', '.', cwd=root)
    _git('commit', '-m', 'Approved source', cwd=root)
    commit = _git('rev-parse', 'HEAD', cwd=root)
    @contextmanager
    def clone(*args):
        yield root, lambda *parts: _git(*parts, cwd=root), {}
    class GitHub:
        def __init__(self, settings): self.settings = settings
        def installation_token(self, installation): return 'app-token'
        def branch_sha(self, *args): return commit
        def close(self): pass
    monkeypatch.setattr('docsync.online.onboarding.GitHubClient', GitHub)
    monkeypatch.setattr('docsync.online.onboarding.cloned_repository', clone)
    inspected = discover(settings, second, code_paths=['auth.py'], doc_paths=['README.md'])
    assert inspected['sha'] == commit
    assert inspected['symbols'][0]['code_id'] == 'auth.py::validate_token'
    with factory() as session:
        confirm_mapping(session, second.id, inspected, 'auth.py::validate_token', 'README.md::token-validation', 'Documents token validation')
    # A changed worktree must never replace the explicit approved commit text.
    (root / 'README.md').write_text('## Token validation\nUnapproved working text.\n', encoding='utf-8')
    monkeypatch.setattr('docsync.web.worker.GitHubClient', GitHub)
    monkeypatch.setattr('docsync.web.worker.cloned_repository', clone)
    monkeypatch.setattr('docsync.web.worker.SentenceEmbedder', lambda *args: Embedder())
    from docsync.web.worker import _baseline_index
    job = Job(repo_id=second.id, kind='index_baseline', payload={'baseline_sha': commit})
    _baseline_index(engine, settings, job)
    _baseline_index(engine, settings, job)
    with factory() as session:
        repo = session.get(Repository, second.id)
        version, rows = retrieve(session, repo, Embedder().embed('query'))
        assert version.source_commit == commit
        assert 'Validates tokens.' in rows[0].content and 'Unapproved' not in rows[0].content
        assert session.scalar(select(func.count()).select_from(KnowledgeVersion).where(KnowledgeVersion.repo_id == repo.id)) == 1


@pytest.mark.parametrize('permissions', [{}, {'contents': 'read', 'pull_requests': 'write'},
    {'contents': 'write', 'pull_requests': 'read'}, {'contents': 'write', 'pull_requests': 'write'}])
def test_installation_verification_requires_existing_write_permissions(system, monkeypatch, permissions):
    import httpx
    from docsync.web.github import GitHubClient, GitHubError
    settings, *_ = system
    monkeypatch.setattr('docsync.web.github.jwt.encode', lambda *args, **kwargs: 'jwt')
    settings = replace(settings, github_private_key='test-key')
    transport = httpx.MockTransport(lambda request: httpx.Response(201,
        json={'token': 'test-token', 'permissions': permissions}))
    with httpx.Client(transport=transport) as http:
        client = GitHubClient(settings, http)
        if permissions == {'contents': 'write', 'pull_requests': 'write'}:
            assert client.installation_token(88, require_writes=True) == 'test-token'
        else:
            with pytest.raises(GitHubError, match='permissions'):
                client.installation_token(88, require_writes=True)
