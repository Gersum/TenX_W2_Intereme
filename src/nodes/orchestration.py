from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from ..state import AgentState


class _PreRouteOut(BaseModel):
    doc_branch: Literal["doc_analyst", "doc_skipped"]
    rationale: str


class _PostRouteOut(BaseModel):
    post_branch: Literal["judicial", "clone_failure", "missing_evidence"]
    rationale: str


def _maybe_ollama_pre_route(state: AgentState) -> _PreRouteOut | None:
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
                "content": "You are an orchestration router. Return strict JSON only.",
            },
            {
                "role": "user",
                "content": (
                    f"Repo URL: {state['repo_url']}\n"
                    f"PDF Path: {state.get('pdf_path')}\n\n"
                    "Return JSON: {\"doc_branch\": \"doc_analyst\"|\"doc_skipped\", \"rationale\": \"...\"}\n"
                    "Use doc_analyst only if PDF path is present."
                ),
            },
        ],
        "options": {"temperature": 0},
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
        return _PreRouteOut.model_validate_json(content)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _maybe_ollama_post_route(state: AgentState) -> _PostRouteOut | None:
    model = os.getenv("OLLAMA_MODEL")
    if not model:
        return None
    has_repo = any(ev_id.startswith("repo.") and ev.found for ev_id, ev in state["evidences"].items())
    has_doc = any(ev_id.startswith("doc.") and ev.found for ev_id, ev in state["evidences"].items())
    has_clone_failure = any(
        ev_id.startswith("repo.") and "repo_access_error" in ev.tags
        for ev_id, ev in state["evidences"].items()
    )
    doc_required = bool(state.get("pdf_path"))
    summary = {
        "repo_url": state["repo_url"],
        "pdf_path": state.get("pdf_path"),
        "doc_required": doc_required,
        "repo_evidence_found": has_repo,
        "doc_evidence_found": has_doc,
        "clone_failure_detected": has_clone_failure,
        "evidence": {k: v.model_dump() for k, v in state["evidences"].items()},
    }
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": "You are an orchestration router. Return strict JSON only.",
            },
            {
                "role": "user",
                "content": (
                    f"Evidence summary:\n{json.dumps(summary)}\n\n"
                    "Return JSON: {\"post_branch\": \"judicial\"|\"clone_failure\"|\"missing_evidence\", \"rationale\": \"...\"}\n"
                    "Choose clone_failure if repository access/clone failed. "
                    "Choose missing_evidence when required evidence is incomplete but clone did not fail. "
                    "Choose judicial only when evidence is sufficient."
                ),
            },
        ],
        "options": {"temperature": 0},
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
        return _PostRouteOut.model_validate_json(content)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _build_router_llm():
    provider = os.getenv("LLM_PROVIDER", "auto").lower()
    if provider in {"auto", "ollama"}:
        ollama_model = os.getenv("OLLAMA_MODEL")
        if ollama_model:
            try:
                from langchain_ollama import ChatOllama

                return ChatOllama(
                    model=ollama_model,
                    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                    temperature=0.0,
                )
            except Exception:
                if provider == "ollama":
                    return None

    if provider in {"auto", "grok"} and os.getenv("GROK_API_KEY"):
        return ChatOpenAI(
            model=os.getenv("GROK_MODEL", "grok-2-latest"),
            api_key=os.getenv("GROK_API_KEY"),
            base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1"),
            temperature=0.0,
        )

    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("OPENAI_MODEL_OVERRIDE") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1") if "deepseek" in model else None
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.0,
    )


def run_orchestration_precheck(state: AgentState) -> dict:
    provider = os.getenv("LLM_PROVIDER", "auto").lower()
    if provider in {"auto", "ollama"}:
        ollama_out = _maybe_ollama_pre_route(state)
        if ollama_out is not None:
            return {
                "routing": {"doc_branch": ollama_out.doc_branch},
                "logs": [f"OrchestrationPrecheck llm selected {ollama_out.doc_branch}: {ollama_out.rationale}"],
            }
        if provider == "ollama":
            branch = "doc_analyst" if state.get("pdf_path") else "doc_skipped"
            return {
                "routing": {"doc_branch": branch},
                "logs": [f"OrchestrationPrecheck fallback selected {branch} (ollama unavailable)"],
            }

    llm = _build_router_llm()
    if llm is None:
        branch = "doc_analyst" if state.get("pdf_path") else "doc_skipped"
        return {
            "routing": {"doc_branch": branch},
            "logs": [f"OrchestrationPrecheck heuristic selected {branch}"],
        }

    structured = llm.with_structured_output(_PreRouteOut)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an orchestration router. Pick doc_branch based on input readiness.",
            ),
            (
                "human",
                "Repo URL: {repo_url}\nPDF Path: {pdf_path}\n"
                "Choose doc_branch as 'doc_analyst' if a report is available, otherwise 'doc_skipped'.",
            ),
        ]
    )
    chain = prompt | structured
    try:
        out = chain.invoke(
            {
                "repo_url": state["repo_url"],
                "pdf_path": state.get("pdf_path"),
            }
        )
        return {
            "routing": {"doc_branch": out.doc_branch},
            "logs": [f"OrchestrationPrecheck llm selected {out.doc_branch}: {out.rationale}"],
        }
    except Exception:
        branch = "doc_analyst" if state.get("pdf_path") else "doc_skipped"
        return {
            "routing": {"doc_branch": branch},
            "logs": [f"OrchestrationPrecheck fallback selected {branch}"],
        }


def run_orchestration_postcheck(state: AgentState) -> dict:
    has_repo = any(
        ev_id.startswith("repo.") and ev.found
        for ev_id, ev in state["evidences"].items()
    )
    has_doc = any(
        ev_id.startswith("doc.") and ev.found
        for ev_id, ev in state["evidences"].items()
    )
    has_clone_failure = any(
        ev_id.startswith("repo.") and "repo_access_error" in ev.tags
        for ev_id, ev in state["evidences"].items()
    )
    doc_required = bool(state.get("pdf_path"))

    provider = os.getenv("LLM_PROVIDER", "auto").lower()
    if provider in {"auto", "ollama"}:
        ollama_out = _maybe_ollama_post_route(state)
        if ollama_out is not None:
            return {
                "routing": {"post_branch": ollama_out.post_branch},
                "logs": [f"OrchestrationPostcheck llm selected {ollama_out.post_branch}: {ollama_out.rationale}"],
            }
        if provider == "ollama":
            if has_clone_failure:
                post_branch = "clone_failure"
            elif has_repo and (has_doc or not doc_required):
                post_branch = "judicial"
            else:
                post_branch = "missing_evidence"
            return {
                "routing": {"post_branch": post_branch},
                "logs": [f"OrchestrationPostcheck fallback selected {post_branch} (ollama unavailable)"],
            }

    llm = _build_router_llm()
    if llm is None:
        if has_clone_failure:
            post_branch = "clone_failure"
        elif has_repo and (has_doc or not doc_required):
            post_branch = "judicial"
        else:
            post_branch = "missing_evidence"
        return {
            "routing": {"post_branch": post_branch},
            "logs": [f"OrchestrationPostcheck heuristic selected {post_branch}"],
        }

    structured = llm.with_structured_output(_PostRouteOut)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an orchestration router. Choose post_branch using evidence completeness.",
            ),
            (
                "human",
                "Evidence summary:\n{summary}\n\n"
                "Choose 'clone_failure' if repository access/clone failed. "
                "Choose 'missing_evidence' when required evidence is incomplete but clone did not fail. "
                "Choose 'judicial' only if repo evidence is sufficient and required doc evidence is present.",
            ),
        ]
    )
    summary = {
        "repo_url": state["repo_url"],
        "pdf_path": state.get("pdf_path"),
        "doc_required": doc_required,
        "repo_evidence_found": has_repo,
        "doc_evidence_found": has_doc,
        "clone_failure_detected": has_clone_failure,
        "evidence": {k: v.model_dump() for k, v in state["evidences"].items()},
    }
    chain = prompt | structured
    try:
        out = chain.invoke({"summary": json.dumps(summary)})
        return {
            "routing": {"post_branch": out.post_branch},
            "logs": [f"OrchestrationPostcheck llm selected {out.post_branch}: {out.rationale}"],
        }
    except Exception:
        if has_clone_failure:
            post_branch = "clone_failure"
        elif has_repo and (has_doc or not doc_required):
            post_branch = "judicial"
        else:
            post_branch = "missing_evidence"
        return {
            "routing": {"post_branch": post_branch},
            "logs": [f"OrchestrationPostcheck fallback selected {post_branch}"],
        }


def run_judicial_fanout(state: AgentState) -> dict:
    return {"logs": ["JudicialFanout dispatched"]}


def run_judicial_integrity_check(state: AgentState) -> dict:
    criteria = state["rubric"].get("dimensions") or state["rubric"].get("criteria") or []
    criterion_ids = {
        str(item.get("id"))
        for item in criteria
        if isinstance(item, dict) and item.get("id")
    }

    malformed_reasons: list[str] = []
    opinions = state.get("opinions", [])
    if not criterion_ids:
        malformed_reasons.append("rubric_missing_criteria")

    for op in opinions:
        if op.criterion_id not in criterion_ids:
            malformed_reasons.append(f"unknown_criterion_id:{op.criterion_id}")
        if not (1 <= op.score <= 5):
            malformed_reasons.append(f"invalid_score:{op.judge}:{op.criterion_id}:{op.score}")

    expected = len(criterion_ids) * 3 if criterion_ids else 0
    if expected and len(opinions) < expected:
        malformed_reasons.append(f"incomplete_judicial_output:expected={expected},actual={len(opinions)}")

    branch = "malformed_outputs_handler" if malformed_reasons else "chief_justice"
    detail = ", ".join(sorted(set(malformed_reasons))) if malformed_reasons else "all_opinions_well_formed"
    return {
        "routing": {"judicial_branch": branch},
        "logs": [f"JudicialIntegrityCheck selected {branch}: {detail}"],
    }
