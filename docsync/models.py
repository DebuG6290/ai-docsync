from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


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


# Mechanical output bounds; never truncate replacement documentation or infer a decision.
ImpactNote = Annotated[str, Field(max_length=400)]


class SectionAnalysis(StrictModel):
    section_id: str
    decision: Decision
    proposed_text: str | None
    reason: str = Field(max_length=800)
    code_evidence: list[ImpactNote] = Field(max_length=8)
    evidence_completeness: EvidenceCompleteness
    missing_information: list[ImpactNote] = Field(max_length=8)
    safe_claims: list[ImpactNote] = Field(max_length=8)
    unsupported_claims: list[ImpactNote] = Field(max_length=8)


class ImpactResponse(StrictModel):
    summary: str = Field(max_length=600)
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

