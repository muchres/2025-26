"""
Lineup data processing — mirrors the team_overview.ipynb pipeline.

All data loading, merging, and computation lives here.
pages/lineup.py imports from this module and contains no business logic.
"""

import os
from collections import defaultdict
from datetime import datetime

import pandas as pd

from utils.data_loader import TEAM_DATA, MATCHES_DESC, team_name
from utils.constants import formation_coords

# ── Absolute paths ────────────────────────────────────────────────────────────
_HERE    = os.path.dirname(os.path.abspath(__file__))   # utils/
_APP_DIR = os.path.dirname(_HERE)                        # 6_Final/
_PROJECT = os.path.dirname(_APP_DIR)                     # 2025-26/FMP
_DATA    = os.path.join(_PROJECT, "2_Data")
_WORKING = os.path.join(_PROJECT, "3_Working")

# ── Raw data (loaded once at import time) ─────────────────────────────────────
mins_raw     = pd.read_csv(os.path.join(_DATA, "laliga_player_minutes_formations.csv"))
form_map_raw = pd.read_csv(os.path.join(_WORKING, "formation_mapping.csv"), encoding="utf-8-sig")
form_map_raw["formation"] = form_map_raw["formation"].apply(
    lambda x: str(int(x)) if pd.notna(x) else None
)
players_raw  = pd.read_csv(os.path.join(_DATA, "laliga_player_list.csv"),   encoding="utf-8-sig")
depart_raw   = pd.read_csv(os.path.join(_DATA, "laliga_confirmed_departure.csv"))

# ── Public lookups ────────────────────────────────────────────────────────────
DISP_NAME  = dict(zip(players_raw["player_id"], players_raw["Display Name"]))
SHORT_NAME = dict(zip(players_raw["player_id"], players_raw["Short Display Name"]))

JERSEY_NUM: dict = (
    players_raw.dropna(subset=["Jersey Number"])
    .drop_duplicates("player_id", keep="first")
    .assign(_jn=lambda d: d["Jersey Number"].astype(float).astype(int).astype(str))
    .set_index("player_id")["_jn"]
    .to_dict()
)

# ── Formation number → string (e.g. formation# 2 → "442") ────────────────────
_FORM_NUM_TO_STR = (
    form_map_raw[["formation#", "formation"]]
    .drop_duplicates("formation#")
    .set_index("formation#")["formation"]
    .astype(str)
    .to_dict()
)

# ── Pre-compute starting formation per (match_id, team_code) ─────────────────
# Used to build match-selector labels.
_start_rows = (
    mins_raw[mins_raw["team setp up"] == 1]
    [["match_id", "team_code", "Team Formation"]]
    .drop_duplicates(["match_id", "team_code"])
    .dropna(subset=["Team Formation"])
    .copy()
)
_start_rows["Team Formation"] = _start_rows["Team Formation"].astype(int)
_start_rows["formation_str"]  = _start_rows["Team Formation"].map(_FORM_NUM_TO_STR)

MATCH_TEAM_FORMATION = dict(
    zip(
        zip(_start_rows["match_id"], _start_rows["team_code"]),
        _start_rows["formation_str"],
    )
)

# ── Canonical position order for the predicted lineup table ──────────────────
POS_ORDER = ["GK", "LWB", "LB", "CB", "RB", "RWB", "CDM", "LM", "CM", "RM", "CAM", "LW", "RW", "SS", "ST"]

# ── Position sections (display order in the minutes table) ────────────────────
SQUAD_SECTIONS = [
    ("Goalkeepers",  {"GK"}),
    ("Full Backs",   {"LB", "RB", "LWB", "RWB"}),
    ("Centre Backs", {"CB"}),
    ("Midfielders",  {"CDM", "CM", "CAM"}),
    ("Wingers",      {"LW", "RW", "LM", "RM"}),
    ("Strikers",     {"ST", "SS"}),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def fmt_formation(f):
    """'442' → '4-4-2',  '4231' → '4-2-3-1'.  None → '?'."""
    if f is None:
        return "?"
    s = str(int(f)) if not isinstance(f, str) else str(f)
    return "-".join(list(s))


# ─────────────────────────────────────────────────────────────────────────────
# Match selector options
# ─────────────────────────────────────────────────────────────────────────────

def get_match_options(code):
    """
    Return (options, all_ids) for the dcc.Checklist, sorted date desc.

    Label format:
      Matchweek 33 - 08/05/2026  4-2-3-1 vs Barcelona 4-3-3 (W3-0 H)
    """
    options, all_ids = [], []
    for m in MATCHES_DESC:
        if m["home"] != code and m["away"] != code:
            continue

        is_home  = m["home"] == code
        opp_code = m["away"] if is_home else m["home"]
        HA       = "H" if is_home else "A"

        h_str, a_str = m["score"].split("-")
        h_sc, a_sc   = int(h_str), int(a_str)
        own_sc  = h_sc if is_home else a_sc
        opp_sc  = a_sc if is_home else h_sc
        result  = "W" if own_sc > opp_sc else "L" if own_sc < opp_sc else "D"

        own_raw = MATCH_TEAM_FORMATION.get((m["id"], code))
        opp_raw = MATCH_TEAM_FORMATION.get((m["id"], opp_code))
        own_fmt = fmt_formation(own_raw) if own_raw else "?"
        opp_fmt = fmt_formation(opp_raw) if opp_raw else "?"

        try:
            date_str = datetime.strptime(m["date"], "%d %b %Y").strftime("%d/%m/%Y")
        except Exception:
            date_str = m["date"]

        opp   = team_name(opp_code)
        label = (
            f"Matchweek {m['matchweek']} - {date_str}  "
            f"{own_fmt} vs {opp} {opp_fmt} ({result}{own_sc}-{opp_sc} {HA})"
        )
        options.append({"label": label, "value": m["id"]})
        all_ids.append(m["id"])

    return options, all_ids


# ─────────────────────────────────────────────────────────────────────────────
# Core data pipeline  (mirrors team_overview.ipynb, week_selection → match_ids)
# ─────────────────────────────────────────────────────────────────────────────

def prepare_team_data(code, match_ids=None):
    """
    Process player-minutes data for a team.

    match_ids acts as week_selection in the notebook:
      None    → full season
      [...]   → only those match_id values (equiv. to week_selection)
      []      → no matches → all empty results

    Returns: (formation_df1, formation_summary, all_players, mins_merged)
    """
    mins = mins_raw[mins_raw["team_code"] == code].copy()

    if match_ids is not None:
        mins = mins[mins["match_id"].isin(match_ids)]

    mins = mins.merge(
        form_map_raw[["formation#", "pos#", "formation", "pos"]],
        left_on=["Team Formation", "Team Player Formation"],
        right_on=["formation#", "pos#"],
        how="left",
    ).drop(columns=["formation#", "pos#"])

    mins["Jersey Number"] = (
        mins.groupby(["team_code", "player_id"])["Jersey Number"].transform("min")
    )

    formation_df = (
        mins[mins["team setp up"] == 1]
        [["match_id", "team_code", "formation"]]
        .drop_duplicates()
        .groupby(["team_code", "formation"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
        .sort_values(["team_code", "count"], ascending=[True, False])
        .reset_index(drop=True)
    )

    if formation_df.empty:
        return (
            pd.DataFrame(columns=["team_code", "formation", "count", "default"]),
            pd.DataFrame({"team_code": [code], "back3": [0], "back4": [0], "back5": [0],
                          "front1": [0], "front2": [0], "front3": [0]}),
            pd.DataFrame(columns=[
                "team_code", "Jersey Number", "player_id",
                "starts", "subs", "Games Played",
                "Position", "Secondary Position", "Mins",
            ]),
            mins,
        )

    # ── formation_summary: back/front breakdown ───────────────────────────────
    _f = formation_df.copy()
    _f["back"]  = _f["formation"].astype(str).str[0].astype(int)
    _f["front"] = _f["formation"].astype(str).str[-1].astype(int)
    for b in [3, 4, 5]:
        _f[f"back{b}"] = _f["count"] * (_f["back"] == b).astype(int)
    for f in [1, 2, 3]:
        _f[f"front{f}"] = _f["count"] * (_f["front"] == f).astype(int)
    formation_summary = (
        _f.groupby("team_code", as_index=False)
        [["back3", "back4", "back5", "front1", "front2", "front3"]]
        .sum()
    )

    # ── formation_df1: add default flag ───────────────────────────────────────
    formation_df1 = formation_df.copy()
    formation_df1["_front"] = formation_df1["formation"].astype(str).str[-1].astype(int)
    formation_df1 = formation_df1.merge(
        formation_summary[["team_code", "front1", "front2", "front3"]],
        on="team_code", how="left",
    )
    formation_df1["_dom_front"] = (
        formation_df1[["front1", "front2", "front3"]]
        .idxmax(axis=1).str[-1].astype(int)
    )
    _max = formation_df1.groupby("team_code")["count"].transform("max")
    formation_df1["_is_max"] = formation_df1["count"] == _max
    formation_df1["_n_max"]  = formation_df1.groupby("team_code")["_is_max"].transform("sum")
    formation_df1["default"] = (
        formation_df1["_is_max"] & (
            (formation_df1["_n_max"] == 1) |
            (formation_df1["_front"] == formation_df1["_dom_front"])
        )
    ).astype(int)
    formation_df1 = (
        formation_df1
        .drop(columns=["_front", "_is_max", "_n_max", "front1", "front2", "front3", "_dom_front"])
        .sort_values(["team_code", "default", "count"], ascending=[True, False, False])
        .reset_index(drop=True)
    )

    # ── start_sub: starts and substitute counts ───────────────────────────────
    start_sub = (
        mins.groupby(["team_code", "Jersey Number", "player_id"], as_index=False)
        .agg(starts=("team setp up", "sum"), subs=("player on", "sum"))
    )

    # ── mins_pos: total minutes per player per position (with collapse) ────────
    mins_pos = mins.copy()
    #mins_pos["pos"] = mins_pos["pos"].replace(
    #    {"LWB": "LB", "RWB": "RB", "LM": "LW", "RM": "RW"}
    #)
    mins_pos = (
        mins_pos.groupby(["team_code", "Jersey Number", "player_id", "pos"], as_index=False)
        .agg(minsec=("minsec", "sum"))
    )
    mins_pos["pct"] = (
        mins_pos["minsec"]
        / mins_pos.groupby(["team_code", "Jersey Number", "player_id"])["minsec"]
        .transform("sum")
    )

    _key = ["team_code", "Jersey Number", "player_id"]
    _primary = (
        mins_pos.loc[mins_pos.groupby(_key)["minsec"].idxmax(), _key + ["pos"]]
        .rename(columns={"pos": "Position"})
    )
    _secondary = (
        mins_pos.merge(_primary, on=_key)
        .query("pct >= 0.2 and pos != Position")
        .groupby(_key)["pos"]
        .agg(", ".join)
        .reset_index()
        .rename(columns={"pos": "Secondary Position"})
    )
    _total_mins = (
        mins_pos.groupby(_key, as_index=False)["minsec"]
        .sum()
        .rename(columns={"minsec": "Mins"})
    )

    all_players = start_sub.copy()
    all_players["Games Played"] = (
        all_players["starts"].astype(int).astype(str)
        + "(" + all_players["subs"].astype(int).astype(str) + ")"
    )
    all_players = (
        all_players
        .merge(_primary,    on=_key, how="left")
        .merge(_secondary,  on=_key, how="left")
        .merge(_total_mins, on=_key, how="left")
    )
    all_players["Mins"] = all_players["Mins"].fillna(0).round().astype(int)

    return formation_df1, formation_summary, all_players, mins


def get_default_formation(formation_df1):
    """Return the default formation string, or None if no data."""
    if formation_df1.empty:
        return None
    defaults = formation_df1[formation_df1["default"] == 1]
    return defaults.iloc[0]["formation"] if not defaults.empty else None


def get_predicted_lineup(formation_df1, mins, unavailable_ids=None, code=None):
    """
    Predict the starting XI for a team using a greedy slot-filling algorithm.

    Params
    ------
    formation_df1   : output of prepare_team_data (formation counts + default flag)
    mins            : output of prepare_team_data (player-minute rows, already has pos column)
    unavailable_ids : iterable of player_ids to exclude from selection
    code            : team_code; when provided, full-season data is used as fallback
                      so that positions vacated by unavailable players are still filled

    Returns
    -------
    DataFrame with columns ['pos', 'Jersey Number', 'player_id', 'alt_player_id'],
    sorted by POS_ORDER.  Empty DataFrame if no formation / match data.
    """
    selected_formation = get_default_formation(formation_df1)
    if selected_formation is None or mins.empty:
        return pd.DataFrame(columns=["pos", "Jersey Number", "player_id", "alt_player_id"])

    unavailable_set = set(unavailable_ids or [])

    lineup_slots = (
        form_map_raw[form_map_raw["formation"] == selected_formation][["pos"]]
        .reset_index(drop=True)
    )

    # Minutes and starts per player per position (mirrors minpos_selected_team in notebook)
    mins_pos = (
        mins.dropna(subset=["pos"])
        .groupby(["Jersey Number", "player_id", "pos"], as_index=False)
        .agg(starts=("team setp up", "sum"), minsec=("minsec", "sum"))
    )
    mins_pos = mins_pos.sort_values(["starts", "minsec"], ascending=[False, False]).reset_index(drop=True)

    # Greedy slot-filling: iterate players (best first) and fill position slots
    slots_needed = lineup_slots["pos"].value_counts().to_dict()
    slots_filled = defaultdict(list)
    assigned = set()

    for _, row in mins_pos.iterrows():
        pos = row["pos"]
        pid = row["player_id"]
        if pid in assigned or pid in unavailable_set:
            continue
        if pos in slots_needed and len(slots_filled[pos]) < slots_needed[pos]:
            slots_filled[pos].append(pid)
            assigned.add(pid)

    # Fallback: fill any slot still empty using full-season data for this team
    unfilled = {pos for pos, need in slots_needed.items()
                if len(slots_filled.get(pos, [])) < need}
    if unfilled and code is not None:
        fb = mins_raw[mins_raw["team_code"] == code].copy()
        fb = fb.merge(
            form_map_raw[["formation#", "pos#", "formation", "pos"]],
            left_on=["Team Formation", "Team Player Formation"],
            right_on=["formation#", "pos#"],
            how="left",
        ).drop(columns=["formation#", "pos#"])
        fb_pos = (
            fb.dropna(subset=["pos"])
            .groupby(["Jersey Number", "player_id", "pos"], as_index=False)
            .agg(starts=("team setp up", "sum"), minsec=("minsec", "sum"))
        )
        fb_pos = fb_pos.sort_values(["starts", "minsec"], ascending=[False, False])
        for _, row in fb_pos.iterrows():
            pos = row["pos"]
            pid = row["player_id"]
            if pos not in unfilled or pid in assigned or pid in unavailable_set:
                continue
            if len(slots_filled.get(pos, [])) < slots_needed.get(pos, 0):
                slots_filled[pos].append(pid)
                assigned.add(pid)
                if len(slots_filled.get(pos, [])) >= slots_needed.get(pos, 0):
                    unfilled.discard(pos)
            if not unfilled:
                break

    # Map filled slots back to the ordered lineup rows
    pos_cursor = defaultdict(int)
    player_ids = []
    for pos in lineup_slots["pos"]:
        idx = pos_cursor[pos]
        bucket = slots_filled.get(pos, [])
        player_ids.append(bucket[idx] if idx < len(bucket) else None)
        pos_cursor[pos] += 1

    result = lineup_slots.copy()
    result["player_id"] = player_ids

    # Build alternative pools: best non-starter per position (mins_pos already sorted)
    alt_pool = defaultdict(list)
    for _, row in mins_pos.iterrows():
        pid = row["player_id"]
        if pid not in assigned and pid not in unavailable_set:
            alt_pool[row["pos"]].append(pid)

    alt_cursor = defaultdict(int)
    alt_ids = []
    for pos in lineup_slots["pos"]:
        pool = alt_pool.get(pos, [])
        idx = alt_cursor[pos]
        alt_ids.append(pool[idx] if idx < len(pool) else None)
        alt_cursor[pos] += 1

    result["alt_player_id"] = alt_ids

    jersey_map = (
        mins_pos[["player_id", "Jersey Number"]]
        .drop_duplicates("player_id")
    )
    result = result.merge(jersey_map, on="player_id", how="left")

    # Fill jersey numbers for fallback players absent from the selected-match data
    _jn_fb = result["player_id"].map(
        lambda pid: float(JERSEY_NUM[pid]) if pid in JERSEY_NUM else float("nan")
    )
    result["Jersey Number"] = result["Jersey Number"].fillna(_jn_fb)

    # Sort by canonical position order
    pos_rank = {p: i for i, p in enumerate(POS_ORDER)}
    result["_rank"] = result["pos"].map(lambda p: pos_rank.get(p, 99))
    result = (
        result.sort_values("_rank")
        .drop(columns=["_rank"])
        .reset_index(drop=True)
    )

    return result[["pos", "Jersey Number", "player_id", "alt_player_id"]]


def get_squad_sections(code, all_players):
    """
    Split all_players into display sections for the minutes table.

    Returns: list of (label, DataFrame) tuples, in display order.
    Special sections (long-term inactive, mid-season departures) appended last.
    """
    team_dep     = depart_raw[depart_raw["team_code"] == code]
    departed_ids = set(team_dep[team_dep["midseason_departure"] == 1]["player_id"])
    inactive_ids = set(team_dep[team_dep["longterm_inactive"]   == 1]["player_id"])
    special_ids  = departed_ids | inactive_ids

    active = all_players[~all_players["player_id"].isin(special_ids)].copy()

    sections = []
    for label, pos_set in SQUAD_SECTIONS:
        df = (
            active[active["Position"].isin(pos_set)]
            .sort_values(["starts", "Mins"], ascending=[False, False])
        )
        if not df.empty:
            sections.append((label, df))

    if inactive_ids:
        df = _special_section_df(inactive_ids, all_players, code)
        if not df.empty:
            sections.append(("Long-term Inactive", df))

    if departed_ids:
        df = _special_section_df(departed_ids, all_players, code)
        if not df.empty:
            sections.append(("Mid-season Departures", df))

    return sections


def _special_section_df(player_ids, all_players, code):
    """Build a row-set for players who may have zero match data."""
    known = (
        all_players[all_players["player_id"].isin(player_ids)]
        .copy()
        .sort_values(["starts", "Mins"], ascending=[False, False])
    )
    unknown_ids = player_ids - set(known["player_id"])
    if unknown_ids:
        lookup = players_raw[players_raw["player_id"].isin(unknown_ids)].copy()
        lookup = lookup[lookup["team_code"] == code] if code in lookup["team_code"].values else lookup
        lookup = lookup[["player_id", "Jersey Number"]].copy()
        lookup["team_code"]          = code
        lookup["starts"]             = 0
        lookup["subs"]               = 0
        lookup["Games Played"]       = "0(0)"
        lookup["Position"]           = "-"
        lookup["Secondary Position"] = None
        lookup["Mins"]               = 0
        known = pd.concat([known, lookup], ignore_index=True)
    return known
