from __future__ import annotations

import json
import os
from difflib import SequenceMatcher
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from ..models import JudicialOpinion, Statute
from ..state import AgentState


class _OpinionOut(BaseModel):
    criterion_id: str
    statute: Statute
    score: int
    argument: str
    cited_evidence: list[str]


def _criteria(state: AgentState) -> list[dict]:
    return state["rubric"].get("criteria", [])


def _evidence_payload(state: AgentState) -> dict:
    return {k: v.model_dump() for k, v in state["evidences"].items()}


def _heuristic_score(judge: str, criterion: dict, evidence: dict) -> JudicialOpinion:
    cid = criterion["id"]
    statute = Statute(criterion.get("statute", Statute.ENGINEERING.value))
    found_count = sum(1 for e in evidence.values() if e.get("found"))
    total = max(len(evidence), 1)
    confidence = found_count / total
    if judge == "Prosecutor":
        score = 2 if confidence > 0.7 else 1
    elif judge == "Defense":
        score = 5 if confidence > 0.5 else 4
    else:
        score = 5 if confidence > 0.8 else 3 if confidence > 0.4 else 1
    return JudicialOpinion(
        judge=judge,  # type: ignore[arg-type]
        criterion_id=cid,
        statute=statute,
        score=score,
        argument=f"{judge} heuristic opinion based on found_ratio={confidence:.2f}.",
        cited_evidence=list(evidence.keys())[:4],
    )


def _maybe_llm_opinion(judge: Literal["Prosecutor", "Defense", "TechLead"], criterion: dict, evidence: dict) -> JudicialOpinion:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _heuristic_score(judge, criterion, evidence)

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=model, temperature=0.1)
    structured = llm.with_structured_output(_OpinionOut)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You are {judge}. Return strict JSON for legal-style code governance scoring."),
            (
                "human",
                "Criterion:\n{criterion}\n\nEvidence:\n{evidence}\n\n"
                "Statutes: Orchestration, Engineering, Effort, Security.\n"
                "Cite only existing evidence ids.",
            ),
        ]
    )
    chain = prompt | structured
    out = chain.invoke(
        {
            "judge": judge,
            "criterion": json.dumps(criterion),
            "evidence": json.dumps(evidence),
        }
    )
    return JudicialOpinion(
        judge=judge,
        criterion_id=out.criterion_id,
        statute=out.statute,
        score=max(1, min(5, out.score)),
        argument=out.argument,
        cited_evidence=out.cited_evidence,
    )


def _judge_node(state: AgentState, judge: Literal["Prosecutor", "Defense", "TechLead"]) -> dict:
    evidence = _evidence_payload(state)
    opinions: list[JudicialOpinion] = []
    for criterion in _criteria(state):
        opinions.append(_maybe_llm_opinion(judge, criterion, evidence))
    return {"opinions": opinions, "logs": [f"{judge} completed"]}


def prosecutor_node(state: AgentState) -> dict:
    return _judge_node(state, "Prosecutor")


def defense_node(state: AgentState) -> dict:
    return _judge_node(state, "Defense")


def tech_lead_node(state: AgentState) -> dict:
    return _judge_node(state, "TechLead")


def detect_persona_collusion(state: AgentState) -> dict:
    args_by_judge = {
        "Prosecutor": [],
        "Defense": [],
        "TechLead": [],
    }
    for op in state["opinions"]:
        args_by_judge[op.judge].append(op.argument)

    similarities: list[float] = []
    pairs = [("Prosecutor", "Defense"), ("Prosecutor", "TechLead"), ("Defense", "TechLead")]
    for a, b in pairs:
        text_a = " ".join(args_by_judge[a])
        text_b = " ".join(args_by_judge[b])
        if text_a and text_b:
            similarities.append(SequenceMatcher(None, text_a, text_b).ratio())

    max_sim = max(similarities) if similarities else 0.0
    if max_sim >= 0.9:
        capped = [
            op.model_copy(update={"score": min(op.score, 2)})
            for op in state["opinions"]
        ]
        return {"opinions": capped, "logs": [f"Persona collusion detected (max_similarity={max_sim:.2f}); scores capped"]}
    return {"logs": [f"No persona collusion (max_similarity={max_sim:.2f})"]}

