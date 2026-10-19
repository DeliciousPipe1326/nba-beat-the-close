import datetime as dt
import sqlite3

import pytest

from nbatotals import params as P
from nbatotals import store
from nbatotals.ingest import common, theodds
from tests.fixtures.api_payloads import (EVENTS, FAKE_ODDS_KEY, FakeResponse, FakeSession, odds_event,
                                         quota_headers)

T = lambda s: dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)


@pytest.fixture
def con(tmp_path):
    c = store.connect(tmp_path / "s.db")
    c.execute("INSERT INTO games (id, game_date, season, home, away, status, source) "
              "VALUES (9001, '2025-11-04', 2025, 'BOS', 'NYK', 'scheduled', 't')")
    return c


@pytest.fixture
def prm():
    return P.load()


def session_for(*odds_payloads, remaining=480):
    return FakeSession({
        "/events": FakeResponse(EVENTS, headers=quota_headers(10, remaining, 0)),
        "/odds": [FakeResponse(p, headers=quota_headers(10 + 3 * i, remaining - 3 * (i + 1), 3))
                  for i, p in enumerate(odds_payloads)],
    })


def all_text(con):
    out = []
    for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        for row in con.execute(f"SELECT * FROM {table}"):
            out += [str(v) for v in row]
    return " ".join(out)


def test_first_poll_records_opening_and_close_with_times(con, prm):
    s = session_for([odds_event(EVENTS[0], 221.0), odds_event(EVENTS[1], 232.0)])
    out = theodds.poll(con, prm, session=s, key=FAKE_ODDS_KEY, now=T("2025-11-04T04:00:00"))
    assert out["fetched"] and out["credits_used"] == 3
    rows = con.execute("SELECT event_id, anchor, captured_utc, commence_utc, lead_minutes, game_id, line "
                       "FROM odds_snapshots WHERE market='totals' AND book='fanduel' ORDER BY event_id, anchor").fetchall()
    assert [(r[0], r[1]) for r in rows] == [("evA", "close"), ("evA", "opening"), ("evB", "close"), ("evB", "opening")]
    evA = rows[1]
    assert evA[2] == "2025-11-04T04:00:00Z" and evA[3] == "2025-11-05T00:00:00Z" and evA[4] == 20 * 60
    assert evA[5] == 9001  # matched to the BallDontLie fixture by Eastern date and teams
    assert rows[3][5] is None  # no fixture for the Lakers game yet
    # the key is sent but never stored
    assert s.calls[1]["params"]["apiKey"] == FAKE_ODDS_KEY
    assert FAKE_ODDS_KEY not in all_text(con)
    usage = con.execute("SELECT endpoint, requests_remaining, cost FROM api_usage ORDER BY rowid").fetchall()
    assert usage == [("events", 480, 0), ("odds", 477, 3)]


def test_anchor_offsets_first_capture_wins_close_moves(con, prm):
    both = [odds_event(EVENTS[0], 221.0), odds_event(EVENTS[1], 232.0)]
    s = session_for(both, [odds_event(EVENTS[0], 223.0), odds_event(EVENTS[1], 232.0)])
    theodds.poll(con, prm, session=s, key=FAKE_ODDS_KEY, now=T("2025-11-04T04:00:00"))
    # nothing new is due an hour later: no odds call, no credits
    n_calls = len(s.calls)
    out = theodds.poll(con, prm, session=s, key=FAKE_ODDS_KEY, now=T("2025-11-04T05:00:00"))
    assert not out["fetched"] and len(s.calls) == n_calls + 1  # events only
    # at T-9h evA is inside the 10 h anchor
    out = theodds.poll(con, prm, session=s, key=FAKE_ODDS_KEY, now=T("2025-11-04T15:00:00"))
    assert out["due"]["evA"] == ["t-10h"]
    lines = dict(con.execute("SELECT anchor, line FROM odds_snapshots WHERE event_id='evA' AND book='fanduel' "
                             "AND market='totals'").fetchall())
    assert lines == {"opening": 221.0, "t-10h": 223.0, "close": 223.0}
    lead = con.execute("SELECT lead_minutes FROM odds_snapshots WHERE event_id='evA' AND anchor='t-10h' "
                       "AND book='fanduel' AND market='totals'").fetchone()[0]
    assert lead == 9 * 60  # the real lead, not the nominal 600


def test_unpriced_event_does_not_spend_credits_every_poll(con, prm):
    s = session_for([odds_event(EVENTS[0], 221.0)], [odds_event(EVENTS[0], 221.0), odds_event(EVENTS[1], 232.0)])
    theodds.poll(con, prm, session=s, key=FAKE_ODDS_KEY, now=T("2025-11-04T04:00:00"))  # evB not priced yet
    assert not theodds.poll(con, prm, session=s, key=FAKE_ODDS_KEY, now=T("2025-11-04T04:30:00"))["fetched"]
    out = theodds.poll(con, prm, session=s, key=FAKE_ODDS_KEY, now=T("2025-11-04T05:01:00"))
    assert out["fetched"] and out["due"] == {"evB": ["opening"]}


def test_in_play_and_late_books_are_not_stored(con, prm):
    started = dict(EVENTS[0], commence_time="2025-11-04T03:00:00Z")
    late_book = odds_event(EVENTS[1], 230.0, last_update="2025-11-05T03:30:00Z")
    rows, skipped = theodds.parse_odds([odds_event(started, 220.0), late_book], T("2025-11-04T04:00:00"))
    assert rows == []
    assert skipped["in_play_events"] == 1 and skipped["book_updated_after_tip"] == 3


def test_quota_floor_stops_spending(con, prm):
    con.execute("INSERT INTO api_usage VALUES ('2025-11-04T00:00:00Z', 'theoddsapi', 'odds', 499, 5, 3)")
    s = session_for([odds_event(EVENTS[0], 221.0)], remaining=5)
    with pytest.raises(common.ApiError, match="quota low"):
        theodds.poll(con, prm, session=s, key=FAKE_ODDS_KEY, now=T("2025-11-04T04:00:00"))
    assert not any(c["url"].endswith("/odds") for c in s.calls)


def test_errors_never_echo_the_key(prm, con):
    s = FakeSession({"/events": FakeResponse({}, status=401, text=f"invalid apiKey {FAKE_ODDS_KEY}")})
    with pytest.raises(common.ApiError) as e:
        theodds.poll(con, prm, session=s, key=FAKE_ODDS_KEY, now=T("2025-11-04T04:00:00"))
    assert FAKE_ODDS_KEY not in str(e.value) and "<redacted>" in str(e.value)

    class Boom:
        def get(self, url, params=None, **kw):
            raise ConnectionError(f"{url}?apiKey={params['apiKey']} unreachable")

    with pytest.raises(common.ApiError) as e:
        theodds.poll(con, prm, session=Boom(), key=FAKE_ODDS_KEY, now=T("2025-11-04T04:00:00"))
    assert FAKE_ODDS_KEY not in str(e.value) and e.value.__cause__ is None and e.value.__suppress_context__


def test_key_only_from_environment_or_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv(theodds.KEY_VAR, raising=False)
    with pytest.raises(common.MissingKey, match="THEODDS_API_KEY"):
        common.get_key(theodds.KEY_VAR, dotenv=tmp_path / "missing.env")
    (tmp_path / ".env").write_text(f"# comment\n{theodds.KEY_VAR}='from-dotenv'\n")
    assert common.get_key(theodds.KEY_VAR, dotenv=tmp_path / ".env") == "from-dotenv"
    monkeypatch.setenv(theodds.KEY_VAR, "from-env")
    assert common.get_key(theodds.KEY_VAR, dotenv=tmp_path / ".env") == "from-env"
