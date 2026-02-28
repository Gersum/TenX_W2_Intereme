from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def load_env(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, value = s.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def request_json(url: str, api_key: str, method: str = "GET", payload: dict | None = None):
    command = [
        "curl",
        "-sS",
        "-X",
        method,
        "-H",
        f"x-api-key: {api_key}",
        "-H",
        "Accept: application/json",
        "-H",
        "Content-Type: application/json",
        "-w",
        "\n%{http_code}",
        url,
    ]
    if payload is not None:
        command.extend(["-d", json.dumps(payload)])

    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "curl failed")

    output = proc.stdout
    if "\n" not in output:
        raise RuntimeError("unexpected curl output")
    body, status_text = output.rsplit("\n", 1)
    status = int(status_text.strip())
    if status >= 400:
        raise RuntimeError(f"HTTP {status}: {body[:200]}")
    return json.loads(body)


def main() -> int:
    load_env()
    endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com").rstrip("/")
    api_key = os.getenv("LANGSMITH_API_KEY", "")
    project = os.getenv("LANGSMITH_PROJECT", "")

    if not api_key:
        print("LANGSMITH_API_KEY missing. Set it in .env or your shell.")
        return 1

    try:
        sessions_url = f"{endpoint}/api/v1/sessions?limit=100"
        sessions = request_json(sessions_url, api_key)
    except Exception as exc:
        print(f"Unable to reach LangSmith API: {exc}")
        return 1

    if not isinstance(sessions, list) or not sessions:
        print("No LangSmith sessions/projects found for this key.")
        return 1

    session = None
    if project:
        for candidate in sessions:
            if candidate.get("name") == project:
                session = candidate
                break
    if session is None:
        session = sessions[0]

    session_id = session.get("id")
    session_name = session.get("name", "<unnamed>")
    if not session_id:
        print("Unable to resolve a valid session id.")
        return 1

    try:
        runs_url = f"{endpoint}/api/v1/runs/query"
        runs_payload = {"session": [session_id], "limit": 5}
        runs = request_json(runs_url, api_key, method="POST", payload=runs_payload)
    except Exception as exc:
        print(f"Unable to query runs: {exc}")
        return 1

    if isinstance(runs, dict) and "runs" in runs:
        runs_list = runs["runs"]
    elif isinstance(runs, list):
        runs_list = runs
    else:
        runs_list = []

    print(f"Project: {session_name}")
    if not runs_list:
        print("No runs found yet. Execute an audited run with tracing enabled, then run make trace-check again.")
        return 0

    print("Latest run URLs:")
    for run in runs_list[:3]:
        run_id = run.get("id")
        app_path = run.get("app_path")
        if app_path:
            print(f"- https://smith.langchain.com{app_path}")
        elif run_id:
            print(f"- https://smith.langchain.com/r/{run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
