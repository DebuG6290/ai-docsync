from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1)
    used_section_ids: list[str]
