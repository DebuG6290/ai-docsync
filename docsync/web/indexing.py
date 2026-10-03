from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from docsync.web.models import (
    ChangeCase,
    IndexedSection,
    KnowledgeVersion,
    Repository,
    uid,
)


@dataclass(frozen=True)
class IndexInput:
    section_id: str
    path: str
    heading: str
    content: str
    source_commit: str


def chunk_text(text: str, limit: int = 1800) -> list[str]:
    """Split one approved heading section into paragraph-preserving retrieval chunks."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for paragraph in text.splitlines(keepends=True):
        rest = paragraph
        while len(rest) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(rest[:limit])
            rest = rest[limit:]
        if current and len(current) + len(rest) > limit:
            chunks.append(current)
            current = ""
        current += rest
    if current:
        chunks.append(current)
    return chunks or [text]


def replace_approved_sections(
    session: Session,
    repository: Repository,
    source_commit: str,
    changed: list[IndexInput],
    embedder,
    *,
    case: ChangeCase | None = None,
    release=None,
) -> KnowledgeVersion:
    """Build a full immutable index snapshot, then switch the active pointer in one transaction."""
    changed_ids = {section.section_id for section in changed}
    staged: list[tuple[IndexInput, int, str, list[float]]] = []
    for section in changed:
        for chunk_index, chunk in enumerate(chunk_text(section.content)):
            staged.append((section, chunk_index, chunk, embedder.embed(chunk)))

    old_id = repository.active_index_version_id
    # Compare-and-swap prevents a concurrent activation from losing approved sections.
    switched = session.execute(update(Repository).where(
        Repository.id == repository.id,
        Repository.active_index_version_id == old_id,
    ).values(active_index_version_id=old_id))
    if switched.rowcount != 1:
        raise ValueError("The active index changed concurrently; retry indexing")
    old_sections = session.scalars(
        select(IndexedSection).where(IndexedSection.version_id == old_id)
    ).all() if old_id else []
    version = KnowledgeVersion(repo_id=repository.id, source_commit=source_commit, active=False)
    session.add(version)
    session.flush()
    for old in old_sections:
        if old.section_id in changed_ids:
            continue
        session.add(
            IndexedSection(
                version_id=version.id,
                section_id=old.section_id,
                chunk_index=old.chunk_index,
                path=old.path,
                heading=old.heading,
                content=old.content,
                source_commit=old.source_commit,
                embedding=list(old.embedding),
            )
        )
    for section, chunk_index, chunk, vector in staged:
        if len(vector) != 384:
            raise ValueError(f"Embedding model returned {len(vector)} dimensions; expected 384")
        session.add(
            IndexedSection(
                version_id=version.id,
                section_id=section.section_id,
                chunk_index=chunk_index,
                path=section.path,
                heading=section.heading,
                content=chunk,
                source_commit=section.source_commit,
                embedding=vector,
            )
        )
    if old_id:
        old_version = session.get(KnowledgeVersion, old_id)
        if old_version is not None:
            old_version.active = False
    version.active = True
    repository.active_index_version_id = version.id
    if case is not None:
        case.status = "INDEXED"
        if release is not None:
            release.status = "INDEXED"
            release.merged_sha = source_commit
    session.flush()
    return version


def prepared_embeddings(changed, embedder):
    """Run model initialization/inference before opening an activation transaction."""
    vectors = {chunk: embedder.embed(chunk) for section in changed for chunk in chunk_text(section.content)}

    class Prepared:
        def embed(self, text):
            return vectors[text]

    return Prepared()


def retrieve(session: Session, repository: Repository, vector: list[float], limit: int = 6) -> tuple[KnowledgeVersion, list[IndexedSection]]:
    version_id = repository.active_index_version_id
    if not version_id:
        raise ValueError("The approved documentation index has not been initialized")
    version = session.get(KnowledgeVersion, version_id)
    if version is None or not version.active:
        raise ValueError("The active documentation index pointer is invalid")
    query = select(IndexedSection).where(IndexedSection.version_id == version_id)
    if session.get_bind().dialect.name == "postgresql":
        rows = session.scalars(
            query.order_by(IndexedSection.embedding.cosine_distance(vector)).limit(limit)
        ).all()
    else:
        rows = session.scalars(query).all()
        rows.sort(key=lambda row: _cosine_distance(vector, list(row.embedding)))
        rows = rows[:limit]
    return version, rows


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)
