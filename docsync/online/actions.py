"""Trusted Actions event plumbing. Never execute monitored repository code."""
import argparse
import json
import os
import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from docsync.online.operations import execute
from docsync.repository.git_reader import changed_paths, changed_python_symbols, read_file
from docsync.repository.markdown_sections import parse_sections
from docsync.web.config import get_settings
from docsync.web.database import make_engine, session_factory
from docsync.web.github import cloned_repository
from docsync.web.models import GitHubDelivery, Job, DocumentationRelease, IndexedSection, Repository, utcnow
from docsync.web.repository import ensure_repository, enqueue
from docsync.web.workflow import audit, approved_mappings


def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value) or value == "0" * 40:
        raise ValueError("A full nonzero Git commit SHA is required")
    return value


def event_input(settings, name, payload):
    if (payload.get('repository') or {}).get('full_name', '').casefold() != settings.repository.casefold():
        raise PermissionError("Event repository is outside the allowlist")
    if name == 'push':
        if payload.get('ref') != f'refs/heads/{settings.monitored_branch}':
            return None
        if payload.get('deleted'):
            return None
        return 'analyze_push', {'before_sha': sha(payload.get('before')), 'after_sha': sha(payload.get('after'))}
    if name == 'workflow_dispatch':
        inputs = payload.get('inputs') or {}
        return 'analyze_push', {'before_sha': sha(inputs.get('before_sha')), 'after_sha': sha(inputs.get('after_sha'))}
    if name == 'pull_request':
        pr = payload.get('pull_request') or {}
        if payload.get('action') != 'closed' or not pr.get('merged') or pr.get('base', {}).get('ref') != settings.monitored_branch:
            return None
        return 'activate_release', {'pr_number': int(pr['number']), 'merge_sha': sha(pr.get('merge_commit_sha'))}
    raise ValueError("Unsupported event")


def existing_analysis_job(engine, settings, data):
    """Manual recovery reuses a known push operation, never creates a new case."""
    key = f"push:{sha(data['before_sha'])}:{sha(data['after_sha'])}"
    with session_factory(engine)() as session:
        repo = session.scalar(select(Repository).where(Repository.full_name == settings.repository))
        job = session.scalar(select(Job).where(Job.repo_id == repo.id, Job.kind == 'analyze_push',
            Job.delivery_id == f'{repo.id}:{key}')) if repo else None
        if job is None or job.payload.get('before_sha') != data['before_sha'] or job.payload.get('after_sha') != data['after_sha']:
            raise ValueError('No existing analysis operation matches these commits')
        if job.status not in {'ERROR', 'PROCESSING', 'COMPLETED'}:
            raise ValueError('Manual recovery requires a failed or interrupted analysis')
        if job.status == 'PROCESSING':
            if job.claimed_at and job.claimed_at.replace(tzinfo=utcnow().tzinfo) > utcnow() - timedelta(minutes=30):
                raise ValueError('Operation is already running')
        return job.id


def register(engine, settings, kind, data, *, run_url='', run_id=''):
    factory = session_factory(engine)
    key = (f"push:{data['before_sha']}:{data['after_sha']}" if kind == 'analyze_push' else
        f"index:{data['pr_number']}:{data['merge_sha']}" if kind == 'activate_release' else f"baseline:{data['baseline_sha']}")
    with factory() as session:
        repo = ensure_repository(session, settings)
        session.flush()
        # Serializes registration even when different Actions run IDs replay one event.
        from docsync.web.models import Repository
        session.scalar(select(Repository).where(Repository.id == repo.id).with_for_update())
        key = f'{repo.id}:{key}'
        prior = session.get(GitHubDelivery, key)
        if prior:
            return session.scalar(select(Job.id).where(Job.delivery_id == key))
        if kind == 'activate_release':
            release = session.scalar(select(DocumentationRelease).where(
                DocumentationRelease.repo_id == repo.id, DocumentationRelease.pr_number == data['pr_number']))
            if release is None:
                audit(session, 'unregistered_merge_ignored', data)
                session.commit()
                return None
        session.add(GitHubDelivery(delivery_id=key, repo_id=repo.id, event_name=kind, status='QUEUED'))
        session.flush()
        job = Job(repo_id=repo.id, delivery_id=key, kind=kind, payload=data)
        session.add(job)
        session.flush()
        audit(session, 'action_received', {'job_id': job.id, 'run_url': run_url, 'run_id': run_id, **data})
        session.commit()
        return job.id


def prepare_push(engine, settings, data):
    """Complete Git diff and approved-context check; no semantic impact rules."""
    with cloned_repository(settings.repository, settings.github_token, data['before_sha'], data['after_sha']) as (root, git, env):
        changes = changed_python_symbols(root, data['before_sha'], data['after_sha'])
        data['changed_paths'] = changed_paths(root, data['before_sha'], data['after_sha'])
        data['commits'] = git('log', '--format=%H %s', f"{data['before_sha']}..{data['after_sha']}")
        with session_factory(engine)() as session:
            repo = ensure_repository(session, settings)
            if not changes:
                audit(session, 'analysis_skipped_no_supported_symbols', data)
                session.commit()
                return False
            if not repo.active_index_version_id:
                raise ValueError("Initialize the approved baseline before code analysis")
            mappings = approved_mappings(session, repo.id)
            data['approved_documentation_commits'] = {}
            candidate_ids = {m['section_id'] for m in mappings if m['code_id'] in {c.code_id for c in changes}}
            for sid in candidate_ids:
                chunks = session.scalars(select(IndexedSection).where(
                    IndexedSection.version_id == repo.active_index_version_id, IndexedSection.section_id == sid)
                    .order_by(IndexedSection.chunk_index)).all()
                if not chunks:
                    raise ValueError(f"Candidate has no approved context: {sid}")
                source = read_file(root, data['after_sha'], chunks[0].path)
                section = next((s for s in parse_sections(chunks[0].path, source or '') if s.section_id == sid), None)
                if section is None or section.text != ''.join(c.content for c in chunks):
                    audit(session, 'approved_context_conflict', {'section_id': sid, **data})
                    session.commit()
                    raise ValueError("Candidate documentation differs from the active approved context")
                data['approved_documentation_commits'][sid] = chunks[0].source_commit
            session.commit()
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['analysis', 'index'], required=True)
    parser.add_argument('--baseline-sha', default='')
    parser.add_argument('--retry', action='store_true')
    args = parser.parse_args()
    settings = get_settings()
    if not settings.database_url.startswith(('postgres://', 'postgresql')):
        raise ValueError("Hosted Actions requires PostgreSQL")
    engine = make_engine(settings.database_url)
    recovery = not args.baseline_sha and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
    if recovery and (args.mode != 'analysis' or not args.retry):
        raise ValueError('Manual analysis recovery requires explicit --retry')
    if args.baseline_sha:
        if args.mode != 'index':
            raise ValueError("Baseline is an indexing operation")
        kind, data = 'index_baseline', {'baseline_sha': sha(args.baseline_sha)}
    else:
        event = event_input(settings, os.environ['GITHUB_EVENT_NAME'], json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text()))
        if not event:
            return
        kind, data = event
        if (args.mode == 'analysis') != (kind == 'analyze_push'):
            raise ValueError("Event does not match workflow")
    url = f"https://github.com/{settings.repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    job_id = (existing_analysis_job(engine, settings, data) if recovery else
        register(engine, settings, kind, data, run_url=url, run_id=os.environ['GITHUB_RUN_ID']))
    if not job_id:
        return
    # Replays check durable completion before spending on Git/model work.
    with session_factory(engine)() as session:
        if session.get(Job, job_id).status == 'COMPLETED':
            return
    if kind == 'analyze_push':
        try:
            supported = prepare_push(engine, settings, data)
        except Exception as exc:
            with session_factory(engine)() as session:
                session.get(Job, job_id).status = 'ERROR'
                audit(session, 'action_preparation_failed', {'job_id': job_id, 'run_url': url, 'error_type': type(exc).__name__})
                session.commit()
            raise
        if not supported:
            with session_factory(engine)() as session:
                session.get(Job, job_id).status = 'COMPLETED'
                session.commit()
            return
    if kind == 'analyze_push':
        with session_factory(engine)() as session:
            session.get(Job, job_id).payload = dict(data)
            audit(session, 'git_context_prepared', {'job_id': job_id, **data})
            session.commit()
    execute(engine, settings, job_id, run_url=url, retry=args.retry)


if __name__ == '__main__':
    main()
