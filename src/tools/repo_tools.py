from __future__ import annotations

import ast
import subprocess
import tempfile
from pathlib import Path

from ..state import Evidence


def is_url(target: str) -> bool:
    return target.startswith("http://") or target.startswith("https://") or target.endswith(".git")


def resolve_repo(target: str) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if is_url(target):
        temp_dir = tempfile.TemporaryDirectory()
        repo_path = Path(temp_dir.name) / "repo"
        proc = subprocess.run(
            ["git", "clone", "--depth", "200", target, str(repo_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            temp_dir.cleanup()
            raise RuntimeError((proc.stderr or proc.stdout or "git clone failed").strip())
        return repo_path, temp_dir
    return Path(target).resolve(), None


def _find_state_file(repo_path: Path) -> Path | None:
    for rel in ("src/state.py", "src/graph.py"):
        candidate = repo_path / rel
        if candidate.exists():
            return candidate
    return None


def analyze_graph_structure(path: str) -> dict[str, object]:
    graph_file = Path(path) / "src/graph.py"
    if not graph_file.exists():
        return {
            "exists": False,
            "add_edge_calls": 0,
            "fan_out_sources": [],
            "fan_in_targets": [],
            "summary": "Missing src/graph.py.",
        }

    tree = ast.parse(graph_file.read_text(encoding="utf-8"))
    edges: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_edge"
            and len(node.args) >= 2
        ):
            src = _ast_name(node.args[0])
            dst = _ast_name(node.args[1])
            if src and dst:
                edges.append((src, dst))

    source_counts: dict[str, int] = {}
    target_counts: dict[str, int] = {}
    for src, dst in edges:
        source_counts[src] = source_counts.get(src, 0) + 1
        target_counts[dst] = target_counts.get(dst, 0) + 1

    fan_out = sorted(k for k, v in source_counts.items() if v > 1)
    fan_in = sorted(k for k, v in target_counts.items() if v > 1)
    return {
        "exists": True,
        "add_edge_calls": len(edges),
        "fan_out_sources": fan_out,
        "fan_in_targets": fan_in,
        "summary": f"edges={len(edges)}, fan_out={fan_out}, fan_in={fan_in}",
    }


def extract_git_history(path: str, max_count: int = 25) -> list[dict[str, str]]:
    proc = subprocess.run(
        [
            "git",
            "-C",
            path,
            "log",
            "--oneline",
            "--reverse",
            f"--max-count={max_count}",
            "--date=iso-strict",
            "--pretty=%h|%ad|%s",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []

    commits: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", maxsplit=2)
        if len(parts) != 3:
            continue
        commit_hash, timestamp, message = parts
        commits.append(
            {
                "hash": commit_hash.strip(),
                "timestamp": timestamp.strip(),
                "message": message.strip(),
            }
        )
    return commits


def _ast_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    return None


def protocol_state_structure(target: str) -> Evidence:
    try:
        repo_path, temp_dir = resolve_repo(target)
    except Exception as exc:
        return Evidence(
            id="repo.state_structure",
            goal="Verify typed state definitions.",
            found=False,
            location=target,
            rationale=f"Repository resolution failed: {exc}",
            confidence=1.0,
            tags=["orchestration", "state", "repo_access_error"],
        )
    try:
        state_file = _find_state_file(repo_path)
        if not state_file:
            return Evidence(
                id="repo.state_structure",
                goal="Verify typed state definitions.",
                found=False,
                location=str(repo_path),
                rationale="Neither src/state.py nor src/graph.py exists.",
                confidence=0.98,
                tags=["orchestration", "state"],
            )

        source = state_file.read_text(encoding="utf-8")
        typed_hints = ("TypedDict", "BaseModel", "Annotated")
        has_typed_state = any(hint in source for hint in typed_hints)

        return Evidence(
            id="repo.state_structure",
            goal="Verify typed state definitions.",
            found=has_typed_state,
            content=f"checked={state_file.name}",
            location=str(state_file),
            rationale="Typed state markers searched: TypedDict/BaseModel/Annotated.",
            confidence=0.92 if has_typed_state else 0.9,
            tags=["orchestration", "state"],
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def protocol_graph_wiring(target: str) -> Evidence:
    try:
        repo_path, temp_dir = resolve_repo(target)
    except Exception as exc:
        return Evidence(
            id="repo.graph_wiring",
            goal="Verify fan-out/fan-in graph topology.",
            found=False,
            location=target,
            rationale=f"Repository resolution failed: {exc}",
            confidence=1.0,
            tags=["orchestration", "parallelism", "repo_access_error"],
        )
    try:
        analysis = analyze_graph_structure(str(repo_path))
        if analysis["exists"] is False:
            return Evidence(
                id="repo.graph_wiring",
                goal="Verify fan-out/fan-in graph topology.",
                found=False,
                location=str(repo_path / "src/graph.py"),
                rationale="Missing src/graph.py.",
                confidence=0.98,
                tags=["orchestration", "parallelism"],
            )

        add_edge_calls = int(analysis["add_edge_calls"])
        fan_out = analysis.get("fan_out_sources", [])
        fan_in = analysis.get("fan_in_targets", [])
        found = add_edge_calls >= 4 and bool(fan_out) and bool(fan_in)
        return Evidence(
            id="repo.graph_wiring",
            goal="Verify fan-out/fan-in graph topology.",
            found=found,
            content=str(analysis["summary"]),
            location=str(repo_path / "src/graph.py"),
            rationale="AST traversal inspected add_edge wiring and fan-out/fan-in signals.",
            confidence=0.85 if found else 0.8,
            tags=["orchestration", "parallelism"],
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def protocol_git_narrative(target: str) -> Evidence:
    try:
        repo_path, temp_dir = resolve_repo(target)
    except Exception as exc:
        return Evidence(
            id="repo.git_narrative",
            goal="Assess whether engineering happened in atomic increments.",
            found=False,
            location=target,
            rationale=f"Repository resolution failed: {exc}",
            confidence=1.0,
            tags=["effort", "process", "git", "repo_access_error"],
        )
    try:
        commits = extract_git_history(str(repo_path))
        commit_count = len(commits)
        found = commit_count >= 4
        sample = "\n".join(
            f"{c['hash']} {c['timestamp']} {c['message']}"
            for c in commits[:5]
        )
        return Evidence(
            id="repo.git_narrative",
            goal="Assess whether engineering happened in atomic increments.",
            found=found,
            content=sample,
            location="git log",
            rationale=">=4 recent commits treated as minimal iterative signal.",
            confidence=0.7,
            tags=["effort", "process", "git"],
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def protocol_security_scan(target: str) -> Evidence:
    try:
        repo_path, temp_dir = resolve_repo(target)
    except Exception as exc:
        return Evidence(
            id="repo.security_scan",
            goal="Identify risky command execution patterns.",
            found=False,
            location=target,
            rationale=f"Repository resolution failed: {exc}",
            confidence=1.0,
            tags=["security", "repo_access_error"],
        )
    try:
        risky_hits: list[str] = []
        excluded_dirs = {".venv", "venv", ".git", "__pycache__", "site-packages", "node_modules"}
        for file in repo_path.rglob("*.py"):
            if any(part in excluded_dirs for part in file.parts):
                continue
            text = file.read_text(encoding="utf-8", errors="ignore")
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                if isinstance(fn, ast.Attribute):
                    if (
                        isinstance(fn.value, ast.Name)
                        and fn.value.id == "os"
                        and fn.attr == "system"
                    ):
                        risky_hits.append(f"{file}:os.system")
                    if (
                        isinstance(fn.value, ast.Name)
                        and fn.value.id == "subprocess"
                        and fn.attr == "run"
                    ):
                        shell_true = any(
                            isinstance(k, ast.keyword)
                            and k.arg == "shell"
                            and isinstance(k.value, ast.Constant)
                            and k.value.value is True
                            for k in node.keywords
                        )
                        dynamic_cmd = False
                        if node.args:
                            cmd_arg = node.args[0]
                            dynamic_cmd = isinstance(cmd_arg, (ast.JoinedStr, ast.BinOp, ast.Call, ast.Name))
                        if shell_true or dynamic_cmd:
                            risky_hits.append(f"{file}:subprocess.run(shell=True/dynamic)")
                if isinstance(fn, ast.Name) and fn.id in {"eval", "exec"}:
                    risky_hits.append(f"{file}:{fn.id}")
        found = len(risky_hits) == 0
        return Evidence(
            id="repo.security_scan",
            goal="Identify risky command execution patterns.",
            found=found,
            content="\n".join(risky_hits[:20]) if risky_hits else "No risky patterns matched.",
            location=str(repo_path),
            rationale="Pattern scan for unsafe execution primitives.",
            confidence=0.75,
            tags=["security"],
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()
