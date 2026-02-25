PYTHON := .venv/bin/python
RUFF := .venv/bin/ruff
AUDITOR := .venv/bin/auditor

.PHONY: setup lint typecheck check audit clean

setup:
	uv sync --frozen

lint:
	$(RUFF) check src

typecheck:
	$(PYTHON) -m compileall src

check: lint typecheck

audit:
	$(AUDITOR) --repo . --rubric rubric/week2_rubric.json

clean:
	rm -rf audit/__pycache__ src/__pycache__ src/nodes/__pycache__ src/tools/__pycache__
