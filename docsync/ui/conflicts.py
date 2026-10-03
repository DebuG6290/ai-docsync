"""Human conflict resolution over durable candidate evidence."""
import streamlit as st
from sqlalchemy import select
from docsync.sarvam import SarvamClient
from docsync.knowledge.gate import resolve, scan_pending, audit_current, activate_audit, aware, review_queries
from docsync.web.models import KnowledgeScan
from docsync.ui.components import action, operation, prose, date

LABELS = {'PREFER_A': 'Prefer A (exclude B from trusted knowledge)',
    'PREFER_B': 'Prefer B (exclude A from trusted knowledge)',
    'DIFFERENT_SCOPES': 'Keep both: explicitly different scopes',
    'EXCLUDE_A': 'Exclude section A', 'EXCLUDE_B': 'Exclude section B', 'EXCLUDE_BOTH': 'Exclude both sections'}


def pair_table(pairs):
    st.dataframe([{'A': p.left_id, 'B': p.right_id, 'Assessment': p.classification or 'Pending',
        'Uncertain': p.uncertain, 'Human resolution': p.resolution or '—'} for p in pairs], hide_index=True)


def render(ctx, view):
    if view['active'] and st.button('Audit current approved knowledge for conflicts'):
        action(lambda: audit_current(ctx.engine, ctx.repo_id), 'Approved snapshot staged for integrity review.')
    with ctx.factory() as session:
        scans = session.scalars(select(KnowledgeScan).where(KnowledgeScan.repo_id == ctx.repo_id)
            .order_by(KnowledgeScan.created_at.desc())).all()
    if not scans:
        return
    st.subheader('Knowledge integrity review')
    st.caption('Conflict assessments do not approve documentation. Resolve blocking or uncertain pairs before activating this snapshot. Preference excludes a whole section from retrieval; it does not edit GitHub files.')
    selected = st.selectbox('Integrity scan', [s.id for s in scans],
        format_func=lambda sid: next(s.state.replace('_', ' ').title() + ' · ' + s.source_commit[:7] + ' · ' + date(s.created_at) for s in scans if s.id == sid),
        key='integrity-scan-' + ctx.repo_id)
    scan = next(s for s in scans if s.id == selected)
    with ctx.factory() as session:
        counts, _, _ = review_queries(session, scan)
    def table_page():
        page = int(st.number_input('Evidence page', min_value=1, max_value=max(1, (counts['total'] + 9) // 10), value=1, step=1, key='evidence-page-' + scan.id))
        with ctx.factory() as session:
            _, _, query = review_queries(session, scan)
            pair_table(session.scalars(query.offset((page - 1) * 10).limit(10)).all())
        st.caption('All durable pairs remain available through these pages.')
    for scan in [scan]:
        current = scan.parent_version_id == view['repo'].active_index_version_id
        if scan.state == 'ACTIVATED':
            with st.expander('Completed integrity review · ' + scan.source_commit[:7] + ' · ' + date(scan.created_at)):
                st.caption('Knowledge version: ' + scan.activated_version_id)
                table_page()
            continue
        with st.expander(f'{scan.state.replace("_", " ").title()} · {scan.source_commit[:7]} · {date(scan.created_at)}', expanded=current):
            st.caption(f'{len(scan.snapshot["sections"])} sections · {counts["total"]} plausible pairs · {counts["pending"]} unresolved · {scan.narrowing_version} / {scan.prompt_version}')
            if not current:
                st.warning('This scan belongs to an older parent snapshot. Resume indexing to stage fresh evidence.')
                continue
            if scan.state in {'PENDING', 'ERROR'}:
                if st.button('Run / resume semantic conflict scan', key='scan-' + scan.id):
                    action(lambda s=scan: scan_pending(ctx.engine, ctx.repo_id, s.id,
                        SarvamClient(ctx.settings.sarvam_model)), 'Conflict scan completed.')
            if scan.state == 'SCANNING':
                st.info('Conflict scan is running. Refresh after completion. An interrupted scan can be retried after its 30-minute lease.')
                from docsync.web.models import utcnow
                from datetime import timedelta
                if not scan.claimed_at or aware(scan.claimed_at) < utcnow() - timedelta(minutes=30):
                    if st.button('Retry interrupted scan', key='retry-scan-' + scan.id):
                        action(lambda s=scan: scan_pending(ctx.engine, ctx.repo_id, s.id,
                            SarvamClient(ctx.settings.sarvam_model)), 'Conflict scan resumed.')
            sources = {s['section_id']: s for s in scan.snapshot['sections']}
            st.caption(f'{counts["assessed"]} assessed pairs need human judgement; {counts["pending"] - counts["assessed"]} await semantic assessment.')
            if counts['assessed']:
                page = int(st.number_input('Review page', min_value=1, max_value=max(1, (counts['assessed'] + 9) // 10), value=1, step=1, key='conflict-page-' + scan.id))
            else:
                page = 1
            # Pending pairs remain blocking; only evaluated evidence gets forms.
            with ctx.factory() as session:
                _, query, _ = review_queries(session, scan)
                assessed = session.scalars(query.offset((page - 1) * 10).limit(10)).all()
            for pair in assessed:
                with st.container(border=True):
                    st.write(pair.classification or 'Assessment pending')
                    if pair.uncertain:
                        st.warning('Model uncertainty requires your judgement.')
                    a, b = st.columns(2)
                    for column, label, sid in ((a, 'A', pair.left_id), (b, 'B', pair.right_id)):
                        with column:
                            st.write(f'{label}: {sources[sid]["heading"]}')
                            st.caption(sid + ' · source ' + sources[sid]['source_commit'][:7])
                            with st.expander('Read source ' + label):
                                prose(sources[sid]['content'])
                    if pair.assessment:
                        prose(pair.assessment['reason'])
                        if pair.assessment['missing_information']:
                            st.write('Missing information: ' + '; '.join(pair.assessment['missing_information']))
                    with st.form('resolve-' + pair.id):
                        choice = st.selectbox('Human resolution', list(LABELS), format_func=LABELS.get)
                        rationale = st.text_area('Rationale and scope evidence')
                        if st.form_submit_button('Record human resolution', type='primary', disabled=scan.state == 'SCANNING'):
                            def save(p=pair, choice=choice, rationale=rationale):
                                with ctx.factory() as session:
                                    resolve(session, ctx.repo_id, p.id, choice, rationale, ctx.settings.review_username)
                                    session.commit()
                            action(save, 'Human resolution saved.')
            if counts['excluded']:
                st.write('Excluded from this trusted snapshot: ' + ', '.join(sorted(counts['excluded'])))
            if not counts['pending'] and scan.state == 'READY':
                if scan.snapshot.get('mode') == 'AUDIT':
                    st.success('Integrity review is complete. Apply human exclusions to a new immutable knowledge version.')
                    if st.button('Activate reviewed integrity snapshot', key='activate-audit-' + scan.id, type='primary'):
                        action(lambda s=scan: activate_audit(ctx.engine, ctx.repo_id, s.id), 'Reviewed integrity snapshot activated.')
                else:
                    st.success('Integrity review is complete. Resume the original operation to reverify the approved Git snapshot and activate knowledge.')
                    waiting = [j for j in view['jobs'] if j.status == 'WAITING_REVIEW' and
                        (j.kind == 'index_baseline' and j.payload.get('baseline_sha') == scan.source_commit or
                         j.kind == 'activate_release' and j.payload.get('merge_sha') == scan.source_commit)]
                    for job in waiting:
                        if st.button('Resume verified knowledge activation', key='resume-knowledge-' + job.id, type='primary'):
                            action(lambda j=job: operation(ctx, j.id), 'Knowledge activation finished.')
            with st.expander('All assessed pairs and recorded resolutions'):
                table_page()
