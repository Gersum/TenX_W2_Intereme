from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from langgraph.graph import END, START, StateGraph

from .nodes.detectives import (
    run_doc_analyst,
    run_doc_skipped,
    run_evidence_aggregator,
    run_missing_artifacts_handler,
    run_repo_investigator,
)
from .nodes.judges import defense_node, prosecutor_node, tech_lead_node
from .nodes.supreme_court import chief_justice_node
from .state import AgentState


DEFAULT_RUBRIC = {
    "dimensions": [
        {
            "id": "C1_Orchestration",
            "statute": "Statute of Orchestration",
            "remediation_templates": [
                "Implement explicit fan-out/fan-in edges in src/graph.py.",
                "Ensure detectives and judges execute in parallel nodes.",
            ],
        },
        {
            "id": "C2_Engineering",
            "statute": "Statute of Engineering",
            "remediation_templates": [
                "Strengthen typed state and Pydantic validation contracts.",
                "Add deterministic synthesis constraints for final scoring.",
            ],
        },
        {
            "id": "C3_Effort",
            "statute": "Statute of Effort",
            "remediation_templates": [
                "Use atomic commits with meaningful messages.",
                "Document iteration decisions in README or report.",
            ],
        },
    ]
}


def load_rubric(path: str | None) -> dict:
    if not path:
        return DEFAULT_RUBRIC
    file_path = Path(path)
    if not file_path.exists():
        return DEFAULT_RUBRIC
    return json.loads(file_path.read_text(encoding="utf-8"))


def _route_doc_branch(state: AgentState) -> Literal["doc_analyst", "doc_skipped"]:
    return "doc_analyst" if state.get("pdf_path") else "doc_skipped"


def _route_post_aggregation(
    state: AgentState,
) -> list[Literal["prosecutor", "defense", "tech_lead"]] | Literal["missing_artifacts_handler"]:
    has_repo = any(
        ev_id.startswith("repo.") and ev.found
        for ev_id, ev in state["evidences"].items()
    )
    has_doc = any(
        ev_id.startswith("doc.") and ev.found
        for ev_id, ev in state["evidences"].items()
    )
    doc_required = bool(state.get("pdf_path"))
    if has_repo and (has_doc or not doc_required):
        return ["prosecutor", "defense", "tech_lead"]
    return "missing_artifacts_handler"


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("repo_investigator", run_repo_investigator)
    builder.add_node("doc_analyst", run_doc_analyst)
    builder.add_node("doc_skipped", run_doc_skipped)
    builder.add_node("evidence_aggregator", run_evidence_aggregator)
    builder.add_node("missing_artifacts_handler", run_missing_artifacts_handler)
    builder.add_node("prosecutor", prosecutor_node)
    builder.add_node("defense", defense_node)
    builder.add_node("tech_lead", tech_lead_node)
    builder.add_node("chief_justice", chief_justice_node)

    builder.add_edge(START, "repo_investigator")
    builder.add_conditional_edges(START, _route_doc_branch)

    builder.add_edge("repo_investigator", "evidence_aggregator")
    builder.add_edge("doc_analyst", "evidence_aggregator")
    builder.add_edge("doc_skipped", "evidence_aggregator")

    builder.add_conditional_edges("evidence_aggregator", _route_post_aggregation)

    builder.add_edge("prosecutor", "chief_justice")
    builder.add_edge("defense", "chief_justice")
    builder.add_edge("tech_lead", "chief_justice")

    builder.add_edge("missing_artifacts_handler", END)
    builder.add_edge("chief_justice", END)
    return builder.compile()
