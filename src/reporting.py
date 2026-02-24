from __future__ import annotations

from pathlib import Path

from .state import Evidence


def render_detective_report(
    repo_url: str,
    pdf_path: str | None,
    evidences: dict[str, Evidence],
    logs: list[str],
    output_path: str,
) -> str:
    lines: list[str] = []
    lines.append("# Interim Detective Audit Report")
    lines.append("")
    lines.append("## Input")
    lines.append("")
    lines.append(f"- Repository Target: `{repo_url}`")
    lines.append(f"- PDF Report: `{pdf_path or 'N/A'}`")
    lines.append("")
    lines.append("## Evidence Index")
    lines.append("")

    for evidence_id in sorted(evidences.keys()):
        ev = evidences[evidence_id]
        lines.append(f"### {evidence_id}")
        lines.append(f"- Goal: {ev.goal}")
        lines.append(f"- Found: `{ev.found}`")
        lines.append(f"- Confidence: `{ev.confidence:.2f}`")
        lines.append(f"- Location: `{ev.location}`")
        lines.append(f"- Rationale: {ev.rationale}")
        if ev.content:
            lines.append("- Content:")
            lines.append("```text")
            lines.append(ev.content)
            lines.append("```")
        if ev.tags:
            lines.append(f"- Tags: {', '.join(ev.tags)}")
        lines.append("")

    lines.append("## Execution Log")
    lines.append("")
    for log in logs:
        lines.append(f"- {log}")

    content = "\n".join(lines) + "\n"
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return content

