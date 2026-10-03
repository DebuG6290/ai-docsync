from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "repositories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    full_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    monitored_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    installation_id: Mapped[int | None] = mapped_column(Integer)
    active_index_version_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GitHubDelivery(Base):
    __tablename__ = "github_deliveries"
    delivery_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    event_name: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str | None] = mapped_column(String(40))
    before_sha: Mapped[str | None] = mapped_column(String(64))
    after_sha: Mapped[str | None] = mapped_column(String(64))
    ref: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="RECEIVED", nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    delivery_id: Mapped[str | None] = mapped_column(ForeignKey("github_deliveries.delivery_id"))
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CodeDocMapping(Base):
    __tablename__ = "code_doc_mappings"
    __table_args__ = (UniqueConstraint("repo_id", "code_id", "section_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    code_id: Mapped[str] = mapped_column(String(512), nullable=False)
    section_id: Mapped[str] = mapped_column(String(512), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="APPROVED", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChangeCase(Base):
    __tablename__ = "change_cases"
    __table_args__ = (UniqueConstraint("repo_id", "before_sha", "after_sha"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    delivery_id: Mapped[str | None] = mapped_column(ForeignKey("github_deliveries.delivery_id"), unique=True)
    before_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    after_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ANALYZING", nullable=False)
    decision: Mapped[str | None] = mapped_column(String(24))
    summary: Mapped[str | None] = mapped_column(Text)
    case_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    documentation_pr_number: Mapped[int | None] = mapped_column(Integer)
    documentation_pr_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SectionAssessment(Base):
    __tablename__ = "section_assessments"
    __table_args__ = (UniqueConstraint("case_id", "section_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("change_cases.id"), nullable=False)
    section_id: Mapped[str] = mapped_column(String(512), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    heading: Mapped[str] = mapped_column(Text, nullable=False)
    current_text: Mapped[str] = mapped_column(Text, nullable=False)
    base_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_completeness: Mapped[str] = mapped_column(String(24), nullable=False)
    code_evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    missing_information: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    safe_claims: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    unsupported_claims: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    proposed_text: Mapped[str | None] = mapped_column(Text)
    human_resolution: Mapped[str | None] = mapped_column(String(24))
    triage_reason: Mapped[str | None] = mapped_column(Text)


class SarvamCall(Base):
    __tablename__ = "sarvam_calls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("change_cases.id"))
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (UniqueConstraint("case_id", "section_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("change_cases.id"), nullable=False)
    section_id: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    accepted_version_id: Mapped[str | None] = mapped_column(String(36))
    applied_sha256: Mapped[str | None] = mapped_column(String(64))


class ProposalVersion(Base):
    __tablename__ = "proposal_versions"
    __table_args__ = (UniqueConstraint("proposal_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    author: Mapped[str] = mapped_column(String(40), nullable=False)
    human_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    proposed_text: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    code_evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    evidence_completeness: Mapped[str | None] = mapped_column(String(24))
    missing_information: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    safe_claims: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    unsupported_claims: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewAction(Base):
    __tablename__ = "review_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    version_id: Mapped[str | None] = mapped_column(String(36))
    reason: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("change_cases.id"))
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentationRelease(Base):
    __tablename__ = "documentation_releases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("change_cases.id"), unique=True, nullable=False)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pr_url: Mapped[str] = mapped_column(Text, nullable=False)
    merged_sha: Mapped[str | None] = mapped_column(String(64))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    index_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="PENDING_MERGE", nullable=False)


class ReleaseSection(Base):
    __tablename__ = "release_sections"
    __table_args__ = (UniqueConstraint("release_id", "section_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    release_id: Mapped[str] = mapped_column(ForeignKey("documentation_releases.id"), nullable=False)
    section_id: Mapped[str] = mapped_column(String(512), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class KnowledgeVersion(Base):
    __tablename__ = "knowledge_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    source_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IndexedSection(Base):
    __tablename__ = "indexed_sections"
    __table_args__ = (UniqueConstraint("version_id", "section_id", "chunk_index"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    version_id: Mapped[str] = mapped_column(ForeignKey("knowledge_versions.id"), nullable=False)
    section_id: Mapped[str] = mapped_column(String(512), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    heading: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)


class ChatTurn(Base):
    __tablename__ = "chat_turns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    knowledge_version_id: Mapped[str] = mapped_column(ForeignKey("knowledge_versions.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
