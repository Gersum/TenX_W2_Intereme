from __future__ import annotations

from ..state import AgentState, Evidence
from ..tools.doc_tools import protocol_citation_check, protocol_concept_verification
from ..tools.repo_tools import (
    protocol_git_narrative,
    protocol_graph_wiring,
    protocol_security_scan,
    protocol_state_structure,
    resolve_repo,
)


def _repo_file_inventory(repo_target: str) -> list[str]:
    try:
        path, temp_dir = resolve_repo(repo_target)
        inventory = [
            str(p.relative_to(path))
            for p in path.rglob("*")
            if p.is_file()
        ]
        if temp_dir:
            temp_dir.cleanup()
        return inventory
    except Exception:
        return []


def run_repo_investigator(state: AgentState) -> dict:
    evidences: dict[str, Evidence] = {}
    for protocol in (
        protocol_state_structure,
        protocol_graph_wiring,
        protocol_git_narrative,
        protocol_security_scan,
    ):
        ev = protocol(state["repo_url"])
        evidences[ev.id] = ev
    return {"evidences": evidences, "logs": ["RepoInvestigator completed"]}  # type: ignore[return-value]


def run_doc_analyst(state: AgentState) -> dict:
    known_paths = _repo_file_inventory(state["repo_url"])
    citation = protocol_citation_check(state.get("pdf_path"), known_paths)
    concept = protocol_concept_verification(state.get("pdf_path"))
    return {
        "evidences": {citation.id: citation, concept.id: concept},
        "logs": ["DocAnalyst completed"],
    }


def run_doc_skipped(state: AgentState) -> dict:
    return {
        "logs": [
            "DocAnalyst skipped: no PDF report path provided; continuing with repository-only evidence."
        ]
    }


def run_evidence_aggregator(state: AgentState) -> dict:
    evidence_count = len(state["evidences"])
    has_repo = any(
        ev_id.startswith("repo.") and ev.found
        for ev_id, ev in state["evidences"].items()
    )
    has_doc = any(
        ev_id.startswith("doc.") and ev.found
        for ev_id, ev in state["evidences"].items()
    )
    doc_required = bool(state.get("pdf_path"))
    status = "ready" if (has_repo and (has_doc or not doc_required)) else "incomplete"
    return {
        "logs": [
            (
                f"EvidenceAggregator completed: evidence_count={evidence_count}, "
                f"repo_evidence={has_repo}, doc_evidence={has_doc}, doc_required={doc_required}, status={status}"
            )
        ]
    }


def run_missing_artifacts_handler(state: AgentState) -> dict:
    return {
        "logs": [
            "MissingArtifactsHandler: required detective evidence was incomplete; "
            "continuing with partial output for graceful degradation."
        ]
    }
