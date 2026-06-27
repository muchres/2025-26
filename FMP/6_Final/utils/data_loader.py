"""
Loads LaLiga team metadata and the season's match list.

Data is read once at import time (matching the original behaviour) and exposed
as module-level objects plus a couple of convenience lookups.
"""

import pandas as pd

from utils.constants import LALIGA_COLOUR_CSV, LALIGA_MATCH_CSV, TEAM_MAP

# ── Team metadata ─────────────────────────────────────────────────────────────
_colour_df     = pd.read_csv(LALIGA_COLOUR_CSV)
ALL_TEAM_CODES = list(_colour_df["team_code"])

# Keyed by team_code — no accent characters ever appear in component IDs.
TEAM_DATA = {
    row["team_code"]: {
        "display":   row["team_display_name"],
        "full_name": row["team_full_name"],
        "logo":      row["team_logo"],
        "bg":        row["HEX1"],
        "text":      row["HEXT"],
        "b1":        row["HEX2"],
        "b2":        row["HEX3"],
    }
    for _, row in _colour_df.iterrows()
}

# ── Match list ────────────────────────────────────────────────────────────────
_match_df = pd.read_csv(LALIGA_MATCH_CSV)
_match_df["date_parsed"] = pd.to_datetime(_match_df["date"], format="%d/%m/%Y")

MATCHES = [
    {
        "id":        r["match_id"],
        "home":      TEAM_MAP.get(r["home"], r["home"]),
        "away":      TEAM_MAP.get(r["away"], r["away"]),
        "score":     f"{int(r['home_score'])}-{int(r['away_score'])}",
        "date":      r["date_parsed"].strftime("%d %b %Y"),
        "date_raw":  r["date_parsed"],
        "matchweek": int(r["matchweek"]),
    }
    for _, r in _match_df.iterrows()
]
MATCHES_DESC = sorted(MATCHES, key=lambda m: m["date_raw"], reverse=True)
MATCH_BY_ID  = {m["id"]: m for m in MATCHES}


# ── Convenience lookups ───────────────────────────────────────────────────────
def get_team_matches(code):
    return [m for m in MATCHES_DESC if m["home"] == code or m["away"] == code]


def team_name(code):
    return TEAM_DATA.get(code, {}).get("display", code)
