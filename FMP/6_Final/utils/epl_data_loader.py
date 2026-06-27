"""Loads Premier League team metadata and the season's match list."""

import pandas as pd

from utils.constants import EPL_COLOUR_CSV, EPL_MATCH_CSV, EPL_TEAM_MAP

# ── Team metadata ─────────────────────────────────────────────────────────────
_colour_df = pd.read_csv(EPL_COLOUR_CSV, encoding="utf-8-sig")
EPL_ALL_TEAM_CODES = list(_colour_df["team_code"])

EPL_TEAM_DATA = {
    row["team_code"]: {
        "display":   row["team_display_name"],
        "full_name": row["team_full_name"],
        "logo":      row["team_logo"],
        "logo_src":  f"/epl-logos/{row['team_logo']}",
        "bg":        row["HEX1"],
        "text":      row["HEXT"],
        "b1":        row["HEX2"],
        "b2":        row["HEX3"],
    }
    for _, row in _colour_df.iterrows()
}

# ── Match list ────────────────────────────────────────────────────────────────
_match_df = pd.read_csv(EPL_MATCH_CSV, encoding="utf-8-sig")
_match_df["date_parsed"] = pd.to_datetime(_match_df["date"], format="%d/%m/%Y")

EPL_MATCHES = [
    {
        "id":       r["match_id"],
        "home":     EPL_TEAM_MAP.get(r["home"], r["home"]),
        "away":     EPL_TEAM_MAP.get(r["away"], r["away"]),
        "score":    f"{int(r['home_score'])}-{int(r['away_score'])}",
        "date":     r["date_parsed"].strftime("%d %b %Y"),
        "date_raw": r["date_parsed"],
        "league":   "epl",
    }
    for _, r in _match_df.iterrows()
]
EPL_MATCHES_DESC = sorted(EPL_MATCHES, key=lambda m: m["date_raw"], reverse=True)
EPL_MATCH_BY_ID  = {m["id"]: m for m in EPL_MATCHES}


# ── Convenience lookups ───────────────────────────────────────────────────────
def epl_get_team_matches(code):
    return [m for m in EPL_MATCHES_DESC if m["home"] == code or m["away"] == code]


def epl_team_name(code):
    return EPL_TEAM_DATA.get(code, {}).get("display", code)
