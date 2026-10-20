#!/usr/bin/env sh
# Lint, type-check, complexity budget and tests. Run from the repository root.
# See docs/CODE_QUALITY.md. Exits non-zero on the first failing step.
set -eu
PY=${PYTHON:-python}
echo "== ruff"
"$PY" -m ruff check nbatotals tests scripts
echo "== mypy"
"$PY" -m mypy
echo "== radon (complexity budget: every function 15 or below)"
"$PY" scripts/complexity_budget.py nbatotals tests
echo "== pytest"
"$PY" -m pytest -q "$@"
