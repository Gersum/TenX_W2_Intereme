# Automaton Auditor (Digital Courtroom)

Week 2 interim implementation of a LangGraph-based detective swarm focused on forensic evidence collection.

Current scope:

- RepoInvestigator (repository forensics)
- DocAnalyst (PDF/report forensics)
- EvidenceAggregator fan-in synchronization node

## Architecture

- `src/state.py`: Pydantic/TypedDict definitions for `Evidence`, `JudicialOpinion`, and `AgentState` with reducers.
- `src/tools/repo_tools.py`: Sandboxed `git clone`, git history extraction, AST-based graph analysis.
- `src/tools/doc_tools.py`: PDF ingestion and chunked querying (RAG-lite).
- `src/nodes/detectives.py`: LangGraph nodes for RepoInvestigator + DocAnalyst + EvidenceAggregator.
- `src/graph.py`: Partial StateGraph wiring detectives in parallel (fan-out) then fan-in aggregator.

## Setup (uv)

```bash
uv sync --frozen
cp .env.example .env
```

Set `.env` values as needed:

- `LLM_PROVIDER` (`auto`, `openai`, or `ollama`; defaults to `auto`)
- `OLLAMA_MODEL` (for local Ollama, e.g. `deepseek-r1:8b`)
- `OLLAMA_BASE_URL` (defaults to `http://localhost:11434`)
- `OPENAI_API_KEY` + `OPENAI_MODEL` (used when provider is `openai` or `auto` with key present)
- `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE`, `OPENAI_MODEL_OVERRIDE` (optional legacy cloud config)
- `GEMINI_API_KEY` (for future VisionInspector node)
- `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` for LangSmith

## Run

Audit a local repo:

```bash
uv run auditor --repo . --rubric rubric/week2_rubric.json
```

Audit a git URL:

```bash
uv run auditor --repo https://github.com/org/repo.git --report /path/to/report.pdf --rubric rubric/week2_rubric.json
```

Use local Ollama for judge LLMs (future judicial graph stage):

```bash
ollama pull deepseek-r1:8b
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=deepseek-r1:8b
uv run auditor --repo . --report reports/interim_report.pdf --rubric rubric/week2_rubric.json
```

Outputs:

- Markdown report: `audit/interim_detective_report.md`
- JSON report: `audit/interim_detective_report.json`

## Automation and CI

- `Makefile` commands:
  - `make setup` -> install dependencies from `uv.lock`
  - `make check` -> lint + compile checks
  - `make audit` -> local smoke run of detective workflow
- GitHub Actions CI:
  - Workflow file: `.github/workflows/ci.yml`
  - Runs `uv sync --frozen`, lint, compile check, and a smoke audit on every push/PR.

## Notes

- Repository access is sandboxed via temporary clone directories for URL targets.
- `uv.lock` is committed for exact dependency pinning and reproducible installs.
- `reports/interim_report.pdf` is included for peer-accessible architecture context.
