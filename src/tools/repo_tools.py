from __future__ import annotations

import ast
import subprocess
import tempfile
from difflib import SequenceMatcher
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
            "edge_calls": 0,
            "add_edge_calls": 0,
            "fan_out_sources": [],
            "fan_in_targets": [],
            "summary": "Missing src/graph.py.",
        }

    tree = ast.parse(graph_file.read_text(encoding="utf-8"))
    edges: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and len(node.args) >= 2
        ):
            continue

        if node.func.attr == "add_edge":
            src = _ast_name(node.args[0])
            dst = _ast_name(node.args[1])
            if src and dst:
                edges.append((src, dst))
            continue

        if node.func.attr == "add_conditional_edges":
            src = _ast_name(node.args[0])
            if not src:
                continue

            # Conditional routes may omit explicit path_map; conservatively treat as fan-out.
            if len(node.args) >= 3 and isinstance(node.args[2], ast.Dict):
                for key in node.args[2].keys:
                    dst = _ast_name(key)
                    if dst:
                        edges.append((src, dst))
            else:
                edges.append((src, "__conditional__"))

    source_counts: dict[str, int] = {}
    target_counts: dict[str, int] = {}
    for src, dst in edges:
        source_counts[src] = source_counts.get(src, 0) + 1
        target_counts[dst] = target_counts.get(dst, 0) + 1

    fan_out = sorted(k for k, v in source_counts.items() if v > 1)
    fan_in = sorted(k for k, v in target_counts.items() if v > 1)
    return {
        "exists": True,
        "edge_calls": len(edges),
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

        edge_calls = int(analysis["edge_calls"])
        fan_out = analysis.get("fan_out_sources", [])
        fan_in = analysis.get("fan_in_targets", [])
        found = edge_calls >= 4 and bool(fan_out) and bool(fan_in)
        return Evidence(
            id="repo.graph_wiring",
            goal="Verify fan-out/fan-in graph topology.",
            found=found,
            content=str(analysis["summary"]),
            location=str(repo_path / "src/graph.py"),
            rationale="AST traversal inspected edge and conditional-edge wiring with fan-out/fan-in signals.",
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
                            and getattr(k.value, "value", False) is True
                            for k in node.keywords
                        )
                        if shell_true:
                            risky_hits.append(f"{file}:subprocess.run(shell=True)")
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


def _load_source(repo_path: Path, relative_path: str) -> str | None:
    file_path = repo_path / relative_path
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8", errors="ignore")


def _extract_judge_prompts(source: str) -> dict[str, str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    prompts: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "_judge_system_prompt":
            continue
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.If):
                test = stmt.test
                if (
                    isinstance(test, ast.Compare)
                    and isinstance(test.left, ast.Name)
                    and test.left.id == "judge"
                    and len(test.comparators) == 1
                    and isinstance(test.comparators[0], ast.Constant)
                    and isinstance(test.comparators[0].value, str)
                ):
                    persona = test.comparators[0].value
                    if stmt.body and isinstance(stmt.body[0], ast.Return):
                        prompt = _literal_string_from_node(stmt.body[0].value)
                        if prompt:
                            prompts[persona] = prompt
        # Default return (TechLead in current implementation)
        for stmt in node.body:
            if isinstance(stmt, ast.Return):
                default_prompt = _literal_string_from_node(stmt.value)
                if default_prompt:
                    prompts.setdefault("TechLead", default_prompt)
    return prompts


def _literal_string_from_node(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
        return "".join(parts) if parts else None
    return None


def protocol_judicial_personas(target: str) -> Evidence:
    try:
        repo_path, temp_dir = resolve_repo(target)
    except Exception as exc:
        return Evidence(
            id="repo.judicial_personas",
            goal="Verify distinct Prosecutor/Defense/TechLead judicial personas.",
            found=False,
            location=target,
            rationale=f"Repository resolution failed: {exc}",
            confidence=1.0,
            tags=["judicial", "persona", "repo_access_error"],
        )
    try:
        source = _load_source(repo_path, "src/nodes/judges.py")
        if source is None:
            return Evidence(
                id="repo.judicial_personas",
                goal="Verify distinct Prosecutor/Defense/TechLead judicial personas.",
                found=False,
                location=str(repo_path / "src/nodes/judges.py"),
                rationale="Missing src/nodes/judges.py.",
                confidence=0.98,
                tags=["judicial", "persona"],
            )

        prompts = _extract_judge_prompts(source)
        prosecutor = prompts.get("Prosecutor", "")
        defense = prompts.get("Defense", "")
        tech = prompts.get("TechLead", "")
        if not (prosecutor and defense and tech):
            return Evidence(
                id="repo.judicial_personas",
                goal="Verify distinct Prosecutor/Defense/TechLead judicial personas.",
                found=False,
                location=str(repo_path / "src/nodes/judges.py"),
                rationale="Could not extract all three persona prompts.",
                confidence=0.9,
                tags=["judicial", "persona"],
            )

        p_d = SequenceMatcher(None, prosecutor, defense).ratio()
        p_t = SequenceMatcher(None, prosecutor, tech).ratio()
        d_t = SequenceMatcher(None, defense, tech).ratio()
        max_similarity = max(p_d, p_t, d_t)

        has_keywords = (
            "aggressively" in prosecutor.lower()
            and "tradeoff" in defense.lower()
            and "maintainability" in tech.lower()
        )
        found = max_similarity < 0.85 and has_keywords
        return Evidence(
            id="repo.judicial_personas",
            goal="Verify distinct Prosecutor/Defense/TechLead judicial personas.",
            found=found,
            content=f"max_similarity={max_similarity:.2f}, keyword_profile={has_keywords}",
            location=str(repo_path / "src/nodes/judges.py"),
            rationale="Prompt distinctness and role-keyword profile were checked for persona separation.",
            confidence=0.88 if found else 0.8,
            tags=["judicial", "persona", "dialectics"],
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def protocol_structured_output_contract(target: str) -> Evidence:
    try:
        repo_path, temp_dir = resolve_repo(target)
    except Exception as exc:
        return Evidence(
            id="repo.structured_output",
            goal="Verify schema-enforced structured judge outputs.",
            found=False,
            location=target,
            rationale=f"Repository resolution failed: {exc}",
            confidence=1.0,
            tags=["structured_output", "repo_access_error"],
        )
    try:
        source = _load_source(repo_path, "src/nodes/judges.py")
        if source is None:
            return Evidence(
                id="repo.structured_output",
                goal="Verify schema-enforced structured judge outputs.",
                found=False,
                location=str(repo_path / "src/nodes/judges.py"),
                rationale="Missing src/nodes/judges.py.",
                confidence=0.98,
                tags=["structured_output"],
            )
        has_structured = "with_structured_output(JudicialOpinion)" in source
        has_fallback = "except Exception" in source and "_heuristic_score" in source
        found = has_structured and has_fallback
        return Evidence(
            id="repo.structured_output",
            goal="Verify schema-enforced structured judge outputs.",
            found=found,
            content=f"with_structured_output={has_structured}, fallback={has_fallback}",
            location=str(repo_path / "src/nodes/judges.py"),
            rationale="Searched for structured-output binding and parse-failure fallback path.",
            confidence=0.9 if found else 0.82,
            tags=["structured_output", "judicial"],
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def protocol_chief_justice_rules(target: str) -> Evidence:
    try:
        repo_path, temp_dir = resolve_repo(target)
    except Exception as exc:
        return Evidence(
            id="repo.chief_justice_rules",
            goal="Verify deterministic Chief Justice synthesis rules are implemented.",
            found=False,
            location=target,
            rationale=f"Repository resolution failed: {exc}",
            confidence=1.0,
            tags=["justice", "synthesis", "repo_access_error"],
        )
    try:
        source = _load_source(repo_path, "src/nodes/justice.py")
        if source is None:
            return Evidence(
                id="repo.chief_justice_rules",
                goal="Verify deterministic Chief Justice synthesis rules are implemented.",
                found=False,
                location=str(repo_path / "src/nodes/justice.py"),
                rationale="Missing src/nodes/justice.py.",
                confidence=0.98,
                tags=["justice", "synthesis"],
            )

        required_markers = [
            "functionality_weight",
            "fact_supremacy",
            "security_override",
            "variance_re_evaluation",
            "dissent",
        ]
        present = [marker for marker in required_markers if marker in source]
        found = len(present) >= 4
        return Evidence(
            id="repo.chief_justice_rules",
            goal="Verify deterministic Chief Justice synthesis rules are implemented.",
            found=found,
            content=f"present_markers={','.join(present)}",
            location=str(repo_path / "src/nodes/justice.py"),
            rationale="Static check for explicit deterministic rule markers in Chief Justice node.",
            confidence=0.9 if found else 0.8,
            tags=["justice", "synthesis", "deterministic_rules"],
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def protocol_vision_implementation(target: str) -> Evidence:
    try:
        repo_path, temp_dir = resolve_repo(target)
    except Exception as exc:
        return Evidence(
            id="repo.vision_implementation",
            goal="Verify VisionInspector implementation exists and is wired.",
            found=False,
            location=target,
            rationale=f"Repository resolution failed: {exc}",
            confidence=1.0,
            tags=["vision", "implementation", "repo_access_error"],
        )
    try:
        doc_tools = _load_source(repo_path, "src/tools/doc_tools.py") or ""
        detectives = _load_source(repo_path, "src/nodes/detectives.py") or ""

        has_protocol = "def protocol_visual_audit" in doc_tools
        has_node = "def run_vision_inspector" in detectives
        has_wiring_call = "protocol_visual_audit" in detectives
        found = has_protocol and has_node and has_wiring_call
        return Evidence(
            id="repo.vision_implementation",
            goal="Verify VisionInspector implementation exists and is wired.",
            found=found,
            content=f"protocol={has_protocol}, node={has_node}, wiring={has_wiring_call}",
            location=str(repo_path / "src/nodes/detectives.py"),
            rationale="Checked implementation and wiring presence for vision pipeline.",
            confidence=0.9 if found else 0.82,
            tags=["vision", "implementation"],
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()
