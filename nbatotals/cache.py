"""Local caches of intermediate results, stored as parquet plus a JSON manifest.

The maintainer-only commands (`backtest --legacy`, `backtest-books --legacy`,
`python -m nbatotals.experiments.info_latency`) cache parsed payloads and
walk-forward fits under data/cache/ (git-ignored) so a report can be rebuilt
without repeating hours of work. A cache is a directory:

    <name>/manifest.json   {"kind", "schema_version", "frames", "meta"}
    <name>/<frame>.parquet one file per DataFrame

Loading reads data only; nothing in a cache is executed (no pickle). A cache
written under a different SCHEMA_VERSION, or for a different kind of result,
is refused: rebuild it by running the command without its --reuse flag.
Parquet needs pyarrow (`pip install -e ".[legacy]"`).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pandas as pd

# Bump when the layout or the meaning of a cached frame changes.
SCHEMA_VERSION = 1
MANIFEST = "manifest.json"


class CacheError(RuntimeError):
    pass


def exists(path: str | os.PathLike) -> bool:
    return (Path(path) / MANIFEST).is_file()


def save(path: str | os.PathLike, kind: str, frames: dict[str, pd.DataFrame], meta: dict | None = None) -> Path:
    """Write `frames` (and small JSON-serialisable `meta`) atomically to directory `path`."""
    path = Path(path)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        for name, df in frames.items():
            df.to_parquet(tmp / f"{name}.parquet")
    except ImportError as exc:
        shutil.rmtree(tmp)
        raise CacheError('caches need pyarrow: pip install -e ".[legacy]"') from exc
    manifest = {"kind": kind, "schema_version": SCHEMA_VERSION, "frames": list(frames), "meta": meta or {}}
    (tmp / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True))
    if path.exists():
        shutil.rmtree(path)
    tmp.rename(path)
    return path


def load(path: str | os.PathLike, kind: str) -> tuple[dict[str, pd.DataFrame], dict]:
    """Read a cache written by `save`; refuse one of another kind or schema version."""
    path = Path(path)
    if not exists(path):
        raise CacheError(f"{path}: no cache here")
    manifest = json.loads((path / MANIFEST).read_text())
    if manifest.get("kind") != kind:
        raise CacheError(f"{path}: holds {manifest.get('kind')!r}, expected {kind!r}")
    version = manifest.get("schema_version")
    if version != SCHEMA_VERSION:
        newer = isinstance(version, int) and version > SCHEMA_VERSION
        raise CacheError(f"{path}: cache schema version {version} is {'newer' if newer else 'older'} than this "
                         f"code's ({SCHEMA_VERSION}); rebuild it by running without the --reuse flag")
    frames = {name: pd.read_parquet(path / f"{name}.parquet") for name in manifest["frames"]}
    return frames, manifest.get("meta", {})


# --------------------------------------------------------------------------- the walk-forward fit tuple

FIT_KIND = "walk_forward_fit"


def save_fit(path: str | os.PathLike, fitted: tuple) -> Path:
    """`fitted` is backtest.predictions' (pred, fits, log_rows)."""
    pred, fits, log_rows = fitted
    return save(path, FIT_KIND, {"pred": pred, "fits": fits}, {"log_rows": int(log_rows)})


def load_fit(path: str | os.PathLike) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    frames, meta = load(path, FIT_KIND)
    return frames["pred"], frames["fits"], int(meta["log_rows"])


def fit_cache_path(data_dir: str | os.PathLike, model: str, default_model: str = "pace_eff") -> Path:
    """Where `backtest --legacy --model <model>` keeps its walk-forward fit."""
    suffix = "" if model == default_model else f"_{model}"
    return Path(data_dir) / "cache" / f"fit{suffix}"
