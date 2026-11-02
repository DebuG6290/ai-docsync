"""Application authorization. OIDC claims must come from Streamlit's verified st.user.

An identity-provider login is not repository permission. No email/domain matching,
wildcard grants, user-supplied JWTs, or implicit access for newly connected repos.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urlsplit


class AccessDenied(ValueError):
    pass


ROLES = {"reader": 1, "reviewer": 2, "admin": 3}
current_actor: ContextVar[str | None] = ContextVar("docsync_actor", default=None)


def _identity(issuer, subject):
    if not isinstance(issuer, str) or not isinstance(subject, str) or not subject or len(subject) > 512:
        raise ValueError("An exact issuer and subject are required for every member")
    parsed = urlsplit(issuer)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Identity issuers must be HTTPS URLs without credentials or query strings")
    return issuer, subject


def parse_policy(raw):
    """Validate operator configuration before any repository metadata is loaded."""
    try:
        if not isinstance(raw, str) or not raw or len(raw) > 65536:
            raise ValueError()
        value = json.loads(raw)
        if not isinstance(value, dict) or set(value) != {"version", "members"} or type(value["version"]) is not int or value["version"] != 1:
            raise ValueError()
        if not isinstance(value["members"], list) or not value["members"]:
            raise ValueError()
        members = {}
        for member in value["members"]:
            if not isinstance(member, dict) or set(member) - {"issuer", "subject", "admin", "repositories"}:
                raise ValueError()
            key = _identity(member.get("issuer"), member.get("subject"))
            if key in members or type(member.get("admin", False)) is not bool:
                raise ValueError()
            grants = member.get("repositories", {})
            if not isinstance(grants, dict):
                raise ValueError()
            normalized = {}
            # Lazy import avoids a dependency cycle with onboarding services.
            from docsync.online.onboarding import repository_name
            for name, role in grants.items():
                name = repository_name(name).casefold()
                if role not in {"reader", "reviewer"} or name in normalized:
                    raise ValueError()
                normalized[name] = role
            members[key] = {"admin": member.get("admin", False), "repositories": normalized}
        if not any(member["admin"] for member in members.values()):
            raise ValueError()
        return members
    except (ValueError, TypeError, KeyError, AttributeError):
        # Never echo the policy or credentials into the UI/logs.
        raise ValueError("Configure a valid version-1 DOCSYNC_ACCESS_POLICY with at least one explicit administrator") from None


@dataclass(frozen=True)
class Principal:
    actor_id: str
    grants: dict[str, str]
    administrator: bool
    expires_at: float
    label: str

    def require(self, repository=None, role="reader", *, now=None):
        now = time.time() if now is None else now
        if now >= self.expires_at:
            raise AccessDenied("Your session has expired. Sign in again.")
        actual = "admin" if self.administrator else self.grants.get((repository or "").casefold())
        if role not in ROLES or ROLES.get(actual, 0) < ROLES[role]:
            raise AccessDenied("Your account does not have permission for this repository action.")

    def allows(self, repository=None, role="reader"):
        try:
            self.require(repository, role)
            return True
        except AccessDenied:
            return False


def oidc_principal(claims, policy, *, now=None, max_age=28800):
    now = time.time() if now is None else now
    try:
        issuer, subject = _identity(claims.get("iss"), claims.get("sub"))
        issued, expires = claims["iat"], claims["exp"]
        if type(issued) not in (int, float) or type(expires) not in (int, float):
            raise ValueError()
        if not all(math.isfinite(v) for v in (issued, expires)) or issued > now + 60 or expires <= issued:
            raise ValueError()
        expiry = min(expires, issued + max_age)
        if expiry <= now:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise AccessDenied("Your identity token is missing required claims or has expired. Sign in again.") from None
    member = parse_policy(policy).get((issuer, subject))
    if member is None:
        raise AccessDenied("Your account has not been invited to this workspace.")
    actor = "oidc:" + hashlib.sha256(json.dumps([issuer, subject]).encode()).hexdigest()
    label = str(claims.get("name") or "Workspace member")[:100]
    return Principal(actor, member["repositories"], member["admin"], expiry, label)


def local_principal(username="local", *, issued_at=None, max_age=28800):
    issued_at = time.time() if issued_at is None else issued_at
    return Principal("local:" + username, {}, True, issued_at + max_age, username)


@contextmanager
def actor_scope(principal):
    token = current_actor.set(principal.actor_id)
    try:
        yield
    finally:
        current_actor.reset(token)


def hosted_environment():
    import os
    return os.getenv("DOCSYNC_HOSTED", "").lower() == "true" or bool(os.getenv("STREAMLIT_SHARING_MODE"))


def validate_auth_mode(settings):
    if settings.auth_mode not in {"local", "oidc"}:
        raise ValueError("DOCSYNC_AUTH_MODE must be oidc or local")
    if settings.auth_mode == "local":
        if hosted_environment():
            raise ValueError("Hosted workspaces require OIDC sign-in. Shared passwords are for loopback development only.")
        if len(settings.review_password) < 12:
            raise ValueError("Local development requires DOCSYNC_REVIEW_PASSWORD with at least 12 characters")
    else:
        parse_policy(settings.access_policy)


def validate_oidc_configuration(auth, *, hosted=False):
    if not isinstance(auth, dict):
        raise ValueError('Configure the [auth] section in Streamlit deployment secrets')
    for key in ('redirect_uri', 'cookie_secret', 'client_id', 'client_secret', 'server_metadata_url'):
        if not isinstance(auth.get(key), str) or not auth[key].strip():
            raise ValueError('The OIDC configuration is missing a required setting: ' + key)
    if len(auth['cookie_secret']) < 32:
        raise ValueError('Use a random OIDC cookie_secret of at least 32 characters')
    metadata = urlsplit(auth['server_metadata_url'])
    redirect = urlsplit(auth['redirect_uri'])
    if metadata.scheme != 'https' or not metadata.netloc or metadata.username or metadata.password:
        raise ValueError('OIDC discovery must use an HTTPS provider metadata URL')
    loopback = redirect.hostname in {'localhost', '127.0.0.1', '::1'}
    if (redirect.scheme != 'https' and (hosted or not loopback or redirect.scheme != 'http')) or not redirect.netloc:
        raise ValueError('Use an HTTPS OIDC redirect URI; HTTP is allowed only on local loopback')
    if redirect.username or redirect.password or redirect.query or redirect.fragment or redirect.path != '/oauth2callback':
        raise ValueError('The OIDC redirect URI must end in /oauth2callback without credentials, query or fragment')
