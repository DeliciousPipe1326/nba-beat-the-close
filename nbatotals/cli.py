"""Command line entry point: `python -m nbatotals <command>`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nbatotals", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("verify-legacy", help="read $NBA_LEGACY_DB and print row-count checks")
    bt = sub.add_parser("backtest", help="walk-forward backtest (docs/RESULTS.md)")
    bt.add_argument("--legacy", action="store_true", required=True,
                    help="use the maintainer's legacy DB ($NBA_LEGACY_DB) and raw odds payloads")
    bt.add_argument("--market", choices=("true-close", "temporal"), default="true-close",
                    help="true-close: multi-region payloads with a T-15 min close ($NBA_LEGACY_MULTIREGION), the "
                         "pre-registered primary; temporal: the older 3-a-day payloads ($NBA_LEGACY_ODDS_LAKE), "
                         "kept as a cross-check")
    bt.add_argument("--params", default=None, help="params.yaml to use (default config/params.yaml)")
    bt.add_argument("--out", default=None, help="where to write the full report (default under docs/)")
    bt.add_argument("--log", default=str(ROOT / "docs" / "search" / "fit_log.tsv.gz"), help="grid-search log path")
    bt.add_argument("--reuse-fit", action="store_true",
                    help="reuse the odds-free walk-forward fit cached in data/fit_cache.pkl by an earlier run")
    return p


def cmd_backtest(args) -> int:
    from nbatotals import params as P
    from nbatotals.evaluate import backtest
    from nbatotals.evaluate.adapters import legacy_lake, legacy_multiregion, legacy_nba_db

    source = legacy_multiregion if args.market == "true-close" else legacy_lake
    if not os.environ.get(source.ENV_VAR):
        print(f"{source.ENV_VAR} is required: the market anchors are rebuilt from the raw payloads by measured "
              "capture time, never taken from the legacy odds table (see docs/RESULTS.md).", file=sys.stderr)
        return 2
    import pickle

    # Games and box scores from the legacy DB (without its odds-lake stamping);
    # market anchors rebuilt from raw payloads (pre-registration Amendments 1 and 2).
    old = os.environ.pop(legacy_lake.ENV_VAR, None)
    try:
        frames = legacy_nba_db.load()
    finally:
        if old is not None:
            os.environ[legacy_lake.ENV_VAR] = old
    games = frames["games"]
    box = frames["team_box"].drop(columns=["legacy_pace"])
    if args.market == "true-close":
        quotes, counts = legacy_multiregion.anchor_quotes(legacy_multiregion.read_files(), games)
        spec = backtest.TRUE_CLOSE
        out_path = args.out or str(ROOT / "docs" / "backtest_legacy_report.md")
    else:
        quotes, counts = legacy_lake.anchor_quotes(legacy_lake.read_lake(), games)
        spec = backtest.TEMPORAL
        out_path = args.out or str(ROOT / "docs" / "backtest_legacy_temporal_report.md")
    base = P.load(args.params)
    cache = ROOT / "data" / "fit_cache.pkl"
    fitted = None
    if args.reuse_fit and cache.exists():
        fitted = pickle.loads(cache.read_bytes())
        print(f"reusing walk-forward fit from {cache}", file=sys.stderr)
    res = backtest.run(games, box, quotes, base, spec=spec, fitted=fitted,
                       progress=lambda i, n: print(f"\rgrid: blend point {i}/{n}", end="", file=sys.stderr),
                       log_path=args.log)
    print(file=sys.stderr)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(res["fitted"]))
    res["anchor_counts"] = counts
    md = backtest.report_markdown(res)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(md)
    print(f"## Per-season results against {spec.labels[spec.ref]}\n")
    print(backtest.headline_table(res))
    print()
    print(backtest.fit_table(res))
    print(f"\nfull report: {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "verify-legacy":
        from nbatotals.evaluate.adapters import legacy_nba_db

        return legacy_nba_db.main([])
    if args.command == "backtest":
        return cmd_backtest(args)
    return 2
