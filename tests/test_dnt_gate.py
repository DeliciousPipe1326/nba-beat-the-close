"""Experiment 1 (Dunks & Threes): the file reader, the game join and the Phase A gate logic, offline."""

import json

import numpy as np
import pandas as pd
import pytest

from nbatotals.evaluate import dnt_gate
from nbatotals.evaluate.adapters import dnt_box
from nbatotals.teams import ALIASES, NBA_STATS_ID_TO_ALIAS

ID = {a: i for i, a in NBA_STATS_ID_TO_ALIAS.items()}


def test_nba_stats_map_is_one_to_one():
    assert len(NBA_STATS_ID_TO_ALIAS) == 30 and set(NBA_STATS_ID_TO_ALIAS.values()) == set(ALIASES)
    assert NBA_STATS_ID_TO_ALIAS[1610612739] == "CLE" and NBA_STATS_ID_TO_ALIAS[1610612737] == "ATL"


def _player(gid, team, name, mp, pts):
    return {"game_id": gid, "team_id": ID[team], "player_id": hash(name) % 10**7, "player_name": name, "p_mp": mp,
            "p_pts": pts, "p_pace": 99.0, "p_fg2a": 5.0, "p_fg3a": 3.0, "p_fta": 2.0, "p_orb": 0.5, "p_tov": 1.0}


def _write(root, date, rows):
    (root / date).mkdir(parents=True, exist_ok=True)
    (root / date / dnt_box.FILE).write_text(json.dumps(rows))


def _games():
    return pd.DataFrame({
        "id": [1, 2, 3], "game_date": ["2023-01-10", "2023-01-10", "2023-01-11"], "season": 2022,
        "postseason": 0, "status": "final", "home": ["CLE", "BOS", "CLE"], "away": ["ATL", "MIA", "BOS"],
        "home_pts": [110.0, 100.0, 120.0], "away_pts": [105.0, 98.0, 125.0], "periods": [4, 4, 5]})


def test_read_day_and_join_by_date_and_both_aliases(tmp_path):
    _write(tmp_path, "2023-01-10", [_player(22200001, "ATL", "A", 30, 20), _player(22200001, "CLE", "B", 30, 20),
                                    _player(22200002, "MIA", "C", 30, 20), _player(22200002, "BOS", "D", 30, 20)])
    _write(tmp_path, "2023-01-11", [_player(22200003, "BOS", "E", 30, 20), _player(22200003, "CLE", "F", 30, 20)])
    (tmp_path / "2023-01-12").mkdir()  # a date folder without the file reads as empty
    assert dnt_box.read_day(tmp_path, "2023-01-12").empty
    rows = dnt_box.read_all(tmp_path)
    m = dnt_box.match_games(rows, _games()).sort_values("id")
    assert list(m["id"]) == [1, 2, 3] and list(m["game_id"]) == [22200001, 22200002, 22200003]
    # same teams on another date do not join
    moved = rows.assign(date=rows["date"].replace({"2023-01-11": "2023-01-12"}))
    assert set(dnt_box.match_games(moved, _games())["id"]) == {1, 2}


def test_unknown_team_id_is_refused(tmp_path):
    bad = _player(22200001, "ATL", "A", 30, 20) | {"team_id": 99}
    _write(tmp_path, "2023-01-10", [bad])
    with pytest.raises(ValueError, match="team id"):
        dnt_box.read_day(tmp_path, "2023-01-10")


def test_name_normalisation_and_minutes():
    assert dnt_gate.norm_name("Luka Dončić") == dnt_gate.norm_name("luka doncic")
    assert dnt_gate.norm_name("Tim Hardaway Jr.") == "tim hardaway"
    assert dnt_gate.norm_name("Kelly Oubre Jr") == dnt_gate.norm_name("Kelly Oubre")
    assert dnt_gate.norm_name("Shai Gilgeous-Alexander") == "shai gilgeous alexander"
    assert dnt_gate.parse_minutes("32") == 32.0 and dnt_gate.parse_minutes("12:30") == 12.5
    assert all(dnt_gate.parse_minutes(v) == 0.0 for v in ("00", "0:00", None, ""))


def _s(**kw):
    base = {"a_r2": 0.8, "b_share": 0.015, "c_delta": 20.0, "d_median": 240.0, "d_ot_diff": 0.0}
    return base | kw


@pytest.mark.parametrize("kw, season", [
    ({}, "pre-game"),
    ({"b_share": 0.003}, "pre-game (near tip / active list known)"),
    ({"a_r2": 0.97}, "gate fails"),
    ({"b_share": 0.001}, "gate fails"),
    ({"c_delta": 3.0}, "gate fails"),
    ({"d_ot_diff": 24.0}, "gate fails"),
    ({"d_median": 260.0}, "gate fails"),
    ({"d_ot_diff": 3.0}, "gate fails (ambiguous)"),
    ({"d_median": 233.0}, "gate fails (ambiguous)"),
    ({"a_r2": 0.92}, "gate fails (ambiguous)"),
    ({"c_delta": 9.0}, "gate fails (ambiguous)"),
    ({"b_share": 0.003, "d_ot_diff": 3.0}, "gate fails (ambiguous)"),
])
def test_pre_registered_decision_rule(kw, season):
    assert dnt_gate.verdicts(_s(**kw))["season"] == season


def test_build_and_stats_on_a_tiny_league(tmp_path):
    # game 1 regulation, game 3 overtime; each team: two players, minutes summing to 240
    rows = []
    for gid, (h, a) in {22200001: ("CLE", "ATL"), 22200003: ("CLE", "BOS")}.items():
        for team in (h, a):
            rows += [_player(gid, team, f"{team} one", 200.0, 50.0), _player(gid, team, f"{team} two", 40.0, 10.0)]
    date = {22200001: "2023-01-10", 22200003: "2023-01-11"}
    dnt = pd.DataFrame(rows)
    dnt = dnt.assign(date=dnt["game_id"].map(date), team=dnt["team_id"].map(NBA_STATS_ID_TO_ALIAS))
    bdl = pd.DataFrame([
        {"game_id": gid, "game_date": "", "season": 2022, "team": t, "key": dnt_gate.norm_name(f"{t} {w}"),
         "minutes": m}
        for gid, teams in {1: ("CLE", "ATL"), 3: ("CLE", "BOS")}.items() for t in teams
        for w, m in (("one", 190.0), ("two", 50.0 if gid == 1 else 0.0))])
    d = dnt_gate.build(_games(), dnt, bdl)
    s = dnt_gate.stats(d, (2022,))
    assert s["d_median"] == 240.0 and s["d_ot_diff"] == 0.0
    # game totals: projection 120 per game; actual 215 (regulation) and 245 (OT)
    assert s["c_reg_err"] == 95.0 and s["c_ot_err"] == 125.0 and s["c_delta"] == 30.0
    # p_mp >= 20 is every player-game (8); the two "two" players in the OT game played 0
    assert s["b_n"] == 8 and s["b_zero"] == 2
    assert np.isclose(s["a_r2"], dnt_gate._r2([190, 50] * 2 + [190, 0] * 2, [200, 40] * 4))
