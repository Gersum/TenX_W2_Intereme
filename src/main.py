from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .graph import build_graph, load_rubric
from .reporting import render_detective_report, write_report
from .state import AgentState
from .tools.repo_tools import is_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Digital Courtroom governance swarm.")
    parser.add_argument("--repo", required=True, help="Local repo path or git URL to audit.")
    parser.add_argument("--report", default=None, help="Optional PDF report path.")
    parser.add_argument("--rubric", default=None, help="Optional rubric JSON path.")
    parser.add_argument(
        "--out",
        default="audit/report_onself_generated/final_report.md",
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--out-json",
        default="audit/report_onself_generated/final_report.json",
        help="JSON output path.",
    )
    return parser.parse_args()


def validate_inputs(args: argparse.Namespace) -> None:
    repo_target = (args.repo or "").strip()
    if not repo_target:
        raise ValueError("--repo cannot be empty.")
    if not is_url(repo_target):
        repo_path = Path(repo_target)
        if not repo_path.exists():
            raise ValueError(f"Local repo path does not exist: {repo_target}")

    if args.report:
        report_path = Path(args.report)
        if report_path.suffix.lower() != ".pdf":
            raise ValueError(f"--report must point to a .pdf file: {args.report}")
        if not report_path.exists():
            raise ValueError(f"Report file not found: {args.report}")

    if args.rubric:
        rubric_path = Path(args.rubric)
        if not rubric_path.exists():
            raise ValueError(f"Rubric file not found: {args.rubric}")
        try:
            payload = json.loads(rubric_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Rubric file is not valid JSON: {args.rubric} ({exc})") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Rubric JSON must be an object/dict: {args.rubric}")


def main() -> None:
    load_dotenv()
    args = parse_args()
    try:
        validate_inputs(args)
    except ValueError as exc:
        raise SystemExit(f"Input validation error: {exc}") from exc
    app = build_graph()
    initial_state: AgentState = {
        "repo_url": args.repo,
        "pdf_path": args.report,
        "rubric": load_rubric(args.rubric),
        "evidences": {},
        "opinions": [],
        "routing": {},
        "logs": [],
        "audit_report": None,
        "final_report": None,
    }
    result = app.invoke(initial_state)
    evidences = result.get("evidences", {})
    logs = result.get("logs", [])
    audit_report = result.get("audit_report")
    final_report = result.get("final_report")

    if final_report:
        write_report(args.out, final_report)
    else:
        render_detective_report(args.repo, args.report, evidences, logs, args.out)

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    json_data = {
        "repo_url": args.repo,
        "pdf_path": args.report,
        "evidences": {k: v.model_dump() for k, v in evidences.items()},
        "logs": logs,
    }
    if audit_report:
        json_data["audit_report"] = audit_report.model_dump()

    out_json.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"JSON written to {args.out_json}")
    if audit_report:
        print("\n--- CHIEF JUSTICE FINAL VERDICT ---")
        print(f"Total Score: {audit_report.aggregate_score} / 5.0")
        print(f"Summary: {audit_report.executive_summary}")
        print("-----------------------------------")


if __name__ == "__main__":
    main()
