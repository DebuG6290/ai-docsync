"""Adversarial identity, repository and usage boundaries for the supported UI."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func
from streamlit.testing.v1 import AppTest

from docsync.security import (AccessDenied, Principal, oidc_principal, parse_policy, local_principal,
    validate_auth_mode, validate_oidc_configuration)
from docsync.ui.components import Context
from docsync.ui.reviews import service
from docsync.ui.state import load
from docsync.ui.workspace import repositories, scoped_settings
from docsync.usage import reserve_usage
from docsync.web.models import Repository, Proposal, AuditEvent, UsageBucket, Job
from docsync.web.workflow import accept_proposal, modify_proposal
from test_online_phase2 import system, make_case

ISSUER = 'https://identity.example.test'


def policy(repo, role='reviewer'):
    return json.dumps({'version': 1, 'members': [
        {'issuer': ISSUER, 'subject': 'operator', 'admin': True},
        {'issuer': ISSUER, 'subject': 'member', 'repositories': {repo: role}},
    ]})


def claims(**extra):
    now = time.time()
    return {'iss': ISSUER, 'sub': 'member', 'iat': now - 10, 'exp': now + 3600, **extra}


@pytest.mark.parametrize('change', [
    {'sub': 'uninvited'}, {'iss': 'https://other.example.test'}, {'exp': 1},
    {'exp': float('inf')}, {'iat': time.time() + 600}, {'iat': None}, {'exp': True},
    {'sub': None}, {'iss': 'http://identity.example.test'},
])
def test_uninvited_wrong_issuer_and_invalid_expiry_denied(change):
    with pytest.raises(AccessDenied):
        oidc_principal(claims(**change), policy('owner/repo'))


def test_verified_email_or_same_subject_does_not_bypass_exact_identity():
    with pytest.raises(AccessDenied):
        oidc_principal(claims(sub='attacker', email='operator@example.test', email_verified=True), policy('owner/repo'))
    p = oidc_principal(claims(), policy('owner/repo'))
    p.require('OWNER/REPO', 'reviewer')
    with pytest.raises(AccessDenied):
        p.require('owner/other')
    with pytest.raises(AccessDenied):
        p.require(role='admin')
    with pytest.raises(AccessDenied):
        p.require('owner/repo', now=time.time() + 3601)


def test_cookie_cannot_extend_token_age_and_revocation_is_rechecked():
    with pytest.raises(AccessDenied):
        oidc_principal(claims(iat=time.time() - 28801, exp=time.time() + 3600), policy('owner/repo'))
    changed = json.loads(policy('owner/repo'))
    changed['members'].pop()
    with pytest.raises(AccessDenied):
        oidc_principal(claims(), json.dumps(changed))


@pytest.mark.parametrize('value', [None, '', '{}', '{bad', '[]',
    '{"version":1,"members":[]}',
    json.dumps({'version': 1, 'members': [{'issuer': ISSUER, 'subject': 'operator', 'admin': 'true'}]}),
    json.dumps({'version': 1, 'members': [{'issuer': ISSUER, 'subject': 'operator', 'admin': True, 'repositories': {'*': 'reviewer'}}]}),
])
def test_policy_fails_closed_without_exposing_input(value):
    with pytest.raises(ValueError, match='valid version-1'):
        parse_policy(value)


def test_missing_identity_and_forged_repository_context_cannot_read(system):
    settings, engine, factory, repo_id = system
    with pytest.raises(AccessDenied):
        load(Context(settings, engine, factory, repo_id))
    p = oidc_principal(claims(), policy(settings.repository))
    with factory() as session:
        other = Repository(full_name='private/other', monitored_branch='main')
        session.add(other)
        session.commit()
        assert [r.id for r in repositories(session, p)] == [repo_id]
    # The attacker pairs an allowed repository name with another repository's ID.
    with pytest.raises(AccessDenied, match='identity is inconsistent'):
        load(Context(settings, engine, factory, other.id, p))
    with pytest.raises(AccessDenied):
        load(Context(scoped_settings(settings, other), engine, factory, other.id, p))


def test_reader_cannot_mutate_or_execute_and_review_actor_is_recorded(system, monkeypatch):
    settings, engine, factory, repo_id = system
    with factory() as session:
        case, section, proposal, version = make_case(session, repo_id)
        session.commit()
    reader = oidc_principal(claims(), policy(settings.repository, 'reader'))
    ctx = Context(settings, engine, factory, repo_id, reader)
    with pytest.raises(AccessDenied):
        service(ctx, accept_proposal, proposal.id, version.id)
    with pytest.raises(AccessDenied):
        ctx.run(lambda: pytest.fail('Must not execute'))
    with factory() as session:
        assert session.get(Proposal, proposal.id).status == 'PENDING'
        assert session.scalar(select(func.count()).select_from(Job)) == 0
    reviewer = oidc_principal(claims(), policy(settings.repository))
    service(Context(settings, engine, factory, repo_id, reviewer), accept_proposal, proposal.id, version.id)
    with factory() as session:
        event = session.scalar(select(AuditEvent).where(AuditEvent.kind == 'review_accept'))
        assert event.payload['actor_id'] == reviewer.actor_id
        assert 'member' not in reviewer.actor_id


def test_atomic_allowances_hold_under_parallel_requests(system):
    settings, engine, factory, repo_id = system
    settings = replace(settings, chat_daily_limit=3)
    def reserve(_):
        try:
            reserve_usage(engine, 'same-user', repo_id, scope='chat', settings=settings, now=1700000000)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(12))) == 3
    with factory() as session:
        assert sorted(session.scalars(select(UsageBucket.count)).all()) == [3, 3, 3]
    # A new session cannot reset the database counter; a new day can.
    assert reserve(0) is False
    reserve_usage(engine, 'same-user', repo_id, scope='chat', settings=settings, now=1700086400)


def test_repository_allowance_shared_across_users_and_denied_calls_rollback(system):
    settings, engine, factory, repo_id = system
    settings = replace(settings, repository_daily_limit=2)
    for actor in ['alice', 'bob']:
        reserve_usage(engine, actor, repo_id, scope='chat', settings=settings, now=1700000000)
    with pytest.raises(ValueError, match='allowance'):
        reserve_usage(engine, 'charlie', repo_id, scope='model', settings=settings, now=1700000000)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(UsageBucket)) == 5


def test_model_allowance_denied_before_callback(system):
    settings, engine, _, repo_id = system
    settings = replace(settings, chat_daily_limit=1)
    ctx = Context(settings, engine, system[2], repo_id, oidc_principal(claims(), policy(settings.repository, 'reader')))
    assert ctx.run(lambda: 'first', role='reader', model=True) == 'first'
    with pytest.raises(ValueError, match='allowance'):
        ctx.run(lambda: pytest.fail('No model call allowed'), role='reader', model=True)


def test_shared_password_disallowed_when_hosted(system, monkeypatch):
    monkeypatch.setenv('DOCSYNC_HOSTED', 'true')
    with pytest.raises(ValueError, match='OIDC'):
        validate_auth_mode(system[0])


def test_oidc_configuration_requires_secure_cookie_and_redirect():
    auth = {'redirect_uri': 'https://docs.example.test/oauth2callback', 'cookie_secret': 'x' * 48,
        'client_id': 'client', 'client_secret': 'secret', 'server_metadata_url': ISSUER + '/.well-known/openid-configuration'}
    validate_oidc_configuration(auth, hosted=True)
    for updates in [{'redirect_uri': 'http://docs.example.test/oauth2callback'}, {'cookie_secret': 'short'},
                    {'redirect_uri': 'https://evil:secret@docs.example.test/oauth2callback'},
                    {'server_metadata_url': 'http://identity.example.test/metadata'}]:
        with pytest.raises(ValueError):
            validate_oidc_configuration({**auth, **updates}, hosted=True)


def test_input_bounds_rejected_before_any_model_call_or_version(system):
    from docsync.web.chat import answer_question
    settings, _, factory, repo_id = system
    with factory() as session:
        _, _, proposal, _ = make_case(session, repo_id)
        with pytest.raises(ValueError, match='100000'):
            modify_proposal(session, proposal.id, 'x' * 100001)
        with pytest.raises(ValueError, match='4000'):
            answer_question(session, settings, session.get(Repository, repo_id), 'x' * 4001, None)


def launch_oidc(settings, monkeypatch, *, role='reader', logged_in=True):
    import streamlit as st
    class User(dict):
        is_logged_in = logged_in
    monkeypatch.setattr(st, 'user', User(claims()))
    values = {'DATABASE_URL': settings.database_url, 'DOCSYNC_REPOSITORY': settings.repository,
        'DOCSYNC_AUTH_MODE': 'oidc', 'DOCSYNC_ACCESS_POLICY': policy(settings.repository, role),
        'DOCSYNC_HOSTED': 'false'}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'streamlit_app.py')
    app.secrets.update({**values, 'auth': {'redirect_uri': 'http://localhost:8501/oauth2callback',
        'cookie_secret': 'x' * 48, 'client_id': 'test', 'client_secret': 'test',
        'server_metadata_url': ISSUER + '/.well-known/openid-configuration'}})
    return app


def test_reader_ui_hides_foreign_repo_setup_and_approval(system, monkeypatch):
    settings, _, factory, repo_id = system
    with factory() as session:
        make_case(session, repo_id)
        session.add(Repository(full_name='private/other', monitored_branch='main'))
        session.commit()
    app = launch_oidc(settings, monkeypatch)
    app.run(timeout=20)
    assert not app.exception and not app.error
    assert len(app.sidebar.selectbox[0].options) == 1
    assert 'Settings' not in app.sidebar.radio[0].options
    assert not any(b.label == '+ Connect repository' for b in app.button)
    app.sidebar.radio[0].set_value('Reviews').run(timeout=20)
    next(b for b in app.button if b.label == 'Open review').click().run(timeout=20)
    assert not app.exception and not app.error
    assert not any(b.label in {'Approve update', 'Edit suggestion', 'Create documentation PR'} for b in app.button)


def test_forged_legacy_session_boolean_does_not_bypass_oidc(system, monkeypatch):
    app = launch_oidc(system[0], monkeypatch, logged_in=False)
    app.session_state['authenticated'] = True
    app.session_state['authenticated_at'] = time.time()
    app.run(timeout=20)
    assert not app.exception
    assert not len(app.sidebar.radio)
    assert any(b.label == 'Sign in' for b in app.button)


def test_legacy_surface_cannot_bypass_oidc(system):
    from fastapi.testclient import TestClient
    from docsync.web.app import create_app
    settings, engine, _, _ = system
    with TestClient(create_app(replace(settings, auth_mode='oidc'), engine)) as client:
        assert client.get('/', auth=(settings.review_username, settings.review_password)).status_code == 503
        assert client.post('/webhooks/github').status_code == 503


def test_remote_git_input_and_errors_do_not_execute_or_leak_secrets(monkeypatch):
    from docsync.web.github import cloned_repository, GitHubError
    monkeypatch.setattr('subprocess.run', lambda *a, **k: SimpleNamespace(returncode=1, stderr='SECRET_TOKEN', stdout=''))
    for repository, before in [('https://evil.test/repo', 'a' * 40), ('owner/repo', '--upload-pack=evil')]:
        with pytest.raises(ValueError):
            with cloned_repository(repository, 'SECRET_TOKEN', before, 'b' * 40):
                pytest.fail('Invalid remote inputs')
    with pytest.raises(GitHubError) as exc:
        with cloned_repository('owner/repo', 'SECRET_TOKEN', 'a' * 40, 'b' * 40):
            pass
    assert 'SECRET' not in str(exc.value)
