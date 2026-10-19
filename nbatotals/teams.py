"""Team identity: every table keys teams by the 3-letter alias below.

Sources name teams differently (BallDontLie integer ids, The Odds API full
names). Everything is mapped to these aliases at ingest time.
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


def alias_from_full_name(name: str) -> str:
    try:
        return FULL_NAME_TO_ALIAS[name]
    except KeyError:
        raise KeyError(f"unknown team name {name!r}; add it to FULL_NAME_TO_ALIAS") from None
