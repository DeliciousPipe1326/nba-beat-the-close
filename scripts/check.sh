#!/usr/bin/env sh
# Lint, type-check, complexity budget and tests. Run from the repository root with your virtual environment active (or set PYTHON=path/to/python).
# See docs/CODE_QUALITY.md. Exits non-zero on the first failing step.
set -eu
if [ -z "${PYTHON:-}" ] && [ -x ".venv/bin/python" ]; then PYTHON=".venv/bin/python"; fi
PY=${PYTHON:-$(command -v python3 || command -v python)}
echo "== ruff"
"$PY" -m ruff check nbatotals tests scripts
echo "== mypy"
"$PY" -m mypy
echo "== radon (complexity budget: every function 15 or below)"
"$PY" scripts/complexity_budget.py nbatotals tests
echo "== pytest"
"$PY" -m pytest -q "$@"
