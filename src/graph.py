from __future__ import annotations

import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from .nodes.detectives import run_doc_analyst, run_evidence_aggregator, run_repo_investigator
from .state import AgentState


DEFAULT_RUBRIC = {
    "criteria": [
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


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("repo_investigator", run_repo_investigator)
    builder.add_node("doc_analyst", run_doc_analyst)
    builder.add_node("evidence_aggregator", run_evidence_aggregator)

    builder.add_edge(START, "repo_investigator")
    builder.add_edge(START, "doc_analyst")

    builder.add_edge("repo_investigator", "evidence_aggregator")
    builder.add_edge("doc_analyst", "evidence_aggregator")

    builder.add_edge("evidence_aggregator", END)
    return builder.compile()
