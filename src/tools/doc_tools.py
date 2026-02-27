from __future__ import annotations

import base64
import os
import re
from pathlib import Path

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
    cited = set(re.findall(r"\b(?:src|tests|audit)/[\w./-]+", text))
    repo_set = set(known_paths)
    missing = sorted(p for p in cited if p not in repo_set)
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
    if not report_path or not Path(report_path).exists():
        return Evidence(
            id="doc.visual_audit",
            goal="Verify architectural diagrams in the report using Vision AI.",
            found=False,
            location=report_path or "N/A",
            rationale="No readable report supplied.",
            confidence=1.0,
            tags=["docs", "vision"],
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
            goal="Verify architectural diagrams in the report using Vision AI.",
            found=False,
            location=report_path,
            rationale=f"Failed to extract images from PDF: {e}",
            confidence=1.0,
            tags=["docs", "vision"],
        )

    if not b64_images:
        return Evidence(
            id="doc.visual_audit",
            goal="Verify architectural diagrams in the report using Vision AI.",
            found=False,
            location=report_path,
            rationale="No images extracted from the PDF to audit.",
            confidence=1.0,
            tags=["docs", "vision"],
        )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return Evidence(
            id="doc.visual_audit",
            goal="Verify architectural diagrams in the report using Vision AI.",
            found=False,
            location=report_path,
            rationale="GEMINI_API_KEY not configured. Vision skipped.",
            confidence=1.0,
            tags=["docs", "vision"],
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
            goal="Verify architectural diagrams in the report using Vision AI.",
            found=out.architectural_match,
            content=f"images_scanned={len(b64_images)}",
            location=report_path,
            rationale=out.rationale,
            confidence=0.9,
            tags=["docs", "vision"],
        )
    except Exception as e:
        return Evidence(
            id="doc.visual_audit",
            goal="Verify architectural diagrams in the report using Vision AI.",
            found=False,
            location=report_path,
            rationale=f"Vision API error: {str(e)}",
            confidence=1.0,
            tags=["docs", "vision"],
        )

