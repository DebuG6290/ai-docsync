"""A read-only case trace. Completed steps require stored, scoped evidence."""
from dataclasses import dataclass

import streamlit as st
from sqlalchemy import select

from docsync.web.models import AuditEvent, ChangeCase, Proposal, ProposalVersion
from docsync.ui.mapping_health import changed_symbol_coverage


@dataclass(frozen=True)
class TraceStep:
    title: str
    state: str
    details: tuple[str, ...]


def build_change_trace(repo_id, item, *, proposal_versions=(), audit_events=(),
                       knowledge_versions=(), active_version_id=None, version_names=None):
    """Build display data without writes, network requests, or inferred activation."""
    case = item['case']
    if case.repo_id != repo_id:
        raise ValueError('This review belongs to another repository')
    sections = [s for s in item['sections'] if s.case_id == case.id]
    proposals = [p for p in item['proposals'] if p.case_id == case.id]
    release = item.get('release')
    if release and (release.repo_id != repo_id or release.case_id != case.id):
        raise ValueError('This release belongs to another review or repository')
    events = [e for e in audit_events if e.case_id == case.id]
    mappings = (case.case_data or {}).get('mappings', [])
    mapped = sorted({m['section_id'] for m in mappings if isinstance(m, dict) and m.get('section_id')})
    steps = [TraceStep('Code change', 'Recorded', (f'{case.before_sha} → {case.after_sha}',))]
    assessed_ids = {s.section_id for s in sections}
    unassessed_ids = set(mapped) - assessed_ids
    unmapped_ids = changed_symbol_coverage(case.case_data or {})['unmapped_code_ids']
    assessment_details = tuple(f'{s.section_id}: {s.decision}' for s in sections)
    assessment_details += tuple(f'{section_id}: Not assessed' for section_id in mapped if section_id not in assessed_ids)
    assessment_details += tuple(f'{code_id}: No approved mapping; not assessed' for code_id in unmapped_ids)
    assessment_state = 'Partially assessed' if sections and (unassessed_ids or unmapped_ids) else 'Assessed' if sections else 'Pending'
    steps.append(TraceStep('Mapped documentation', assessment_state,
        (f'{len(mapped)} mapped sections in the saved case; {len(sections)} assessed.',)
        + assessment_details))

    accepted, pending = [], []
    for proposal in proposals:
        version = next((v for v in proposal_versions if v.id == proposal.accepted_version_id
            and v.proposal_id == proposal.id), None)
        if proposal.status in {'ACCEPTED', 'APPLIED'} and version:
            accepted.append(f'{proposal.section_id}: Version {version.version} ({version.id})')
        elif proposal.accepted_version_id:
            pending.append(f'{proposal.section_id}: accepted version could not be verified.')
        else:
            pending.append(f'{proposal.section_id}: {proposal.status.replace("_", " ").title()}')
    proposed_sections = {p.section_id for p in proposals}
    pending.extend(f'{s.section_id}: no proposal version recorded.' for s in sections
        if (s.decision == 'UPDATE' or s.human_resolution == 'HUMAN_UPDATE')
        and s.section_id not in proposed_sections)
    no_update = bool(sections) and not proposals and not unassessed_ids and not unmapped_ids and all(
        s.decision == 'NO_CHANGE' or s.human_resolution == 'NO_CHANGE' for s in sections)
    unresolved = any(s.decision == 'UNCERTAIN' and not s.human_resolution for s in sections)
    approval_state = ('No update required' if no_update else 'Approved' if accepted and not pending
        and not unresolved else 'Pending')
    steps.append(TraceStep('Human approval', approval_state,
        tuple(accepted + pending) or (('No update requires approval.' if no_update
            else 'No approved proposal version recorded.'),)))

    if release and release.pr_number and release.pr_url:
        publication = TraceStep('Documentation PR', 'Closed' if release.status == 'CLOSED' else 'Created',
            (f'#{release.pr_number} · {release.pr_url}', f'Approved documentation commit: {release.commit_sha}'))
    elif release:
        publication = TraceStep('Documentation PR', 'Prepared',
            (f'Approved documentation commit: {release.commit_sha}', 'No PR recorded yet.'))
    else:
        publication = TraceStep('Documentation PR', 'Not required' if no_update else 'Pending',
            ('No documentation release recorded.',))
    steps.append(publication)

    merge_verified = bool(release and release.merged_sha and any(e.kind == 'documentation_merge_verified'
        and e.payload.get('pr_number') == release.pr_number
        and e.payload.get('merged_sha') == release.merged_sha for e in events))
    steps.append(TraceStep('Merge verification', 'Verified' if merge_verified else
        'Merge recorded' if release and release.merged_sha else 'Not merged',
        (release.merged_sha,) if release and release.merged_sha else ('No merged commit recorded.',)))

    activation = None
    if release and release.status == 'INDEXED' and release.activated_at and merge_verified:
        for event in reversed(events):
            if event.kind != 'knowledge_index_activated' or event.payload.get('merged_sha') != release.merged_sha:
                continue
            activation = next((v for v in knowledge_versions if v.id == event.payload.get('version_id')
                and v.repo_id == repo_id and v.source_commit == release.merged_sha), None)
            if activation:
                break
    if activation:
        label = (version_names or {}).get(activation.id, activation.id)
        current = 'Currently selected for this repository.' if active_version_id == activation.id else 'Historical activation; another version may now be selected.'
        knowledge = TraceStep('Knowledge activation', 'Verified',
            (f'{label} · {activation.id}', f'Activated from merged commit: {activation.source_commit}', current))
    else:
        state = 'Needs attention' if release and release.status in {'INDEX_ERROR', 'INDEX_CONFLICT', 'KNOWLEDGE_REVIEW'} else 'Not verified'
        knowledge = TraceStep('Knowledge activation', state,
            ('No matching verified activation evidence for this release.',))
    steps.append(knowledge)
    return tuple(steps)


def load_change_trace(ctx, item, view):
    """Read only version/event rows owned by the selected repository and case."""
    case = item['case']
    if case.repo_id != ctx.repo_id:
        raise ValueError('This review belongs to another repository')
    with ctx.factory() as session:
        versions = session.scalars(select(ProposalVersion).join(Proposal,
            ProposalVersion.proposal_id == Proposal.id).join(ChangeCase, Proposal.case_id == ChangeCase.id)
            .where(ChangeCase.repo_id == ctx.repo_id, ChangeCase.id == case.id)).all()
        events = session.scalars(select(AuditEvent).join(ChangeCase, AuditEvent.case_id == ChangeCase.id)
            .where(ChangeCase.repo_id == ctx.repo_id, ChangeCase.id == case.id)
            .order_by(AuditEvent.created_at, AuditEvent.id)).all()
    repo = view['repo']
    if repo.id != ctx.repo_id:
        raise ValueError('This workspace belongs to another repository')
    return build_change_trace(ctx.repo_id, item, proposal_versions=versions, audit_events=events,
        knowledge_versions=view['versions'], active_version_id=repo.active_index_version_id,
        version_names=view.get('version_names'))


def render_change_trace(ctx, item, view):
    with st.expander('Change trace'):
        for step in load_change_trace(ctx, item, view):
            st.markdown(f'**{step.title} · {step.state}**')
            for detail in step.details:
                st.caption(detail)
        case = item['case']
        st.link_button('Compare code commits',
            f'https://github.com/{ctx.settings.repository}/compare/{case.before_sha}...{case.after_sha}',
            key='trace-code-' + case.id)
        release = item.get('release')
        if release and release.pr_url:
            st.link_button('Inspect documentation PR', release.pr_url, key='trace-pr-' + case.id)
        st.caption('Chat citations remain attached to their own recorded knowledge versions.')
