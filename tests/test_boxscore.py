import pytest

from nbatotals import boxscore


def side(**kw):
    base = dict(pts=110, fgm=40, fga=88, fta=20, orb=10, drb=34, tov=13)
    base.update(kw)
    return base


def test_possessions_formula():
    # 88 - 10 + 13 + 0.44 * 20 = 99.8
    assert boxscore.team_possessions(88, 20, 10, 13) == pytest.approx(99.8)


def test_derive_regulation_and_overtime():
    h, a = boxscore.derive(side(pts=110), side(pts=100, fga=90), periods=4)
    poss = 0.5 * (99.8 + 101.8)
    assert h["possessions"] == a["possessions"] == pytest.approx(poss)
    assert h["pace"] == pytest.approx(poss)
    assert h["ortg"] == pytest.approx(100 * 110 / poss)
    assert h["drtg"] == pytest.approx(a["ortg"])

    h_ot, _ = boxscore.derive(side(), side(), periods=5)
    assert h_ot["minutes"] == 53
    assert h_ot["pace"] == pytest.approx(48 * 99.8 / 53)


def test_american_to_decimal():
    assert boxscore.american_to_decimal(150) == pytest.approx(2.5)
    assert boxscore.american_to_decimal(-110) == pytest.approx(1 + 100 / 110)
    assert boxscore.american_to_decimal(-100) == pytest.approx(2.0)
    assert boxscore.american_to_decimal(50) is None
    assert boxscore.american_to_decimal(None) is None
