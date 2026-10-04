import json
import subprocess
from contextlib import contextmanager

import pytest
from sqlalchemy import select, func

from docsync.engine import analyze, aggregate_case_decision, IMPACT_SYSTEM
from docsync.errors import ModelError
from docsync.models import CodeChange, Decision
from docsync.sarvam import ModelClient, SarvamClient, OUTPUT_TOKEN_BUDGETS
from docsync.store import Store
from docsync.online.actions import register, existing_analysis_job, event_input
from docsync.online.operations import execute
from docsync.web.models import ChangeCase, Proposal, SectionAssessment, SarvamCall, AuditEvent, Job
from docsync.web.workflow import persist_analysis
from test_online_phase2 import system


class Client(ModelClient):
    def __init__(self, fail_batch=None, violation=None):
        self.requests = []
        self.fail_batch = fail_batch
        self.violation = violation

    def complete(self, system, user, schema_name, schema):
        context = json.loads(user.split('\n\n')[0])
        self.requests.append((system, context, user))
        self.last_response_diagnostics = {'finish_reason': 'stop', 'input_tokens': 100,
            'output_tokens': 200, 'total_tokens': 300}
        first = context['sections'][0]['section_id']
        if first == self.fail_batch:
            if self.violation == 'length':
                self.last_response_diagnostics['finish_reason'] = 'length'
                raise ModelError('Sarvam output was truncated because finish_reason=length',
                    diagnostics=self.last_response_diagnostics)
            if self.violation == 'transport':
                raise ModelError('Provider unavailable', category='API_ERROR', retryable=True)
        rows = [assessment(s['section_id']) for s in context['sections']]
        if first == self.fail_batch:
            if self.violation == 'missing':
                rows = []
            elif self.violation == 'duplicate':
                rows.append(rows[0])
            elif self.violation == 'unknown':
                rows[0]['section_id'] = 'docs/unknown.md::x'
        return json.dumps({'summary': 'Supported section assessment.', 'sections': rows})


def assessment(sid):
    index = int(sid.split('::s')[1])
    decision = ['UPDATE', 'NO_CHANGE', 'UNCERTAIN'][index % 3]
    return {'section_id': sid, 'decision': decision,
        'proposed_text': '## Updated\nA supported statement.\n' if decision == 'UPDATE' else None,
        'reason': 'Evidence-based reason.', 'code_evidence': ['Visible code assignment.'],
        'evidence_completeness': 'INSUFFICIENT' if decision == 'UNCERTAIN' else 'COMPLETE',
        'missing_information': ['Unavailable implementation.'] if decision == 'UNCERTAIN' else [],
        'safe_claims': ['A supported statement.'], 'unsupported_claims': ['An unsupported detail.']}


def test_impact_schema_bounds_explanations_without_clipping_proposal():
    from pydantic import ValidationError
    from docsync.models import ImpactResponse
    schema = ImpactResponse.model_json_schema()
    assert schema['properties']['summary']['maxLength'] == 600
    fields = schema['$defs']['SectionAnalysis']['properties']
    assert fields['reason']['maxLength'] == 800
    for name in ('code_evidence', 'missing_information', 'safe_claims', 'unsupported_claims'):
        assert fields[name]['maxItems'] == 8
        assert fields[name]['items']['maxLength'] == 400
    row = assessment('docs/guide.md::s0')
    row['proposed_text'] = 'Approved details preserved.\n' * 1000
    payload = {'summary': 'Bounded explanation.', 'sections': [row]}
    result = ImpactResponse.model_validate(payload)
    assert result.sections[0].proposed_text == row['proposed_text']
    assert result.sections[0].decision == Decision.UPDATE
    for name, value in (('reason', 'x' * 801), ('safe_claims', ['x'] * 9),
                        ('missing_information', ['x' * 401])):
        with pytest.raises(ValidationError):
            ImpactResponse.model_validate({**payload, 'sections': [{**row, name: value}]})
    with pytest.raises(ValidationError):
        ImpactResponse.model_validate({**payload, 'summary': 'x' * 601})


@pytest.fixture
def context(tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    root.mkdir()
    sections = [{'section_id': f'docs/guide.md::s{i}', 'path': 'docs/guide.md', 'heading': f'S{i}',
        'text': f'## S{i}\nCurrent text.\n', 'sha256': 'c' * 64, 'start_line': i*3+1, 'end_line': i*3+3}
        for i in range(5)]
    change = CodeChange(code_id='pkg/config.py::DEFAULT', path='pkg/config.py', name='DEFAULT',
        kind='assignment', old_code='DEFAULT = 8', new_code='DEFAULT = 9', diff='-8\n+9', change_kind='modified')
    monkeypatch.setattr('docsync.engine.resolve_commit', lambda repo, rev: rev)
    monkeypatch.setattr('docsync.engine.changed_python_symbols', lambda *args: [change])
    monkeypatch.setattr('docsync.engine._section_context', lambda repo, sha, sid: next(s for s in sections if s['section_id'] == sid))
    return root, sections, change


def store_for(path, sections):
    store = Store(path)
    for section in sections:
        store.add_confirmed_mapping('pkg/config.py::DEFAULT', section['section_id'], 'Confirmed mapping')
    return store


def events(store, cid, kind):
    return [json.loads(e['payload_json']) for e in store.audit(cid) if e['kind'] == kind]


def test_multiple_batches_preserve_context_coverage_and_semantics(context, tmp_path):
    root, sections, change = context
    with_batch = store_for(tmp_path / 'batched.sqlite3', sections)
    single = store_for(tmp_path / 'single.sqlite3', sections)
    client, logical = Client(), Client()
    try:
        cid, decision = analyze(root, 'a'*40, 'b'*40, with_batch, client, max_sections_per_call=2)
        single_id, single_decision = analyze(root, 'a'*40, 'b'*40, single, logical, max_sections_per_call=5)
        assert len(client.requests) == 3
        actual = events(with_batch, cid, 'section_decision')
        assert actual == events(single, single_id, 'section_decision')
        assert decision == single_decision == aggregate_case_decision([Decision(a['decision']) for a in actual])
        ids = [a['section_id'] for a in actual]
        assert len(ids) == len(set(ids)) == len(sections)
        assert set(ids) == {s['section_id'] for s in sections}
        for system, payload, _ in client.requests:
            assert system.startswith(IMPACT_SYSTEM)
            assert payload['changes'] == [change.model_dump()]
            assert payload['mappings'] == with_batch.case_snapshot(cid)['mappings']
            assert 'related_documentation_sections' not in payload
            assert all(s in sections for s in payload['sections'])
        diagnostics = events(with_batch, cid, 'sarvam_call')
        assert [d['batch_number'] for d in diagnostics] == [1, 2, 3]
        assert all(d['total_candidate_sections'] == 5 and d['batch_count'] == 3 and d['attempt_count'] == 1 for d in diagnostics)
        assert all(d['finish_reason'] == 'stop' and d['total_tokens'] == 300 for d in diagnostics)
    finally:
        with_batch.db.close(); single.db.close()


def test_one_section_calls_exclude_other_documentation(context, tmp_path):
    root, sections, change = context
    store = store_for(tmp_path / 'isolated.sqlite3', sections)
    try:
        client = Client()
        cid, _ = analyze(root, 'a'*40, 'b'*40, store, client)
        assert len(client.requests) == len(sections)
        for (_, payload, raw), target in zip(client.requests, sections):
            assert payload['sections'] == [target]
            assert 'related_documentation_sections' not in payload
            assert payload['changes'] == [change.model_dump()]
            assert payload['mappings'] == store.case_snapshot(cid)['mappings']
            assert payload['old_sha'] == 'a'*40 and payload['new_sha'] == 'b'*40
            for other in sections:
                if other != target:
                    assert other['text'] not in raw
    finally:
        store.db.close()


def test_small_case_keeps_original_prompt_and_one_call(context, tmp_path):
    root, sections, _ = context
    store = store_for(tmp_path / 'small.sqlite3', sections[:1])
    try:
        client = Client()
        cid, decision = analyze(root, 'a'*40, 'b'*40, store, client)
        assert decision == Decision.UPDATE and len(client.requests) == 1
        assert client.requests[0][0] == IMPACT_SYSTEM
        assert client.requests[0][1] == store.case_snapshot(cid)
    finally:
        store.db.close()


def test_real_git_change_is_assessed_in_bounded_calls(tmp_path):
    root = tmp_path / 'git-repo'
    root.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()
    git('init')
    git('config', 'user.name', 'DocSync test')
    git('config', 'user.email', 'docsync@example.test')
    (root / 'pkg').mkdir()
    (root / 'docs').mkdir()
    config = root / 'pkg' / 'config.py'
    config.write_text('DEFAULT = 8\n', encoding='utf-8')
    (root / 'docs' / 'guide.md').write_text('## S0\nCurrent text.\n## S1\nAnother section.\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'Before')
    before = git('rev-parse', 'HEAD')
    config.write_text('DEFAULT = 9\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-m', 'After')
    after = git('rev-parse', 'HEAD')
    store = store_for(tmp_path / 'real-git.sqlite3', [{'section_id':'docs/guide.md::s0'}, {'section_id':'docs/guide.md::s1'}])
    try:
        client = Client()
        cid, decision = analyze(root, before, after, store, client)
        assert decision == Decision.UPDATE and len(client.requests) == 2
        assert all('DEFAULT = 8' in p['changes'][0]['old_code'] and 'DEFAULT = 9' in p['changes'][0]['new_code']
            for _, p, _ in client.requests)
        assert len(events(store, cid, 'section_decision')) == 2
    finally:
        store.db.close()


@pytest.mark.parametrize('violation,attempts', [('missing', 2), ('duplicate', 2), ('unknown', 2), ('length', 1)])
def test_failed_later_batch_exposes_no_partial_review(context, tmp_path, violation, attempts):
    root, sections, _ = context
    store = store_for(tmp_path / 'failure.sqlite3', sections)
    client = Client(sections[1]['section_id'], violation)
    try:
        with pytest.raises(ModelError):
            analyze(root, 'a'*40, 'b'*40, store, client)
        cid = store.db.execute('SELECT id FROM cases').fetchone()['id']
        assert store.case(cid)['status'] == 'ERROR' and store.case(cid)['decision'] is None
        assert not store.proposals(cid) and not events(store, cid, 'section_decision')
        assert len(client.requests) == 1 + attempts
        assert events(store, cid, 'impact_batch_completed')[0]['batch_number'] == 1
        assert events(store, cid, 'impact_batch_failed')[0]['batch_number'] == 2
        diagnostics = events(store, cid, 'sarvam_call')
        assert diagnostics[-1]['attempt_count'] == attempts
        assert not diagnostics[-1]['retry_scheduled']
    finally:
        store.db.close()


def test_provider_length_is_rejected_even_with_valid_complete_json(monkeypatch):
    calls, diagnostics = [], []
    payload = {'choices': [{'finish_reason': 'length', 'message': {'content': json.dumps({'summary':'ok','sections':[]})}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 8192, 'total_tokens': 8292}}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return json.dumps(payload).encode()
    def response(request, **kwargs):
        calls.append(json.loads(request.data))
        return Response()
    monkeypatch.setenv('SARVAM_API_KEY', 'test-key')
    monkeypatch.setattr('docsync.sarvam.urllib.request.urlopen', response)
    from docsync.models import ImpactResponse
    with pytest.raises(ModelError, match='finish_reason=length'):
        SarvamClient().structured('system', 'user', ImpactResponse, 'impact_analysis', diagnostic_sink=diagnostics.append)
    assert len(calls) == 1 and calls[0]['max_tokens'] == OUTPUT_TOKEN_BUDGETS['impact'] == 8192
    assert diagnostics[0]['finish_reason'] == 'length' and diagnostics[0]['output_tokens'] == 8192
    assert diagnostics[0]['retry_scheduled'] is False


def test_online_failure_diagnostics_and_explicit_retry_are_atomic(system, context, monkeypatch):
    settings, engine, factory, repo_id = system
    root, sections, _ = context
    from docsync.web.models import CodeDocMapping
    with factory() as session:
        session.add_all([CodeDocMapping(repo_id=repo_id, code_id='pkg/config.py::DEFAULT',
            section_id=s['section_id'], reason='Confirmed') for s in sections])
        session.commit()
    data = {'before_sha': 'a'*40, 'after_sha': 'b'*40}
    job_id = register(engine, settings, 'analyze_push', data)
    class GitHub:
        def __init__(self, settings): self.settings = settings
        def close(self): pass
    @contextmanager
    def cloned(*args): yield root, None, None
    client = Client(sections[1]['section_id'], 'length')
    monkeypatch.setattr('docsync.web.worker.GitHubClient', GitHub)
    monkeypatch.setattr('docsync.web.worker.cloned_repository', cloned)
    monkeypatch.setattr('docsync.web.worker._token', lambda *args: 'test')
    monkeypatch.setattr('docsync.web.worker.SarvamClient', lambda *args: client)
    with pytest.raises(ModelError, match='truncated'):
        execute(engine, settings, job_id)
    with factory() as session:
        case = session.scalar(select(ChangeCase))
        cid = case.id
        assert case.status == 'ERROR' and case.decision is None
        assert session.scalar(select(func.count()).select_from(Proposal)) == 0
        assert session.scalar(select(func.count()).select_from(SectionAssessment)) == 0
        calls = session.scalars(select(SarvamCall).where(SarvamCall.case_id == cid)).all()
        assert len(calls) == 2 and calls[-1].metadata_json['batch_number'] == 2
        assert session.scalar(select(AuditEvent).where(AuditEvent.kind == 'impact_batch_failed')).payload['batch_number'] == 2
    assert existing_analysis_job(engine, settings, data) == job_id
    with pytest.raises(ValueError, match='explicit retry'):
        execute(engine, settings, job_id)
    client.fail_batch = None
    assert execute(engine, settings, job_id, retry=True)
    with factory() as session:
        case = session.get(ChangeCase, cid)
        assert case.status == 'NEEDS_TRIAGE' or case.status == 'READY_FOR_REVIEW'
        assert case.decision == 'UPDATE' and case.error is None
        assert session.scalar(select(func.count()).select_from(ChangeCase)) == 1
        assert session.scalar(select(func.count()).select_from(SectionAssessment)) == 5
        assert session.scalar(select(func.count()).select_from(Proposal)) == 2
        assert session.get(Job, job_id).attempts == 2
    count = len(client.requests)
    assert not execute(engine, settings, job_id, retry=True)
    assert len(client.requests) == count


def test_dispatch_requires_existing_operation_and_valid_repository(system):
    settings, engine, factory, _ = system
    payload = {'repository': {'full_name': settings.repository}, 'inputs': {'before_sha':'a'*40, 'after_sha':'b'*40}}
    kind, data = event_input(settings, 'workflow_dispatch', payload)
    with pytest.raises(ValueError, match='No existing'):
        existing_analysis_job(engine, settings, data)
    job_id = register(engine, settings, kind, data)
    with pytest.raises(ValueError, match='failed or interrupted'):
        existing_analysis_job(engine, settings, data)
    with factory() as session:
        session.get(Job, job_id).status = 'ERROR'; session.commit()
    assert existing_analysis_job(engine, settings, data) == job_id
    with pytest.raises(PermissionError):
        event_input(settings, 'workflow_dispatch', {**payload, 'repository': {'full_name':'other/repo'}})


def test_dispatch_cannot_mutate_an_active_operation(system):
    settings, engine, factory, _ = system
    data = {'before_sha':'a'*40, 'after_sha':'b'*40}
    job_id = register(engine, settings, 'analyze_push', data)
    from docsync.web.models import utcnow
    with factory() as session:
        job = session.get(Job, job_id)
        job.status = 'PROCESSING'; job.claimed_at = utcnow(); session.commit()
    with pytest.raises(ValueError, match='already running'):
        existing_analysis_job(engine, settings, data)


def test_persistence_rejects_incomplete_local_case_before_exposing_any_rows(system, context, tmp_path):
    settings, engine, factory, repo_id = system
    root, sections, _ = context
    local = store_for(tmp_path / 'incomplete.sqlite3', sections)
    cid = local.create_case({'repo_root':str(root), 'old_sha':'a'*40, 'new_sha':'b'*40,
        'changes':[], 'mappings':[], 'sections':sections})
    local.set_case_result(cid, 'UPDATE', 'Incomplete result', 'READY')
    local.event('section_decision', assessment(sections[0]['section_id']), cid)
    from test_online_phase2 import make_case
    try:
        with factory() as session:
            case, _, _, _ = make_case(session, repo_id, with_proposal=False)
            session.commit()
            with pytest.raises(ValueError, match='complete, validated'):
                persist_analysis(session, case.id, '', local, cid)
            assert session.scalar(select(func.count()).select_from(Proposal)) == 0
    finally:
        local.db.close()
