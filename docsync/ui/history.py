import html
import streamlit as st
from sqlalchemy import select
from docsync.ui.components import heading, empty, date
from docsync.web.models import AuditEvent

LABELS = {
    'github_commit_received': 'Code change detected', 'action_received': 'GitHub Action received',
    'analysis_started': 'Documentation assessment started', 'analysis_completed': 'Documentation assessment completed',
    'proposal_created': 'Suggested update created', 'review_accept': 'Documentation version approved',
    'review_modify': 'Human edit saved', 'review_reject': 'Revision requested',
    'proposal_revision_completed': 'Revised suggestion saved', 'no_change_overridden': 'Human update replaces no-update recommendation',
    'uncertainty_triaged_no_change': 'Human decision: keep documentation unchanged',
    'uncertainty_triaged_to_human_update': 'Human update resolves uncertainty',
    'approval_complete': 'Required updates approved', 'publication_prepared': 'Approved publication snapshot saved',
    'documentation_pr_created': 'Documentation PR created', 'documentation_merge_confirmed': 'Documentation merge confirmed',
    'documentation_merge_verified': 'Approved merge verified', 'knowledge_refresh_started': 'Knowledge refresh started',
    'knowledge_index_activated': 'Approved knowledge activated', 'approved_baseline_indexed': 'Approved baseline initialized',
    'operation_failed': 'Operation needs attention', 'analysis_error': 'Assessment could not finish',
    'index_refresh_conflict': 'Merged documentation needs reconciliation',
}


def render(ctx, view):
    heading('A clear record of every decision', 'Trace a code change through review, publication, and approved knowledge.', 'ACTIVITY HISTORY')
    cases = {i['case'].id: i['case'] for i in view['cases']}
    selection = st.selectbox('Show activity for', ['all', *cases], format_func=lambda k: 'All activity' if k == 'all' else
        (cases[k].summary or 'Code change')[:90] + ' · ' + cases[k].after_sha[:7])
    with ctx.factory() as session:
        query = select(AuditEvent).where((AuditEvent.case_id.in_(list(cases))) | AuditEvent.case_id.is_(None))
        if selection != 'all':
            query = query.where(AuditEvent.case_id == selection)
        rows = session.scalars(query.order_by(AuditEvent.created_at.desc()).limit(300)).all()
    jobs = {j.id for j in view['jobs']}
    rows = [r for r in rows if r.case_id or r.payload.get('job_id') in jobs or r.kind == 'approved_baseline_indexed']
    details = st.toggle('Include technical events', value=False)
    visible = rows if details else [r for r in rows if r.kind in LABELS]
    if not visible:
        empty('Your activity will appear here', 'Review decisions, documentation releases, and knowledge updates are recorded automatically.')
    for row in visible:
        title = LABELS.get(row.kind, row.kind.replace('_', ' ').capitalize())
        st.markdown(f'<div class="ds-timeline"><small>{html.escape(date(row.created_at))}</small><h4>{html.escape(title)}</h4></div>', unsafe_allow_html=True)
        if row.payload.get('reason'):
            st.write(row.payload['reason'])
        with st.expander('Event details', key='event-' + row.id):
            if row.case_id:
                st.caption('Review identity: ' + row.case_id)
            st.json(row.payload)
            if row.payload.get('run_url'):
                st.link_button('Open GitHub Actions run', row.payload['run_url'])
