import pandas as pd
import pytest

from nbatotals import params as P
from nbatotals.evaluate import market


def quotes(rows):
    return pd.DataFrame(
        [dict(game_id=g, book=b, market="totals", anchor=a, line=l, over_price=o, under_price=u)
         for g, b, a, l, o, u in rows]
    )


def test_consensus_rules():
    prm = P.load()
    odds = quotes([
        (1, "a", "close", 220.0, 1.91, 1.91),
        (1, "b", "close", 221.0, 1.87, 1.95),
        (1, "c", "close", 221.0, 1.95, 1.87),
        (1, "d", "close", 55.0, 1.91, 1.91),      # half total filed as full game: >10 pts from median
        (1, "e", "close", 221.5, 1.90, None),     # missing price: ignored
        (2, "a", "close", 210.0, 1.91, 1.91),     # only two books: not scored
        (2, "b", "close", 210.5, 1.91, 1.91),
    ])
    c = market.consensus(odds, prm).set_index("game_id")
    assert list(c.index) == [1]
    row = c.loc[1]
    assert row["books"] == 3
    assert row["line"] == 221.0
    p = [0.5, (1 / 1.87) / (1 / 1.87 + 1 / 1.95), (1 / 1.95) / (1 / 1.95 + 1 / 1.87)]
    assert row["p_over"] == pytest.approx(sum(p) / 3)
    assert row["over_price"] == 1.91 and row["under_price"] == 1.91
    assert row["p_under"] == pytest.approx(1 - row["p_over"])
