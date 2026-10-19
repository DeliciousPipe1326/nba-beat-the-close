"""Command line entry point: `python -m nbatotals <command>`."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nbatotals", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("verify-legacy", help="read $NBA_LEGACY_DB and print row-count checks")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "verify-legacy":
        from nbatotals.evaluate.adapters import legacy_nba_db

        return legacy_nba_db.main([])
    return 2
