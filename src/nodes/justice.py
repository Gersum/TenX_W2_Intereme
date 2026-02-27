from __future__ import annotations

from collections import defaultdict

from ..models import AuditReport, CriterionBreakdown, JudicialOpinion, Statute
from ..reporting import render_audit_report_markdown
from ..state import AgentState


def _coerce_statute(raw: str | None) -> Statute:
    if not raw:
        return Statute.ENGINEERING
    for statute in Statute:
        if statute.value == raw:
            return statute
    return Statute.ENGINEERING


def _clamp_score(score: int | float) -> int:
    return max(1, min(5, int(round(score))))


def _missing_or_unfound_citations(opinion: JudicialOpinion, state: AgentState) -> list[str]:
    missing: list[str] = []
    for evidence_id in opinion.cited_evidence:
        ev = state["evidences"].get(evidence_id)
        if ev is None or not ev.found:
            missing.append(evidence_id)
    return missing


def chief_justice_node(state: AgentState) -> dict:
    opinions_by_criterion: dict[str, list[JudicialOpinion]] = defaultdict(list)
    for opinion in state["opinions"]:
        opinions_by_criterion[opinion.criterion_id].append(opinion)

    criteria = state["rubric"].get("dimensions") or state["rubric"].get("criteria") or []
    breakdown: list[CriterionBreakdown] = []
    dissent_log: list[str] = []
    remediation_plan: dict[str, list[str]] = {}
    aggregate_scores: list[int] = []
    security_override_triggered = False

    security_evidence = state["evidences"].get("repo.security_scan")

    for criterion in criteria:
        criterion_id = criterion.get("id", "unknown_criterion")
        criterion_name = criterion.get("name", criterion_id)
        statute = _coerce_statute(criterion.get("statute"))
        criterion_ops = opinions_by_criterion.get(criterion_id, [])

        by_judge = {op.judge: op for op in criterion_ops}
        prosecutor = by_judge.get("Prosecutor")
        defense = by_judge.get("Defense")
        tech_lead = by_judge.get("TechLead")

        # Normalize missing judges to deterministic fallback opinions.
        if prosecutor is None:
            prosecutor = JudicialOpinion(
                judge="Prosecutor",
                criterion_id=criterion_id,
                statute=statute,
                score=1,
                argument="Missing Prosecutor opinion; defaulting to strict score.",
                cited_evidence=[],
            )
        if defense is None:
            defense = JudicialOpinion(
                judge="Defense",
                criterion_id=criterion_id,
                statute=statute,
                score=1,
                argument="Missing Defense opinion; defaulting to minimal score.",
                cited_evidence=[],
            )
        if tech_lead is None:
            tech_lead = JudicialOpinion(
                judge="TechLead",
                criterion_id=criterion_id,
                statute=statute,
                score=1,
                argument="Missing TechLead opinion; defaulting to minimal score.",
                cited_evidence=[],
            )

        judge_opinions = [prosecutor, defense, tech_lead]
        scores = [op.score for op in judge_opinions]
        variance = max(scores) - min(scores)
        violated_rules: list[str] = []

        # Baseline uses all judges.
        base_score = _clamp_score(sum(scores) / 3)

        # Rule of Functionality: architecture criterion is weighted by Tech Lead.
        if "orchestration" in criterion_id.lower() or "architecture" in criterion_name.lower():
            base_score = _clamp_score((tech_lead.score * 2 + prosecutor.score + defense.score) / 4)
            violated_rules.append("functionality_weight")

        # Rule of Evidence (fact supremacy): unsupported defense claims are overruled.
        invalid_defense_citations = _missing_or_unfound_citations(defense, state)
        if invalid_defense_citations:
            base_score = _clamp_score((prosecutor.score + tech_lead.score) / 2)
            violated_rules.append("fact_supremacy")

        # Rule of Security: confirmed vulnerability caps score at 3.
        security_claimed = (
            "security" in prosecutor.argument.lower()
            or "vulnerability" in prosecutor.argument.lower()
            or "repo.security_scan" in prosecutor.cited_evidence
            or "security" in criterion_id.lower()
        )
        if security_evidence is not None and not security_evidence.found and security_claimed:
            base_score = min(base_score, 3)
            security_override_triggered = True
            violated_rules.append("security_override")

        # Variance re-evaluation rule.
        if variance > 2:
            violated_rules.append("variance_re_evaluation")
            prosecutor_cites = set(prosecutor.cited_evidence)
            defense_cites = set(defense.cited_evidence)
            tech_cites = set(tech_lead.cited_evidence)
            shared_cites = sorted(prosecutor_cites & defense_cites & tech_cites)
            valid_shared = [
                evidence_id for evidence_id in shared_cites if state["evidences"].get(evidence_id, None) and state["evidences"][evidence_id].found
            ]
            if valid_shared:
                base_score = _clamp_score((base_score + tech_lead.score) / 2)

        if variance > 2:
            dissent = (
                "High-variance dissent resolved by deterministic re-evaluation. "
                f"Scores P/D/T = {prosecutor.score}/{defense.score}/{tech_lead.score}; "
                f"final={base_score}."
            )
        else:
            dissent = (
                f"Routine dissent summary: P/D/T = {prosecutor.score}/{defense.score}/{tech_lead.score}; "
                f"final={base_score}."
            )
        dissent_log.append(f"{criterion_id}: {dissent}")

        remediation = list(criterion.get("remediation_templates") or [])
        if not remediation:
            remediation = ["Review cited evidence and improve implementation quality for this criterion."]
        if invalid_defense_citations:
            remediation.append(
                "Align defense claims with concrete evidence ids; remove unsupported arguments from judge prompts."
            )
        if "security_override" in violated_rules:
            remediation.append(
                "Fix confirmed security issues first; security findings cap criterion and aggregate scoring."
            )

        remediation_plan[criterion_id] = remediation
        aggregate_scores.append(base_score)

        breakdown.append(
            CriterionBreakdown(
                criterion_id=criterion_id,
                criterion_name=criterion_name,
                statute=statute,
                final_score=base_score,
                judge_opinions=judge_opinions,
                dissent_summary=dissent,
                final_rationale=(
                    "Deterministic synthesis applied with functionality weighting, evidence checks, "
                    "security override, and variance re-evaluation."
                ),
                violated_rules=violated_rules,
                remediation=remediation,
            )
        )

    aggregate_score = sum(aggregate_scores) / max(1, len(aggregate_scores))
    if security_override_triggered:
        aggregate_score = min(aggregate_score, 3.0)
    aggregate_score = max(1.0, round(aggregate_score, 2))

    summary_parts = [
        "Chief Justice synthesis completed with deterministic conflict resolution.",
        "Applied Rule of Evidence and dissent enforcement across all criteria.",
    ]
    if security_override_triggered:
        summary_parts.append("Rule of Security triggered: aggregate score capped at 3.0.")

    report = AuditReport(
        executive_summary=" ".join(summary_parts),
        aggregate_score=aggregate_score,
        criterion_breakdown=breakdown,
        remediation_plan=remediation_plan,
        evidence_index=list(state["evidences"].values()),
        dissent_log=dissent_log,
    )
    final_report = render_audit_report_markdown(report)
    return {
        "audit_report": report,
        "final_report": final_report,
        "logs": ["Chief Justice completed"],
    }
