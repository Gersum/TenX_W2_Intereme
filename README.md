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
uv sync
cp .env.example .env
```

Set `.env` values as needed:

- `OPENAI_API_KEY` (optional for future judicial layer work)
- `OPENAI_MODEL`
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

Outputs:

- Markdown report: `audit/interim_detective_report.md`
- JSON report: `audit/interim_detective_report.json`

## Notes

- Repository access is sandboxed via temporary clone directories for URL targets.
- The interim graph intentionally stops at evidence aggregation (judges are not wired yet).
- `reports/interim_report.pdf` is included for peer-accessible architecture context.
