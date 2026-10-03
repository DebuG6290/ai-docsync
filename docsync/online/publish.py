"""Publish a durable approved snapshot with resumable GitHub writes."""
from sqlalchemy import select

from docsync.apply import apply_case
from docsync.errors import ConflictError
from docsync.repository.markdown_sections import parse_sections, section_sha256
from docsync.web.database import session_factory
from docsync.web.github import GitHubClient, cloned_repository
from docsync.web.models import ChangeCase, Repository, DocumentationRelease, ReleaseSection, Proposal, ProposalVersion, SectionAssessment, ReviewAction
from docsync.web.workflow import audit, local_store_from_online


def publish(engine, settings, case_id):
    if settings.github_token:
        raise PermissionError("Publication requires the fork-scoped GitHub App, not the Actions read token")
    factory = session_factory(engine)
    github = GitHubClient(settings)
    try:
        with factory() as session:
            case = session.get(ChangeCase, case_id)
            if case is None:
                raise ValueError("Unknown case")
            repo = session.get(Repository, case.repo_id)
            repository, base, branch = repo.full_name, case.after_sha, repo.monitored_branch
            installation = repo.installation_id or settings.github_installation_id
            if not installation:
                raise ValueError("GitHub App installation is required")
            release = session.scalar(select(DocumentationRelease).where(DocumentationRelease.case_id == case_id))
            if release and release.pr_number:
                return
            prepared_id = release.id if release else None
        token = github.installation_token(installation)
        api = f'/repos/{repository}'
        if not prepared_id:
            if github.branch_sha(repository, branch, token) != base:
                raise ConflictError("Monitored branch advanced; review a fresh case")
            with cloned_repository(repository, token, base, base) as (root, git, env):
                git('checkout', '--detach', base)
                with factory() as session:
                    case = session.scalar(select(ChangeCase).where(ChangeCase.id == case_id).with_for_update())
                    proposals = session.scalars(select(Proposal).where(Proposal.case_id == case_id)).all()
                    if not proposals or any(p.status != 'ACCEPTED' or not p.accepted_version_id for p in proposals):
                        raise ValueError("Every proposal must have an explicitly accepted version")
                    assessments = session.scalars(select(SectionAssessment).where(SectionAssessment.case_id == case_id)).all()
                    if any(a.decision == 'UNCERTAIN' and not a.human_resolution for a in assessments):
                        raise ValueError("Resolve uncertainty before publishing")
                    local, local_case, ids = local_store_from_online(session, case, root)
                    accepted = {}
                    try:
                        for proposal in proposals:
                            version = session.get(ProposalVersion, proposal.accepted_version_id)
                            if version is None or version.proposal_id != proposal.id:
                                raise ValueError("Accepted version is invalid")
                            accepted[proposal.section_id] = (proposal.id, version.id)
                            local_id = ids[proposal.id]
                            local_version = next(v for v in local.versions(local_id) if v['version'] == version.version)
                            local.set_proposal_status(local_id, 'ACCEPTED', accepted_version_id=local_version['id'])
                        apply_case(local, local_case)
                    finally:
                        local.db.close()
                    changed = sorted({a.path for a in assessments if a.section_id in accepted})
                    if any(not path.startswith('docs/') or not path.endswith('.md') for path in changed):
                        raise ValueError("Publication paths must be Markdown documents under docs/")
                    snapshot = []
                    for assessment in assessments:
                        if assessment.section_id not in accepted:
                            continue
                        path = (root / assessment.path).resolve()
                        path.relative_to(root.resolve())
                        section = next(s for s in parse_sections(assessment.path, path.read_text(encoding='utf-8'))
                            if s.section_id == assessment.section_id)
                        snapshot.append((section, accepted[section.section_id]))
                    audit(session, 'approved_publication_snapshot', {'accepted_versions': accepted}, case_id)
                    case.status = 'PUBLISHING'
                    session.commit()
                # Git objects are immutable; no branch changes until the snapshot is durable.
                base_commit = github.request('GET', f'{api}/git/commits/{base}', token).json()
                tree = github.request('POST', f'{api}/git/trees', token, json={
                    'base_tree': base_commit['tree']['sha'], 'tree': [
                        {'path': path, 'mode': '100644', 'type': 'blob',
                         'content': (root / path).read_text(encoding='utf-8')} for path in changed]}).json()
                if tree['sha'] == base_commit['tree']['sha']:
                    raise ValueError("Approved documentation produces no diff")
                commit = github.request('POST', f'{api}/git/commits', token, json={
                    'message': f'[DocSync] Approved documentation\n\ndocsync-case:{case_id}',
                    'tree': tree['sha'], 'parents': [base]}).json()
                with factory() as session:
                    release = DocumentationRelease(case_id=case_id, repo_id=repo.id,
                        branch=f'codex/docsync/case-{case_id}', commit_sha=commit['sha'],
                        pr_number=0, pr_url='', status='PREPARED')
                    session.add(release)
                    session.flush()
                    prepared_id = release.id
                    for section, (proposal_id, version_id) in snapshot:
                        session.add(ReleaseSection(release_id=release.id, section_id=section.section_id,
                            path=section.path, text=section.text, sha256=section_sha256(section.text)))
                    audit(session, 'publication_prepared', {'release_id': release.id, 'commit_sha': release.commit_sha}, case_id)
                    session.commit()
        with factory() as session:
            release = session.get(DocumentationRelease, prepared_id)
            docs_branch, commit_sha = release.branch, release.commit_sha
        if github.branch_sha(repository, branch, token) != base:
            raise ConflictError("Monitored branch advanced before publication; manual reconciliation required")
        from urllib.parse import quote
        ref_path = f"{api}/git/ref/heads/{quote(docs_branch, safe='/')}"
        response = github.http.get('https://api.github.com' + ref_path,
            headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'})
        if response.status_code == 404:
            github.request('POST', f'{api}/git/refs', token, json={'ref': f'refs/heads/{docs_branch}', 'sha': commit_sha})
        elif response.is_error or response.json()['object']['sha'] != commit_sha:
            raise ConflictError("Publication branch differs from the durable approved snapshot")
        number, url = github.create_pull_request(repository, docs_branch, branch, case_id, token)
        with factory() as session:
            release = session.get(DocumentationRelease, prepared_id)
            release.pr_number, release.pr_url, release.status = number, url, 'PENDING_MERGE'
            case = session.get(ChangeCase, case_id)
            case.documentation_pr_number, case.documentation_pr_url, case.status = number, url, 'WAITING_MERGE'
            for proposal in session.scalars(select(Proposal).where(Proposal.case_id == case_id)).all():
                session.add(ReviewAction(proposal_id=proposal.id, action='DOCUMENTATION_PR_CREATED',
                    version_id=proposal.accepted_version_id, content=url))
            audit(session, 'documentation_pr_created', {'pr_number': number, 'pr_url': url, 'commit_sha': commit_sha}, case_id)
            session.commit()
    finally:
        github.close()
