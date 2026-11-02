"""Non-network preflight. Outputs setting names/status, never secret values."""
import argparse
import os
from pathlib import Path

from sqlalchemy.engine import make_url

from docsync.security import validate_auth_mode, validate_oidc_configuration, hosted_environment
from docsync.web.config import get_settings


def checks(settings, *, auth=None, hosted=False):
    results = []
    try:
        validate_auth_mode(settings)
        if hosted and settings.auth_mode != 'oidc':
            raise ValueError('Hosted workspaces require OIDC sign-in')
        if settings.auth_mode == 'oidc':
            validate_oidc_configuration(auth, hosted=hosted)
        results.append(('PASS', 'Sign-in and repository access policy'))
    except ValueError as exc:
        results.append(('FAIL', str(exc)))
    try:
        url = make_url(settings.database_url)
        if hosted and (not url.drivername.startswith('postgres') or url.query.get('sslmode') not in {'require', 'verify-ca', 'verify-full'}):
            raise ValueError()
        results.append(('PASS', 'Database URL format and hosted TLS requirement'))
    except Exception:
        results.append(('FAIL', 'Hosted workspaces need PostgreSQL with sslmode=require, verify-ca or verify-full'))
    key_ok = False
    if settings.github_private_key:
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
            key_ok = isinstance(load_pem_private_key(settings.github_private_key.encode(), password=None), RSAPrivateKey)
        except Exception:
            pass
    for key, present in [('SARVAM_API_KEY', bool(settings.sarvam_api_key) and not settings.sarvam_api_key.startswith('REPLACE')),
        ('GITHUB_APP_ID', settings.github_app_id.isdecimal() and int(settings.github_app_id) > 0),
        ('GITHUB_PRIVATE_KEY', key_ok)]:
        results.append(('PASS' if present else 'FAIL', key + ' configured'))
    limits = (settings.chat_daily_limit, settings.model_action_daily_limit, settings.repository_daily_limit)
    results.append(('PASS' if all(type(v) is int and 1 <= v <= 10000 for v in limits) else 'FAIL', 'Bounded model operation allowances'))
    return results


def main():
    parser = argparse.ArgumentParser(description='Validate DocSync configuration without network access or revealing secrets')
    parser.add_argument('--secrets', type=Path, default=Path('.streamlit/secrets.toml'))
    parser.add_argument('--hosted', action='store_true')
    args = parser.parse_args()
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    try:
        values = tomllib.loads(args.secrets.read_text()) if args.secrets.exists() else {}
        for key, value in values.items():
            if isinstance(value, (str, int)):
                os.environ[key] = str(value)
        settings = get_settings()
        results = checks(settings, auth=values.get('auth'), hosted=args.hosted or hosted_environment())
    except Exception:
        results = [('FAIL', 'Configuration could not be parsed. Check TOML syntax and numeric limit settings.')]
    for status, description in results:
        print(f'{status}: {description}')
    print('This checks configuration only. It does not verify provider access, migration success, or hosted acceptance.')
    raise SystemExit(1 if any(status == 'FAIL' for status, _ in results) else 0)
