#!/usr/bin/env sh
# Lint, type-check, complexity budget and tests. Run from the repository root.
# See docs/CODE_QUALITY.md. Exits non-zero on the first failing step.
set -eu
PY=${PYTHON:-python}
echo "== ruff"
"$PY" -m ruff check nbatotals tests
echo "== mypy"
"$PY" -m mypy
echo "== radon (complexity budget: no function above C, i.e. above 15)"
over=$("$PY" -m radon cc -n D -s nbatotals tests)
if [ -n "$over" ]; then echo "$over"; echo "complexity budget exceeded"; exit 1; fi
echo "ok"
echo "== pytest"
"$PY" -m pytest -q "$@"
