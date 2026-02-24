from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Statute(str, Enum):
    ORCHESTRATION = "Statute of Orchestration"
    ENGINEERING = "Statute of Engineering"
    EFFORT = "Statute of Effort"
    SECURITY = "Rule of Security"


class Evidence(BaseModel):
    id: str = Field(description="Stable evidence identifier.")
    goal: str = Field(description="The forensic objective.")
    found: bool = Field(description="Existence of the artifact.")
    content: str | None = Field(default=None, description="Optional evidence payload.")
    location: str = Field(description="File path or commit hash.")
    rationale: str = Field(description="Justification for confidence level.")
    confidence: float = Field(description="0.0 to 1.0 score of fact certainty.", ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list, description="Classification tags.")


class JudicialOpinion(BaseModel):
    judge: Literal["Prosecutor", "Defense", "TechLead"]
    criterion_id: str
    statute: Statute
    score: int = Field(ge=1, le=5)
    argument: str
    cited_evidence: list[str] = Field(default_factory=list)


class CriterionVerdict(BaseModel):
    criterion_id: str
    score: int = Field(ge=1, le=5)
    rationale: str
    dissent: str
    violated_rules: list[str] = Field(default_factory=list)
    remediation: list[str] = Field(default_factory=list)


class FinalVerdict(BaseModel):
    total_score: float = Field(ge=1.0, le=5.0)
    executive_summary: str
    criteria: list[CriterionVerdict]
    evidence_index: list[Evidence] = Field(default_factory=list)
    dissent_log: list[str] = Field(default_factory=list)

