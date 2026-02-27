from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Statute(str, Enum):
    ORCHESTRATION = "Statute of Orchestration"
    ENGINEERING = "Statute of Engineering"
    EFFORT = "Statute of Effort"
    SECURITY = "Statute of Security"


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
    statute: Statute = Field(default=Statute.ENGINEERING)
    score: int = Field(ge=1, le=5)
    argument: str
    cited_evidence: list[str] = Field(default_factory=list)


class CriterionBreakdown(BaseModel):
    criterion_id: str
    criterion_name: str
    statute: Statute
    final_score: int = Field(ge=1, le=5)
    judge_opinions: list[JudicialOpinion] = Field(default_factory=list)
    dissent_summary: str
    final_rationale: str
    violated_rules: list[str] = Field(default_factory=list)
    remediation: list[str] = Field(default_factory=list)


class AuditReport(BaseModel):
    executive_summary: str
    aggregate_score: float = Field(ge=1.0, le=5.0)
    criterion_breakdown: list[CriterionBreakdown] = Field(default_factory=list)
    remediation_plan: dict[str, list[str]] = Field(default_factory=dict)
    evidence_index: list[Evidence] = Field(default_factory=list)
    dissent_log: list[str] = Field(default_factory=list)
