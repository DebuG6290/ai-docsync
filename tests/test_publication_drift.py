import os
import subprocess
from contextlib import contextmanager

import pytest
from sqlalchemy import select, func

from test_online_phase2 import system, make_case, _git
from docsync.errors import ConflictError
from docsync.online.operations import execute
from docsync.web.models import ChangeCase, Repository, Proposal, ProposalVersion, DocumentationRelease, Job, AuditEvent, ReviewAction
from docsync.web.workflow import modify_proposal, override_no_change, accept_proposal


@pytest.mark.parametrize('scenario', ['unchanged', 'workflow', 'doc', 'code', 'other_doc', 'other_section',
    'diverged', 'race', 'race_after_ref', 'human_edit', 'human_override', 'error_retry', 'prepared_retry', 'code_reverted'])
def test_publication_validates_real_git_drift_and_exact_approvals(system, tmp_path, monkeypatch, scenario):
    settings, engine, factory, repo_id = system
    source, bare = tmp_path / 'source', tmp_path / 'remote.git'
    source.mkdir()
    _git('init', '--bare', str(bare), cwd=tmp_path)
    _git('init', '--initial-branch=master', cwd=source)
    _git('config', 'user.name', 'DocSync test', cwd=source)
    _git('config', 'user.email', 'test@example.invalid', cwd=source)
    def write(path, text):
        target = source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    def commit(message):
        _git('add', '.', cwd=source)
        _git('commit', '-m', message, cwd=source)
        return _git('rev-parse', 'HEAD', cwd=source)
    original = '## Default timeout\nThe default timeout is five seconds.\n'
    write('docs/advanced/timeouts.md', original)
    write('httpx/_config.py', 'DEFAULT_TIMEOUT_CONFIG = 8\n')
    write('docs/unrelated.md', 'Unrelated original text.\n')
    reviewed = commit('Reviewed base')
    _git('remote', 'add', 'origin', str(bare), cwd=source)
    _git('push', 'origin', 'master', cwd=source)
    human = '## Default timeout\nExact approved human wording.\n'
    with factory() as session:
        repo = session.get(Repository, repo_id)
        repo.installation_id = 77
        override = scenario == 'human_override'
        case, assessment, proposal, version = make_case(session, repo_id,
            decision='NO_CHANGE' if override else 'UPDATE', with_proposal=not override, accepted=not override)
        case.before_sha = case.after_sha = reviewed
        case.case_data = {**case.case_data, 'old_sha':reviewed, 'new_sha':reviewed}
        session.commit()
        if scenario == 'human_edit':
            proposal.status = 'PENDING'; proposal.accepted_version_id = None; session.commit()
            version = modify_proposal(session, proposal.id, human)
            accept_proposal(session, proposal.id, version.id)
        if override:
            version = override_no_change(session, assessment.id, 'Human correction is needed.', human)
            proposal = session.get(Proposal, version.proposal_id)
            accept_proposal(session, proposal.id, version.id)
        expected = version.proposed_text
        accepted_id = version.id
        proposal_id, case_id = proposal.id, case.id
        # A later, unapproved version must never replace the accepted snapshot.
        session.add(ProposalVersion(proposal_id=proposal.id, version=version.version+1, author='sarvam',
            proposed_text='## Default timeout\nUNAPPROVED text.\n', reason='Unapproved', code_evidence=[]))
        job = session.scalar(select(Job).where(Job.kind == 'publish_docs', Job.payload['case_id'].as_string() == case_id))
        if job is None:
            job = Job(repo_id=repo_id, kind='publish_docs', payload={'case_id':case_id})
            session.add(job)
        if scenario == 'error_retry':
            job.status = 'ERROR'; job.attempts = 1
            case.error = 'Monitored branch advanced; review a fresh case'
            session.add(AuditEvent(case_id=case_id, kind='previous_failure', payload={'preserved':True}))
        session.commit()
        job_id = job.id
    tip = reviewed
    if scenario == 'doc':
        write('docs/advanced/timeouts.md', original.replace('five', 'six'))
        tip = commit('Human documentation edit')
    elif scenario in {'code', 'code_reverted'}:
        write('httpx/_config.py', 'DEFAULT_TIMEOUT_CONFIG = 10\n')
        tip = commit('Reviewed code changed')
        if scenario == 'code_reverted':
            write('httpx/_config.py', 'DEFAULT_TIMEOUT_CONFIG = 8\n')
            tip = commit('Revert code change')
    elif scenario == 'other_doc':
        write('docs/unrelated.md', 'New human unrelated text.\n')
        tip = commit('Unrelated documentation edit')
    elif scenario == 'other_section':
        write('docs/advanced/timeouts.md', original + '## Other section\nNew unrelated content.\n')
        tip = commit('Unreviewed section added in same file')
    elif scenario == 'diverged':
        _git('checkout', '--orphan', 'diverged', cwd=source)
        tip = commit('Unrelated history')
        _git('push', 'origin', 'diverged', cwd=source)
        _git('update-ref', 'refs/heads/master', tip, cwd=bare)
    elif scenario not in {'unchanged'}:
        write('.github/workflows/docsync-analysis.yml', 'name: Preserved workflow fix\n')
        tip = commit('Unrelated workflow configuration')
    if scenario != 'diverged':
        _git('push', 'origin', 'master', cwd=source)
    race_tip = tip
    if scenario in {'race', 'race_after_ref', 'prepared_retry'}:
        write('.github/workflows/extra.yml', 'name: Later unrelated workflow\n')
        race_tip = commit('Branch advanced during publication')
        _git('push', 'origin', 'master', cwd=source)

    controls = {'checks':0, 'race':scenario in {'race', 'race_after_ref', 'prepared_retry'}}
    clones, commits, refs, prs = [], [], [], []
    class Response:
        def __init__(self, data, status=200):
            self.data, self.status_code, self.is_error = data, status, status >= 400
        def json(self): return self.data
    class GitHub:
        def __init__(self, settings): self.settings, self.http = settings, self
        def installation_token(self, *args): return 'test-token'
        def branch_sha(self, *args):
            controls['checks'] += 1
            threshold = 3 if scenario == 'race_after_ref' else 2
            return race_tip if controls['race'] and controls['checks'] >= threshold else (tip if controls['race'] else race_tip)
        def get(self, url, **kwargs):
            ref = url.split('/git/ref/heads/')[1]
            result = subprocess.run(['git','rev-parse','refs/heads/'+ref], cwd=bare, text=True, capture_output=True)
            return Response({'object':{'sha':result.stdout.strip()}}, 404 if result.returncode else 200)
        def request(self, method, api, token, **kwargs):
            clone = clones[-1]
            if method == 'GET':
                sha = api.split('/git/commits/')[1]
                return Response({'tree':{'sha':_git('rev-parse',sha+'^{tree}',cwd=clone)}})
            payload = kwargs['json']
            if api.endswith('/git/trees'):
                assert {r['path'] for r in payload['tree']} == {'docs/advanced/timeouts.md'}
                _git('add','docs/advanced/timeouts.md',cwd=clone)
                return Response({'sha':_git('write-tree',cwd=clone)})
            if api.endswith('/git/commits'):
                commits.append(payload)
                sha = _git('commit-tree',payload['tree'],'-p',payload['parents'][0],'-m',payload['message'],cwd=clone)
                return Response({'sha':sha})
            if api.endswith('/git/refs'):
                refs.append(payload)
                _git('push','origin',payload['sha']+':'+payload['ref'],cwd=clone)
                return Response({})
            raise AssertionError(api)
        def create_pull_request(self, *args):
            prs.append(args)
            return 42, 'https://example/pr/42'
        def close(self): pass
    @contextmanager
    def cloned(*args):
        clone = tmp_path / f'clone-{len(clones)}'
        clones.append(clone)
        _git('clone',str(bare),str(clone),cwd=tmp_path)
        _git('config','user.name','DocSync test',cwd=clone)
        _git('config','user.email','test@example.invalid',cwd=clone)
        def git(*args):
            try:
                return _git(*args, cwd=clone)
            except subprocess.CalledProcessError as exc:
                from docsync.web.github import GitHubError
                raise GitHubError('Git command failed') from exc
        yield clone, git, os.environ.copy()
    monkeypatch.setattr('docsync.online.publish.GitHubClient', GitHub)
    monkeypatch.setattr('docsync.online.publish.cloned_repository', cloned)
    monkeypatch.setattr('docsync.sarvam.SarvamClient.complete', lambda *args:pytest.fail('Publication must not call Sarvam'))
    blocked = {'doc':'DOCUMENTATION_DRIFT', 'code':'CODE_DRIFT', 'code_reverted':'CODE_DRIFT',
        'diverged':'DIVERGED', 'race':'PUBLICATION_RACE', 'race_after_ref':'PUBLICATION_RACE', 'prepared_retry':'PUBLICATION_RACE'}
    if scenario in blocked:
        with pytest.raises(ConflictError):
            execute(engine, settings, job_id)
        assert not prs
        with factory() as session:
            blocked_event = session.scalars(select(AuditEvent).where(AuditEvent.kind == 'publication_drift_blocked')).first()
            assert blocked_event.payload['validation_result'] == blocked[scenario]
            assert session.get(Job, job_id).status == 'ERROR'
            assert session.get(Proposal, proposal_id).accepted_version_id == accepted_id
        if scenario != 'prepared_retry':
            return
        controls['race'] = False
        controls['checks'] = 0
        with factory() as session:
            prepared_id = session.scalar(select(DocumentationRelease.id))
        assert execute(engine, settings, job_id, retry=True)
        with factory() as session:
            assert session.scalar(select(DocumentationRelease.id)) == prepared_id
    else:
        if scenario == 'error_retry':
            with pytest.raises(ValueError, match='explicit retry'):
                execute(engine, settings, job_id)
        assert execute(engine, settings, job_id, retry=scenario == 'error_retry')
    with factory() as session:
        release = session.scalar(select(DocumentationRelease).where(DocumentationRelease.case_id == case_id))
        assert session.scalar(select(func.count()).select_from(DocumentationRelease)) == 1
        assert session.scalar(select(func.count()).select_from(Job).where(Job.kind == 'publish_docs')) == 1
        assert session.get(Proposal, proposal_id).accepted_version_id == accepted_id
        assert session.get(ChangeCase, case_id).error is None
        if scenario == 'error_retry':
            assert session.get(Job, job_id).attempts == 2
            assert session.scalar(select(AuditEvent).where(AuditEvent.kind == 'previous_failure'))
        assert session.scalar(select(ReviewAction).where(ReviewAction.action == 'DOCUMENTATION_PR_CREATED')).version_id == accepted_id
        commit_sha = release.commit_sha
    assert len(prs) == 1
    parent = race_tip if scenario == 'prepared_retry' else tip
    assert commits[-1]['parents'] == [parent]
    assert _git('rev-parse',commit_sha+'^',cwd=bare) == parent
    assert _git('diff','--name-only',parent,commit_sha,cwd=bare) == 'docs/advanced/timeouts.md'
    from docsync.repository.markdown_sections import parse_sections
    published_text = _git('show',commit_sha+':docs/advanced/timeouts.md',cwd=bare)
    assert parse_sections('docs/advanced/timeouts.md', published_text)[0].text.strip() == expected.strip()
    if scenario in {'workflow','human_edit','human_override','error_retry','prepared_retry'}:
        assert 'Preserved workflow fix' in _git('show',commit_sha+':.github/workflows/docsync-analysis.yml',cwd=bare)
    if scenario == 'other_section':
        assert 'New unrelated content.' in _git('show',commit_sha+':docs/advanced/timeouts.md',cwd=bare)
    count = len(prs)
    assert not execute(engine, settings, job_id, retry=True)
    assert len(prs) == count
