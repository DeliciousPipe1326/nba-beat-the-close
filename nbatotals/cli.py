"""nbatotals: transparent pace x efficiency NBA totals engine (research tool, no edge found).

Typical use, with keys in .env:
  python -m nbatotals init
  python -m nbatotals ingest-games --season 2025
  python -m nbatotals ingest-box --season 2025
  python -m nbatotals poll-odds          # schedule every 5-10 minutes
  python -m nbatotals today
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _today_eastern() -> str:
    import datetime as dt
    from zoneinfo import ZoneInfo

    return dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nbatotals", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def with_db(sp):
        sp.add_argument("--db", default=str(ROOT / "data" / "nbatotals.db"), help="local SQLite store (git-ignored)")
        sp.add_argument("--params", default=None, help="params.yaml to use (default config/params.yaml)")
        return sp

    with_db(sub.add_parser("init", help="create the local store"))
    g = with_db(sub.add_parser("ingest-games", help="BallDontLie fixtures and finals into the store"))
    g.add_argument("--season", type=int, action="append", help="season start year, e.g. 2025 for 2025-26 (repeatable)")
    g.add_argument("--date", action="append", help="YYYY-MM-DD (repeatable)")
    b = with_db(sub.add_parser("ingest-box", help="BallDontLie team box scores for final games missing one"))
    b.add_argument("--season", type=int, action="append")
    b.add_argument("--date", action="append")
    with_db(sub.add_parser("ingest-injuries", help="BallDontLie injury report snapshot (plan permitting)"))
    o = with_db(sub.add_parser("poll-odds", help="The Odds API: record any due anchors (run on a schedule)"))
    o.add_argument("--force", action="store_true", help="fetch odds even if no anchor is due (costs credits)")
    t = with_db(sub.add_parser("today", help="write the research CSV for a date's fixtures"))
    t.add_argument("--date", default=None, help="YYYY-MM-DD, default today (US Eastern)")
    t.add_argument("--out", default=None, help="CSV path, default out/today_<date>.csv (git-ignored)")
    t.add_argument("--model", default=None, help="registered projector (default pace_eff); see nbatotals/model/registry.py")
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
    bt.add_argument("--model", default=None, help="registered projector (default pace_eff); see nbatotals/model/registry.py")
    bt.add_argument("--log", default=None, help="fit log path (default docs/search/fit_log[_<model>].tsv.gz)")
    bt.add_argument("--reuse-fit", action="store_true",
                    help="reuse the odds-free walk-forward fit cached in data/ by an earlier run of the same model")
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
    from nbatotals.model import registry

    projector = registry.get(args.model or registry.DEFAULT)
    suffix = "" if projector.name == registry.DEFAULT else f"_{projector.name}"
    if args.market == "true-close":
        quotes, counts = legacy_multiregion.anchor_quotes(legacy_multiregion.read_files(), games)
        spec = backtest.TRUE_CLOSE
        out_path = args.out or str(ROOT / "docs" / f"backtest_legacy_report{suffix}.md")
    else:
        quotes, counts = legacy_lake.anchor_quotes(legacy_lake.read_lake(), games)
        spec = backtest.TEMPORAL
        out_path = args.out or str(ROOT / "docs" / f"backtest_legacy_temporal_report{suffix}.md")
    log_path = args.log or str(ROOT / "docs" / "search" / f"fit_log{suffix}.tsv.gz")
    base = P.load(args.params)
    cache = ROOT / "data" / f"fit_cache{suffix}.pkl"
    fitted = None
    if args.reuse_fit and cache.exists():
        fitted = pickle.loads(cache.read_bytes())
        print(f"reusing walk-forward fit from {cache}", file=sys.stderr)
    res = backtest.run(games, box, quotes, base, spec=spec, fitted=fitted, projector=projector,
                       progress=lambda i, n: print(f"\rgrid: blend point {i}/{n}", end="", file=sys.stderr),
                       log_path=log_path)
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


def cmd_store(args) -> int:
    import json

    from nbatotals import params as P
    from nbatotals import store
    from nbatotals.ingest import balldontlie, common, theodds

    prm = P.load(args.params)
    con = store.connect(args.db)
    try:
        if args.command == "init":
            print(f"store ready: {args.db}")
        elif args.command in ("ingest-games", "ingest-box", "ingest-injuries"):
            client = balldontlie.Client(prm)
            if args.command == "ingest-games":
                if not (args.season or args.date):
                    args.date = [_today_eastern()]
                n = balldontlie.ingest_games(con, client, dates=args.date, seasons=args.season)
                fixed = theodds.resolve_game_ids(con)
                con.commit()
                print(f"games upserted: {n}; odds rows matched to games: {fixed}")
            elif args.command == "ingest-box":
                n = balldontlie.ingest_box(con, client, dates=args.date, seasons=args.season)
                print(f"team box rows written: {n}")
            else:
                print(f"injury rows written: {balldontlie.ingest_injuries(con, client)}")
        elif args.command == "poll-odds":
            print(json.dumps(theodds.poll(con, prm, force=args.force), indent=2, default=str))
        elif args.command == "today":
            from nbatotals import today

            date = args.date or _today_eastern()
            out = Path(args.out or ROOT / "out" / f"today_{date}.csv")
            out.parent.mkdir(parents=True, exist_ok=True)
            df = today.build(con, date, prm, model=args.model)
            today.write_csv(df, out)
            print(today.HEADER)
            print(df.to_string(index=False) if len(df) else f"no fixtures for {date} in the store; run ingest-games")
            print(f"\nwritten: {out}")
    except (common.MissingKey, common.ApiError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        con.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in ("init", "ingest-games", "ingest-box", "ingest-injuries", "poll-odds", "today"):
        return cmd_store(args)
    if args.command == "verify-legacy":
        from nbatotals.evaluate.adapters import legacy_nba_db

        return legacy_nba_db.main([])
    if args.command == "backtest":
        return cmd_backtest(args)
    return 2
