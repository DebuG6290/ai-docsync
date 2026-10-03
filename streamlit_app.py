"""DocSync Community Cloud entry point: presentation over existing domain services."""
import os
import tempfile
import hmac
from datetime import timedelta
import streamlit as st
from sqlalchemy import select

from docsync.web.config import get_settings
from docsync.web.database import make_engine, session_factory
from docsync.web.models import Repository, utcnow
from docsync.ui.components import Context, styles, knowledge_summary, heading
from docsync.ui.state import load
from docsync.ui import home, reviews, knowledge, chat, history, settings as settings_page
from docsync.online.status import reconcile_release

st.set_page_config(page_title='DocSync · Approved knowledge', page_icon='D', layout='wide')
try:
    secret_values = dict(st.secrets)
except FileNotFoundError:
    secret_values = {}
for name, value in secret_values.items():
    if isinstance(value, (str, int)):
        os.environ[name] = str(value)
os.environ.setdefault('DOCSYNC_EMBEDDING_CACHE', tempfile.gettempdir() + '/docsync-embeddings')
settings = get_settings()
styles()


def login():
    if not st.session_state.get('authenticated'):
        left, center, right = st.columns([1, 2, 1])
        with center:
            heading('Documentation you can trust.', 'Review changes with confidence. Keep every answer grounded in approved knowledge.', 'DOCSYNC')
            with st.container(border=True):
                st.subheader('Welcome back')
                st.caption('Sign in to your documentation workspace.')
                if not settings.review_password:
                    st.info('Workspace setup is incomplete. Configure the review credentials in deployment secrets.')
                    st.stop()
                with st.form('login'):
                    username = st.text_input('Username')
                    password = st.text_input('Password', type='password')
                    if st.form_submit_button('Sign in', type='primary', use_container_width=True):
                        if hmac.compare_digest(username, settings.review_username) and hmac.compare_digest(password, settings.review_password):
                            st.session_state.authenticated = True
                            st.rerun()
                        st.error('The username or password is incorrect. Please try again.')
            st.caption('Human-reviewed documentation. Approved-only answers.')
        st.stop()


@st.cache_resource
def database(url):
    # Additive schema upgrades run once per process/database, never on fragment polls.
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    command.upgrade(Config(str(Path(__file__).resolve().parent / 'alembic.ini')), 'head')
    return make_engine(url)


login()
if (os.getenv('STREAMLIT_SHARING_MODE') or os.getenv('DOCSYNC_HOSTED') == 'true') and not settings.database_url.startswith(('postgres://', 'postgresql')):
    st.error('Hosted deployment requires PostgreSQL. Update the deployment configuration.'); st.stop()
try:
    engine = database(settings.database_url)
    factory = session_factory(engine)
    with factory() as session:
        repo = session.scalar(select(Repository).where(Repository.full_name == settings.repository))
    if repo is None:
        st.info('Initialize the workspace database and approved mappings before opening DocSync. See DEPLOYMENT.md.'); st.stop()
    ctx = Context(settings, engine, factory, repo.id)
    view = load(ctx)
except Exception:
    st.error('The workspace could not be loaded. Check the database connection and apply the latest schema migration.'); st.stop()

with st.sidebar:
    st.markdown('<div class="ds-brand"><span class="ds-brand-mark">D</span><span class="ds-brand-name">DocSync</span></div>', unsafe_allow_html=True)
    st.caption('From code changes to trusted answers.')
    st.divider()
    page = st.radio('Workspace', ['Home', 'Reviews', 'Knowledge', 'Chat', 'History', 'Settings'], key='page', label_visibility='collapsed')
    st.divider()
    st.caption('MONITORED REPOSITORY')
    st.write(settings.repository)
    st.caption(settings.monitored_branch + ' · Human-governed updates')
    if st.button('Sign out', use_container_width=True):
        st.session_state.clear(); st.rerun()

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
    latest = load(ctx)
    for release in latest['pending']:
        checked = release.status_checked_at
        if release.pr_number and not release.merged_sha and (not checked or checked.replace(tzinfo=utcnow().tzinfo) < utcnow() - timedelta(seconds=60)):
            # Bound reads per active session even if GitHub is temporarily unavailable.
            key = 'checked-' + release.id
            last_attempt = st.session_state.get(key)
            if last_attempt is None or last_attempt < utcnow() - timedelta(seconds=60):
                st.session_state[key] = utcnow()
                try:
                    reconcile_release(factory, release.id)
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
