#!/usr/bin/env python3
"""
Simple helper to upload an audit report to LangSmith.

Usage (run locally after setting your API key):

  export LANGSMITH_API_KEY="<your_key_here>"
  python3 scripts/langsmith_upload.py reports/final_report.md

The script reads the report file and posts a minimal JSON payload to the
LangSmith runs endpoint. It requires the `requests` package. If you prefer
to use the official LangSmith SDK, adapt this script accordingly.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

try:
    import requests
except Exception as e:
    print("This script requires the 'requests' package. Install with: pip install requests")
    raise


def main(argv: list[str]) -> int:
    api_key = os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        print("ERROR: Set LANGSMITH_API_KEY environment variable before running.")
        return 2

    report_path = argv[1] if len(argv) > 1 else "reports/final_report.md"
    p = pathlib.Path(report_path)
    if not p.exists():
        print(f"ERROR: Report file not found: {report_path}")
        return 3

    content = p.read_text(encoding="utf-8")

    payload = {
        "name": p.name,
        "type": "audit_report",
        "content": content,
        "metadata": {"uploader": os.environ.get("USER", "local"), "source": "auditor"},
    }

    endpoint = os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com/api/v1/runs")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "langsmith-uploader/1.0 (+https://github.com)",
    }

    print("Posting report to LangSmith endpoint:", endpoint)
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=30)
    except Exception as e:
        print("Network error while contacting LangSmith:", e)
        return 4

    print("HTTP status:", resp.status_code)
    # Prefer JSON output when available
    try:
        j = resp.json()
        print(json.dumps(j, indent=2))
        # Attempt to surface a run id or URL if present
        run_id = j.get("id") or j.get("run_id") or j.get("tr_uuid")
        if run_id:
            print("Open the run in the browser:", f"https://api.langsmith.ai/v1/runs?tr_uuid={run_id}")
        return 0
    except Exception:
        text = resp.text
        print(text)
        # Try to extract a tr_uuid from HTML redirect links if present
        import re

        m = re.search(r"tr_uuid=([0-9a-fA-F\-]+)", text)
        if m:
            tr = m.group(1)
            run_url = f"https://api.langsmith.ai/v1/runs?tr_uuid={tr}"
            print("Detected run redirect URL (open in browser):", run_url)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
