import difflib
import html
import streamlit as st
from sqlalchemy import select

from docsync.ui.components import heading, badge, empty, short, date, case_card, action, operation
from docsync.ui.state import DECISIONS, interrupted
from docsync.web.models import ProposalVersion, ReviewAction, Job
from docsync.web.workflow import accept_proposal, modify_proposal, reject_proposal, triage_section, override_no_change


def service(ctx, function, *args):
    with ctx.factory() as session:
        return function(session, *args)


def show_diff(before, after):
    lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile='CURRENT', tofile='PROPOSED', n=3, lineterm=''))
    if not lines:
        st.info('This version has the same text as the current documentation.')
        return
    rendered = []
    for line in lines:
        cls = 'add' if line.startswith('+') and not line.startswith('+++') else 'remove' if line.startswith('-') and not line.startswith('---') else ''
        rendered.append(f'<span class="line {cls}">{html.escape(line) or " "}</span>')
    st.markdown('<div class="ds-diff">' + ''.join(rendered) + '</div>', unsafe_allow_html=True)


def preserve_draft(key, draft_id):
    drafts = dict(st.session_state.get('drafts', {}))
    drafts[draft_id] = st.session_state[key]
    st.session_state.drafts = drafts


def editor(text, draft_id, label='Documentation text'):
    key = 'editor-' + draft_id
    if key not in st.session_state:
        st.session_state[key] = st.session_state.get('drafts', {}).get(draft_id, text)
    return st.text_area(label, key=key, height=260, on_change=preserve_draft, args=(key, draft_id))


def inspect_evidence(case, section):
    with st.expander('View evidence'):
        st.write('**Evidence completeness:** ' + section.evidence_completeness.replace('_', ' ').title())
        for title, values in [('Code evidence', section.code_evidence), ('Missing information', section.missing_information),
            ('Supported claims', section.safe_claims), ('Unsupported claims', section.unsupported_claims)]:
            st.markdown('**' + title + '**')
            if values:
                for value in values:
                    st.write('• ' + str(value))
            else:
                st.caption('None recorded.')
    with st.expander('View code change'):
        st.caption(f'Before {short(case.before_sha)} → After {short(case.after_sha)}')
        for change in case.case_data.get('changes', []):
            st.markdown('**' + change.get('path', 'Changed file') + '**')
            old, new = st.columns(2)
            with old:
                st.caption('BEFORE'); st.code(change.get('old_code') or '(not present)', language='python')
            with new:
                st.caption('AFTER'); st.code(change.get('new_code') or '(not present)', language='python')
            st.code(change.get('diff') or 'No diff recorded.', language='diff')
    with st.expander('View assessment details'):
        st.write('Original recommendation: ' + DECISIONS.get(section.decision, section.decision))
        st.write(section.rationale)
        st.caption('Section identity: ' + section.section_id)
        provenance = case.case_data.get('context_provenance', {}).get(section.section_id)
        if provenance:
            st.caption('Approved documentation commit used for analysis: ' + provenance)
        if section.triage_reason:
            st.write('Human resolution: ' + section.triage_reason)
        st.caption('Original section hash: ' + section.base_sha256)


def resolve_section(ctx, section, case, frozen):
    if section.decision == 'UNCERTAIN' and not section.human_resolution:
        st.warning('The available evidence does not establish a safe documentation decision. Your judgment is required.')
        choice = st.radio('How should this section be handled?', ['Keep documentation unchanged', 'Write an update'], key='triage-choice-' + section.id)
        with st.form('triage-' + section.id):
            reason = st.text_area('Reason for your decision', help='This explanation is saved in the audit history.')
            content = st.text_area('Human-authored update', value=section.current_text, height=200) if choice == 'Write an update' else ''
            if st.form_submit_button('Save decision', type='primary', disabled=frozen):
                action(lambda: service(ctx, triage_section, section.id, 'NO_CHANGE' if choice.startswith('Keep') else 'HUMAN_UPDATE', reason, content),
                    'Your decision was saved. Human updates still require explicit approval.')
    elif section.decision == 'NO_CHANGE' and not frozen:
        with st.expander('Write an update instead'):
            st.caption('The original recommendation stays in history. Your text is saved as a human version and requires approval.')
            reason = st.text_area('Why is an update needed?', key='override-reason-' + section.id)
            content = editor(section.current_text, 'override-' + section.id)
            if st.button('Save human update', key='override-' + section.id, type='primary'):
                action(lambda: service(ctx, override_no_change, section.id, reason, content), 'Human update saved. Review and approve your exact text.')


def review_section(ctx, case, section, proposal, frozen):
    st.subheader(section.heading or 'Introduction')
    st.caption(section.path)
    badge('Human update' if section.human_resolution == 'HUMAN_UPDATE' else DECISIONS.get(section.decision, section.decision),
        'warning' if section.decision == 'UNCERTAIN' else 'progress' if proposal else 'neutral')
    st.write(section.rationale)
    if section.missing_information and not section.human_resolution:
        st.warning('Missing evidence: ' + '; '.join(map(str, section.missing_information)))
    if section.unsupported_claims:
        st.caption('Not established by the evidence: ' + '; '.join(map(str, section.unsupported_claims)))
    if not proposal:
        with st.container(border=True):
            st.caption('CURRENT DOCUMENTATION')
            st.markdown(section.current_text)
        resolve_section(ctx, section, case, frozen)
        inspect_evidence(case, section)
        return
    with ctx.factory() as session:
        versions = session.scalars(select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id).order_by(ProposalVersion.version)).all()
        events = session.scalars(select(ReviewAction).where(ReviewAction.proposal_id == proposal.id).order_by(ReviewAction.created_at)).all()
    latest = versions[-1]
    st.caption(f'Version {latest.version} · {"Your edit" if latest.author == "human" else "DocSync suggestion"}')
    if proposal.status == 'ACCEPTED':
        badge('Approved', 'success')
        st.success(f'Approved version {next((v.version for v in versions if v.id == proposal.accepted_version_id), latest.version)} is saved for publication.')
    elif proposal.status == 'REVISING':
        st.info('A targeted revision is in progress. Your other sections are unchanged.')
    view = st.radio('Compare documentation', ['Changes', 'Full text'], horizontal=True, key='compare-' + proposal.id, label_visibility='collapsed')
    if view == 'Changes':
        show_diff(section.current_text, latest.proposed_text)
    else:
        old, new = st.columns(2)
        with old:
            st.caption('CURRENT'); st.markdown(section.current_text)
        with new:
            st.caption('PROPOSED'); st.markdown(latest.proposed_text)
    if not frozen and proposal.status not in {'ACCEPTED', 'APPLIED', 'REVISING'}:
        st.caption(f'Approving means accepting Version {latest.version} exactly as shown.')
        approve, edit = st.columns(2)
        approved = approve.button('Approve update', key='approve-' + latest.id, type='primary', use_container_width=True,
            on_click=None)
        # A regular widget result keeps domain errors inline rather than hiding them in a callback.
        if approved:
            action(lambda: service(ctx, accept_proposal, proposal.id, latest.id), 'Update approved. Your exact version is saved.')
        if edit.button('Edit suggestion', key='edit-' + latest.id, use_container_width=True):
            st.session_state.editing = latest.id
        if st.session_state.get('editing') == latest.id:
            with st.container(border=True):
                st.markdown('#### Your edit')
                content = editor(latest.proposed_text, latest.id)
                st.caption('Saving creates a human-authored version. It is not sent to the model and is not approved yet.')
                if st.button('Save edit', key='save-' + latest.id, type='primary'):
                    action(lambda: service(ctx, modify_proposal, proposal.id, content, latest.id), 'Your edit was saved. Approve the new version when ready.')
        with st.expander('Request revision'):
            with st.form('revision-' + latest.id):
                reason = st.text_area('What should change?', help='Give a specific reason. Only this section will be revised.')
                if st.form_submit_button('Request revision'):
                    try:
                        service(ctx, reject_proposal, proposal.id, reason, latest.id)
                        with ctx.factory() as session:
                            jobs = session.scalars(select(Job).where(Job.kind == 'revise_proposal', Job.repo_id == ctx.repo_id, Job.status == 'PENDING').order_by(Job.created_at.desc())).all()
                            job = next(j for j in jobs if j.payload.get('proposal_id') == proposal.id and j.payload.get('source_version_id') == latest.id)
                        operation(ctx, job.id)
                    except ValueError as exc:
                        st.error(str(exc))
    inspect_evidence(case, section)
    with st.expander('View version history'):
        for event in events:
            st.write(f'{date(event.created_at)} · {event.action.replace("_", " ").title()}')
            if event.reason:
                st.write(event.reason)
        for version in versions:
            st.markdown(f'**Version {version.version} · {"Human-authored" if version.author == "human" else "DocSync"}**')
            st.write(version.reason)
            st.code(version.proposed_text, language='markdown')


def render_case(ctx, item, view):
    case = item['case']
    if st.button('← All reviews'):
        st.session_state.pop('case_id', None); st.rerun()
    heading(case.summary or 'Review this code change', f'{ctx.settings.repository} · {short(case.after_sha)}', 'DOCUMENTATION REVIEW')
    badge(item['status'].label, item['status'].tone)
    st.write(item['status'].message)
    st.link_button('View code change', f'https://github.com/{ctx.settings.repository}/compare/{case.before_sha}...{case.after_sha}')
    if item['required']:
        st.progress(min(item['approved'] / item['required'], 1), text=f"{item['approved']} of {item['required']} required decisions complete")
    release = item['release']
    if release and release.pr_url:
        st.link_button('Open documentation PR', release.pr_url)
    frozen = bool(release or case.status in {'PUBLISHING', 'WAITING_MERGE', 'INDEXED'})
    sections = sorted(item['sections'], key=lambda s: ({'UNCERTAIN': 0, 'UPDATE': 1, 'NO_CHANGE': 2}.get(s.decision, 3), s.path, s.start_line))
    if not sections:
        empty('Assessment is not ready yet', 'The code change is saved. The analysis result will appear here when it is available.')
    else:
        nav, detail = st.columns([1, 3], gap='large')
        with nav:
            st.markdown('#### Documentation sections')
            by_id = {s.id: s for s in sections}
            proposals = {p.section_id: p for p in item['proposals']}
            def label(sid):
                s = by_id[sid]
                p = proposals.get(s.section_id)
                state = 'Approved' if p and p.status == 'ACCEPTED' else 'Revising' if p and p.status == 'REVISING' else DECISIONS.get(s.decision, '')
                return f'{s.heading or "Introduction"} · {state}'
            selector_key = 'section-' + case.id
            chosen = st.radio('Choose a section', list(by_id), format_func=label, key=selector_key, label_visibility='collapsed')
        with detail:
            selected = by_id[chosen]
            review_section(ctx, case, selected, proposals.get(selected.section_id), frozen)
            index = list(by_id).index(chosen)
            def move(offset):
                st.session_state[selector_key] = list(by_id)[index + offset]
            prev, nxt = st.columns(2)
            prev.button('← Previous section', disabled=index == 0, on_click=move, args=(-1,), use_container_width=True)
            nxt.button('Next section →', disabled=index == len(by_id)-1, on_click=move, args=(1,), use_container_width=True)
    jobs = [j for j in view['jobs'] if j.payload.get('case_id') == case.id or j.payload.get('proposal_id') in {p.id for p in item['proposals']}]
    publish_jobs = [j for j in jobs if j.kind == 'publish_docs' and j.status not in {'COMPLETED', 'CANCELLED'}]
    if publish_jobs:
        job = publish_jobs[0]
        with st.container(border=True):
            st.subheader('Publish approved documentation')
            st.write('Only approved versions are included. You will inspect and merge the PR in GitHub.')
            with st.expander('Included approved versions'):
                with ctx.factory() as session:
                    for p in item['proposals']:
                        if p.accepted_version_id:
                            v = session.get(ProposalVersion, p.accepted_version_id)
                            st.write(f'{p.section_id.split("::")[-1]} · Version {v.version}')
            if st.button('Create documentation PR' if job.status == 'PENDING' else 'Resume publication', type='primary',
                disabled=job.status == 'PROCESSING' and not interrupted(job)):
                operation(ctx, job.id, retry=True)
    for job in jobs:
        if job.kind == 'revise_proposal' and (job.status == 'ERROR' or interrupted(job)):
            st.warning('A revision did not finish. The reason and prior versions are saved. A retry may make another Sarvam call.')
            if st.button('Retry this revision', key='retry-' + job.id):
                operation(ctx, job.id, retry=True)
    with st.expander('Operation & recovery details'):
        if case.error:
            st.write(case.error)
        for job in jobs:
            st.caption(f'{job.kind} · {job.status} · attempt {job.attempts}')
            if job.status == 'ERROR':
                st.write('If the review is stale, start from a new code change. For an execution failure, check the saved operation before retrying.')


def render(ctx, view):
    item = next((i for i in view['cases'] if i['case'].id == st.session_state.get('case_id')), None)
    if item:
        render_case(ctx, item, view); return
    heading('Documentation reviews', 'See what changed and decide which updates should become approved documentation.', 'HUMAN REVIEW')
    filter_name = st.radio('Show reviews', ['Needs action', 'All reviews', 'Published'], horizontal=True)
    items = view['cases']
    if filter_name == 'Needs action':
        items = [i for i in items if i['status'].label in {'Ready for review', 'Human decision needed', 'Ready to publish', 'Needs attention', 'Publication prepared', 'Refresh needs attention', 'Refresh interrupted'}]
    elif filter_name == 'Published':
        items = [i for i in items if i['release']]
    if not items:
        empty('No reviews in this view', 'New code changes appear automatically. Choose All reviews to inspect previous recommendations.')
    for item in items:
        case_card(ctx, item, 'reviews')
