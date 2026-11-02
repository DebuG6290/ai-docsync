"""Sign-in UI with fail-closed policy, expiring sessions and bounded local attempts."""
import hmac
import threading
import time
from collections import deque

import streamlit as st

from docsync.security import (AccessDenied, local_principal, oidc_principal, validate_auth_mode,
    validate_oidc_configuration, hosted_environment)
from docsync.ui.components import heading

_attempts = deque()
_attempt_lock = threading.Lock()


def local_credentials(settings, username, password, *, now=None):
    """Process-wide throttle, intentionally only supported for local development."""
    now = time.monotonic() if now is None else now
    with _attempt_lock:
        while _attempts and _attempts[0] <= now - 60:
            _attempts.popleft()
        if len(_attempts) >= 5:
            return False
        _attempts.append(now)
        good = hmac.compare_digest(username.encode(), settings.review_username.encode()) & hmac.compare_digest(password.encode(), settings.review_password.encode())
        if good:
            _attempts.clear()
        return bool(good)


def sign_out(settings):
    st.session_state.clear()
    if settings.auth_mode == "oidc":
        st.logout()
    st.rerun()


def login(settings):
    try:
        validate_auth_mode(settings)
        if settings.auth_mode == 'oidc':
            validate_oidc_configuration(dict(st.secrets.get('auth', {})), hosted=hosted_environment())
    except ValueError as exc:
        heading('Set up your DocSync workspace', 'Individual sign-in and explicit repository access protect your documentation.')
        st.error(str(exc))
        st.caption('New here? Run `docsync-demo` for the isolated example. See README.md for workspace setup.')
        st.stop()
    if settings.auth_mode == "oidc" and st.user.is_logged_in:
        try:
            principal = oidc_principal(dict(st.user), settings.access_policy)
        except AccessDenied as exc:
            st.warning(str(exc))
            st.caption('Ask the workspace administrator to grant your exact identity. This does not grant access by itself.')
            st.json({key: st.user.get(key) for key in ('iss', 'sub')})
            if st.button('Sign out'):
                sign_out(settings)
            st.stop()
        return principal
    if settings.auth_mode == "local" and st.session_state.get('authenticated'):
        principal = local_principal(settings.review_username, issued_at=st.session_state.get('authenticated_at', 0))
        if principal.allows(role='admin'):
            return principal
        st.session_state.clear()
        st.warning('Your session expired. Sign in again.')
    _, center, _ = st.columns([1, 2, 1])
    with center:
        heading('Documentation you can trust.', 'Review changes with confidence. Keep every answer grounded in approved knowledge.', 'DOCSYNC')
        with st.container(border=True):
            st.subheader('Welcome to your workspace')
            if settings.auth_mode == "oidc":
                st.caption('Sign in with your organization account. Repository access is granted by your administrator.')
                if st.button('Sign in', type='primary', use_container_width=True):
                    try:
                        st.login()
                    except Exception:
                        st.error('Sign-in is not configured correctly. Ask the administrator to check the OIDC settings.')
            else:
                st.info('Local development mode. Bind this app to 127.0.0.1; use OIDC for a shared deployment.')
                with st.form('login'):
                    username = st.text_input('Username', max_chars=100)
                    password = st.text_input('Password', type='password', max_chars=1024)
                    if st.form_submit_button('Sign in', type='primary', use_container_width=True):
                        if local_credentials(settings, username, password):
                            st.session_state.authenticated = True
                            st.session_state.authenticated_at = time.time()
                            st.rerun()
                        st.error('Sign-in failed or too many attempts. Check your credentials and wait a minute before retrying.')
        st.caption('Try the isolated sample with `docsync-demo`. No account, API key or repository access is needed.')
    st.stop()
