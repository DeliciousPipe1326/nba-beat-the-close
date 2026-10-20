import re

import pytest

from nbatotals import cli, demo, report


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo")
    return demo.run(out_dir=root / "out", data_dir=root / "data")


def test_demo_writes_synthetic_csv_and_html(demo_run):
    first = demo_run["csv"].read_text().splitlines()[0]
    assert first == demo.HEADER and "SYNTHETIC" in first
    assert len(demo_run["table"]) == demo_run["fixtures"] and demo_run["table"]["market_line"].notna().all()
    assert "SYNTHETIC DEMO DATA" in demo_run["html"].read_text()


def test_report_has_the_headline_numbers_from_results_md(demo_run):
    page = demo_run["html"].read_text()
    sentence, header, rows = report.summary()
    assert sentence in page
    numbers = {n for r in rows for n in re.findall(r"[−+]?\d[\d,]*(?:\.\d+)?%?", r[-1])}
    assert {"48.9%", "−6.7%", "49.5%", "−0.117"} <= numbers
    missing = [n for n in numbers if n not in page]
    assert missing == []


def test_report_is_self_contained(demo_run):
    page = demo_run["html"].read_text().lower()
    assert "<script" not in page
    assert "http" not in page
    assert "<link" not in page and "@import" not in page and "url(" not in page
    assert "prefers-color-scheme: dark" in page and 'name="viewport"' in page


def test_report_rows_sorted_by_tip_and_quarter_lines_kept(demo_run):
    page = demo_run["html"].read_text()
    tips = re.findall(r"<tr><td>[A-Z]{3} @ [A-Z]{3}</td><td>(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)</td>", page)
    assert tips == sorted(tips) and len(tips) == demo_run["fixtures"]
    assert report._fmt(224.75, "market_line") == "224.75" and report._fmt(219.0, "market_line") == "219"


def test_report_command(demo_run, tmp_path):
    out = tmp_path / "r.html"
    assert cli.main(["report", "--csv", str(demo_run["csv"]), "--out", str(out)]) == 0
    assert out.read_text() == report.render(demo_run["csv"])
    assert cli.main(["report", "--csv", str(tmp_path / "missing.csv")]) == 2


def test_summary_needs_the_section(tmp_path):
    bad = tmp_path / "R.md"
    bad.write_text("# nothing here\n")
    with pytest.raises(ValueError, match="Summary"):
        report.summary(bad)
