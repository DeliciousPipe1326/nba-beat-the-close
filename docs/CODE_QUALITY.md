# Code quality

Everything here is checked by one script. Run it before every commit:

```bash
pip install -e ".[dev]"
```

```bash
PYTHON=.venv/bin/python scripts/check.sh
```

It stops at the first failure. The steps:

| Step | Tool | What it enforces | Configuration |
|---|---|---|---|
| Lint | ruff | pycodestyle (E, W), pyflakes (F), bugbear (B), pyupgrade (UP), simplify (SIM), naming (N), mccabe (C90) at line length 120 | `[tool.ruff]` in pyproject.toml |
| Types | mypy | no type errors with `check_untyped_defs` over nbatotals, tests and scripts | `[tool.mypy]` in pyproject.toml |
| Complexity | radon | no function above the budget below | `scripts/complexity_budget.py` |
| Tests | pytest | the suite passes offline: no API keys, no private data | `[tool.pytest.ini_options]` |

ruff, mypy and radon are dev extras only; nothing at runtime depends on them.

## Rules

**Complexity budget.** No function or method may have a cyclomatic complexity
above 15 (radon grade C or better; ruff's mccabe limit is set to the same
number). When a function grows past it, split it into named steps. Report
builders are composed from one function per section, and parsers handle one
item per helper.

**Layering.** A module may import its own layer or a lower one, never a higher
one:

```
foundations (teams, boxscore, params, cache)
  -> ingest -> store, data -> features -> model -> evaluate -> experiments -> today, cli
```

Experiments sit beside the evaluator: they may import it, it may not import
them. Models never import the evaluator. That is why the pace_eff parameter
search lives in `nbatotals/model/pace_eff_fit.py`. Features never read data
sources: lineup projectors receive `PlayerInputs` from whoever builds them, and
the maintainer's private folders are read by
`nbatotals.evaluate.adapters.legacy_players.player_inputs`.
`tests/test_layering.py` checks every import in the package against this
order.

**No suppression by default.** There is no `type: ignore` anywhere. One `noqa`
remains: an intentional re-export (`F401` in
`evaluate/adapters/legacy_players.py`). The three `== True` / `== False` pandas
comparisons that used to need `noqa: E712` now use `.eq(...)`. Two `nosec
B608` comments tell bandit, which is not part of the check script, that a query
interpolates only placeholders. If a rule is wrong for a specific line,
suppress that one rule on that line and say why in the comment.

**Caches are data, not code.** Intermediate results under `data/cache/` are
parquet files plus a JSON manifest (`nbatotals/cache.py`). Nothing is
unpickled. A cache written under another schema version, newer or older, or for
another kind of result, is refused; rebuild it by running the command without
`--reuse-fit` or `--reuse-quotes`.

**SQL binds every value.** The only text ever interpolated into a query is a run
of `?` placeholders from `store.placeholders(n)`, and column lists that are
module constants.

## Numbers before and after this pass

Measured on 20 October 2026: before at f1bbfae (main after the five experiment
merges), after at the commit that adds this file. Same tool versions: ruff
0.17.1, mypy 2.4.0, radon 6.0.1.

| Check | Before | After |
|---|---|---|
| ruff findings (rules above, line length 120) | 156 (73 long lines, 26 `import params as P`, 18 `zip` without `strict`, 13 upper-case locals, 9 lambda assignments, …) | 0 |
| mypy errors, `check_untyped_defs`, nbatotals + tests | 31 in 15 files (16 in 8 files with the narrower flags of the first scan) | 0 in 71 files |
| radon, highest function complexity | 32 (`market_vs_market.report_markdown`, grade E) | 15 |
| radon, functions at grade C (11–20) / D / E | 19 / 0 / 1 | 12 / 0 / 0, all at 15 or below |
| radon, average complexity | 3.93 over 498 blocks | 3.64 over 567 blocks |
| radon maintainability index, `evaluate/props_market.py` | 13.62 (B) | 13.45 (B) |
| radon maintainability index, `evaluate/market_vs_market.py` | 15.24 (B) | 12.99 (B) |
| layering violations | 2 (`model.pace_eff` → `evaluate`, `features.players` → `evaluate.adapters`) | 0, enforced by a test |
| bandit, medium and above | 8 (6 `pickle.loads`, 2 string-built SQL) | 0 (pickle removed; the two placeholder lists annotated) |
| vulture, 80% confidence | 2 unused variables | 0 |
| tests | 126 passed, 2 skipped | 136 passed, 2 skipped |

The two maintainability grades did not improve. The index penalises module
size, and splitting long functions into named steps added lines. Both modules
are an experiment's whole harness plus its report. Moving each report's
section builders into a module of its own would lift both to A without
changing behaviour, and is the next step if the grade matters.
