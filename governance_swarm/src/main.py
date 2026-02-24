from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .graph import build_graph, load_rubric
from .reporting import render_detective_report
from .state import AgentState


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Digital Courtroom detective graph.")
    parser.add_argument("--repo", required=True, help="Local repo path or git URL to audit.")
    parser.add_argument("--report", default=None, help="Optional PDF report path.")
    parser.add_argument("--rubric", default=None, help="Optional rubric JSON path.")
    parser.add_argument("--out", default="audit/interim_detective_report.md", help="Markdown report output path.")
    parser.add_argument("--out-json", default="audit/interim_detective_report.json", help="JSON output path.")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    app = build_graph()
    initial_state: AgentState = {
        "repo_url": args.repo,
        "pdf_path": args.report,
        "rubric": load_rubric(args.rubric),
        "evidences": {},
        "opinions": [],
        "logs": [],
    }
    result = app.invoke(initial_state)
    evidences = result.get("evidences", {})
    logs = result.get("logs", [])

    render_detective_report(args.repo, args.report, evidences, logs, args.out)
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(
            {
                "repo_url": args.repo,
                "pdf_path": args.report,
                "evidences": {k: v.model_dump() for k, v in evidences.items()},
                "logs": logs,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Report written to {args.out}")
    print(f"JSON written to {args.out_json}")


if __name__ == "__main__":
    main()
