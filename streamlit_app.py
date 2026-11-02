"""DocSync Community Cloud entry point: presentation over existing domain services."""
import os
import tempfile
from datetime import timedelta
import streamlit as st
from sqlalchemy import select

from docsync.web.config import get_settings
from docsync.web.database import make_engine, session_factory
from docsync.web.models import Repository, utcnow
from docsync.ui.components import Context, styles, knowledge_summary, heading
from docsync.ui.state import load
from docsync.ui.workspace import repositories, select_repository, switch_repository, scoped_settings
from docsync.ui import onboarding
from docsync.web.repository import ensure_repository
from docsync.ui import home, reviews, knowledge, chat, history, settings as settings_page
from docsync.online.status import reconcile_release
from docsync.ui.auth import login, sign_out
from docsync.security import hosted_environment

st.set_page_config(page_title='DocSync · Approved knowledge', page_icon='D', layout='wide')
try:
    secret_values = dict(st.secrets)
except FileNotFoundError:
    secret_values = {}
for name, value in secret_values.items():
    if isinstance(value, (str, int)):
        os.environ[name] = str(value)
os.environ.setdefault('DOCSYNC_EMBEDDING_CACHE', tempfile.gettempdir() + '/docsync-embeddings')
try:
    settings = get_settings()
except (ValueError, TypeError):
    st.error('Workspace configuration is invalid. Check numeric IDs and usage limits in deployment settings.')
    st.stop()
styles()


@st.cache_resource
def database(url):
    # Additive schema upgrades run once per process/database, never on fragment polls.
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    command.upgrade(Config(str(Path(__file__).resolve().parent / 'alembic.ini')), 'head')
    return make_engine(url)


principal = login(settings)
connected_repository_id = st.session_state.pop('connected_repository_id', None)
if connected_repository_id:
    switch_repository(st.session_state, connected_repository_id)
    st.session_state.page = 'Settings'
    st.session_state.notice = 'Repository connected. Confirm mappings and initialize an approved baseline next.'
if (os.getenv('STREAMLIT_SHARING_MODE') or os.getenv('DOCSYNC_HOSTED') == 'true') and not settings.database_url.startswith(('postgres://', 'postgresql')):
    st.error('Hosted deployment requires PostgreSQL. Update the deployment configuration.'); st.stop()
if hosted_environment():
    from sqlalchemy.engine import make_url
    if make_url(settings.database_url).query.get('sslmode') not in {'require', 'verify-ca', 'verify-full'}:
        st.error('Hosted database connections require TLS. Add sslmode=require or a verified TLS mode.'); st.stop()
try:
    engine = database(settings.database_url)
    factory = session_factory(engine)
    with factory() as session:
        rows = repositories(session, principal)
        if principal.administrator and settings.repository and not any(r.full_name.casefold() == settings.repository.casefold() for r in rows):
            ensure_repository(session, settings)
            session.commit()
            rows = repositories(session, principal)
    repo = select_repository(rows, st.session_state, settings.repository)
except Exception:
    st.error('The workspace could not be loaded. Check the database connection and apply the latest schema migration.'); st.stop()

with st.sidebar:
    st.markdown('<div class="ds-brand"><span class="ds-brand-mark">D</span><span class="ds-brand-name">DocSync</span></div>', unsafe_allow_html=True)
    st.caption('From code changes to trusted answers.')
    if rows:
        by_id = {r.id: r for r in rows}
        def repository_changed():
            switch_repository(st.session_state, st.session_state.repository_id)
        st.selectbox('Repository', list(by_id), format_func=lambda rid: by_id[rid].full_name,
            key='repository_id', on_change=repository_changed)
        repo = by_id[st.session_state.repository_id]
    st.caption('Signed in as ' + principal.label)
    if principal.administrator and st.button('+ Connect repository', use_container_width=True):
        st.session_state.connecting = True
        st.rerun()
    st.divider()
    def workspace_changed():
        st.session_state.pop('connecting', None)
    allowed_pages = ['Home', 'Reviews', 'Knowledge', 'Chat', 'History']
    if repo and principal.allows(repo.full_name, 'reviewer'):
        allowed_pages.append('Settings')
    if st.session_state.get('page') not in allowed_pages:
        st.session_state.page = 'Home'
    page = st.radio('Workspace', allowed_pages, key='page',
        label_visibility='collapsed', on_change=workspace_changed)
    st.divider()
    st.caption('MONITORED REPOSITORY')
    if repo:
        st.write(repo.full_name)
        st.caption(repo.monitored_branch + ' · Human-governed updates')
    if st.button('Sign out', use_container_width=True):
        sign_out(settings)

if st.session_state.get('connecting') or repo is None:
    if principal.administrator:
        onboarding.connect(settings, factory, principal)
    else:
        st.info('No repositories have been assigned to your account. Ask the workspace administrator for access.')
    st.stop()
ctx = Context(scoped_settings(settings, repo), engine, factory, repo.id, principal)
if not ctx.can('reviewer'):
    st.caption('Reader access · You can inspect approved knowledge and ask questions. Review and publication require a reviewer.')
view = load(ctx)

def needs_refresh(snapshot):
    return bool(any(r.status in {'PENDING_MERGE', 'MERGED', 'VERIFYING', 'INDEXING'} for r in snapshot['pending'])
        or any(i['status'].tone == 'progress' for i in snapshot['cases']))


pending = needs_refresh(view)


def refresh_signature(snapshot):
    return (snapshot['repo'].active_index_version_id,
        tuple((r.id, r.status, r.merged_sha) for r in snapshot['releases']),
        tuple((i['case'].id, i['status'].label, i['approved'], i['required']) for i in snapshot['cases']))


@st.fragment(run_every='15s' if pending else None)
def live_knowledge():
    from docsync.security import AccessDenied
    try:
        latest = load(ctx)
    except AccessDenied:
        st.rerun()
    for release in latest['pending']:
        checked = release.status_checked_at
        if release.pr_number and not release.merged_sha and (not checked or checked.replace(tzinfo=utcnow().tzinfo) < utcnow() - timedelta(seconds=60)):
            # Bound reads per active session even if GitHub is temporarily unavailable.
            key = 'checked-' + release.id
            last_attempt = st.session_state.get(key)
            if last_attempt is None or last_attempt < utcnow() - timedelta(seconds=60):
                st.session_state[key] = utcnow()
                try:
                    ctx.run(lambda: reconcile_release(factory, release.id, repo_id=ctx.repo_id), role='reader')
                    latest = load(ctx)
                except Exception:
                    st.caption('GitHub status could not be checked. The last confirmed state is shown.')
    knowledge_summary(latest)
    if refresh_signature(latest) != refresh_signature(view) or needs_refresh(latest) != pending:
        st.rerun()


live_knowledge()
notice = st.session_state.pop('notice', None)
if notice:
    st.success(notice)
if st.button('Refresh workspace', type='tertiary'):
    st.rerun()
pages = {'Home': home.render, 'Reviews': reviews.render, 'Knowledge': knowledge.render,
    'Chat': chat.render, 'History': history.render, 'Settings': settings_page.render}
try:
    pages[page](ctx, view)
except Exception:
    st.error('This view could not be loaded. Saved decisions are preserved. Refresh the workspace or check the operation details.')
