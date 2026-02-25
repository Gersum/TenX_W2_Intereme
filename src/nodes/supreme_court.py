from __future__ import annotations

from collections import defaultdict

from ..models import CriterionVerdict, FinalVerdict
from ..state import AgentState


def _security_cap_triggered(state: AgentState) -> bool:
    ev = state["evidences"].get("repo.security_scan")
    if not ev:
        return False
    # Security evidence uses found=True when no risky patterns are discovered.
    return ev.found is False


def chief_justice_node(state: AgentState) -> dict:
    opinions_by_criterion = defaultdict(list)
    for op in state["opinions"]:
        opinions_by_criterion[op.criterion_id].append(op)

    criteria_verdicts: list[CriterionVerdict] = []
    dissent_log: list[str] = []
    score_accumulator: list[int] = []

    rubric = state["rubric"]
    criteria_list = rubric.get("dimensions") or rubric.get("criteria") or []
    for criterion in criteria_list:
        cid = criterion["id"]
        ops = opinions_by_criterion.get(cid, [])
        if not ops:
            criteria_verdicts.append(
                CriterionVerdict(
                    criterion_id=cid,
                    score=1,
                    rationale="No judicial opinions emitted.",
                    dissent="Insufficient evidence/opinion coverage.",
                    violated_rules=["Rule of Evidence"],
                    remediation=["Ensure all judges run for all criteria."],
                )
            )
            score_accumulator.append(1)
            continue

        prosecutor = next((o for o in ops if o.judge == "Prosecutor"), None)
        defense = next((o for o in ops if o.judge == "Defense"), None)
        techlead = next((o for o in ops if o.judge == "TechLead"), None)
        base_score = techlead.score if techlead else round(sum(o.score for o in ops) / len(ops))

        rationale = (
            f"TechLead weighted for functionality. Prosecutor={prosecutor.score if prosecutor else 'NA'}, "
            f"Defense={defense.score if defense else 'NA'}, TechLead={techlead.score if techlead else 'NA'}."
        )
        dissent = (
            f"Disagreement: Prosecutor argued '{prosecutor.argument[:120] if prosecutor else 'N/A'}' vs "
            f"Defense argued '{defense.argument[:120] if defense else 'N/A'}'."
        )
        dissent_log.append(dissent)

        remediation = criterion.get("remediation_templates", ["Address cited evidence gaps and re-run audit."])
        criteria_verdicts.append(
            CriterionVerdict(
                criterion_id=cid,
                score=max(1, min(5, int(base_score))),
                rationale=rationale,
                dissent=dissent,
                violated_rules=[],
                remediation=remediation,
            )
        )
        score_accumulator.append(max(1, min(5, int(base_score))))

    final_score = sum(score_accumulator) / max(1, len(score_accumulator))
    if _security_cap_triggered(state):
        final_score = min(final_score, 3.0)

    final_score = max(1.0, final_score)
    verdict_data = {
        "total_score": round(final_score, 2),
        "executive_summary": (
            "Deterministic synthesis complete. Fact supremacy enforced; "
            "security risks cap maximum score to 3.0."
        ),
        "criteria": [c.model_dump() for c in criteria_verdicts],
        "evidence_index": [e.model_dump() if hasattr(e, "model_dump") else e for e in state["evidences"].values()],
        "dissent_log": dissent_log,
    }
    verdict = FinalVerdict.model_validate(verdict_data)
    return {"final_verdict": verdict, "logs": ["Chief Justice completed"]}

