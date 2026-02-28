# Auditor Best Practices Playbook

This document captures practical guardrails applied from remediation priorities.

## 1) Git Forensic Analysis

- Use atomic commits with one intent per commit (`feat`, `fix`, `chore`, `docs`).
- Keep commit messages action-oriented and subsystem-specific.
- Preserve progression order: setup -> tools -> graph -> judges -> justice -> docs.
- Avoid bulk "upload all changes" commits.

## 2) State Management Rigor

- Keep all shared graph state in typed models (`Pydantic` + `TypedDict`).
- Use reducers for parallel writes:
  - `operator.add` for list accumulation (`opinions`, `logs`)
  - `operator.ior` for map merges (`evidences`, `routing`)
- Keep scoring ranges constrained (`score: 1..5`, `confidence: 0..1`).

## 3) Graph Orchestration Architecture

- Maintain explicit dual fan-out/fan-in:
  - Detectives fan-out, aggregate, then route
  - Judges fan-out, then Chief Justice fan-in
- Keep conditional edges for degraded paths:
  - missing artifacts / failed clone / missing report
- Ensure graph has a deterministic END path for both success and failure.

## 4) Safe Tool Engineering

- Clone remote repos only in `tempfile.TemporaryDirectory`.
- Prefer `subprocess.run(..., capture_output=True, text=True, check=False)` with explicit return-code checks.
- Never use raw `os.system()`.
- Parse code structure via `ast`, not brittle regex for architecture checks.

## 5) Structured Output Enforcement

- Bind judge outputs to `JudicialOpinion` schema using `.with_structured_output(...)`.
- Clamp and validate scores before state merge.
- Keep persona prompts distinct to avoid role collapse.
- Fallback to deterministic heuristics when model output is malformed/unavailable.
