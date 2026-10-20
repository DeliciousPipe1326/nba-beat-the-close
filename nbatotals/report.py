"""Render a day's research CSV as one self-contained HTML page.

    python -m nbatotals report [--csv out/today_<date>.csv] [--out out/report_<date>.html]

The page leads with the repository's main result, read from docs/RESULTS.md's
summary when the page is built (nothing is copied by hand), then the day's
table, then a footer. It is plain semantic HTML with a small inline stylesheet:
no scripts, no fonts, no external files or links, readable without JavaScript,
on a phone, in light or dark mode.
"""

from __future__ import annotations

import html
import re
from collections.abc import Collection
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS_MD = ROOT / "docs" / "RESULTS.md"

DAY_COLUMNS = [  # (CSV column, heading)
    ("fixture", "fixture"), ("tip", "tip (UTC)"), ("projected_total", "projected total"),
    ("market_line", "market line"), ("market_captured_utc", "line captured (UTC)"),
    ("p_over_devig", "devigged P(over)"), ("edge", "edge (projection − line)"),
]

STYLE = """
:root { color-scheme: light dark; --fg: #1b1b1b; --bg: #ffffff; --muted: #5b5b5b; --rule: #d9d9d9;
        --head: #f3f3f3; --accent: #0b5cad; }
@media (prefers-color-scheme: dark) {
  :root { --fg: #e8e8e8; --bg: #141414; --muted: #a8a8a8; --rule: #3a3a3a; --head: #1f1f1f; --accent: #7ab4ff; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
       font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 60rem; margin: 0 auto; padding: 1rem; }
h1 { font-size: 1.4rem; margin: 0.5rem 0; } h2 { font-size: 1.15rem; margin-top: 2rem; }
p.lede { font-size: 1.05rem; } p.note, footer { color: var(--muted); font-size: 0.9rem; }
.scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { border-bottom: 1px solid var(--rule); padding: 0.4rem 0.5rem; text-align: left; vertical-align: top; }
thead th { background: var(--head); position: sticky; top: 0; }
td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
strong { color: var(--accent); }
code { font-size: 0.9em; }
footer { border-top: 1px solid var(--rule); margin-top: 2rem; padding-top: 1rem; }
"""


def _inline(md: str) -> str:
    """Escape, then render the inline markdown RESULTS.md uses: **bold**, `code`, [text](link) -> text."""
    s = html.escape(md, quote=False)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", s)


def summary(results_md: Path = RESULTS_MD) -> tuple[str, list[str], list[list[str]]]:
    """(one-sentence result, table header, table rows) from RESULTS.md's '## Summary' section."""
    text = Path(results_md).read_text()
    m = re.search(r"^## Summary\n(.*?)(?=^## )", text, re.S | re.M)
    if not m:
        raise ValueError(f"{results_md}: no '## Summary' section")
    section = m.group(1)
    table = [ln for ln in section.splitlines() if ln.startswith("|")]
    cells = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in table]
    header, rows = cells[0], [r for r in cells[2:]]
    para = re.search(r"In plain words:\s*(.+?\.)(?:\s|$)", " ".join(section.split()))
    if not para:
        raise ValueError(f"{results_md}: no 'In plain words:' sentence in the summary")
    sentence = para.group(1)
    return sentence[0].upper() + sentence[1:], header, rows


def _table(header: list[str], rows: list[list[str]], numeric: Collection[int] = ()) -> str:
    head = "".join(f"<th scope=\"col\">{h}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td class=\"num\">{c}</td>" if i in numeric else f"<td>{c}</td>"
                                    for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f"<div class=\"scroll\"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _fmt(v, kind: str) -> str:
    if pd.isna(v):
        return "–"
    if kind == "p_over_devig":
        return f"{float(v):.3f}"
    if kind == "projected_total":
        return f"{float(v):.1f}"
    if kind == "market_line":  # quarter-point consensus lines keep their precision
        return f"{float(v):.2f}".rstrip("0").rstrip(".")
    if kind == "edge":
        return f"{float(v):+.1f}"
    return html.escape(str(v))


def read_day(csv_path: Path) -> tuple[list[str], pd.DataFrame]:
    """The CSV's '#' header lines and its table."""
    lines = Path(csv_path).read_text().splitlines()
    notes = [ln.lstrip("#").strip() for ln in lines if ln.startswith("#")]
    df = pd.read_csv(csv_path, comment="#")
    return notes, df


def day_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "<p>No fixtures in this file.</p>"
    d = df.sort_values(["tip_utc", "home"], na_position="last").copy()
    d["fixture"] = d["away"].astype(str) + " @ " + d["home"].astype(str)
    d["tip"] = d["tip_utc"]
    rows = [[_fmt(r[col], col) for col, _ in DAY_COLUMNS] for _, r in d.iterrows()]
    return _table([h for _, h in DAY_COLUMNS], rows, numeric={2, 3, 5, 6})


def render(csv_path: Path, results_md: Path = RESULTS_MD) -> str:
    sentence, header, rows = summary(results_md)
    notes, df = read_day(csv_path)
    date = str(df["game_date"].iloc[0]) if len(df) else Path(csv_path).stem
    note_html = "".join(f"<p class=\"note\">{html.escape(n)}</p>" for n in notes)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>nbatotals: {html.escape(date)}</title>
<style>{STYLE}</style></head>
<body><main>
<header><h1>nbatotals research output for {html.escape(date)}</h1>
<p class="lede">{_inline(sentence)}</p></header>
<section><h2>The pre-registered backtest (from docs/RESULTS.md)</h2>
{_table([_inline(h) for h in header], [[_inline(c) for c in r] for r in rows])}
</section>
<section><h2>Projections for {html.escape(date)}</h2>
{note_html}
{day_table(df)}
</section>
<footer><p>Research output, not betting advice. Projections come from a model that did not beat the closing
line in its pre-registered test; the market line is the latest one stored, and edge is projection minus
line. Source code and the full results: the nbatotals repository, docs/RESULTS.md.</p></footer>
</main></body></html>
"""


def write(csv_path: Path, out_path: Path, results_md: Path = RESULTS_MD) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(csv_path, results_md))
    return out_path
