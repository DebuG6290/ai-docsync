"""Read-only, repository-scoped operational measurements. No semantic pseudo-labels."""
from datetime import timezone
from sqlalchemy import select
from docsync.evaluation.metrics import ratio, distribution, review_action_rates
from docsync.web.models import (Repository, ChangeCase, SarvamCall, Proposal, ReviewAction, Job,
    AuditEvent, DocumentationRelease, KnowledgeScan, KnowledgeConflict, ConflictResolution)


def seconds(start, end):
    if not start or not end:
        return None
    value = (end.replace(tzinfo=end.tzinfo or timezone.utc) - start.replace(tzinfo=start.tzinfo or timezone.utc)).total_seconds()
    return value if value >= 0 else None


def report(session, repo_id):
    repo = session.get(Repository, repo_id)
    if repo is None:
        raise ValueError('Unknown repository')
    cases = session.scalars(select(ChangeCase).where(ChangeCase.repo_id == repo_id)).all()
    case_ids = [c.id for c in cases]
    calls = session.scalars(select(SarvamCall).where(SarvamCall.case_id.in_(case_ids) |
        (SarvamCall.case_id.is_(None) & (SarvamCall.metadata_json['repo_id'].as_string() == repo_id)))).all()
    proposals = session.scalars(select(Proposal).where(Proposal.case_id.in_(case_ids))).all()
    actions = session.scalars(select(ReviewAction).where(ReviewAction.proposal_id.in_([p.id for p in proposals]))).all()
    jobs = session.scalars(select(Job).where(Job.repo_id == repo_id, Job.kind == 'analyze_push')).all()
    events = session.scalars(select(AuditEvent).where(AuditEvent.case_id.in_(case_ids))).all()
    releases = session.scalars(select(DocumentationRelease).where(DocumentationRelease.repo_id == repo_id)).all()
    scans = session.scalars(select(KnowledgeScan).where(KnowledgeScan.repo_id == repo_id)).all()
    conflicts = session.scalars(select(KnowledgeConflict).where(KnowledgeConflict.repo_id == repo_id)).all()
    resolutions = session.scalars(select(ConflictResolution).where(ConflictResolution.repo_id == repo_id)).all()
    ready = []
    activation = []
    for case in cases:
        completed = [e.created_at for e in events if e.case_id == case.id and e.kind == 'analysis_completed']
        ready.append(seconds(case.created_at, min(completed) if completed else None))
    for release in releases:
        approved = [e.created_at for e in events if e.case_id == release.case_id and e.kind == 'approval_complete']
        activation.append(seconds(max(approved) if approved else None, release.activated_at))
    attempted = [j for j in jobs if j.attempts > 0]
    terminal = [j for j in jobs if j.status in {'COMPLETED', 'ERROR'}]
    impact = [c for c in calls if c.operation == 'impact']
    with_calls = {c.case_id for c in impact}
    return {'schema_version': 'live-measurement.v1', 'repository_id': repo_id, 'repository': repo.full_name,
        'counts': {'cases': len(cases), 'proposals': len(proposals), 'review_actions': len(actions),
            'analysis_jobs': len(jobs), 'releases': len(releases), 'impact_provider_attempts': len(impact)},
        'review_action_event_rates': review_action_rates([a.action for a in actions]),
        'analysis_terminal_job_failure_rate': ratio(sum(j.status == 'ERROR' for j in terminal), len(terminal)),
        'analysis_retried_job_rate': ratio(sum(j.attempts > 1 for j in attempted), len(attempted)),
        'impact_call_diagnostic_case_coverage': ratio(len(with_calls), len(cases)),
        'recorded_impact_attempts_per_case': len(impact) / len(cases) if cases else None,
        'impact_attempt_latency_ms': distribution([c.metadata_json.get('latency_ms') for c in impact]),
        'intake_to_first_review_ready_seconds': distribution(ready),
        'final_approval_to_activation_seconds': distribution(activation),
        'input_token_observation_coverage': ratio(sum(c.metadata_json.get('input_tokens') is not None for c in calls), len(calls)),
        'quality_metrics': None, 'estimated_cost': None,
        'conflict_workflow_counts': {'scans': len(scans), 'candidate_pairs_across_scans': len(conflicts),
            'assessed_pairs_across_scans': sum(c.classification is not None for c in conflicts),
            'blocking_assessments_across_scans': sum(c.classification in {'VERSION_DRIFT', 'HARD_CONFLICT'} for c in conflicts),
            'uncertain_assessments_across_scans': sum(c.uncertain for c in conflicts),
            'human_resolutions': len(resolutions)},
        'limitations': ['Review event rates measure interactions, not factual quality or unique-proposal acceptance.',
            'Case intake is not the code commit timestamp. Provider attempt latency is not end-to-end analysis latency.',
            'Diagnostic totals can undercount interrupted/older executions. Retries are job-level, not provider-level.',
            'Imported audit timestamps describe online persistence, not original offline execution.',
            'Human quality/retrieval/conflict labels and a versioned price assumption are required for further metrics.']}
