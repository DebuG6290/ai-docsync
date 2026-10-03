from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from docsync.web.config import Settings
from docsync.web.models import CodeDocMapping, GitHubDelivery, Job, Repository, uid


def ensure_repository(
    session: Session, settings: Settings, installation_id: int | None = None
) -> Repository:
    if not settings.repository:
        raise ValueError("DOCSYNC_REPOSITORY is not configured")
    repository = session.scalar(
        select(Repository).where(func.lower(Repository.full_name) == settings.repository.casefold())
    )
    if repository is None:
        repository = Repository(
            full_name=settings.repository,
            monitored_branch=settings.monitored_branch,
            installation_id=installation_id or settings.github_installation_id,
        )
        session.add(repository)
        session.flush()
    else:
        repository.monitored_branch = settings.monitored_branch
        if installation_id:
            repository.installation_id = installation_id
    _seed_mappings(session, repository)
    return repository


def _seed_mappings(session: Session, repository: Repository) -> None:
    if repository.full_name.casefold() != 'debug6290/httpx':
        return
    path = Path(__file__).resolve().parents[2] / "config" / "httpx-mappings.json"
    for item in json.loads(path.read_text(encoding="utf-8")):
        exists = session.scalar(
            select(CodeDocMapping.id).where(
                CodeDocMapping.repo_id == repository.id,
                CodeDocMapping.code_id == item["code_id"],
                CodeDocMapping.section_id == item["section_id"],
                CodeDocMapping.version == 1,
            )
        )
        if exists is None:
            session.add(CodeDocMapping(repo_id=repository.id, **item, version=1))


def _push_paths(payload: dict) -> tuple[list[str], list[str]]:
    paths: list[str] = []
    messages: list[str] = []
    for commit in payload.get("commits") or []:
        messages.append(str(commit.get("message", "")))
        for key in ("added", "modified", "removed"):
            paths.extend(str(path) for path in (commit.get(key) or []))
    return paths, messages


def accept_delivery(
    session: Session,
    settings: Settings,
    delivery_id: str,
    event_name: str,
    payload: dict,
) -> tuple[str, bool]:
    """Persist only allowlisted event metadata and enqueue work once."""
    existing = session.get(GitHubDelivery, delivery_id)
    if existing is not None:
        return existing.status, True
    event_repo = (payload.get("repository") or {}).get("full_name")
    if not settings.repository or not isinstance(event_repo, str) or event_repo.casefold() != settings.repository.casefold():
        raise PermissionError("Repository is outside the configured allowlist")
    installation_id = (payload.get("installation") or {}).get("id")
    repository = ensure_repository(
        session, settings, int(installation_id) if installation_id is not None else None
    )
    # Serialize delivery processing per configured repository so concurrent redeliveries
    # with the same commit range cannot both enqueue analysis jobs.
    repository = session.scalar(
        select(Repository).where(Repository.id == repository.id).with_for_update()
    )
    existing = session.get(GitHubDelivery, delivery_id)
    if existing is not None:
        return existing.status, True
    action = payload.get("action")
    before_sha = after_sha = ref = None
    status = "IGNORED"
    job_kind = None
    job_payload: dict = {}

    if event_name == "push":
        ref = payload.get("ref")
        before_sha = payload.get("before")
        after_sha = payload.get("after")
        expected_ref = f"refs/heads/{repository.monitored_branch}"
        paths, _messages = _push_paths(payload)
        documentation_only = bool(paths) and all(path.lower().endswith(".md") for path in paths)
        if ref == expected_ref and before_sha and after_sha and before_sha != after_sha and not documentation_only:
            prior_push = session.scalar(
                select(GitHubDelivery.delivery_id).where(
                    GitHubDelivery.repo_id == repository.id,
                    GitHubDelivery.event_name == "push",
                    GitHubDelivery.ref == ref,
                    GitHubDelivery.before_sha == before_sha,
                    GitHubDelivery.after_sha == after_sha,
                ).limit(1)
            )
            if prior_push:
                status = "DUPLICATE_CHANGE"
            else:
                status = "QUEUED"
                job_kind = "analyze_push"
                job_payload = {"before_sha": before_sha, "after_sha": after_sha, "ref": ref}
        elif ref == expected_ref and documentation_only:
            status = "IGNORED_DOCUMENTATION_ONLY"
    elif event_name == "pull_request" and action == "closed":
        pr = payload.get("pull_request") or {}
        base = (pr.get("base") or {}).get("ref")
        head = (pr.get("head") or {}).get("ref", "")
        if pr.get("merged") and base == repository.monitored_branch and head.startswith("docsync/case-"):
            status = "QUEUED"
            job_kind = "activate_release"
            job_payload = {
                "pr_number": int(pr["number"]),
                "merge_sha": pr.get("merge_commit_sha"),
            }

    event = GitHubDelivery(
        delivery_id=delivery_id,
        repo_id=repository.id,
        event_name=event_name,
        action=str(action) if action is not None else None,
        before_sha=str(before_sha) if before_sha else None,
        after_sha=str(after_sha) if after_sha else None,
        ref=str(ref) if ref else None,
        status=status,
    )
    session.add(event)
    session.flush()
    if job_kind:
        session.add(
            Job(
                delivery_id=delivery_id,
                repo_id=repository.id,
                kind=job_kind,
                payload=job_payload,
            )
        )
    session.commit()
    return status, False


def enqueue(session: Session, repo_id: str, kind: str, payload: dict) -> str:
    job = Job(id=uid(), repo_id=repo_id, kind=kind, payload=payload)
    session.add(job)
    session.flush()
    return job.id
