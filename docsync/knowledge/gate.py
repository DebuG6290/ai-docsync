"""Durable conflict staging, finite assessment and explicit human resolution."""
import hashlib
import json
from dataclasses import asdict
from datetime import timedelta, timezone
from sqlalchemy import select, func, or_
from docsync.errors import ConflictError
from docsync.knowledge.conflicts import candidate_pairs, assess, BLOCKING, NARROWING_VERSION, PROMPT_VERSION
from docsync.web.database import session_factory
from docsync.web.models import (Repository, KnowledgeVersion, IndexedSection, KnowledgeScan,
    KnowledgeConflict, ConflictResolution, DocumentationRelease, SarvamCall, AuditEvent, utcnow)

ACTIONS = {'PREFER_A', 'PREFER_B', 'DIFFERENT_SCOPES', 'EXCLUDE_A', 'EXCLUDE_B', 'EXCLUDE_BOTH'}
# Bound one finite invocation below the operation lease/workflow timeout; never drop pairs.
PAIR_BATCH_LIMIT = 4


class KnowledgeReviewPending(ConflictError):
    """Expected review boundary, not a provider failure or a successful activation."""


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def wait_for_review(session, job):
    job.status = 'WAITING_REVIEW'
    if job.kind == 'activate_release':
        release = session.scalar(select(DocumentationRelease).where(DocumentationRelease.repo_id == job.repo_id,
            DocumentationRelease.pr_number == job.payload.get('pr_number')))
        if release:
            release.status = 'KNOWLEDGE_REVIEW'
    session.add(AuditEvent(kind='knowledge_activation_waiting', payload={'repo_id': job.repo_id, 'job_id': job.id}))


def owned_scan(session, repo_id, scan_id, *, lock=False):
    query = select(KnowledgeScan).where(KnowledgeScan.id == scan_id, KnowledgeScan.repo_id == repo_id)
    scan = session.scalar(query.with_for_update() if lock else query)
    if scan is None:
        raise ValueError('Conflict scan belongs to another repository or does not exist')
    return scan


def rows(session, scan):
    return session.scalars(select(KnowledgeConflict).where(KnowledgeConflict.scan_id == scan.id,
        KnowledgeConflict.repo_id == scan.repo_id).order_by(KnowledgeConflict.left_id, KnowledgeConflict.right_id)).all()


def exclusions(pairs):
    ids = set()
    for pair in pairs:
        if pair.resolution in {'PREFER_B', 'EXCLUDE_A', 'EXCLUDE_BOTH'}:
            ids.add(pair.left_id)
        if pair.resolution in {'PREFER_A', 'EXCLUDE_B', 'EXCLUDE_BOTH'}:
            ids.add(pair.right_id)
    return ids


def unresolved(pairs):
    excluded = exclusions(pairs)
    return [p for p in pairs if not {p.left_id, p.right_id} & excluded and not p.resolution
        and (p.classification is None or p.classification in BLOCKING or p.uncertain)]


def review_queries(session, scan):
    """Repository-scoped counts and SQL pagination without loading every pair.

    All unresolved evidence still blocks activation, including off-screen pairs.
    """
    base = select(KnowledgeConflict).where(KnowledgeConflict.repo_id == scan.repo_id,
        KnowledgeConflict.scan_id == scan.id)
    resolved = session.scalars(base.where(KnowledgeConflict.resolution.is_not(None))).all()
    excluded = exclusions(resolved)
    pending = base.where(KnowledgeConflict.resolution.is_(None), or_(
        KnowledgeConflict.classification.is_(None), KnowledgeConflict.classification.in_(BLOCKING),
        KnowledgeConflict.uncertain.is_(True)))
    if excluded:
        pending = pending.where(KnowledgeConflict.left_id.not_in(excluded), KnowledgeConflict.right_id.not_in(excluded))
    assessed = pending.where(KnowledgeConflict.classification.is_not(None))
    def count(query):
        return session.scalar(select(func.count()).select_from(query.subquery()))
    counts = {'total': count(base), 'pending': count(pending), 'assessed': count(assessed), 'excluded': excluded}
    order = (KnowledgeConflict.left_id, KnowledgeConflict.right_id)
    return counts, assessed.order_by(*order), base.order_by(*order)


def review_state(pairs):
    pending = unresolved(pairs)
    if any(p.classification is None for p in pending):
        return 'PENDING'
    return 'REVIEW_REQUIRED' if pending else 'READY'


def snapshot(session, repo, source_commit, changed, *, mode='UPDATE'):
    if len({s.section_id for s in changed}) != len(changed):
        raise ValueError('Duplicate changed section identities')
    sections = {}
    if repo.active_index_version_id:
        owner = session.get(KnowledgeVersion, repo.active_index_version_id)
        if owner is None or owner.repo_id != repo.id:
            raise ValueError('Active knowledge belongs to another repository')
        old = session.scalars(select(IndexedSection).where(IndexedSection.version_id == owner.id)
            .order_by(IndexedSection.section_id, IndexedSection.chunk_index)).all()
        for chunk in old:
            item = sections.setdefault(chunk.section_id, {'section_id': chunk.section_id, 'path': chunk.path,
                'heading': chunk.heading, 'content': '', 'source_commit': chunk.source_commit})
            item['content'] += chunk.content
    sections.update({s.section_id: asdict(s) for s in changed})
    return {'mode': mode, 'parent_version_id': repo.active_index_version_id, 'source_commit': source_commit,
        'sections': [sections[k] for k in sorted(sections)], 'changed_ids': sorted(s.section_id for s in changed),
        'narrowing_version': NARROWING_VERSION, 'prompt_version': PROMPT_VERSION}


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def stage_scan(session, repo, source_commit, changed, *, mode='UPDATE'):
    # Hold repository lock through deduplication; activation takes the same lock.
    current = session.scalar(select(Repository).where(Repository.id == repo.id).with_for_update())
    if current is None:
        raise ValueError('Unknown repository')
    actual_parent = session.scalar(select(Repository.active_index_version_id).where(Repository.id == repo.id))
    if actual_parent != repo.active_index_version_id:
        raise ConflictError('Approved knowledge changed; retry against the current snapshot')
    if mode not in {'UPDATE', 'AUDIT'}:
        raise ValueError('Unknown scan mode')
    if mode == 'AUDIT':
        parent = session.get(KnowledgeVersion, repo.active_index_version_id) if repo.active_index_version_id else None
        if parent is None or parent.repo_id != repo.id or parent.source_commit != source_commit or changed:
            raise ValueError('Audit scans may only inspect the existing approved snapshot')
    data = snapshot(session, repo, source_commit, changed, mode=mode)
    digest = fingerprint(data)
    scan = session.scalar(select(KnowledgeScan).where(KnowledgeScan.repo_id == repo.id, KnowledgeScan.fingerprint == digest))
    if scan:
        return scan
    pairs = candidate_pairs(data['sections'], set(data['changed_ids']) if data['parent_version_id'] and mode != 'AUDIT' else None)
    scan = KnowledgeScan(repo_id=repo.id, parent_version_id=repo.active_index_version_id,
        source_commit=source_commit, fingerprint=digest, narrowing_version=NARROWING_VERSION,
        prompt_version=PROMPT_VERSION, snapshot=data, state='PENDING' if pairs else 'READY',
        completed_at=None if pairs else utcnow())
    session.add(scan); session.flush()
    for left, right, signals in pairs:
        session.add(KnowledgeConflict(repo_id=repo.id, scan_id=scan.id, left_id=left, right_id=right,
            narrowing_signals=signals))
    session.add(AuditEvent(kind='knowledge_conflict_scan_staged', payload={'repo_id': repo.id,
        'scan_id': scan.id, 'source_commit': source_commit, 'parent_version_id': scan.parent_version_id,
        'section_count': len(data['sections']), 'candidate_pair_count': len(pairs),
        'narrowing_version': NARROWING_VERSION, 'prompt_version': PROMPT_VERSION}))
    session.flush()
    return scan


def scan_pending(engine, repo_id, scan_id, client):
    factory = session_factory(engine)
    with factory() as session:
        scan = owned_scan(session, repo_id, scan_id, lock=True)
        if scan.state in {'READY', 'REVIEW_REQUIRED', 'ACTIVATED'}:
            return scan.state
        repo = session.get(Repository, repo_id)
        if repo.active_index_version_id != scan.parent_version_id:
            raise ConflictError('Scan is stale; stage against current approved knowledge')
        if scan.state == 'SCANNING' and scan.claimed_at and aware(scan.claimed_at) > utcnow() - timedelta(minutes=30):
            raise ValueError('Conflict scan is already running')
        scan.state, scan.claimed_at = 'SCANNING', utcnow()
        claim = scan.claimed_at
        sections = {s['section_id']: s for s in scan.snapshot['sections']}
        pair_ids = [p.id for p in unresolved(rows(session, scan)) if p.classification is None][:PAIR_BATCH_LIMIT]
        session.commit()
    try:
        for pair_id in pair_ids:
            with factory() as session:
                pair = session.get(KnowledgeConflict, pair_id)
                left, right = sections[pair.left_id], sections[pair.right_id]
            def diagnostic(entry):
                with factory() as session:
                    session.add(SarvamCall(operation='conflict', metadata_json={**entry,
                        'repo_id': repo_id, 'scan_id': scan_id, 'conflict_id': pair_id}))
                    session.commit()
            assessment = assess(client, left, right, diagnostic)
            with factory() as session:
                scan = owned_scan(session, repo_id, scan_id, lock=True)
                if scan.state != 'SCANNING' or aware(scan.claimed_at) != claim:
                    raise ConflictError('Conflict scan lease changed; refresh before continuing')
                pair = session.get(KnowledgeConflict, pair_id)
                pair.classification = assessment.classification
                pair.uncertain = assessment.uncertain
                pair.assessment = assessment.model_dump()
                pair.assessed_at = utcnow()
                session.add(AuditEvent(kind='knowledge_conflict_assessed', payload={'repo_id': repo_id,
                    'scan_id': scan_id, 'conflict_id': pair_id, 'classification': pair.classification,
                    'uncertain': pair.uncertain}))
                session.commit()
        with factory() as session:
            scan = owned_scan(session, repo_id, scan_id, lock=True)
            if scan.state != 'SCANNING' or aware(scan.claimed_at) != claim:
                raise ConflictError('Conflict scan lease changed before completion')
            scan.state = review_state(rows(session, scan))
            scan.completed_at = None if scan.state == 'PENDING' else utcnow()
            session.commit()
            return scan.state
    except Exception as exc:
        with factory() as session:
            scan = owned_scan(session, repo_id, scan_id, lock=True)
            if scan.state == 'SCANNING' and aware(scan.claimed_at) == claim:
                scan.state = 'ERROR'
                session.add(AuditEvent(kind='knowledge_conflict_scan_failed', payload={'repo_id': repo_id,
                    'scan_id': scan_id, 'error_type': type(exc).__name__}))
                session.commit()
        raise


def prepare_gate(engine, repo_id, source_commit, changed, *, parent_id, client=None):
    factory = session_factory(engine)
    with factory() as session:
        repo = session.get(Repository, repo_id)
        if repo.active_index_version_id != parent_id:
            raise ConflictError('Approved knowledge changed during verification; retry indexing')
        scan = stage_scan(session, repo, source_commit, changed)
        scan_id, state = scan.id, scan.state
        session.commit()
    if state in {'PENDING', 'ERROR'} and client is not None:
        state = scan_pending(engine, repo_id, scan_id, client)
    if state != 'READY':
        raise KnowledgeReviewPending('Knowledge activation waits for conflict scanning/resolution in Knowledge.')
    return scan_id


def resolve(session, repo_id, conflict_id, action, rationale, actor):
    pair = session.scalar(select(KnowledgeConflict).where(KnowledgeConflict.id == conflict_id,
        KnowledgeConflict.repo_id == repo_id))
    if pair is None:
        raise ValueError('Conflict belongs to another repository')
    scan = owned_scan(session, repo_id, pair.scan_id, lock=True)
    session.refresh(pair)  # Refresh after the scan lock serializes concurrent reviewers.
    if scan.state not in {'REVIEW_REQUIRED', 'PENDING', 'ERROR', 'READY'}:
        raise ValueError('This scan cannot be reviewed now')
    if session.get(Repository, repo_id).active_index_version_id != scan.parent_version_id:
        raise ConflictError('Conflict scan is stale; stage a new scan')
    if action not in ACTIONS or not rationale.strip() or not actor.strip():
        raise ValueError('Choose a resolution and record a human identity and rationale')
    if pair.resolution:
        prior = session.scalar(select(ConflictResolution).where(ConflictResolution.conflict_id == pair.id))
        if prior.action == action and prior.rationale == rationale.strip() and prior.actor == actor.strip():
            return prior
        raise ValueError('Resolution is already recorded; refresh the scan')
    pair.resolution = action
    entry = ConflictResolution(repo_id=repo_id, conflict_id=pair.id, action=action,
        rationale=rationale.strip(), actor=actor.strip())
    session.add(entry); session.flush()
    # Human exclusion can resolve multiple overlapping conflicts; no model chooses truth.
    scan.state = review_state(rows(session, scan))
    session.add(AuditEvent(kind='knowledge_conflict_resolved', payload={'repo_id': repo_id,
        'scan_id': scan.id, 'conflict_id': pair.id, 'resolution_id': entry.id,
        'action': action, 'reason': entry.rationale, 'actor': entry.actor}))
    session.flush()
    return entry


def activation_gate(session, repo, source_commit, changed, scan_id=None):
    scan = owned_scan(session, repo.id, scan_id, lock=True) if scan_id else stage_scan(session, repo, source_commit, changed)
    mode = scan.snapshot.get('mode', 'UPDATE')
    if mode == 'AUDIT':
        parent = session.get(KnowledgeVersion, repo.active_index_version_id) if repo.active_index_version_id else None
        if parent is None or parent.source_commit != source_commit or changed:
            raise ConflictError('Audit activation cannot introduce new documentation')
    if fingerprint(snapshot(session, repo, source_commit, changed, mode=mode)) != scan.fingerprint:
        raise ConflictError('Conflict evidence does not match this activation snapshot')
    pairs = rows(session, scan)
    if scan.state != 'READY' or unresolved(pairs):
        raise KnowledgeReviewPending('Unresolved knowledge conflicts block activation')
    excluded = exclusions(pairs)
    if not {s['section_id'] for s in scan.snapshot['sections']} - excluded:
        raise ValueError('Cannot activate an empty trusted knowledge snapshot')
    return scan, excluded


def audit_current(engine, repo_id):
    with session_factory(engine)() as session:
        repo = session.get(Repository, repo_id)
        parent = session.get(KnowledgeVersion, repo.active_index_version_id) if repo and repo.active_index_version_id else None
        if parent is None:
            raise ValueError('No approved knowledge to audit')
        scan = stage_scan(session, repo, parent.source_commit, [], mode='AUDIT')
        session.commit()
        return scan.id


def activate_audit(engine, repo_id, scan_id):
    from docsync.web.indexing import replace_approved_sections
    with session_factory(engine)() as session:
        repo = session.get(Repository, repo_id)
        scan = owned_scan(session, repo_id, scan_id, lock=True)
        if scan.state == 'ACTIVATED':
            return scan.activated_version_id
        if scan.snapshot.get('mode') != 'AUDIT':
            raise ValueError('Baseline/release scans must resume their original verified operation')
        # No changed sections: preserve all approved vectors/provenance except human exclusions.
        version = replace_approved_sections(session, repo, scan.source_commit, [], None, conflict_scan_id=scan_id)
        session.add(AuditEvent(kind='knowledge_integrity_audit_activated', payload={'repo_id': repo_id,
            'scan_id': scan_id, 'version_id': version.id, 'source_commit': scan.source_commit}))
        session.commit()
        return version.id
