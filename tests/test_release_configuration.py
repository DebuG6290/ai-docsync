import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import select, inspect

from docsync.doctor import checks
from docsync.sarvam import _NoRedirect, SarvamClient
from docsync.errors import ModelError
from docsync.web.models import Repository, UsageBucket
from test_online_phase2 import system
from test_public_beta_security import ISSUER, policy


def test_doctor_rejects_unconfigured_hosting_and_never_echoes_secrets(system):
    settings, _, _, _ = system
    secret = 'SECRET-that-must-never-appear'
    results = checks(replace(settings, sarvam_api_key=secret, github_private_key=secret), hosted=True)
    assert any(status == 'FAIL' for status, _ in results)
    assert secret not in str(results)


def test_doctor_accepts_valid_configuration_without_connecting(system, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    settings = replace(system[0], auth_mode='oidc', access_policy=policy(system[0].repository),
        database_url='postgresql://user:PRIVATE_PASSWORD@database.invalid/docs?sslmode=require', github_private_key=key)
    monkeypatch.setattr('socket.create_connection', lambda *a, **k: pytest.fail('Doctor must not access the network'))
    auth = {'redirect_uri': 'https://docs.example.test/oauth2callback', 'cookie_secret': 'x' * 48,
        'client_id': 'client', 'client_secret': 'PRIVATE_SECRET',
        'server_metadata_url': ISSUER + '/.well-known/openid-configuration'}
    results = checks(settings, auth=auth, hosted=True)
    assert all(status == 'PASS' for status, _ in results)
    assert 'PRIVATE_PASSWORD' not in str(results) and 'PRIVATE_SECRET' not in str(results) and key not in str(results)


def test_additive_usage_migration_preserves_repository_history(system, monkeypatch):
    from alembic import command
    from alembic.config import Config
    settings, engine, factory, repo_id = system
    monkeypatch.setenv('DATABASE_URL', settings.database_url)
    UsageBucket.__table__.drop(engine)
    command.stamp(Config('alembic.ini'), '004_conflicts')
    command.upgrade(Config('alembic.ini'), 'head')
    assert 'usage_buckets' in inspect(engine).get_table_names()
    with factory() as session:
        assert session.get(Repository, repo_id).full_name == settings.repository


def test_provider_redirect_is_not_followed():
    # urllib treats None as a rejected redirect and raises HTTPError instead.
    assert _NoRedirect().redirect_request(None, None, 302, '', {}, 'https://attacker.invalid/steal') is None


def test_oversized_provider_response_fails_before_json_parsing(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            assert limit == 2_000_001
            return b'x' * limit
    monkeypatch.setenv('SARVAM_API_KEY', 'synthetic-test-key')
    monkeypatch.setattr('docsync.sarvam._open_request', lambda *a, **k: Response())
    with pytest.raises(ModelError, match='safe size limit'):
        SarvamClient().complete('system', 'user', 'schema', {})
