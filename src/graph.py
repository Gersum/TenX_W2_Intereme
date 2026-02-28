from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from langgraph.graph import END, START, StateGraph

try:
    from langsmith import traceable
except Exception:  # pragma: no cover - optional runtime dependency fallback
    traceable = None

from .nodes.detectives import (
    run_doc_analyst,
    run_doc_skipped,
    run_evidence_aggregator,
    run_missing_artifacts_handler,
    run_repo_investigator,
    run_vision_inspector,
)
from .nodes.judges import defense_node, prosecutor_node, tech_lead_node
from .nodes.justice import chief_justice_node
from .nodes.orchestration import (
    run_judicial_fanout,
    run_orchestration_postcheck,
    run_orchestration_precheck,
)
from .state import AgentState


def _traced_node(name: str, func):
    if traceable is None:
        return func
    return traceable(name=name, run_type="chain")(func)


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
    return state.get("routing", {}).get("doc_branch", "doc_skipped")  # type: ignore[return-value]


def _route_post_orchestration(
    state: AgentState,
) -> Literal["judicial_fanout", "missing_artifacts_handler"]:
    if state.get("routing", {}).get("post_branch") == "judicial":
        return "judicial_fanout"
    return "missing_artifacts_handler"


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("repo_investigator", _traced_node("RepoInvestigator", run_repo_investigator))
    builder.add_node("orchestration_precheck", _traced_node("OrchestrationPrecheck", run_orchestration_precheck))
    builder.add_node("doc_analyst", _traced_node("DocAnalyst", run_doc_analyst))
    builder.add_node("doc_skipped", _traced_node("DocSkipped", run_doc_skipped))
    builder.add_node("vision_inspector", _traced_node("VisionInspector", run_vision_inspector))
    builder.add_node("evidence_aggregator", _traced_node("EvidenceAggregator", run_evidence_aggregator))
    builder.add_node("orchestration_postcheck", _traced_node("OrchestrationPostcheck", run_orchestration_postcheck))
    builder.add_node("judicial_fanout", _traced_node("JudicialFanout", run_judicial_fanout))
    builder.add_node("missing_artifacts_handler", _traced_node("MissingArtifactsHandler", run_missing_artifacts_handler))
    builder.add_node("prosecutor", _traced_node("Prosecutor", prosecutor_node))
    builder.add_node("defense", _traced_node("Defense", defense_node))
    builder.add_node("tech_lead", _traced_node("TechLead", tech_lead_node))
    builder.add_node("chief_justice", _traced_node("ChiefJustice", chief_justice_node))

    builder.add_edge(START, "repo_investigator")
    builder.add_edge(START, "orchestration_precheck")
    builder.add_edge(START, "vision_inspector")
    builder.add_conditional_edges("orchestration_precheck", _route_doc_branch)

    builder.add_edge("repo_investigator", "evidence_aggregator")
    builder.add_edge("doc_analyst", "evidence_aggregator")
    builder.add_edge("doc_skipped", "evidence_aggregator")
    builder.add_edge("vision_inspector", "evidence_aggregator")

    builder.add_edge("evidence_aggregator", "orchestration_postcheck")
    builder.add_conditional_edges("orchestration_postcheck", _route_post_orchestration)
    builder.add_edge("judicial_fanout", "prosecutor")
    builder.add_edge("judicial_fanout", "defense")
    builder.add_edge("judicial_fanout", "tech_lead")

    builder.add_edge("prosecutor", "chief_justice")
    builder.add_edge("defense", "chief_justice")
    builder.add_edge("tech_lead", "chief_justice")

    builder.add_edge("missing_artifacts_handler", END)
    builder.add_edge("chief_justice", END)
    return builder.compile()
