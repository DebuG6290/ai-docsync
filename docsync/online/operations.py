from datetime import timedelta

from sqlalchemy import select

from docsync.web.database import session_factory
from docsync.web.models import AuditEvent, ChangeCase, Job, Proposal, ProposalVersion, DocumentationRelease, utcnow
from docsync.web.worker import _process_job


def execute(engine, settings, job_id, *, run_url="", retry=False):
    """Claim one durable operation; no polling or background service required.

    A 30-minute lease exceeds our finite execution timeout. A retry is explicit:
    the remote model may have billed a response before an interrupted persistence.
    """
    factory = session_factory(engine)
    with factory() as session:
        job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None:
            raise ValueError("Unknown operation")
        if job.status == "COMPLETED":
            return False
        if job.status == "PROCESSING":
            claim = job.claimed_at
            if claim and claim.replace(tzinfo=utcnow().tzinfo) > utcnow() - timedelta(minutes=30):
                raise ValueError("Operation is already running")
            if not retry:
                raise ValueError("Interrupted operation: explicit retry required")
        if job.status == "ERROR" and not retry:
            raise ValueError("Failed operation: explicit retry required")
        # Reconcile completed persistence before repeating an external call.
        done = False
        if job.kind == "analyze_push":
            case = session.scalar(select(ChangeCase).where(ChangeCase.repo_id == job.repo_id,
                ChangeCase.before_sha == job.payload['before_sha'], ChangeCase.after_sha == job.payload['after_sha']))
            done = bool(case and case.decision)
        elif job.kind == "revise_proposal":
            proposal = session.get(Proposal, job.payload['proposal_id'])
            latest = session.scalar(select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id)
                .order_by(ProposalVersion.version.desc()).limit(1))
            done = bool(latest and job.payload.get('source_version_id') and latest.id != job.payload['source_version_id'])
        elif job.kind == "publish_docs":
            release = session.scalar(select(DocumentationRelease).where(
                DocumentationRelease.case_id == job.payload['case_id']))
            done = bool(release and release.pr_number)
        if done:
            job.status = "COMPLETED"
            session.commit()
            return False
        job.status = "PROCESSING"
        job.claimed_at = utcnow()
        job.attempts += 1
        session.add(AuditEvent(kind="operation_started", payload={"job_id": job.id,
            "kind": job.kind, "attempt": job.attempts, "run_url": run_url}))
        session.commit()
        detached = Job(id=job.id, repo_id=job.repo_id, delivery_id=job.delivery_id,
            kind=job.kind, payload=dict(job.payload))
    try:
        _process_job(engine, settings, detached)
    except Exception as exc:
        with factory() as session:
            job = session.get(Job, job_id)
            job.status = "ERROR"
            if job.kind == "revise_proposal":
                proposal = session.get(Proposal, job.payload['proposal_id'])
                if proposal:
                    proposal.status = "REVISION_ERROR"
            session.add(AuditEvent(kind="operation_failed", payload={"job_id": job_id,
                "error_type": type(exc).__name__, "run_url": run_url}))
            session.commit()
        raise
    with factory() as session:
        job = session.get(Job, job_id)
        job.status = "COMPLETED"
        session.add(AuditEvent(kind="operation_completed", payload={"job_id": job_id, "run_url": run_url}))
        session.commit()
    return True
