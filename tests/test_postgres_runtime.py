"""Real pgvector integration: CI uses a free ephemeral PostgreSQL container."""
import os
import pytest
from sqlalchemy import text, select
from alembic import command
from alembic.config import Config

from docsync.web.database import make_engine, session_factory
from docsync.web.models import Repository, uid
from docsync.web.indexing import IndexInput, replace_approved_sections, retrieve


@pytest.mark.skipif(not os.getenv('DOCSYNC_TEST_POSTGRES_URL'), reason='No ephemeral PostgreSQL configured locally')
def test_real_postgres_migration_vector_retrieval_and_rollback(monkeypatch):
    url = os.environ['DOCSYNC_TEST_POSTGRES_URL']
    monkeypatch.setenv('DATABASE_URL', url)
    command.upgrade(Config('alembic.ini'), 'head')
    command.upgrade(Config('alembic.ini'), 'head')
    engine = make_engine(url)
    class Embedder:
        def embed(self, text): return [1.0] + [0.0] * 383
    with session_factory(engine)() as session:
        assert session.scalar(text("SELECT extname FROM pg_extension WHERE extname = 'vector'")) == 'vector'
        repo = Repository(full_name='integration/' + uid(), monitored_branch='master')
        session.add(repo); session.flush(); repo_id = repo.id
        version = replace_approved_sections(session, repo, 'a' * 40,
            [IndexInput('docs/a.md::a', 'docs/a.md', 'A', 'Approved text', 'a' * 40)], Embedder())
        selected, chunks = retrieve(session, repo, [1.0] + [0.0] * 383)
        assert selected.id == version.id and chunks[0].content == 'Approved text'
        session.rollback()
    with session_factory(engine)() as session:
        assert session.get(Repository, repo_id) is None
    engine.dispose()
