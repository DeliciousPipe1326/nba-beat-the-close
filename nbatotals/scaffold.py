"""Scaffold a new projector: python -m nbatotals new-model my_model

Writes nbatotals/model/<slug>.py from TEMPLATE (the same template as
docs/YOUR_FIRST_MODEL.md) and registers it in nbatotals/model/registry.py:
one import line and one PROJECTORS line. It refuses, changing nothing, if the
slug is not lowercase letters, digits and underscores, or if the file, the
class or the name already exists.
"""

from __future__ import annotations

import keyword
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent

TEMPLATE = '''"""{slug}: one line on the idea."""

from __future__ import annotations

import pandas as pd

from nbatotals.features.pointintime import build_features


class {cls}:
    name = "{slug}"

    def fit(self, train_games, train_box, params, progress=None) -> dict:
        # Called once per test season with earlier seasons only, never odds. Tune here if you like;
        # what you return comes back to predict() as `state` (None means untuned).
        return {{}}

    def predict(self, targets, games, box, state, params) -> pd.DataFrame:
        f = build_features(targets, games, box, params)  # one row per target game, history dated before it
        # Columns of f (side is home or away):
        #   {{side}}_pace, {{side}}_ortg, {{side}}_drtg     blended (features.blend in params.yaml), never missing
        #   {{side}}_pace_l3, _l10, _season, and the same for ortg and drtg: last 3, last 10, season to date
        #                                             (missing before a team's first game of the season)
        #   {{side}}_rest_days, {{side}}_b2b               days off before this game; True on a back-to-back
        #   league_pace, league_ortg                  league averages to date
        total = f["league_pace"] * 2 * f["league_ortg"] / 100.0  # <- your arithmetic goes here
        return pd.DataFrame({{"game_id": f["game_id"], "total_proj": total}})
'''

SLUG = re.compile(r"^[a-z][a-z0-9_]*$")


def class_name(slug: str) -> str:
    return "".join(part.capitalize() for part in slug.split("_"))


def render(slug: str) -> str:
    return TEMPLATE.format(slug=slug, cls=class_name(slug))


def _refusal(slug: str, model_dir: Path, registry_text: str) -> str | None:
    if not SLUG.match(slug) or keyword.iskeyword(slug):
        return f"{slug!r}: use lowercase letters, digits and underscores, starting with a letter"
    if (model_dir / f"{slug}.py").exists():
        return f"{model_dir / f'{slug}.py'} already exists"
    cls = class_name(slug)
    if re.search(rf"\b{cls}\b", registry_text) or f'"{slug}"' in registry_text:
        return f"{cls} or {slug!r} is already in the registry"
    from nbatotals.model import registry

    if slug in registry.PROJECTORS:
        return f"a model named {slug!r} is already registered"
    return None


def _register(text: str, slug: str, cls: str) -> str:
    lines = text.splitlines(keepends=True)
    last_import = max(i for i, ln in enumerate(lines) if ln.startswith("from nbatotals.model."))
    lines.insert(last_import + 1, f"from nbatotals.model.{slug} import {cls}\n")
    start = next(i for i, ln in enumerate(lines) if ln.startswith("PROJECTORS"))
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("}"))
    lines.insert(end, f"    {cls}.name: {cls},\n")
    return "".join(lines)


def new_model(slug: str, package: Path = PACKAGE) -> Path:
    """Write the projector file and register it; raise ValueError (nothing written) on any refusal."""
    model_dir = Path(package) / "model"
    registry_path = model_dir / "registry.py"
    text = registry_path.read_text()
    why = _refusal(slug, model_dir, text)
    if why:
        raise ValueError(why)
    path = model_dir / f"{slug}.py"
    path.write_text(render(slug))
    registry_path.write_text(_register(text, slug, class_name(slug)))
    return path


def next_steps(slug: str) -> str:
    return ("Next:\n"
            "  pytest tests/test_leakage.py\n"
            f"  python -m nbatotals backtest --store --model {slug}")
