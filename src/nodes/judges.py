from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from difflib import SequenceMatcher
import re
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


_CRITERION_EVIDENCE_HINTS: dict[str, list[str]] = {
    "git_forensic_analysis": ["repo.git_narrative"],
    "state_management_rigor": ["repo.state_structure"],
    "graph_orchestration": ["repo.graph_wiring"],
    "safe_tool_engineering": ["repo.security_scan"],
    "structured_output_enforcement": ["repo.structured_output"],
    "judicial_nuance": ["repo.judicial_personas"],
    "chief_justice_synthesis": ["repo.chief_justice_rules"],
    "theoretical_depth": ["doc.concept_verification"],
    "report_accuracy": ["doc.citation_check"],
    "swarm_visual": ["repo.vision_implementation"],
}


def _criterion_relevant_evidence_keys(criterion: dict, evidence: dict) -> list[str]:
    cid = str(criterion.get("id", "")).strip().lower()
    cname = str(criterion.get("name", "")).strip().lower()

    hinted = [k for k in _CRITERION_EVIDENCE_HINTS.get(cid, []) if k in evidence]
    if hinted:
        return hinted

    keywords = set(re.findall(r"[a-z0-9_]+", f"{cid} {cname}"))
    keywords = {k for k in keywords if len(k) > 2 and k not in {"the", "and", "for"}}

    synonym_map = {
        "git": {"commit", "history"},
        "state": {"typed", "typedict", "pydantic", "reducers"},
        "orchestration": {"graph", "fan", "parallel", "edge"},
        "security": {"unsafe", "sandbox", "subprocess"},
        "documentation": {"doc", "pdf", "concept"},
        "diagram": {"visual", "vision"},
    }

    expanded = set(keywords)
    for kw in list(keywords):
        expanded.update(synonym_map.get(kw, set()))

    relevant: list[str] = []
    for key, value in evidence.items():
        tags = " ".join(value.get("tags", []))
        haystack = f"{key} {tags} {value.get('goal', '')} {value.get('rationale', '')}".lower()
        if any(token in haystack for token in expanded):
            relevant.append(key)

    if relevant:
        return relevant

    # Fallback to all evidence if no criterion-specific match is possible.
    return list(evidence.keys())


def _score_from_ratio(judge: JudgeName, ratio: float) -> int:
    if judge == "Prosecutor":
        if ratio >= 0.85:
            return 3
        if ratio >= 0.60:
            return 2
        return 1
    if judge == "Defense":
        if ratio >= 0.85:
            return 5
        if ratio >= 0.60:
            return 4
        if ratio >= 0.40:
            return 3
        return 2
    # TechLead
    if ratio >= 0.85:
        return 5
    if ratio >= 0.65:
        return 4
    if ratio >= 0.45:
        return 3
    if ratio >= 0.25:
        return 2
    return 1


def _heuristic_score(judge: JudgeName, criterion: dict, evidence: dict) -> JudicialOpinion:
    cid = criterion["id"]
    statute = _coerce_statute(criterion.get("statute"))

    relevant_keys = _criterion_relevant_evidence_keys(criterion, evidence)
    relevant = [evidence[k] for k in relevant_keys if k in evidence]
    found_count = sum(1 for e in relevant if e.get("found"))
    total = max(len(relevant), 1)
    confidence = found_count / total
    score = _score_from_ratio(judge, confidence)

    cited = sorted(
        relevant_keys,
        key=lambda key: 0 if evidence.get(key, {}).get("found") else 1,
    )[:2]

    return JudicialOpinion(
        judge=judge,
        criterion_id=cid,
        statute=statute,
        score=score,
        argument=(
            f"{judge} heuristic opinion based on criterion_evidence_ratio={confidence:.2f} "
            f"(relevant_evidence={len(relevant)})."
        ),
        cited_evidence=cited,
    )


def _build_judge_llm():
    provider = os.getenv("LLM_PROVIDER", "auto").lower()
    
    if provider in {"auto", "gemini"} and os.getenv("GEMINI_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.1,
        )

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
