"""Community Cloud entry point. Durable state belongs in PostgreSQL."""
import difflib
import hmac
import os
import tempfile

import streamlit as st
from sqlalchemy import select

from docsync.online.operations import execute
from docsync.web.chat import answer_question, chat_history
from docsync.web.config import get_settings
from docsync.web.database import make_engine, session_factory
from docsync.web.embeddings import SentenceEmbedder
from docsync.web.models import ChangeCase, SectionAssessment, Proposal, ProposalVersion, AuditEvent, Job, Repository, KnowledgeVersion
from docsync.web.workflow import accept_proposal, modify_proposal, reject_proposal, triage_section, approved_mappings


st.set_page_config(page_title='DocSync', layout='wide')
# Secrets are injected before constructing clients. No secret values are displayed.
try:
    secret_values = dict(st.secrets)
except FileNotFoundError:
    secret_values = {}
for name, value in secret_values.items():
    if isinstance(value, (str, int)):
        os.environ[name] = str(value)
os.environ.setdefault('DOCSYNC_EMBEDDING_CACHE', tempfile.gettempdir() + '/docsync-embeddings')
settings = get_settings()


def login():
    # Always require application login; provider viewer restrictions add another gate.
    if not settings.review_password:
        st.error('Set DOCSYNC_REVIEW_PASSWORD in application secrets.')
        st.stop()
    if not st.session_state.get('authenticated'):
        with st.form('login'):
            username = st.text_input('Username')
            password = st.text_input('Password', type='password')
            submitted = st.form_submit_button('Sign in')
        if submitted:
            if hmac.compare_digest(username, settings.review_username) and hmac.compare_digest(password, settings.review_password):
                st.session_state.authenticated = True
                st.rerun()
            st.error('Invalid credentials')
        st.stop()


@st.cache_resource
def database(url):
    return make_engine(url)


@st.cache_resource
def embedder(model, cache):
    return SentenceEmbedder(model, cache)


def run_operation(job_id, retry=False):
    with st.spinner('Processing and saving the result…'):
        execute(engine, settings, job_id, retry=retry)
    st.rerun()


def review(case_id):
    with factory() as session:
        case = session.get(ChangeCase, case_id)
        st.caption(f'{case.before_sha} → {case.after_sha} · {case.status}')
        st.write(case.summary or '')
        if case.error:
            st.error(case.error)
        if case.documentation_pr_url:
            st.link_button('Open documentation PR', case.documentation_pr_url)
        with st.expander('Code evidence: old/new context and Git diff'):
            st.json(case.case_data.get('changes', []))
        sections = session.scalars(select(SectionAssessment).where(SectionAssessment.case_id == case.id)).all()
        for section in sections:
            st.subheader(section.heading)
            st.caption(f'{section.path} · {section.section_id} · {section.decision}')
            st.write(section.rationale)
            st.json({'evidence_completeness': section.evidence_completeness, 'code_evidence': section.code_evidence,
                'missing_information': section.missing_information, 'safe_claims': section.safe_claims,
                'unsupported_claims': section.unsupported_claims})
            st.markdown('**Current documentation**')
            st.code(section.current_text, language='markdown')
            from docsync.web.models import IndexedSection
            repo = session.get(Repository, case.repo_id)
            source = session.scalar(select(IndexedSection).where(IndexedSection.version_id == repo.active_index_version_id,
                IndexedSection.section_id == section.section_id).limit(1))
            provenance = case.case_data.get('context_provenance', {}).get(section.section_id)
            if provenance:
                st.caption(f'Approved documentation commit used for analysis: {provenance}')
            elif source:
                st.caption(f'Active approved documentation commit: {source.source_commit}')
            if section.decision == 'UNCERTAIN' and not section.human_resolution:
                with st.form('triage-' + section.id):
                    resolution = st.selectbox('Human resolution', ['NO_CHANGE', 'HUMAN_UPDATE'])
                    reason = st.text_area('Triage reason')
                    text = st.text_area('Human documentation text')
                    if st.form_submit_button('Save resolution'):
                        triage_section(session, section.id, resolution, reason, text)
                        st.rerun()
            proposal = session.scalar(select(Proposal).where(Proposal.case_id == case.id, Proposal.section_id == section.section_id))
            if not proposal:
                continue
            versions = session.scalars(select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id)
                .order_by(ProposalVersion.version)).all()
            latest = versions[-1]
            st.caption(f'V{latest.version} · {latest.author} · {proposal.status} · human_modified={latest.human_modified}')
            st.code(''.join(difflib.unified_diff(section.current_text.splitlines(True), latest.proposed_text.splitlines(True),
                fromfile='CURRENT', tofile='PROPOSED')), language='diff')
            with st.expander('Append-only proposal history'):
                from docsync.web.models import ReviewAction
                for action in session.scalars(select(ReviewAction).where(ReviewAction.proposal_id == proposal.id)
                    .order_by(ReviewAction.created_at)).all():
                    st.write(f'{action.action} · {action.version_id} · {action.reason or ""}')
                for version in versions:
                    st.write(f'V{version.version} · {version.author}: {version.reason}')
                    st.code(version.proposed_text, language='markdown')
            if proposal.status not in {'ACCEPTED', 'APPLIED', 'REVISING'}:
                if st.button('Accept exact displayed version', key='accept-' + latest.id):
                    accept_proposal(session, proposal.id, latest.id)
                    st.rerun()
                with st.form('modify-' + latest.id):
                    text = st.text_area('Edit documentation', latest.proposed_text)
                    if st.form_submit_button('Save human version'):
                        modify_proposal(session, proposal.id, text, latest.id)
                        st.rerun()
                with st.form('reject-' + latest.id):
                    reason = st.text_area('Rejection reason')
                    if st.form_submit_button('Reject and request targeted revision'):
                        reject_proposal(session, proposal.id, reason, latest.id)
                        job = session.scalar(select(Job).where(Job.repo_id == case.repo_id, Job.kind == 'revise_proposal',
                            Job.status == 'PENDING').order_by(Job.created_at.desc()))
                        run_operation(job.id)
        jobs = session.scalars(select(Job).where(Job.repo_id == case.repo_id,
            Job.kind.in_(['publish_docs', 'revise_proposal'])).order_by(Job.created_at.desc())).all()
        proposal_ids = {p.id for p in session.scalars(select(Proposal).where(Proposal.case_id == case.id)).all()}
        for job in jobs:
            if job.payload.get('case_id') != case.id and job.payload.get('proposal_id') not in proposal_ids:
                continue
            if job.status != 'COMPLETED':
                st.caption(f'{job.kind} · {job.status} · attempt {job.attempts}')
                if st.button('Create approved docs PR' if job.kind == 'publish_docs' else 'Resume targeted revision', key=job.id):
                    run_operation(job.id, retry=True)


login()
if os.getenv('STREAMLIT_SHARING_MODE') or os.getenv('DOCSYNC_HOSTED') == 'true':
    if not settings.database_url.startswith(('postgres://', 'postgresql')):
        st.error('Hosted deployment requires Neon PostgreSQL.'); st.stop()
engine = database(settings.database_url)
factory = session_factory(engine)
st.title('DocSync')
page = st.sidebar.radio('Page', ['Review Queue', 'Case Review', 'Audit Trail', 'Chat', 'Settings / Status'])
if st.sidebar.button('Sign out'):
    st.session_state.clear(); st.rerun()
try:
    with factory() as session:
        repo = session.scalar(select(Repository).where(Repository.full_name == settings.repository))
        if repo is None:
            st.error('Initialize the database and repository with docsync.web.migrate before opening the app.'); st.stop()
        cases = session.scalars(select(ChangeCase).where(ChangeCase.repo_id == repo.id).order_by(ChangeCase.created_at.desc())).all()
        if page == 'Review Queue':
            for case in cases:
                counts = {d: 0 for d in ['UPDATE', 'NO_CHANGE', 'UNCERTAIN']}
                for assessment in session.scalars(select(SectionAssessment).where(SectionAssessment.case_id == case.id)).all():
                    counts[assessment.decision] += 1
                proposals = session.scalars(select(Proposal).where(Proposal.case_id == case.id)).all()
                st.write({'repository': repo.full_name, 'commit': case.after_sha, 'status': case.status, **counts,
                    'unresolved_proposals': sum(p.status != 'ACCEPTED' for p in proposals),
                    'changed_files': sorted({c['path'] for c in case.case_data.get('changes', [])})})
                if st.button('Open case', key=case.id):
                    st.session_state.case_id = case.id
                    st.info('Select Case Review in the sidebar.')
        elif page == 'Case Review':
            if cases:
                ids = [c.id for c in cases]
                selected = st.selectbox('Case', ids, index=ids.index(st.session_state.get('case_id')) if st.session_state.get('case_id') in ids else 0)
                review(selected)
            else:
                st.info('No cases yet.')
        elif page == 'Audit Trail':
            case_ids = [c.id for c in cases]
            rows = session.scalars(select(AuditEvent).where((AuditEvent.case_id.in_(case_ids)) | AuditEvent.case_id.is_(None))
                .order_by(AuditEvent.created_at.desc()).limit(300)).all()
            for row in rows:
                st.write(f'{row.created_at} · {row.kind} · {row.case_id or "operation"}')
                st.json(row.payload)
                if row.payload.get('run_url'):
                    st.link_button('GitHub Actions run', row.payload['run_url'])
        elif page == 'Settings / Status':
            version = session.get(KnowledgeVersion, repo.active_index_version_id) if repo.active_index_version_id else None
            st.json({'repository': repo.full_name, 'branch': repo.monitored_branch,
                'active_knowledge_version': repo.active_index_version_id, 'approved_snapshot_commit': version.source_commit if version else None,
                'embedding_model': settings.embedding_model})
            st.write('Initialize baseline using the fork’s DocSync index workflow with an explicit approved SHA.')
            st.dataframe(approved_mappings(session, repo.id))
            operations = session.scalars(select(Job).where(Job.repo_id == repo.id).order_by(Job.created_at.desc()).limit(30)).all()
            st.dataframe([{'operation': j.id, 'kind': j.kind, 'status': j.status,
                'attempts': j.attempts, 'claimed_at': str(j.claimed_at or '')} for j in operations])
        elif page == 'Chat':
            question = st.chat_input('Ask about approved documentation')
            if question:
                with st.spinner('Reading approved documentation…'):
                    answer_question(session, settings, repo, question, embedder(settings.embedding_model, settings.embedding_cache))
            for turn in reversed(chat_history(session, repo.id)):
                with st.chat_message('user'):
                    st.write(turn.question)
                with st.chat_message('assistant'):
                    st.write(turn.answer)
                    for citation in turn.citations:
                        st.write(f"[{citation['file']} · {citation['heading']}](https://github.com/{repo.full_name}/blob/{citation['approved_commit']}/{citation['file']})")
                        st.caption(f"Approved commit {citation['approved_commit']} · knowledge version {citation['knowledge_version']}")
except Exception as exc:
    # Provider errors can contain request URLs; detailed credentials never enter UI.
    st.error(f'{type(exc).__name__}: operation could not complete. Review the durable operation status before retrying.')
