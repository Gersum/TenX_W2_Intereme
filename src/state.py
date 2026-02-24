from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    id: str = Field(description="Stable evidence identifier.")
    goal: str = Field(description="Forensic objective for this check.")
    found: bool = Field(description="Whether the expected artifact or pattern was found.")
    content: str | None = Field(default=None, description="Optional structured or text payload.")
    location: str = Field(description="File path, commit hash, or source location.")
    rationale: str = Field(description="Why this evidence is considered reliable.")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score in [0, 1].")
    tags: list[str] = Field(default_factory=list, description="Evidence classification tags.")


class JudicialOpinion(BaseModel):
    judge: Literal["Prosecutor", "Defense", "TechLead"]
    criterion_id: str
    score: int = Field(ge=1, le=5)
    argument: str
    cited_evidence: list[str] = Field(default_factory=list)


class AgentState(TypedDict):
    repo_url: str
    pdf_path: str | None
    rubric: dict
    evidences: Annotated[dict[str, Evidence], operator.ior]
    opinions: Annotated[list[JudicialOpinion], operator.add]
    logs: Annotated[list[str], operator.add]
