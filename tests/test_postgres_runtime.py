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


@pytest.mark.skipif(not os.getenv('DOCSYNC_TEST_POSTGRES_URL'), reason='No ephemeral PostgreSQL configured locally')
def test_real_postgres_conflict_deduplication_ownership_and_stale_activation(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.exc import IntegrityError
    from docsync.errors import ConflictError
    from docsync.knowledge.gate import stage_scan, scan_pending, resolve, rows
    from docsync.web.models import KnowledgeScan, KnowledgeConflict
    from test_knowledge_conflicts import inputs, Client, Embedder
    url = os.environ['DOCSYNC_TEST_POSTGRES_URL']
    monkeypatch.setenv('DATABASE_URL', url)
    command.upgrade(Config('alembic.ini'), 'head')
    engine = make_engine(url)
    factory = session_factory(engine)
    with factory() as session:
        repo = Repository(full_name='conflict-test/' + uid(), monitored_branch='main')
        other = Repository(full_name='other-test/' + uid(), monitored_branch='main')
        session.add_all([repo, other]); session.commit()
        repo_id, other_id = repo.id, other.id
    def stage():
        with factory() as session:
            scan = stage_scan(session, session.get(Repository, repo_id), 'a'*40, inputs())
            session.commit()
            return scan.id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: stage(), range(2)))
    assert ids[0] == ids[1]
    scan_id = ids[0]
    scan_pending(engine, repo_id, scan_id, Client('HARD_CONFLICT'))
    with factory() as stale, factory() as session:
        stale_repo = stale.get(Repository, repo_id)
        scan = session.get(KnowledgeScan, scan_id)
        pair = rows(session, scan)[0]
        resolve(session, repo_id, pair.id, 'PREFER_A', 'Reviewed source evidence.', 'human-test')
        session.commit()
        repo = session.get(Repository, repo_id)
        version = replace_approved_sections(session, repo, 'a'*40, inputs(), Embedder(), conflict_scan_id=scan_id)
        session.commit()
        _, chunks = retrieve(session, repo, [1.] + [0.] * 383)
        assert {s.section_id for s in chunks} == {'docs/guide.md::report-export', 'docs/auth.md::tokens'}
        with pytest.raises(ConflictError):
            replace_approved_sections(stale, stale_repo, 'a'*40, inputs(), Embedder())
        stale.rollback()
        session.add(KnowledgeConflict(repo_id=other_id, scan_id=scan_id, left_id='foreign', right_id='source'))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.get(Repository, repo_id).active_index_version_id == version.id
    engine.dispose()
