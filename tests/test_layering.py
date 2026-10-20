"""The layering rule (docs/CODE_QUALITY.md): nothing lower imports anything higher.

    foundations (teams, boxscore, params) -> ingest -> store/data -> features -> model
    -> evaluate -> experiments -> today/cli

A module may import its own layer or any lower one. Experiments sit beside the
evaluator: they may import it, it may not import them.
"""

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "nbatotals"

RANK = {
    "nbatotals": 0, "nbatotals.teams": 0, "nbatotals.boxscore": 0, "nbatotals.params": 0,
    "nbatotals.ingest": 1,
    "nbatotals.store": 2, "nbatotals.data": 2,
    "nbatotals.features": 3,
    "nbatotals.model": 4,
    "nbatotals.evaluate": 5,
    "nbatotals.experiments": 6,
    "nbatotals.today": 7, "nbatotals.cli": 7, "nbatotals.__main__": 7,
}


def layer(module: str) -> str:
    parts = module.split(".")
    return ".".join(parts[:2])


def imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("nbatotals"):
            yield node.module, node.lineno
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("nbatotals"):
                    yield a.name, node.lineno


def test_every_module_has_a_layer():
    for f in PKG.rglob("*.py"):
        mod = ".".join(f.relative_to(PKG.parent).with_suffix("").parts).removesuffix(".__init__")
        assert layer(mod) in RANK, f"{mod}: add its package to RANK"


def test_nothing_lower_imports_anything_higher():
    bad = []
    for f in PKG.rglob("*.py"):
        mod = ".".join(f.relative_to(PKG.parent).with_suffix("").parts).removesuffix(".__init__")
        for target, line in imports(f):
            if RANK[layer(target)] > RANK[layer(mod)]:
                bad.append(f"{f.relative_to(PKG.parent)}:{line} imports {target}")
    assert bad == [], "\n".join(bad)
