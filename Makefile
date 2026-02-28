PYTHON := .venv/bin/python
RUFF := .venv/bin/ruff
AUDITOR := .venv/bin/auditor

.PHONY: setup lint typecheck check audit audit-self-final audit-peer-final graph trace-check clean

setup:
	uv sync --frozen

lint:
	$(RUFF) check src

typecheck:
	$(PYTHON) -m compileall src

check: lint typecheck

audit:
	$(AUDITOR) --repo . --rubric rubric/week2_rubric.json

audit-self-final:
	$(AUDITOR) --repo . --report reports/final_report.pdf --rubric rubric/final_rubric.json --out audit/report_onself_generated/final_report.md --out-json audit/report_onself_generated/final_report.json

audit-peer-final:
	@test -n "$(REPO)" || (echo "Usage: make audit-peer-final REPO=<peer_repo_url_or_path> REPORT=<peer_pdf_path>" && exit 1)
	@test -n "$(REPORT)" || (echo "Usage: make audit-peer-final REPO=<peer_repo_url_or_path> REPORT=<peer_pdf_path>" && exit 1)
	$(AUDITOR) --repo "$(REPO)" --report "$(REPORT)" --rubric rubric/final_rubric.json --out audit/report_onpeer_generated/final_report.md --out-json audit/report_onpeer_generated/final_report.json

graph:
	uv run auditor-graph

trace-check:
	$(PYTHON) scripts/trace_check.py

clean:
	rm -rf audit/__pycache__ src/__pycache__ src/nodes/__pycache__ src/tools/__pycache__
