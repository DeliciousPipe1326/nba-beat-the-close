"""Optional Tier B: Dunks & Threes player EPM. A stub, not implemented.

Tier A (the engine in this repository) uses box scores only, and that is what
the backtest in docs/RESULTS.md tested. Tier B would adjust each team's
efficiency for who is actually playing, using player EPM from Dunks & Threes
behind your own DUNKSANDTHREES_API_KEY. It has not been built or tested here,
so no result in this repository says anything about it.

If you build it:
- read the key with `common.get_key(KEY_VAR)` and never store it;
- keep everything point-in-time: an EPM value may only be used for games dated
  after the day it was published, and must pass the same truncation test as
  the Tier A features (`nbatotals/evaluate/leakage.py`);
- pre-register what you expect before you backtest it (docs/PREREGISTRATION.md
  shows the format), and do not commit any fetched data: Dunks & Threes data is
  licensed to you, not redistributable.
"""

from __future__ import annotations

from nbatotals.ingest import common

KEY_VAR = "DUNKSANDTHREES_API_KEY"


def fetch_player_epm(*args, **kwargs):
    common.get_key(KEY_VAR)  # fail early and clearly if the key is missing
    raise NotImplementedError("Tier B (Dunks & Threes player EPM) is a documented stub; see this module's docstring")
