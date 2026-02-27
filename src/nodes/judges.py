from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..models import JudicialOpinion, Statute
from ..state import AgentState

JudgeName = Literal["Prosecutor", "Defense", "TechLead"]


def _judge_system_prompt(judge: JudgeName) -> str:
    if judge == "Prosecutor":
        return (
            "You are the Prosecutor in an AI governance court. "
            "You must aggressively identify implementation gaps, unverifiable claims, security flaws, and signs of low rigor. "
            "Favor strict scoring when evidence is incomplete. "
            "Return only a valid JudicialOpinion JSON payload."
        )
    if judge == "Defense":
        return (
            "You are the Defense in an AI governance court. "
            "You must highlight demonstrated effort, practical constraints, reasonable tradeoffs, and incremental progress. "
            "Do not invent facts; reward evidence-backed improvement. "
            "Return only a valid JudicialOpinion JSON payload."
        )
    return (
        "You are the Tech Lead in an AI governance court. "
        "Prioritize architectural correctness, maintainability, operational safety, and end-to-end viability. "
        "Favor technically defensible decisions grounded in concrete evidence. "
        "Return only a valid JudicialOpinion JSON payload."
    )


def _criteria(state: AgentState) -> list[dict]:
    rubric = state["rubric"]
    return rubric.get("dimensions") or rubric.get("criteria") or []


def _evidence_payload(state: AgentState) -> dict:
    return {k: v.model_dump() for k, v in state["evidences"].items()}


def _coerce_statute(raw: str | None) -> Statute:
    if not raw:
        return Statute.ENGINEERING
    for statute in Statute:
        if statute.value == raw:
            return statute
    return Statute.ENGINEERING


def _heuristic_score(judge: JudgeName, criterion: dict, evidence: dict) -> JudicialOpinion:
    cid = criterion["id"]
    statute = _coerce_statute(criterion.get("statute"))
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
        judge=judge,
        criterion_id=cid,
        statute=statute,
        score=score,
        argument=f"{judge} heuristic opinion based on found_ratio={confidence:.2f}.",
        cited_evidence=list(evidence.keys())[:4],
    )


def _build_judge_llm():
    provider = os.getenv("LLM_PROVIDER", "auto").lower()
    if provider in {"auto", "grok"} and os.getenv("GROK_API_KEY"):
        return ChatOpenAI(
            model=os.getenv("GROK_MODEL", "grok-2-latest"),
            api_key=os.getenv("GROK_API_KEY"),
            base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1"),
            temperature=0.1,
        )

    if provider in {"auto", "openai"} and os.getenv("OPENAI_API_KEY"):
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.1,
        )

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if api_key:
        model = os.getenv("OPENAI_MODEL_OVERRIDE", "deepseek-v3.2:cloud")
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"),
            temperature=0.1,
        )
    return None


def _maybe_ollama_opinion(judge: JudgeName, criterion: dict, evidence: dict) -> JudicialOpinion | None:
    model = os.getenv("OLLAMA_MODEL")
    if not model:
        return None

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    cid = criterion["id"]
    statute = _coerce_statute(criterion.get("statute"))
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": _judge_system_prompt(judge)},
            {
                "role": "user",
                "content": (
                    f"Criterion ID: {cid}\n"
                    f"Statute: {statute.value}\n"
                    f"Evidence JSON:\n{json.dumps(evidence)}\n\n"
                    "Return JSON with keys: judge, criterion_id, statute, score (1-5), argument, cited_evidence."
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
        content = json.loads(raw).get("message", {}).get("content", "")
        if not content:
            return None
        opinion = JudicialOpinion.model_validate_json(content)
        return opinion.model_copy(
            update={
                "judge": judge,
                "criterion_id": cid,
                "statute": statute,
                "score": max(1, min(5, opinion.score)),
            }
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _maybe_llm_opinion(judge: JudgeName, criterion: dict, evidence: dict) -> JudicialOpinion:
    provider = os.getenv("LLM_PROVIDER", "auto").lower()
    if provider in {"auto", "ollama"}:
        ollama_out = _maybe_ollama_opinion(judge, criterion, evidence)
        if ollama_out is not None:
            return ollama_out
        if provider == "ollama":
            return _heuristic_score(judge, criterion, evidence)

    llm = _build_judge_llm()
    if llm is None:
        return _heuristic_score(judge, criterion, evidence)

    cid = criterion["id"]
    statute = _coerce_statute(criterion.get("statute"))
    try:
        structured = llm.with_structured_output(JudicialOpinion)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _judge_system_prompt(judge)),
                (
                    "human",
                    "Criterion JSON:\n{criterion}\n\nEvidence JSON:\n{evidence}\n\n"
                    "Return JudicialOpinion JSON with:\n"
                    "- judge: {judge}\n"
                    "- criterion_id: {criterion_id}\n"
                    "- statute: {statute}\n"
                    "- score: int in [1,5]\n"
                    "- argument: concise legal-style rationale\n"
                    "- cited_evidence: existing evidence ids only",
                ),
            ]
        )
        chain = prompt | structured
        out = chain.invoke(
            {
                "judge": judge,
                "criterion_id": cid,
                "statute": statute.value,
                "criterion": json.dumps(criterion),
                "evidence": json.dumps(evidence),
            }
        )
        return out.model_copy(
            update={
                "judge": judge,
                "criterion_id": cid,
                "statute": statute,
                "score": max(1, min(5, out.score)),
            }
        )
    except Exception:
        return _heuristic_score(judge, criterion, evidence)


def _judge_node(state: AgentState, judge: JudgeName) -> dict:
    criteria = _criteria(state)
    existing = {op.criterion_id for op in state["opinions"] if op.judge == judge}
    pending = [criterion for criterion in criteria if criterion["id"] not in existing]
    if not pending:
        return {"logs": [f"{judge} skipped (already evaluated)"]}

    evidence = _evidence_payload(state)
    opinions = [_maybe_llm_opinion(judge, criterion, evidence) for criterion in pending]
    return {"opinions": opinions, "logs": [f"{judge} completed"]}


def prosecutor_node(state: AgentState) -> dict:
    return _judge_node(state, "Prosecutor")


def defense_node(state: AgentState) -> dict:
    return _judge_node(state, "Defense")


def tech_lead_node(state: AgentState) -> dict:
    return _judge_node(state, "TechLead")


def detect_persona_collusion(state: AgentState) -> dict:
    args_by_judge = {"Prosecutor": [], "Defense": [], "TechLead": []}
    for opinion in state["opinions"]:
        args_by_judge[opinion.judge].append(opinion.argument)

    similarities: list[float] = []
    for left, right in (("Prosecutor", "Defense"), ("Prosecutor", "TechLead"), ("Defense", "TechLead")):
        text_left = " ".join(args_by_judge[left])
        text_right = " ".join(args_by_judge[right])
        if text_left and text_right:
            similarities.append(SequenceMatcher(None, text_left, text_right).ratio())

    max_similarity = max(similarities) if similarities else 0.0
    if max_similarity >= 0.9:
        capped = [op.model_copy(update={"score": min(op.score, 2)}) for op in state["opinions"]]
        return {
            "opinions": capped,
            "logs": [f"Persona collusion detected (max_similarity={max_similarity:.2f}); scores capped"],
        }
    return {"logs": [f"No persona collusion (max_similarity={max_similarity:.2f})"]}
