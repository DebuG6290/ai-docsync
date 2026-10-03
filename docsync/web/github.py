from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

import httpx
import jwt

from docsync.web.config import Settings

API_ROOT = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


def valid_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


class GitHubClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        self.http = http or httpx.Client(timeout=30.0)
        self._owned_http = http is None

    def close(self) -> None:
        if self._owned_http:
            self.http.close()

    def installation_token(self, installation_id: int, *, require_writes=False) -> str:
        if not self.settings.github_app_id or not self.settings.github_private_key:
            raise GitHubError("GitHub App credentials are not configured")
        now = int(time.time())
        app_jwt = jwt.encode(
            {"iat": now - 30, "exp": now + 8 * 60, "iss": self.settings.github_app_id},
            self.settings.github_private_key,
            algorithm="RS256",
        )
        response = self.http.post(
            f"{API_ROOT}/app/installations/{installation_id}/access_tokens",
            headers=_headers(app_jwt),
        )
        if response.is_error:
            raise GitHubError(f"GitHub token exchange failed with HTTP {response.status_code}")
        if require_writes:
            permissions = response.json().get('permissions', {})
            if permissions.get('contents') != 'write' or permissions.get('pull_requests') != 'write':
                raise GitHubError('The GitHub App installation needs the existing contents and pull requests write permissions for approved publication')
        token = response.json().get("token")
        if not isinstance(token, str) or not token:
            raise GitHubError("GitHub returned an invalid installation token response")
        return token

    def request(self, method: str, path: str, token: str, **kwargs) -> httpx.Response:
        response = self.http.request(method, f"{API_ROOT}{path}", headers=_headers(token), **kwargs)
        if response.is_error:
            raise GitHubError(f"GitHub API {method} {path} failed with HTTP {response.status_code}")
        return response

    def branch_sha(self, repository: str, branch: str, token: str) -> str:
        owner, name = repository.split("/", 1)
        ref = quote(f"heads/{branch}", safe="/")
        value = self.request("GET", f"/repos/{owner}/{name}/git/ref/{ref}", token).json()
        try:
            return value["object"]["sha"]
        except (KeyError, TypeError) as exc:
            raise GitHubError("GitHub returned an invalid branch reference") from exc

    def create_pull_request(
        self,
        repository: str,
        branch: str,
        base: str,
        case_id: str,
        token: str,
    ) -> tuple[int, str]:
        owner, name = repository.split("/", 1)
        existing = self.request(
            "GET", f"/repos/{owner}/{name}/pulls", token,
            params={"state": "all", "head": f"{owner}:{branch}", "base": base},
        ).json()
        if existing:
            return int(existing[0]["number"]), str(existing[0]["html_url"])
        payload = {
            "title": f"[DocSync] Approved documentation for case {case_id[:8]}",
            "head": branch,
            "base": base,
            "body": (
                f"Human-approved documentation update for DocSync case `{case_id}`.\n\n"
                "This PR contains only the documentation sections accepted in the review surface. "
                "Merging it activates the corresponding approved knowledge-index version."
            ),
        }
        value = self.request("POST", f"/repos/{owner}/{name}/pulls", token, json=payload).json()
        return int(value["number"]), str(value["html_url"])

    def file_at(self, repository: str, path: str, ref: str, token: str) -> str:
        owner, name = repository.split("/", 1)
        escaped = "/".join(quote(part, safe="") for part in path.split("/"))
        value = self.request(
            "GET", f"/repos/{owner}/{name}/contents/{escaped}", token, params={"ref": ref}
        ).json()
        if value.get("encoding") != "base64" or not isinstance(value.get("content"), str):
            raise GitHubError(f"GitHub did not return file content for {path}")
        try:
            return base64.b64decode(value["content"]).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubError(f"GitHub returned undecodable UTF-8 content for {path}") from exc


@contextmanager
def cloned_repository(repository: str, token: str, before_sha: str, after_sha: str):
    """Clone/fetch Git objects for parsing; repository code is never executed."""
    owner, name = repository.split("/", 1)
    remote = f"https://github.com/{owner}/{name}.git"
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env = os.environ.copy()
    env.update(
        GIT_TERMINAL_PROMPT="0",
        GIT_CONFIG_COUNT="1",
        GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
        GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {auth}",
    )
    with tempfile.TemporaryDirectory(prefix="docsync-git-") as directory:
        path = Path(directory) / "repo"

        def git(*args: str) -> str:
            result = subprocess.run(
                ["git", *args], cwd=path if path.exists() else directory,
                env=env, capture_output=True, text=True, check=False,
            )
            if result.returncode:
                detail = result.stderr.strip().splitlines()[-1:] or ["git command failed"]
                raise GitHubError(detail[0][:500])
            return result.stdout.strip()

        git("clone", "--filter=blob:none", "--no-checkout", remote, str(path))
        git("fetch", "--no-tags", "origin", before_sha)
        git("fetch", "--no-tags", "origin", after_sha)
        yield path, git, env
