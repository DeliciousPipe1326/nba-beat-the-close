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
    t.add_argument("--model", default=None,
                   help="registered projector (default pace_eff); see nbatotals/model/registry.py")
    sub.add_parser("verify-legacy", help="read $NBA_LEGACY_DB and print row-count checks")
    bt = sub.add_parser("backtest", help="walk-forward backtest (docs/RESULTS.md)")
    bt.add_argument("--legacy", action="store_true", required=True,
                    help="use the maintainer's legacy DB ($NBA_LEGACY_DB) and raw odds payloads")
    bt.add_argument("--market", choices=("true-close", "temporal"), default="true-close",
                    help="true-close: multi-region payloads with a T-15 min close ($NBA_LEGACY_MULTIREGION), the "
                         "pre-registered primary; temporal: the older 3-a-day payloads ($NBA_LEGACY_ODDS_LAKE), "
                         "kept as a cross-check")
    bt.add_argument("--market-type", choices=("totals", "spreads", "h2h"), default="totals",
                    help="totals: the pre-registered test (default); spreads or h2h: Experiment 5 "
                         "(docs/experiments/other_markets/PREREGISTRATION.md), true close only")
    bt.add_argument("--params", default=None, help="params.yaml to use (default config/params.yaml)")
    bt.add_argument("--out", default=None, help="where to write the full report (default under docs/)")
    bt.add_argument("--model", default=None,
                    help="registered projector (default pace_eff); see nbatotals/model/registry.py")
    bt.add_argument("--log", default=None, help="fit log path (default docs/search/fit_log[_<model>].tsv.gz)")
    bt.add_argument("--reuse-fit", action="store_true",
                    help="reuse the odds-free walk-forward fit cached in data/ by an earlier run of the same model")
    bb = sub.add_parser("backtest-books", help="experiment 3: soft books against Pinnacle at the same poll "
                                              "(docs/experiments/book_lag)")
    bb.add_argument("--legacy", action="store_true", required=True,
                    help="use $NBA_LEGACY_DB (scores) and $NBA_LEGACY_MULTIREGION (all three markets)")
    bb.add_argument("--out", default=None, help="report path (default docs/experiments/book_lag/report.md)")
    bb.add_argument("--reuse-quotes", action="store_true",
                    help="reuse the parsed payloads cached in data/ by an earlier run (git-ignored)")
    bp = sub.add_parser("backtest-props",
                        help="Experiment 4: retail player props vs Pinnacle (docs/experiments/props_market)")
    bp.add_argument("--legacy", action="store_true", required=True,
                    help="use the maintainer's prop payloads ($NBA_LEGACY_PROPS), props DB ($NBA_LEGACY_PROPS_DB) and "
                         "games DB ($NBA_LEGACY_DB); $NBA_LEGACY_MULTIREGION adds the game-totals benchmark")
    bp.add_argument("--out", default=None,
                    help="full report path (default docs/experiments/props_market/backtest_props_report.md)")
    return p


def cmd_backtest_books(args) -> int:
    from nbatotals import cache as caches
    from nbatotals.evaluate import market_vs_market as mvm
    from nbatotals.evaluate.adapters import legacy_lake, legacy_multiregion, legacy_nba_db

    for var in (legacy_nba_db.ENV_VAR, legacy_multiregion.ENV_VAR):
        if not os.environ.get(var):
            print(f"{var} is required", file=sys.stderr)
            return 2
    old = os.environ.pop(legacy_lake.ENV_VAR, None)
    try:
        games = legacy_nba_db.load()["games"]
    finally:
        if old is not None:
            os.environ[legacy_lake.ENV_VAR] = old
    seasons = mvm.DESCRIPTIVE_SEASONS + mvm.TEST_SEASONS
    cache = ROOT / "data" / "cache" / "book_lag_raw"
    if args.reuse_quotes and caches.exists(cache):
        raw = caches.load(cache, "book_lag_raw")[0]["raw"]
        print(f"reusing parsed payloads from {cache}", file=sys.stderr)
    else:
        print("reading payloads ...", file=sys.stderr)
        raw = legacy_multiregion.read_market_files(seasons=seasons)
        caches.save(cache, "book_lag_raw", {"raw": raw})
    quotes, counts = legacy_multiregion.market_quotes(raw, games)
    res = mvm.run(quotes, games, progress=lambda m: print(m, file=sys.stderr))
    md = mvm.report_markdown(res)
    join = "\n".join(f"- {k}: {v:,}" for k, v in counts.items())
    md = md.replace("## Quote hygiene\n", f"## Quote hygiene\n\nEvent join (Amendment 2 rule):\n\n{join}\n", 1)
    out = Path(args.out or ROOT / "docs" / "experiments" / "book_lag" / "report.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    for mkt in mvm.MARKETS:
        print(f"\n## {mkt}: top of the per-book table (2%, buckets pooled, exact lines)\n")
        print(mvm.pooled_table(res["pooled"]["exact"], mkt, top=8))
    print(f"\nfull report: {out}")
    return 0
def cmd_backtest_props(args) -> int:
    from nbatotals.evaluate import props_market as pm
    from nbatotals.evaluate.adapters import legacy_multiregion, legacy_nba_db, legacy_props

    required = (legacy_props.ENV_PROPS, legacy_props.ENV_PROPS_DB, legacy_nba_db.ENV_VAR)
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"required: {', '.join(missing)}", file=sys.stderr)
        return 2
    raw, read_counts = legacy_props.read_files()
    games = legacy_props.read_games()
    box = legacy_props.read_player_box()
    totals = None
    if os.environ.get(legacy_multiregion.ENV_VAR):
        totals, _ = legacy_multiregion.anchor_quotes(legacy_multiregion.read_files(), games)
    res = pm.run(raw, read_counts, games, box, totals_quotes=totals)
    sens = pm.run(raw, read_counts, games, box, drop_stale=True)
    out = Path(args.out or ROOT / "docs" / "experiments" / "props_market" / "backtest_props_report.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(pm.report_markdown(res, sensitivity=sens))
    bar = res["bar"]
    print(f"cells: {len(bar)}; meeting the evidence bar: {int(bar['meets_bar'].sum()) if len(bar) else 0}")
    print(f"full report: {out}")
    return 0


def _projector(name: str | None):
    """A registered projector; one that needs player inputs gets them from the legacy folders."""
    from nbatotals.evaluate.adapters import legacy_players
    from nbatotals.model import registry

    name = name or registry.DEFAULT
    if getattr(registry.PROJECTORS.get(name), "needs_player_inputs", False):
        return registry.get(name, inputs=legacy_players.player_inputs_from_env())
    return registry.get(name)


def cmd_backtest(args) -> int:
    from nbatotals import params as params_io
    from nbatotals.evaluate import backtest
    from nbatotals.evaluate.adapters import legacy_lake, legacy_multiregion, legacy_nba_db

    source = legacy_multiregion if args.market == "true-close" else legacy_lake
    if not os.environ.get(source.ENV_VAR):
        print(f"{source.ENV_VAR} is required: the market anchors are rebuilt from the raw payloads by measured "
              "capture time, never taken from the legacy odds table (see docs/RESULTS.md).", file=sys.stderr)
        return 2
    from nbatotals import cache as caches

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

    projector = _projector(args.model)
    if args.market_type != "totals":
        if args.market != "true-close":
            print("--market-type spreads/h2h is graded against the true close only", file=sys.stderr)
            return 2
        return _backtest_sides(args, games, box, projector)
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
    base = params_io.load(args.params)
    cache = caches.fit_cache_path(ROOT / "data", projector.name, registry.DEFAULT)
    fitted = None
    if args.reuse_fit and caches.exists(cache):
        fitted = caches.load_fit(cache)
        print(f"reusing walk-forward fit from {cache}", file=sys.stderr)
    res = backtest.run(games, box, quotes, base, spec=spec, fitted=fitted, projector=projector,
                       progress=lambda i, n: print(f"\rgrid: blend point {i}/{n}", end="", file=sys.stderr),
                       log_path=log_path)
    print(file=sys.stderr)
    caches.save_fit(cache, res["fitted"])
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


def _backtest_sides(args, games, box, projector) -> int:
    """Experiment 5: spreads or moneyline against the true close (pre-registered first)."""
    from nbatotals import cache as caches
    from nbatotals import params as params_io
    from nbatotals.evaluate import market, sides
    from nbatotals.evaluate.adapters import legacy_multiregion as mr

    base = params_io.load(args.params)
    quotes, counts = {}, {}
    for mt in ("spreads", "h2h"):
        quotes[mt], counts[mt] = mr.side_quotes(mr.read_files(market=mt), games, mt)
    scored = games[games["season"] <= max(sides.TEST_SEASONS)]
    cons_sp, _ = market.enforce_anchor_order(market.consensus_spreads(quotes["spreads"], base), sides.SPREADS.ref)
    cons_ml, _ = market.enforce_anchor_order(market.consensus_h2h(quotes["h2h"], base), sides.H2H.ref)
    sane = sides.sanity(cons_sp, cons_ml, scored)
    out_dir = ROOT / "docs" / "experiments" / "other_markets"
    out_path = Path(args.out or out_dir / f"backtest_legacy_{args.market_type}_report_{projector.name}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not sane["passed"]:
        out_path.write_text(sides.stopped_report(args.market_type, projector.name, sane, sides.SPREADS.labels))
        print(f"grading stopped: a sanity stop rule failed; see {out_path}", file=sys.stderr)
        return 3
    cache = ROOT / "data" / "cache" / f"margin_fit_{projector.name}"
    if args.reuse_fit and caches.exists(cache):
        frames, _ = caches.load(cache, "margin_fit")
        pred, fits = frames["pred"], frames["fits"]
        print(f"reusing walk-forward margin fit from {cache}", file=sys.stderr)
    else:
        pred, fits = sides.margin_predictions(
            games, box, base, projector,
            progress=lambda i, n: print(f"\rgrid: blend point {i}/{n}", end="", file=sys.stderr))
        print(file=sys.stderr)
        caches.save(cache, "margin_fit", {"pred": pred, "fits": fits})
    run = sides.run_spreads if args.market_type == "spreads" else sides.run_h2h
    res = run(pred, fits, quotes[args.market_type], games, base, sane)
    res["projector"], res["anchor_counts"] = projector.name, counts[args.market_type]
    report = sides.spreads_report if args.market_type == "spreads" else sides.h2h_report
    out_path.write_text(report(res))
    print(backtest_headline(res))
    print(f"\nfull report: {out_path}")
    return 0


def backtest_headline(res) -> str:
    from nbatotals.evaluate import backtest, sides

    return backtest.headline_table(res) if res["market"] == "spreads" else sides.h2h_headline(res)


def cmd_store(args) -> int:
    import json

    from nbatotals import params as params_io
    from nbatotals import store
    from nbatotals.ingest import balldontlie, common, theodds

    prm = params_io.load(args.params)
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
            df = today.build(con, date, prm, projector=_projector(args.model))
            today.write_csv(df, out)
            print(today.HEADER)
            print(df.to_string(index=False) if len(df) else f"no fixtures for {date} in the store; run ingest-games")
            print(f"\nwritten: {out}")
    except (common.MissingKeyError, common.ApiError) as exc:
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
    if args.command == "backtest-books":
        return cmd_backtest_books(args)
    if args.command == "backtest-props":
        return cmd_backtest_props(args)
    return 2
