from __future__ import annotations

from pathlib import Path

from .models import AuditReport, Evidence


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


def render_audit_report_markdown(report: AuditReport) -> str:
    lines: list[str] = []
    lines.append("# Final Audit Report")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- Aggregate Score: `{report.aggregate_score:.2f} / 5.0`")
    lines.append(f"- Verdict: {report.executive_summary}")
    lines.append("")
    lines.append("## Criterion Breakdown")
    lines.append("")

    for criterion in report.criterion_breakdown:
        lines.append(f"### {criterion.criterion_id} - {criterion.criterion_name}")
        lines.append(f"- Statute: {criterion.statute.value}")
        lines.append(f"- Final Score: `{criterion.final_score}`")
        lines.append(f"- Final Rationale: {criterion.final_rationale}")
        lines.append(f"- Dissent Summary: {criterion.dissent_summary}")
        if criterion.violated_rules:
            lines.append(f"- Deterministic Rules Applied: {', '.join(criterion.violated_rules)}")
        lines.append("- Judge Opinions:")
        for opinion in criterion.judge_opinions:
            cited = ", ".join(opinion.cited_evidence) if opinion.cited_evidence else "none"
            lines.append(
                f"  - {opinion.judge}: score={opinion.score}, statute={opinion.statute.value}, cited_evidence={cited}"
            )
            lines.append(f"    - Argument: {opinion.argument}")
        lines.append("- Remediation:")
        for item in criterion.remediation:
            lines.append(f"  - {item}")
        lines.append("")

    lines.append("## Remediation Plan")
    lines.append("")
    for criterion_id, items in report.remediation_plan.items():
        lines.append(f"### {criterion_id}")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## Dissent Log")
    lines.append("")
    for dissent in report.dissent_log:
        lines.append(f"- {dissent}")
    lines.append("")

    lines.append("## Evidence Index")
    lines.append("")
    for ev in report.evidence_index:
        lines.append(f"### {ev.id}")
        lines.append(f"- Goal: {ev.goal}")
        lines.append(f"- Found: `{ev.found}`")
        lines.append(f"- Location: `{ev.location}`")
        lines.append(f"- Confidence: `{ev.confidence:.2f}`")
        lines.append(f"- Rationale: {ev.rationale}")
        if ev.content:
            lines.append("- Content:")
            lines.append("```text")
            lines.append(ev.content)
            lines.append("```")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_report(path: str, content: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
