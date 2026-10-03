"""On-demand public GitHub status reconciliation for known approved releases."""
from sqlalchemy import select
import httpx
from docsync.web.models import DocumentationRelease, Repository, utcnow
from docsync.web.workflow import audit


def reconcile_release(factory, release_id, *, repo_id=None):
    with factory() as session:
        release = session.get(DocumentationRelease, release_id)
        if release is not None and repo_id is not None and release.repo_id != repo_id:
            raise ValueError('This release belongs to another repository')
        if release is None or not release.pr_number or release.status == 'INDEXED':
            return
        repo = session.get(Repository, release.repo_id)
        name, number, expected, branch = repo.full_name, release.pr_number, release.commit_sha, repo.monitored_branch
    # Public demo repositories need no App token for this limited read path.
    response = httpx.get(f'https://api.github.com/repos/{name}/pulls/{number}', timeout=8,
        headers={'Accept': 'application/vnd.github+json'})
    response.raise_for_status()
    pr = response.json()
    if pr.get('head', {}).get('sha') != expected or pr.get('base', {}).get('ref') != branch or pr.get('head', {}).get('repo', {}).get('full_name') != name:
        raise ValueError('GitHub PR identity differs from the approved release')
    with factory() as session:
        release = session.scalar(select(DocumentationRelease).where(DocumentationRelease.id == release_id).with_for_update())
        release.status_checked_at = utcnow()
        if release.status == 'INDEXED':
            session.commit(); return
        if pr.get('merged'):
            import re
            commit = pr.get('merge_commit_sha', '')
            if not re.fullmatch(r'[0-9a-f]{40}', commit):
                raise ValueError('GitHub did not return a merged commit')
            if not release.merged_sha:
                release.merged_sha = commit
                release.merged_at = utcnow()
                audit(session, 'documentation_merge_confirmed', {'pr_number': number, 'merged_sha': commit}, release.case_id)
            if release.status not in {'INDEXING', 'VERIFYING', 'INDEX_ERROR', 'INDEX_CONFLICT'}:
                release.status = 'MERGED'
        elif release.status not in {'INDEXING', 'VERIFYING', 'INDEX_ERROR', 'INDEX_CONFLICT'}:
            release.status = 'CLOSED' if pr.get('state') == 'closed' else 'PENDING_MERGE'
        session.commit()
