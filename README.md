# Automaton Auditor - Final Submission

Digital Courtroom governance swarm for auditing a target Week 2 repository and report PDF.

## What This Project Does

Input:
- Target repository URL or local path
- Architectural PDF report
- Rubric JSON

Process:
- Detectives run in parallel and produce structured `Evidence`
- Judges run in parallel and produce structured `JudicialOpinion`
- Chief Justice applies deterministic conflict-resolution rules and emits an `AuditReport`

Output:
- Final markdown audit report (`final_report` in graph state)
- JSON serialization of evidence, opinions, and report

## Final Architecture

Core flow:
- `START -> [RepoInvestigator || OrchestrationPrecheck || VisionInspector]`
- `OrchestrationPrecheck -> [DocAnalyst | DocSkipped]`
- `Detective fan-in -> EvidenceAggregator -> OrchestrationPostcheck`
- `OrchestrationPostcheck -> [Prosecutor || Defense || TechLead]` or `MissingArtifactsHandler`
- `Judge fan-in -> ChiefJustice -> END`

Key files:
- `src/state.py` - finalized typed state + reducers
- `src/tools/repo_tools.py` - sandboxed clone + AST graph forensics + safety scan
- `src/tools/doc_tools.py` - PDF parsing, chunked retrieval, cross-reference, vision audit
- `src/nodes/detectives.py` - RepoInvestigator, DocAnalyst, VisionInspector, aggregator
- `src/nodes/judges.py` - persona judges with structured outputs
- `src/nodes/justice.py` - deterministic Chief Justice synthesis rules
- `src/graph.py` - full LangGraph wiring with parallel fan-out/fan-in and conditional routing

## Deterministic Justice Rules

Implemented in `src/nodes/justice.py`:
- `security_override`: confirmed security risk caps scoring
- `fact_supremacy`: unsupported defense claims are overruled by evidence facts
- `functionality_weight`: architecture-oriented criteria weight Tech Lead opinion
- `variance_re_evaluation`: high score variance triggers deterministic re-check logic
- `dissent_requirement`: explicit dissent summary is recorded per criterion

## Setup

```bash
uv sync --frozen
cp .env.example .env
```

## Environment Variables

Required or commonly used variables:
- `LLM_PROVIDER=auto|ollama|grok|openai|gemini`
- `OLLAMA_BASE_URL` (default `http://localhost:11434`)
- `OLLAMA_MODEL` (default `llama3:8b`)
- `GROK_API_KEY`, `GROK_BASE_URL`, `GROK_MODEL`
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE`, `OPENAI_MODEL_OVERRIDE`
- `GEMINI_API_KEY`, `GEMINI_MODEL` (used by VisionInspector image validation)
- `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`

## Run

Self-audit (final report paths):
```bash
uv run auditor \
  --repo . \
  --report reports/final_report.pdf \
  --rubric rubric/week2_rubric.json \
  --out audit/report_onself_generated/final_report.md \
  --out-json audit/report_onself_generated/final_report.json
```

Peer-audit:
```bash
uv run auditor \
  --repo https://github.com/<peer>/<repo>.git \
  --report /absolute/path/to/peer_report.pdf \
  --rubric rubric/week2_rubric.json \
  --out audit/report_onpeer_generated/final_report.md \
  --out-json audit/report_onpeer_generated/final_report.json
```

## Required Audit Artifacts

- `audit/report_onself_generated/` - self-generated markdown report
- `audit/report_onpeer_generated/` - report generated on assigned peer repository
- `audit/report_bypeer_received/` - markdown report received from peer's agent
- `reports/final_report.pdf` - final architecture report PDF for peer auditing

## Reproducibility

- Locked dependencies: `uv.lock`
- Automation helpers: `Makefile`
- CI checks: `.github/workflows/ci.yml` (`uv sync --frozen`, lint, compile, smoke run)

## LangSmith Trace

Set:
```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your_key>
export LANGCHAIN_PROJECT=automaton-auditor
```

Then run the auditor and share the resulting trace URL in your submission.
