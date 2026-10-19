"""Shared plumbing for the ingesters: API keys, HTTP, quota logging.

Keys come from the process environment or a `.env` file (git-ignored), never
from code, config or the command line, and are never written to the store,
logs or error messages. Every function that touches the network takes a
`session` argument (anything with a requests-style `.get`), so tests run
offline against synthetic payloads.
"""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class MissingKey(RuntimeError):
    pass


class ApiError(RuntimeError):
    pass


def read_dotenv(path: str | os.PathLike | None = None) -> dict[str, str]:
    """Parse KEY=VALUE lines from .env (cwd first, then the repo root). No interpolation."""
    candidates = [Path(path)] if path else [Path.cwd() / ".env", ROOT / ".env"]
    for p in candidates:
        if p.is_file():
            out = {}
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
            return out
    return {}


def get_key(name: str, dotenv: str | os.PathLike | None = None) -> str:
    value = os.environ.get(name) or read_dotenv(dotenv).get(name)
    if not value:
        raise MissingKey(f"{name} is not set. Put it in .env (see .env.example); it is never committed.")
    return value


def default_session():
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = "nbatotals (research; github.com)"
    return s


def get_json(session, url: str, *, params=None, headers=None, provider: str, redact: str | None = None,
             timeout: float = 30.0):
    """GET and decode JSON. Error messages never include the key."""
    try:
        resp = session.get(url, params=params, headers=headers, timeout=timeout)
    except Exception as exc:  # connection errors can echo the full URL, key included
        raise ApiError(f"{provider} {url} request failed: {type(exc).__name__}") from None
    if resp.status_code != 200:
        body = (getattr(resp, "text", "") or "")[:300]
        if redact:
            body = body.replace(redact, "<redacted>")
        raise ApiError(f"{provider} {url} returned HTTP {resp.status_code}: {body}")
    return resp.json(), resp.headers


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_usage(con: sqlite3.Connection, provider: str, endpoint: str, headers, called: dt.datetime) -> dict:
    """Record the provider's quota headers (The Odds API sends used/remaining/last)."""
    def num(name):
        v = headers.get(name) if headers else None
        try:
            return int(float(v)) if v is not None else None
        except ValueError:
            return None

    row = {"used": num("x-requests-used"), "remaining": num("x-requests-remaining"), "cost": num("x-requests-last")}
    con.execute(
        "INSERT INTO api_usage (called_utc, provider, endpoint, requests_used, requests_remaining, cost) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (iso(called), provider, endpoint, row["used"], row["remaining"], row["cost"]),
    )
    return row


def last_remaining(con: sqlite3.Connection, provider: str) -> int | None:
    r = con.execute(
        "SELECT requests_remaining FROM api_usage WHERE provider = ? AND requests_remaining IS NOT NULL "
        "ORDER BY called_utc DESC, rowid DESC LIMIT 1", (provider,)
    ).fetchone()
    return r[0] if r else None
