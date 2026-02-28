from __future__ import annotations

import argparse
from pathlib import Path

from langchain_core.runnables.graph_mermaid import MermaidDrawMethod

from .graph import build_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export LangGraph visualization artifacts.")
    parser.add_argument(
        "--out-mermaid",
        default="reports/stategraph.mmd",
        help="Path to write Mermaid graph text.",
    )
    parser.add_argument(
        "--out-png",
        default="reports/stategraph.png",
        help="Path to write PNG graph image (best effort).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = build_graph()
    graph = app.get_graph()

    mermaid = graph.draw_mermaid()
    out_mermaid = Path(args.out_mermaid)
    out_mermaid.parent.mkdir(parents=True, exist_ok=True)
    out_mermaid.write_text(mermaid, encoding="utf-8")
    print(f"Mermaid graph written to {out_mermaid}")

    out_png = Path(args.out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    try:
        png = graph.draw_mermaid_png(draw_method=MermaidDrawMethod.PYPPETEER)
        out_png.write_bytes(png)
        print(f"PNG graph written to {out_png}")
    except Exception as exc:
        print(f"PNG rendering skipped: {exc}")


if __name__ == "__main__":
    main()
