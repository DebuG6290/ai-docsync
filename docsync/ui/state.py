"""Read-only product states derived from durable evidence, without AI inference."""
from dataclasses import dataclass
from datetime import timedelta
from sqlalchemy import select
from docsync.web.models import Repository, ChangeCase, SectionAssessment, Proposal, DocumentationRelease, Job, KnowledgeVersion, utcnow

DECISIONS = {'UPDATE': 'Update suggested', 'NO_CHANGE': 'No update recommended', 'UNCERTAIN': 'Human decision needed'}


@dataclass(frozen=True)
class ProductStatus:
    label: str
    message: str
    tone: str = 'neutral'


def interrupted(job):
    return bool(job.status == 'PROCESSING' and (not job.claimed_at or
        job.claimed_at.replace(tzinfo=utcnow().tzinfo) < utcnow() - timedelta(minutes=30)))


def release_status(release, jobs=()):
    related = [j for j in jobs if j.kind == 'activate_release' and j.payload.get('pr_number') == release.pr_number]
    latest = max(related, key=lambda j: j.created_at) if related else None
    if release.status == 'INDEXED':
        return ProductStatus('Knowledge updated', 'This documentation update is available to Chat.', 'success')
    if release.status == 'KNOWLEDGE_REVIEW':
        return ProductStatus('Knowledge conflict review', 'Resolve staged conflicts in Knowledge, then resume verification and indexing. Chat uses the previous approved version.', 'warning')
    if latest and interrupted(latest):
        return ProductStatus('Refresh interrupted', 'Chat still uses the previous version. Retry the indexing Action after checking its run.', 'error')
    if release.status in {'INDEX_ERROR', 'INDEX_CONFLICT'} or (latest and latest.status == 'ERROR'):
        return ProductStatus('Refresh needs attention', 'The update has not been activated. Review the indexing failure; Chat uses the previous approved version.', 'error')
    if release.status == 'INDEXING':
        return ProductStatus('Updating knowledge', 'Approved documentation is being indexed. Chat still uses the previous version.', 'progress')
    if release.status == 'VERIFYING':
        return ProductStatus('Verifying merged documentation', 'The merge is confirmed. DocSync is checking the approved text before indexing.', 'progress')
    if release.merged_sha:
        return ProductStatus('Documentation merged', 'Waiting for the knowledge refresh. Chat still uses the previous version.', 'warning')
    if latest and latest.status in {'PENDING', 'PROCESSING'}:
        return ProductStatus('Checking merged update', 'An indexing run was recorded. Merge verification is pending.', 'progress')
    if release.status == 'CLOSED':
        return ProductStatus('PR closed without merging', 'Reopen the documentation PR in GitHub or start a follow-up review.', 'warning')
    if release.status == 'PREPARED':
        return ProductStatus('Publication prepared', 'The approved snapshot is saved. Resume publication to create its PR.', 'warning')
    return ProductStatus('Waiting for merge', 'The documentation PR needs to be merged in GitHub.')


def case_status(case, sections, proposals, release=None, jobs=()):
    if release:
        return release_status(release, jobs)
    relevant = [j for j in jobs if j.payload.get('case_id') == case.id or j.delivery_id and j.delivery_id == case.delivery_id
        or j.payload.get('proposal_id') in {p.id for p in proposals}]
    if any(j.status == 'ERROR' or interrupted(j) for j in relevant) or case.status in {'ERROR', 'CONFLICT', 'PUBLISH_ERROR', 'INDEX_CONFLICT'}:
        return ProductStatus('Needs attention', 'An operation could not finish. Open this review for recovery details.', 'error')
    if any(s.decision == 'UNCERTAIN' and not s.human_resolution for s in sections):
        return ProductStatus('Human decision needed', 'Resolve the missing evidence before publication.', 'warning')
    if case.status == 'ANALYZING':
        return ProductStatus('Analyzing documentation', 'DocSync is assessing the code change and mapped documentation.', 'progress')
    if case.status == 'PUBLISHING':
        return ProductStatus('Preparing documentation PR', 'Your approved versions are being prepared for GitHub.', 'progress')
    if proposals and all(p.status == 'ACCEPTED' for p in proposals):
        return ProductStatus('Ready to publish', 'All required updates are approved. Create the documentation PR.', 'success')
    if any(p.status == 'REVISING' for p in proposals):
        return ProductStatus('Revision in progress', 'One section is being revised. You can inspect the other sections.', 'progress')
    if not proposals and case.decision == 'NO_CHANGE':
        return ProductStatus('No update recommended', 'Review is optional. You can write a human update if needed.')
    if not proposals and sections and all(s.human_resolution == 'NO_CHANGE' for s in sections if s.decision == 'UNCERTAIN'):
        return ProductStatus('Review complete', 'No documentation update is awaiting approval.', 'success')
    return ProductStatus('Ready for review', 'Review the suggested updates and approve the exact text.')


def load(ctx):
    with ctx.factory() as session:
        repo = session.get(Repository, ctx.repo_id)
        if repo is None:
            raise ValueError('Unknown selected repository')
        cases = session.scalars(select(ChangeCase).where(ChangeCase.repo_id == repo.id).order_by(ChangeCase.created_at.desc())).all()
        ids = [c.id for c in cases]
        sections = session.scalars(select(SectionAssessment).where(SectionAssessment.case_id.in_(ids))).all() if ids else []
        proposals = session.scalars(select(Proposal).where(Proposal.case_id.in_(ids))).all() if ids else []
        releases = session.scalars(select(DocumentationRelease).where(DocumentationRelease.repo_id == repo.id)).all()
        jobs = session.scalars(select(Job).where(Job.repo_id == repo.id).order_by(Job.created_at.desc())).all()
        versions = session.scalars(select(KnowledgeVersion).where(KnowledgeVersion.repo_id == repo.id).order_by(KnowledgeVersion.created_at)).all()
        active = next((v for v in versions if v.id == repo.active_index_version_id), None)
    records = []
    for case in cases:
        ss = [s for s in sections if s.case_id == case.id]
        ps = [p for p in proposals if p.case_id == case.id]
        release = next((r for r in releases if r.case_id == case.id), None)
        required = len(ps) + sum(s.decision == 'UNCERTAIN' and s.section_id not in {p.section_id for p in ps} for s in ss)
        approved = sum(p.status == 'ACCEPTED' for p in ps) + sum(s.decision == 'UNCERTAIN' and s.human_resolution == 'NO_CHANGE' for s in ss)
        records.append({'case': case, 'sections': ss, 'proposals': ps, 'release': release,
            'status': case_status(case, ss, ps, release, jobs), 'required': required, 'approved': approved})
    return {'repo': repo, 'cases': records, 'releases': releases, 'jobs': jobs, 'versions': versions, 'active': active,
        'pending': [r for r in releases if r.status not in {'INDEXED', 'CLOSED'}],
        'version_names': {v.id: f'K{i + 1}' for i, v in enumerate(versions)}}
