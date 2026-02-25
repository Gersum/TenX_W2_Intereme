from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
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
    rubric = state["rubric"]
    return rubric.get("dimensions") or rubric.get("criteria") or []


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


def _build_llm():
    provider = os.getenv("LLM_PROVIDER", "auto").lower()

    if provider in {"auto", "ollama"}:
        ollama_model = os.getenv("OLLAMA_MODEL")
        if ollama_model:
            try:
                from langchain_ollama import ChatOllama

                return ChatOllama(
                    model=ollama_model,
                    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                    temperature=0.1,
                )
            except Exception:
                if provider == "ollama":
                    return None

    if provider in {"auto", "openai"} and os.getenv("OPENAI_API_KEY"):
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        return ChatOpenAI(model=model, temperature=0.1)

    return None


def _maybe_ollama_opinion(
    judge: Literal["Prosecutor", "Defense", "TechLead"],
    criterion: dict,
    evidence: dict,
) -> _OpinionOut | None:
    model = os.getenv("OLLAMA_MODEL")
    if not model:
        return None

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": f"You are {judge}. Return strict JSON for legal-style code governance scoring.",
            },
            {
                "role": "user",
                "content": (
                    "Criterion:\n"
                    f"{json.dumps(criterion)}\n\n"
                    "Evidence:\n"
                    f"{json.dumps(evidence)}\n\n"
                    "Statutes: Orchestration, Engineering, Effort, Security.\n"
                    "Cite only existing evidence ids."
                ),
            },
        ],
        "options": {"temperature": 0.1},
    }
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        content = data.get("message", {}).get("content", "")
        if not content:
            return None
        return _OpinionOut.model_validate_json(content)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _maybe_llm_opinion(judge: Literal["Prosecutor", "Defense", "TechLead"], criterion: dict, evidence: dict) -> JudicialOpinion:
    provider = os.getenv("LLM_PROVIDER", "auto").lower()

    if provider in {"auto", "ollama"}:
        ollama_out = _maybe_ollama_opinion(judge, criterion, evidence)
        if ollama_out is not None:
            return JudicialOpinion(
                judge=judge,
                criterion_id=ollama_out.criterion_id,
                statute=ollama_out.statute,
                score=max(1, min(5, ollama_out.score)),
                argument=ollama_out.argument,
                cited_evidence=ollama_out.cited_evidence,
            )
        if provider == "ollama":
            return _heuristic_score(judge, criterion, evidence)

    # Master Thinker tier: prefer DeepSeek for Judicial reasoning
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _heuristic_score(judge, criterion, evidence)

    model = os.getenv("OPENAI_MODEL_OVERRIDE", "deepseek-v3.2:cloud")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1") if "deepseek" in model else None

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
    )
    try:
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
    except Exception:
        return _heuristic_score(judge, criterion, evidence)

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
