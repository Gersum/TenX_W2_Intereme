from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from .models import AuditReport, Evidence, JudicialOpinion


class AgentState(TypedDict):
    repo_url: str
    pdf_path: str | None
    rubric: dict
    evidences: Annotated[dict[str, Evidence], operator.ior]
    opinions: Annotated[list[JudicialOpinion], operator.add]
    routing: Annotated[dict[str, str], operator.ior]
    logs: Annotated[list[str], operator.add]
    audit_report: AuditReport | None
    final_report: str | None
