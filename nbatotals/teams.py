"""Team identity: every table keys teams by the 3-letter alias below.

Sources name teams differently (BallDontLie integer ids, NBA Stats ids, The
Odds API full names). Everything is mapped to these aliases at ingest time.
"""

ALIASES = (
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
)

# BallDontLie team ids (stable across their v1 API).
BDL_ID_TO_ALIAS = {
    1: "ATL", 2: "BOS", 3: "BKN", 4: "CHA", 5: "CHI", 6: "CLE", 7: "DAL",
    8: "DEN", 9: "DET", 10: "GSW", 11: "HOU", 12: "IND", 13: "LAC", 14: "LAL",
    15: "MEM", 16: "MIA", 17: "MIL", 18: "MIN", 19: "NOP", 20: "NYK",
    21: "OKC", 22: "ORL", 23: "PHI", 24: "PHX", 25: "POR", 26: "SAC",
    27: "SAS", 28: "TOR", 29: "UTA", 30: "WAS",
}

# NBA Stats team ids (stats.nba.com; also used by Dunks & Threes).
NBA_STATS_ID_TO_ALIAS = {
    1610612737: "ATL", 1610612738: "BOS", 1610612751: "BKN", 1610612766: "CHA",
    1610612741: "CHI", 1610612739: "CLE", 1610612742: "DAL", 1610612743: "DEN",
    1610612765: "DET", 1610612744: "GSW", 1610612745: "HOU", 1610612754: "IND",
    1610612746: "LAC", 1610612747: "LAL", 1610612763: "MEM", 1610612748: "MIA",
    1610612749: "MIL", 1610612750: "MIN", 1610612740: "NOP", 1610612752: "NYK",
    1610612760: "OKC", 1610612753: "ORL", 1610612755: "PHI", 1610612756: "PHX",
    1610612757: "POR", 1610612758: "SAC", 1610612759: "SAS", 1610612761: "TOR",
    1610612762: "UTA", 1610612764: "WAS",
}

FULL_NAME_TO_ALIAS = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU",
    "Indiana Pacers": "IND", "Los Angeles Clippers": "LAC",
    "LA Clippers": "LAC", "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR", "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}

assert set(BDL_ID_TO_ALIAS.values()) == set(ALIASES)
assert set(FULL_NAME_TO_ALIAS.values()) == set(ALIASES)
assert set(NBA_STATS_ID_TO_ALIAS.values()) == set(ALIASES) and len(NBA_STATS_ID_TO_ALIAS) == 30


def alias_from_full_name(name: str) -> str:
    try:
        return FULL_NAME_TO_ALIAS[name]
    except KeyError:
        raise KeyError(f"unknown team name {name!r}; add it to FULL_NAME_TO_ALIAS") from None
