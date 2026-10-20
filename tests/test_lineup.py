"""Experiment 2: the lineup projector's arithmetic and its external-file truncation test."""

import shutil

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pyarrow")  # the private lake is parquet; synthetic files mirror it

from nbatotals import params as params_io
from nbatotals.evaluate import leakage
from nbatotals.evaluate.adapters import legacy_players
from nbatotals.features import players
from nbatotals.features.players import PlayerInputs
from nbatotals.model import lineup_pace_eff
from nbatotals.model.lineup_pace_eff import LineupPaceEff
from tests.fixtures import synthetic


@pytest.fixture(scope="module")
def league():
    return synthetic.generate(seasons=(2021, 2022), days=30, games_per_day=5, seed=11)


@pytest.fixture(scope="module")
def prm():
    return params_io.load()


@pytest.fixture(scope="module")
def folders(league, tmp_path_factory):
    games, _ = league
    dnt, ratings = synthetic.player_frames(games, seed=2)
    return synthetic.write_player_files(dnt, ratings, tmp_path_factory.mktemp("players"))


def _truncate(src_dnt, src_epm, dst, date, dnt_game_id):
    """Copy the folders as they stood before `date`'s other games and any later file existed."""
    dnt_dir, epm_dir = dst / "dunksandthrees", dst / "player_epm"
    for d in src_dnt.iterdir():
        if d.name < date:
            shutil.copytree(d, dnt_dir / d.name)
        elif d.name == date:
            rows = pd.read_json(d / legacy_players.DNT_BOX_FILE)
            (dnt_dir / d.name).mkdir(parents=True)
            target = dnt_dir / d.name / legacy_players.DNT_BOX_FILE
            rows[rows["game_id"] == dnt_game_id].to_json(target, orient="records")
    for f in src_epm.glob("season=*/*.parquet"):
        if f.stem > date:
            continue
        out = epm_dir / f.parent.name / f.name
        out.parent.mkdir(parents=True, exist_ok=True)
        rows = pd.read_parquet(f)
        if f.stem == date:
            rows = rows[rows["game_id"] == dnt_game_id]
        rows.to_parquet(out, index=False)
    return dnt_dir, epm_dir


@pytest.mark.parametrize("state", [None, {"scale": 1.25, "shrinkage": 5.0}])
def test_external_file_truncation(league, prm, folders, tmp_path, state):
    games, box = league
    sample = leakage.stratified_sample(games, per_cell=4, seed=1)
    assert sample["season"].nunique() == 2 and len(sample) >= 30
    full = LineupPaceEff(legacy_players.player_inputs(*folders)).predict(sample, games, box, state, prm)
    full = full.set_index("game_id")["total_proj"]
    box_dates = box.merge(games[["id", "game_date"]], left_on="game_id", right_on="id")["game_date"]
    mismatches = []
    for i, target in enumerate(sample.itertuples(index=False)):
        dirs = _truncate(folders[0], folders[1], tmp_path / str(i), target.game_date, 9_000_000 + target.id)
        keep_games = games[games["game_date"] < target.game_date]
        keep_box = box[(box_dates < target.game_date).to_numpy()]
        blind = pd.DataFrame([target._asdict()]).assign(home_pts=np.nan, away_pts=np.nan)
        cut = LineupPaceEff(legacy_players.player_inputs(*dirs)).predict(blind, keep_games, keep_box, state, prm)
        if cut["total_proj"].iloc[0] != full.loc[target.id]:
            mismatches.append((target.id, full.loc[target.id], cut["total_proj"].iloc[0]))
    assert mismatches == []


def test_external_truncation_catches_a_leaky_reference(league, prm, folders, tmp_path, monkeypatch):
    """Positive control: a reference mean over the whole season (later files) must be caught."""
    games, box = league
    honest = lineup_pace_eff._references

    def leaky(f, hist, own, k):
        return honest(f.assign(game_date="9999-12-31"), hist, own, k)

    monkeypatch.setattr(lineup_pace_eff, "_references", leaky)
    sample = leakage.stratified_sample(games, per_cell=2, seed=4)
    sample = sample[sample["phase"] == "mid"].head(3)
    full = LineupPaceEff(legacy_players.player_inputs(*folders)).predict(sample, games, box, None, prm)
    full = full.set_index("game_id")["total_proj"]
    box_dates = box.merge(games[["id", "game_date"]], left_on="game_id", right_on="id")["game_date"]
    caught = 0
    for i, target in enumerate(sample.itertuples(index=False)):
        dirs = _truncate(folders[0], folders[1], tmp_path / str(i), target.game_date, 9_000_000 + target.id)
        blind = pd.DataFrame([target._asdict()]).assign(home_pts=np.nan, away_pts=np.nan)
        cut = LineupPaceEff(legacy_players.player_inputs(*dirs)).predict(
            blind, games[games["game_date"] < target.game_date], box[(box_dates < target.game_date).to_numpy()],
            None, prm)
        caught += cut["total_proj"].iloc[0] != full.loc[target.id]
    assert caught == len(sample)


def test_team_values_arithmetic_and_rating_fallback():
    dnt = pd.DataFrame({
        "date": ["2024-01-02"] * 3, "game_id": [7] * 3, "team": ["BOS"] * 3, "player_id": [1, 2, 3],
        "p_mp": [30.0, 10.0, 0.0],
    })
    ratings = pd.DataFrame({
        "date": ["2024-01-02", "2024-01-01", "2024-01-03"], "game_id": [7, 6, 8], "player_id": [1, 2, 2],
        "oepm": [2.0, -1.0, 9.0], "depm": [1.0, 0.5, 9.0], "p_t_poss_48": [100.0, 96.0, 50.0],
    })
    tv = PlayerInputs(dnt, ratings).team_values().iloc[0]
    # player 2 has no row for game 7: his latest earlier rating (dated 01-01) is used, never the later one
    assert tv["O"] == pytest.approx(5 * (30 * 2.0 + 10 * -1.0) / 40)
    assert tv["Dv"] == pytest.approx(5 * (30 * 1.0 + 10 * 0.5) / 40)
    assert tv["P"] == pytest.approx((30 * 100 + 10 * 96) / 40)
    assert tv["rated_minutes_share"] == pytest.approx(0.75)


def test_dnt_games_joins_on_date_and_both_teams():
    dnt = pd.DataFrame({"date": ["2024-01-02"] * 4, "game_id": [7, 7, 8, 8], "team": ["BOS", "NYK", "LAL", "DEN"]})
    games = pd.DataFrame({"id": [1, 2, 3], "game_date": ["2024-01-02", "2024-01-02", "2024-01-03"],
                          "home": ["NYK", "DEN", "BOS"], "away": ["BOS", "UTA", "NYK"]})
    m = players.dnt_games(dnt, games)
    assert m[["dnt_game_id", "game_id"]].values.tolist() == [[7, 1]]


def test_lineup_information_moves_the_projection(league, prm):
    """Zeroing a team's two best offensive players lowers its O and changes the projection."""
    games, box = league
    inp = synthetic.player_inputs(games, seed=3)
    target = games[games["season"] == 2022].iloc[[60]]
    base = LineupPaceEff(inp).predict(target, games, box, None, prm)["total_proj"].iloc[0]
    tv = inp.team_values()
    gid = 9_000_000 + int(target["id"].iloc[0])
    home = target["home"].iloc[0]
    d = inp.dnt.merge(inp.ratings[["game_id", "player_id", "oepm"]], on=["game_id", "player_id"], how="left")
    top = d[(d["game_id"] == gid) & (d["team"] == home)].nlargest(2, "oepm")["player_id"]
    dnt2 = inp.dnt.copy()
    dnt2.loc[(dnt2["game_id"] == gid) & dnt2["player_id"].isin(top), "p_mp"] = 0.0
    inp2 = PlayerInputs(dnt2, inp.ratings)
    out = LineupPaceEff(inp2).predict(target, games, box, None, prm)["total_proj"].iloc[0]

    def o(t):
        return t[(t["dnt_game_id"] == gid) & (t["team"] == home)]["O"].iloc[0]

    assert o(inp2.team_values()) < o(tv)
    assert out != base
