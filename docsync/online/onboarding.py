"""Explicit repository setup; no remote writes, automatic mappings, or trusted baseline."""
import re
from pathlib import Path
from sqlalchemy import select, func
from docsync.engine import suggest_mappings
from docsync.repository.git_reader import read_file
from docsync.repository.markdown_sections import parse_sections, to_doc_section
from docsync.repository.python_symbols import extract_symbols
from docsync.web.github import GitHubClient, cloned_repository
from docsync.web.models import Repository, CodeDocMapping, SarvamCall
from docsync.web.workflow import audit


def repository_name(value):
    value = value.strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+', value) or value.split('/')[1] in {'.', '..'}:
        raise ValueError('Enter a GitHub repository as owner/repo')
    return value


def verify_access(settings, name, branch, installation_id):
    name = repository_name(name)
    if not branch.strip() or installation_id <= 0:
        raise ValueError('Enter a monitored branch and a positive GitHub App installation ID')
    github = GitHubClient(settings)
    try:
        token = github.installation_token(installation_id, require_writes=True)
        metadata = github.request('GET', f'/repos/{name}', token).json()
        canonical = repository_name(metadata['full_name'])
        if canonical.casefold() != name.casefold():
            raise ValueError('GitHub returned a different repository')
        commit = github.branch_sha(canonical, branch.strip(), token)
        from docsync.online.actions import sha
        return {'name': canonical, 'branch': branch.strip(), 'installation_id': installation_id, 'sha': sha(commit)}
    finally:
        github.close()


def connect_repository(session, verified):
    name = repository_name(verified['name'])
    existing = session.scalar(select(Repository).where(func.lower(Repository.full_name) == name.casefold()))
    if existing:
        # Reconnection never changes a working repository's branch, installation, or knowledge.
        return existing
    repo = Repository(full_name=name, monitored_branch=verified['branch'], installation_id=verified['installation_id'])
    session.add(repo)
    session.flush()
    audit(session, 'repository_connected', {'repo_id': repo.id, 'repository': repo.full_name,
        'monitored_branch': repo.monitored_branch, 'installation_id': repo.installation_id})
    session.commit()
    return repo


def discover(settings, repo, *, code_paths=(), doc_paths=(), commit=None):
    github = GitHubClient(settings)
    try:
        if not repo.installation_id:
            raise ValueError('Validate the GitHub App installation before discovery')
        token = github.installation_token(repo.installation_id)
        from docsync.online.actions import sha
        commit = sha(commit or github.branch_sha(repo.full_name, repo.monitored_branch, token))
        with cloned_repository(repo.full_name, token, commit, commit) as (root, git, _env):
            files = git('ls-tree', '-r', '--name-only', commit).splitlines()
            if len(code_paths) > 10 or len(doc_paths) > 15:
                raise ValueError('Inspect at most 10 Python files and 15 documentation files per batch')
            symbols, sections, skipped = [], [], []
            for path in [*code_paths, *doc_paths]:
                if path not in files or not path.endswith('.py' if path in code_paths else '.md'):
                    raise ValueError('Choose paths from the discovered repository structure')
                source = read_file(root, commit, path)
                if source is None or len(source) > 120000:
                    raise ValueError('A selected file is unavailable or too large; choose a smaller batch')
                if path in code_paths:
                    try:
                        symbols.extend(vars(s) for s in extract_symbols(path, source).values())
                    except ValueError:
                        skipped.append(path)
                else:
                    sections.extend(to_doc_section(s).model_dump() for s in parse_sections(path, source))
            return {'repo_id': repo.id, 'sha': commit, 'files': files, 'symbols': symbols,
                'sections': sections, 'skipped': skipped}
    finally:
        github.close()


def require_snapshot(repo_id, snapshot):
    if snapshot.get('repo_id') != repo_id:
        raise ValueError('Discovery belongs to another repository')


def mapping_suggestions(session, repo_id, snapshot, client):
    require_snapshot(repo_id, snapshot)
    if not snapshot['symbols'] or not snapshot['sections']:
        raise ValueError('Choose Python symbols and documentation sections first')
    if len(snapshot['symbols']) > 30 or len(snapshot['sections']) > 30:
        raise ValueError('Choose at most 30 symbols and 30 sections for one suggestion batch')

    class Diagnostics:
        def event(self, kind, entry):
            session.add(SarvamCall(operation='mapping', metadata_json={**entry, 'repo_id': repo_id}))

    try:
        suggestions = suggest_mappings(client, snapshot['symbols'], snapshot['sections'], Diagnostics())
        audit(session, 'mapping_suggestions_generated', {'repo_id': repo_id, 'source_commit': snapshot['sha'], 'count': len(suggestions)})
        session.commit()
        return suggestions
    except Exception:
        session.commit()  # Preserve model diagnostics without approving any mappings.
        raise


def confirm_mapping(session, repo_id, snapshot, code_id, section_id, reason):
    require_snapshot(repo_id, snapshot)
    if session.get(Repository, repo_id) is None:
        raise ValueError('Unknown repository')
    if code_id not in {s['code_id'] for s in snapshot['symbols']} or section_id not in {s['section_id'] for s in snapshot['sections']}:
        raise ValueError('Mapping identities must exist in the inspected source commit')
    if not reason.strip():
        raise ValueError('Record a reason for confirming this mapping')
    existing = session.scalar(select(CodeDocMapping).where(CodeDocMapping.repo_id == repo_id,
        CodeDocMapping.code_id == code_id, CodeDocMapping.section_id == section_id))
    if existing:
        return existing
    mapping = CodeDocMapping(repo_id=repo_id, code_id=code_id, section_id=section_id, reason=reason.strip(), status='APPROVED')
    session.add(mapping)
    session.flush()
    audit(session, 'mapping_confirmed', {'repo_id': repo_id, 'mapping_id': mapping.id,
        'code_id': code_id, 'section_id': section_id, 'source_commit': snapshot['sha'], 'reason': reason.strip()})
    session.commit()
    return mapping


def release_sha():
    # Resolve only this checkout; never infer a release from the monitored repository.
    import subprocess
    value = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, check=True).stdout.strip()
    from docsync.online.actions import sha
    return sha(value)


def workflow_files(branch, release):
    from docsync.online.actions import sha
    import json
    release = sha(release)
    if not branch.strip() or '\n' in branch:
        raise ValueError('A monitored branch is required')
    base = Path(__file__).resolve().parents[2] / 'integrations' / 'httpx'
    files = {}
    for name in ['docsync-analysis.yml', 'docsync-index.yml']:
        text = (base / name).read_text(encoding='utf-8')
        text = re.sub(r'@([0-9a-f]{40})', '@' + release, text)
        text = re.sub(r'application_ref: [0-9a-f]{40}', 'application_ref: ' + release, text)
        text = text.replace('branches: [master]', 'branches: [' + json.dumps(branch) + ']')
        text = text.replace('monitored_branch: master', 'monitored_branch: ' + json.dumps(branch))
        text = re.sub(r'^\s+default: [0-9a-f]{40}\n', '\n', text, flags=re.M)
        text = text.replace('same reviewed batched-analysis release.', 'same reviewed application release.')
        files['.github/workflows/' + name] = text
    return files
