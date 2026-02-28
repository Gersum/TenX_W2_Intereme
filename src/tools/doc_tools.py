from __future__ import annotations

import base64
import os
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath

from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from pypdf import PdfReader

from ..state import Evidence


def _read_pdf_text(report_path: str) -> str:
    reader = PdfReader(report_path)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def ingest_pdf(path: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    text = _read_pdf_text(path).strip()
    if not text:
        return []

    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(text), step):
        chunk = text[i : i + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def query_pdf_chunks(chunks: list[str], query: str, top_k: int = 3) -> list[str]:
    tokens = [t for t in re.findall(r"[a-zA-Z0-9_-]+", query.lower()) if len(t) > 2]
    if not chunks or not tokens:
        return []

    scored: list[tuple[int, str]] = []
    for chunk in chunks:
        lower = chunk.lower()
        score = sum(lower.count(token) for token in tokens)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def _normalize_cited_path(raw: str) -> str:
    token = unicodedata.normalize("NFKC", raw.strip().strip("`'\""))
    # Common PDF extraction artifact: file path followed by prose suffix
    # e.g. src/nodes/justice.py-dependent
    token = re.sub(r"(\.(?:py|md|json|ya?ml|txt))(?:-[a-z][\w-]*)+", r"\1", token)
    # Common extraction artifact: two paths fused together (e.g. src/state.py/src/graph.py)
    fused = re.match(r"^(.*\.(?:py|md|json|ya?ml|txt))(?:/src/.*)$", token)
    if fused:
        token = fused.group(1)
    while token and token[-1] in ".,;:)]}":
        token = token[:-1]
    token = token.lstrip("./")
    if not token:
        return token
    return str(PurePosixPath(token))


def _known_repo_dirs(known_paths: list[str]) -> set[str]:
    dirs: set[str] = set()
    for rel in known_paths:
        p = PurePosixPath(rel)
        parts = p.parts
        for i in range(1, len(parts)):
            dirs.add(str(PurePosixPath(*parts[:i])))
    return dirs


def _exists_in_repo(path: str, repo_files: set[str], repo_dirs: set[str]) -> bool:
    normalized = path.rstrip("/")
    exists_as_file = normalized in repo_files
    exists_as_dir = normalized in repo_dirs or any(item.startswith(normalized + "/") for item in repo_files)
    return exists_as_file or exists_as_dir


def _resolve_near_match(path: str, repo_files: set[str], repo_dirs: set[str]) -> str | None:
    normalized = path.rstrip("/")

    # Frequent style in prose: directory-like mention of module file (src/models -> src/models.py)
    for ext in (".py", ".md", ".json", ".yaml", ".yml", ".txt"):
        ext_candidate = normalized + ext
        if _exists_in_repo(ext_candidate, repo_files, repo_dirs):
            return ext_candidate

    # Common singular/plural drift from extraction (tool -> tools)
    plural_candidate = normalized + "s"
    if _exists_in_repo(plural_candidate, repo_files, repo_dirs):
        return plural_candidate

    # Fuzzy fallback for slight OCR/wrapping corruption.
    candidates = list(repo_files | repo_dirs)
    best: tuple[float, str] | None = None
    for candidate in candidates:
        if abs(len(candidate) - len(normalized)) > 4:
            continue
        if not candidate.startswith(normalized[:4]) and not normalized.startswith(candidate[:4]):
            continue
        ratio = SequenceMatcher(None, normalized, candidate).ratio()
        if ratio >= 0.93 and (best is None or ratio > best[0]):
            best = (ratio, candidate)
    return best[1] if best else None


def protocol_citation_check(report_path: str | None, known_paths: list[str]) -> Evidence:
    if not report_path:
        return Evidence(
            id="doc.citation_check",
            goal="Cross-reference cited files against repository artifacts.",
            found=False,
            location="N/A",
            rationale="No report supplied.",
            confidence=1.0,
            tags=["docs", "hallucination"],
        )

    path = Path(report_path)
    if not path.exists():
        return Evidence(
            id="doc.citation_check",
            goal="Cross-reference cited files against repository artifacts.",
            found=False,
            location=str(path),
            rationale="Report file not found.",
            confidence=1.0,
            tags=["docs", "hallucination"],
        )

    chunks = ingest_pdf(str(path))
    text = "\n".join(chunks)
    cited_raw = set(re.findall(r"\b(?:src|tests|audit|reports)/[\w./-]+/?", text))
    cited_with_flags: list[tuple[str, bool]] = []
    for item in cited_raw:
        normalized = _normalize_cited_path(item)
        if not normalized:
            continue
        explicit_dir = item.rstrip().endswith("/")
        cited_with_flags.append((normalized, explicit_dir))

    # Deduplicate while preserving explicit-dir signal if any instance had it.
    by_path: dict[str, bool] = {}
    for normalized, explicit_dir in cited_with_flags:
        by_path[normalized] = by_path.get(normalized, False) or explicit_dir

    cited = sorted(by_path.items(), key=lambda pair: pair[0])
    repo_files = {_normalize_cited_path(item) for item in known_paths if _normalize_cited_path(item)}
    repo_dirs = _known_repo_dirs(list(repo_files))

    missing: list[str] = []
    for cited_path, explicit_dir in cited:
        normalized = cited_path.rstrip("/")

        # Ignore ambiguous prose tokens that are not explicit directories and not file-like paths.
        # Example false positives from PDF extraction: src/api, src/utils, src/n
        leaf = PurePosixPath(normalized).name
        has_extension = "." in leaf
        if not explicit_dir and not has_extension:
            continue

        if _exists_in_repo(normalized, repo_files, repo_dirs):
            continue
        near = _resolve_near_match(normalized, repo_files, repo_dirs)
        if near is None:
            missing.append(cited_path)

    found = len(missing) == 0

    return Evidence(
        id="doc.citation_check",
        goal="Cross-reference cited files against repository artifacts.",
        found=found,
        content="missing=" + (", ".join(missing[:20]) if missing else "none"),
        location=str(path),
        rationale="Compared path-like citations extracted from PDF to repo file list.",
        confidence=0.8,
        tags=["docs", "hallucination"],
    )


def protocol_concept_verification(report_path: str | None) -> Evidence:
    if not report_path or not Path(report_path).exists():
        return Evidence(
            id="doc.concept_verification",
            goal="Verify conceptual treatment of metacognition and dialectical synthesis.",
            found=False,
            location=report_path or "N/A",
            rationale="No readable report supplied.",
            confidence=1.0,
            tags=["docs", "concept"],
        )

    chunks = ingest_pdf(report_path)
    hits = query_pdf_chunks(
        chunks,
        "Dialectical Synthesis Fan-In Fan-Out Metacognition State Synchronization",
        top_k=4,
    )
    hit_text = "\n".join(hits).lower()
    has_metacognition = "metacognition" in hit_text
    has_dialectics = "dialectical" in hit_text or "thesis-antithesis-synthesis" in hit_text
    found = has_metacognition and has_dialectics

    return Evidence(
        id="doc.concept_verification",
            goal="Verify conceptual treatment of metacognition and dialectical synthesis.",
            found=found,
            content=f"chunks={len(chunks)}, hits={len(hits)}, metacognition={has_metacognition}, dialectical={has_dialectics}",
            location=report_path,
            rationale="Chunked query over parsed PDF content (RAG-lite retrieval).",
            confidence=0.7,
            tags=["docs", "concept"],
        )


class _VisionOut(BaseModel):
    architectural_match: bool
    rationale: str


def protocol_visual_audit(report_path: str | None) -> Evidence:
    goal = "Verify architectural diagrams in the report using Vision AI."

    if not report_path or not Path(report_path).exists():
        return Evidence(
            id="doc.visual_audit",
            goal=goal,
            found=False,
            location=report_path or "N/A",
            content="status=skipped, reason=missing_report, action=provide_pdf_report",
            rationale="Vision audit skipped because no readable report was supplied.",
            confidence=1.0,
            tags=["docs", "vision", "degraded_mode"],
        )

    try:
        import fitz
        doc = fitz.open(report_path)
        b64_images = []
        # Max scale for clarity, but cap it to avoid huge payloads
        for i in range(len(doc)):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=150)
            b64_images.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
    except Exception as e:
        return Evidence(
            id="doc.visual_audit",
            goal=goal,
            found=False,
            location=report_path,
            content="status=failed, reason=pdf_image_extraction_error, action=validate_pdf_integrity",
            rationale=f"Vision audit degraded: failed to extract images from PDF ({e}).",
            confidence=1.0,
            tags=["docs", "vision", "degraded_mode"],
        )

    if not b64_images:
        return Evidence(
            id="doc.visual_audit",
            goal=goal,
            found=False,
            location=report_path,
            content="status=skipped, reason=no_images_in_pdf, action=embed_architecture_diagram",
            rationale="Vision audit skipped because no images were extracted from the PDF.",
            confidence=1.0,
            tags=["docs", "vision", "degraded_mode"],
        )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return Evidence(
            id="doc.visual_audit",
            goal=goal,
            found=False,
            location=report_path,
            content="status=skipped, reason=missing_gemini_api_key, action=set_GEMINI_API_KEY",
            rationale="Vision audit degraded: GEMINI_API_KEY is not configured; continuing without vision scoring.",
            confidence=1.0,
            tags=["docs", "vision", "degraded_mode"],
        )

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            api_key=api_key,
            temperature=0.0,
        )
        structured = llm.with_structured_output(_VisionOut)

        content: list[dict[str, object]] = [
            {
                "type": "text", 
                "text": "Review these images from a system architecture report. Do they depict a parallel execution graph with fan-out (detectives) and fan-in (aggregation)? Respond based on visual evidence."
            }
        ]
        
        # Limit to first 3 images to conserve tokens and prevent payload bloat
        for b64 in b64_images[:3]:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })

        message = HumanMessage(content=content)
        out = structured.invoke([message])

        # Type guard against untyped invoke returns
        if not isinstance(out, _VisionOut):
            raise TypeError("LLM did not return structured _VisionOut")

        return Evidence(
            id="doc.visual_audit",
            goal=goal,
            found=out.architectural_match,
            content=f"images_scanned={len(b64_images)}",
            location=report_path,
            rationale=out.rationale,
            confidence=0.9,
            tags=["docs", "vision"],
        )
    except Exception as e:
        err = str(e).lower()
        if any(term in err for term in ("quota", "rate", "429", "resource_exhausted")):
            reason = "vision_quota_or_rate_limit"
            action = "retry_later_or_upgrade_quota"
        elif any(term in err for term in ("api key", "permission", "unauthorized", "403", "401")):
            reason = "vision_auth_or_permission_error"
            action = "verify_gemini_key_and_permissions"
        elif any(term in err for term in ("resolve host", "dns", "connection", "timeout", "network")):
            reason = "vision_network_error"
            action = "verify_network_dns_access"
        else:
            reason = "vision_api_error"
            action = "inspect_provider_logs"
        return Evidence(
            id="doc.visual_audit",
            goal=goal,
            found=False,
            content=f"status=degraded, reason={reason}, action={action}",
            location=report_path,
            rationale=(
                "Vision audit degraded due to provider/API failure; pipeline continued with non-vision evidence. "
                f"Raw error: {str(e)}"
            ),
            confidence=1.0,
            tags=["docs", "vision", "degraded_mode"],
        )
