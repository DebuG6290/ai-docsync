"""Repository identity and session boundaries for the shared workspace."""
from dataclasses import replace
from sqlalchemy import select
from docsync.web.models import Repository, ChangeCase, Proposal, SectionAssessment


def repositories(session):
    return session.scalars(select(Repository).order_by(Repository.created_at, Repository.id)).all()


def select_repository(rows, state, default_name):
    by_id = {r.id: r for r in rows}
    chosen = state.get('repository_id')
    if chosen not in by_id:
        chosen = next((r.id for r in rows if r.full_name.casefold() == default_name.casefold()), rows[0].id if rows else None)
        state['repository_id'] = chosen
    return by_id.get(chosen)


def switch_repository(state, repo_id):
    # Preserve authentication/navigation only. Unsaved inputs are never reused in another repo.
    for key in list(state):
        if key not in {'authenticated', 'page', 'repository_id'}:
            del state[key]
    state['repository_id'] = repo_id


def scoped_settings(settings, repo):
    return replace(settings, repository=repo.full_name, monitored_branch=repo.monitored_branch,
        github_installation_id=repo.installation_id)


def require_review_owner(session, repo_id, record_id, *, section=False):
    row = session.get(SectionAssessment if section else Proposal, record_id)
    case = session.get(ChangeCase, row.case_id) if row else None
    if case is None or case.repo_id != repo_id:
        raise ValueError('This review does not belong to the selected repository')
    return row
