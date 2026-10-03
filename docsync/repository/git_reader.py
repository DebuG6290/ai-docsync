from __future__ import annotations

import subprocess
from pathlib import Path

from docsync.errors import GitError
from docsync.models import CodeChange
from docsync.repository.python_symbols import Symbol, extract_symbols


def _git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8"
    )
    if check and proc.returncode:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def resolve_commit(repo: Path, rev: str) -> str:
    sha = _git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()
    if len(sha) != 40:
        raise GitError(f"Could not resolve commit {rev!r}")
    return sha


def read_file(repo: Path, rev: str, path: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{rev}:{path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.stdout if proc.returncode == 0 else None


def changed_python_symbols(repo: Path, old_sha: str, new_sha: str) -> list[CodeChange]:
    old_sha = resolve_commit(repo, old_sha)
    new_sha = resolve_commit(repo, new_sha)
    names = _git(repo, "diff", "--name-only", "--diff-filter=ACDMRT", old_sha, new_sha)
    changes: list[CodeChange] = []
    for path in sorted({item.strip().replace("\\", "/") for item in names.splitlines() if item.strip()}):
        if not path.endswith(".py"):
            continue
        before = read_file(repo, old_sha, path)
        after = read_file(repo, new_sha, path)
        try:
            old_symbols = extract_symbols(path, before) if before is not None else {}
            new_symbols = extract_symbols(path, after) if after is not None else {}
        except ValueError as exc:
            raise GitError(str(exc)) from exc
        diff = _git(repo, "diff", "--no-ext-diff", "--unified=5", old_sha, new_sha, "--", path)
        for code_id in sorted(old_symbols.keys() | new_symbols.keys()):
            old_sym = old_symbols.get(code_id)
            new_sym = new_symbols.get(code_id)
            if old_sym and new_sym and old_sym.source == new_sym.source:
                continue
            sym: Symbol = new_sym or old_sym  # type: ignore[assignment]
            kind = "added" if old_sym is None else "deleted" if new_sym is None else "modified"
            changes.append(
                CodeChange(
                    code_id=code_id,
                    path=path,
                    name=sym.name,
                    kind=sym.kind,
                    old_code=old_sym.source if old_sym else None,
                    new_code=new_sym.source if new_sym else None,
                    diff=diff,
                    change_kind=kind,
                )
            )
    return changes


def changed_paths(repo: Path, old_sha: str, new_sha: str) -> list[str]:
    names = _git(repo, "diff", "--name-only", old_sha, new_sha)
    return sorted(item.strip().replace("\\", "/") for item in names.splitlines() if item.strip())

