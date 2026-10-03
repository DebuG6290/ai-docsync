from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class Decision(str, Enum):
    UPDATE = "UPDATE"
    NO_CHANGE = "NO_CHANGE"
    UNCERTAIN = "UNCERTAIN"


class EvidenceCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class SectionAnalysis(StrictModel):
    section_id: str
    decision: Decision
    proposed_text: str | None
    reason: str
    code_evidence: list[str]
    evidence_completeness: EvidenceCompleteness
    missing_information: list[str]
    safe_claims: list[str]
    unsupported_claims: list[str]


class ImpactResponse(StrictModel):
    summary: str
    sections: list[SectionAnalysis]


class RevisionResponse(StrictModel):
    section_id: str
    proposed_text: str
    reason: str
    code_evidence: list[str]
    evidence_completeness: EvidenceCompleteness
    missing_information: list[str]
    safe_claims: list[str]
    unsupported_claims: list[str]


class MappingCandidate(StrictModel):
    code_id: str
    section_id: str
    reason: str


class MappingSuggestionResponse(StrictModel):
    suggestions: list[MappingCandidate]


class CodeChange(StrictModel):
    code_id: str
    path: str
    name: str
    kind: str
    old_code: str | None = None
    new_code: str | None = None
    diff: str
    change_kind: Literal["added", "modified", "deleted"]


class DocSection(StrictModel):
    section_id: str
    path: str
    heading: str
    text: str
    sha256: str

