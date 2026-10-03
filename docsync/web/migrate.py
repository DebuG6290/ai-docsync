from __future__ import annotations

from docsync.web.config import get_settings
from docsync.web.database import initialize_database, make_engine, session_factory
from docsync.web.repository import ensure_repository


def main() -> None:
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    settings = get_settings()
    engine = make_engine(settings.database_url)
    command.upgrade(Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini')), 'head')
    if settings.repository:
        with session_factory(engine)() as session:
            ensure_repository(session, settings, settings.github_installation_id)
            session.commit()


if __name__ == "__main__":
    main()
