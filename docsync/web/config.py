from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    sarvam_api_key: str
    sarvam_model: str
    github_app_id: str
    github_private_key: str
    github_webhook_secret: str
    github_installation_id: int | None
    repository: str
    monitored_branch: str
    review_username: str
    review_password: str
    base_url: str
    embedding_model: str
    embedding_cache: str
    github_token: str = ""


def get_settings() -> Settings:
    # .env is a local convenience only; deployed secrets come from the host.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    private_key = os.getenv("GITHUB_PRIVATE_KEY", "")
    if not private_key and os.getenv("GITHUB_PRIVATE_KEY_BASE64"):
        import base64

        private_key = base64.b64decode(os.environ["GITHUB_PRIVATE_KEY_BASE64"]).decode()
    private_key = private_key.replace("\\n", "\n")
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./.docsync-state/online.sqlite3"),
        sarvam_api_key=os.getenv("SARVAM_API_KEY", ""),
        sarvam_model=os.getenv("SARVAM_MODEL", "sarvam-105b"),
        github_app_id=os.getenv("GITHUB_APP_ID", ""),
        github_private_key=private_key,
        github_webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET", ""),
        github_installation_id=(int(os.environ["GITHUB_INSTALLATION_ID"]) if os.getenv("GITHUB_INSTALLATION_ID") else None),
        repository=os.getenv("DOCSYNC_REPOSITORY", ""),
        monitored_branch=os.getenv("DOCSYNC_MONITORED_BRANCH", "master"),
        review_username=os.getenv("DOCSYNC_REVIEW_USERNAME", "admin"),
        review_password=os.getenv("DOCSYNC_REVIEW_PASSWORD", ""),
        base_url=os.getenv("DOCSYNC_BASE_URL", ""),
        embedding_model=os.getenv("DOCSYNC_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        embedding_cache=os.getenv("DOCSYNC_EMBEDDING_CACHE", str(Path(".docsync-state") / "embedding-cache")),
        github_token=os.getenv("GITHUB_TOKEN", ""),
    )
