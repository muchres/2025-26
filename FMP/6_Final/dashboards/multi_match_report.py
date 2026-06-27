"""
Pre-match scouting report — "Multiple Matches Analysis" tab.

Aggregates event data across up to 6 selected matches and renders a full
scouting report: lineup prediction, build-up, chance creation, shots,
transitions, defensive, set pieces, key players, and strengths/weaknesses.

All coordinates are in each team's own reference frame (x=0 own goal,
x=100 opponent's goal), so no home/away flip is needed when filtering
to one team's events.
"""

import math
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html, dash_table

from utils.constants import (
    BG_COLOUR, PRIMARY_COL, SECONDARY_COL, TERTIARY_COL, BORDER, CARD_BG, TEXT_MUTED,
    TEXT_MAIN, LALIGA_RED,
    ROW_H, ATT_X0, ATT_MIDX, LW_SPLIT, RW_SPLIT, KEY_ZONES, ARROW_COLORS,
    GOAL_X, GOAL_Y, MAX_DIST,
    LALIGA_DATA_DIR,
    POS_ORDER, formation_coords, formation_position_mapping,
)
from utils.data_loader import TEAM_DATA, MATCHES, team_name
from utils.lineup_data import (
    get_match_options, prepare_team_data, get_default_formation, get_predicted_lineup,
    get_squad_sections, fmt_formation, DISP_NAME, POS_ORDER as LINEUP_POS_ORDER,
)
from pages.lineup import _build_lineup_pitch
from dashboards.pitch import (
    make_pitch4, make_pitch_v, make_pitch_zones_v2,
    make_pitch_simple, make_pitch_30zones, get_zone,
    make_pitch_v_top, make_pitch_v_top_zones, make_pitch_v_bottom,
)
from dashboards.carry_progressive import build_carry_df
from dashboards.match_analysis import (
    make_section_label, make_table, make_graph as _make_graph_raw,
    TABLE_STYLE_HEADER, TABLE_STYLE_CELL, TABLE_STYLE_DATA,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE   = os.path.dirname(os.path.abspath(__file__))
_APP    = os.path.dirname(_HERE)
_DATA   = os.path.join(os.path.dirname(_APP), "2_Data")
_STATS  = os.path.join(_DATA, "laliga_stats")

_TEAM_STATS_MATCH  = os.path.join(_STATS, "team_stats_per_match.csv")
_TEAM_STATS_SEASON = os.path.join(_STATS, "team_stats_season.csv")
_PLAYER_STATS_MATCH = os.path.join(_STATS, "player_stats_per_match.csv")
_PLAYER_LIST        = os.path.join(_DATA, "laliga_player_list.csv")

# ── Pitch geometry constants (vertical-pitch helpers) ────────────────────────
_PW_V, _PL_V, _PH_V, _CX_V = 68.0, 105.0, 52.5, 34.0
_GK_SHORT_THR, _GK_LONG_THR = 25, 40
_COL_EDGES_HM = [0, 17.5, 35, 52.5, 70, 87.5, 105]
_COL_EDGES_DEF = [0, 17.5, 35, 52.5, 70, 87.5, 105]
_ROW_H_HM  = 68 / 5
_GK_GREY   = "#cccccc"

# Cross-zone definitions (vertical pitch coords)
_CZONES = {
    "Left Wide":  dict(x0=0,               x1=_PW_V / 6,        y0=_PH_V, y1=_PL_V),
    "Left HS":    dict(x0=_PW_V / 6,       x1=_PW_V / 3,        y0=70,    y1=_PL_V),
    "Right HS":   dict(x0=_PW_V - _PW_V/3, x1=_PW_V - _PW_V/6, y0=70,    y1=_PL_V),
    "Right Wide": dict(x0=_PW_V - _PW_V/6, x1=_PW_V,            y0=_PH_V, y1=_PL_V),
}
_WIDE_X0_V = _CX_V - 20.16
_WIDE_X1_V = _CX_V + 20.16
_HS_X0_V   = _PW_V / 3
_HS_X1_V   = _PW_V - _PW_V / 3
_BOX_Y0_V, _BOX_Y1_V = 88.5, 105.0
_BOX_X0_SP = _CX_V - 20.16
_BOX_X1_SP = _CX_V + 20.16
_BOX_Y_SP  = 88.5

_HS_ZONES  = {"Left HS", "Right HS"}
_WD_ZONES  = {"Left Wide", "Right Wide"}
_C_FAIL    = "rgba(160,160,160,0.80)"
_C_SUC_HS  = "rgba(0,188,212,0.90)"
_C_SUC_WD  = "rgba(210,105,30,0.90)"

_SP_TYPE_CFG = {
    "Free Kick": dict(col="Free kick taken", color="#27AE60"),
    "Corner":    dict(col="Corner taken",    color="#E74C3C"),
    "Throw In":  dict(col="Throw In",        color="#2980B9"),
}
_SP_SHORT_M = 32
_SP_CORNER_SHORT = 25

# Shot on-target y/z thresholds
_GMY_LO = (34 - 7.32 / 2) / 68 * 100
_GMY_HI = (34 + 7.32 / 2) / 68 * 100


# ══════════════════════════════════════════════════════════════════════════════
# Layout config — adjust here
# ══════════════════════════════════════════════════════════════════════════════

# Row heights (px)
MM_ROW2_H = 240
MM_ROW3_H = 450
MM_ROW4_H = 300
MM_ROW5_H = 240
MM_ROW6_H = 330
MM_ROW7_H = 250
MM_ROW8_H = 250

# Shared component heights (px)
MM_BENCH_H     = 50    # every benchmark strip (title + 3 bars)
MM_TABLE_ROW_H = 16    # every sortable-table data row

# Graph heights inside boxes (px)
MM_R2_PITCH_H = 220
MM_R3_GK_H    = 350
MM_R3_PROG_H  = 350
MM_R3_TBL_H   = 196
MM_R4_RECV_H  = 282
MM_R4_CROSS_H = 224
MM_R4_TBL_H   = 278
MM_R4_TBL2_H  = 122    # each of two tables stacked in Row 4 box 3
MM_R5_SHOT_H  = 168
MM_R5_GOAL_H  = 98
MM_R5_STATS_H = 70
MM_R5_TBL_H   = 218
MM_R6_FB_H    = 248
MM_R6_DEFHM_H = 248
MM_R6_TBL_H   = 318
MM_R7_GRAPH_H = 226
MM_R7_TBL_H   = 100    # each of two stacked tables in Row 7 box 3
MM_R8_RADAR_H = 228

# Season-stat column candidates (first existing column wins).  EDIT these to
# match the column names produced by laliga_stats.py.  Metrics whose column
# isn't found render the "Avg" (selected) bar only.
_SEASON_COLS = {
    "gk_short":           ["gk_short", "gk_pass_short", "gk_short_passes", "short_gk_passes"],
    "gk_long":            ["gk_long", "gk_pass_long", "gk_long_passes", "long_gk_passes"],
    "progressive_passes":           ["progressive_passes", "prog_passes"],
    "progressive_passes_opp_half":  ["progressive_passes_opp_half"],
    "crosses_wide":       ["crosses_wide", "wide_crosses", "open_play_crosses_wide"],
    "crosses_hs":         ["crosses_hs", "crosses_half_space", "half_space_crosses", "hs_crosses"],
    "shots":              ["shots", "shots_total"],
    "shots_on_target":    ["shots_on_target", "sot"],
    "fast_break_seq":     ["fast_break_seq", "fast_breaks", "fast_break_sequences"],
    "ball_recoveries":    ["ball_recoveries", "ball_recovery", "recoveries"],
    "ppda":               ["ppda"],
    "def_actions":        ["def_actions", "defensive_actions"],
}

# Metrics that are already per-match ratios (don't divide by matches).
_SEASON_RATIO = {"ppda"}


def _mg(fig, height):
    """make_graph wrapper: force every graph's plot and paper background to BG_COLOUR."""
    try:
        fig.update_layout(plot_bgcolor=BG_COLOUR, paper_bgcolor=BG_COLOUR)
    except Exception:
        pass
    return _make_graph_raw(fig, height)


# ══════════════════════════════════════════════════════════════════════════════
# Data helpers
# ══════════════════════════════════════════════════════════════════════════════

def _load_event_csvs(match_ids):
    """Load and concatenate LaLiga event CSVs for the given match IDs."""
    dfs = []
    files = os.listdir(LALIGA_DATA_DIR)
    for mid in (match_ids or []):
        for fname in files:
            if fname.endswith(f"_{mid}.csv"):
                dfs.append(pd.read_csv(os.path.join(LALIGA_DATA_DIR, fname)))
                break
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def _safe_col(df, col, default=float("nan")):
    return df[col] if col in df.columns else default


def _preprocess(df_all, code):
    """
    Filter to the team's own events and enrich with normalised pitch coords,
    progressive flags, and zone labels.

    Returns (pass_df, shot_df, carry_df, def_df, df_raw_team).
    All coords are in the team's own reference frame:
      x=0 = own goal, x=100 = opponent goal, plot_x = x * 105/100.
    """
    if df_all.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty, empty

    _NEEDED = [
        "week", "match_id", "event", "period_id", "time_min", "time_sec",
        "team_code", "team_position", "Team Formation", "Team Player Formation",
        "formation", "position", "Jersey Number", "player_id",
        "x", "y", "outcome", "own goal",
        "Cross", "Through ball",
        "Free kick taken", "Corner taken", "Throw In",
        "Pass End X", "Pass End Y",
        "Penalty", "Six Yard Blocked", "Saved Off Line",
        "Set piece", "From corner", "Free kick",
        "Left footed", "Right footed", "Head", "Other body part",
        "Goal Mouth Y Coordinate", "Goal Mouth Z Coordinate",
        "Blocked X Coordinate", "Blocked Y Coordinate",
        "Def block", "Blocked cross",
        "Keeper Throw", "Goal Kick",
        "Yellow Card", "Second yellow", "Red Card",
        "Leading to attempt", "Leading to goal",
        "Fast break", "Inswinger", "Outswinger",
    ]
    _cols = [c for c in _NEEDED if c in df_all.columns]
    df1 = df_all[_cols].copy()
    for _c in ["Inswinger", "Outswinger", "Fast break"]:
        if _c not in df1.columns:
            df1[_c] = float("nan")

    # Filter to team's own events
    team_df = df1[df1["team_code"] == code].reset_index(drop=True)
    if team_df.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty, empty

    # ── Pass DataFrame ────────────────────────────────────────────────────────
    pass_df = team_df.copy()
    pass_df["plot_x"]     = pass_df["x"]          * 105 / 100
    pass_df["plot_y"]     = pass_df["y"]          * 68  / 100
    pass_df["plot_end_x"] = pass_df["Pass End X"] * 105 / 100
    pass_df["plot_end_y"] = pass_df["Pass End Y"] * 68  / 100

    dx = pass_df["plot_end_x"] - pass_df["plot_x"]
    dy = pass_df["plot_end_y"] - pass_df["plot_y"]
    pass_df["pass_angle"] = (np.degrees(np.arctan2(dy, dx)) + 360) % 360

    a = pass_df["pass_angle"]
    pass_df["pass_type"] = np.select(
        [(a >= 300) | (a <= 60),
         ((a > 60) & (a <= 90)) | ((a >= 270) & (a < 300)),
         ((a > 90) & (a <= 120)) | ((a >= 240) & (a < 270)),
         (a > 120) & (a < 240)],
        ["Forward", "Sideway Forward", "Sideway Backward", "Backward"],
        default="",
    )
    pass_df["pass_type"] = pass_df["pass_type"].replace("", np.nan)

    pass_df["ori_dist_to_goal"] = np.sqrt(
        (pass_df["x"] - GOAL_X) ** 2 + (pass_df["y"] - GOAL_Y) ** 2
    )
    pass_df["fin_dist_to_goal"] = np.sqrt(
        (pass_df["Pass End X"] - GOAL_X) ** 2 + (pass_df["Pass End Y"] - GOAL_Y) ** 2
    )
    _rp = (pass_df["ori_dist_to_goal"] - pass_df["fin_dist_to_goal"]) / pass_df["ori_dist_to_goal"] * 100
    pass_df["progressive"] = ((pass_df["pass_type"] == "Forward") & (_rp >= 10)).astype(int)
    pass_df["dist_threat"] = (1 - pass_df["ori_dist_to_goal"] / MAX_DIST).round(2)

    # Pass receive
    is_pass_suc = (pass_df["event"] == "Pass") & (pass_df["outcome"] == 1)
    same_team   = pass_df["team_code"] == pass_df["team_code"].shift(-1)
    pass_df["pass_recipient_id"] = np.where(is_pass_suc & same_team, pass_df["player_id"].shift(-1), np.nan)

    # Final-third zone labels
    def _zone(x, y):
        if x >= ATT_X0:
            if ROW_H <= y <= 2 * ROW_H and x <= ATT_MIDX:
                return "Z14"
            if 2 * ROW_H <= y <= LW_SPLIT:
                return "LHS"
            if RW_SPLIT <= y <= ROW_H:
                return "RHS"
        return "n/a"

    f3_mask = (
        (pass_df["Pass End X"] > 200 / 3) &
        (pass_df["event"] == "Pass") &
        (pass_df["outcome"] == 1)
    )
    pass_df["ori_zone"] = np.nan
    pass_df["fin_zone"] = np.nan
    pass_df["to_plot"]  = 0
    if f3_mask.any():
        pass_df.loc[f3_mask, "ori_zone"] = pass_df.loc[f3_mask].apply(
            lambda r: _zone(r["plot_x"], r["plot_y"]), axis=1
        )
        pass_df.loc[f3_mask, "fin_zone"] = pass_df.loc[f3_mask].apply(
            lambda r: _zone(r["plot_end_x"], r["plot_end_y"]), axis=1
        )
        pass_df.loc[f3_mask, "to_plot"] = (
            pass_df.loc[f3_mask, "ori_zone"] != pass_df.loc[f3_mask, "fin_zone"]
        ).astype(int)

    # ── Shot DataFrame ────────────────────────────────────────────────────────
    shot_df = team_df[team_df["event"].isin(["Goal", "Miss", "Saved Shot", "Post"])].copy()
    shot_df["plot_vx"]     = 68  - (shot_df["y"]                        / 100) * 68
    shot_df["plot_vy"]     =        (shot_df["x"]                        / 100) * 105
    shot_df["plot_end_vx"] = 68  - (shot_df["Goal Mouth Y Coordinate"]  / 100) * 68
    shot_df["plot_end_vy"] = 105.0
    shot_df["on_target"] = (
        shot_df["Goal Mouth Y Coordinate"].between(_GMY_LO, _GMY_HI) &
        (shot_df["Goal Mouth Z Coordinate"] <= 38)
    ).fillna(False).astype(int)

    # ── Carry DataFrame ───────────────────────────────────────────────────────
    carry_df = build_carry_df(team_df)

    # Carry final-third zones
    if not carry_df.empty:
        carry_df["ori_zone"] = carry_df.apply(lambda r: _zone(r["plot_x"], r["plot_y"]), axis=1)
        carry_df["fin_zone"] = carry_df.apply(lambda r: _zone(r["plot_end_x"], r["plot_end_y"]), axis=1)
        carry_df["to_plot"]  = (carry_df["ori_zone"] != carry_df["fin_zone"]).astype(int)

    # ── Defensive action DataFrame ────────────────────────────────────────────
    def_df = team_df[team_df["event"].isin([
        "Ball recovery", "Blocked Pass", "Challenge", "Foul", "Interception", "Tackle"
    ])].copy()
    def_df["plot_x"] = def_df["x"] * 105 / 100
    def_df["plot_y"] = def_df["y"] * 68  / 100

    return pass_df, shot_df, carry_df, def_df, team_df


def _load_benchmarks(code, match_ids):
    """Return (team_avgs_dict, league_avgs_dict, player_stats_df)."""
    team_avgs, league_avgs = {}, {}
    ps_df = pd.DataFrame()

    if os.path.exists(_TEAM_STATS_MATCH):
        ts = pd.read_csv(_TEAM_STATS_MATCH)
        team_sub = ts[(ts["team_code"] == code) & (ts["match_id"].isin(match_ids or []))]
        _numeric = ts.select_dtypes(include="number").columns
        team_avgs   = team_sub[_numeric].mean().to_dict() if not team_sub.empty else {}
        league_avgs = ts[_numeric].mean().to_dict()

    if os.path.exists(_PLAYER_STATS_MATCH):
        ps_all = pd.read_csv(_PLAYER_STATS_MATCH)
        ps_df  = ps_all[(ps_all["team_code"] == code) & (ps_all["match_id"].isin(match_ids or []))]

    return team_avgs, league_avgs, ps_df


def _load_season_stats():
    if not os.path.exists(_TEAM_STATS_SEASON):
        return pd.DataFrame()
    df = pd.read_csv(_TEAM_STATS_SEASON)
    # Patch columns missing from the season file but derivable from per-match data.
    # _def_actions_high: season sum so _cat_percentiles can divide by matches.
    # possession_pct:    season mean (den_col=None → used as-is).
    _patch = {"_def_actions_high": "sum", "possession_pct": "mean"}
    missing = [c for c in _patch if c not in df.columns]
    if missing and os.path.exists(_TEAM_STATS_MATCH):
        pm = pd.read_csv(_TEAM_STATS_MATCH)
        for col in missing:
            if col in pm.columns:
                agg = pm.groupby("team_code")[col].agg(_patch[col]).reset_index()
                df = df.merge(agg, on="team_code", how="left")
    return df


def _load_player_names():
    if os.path.exists(_PLAYER_LIST):
        pl = pd.read_csv(_PLAYER_LIST, encoding="utf-8-sig")
        return pl.drop_duplicates("player_id").set_index("player_id")["Display Name"].to_dict()
    return {}


# ── Shared formatting / lookup helpers ────────────────────────────────────────

def _abbrev_name(name):
    """'Pablo Fornals' → 'P. Fornals' (idempotent for already-short names)."""
    if name is None or name != name:
        return "?"
    parts = str(name).split()
    if len(parts) <= 1:
        return str(name)
    first = parts[0].rstrip(".")
    return f"{first[0]}. {parts[-1]}"


def _player_label(pid, name_lkp, jersey):
    """Leader-table player label, e.g. '#8 P. Fornals'."""
    nm = _abbrev_name(name_lkp.get(pid, str(pid)))
    j  = jersey.get(pid) if jersey else None
    jstr = f"#{int(j)} " if (j is not None and j == j) else ""
    return f"{jstr}{nm}"


def _opp_lookup(df_all, code):
    """match_id → opponent team_code for the selected matches."""
    out = {}
    if df_all.empty or "match_id" not in df_all.columns:
        return out
    for mid, g in df_all.groupby("match_id"):
        opps = [c for c in g["team_code"].dropna().unique() if c != code]
        out[mid] = opps[0] if opps else "?"
    return out


def get_opponent_options(code):
    """Dropdown options of the 19 other teams (sorted by display name)."""
    opts = [{"label": team_name(c), "value": c}
            for c in TEAM_DATA.keys() if c != code]
    return sorted(opts, key=lambda o: o["label"])


def get_preset_matches(code, opp_code):
    """The 5 matches `code` played immediately before its latest meeting with opp.

    Returns a list of match_ids (chronological). Empty if no meeting exists.
    """
    team_ms = sorted([m for m in MATCHES if code in (m["home"], m["away"])],
                     key=lambda m: m["date_raw"])
    vs = [m for m in team_ms if opp_code in (m["home"], m["away"])]
    if not vs:
        return []
    latest = max(vs, key=lambda m: m["date_raw"])
    before = [m for m in team_ms if m["date_raw"] < latest["date_raw"]]
    return [m["id"] for m in before[-5:]]


# ══════════════════════════════════════════════════════════════════════════════
# Low-level pitch helpers (adapted from match_analysis.py inner functions)
# ══════════════════════════════════════════════════════════════════════════════

def _tv(x100, y100):
    """Opta 0-100 coords → vertical pitch (vx=pitch-width, vy=pitch-length)."""
    return 68 - (y100 / 100 * 68), x100 / 100 * 105


def _darken(hex_color, factor=0.6):
    h = hex_color.lstrip("#")
    r, g, b = (int(int(h[i:i+2], 16) * factor) for i in (0, 2, 4))
    return f"#{r:02x}{g:02x}{b:02x}"


def _bright(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b > 180


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _add_carry_traces(fig, df_c, color, opacity=1,
                      xcol="plot_x", ycol="plot_y",
                      xend="plot_end_x", yend="plot_end_y"):
    if df_c.empty:
        return
    xs, ys = [], []
    for _, r in df_c.iterrows():
        x0, y0, x1, y1 = r[xcol], r[ycol], r[xend], r[yend]
        xs += [x0, x1, None]; ys += [y0, y1, None]
        fig.add_annotation(
            x=x1, y=y1, ax=x0, ay=y0,
            xref="x", yref="y", axref="x", ayref="y",
            text="", showarrow=True, arrowhead=2, arrowsize=0.9,
            arrowwidth=1.5, arrowcolor=color, opacity=opacity,
        )
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines",
        line=dict(color=color, width=1.5, dash="dot"),
        opacity=opacity, showlegend=False, hoverinfo="skip",
    ))


# ══════════════════════════════════════════════════════════════════════════════
# Figure functions
# ══════════════════════════════════════════════════════════════════════════════

def _gk_pass_df(pass_df):
    """Shared GK-pass extraction used by the figure and the benchmark bars."""
    if pass_df.empty:
        return pd.DataFrame()
    _df = pass_df[
        (pass_df["event"] == "Pass") &
        (pass_df["position"] == "GK") &
        (pass_df["plot_x"] <= 16.5) &
        (pass_df["plot_y"] >= 13.84) &
        (pass_df["plot_y"] <= 54.16) &
        pass_df["plot_end_x"].notna() &
        pass_df["plot_end_y"].notna()
    ].copy()
    if _df.empty:
        return _df
    _df["vx0"] = 68 - _df["plot_y"]
    _df["vy0"] = _df["plot_x"]
    _df["vx1"] = 68 - _df["plot_end_y"]
    _df["vy1"] = _df["plot_end_x"]
    _df["dist"] = np.sqrt((_df["vx1"] - _df["vx0"])**2 + (_df["vy1"] - _df["vy0"])**2)
    _df["dist_group"] = pd.cut(
        _df["dist"],
        bins=[0, _GK_SHORT_THR, _GK_LONG_THR, float("inf")],
        labels=["short", "medium", "long"], right=False,
    )
    return _df


def _fig_gk(pass_df, color, arrows=True):
    """GK distribution — vertical pitch with heatmap and short/medium/long stats.

    arrows=False keeps only the destination heatmap (used in the multi-match report).
    """
    if pass_df.empty:
        return make_pitch_v()

    _df = _gk_pass_df(pass_df)

    _col = _darken(color) if _bright(color) else color
    fig = make_pitch_v()

    # Heatmap
    if not _df.empty:
        _NX, _NY = 50, 80
        _xg = np.linspace(0, 68, _NX + 1); _yg = np.linspace(0, 105, _NY + 1)
        _h, _, _ = np.histogram2d(_df["vx1"].values, _df["vy1"].values, bins=[_xg, _yg])
        _sigma = 4; _r = int(round(3 * _sigma))
        _k = np.exp(-np.arange(-_r, _r+1)**2 / (2*_sigma**2)); _k /= _k.sum()
        _h = np.apply_along_axis(lambda v: np.convolve(v, _k, mode="same"), 0, _h.astype(float))
        _h = np.apply_along_axis(lambda v: np.convolve(v, _k, mode="same"), 1, _h)
        fig.add_trace(go.Heatmap(
            x=(_xg[:-1]+_xg[1:])/2, y=(_yg[:-1]+_yg[1:])/2, z=_h.T,
            colorscale=[[0,"white"],[0.3,"yellow"],[1,"red"]],
            opacity=0.3, showscale=False, zsmooth="best", hoverinfo="skip",
        ))

    if arrows and not _df.empty:
        for _, r in _df[_df["outcome"] != 1].iterrows():
            fig.add_annotation(x=r["vx1"], y=r["vy1"], ax=r["vx0"], ay=r["vy0"],
                               xref="x", yref="y", axref="x", ayref="y",
                               text="", showarrow=True, arrowhead=2, arrowsize=1,
                               arrowwidth=1.5, arrowcolor=_GK_GREY)
        for _, r in _df[_df["outcome"] == 1].iterrows():
            fig.add_annotation(x=r["vx1"], y=r["vy1"], ax=r["vx0"], ay=r["vy0"],
                               xref="x", yref="y", axref="x", ayref="y",
                               text="", showarrow=True, arrowhead=2, arrowsize=1,
                               arrowwidth=1.5, arrowcolor=_col, opacity=0.7)

    _tot = max(len(_df), 1)
    for g, label, xpos in [("short","Short",11),("medium","Medium",34),("long","Long",57)]:
        _sub = _df[_df["dist_group"] == g]
        _suc = int((_sub["outcome"] == 1).sum())
        fig.add_annotation(
            text=f"<b>{label}</b><br>{_suc}/{len(_sub)}<br>{round(len(_sub)/_tot*100)}%",
            x=xpos, y=88, xref="x", yref="y",
            showarrow=False, font=dict(size=11, color=SECONDARY_COL),
            xanchor="center", yanchor="bottom", align="center",
        )
    fig.add_annotation(text="Attacking Direction →", x=-3, y=52.5,
                       xref="x", yref="y", showarrow=False,
                       font=dict(size=11, color="#222222", family="Arial"),
                       textangle=-90, xanchor="center", yanchor="middle")
    fig.update_layout(
        plot_bgcolor='white', paper_bgcolor='white', showlegend=False,
        xaxis=dict(range=[-5,70], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[-1,106], showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def _fig_prog_passes(pass_df, carry_df, color):
    """Progressive passes & carries — horizontal pitch."""
    if pass_df.empty:
        return make_pitch4()

    _col  = _darken(color) if _bright(color) else color
    prog  = pass_df[
        (pass_df["progressive"] == 1) &
        (pass_df["Pass End X"] > 50) &
        (pass_df["event"] == "Pass") &
        (pass_df["outcome"] == 1)
    ].copy()
    prog["zone"] = np.select(
        [prog["plot_y"] < ROW_H,
         (prog["plot_y"] >= ROW_H) & (prog["plot_y"] <= ROW_H*2),
         prog["plot_y"] > ROW_H*2],
        ["Right","Center","Left"], default="Center",
    )
    zone_stats = (prog.groupby("zone", sort=False).size()
                  .reset_index(name="count")
                  .set_index("zone").reindex(["Right","Center","Left"]).reset_index())
    zone_stats["count"] = zone_stats["count"].fillna(0).astype(int)

    prog_carry = pd.DataFrame()
    if not carry_df.empty:
        prog_carry = carry_df[(carry_df["progressive"] == 1) & (carry_df["plot_end_x"] > 52.5)].copy()
        if not prog_carry.empty:
            prog_carry["zone"] = np.select(
                [prog_carry["plot_y"] < ROW_H,
                 (prog_carry["plot_y"] >= ROW_H) & (prog_carry["plot_y"] <= ROW_H*2),
                 prog_carry["plot_y"] > ROW_H*2],
                ["Right","Center","Left"], default="Center",
            )
    carry_zone = prog_carry.groupby("zone").size().to_dict() if not prog_carry.empty else {}

    z_centres = {"Right": ROW_H*0.5, "Center": ROW_H*1.5, "Left": ROW_H*2.5}
    z_colors  = {"Right": "#27AE60", "Center": "#2980B9",  "Left": "#C0392B"}

    fig = make_pitch4()
    for _, r in prog.iterrows():
        fig.add_annotation(
            x=r["plot_end_x"], y=r["plot_end_y"], ax=r["plot_x"], ay=r["plot_y"],
            xref="x", yref="y", axref="x", ayref="y",
            text="", showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
            arrowcolor=z_colors.get(r["zone"], _col), opacity=0.5,
        )
    _add_carry_traces(fig, prog_carry, "black")
    for _, zr in zone_stats.iterrows():
        z = zr["zone"]
        fig.add_annotation(
            text=f"<b>{z}:</b><br>P: {int(zr['count'])}<br>C: {carry_zone.get(z, 0)}",
            x=107, y=z_centres[z], xref="x", yref="y", showarrow=False,
            font=dict(size=11, color=z_colors[z]), align="left", xanchor="left",
        )
    fig.add_annotation(text="— Passes  -- Carries     Attacking Direction →",
                       x=52.5, xref="x", y=-5, yref="y",
                       showarrow=False, font=dict(size=12, color="#222222", family="Arial"))
    fig.update_layout(xaxis=dict(range=[-5,140]), margin=dict(l=0,r=0,t=0,b=0))
    return fig


def _fig_z14(pass_df, carry_df, color):
    """Final-third entries (Z14 & half-spaces) — horizontal pitch."""
    if pass_df.empty:
        return make_pitch_zones_v2()

    ent = pass_df[
        (pass_df["to_plot"] == 1) &
        (pass_df["fin_zone"].isin(KEY_ZONES))
    ].copy()
    zone_stats = (ent.groupby("fin_zone", sort=False).size()
                  .reset_index(name="count")
                  .set_index("fin_zone").reindex(KEY_ZONES, fill_value=0).reset_index())

    carry_ent = pd.DataFrame()
    if not carry_df.empty:
        carry_ent = carry_df[carry_df["fin_zone"].isin(KEY_ZONES)].copy()
    carry_zone = carry_ent.groupby("fin_zone").size().to_dict() if not carry_ent.empty else {}

    zone_cfg = {
        "Z14": {"y": 1.5*ROW_H,                  "label": "Zone 14",          "color": "#27AE60"},
        "LHS": {"y": (2*ROW_H + LW_SPLIT)/2,     "label": "Left Half Space",  "color": "#B8860B"},
        "RHS": {"y": (RW_SPLIT + ROW_H)/2,        "label": "Right Half Space", "color": "#B8860B"},
    }

    fig = make_pitch_zones_v2()
    _anns = []
    for a in fig.layout.annotations:
        d = a.to_plotly_json()
        if d.get("text") == "Attacking Direction →":
            d["text"] = "— Passes  -- Carries     Attacking Direction →"
        _anns.append(d)
    fig.update_layout(annotations=_anns)

    for _, r in ent.iterrows():
        fig.add_annotation(
            x=r["plot_end_x"], y=r["plot_end_y"], ax=r["plot_x"], ay=r["plot_y"],
            xref="x", yref="y", axref="x", ayref="y",
            text="", showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
            arrowcolor=ARROW_COLORS[r["fin_zone"]], opacity=0.5,
        )
    _add_carry_traces(fig, carry_ent, "black")
    for _, zr in zone_stats.iterrows():
        z = zr["fin_zone"]
        cfg = zone_cfg[z]
        fig.add_annotation(
            text=f"<b>{cfg['label']}:</b><br>P: {int(zr['count'])}<br>C: {carry_zone.get(z,0)}",
            x=1, y=cfg["y"], xref="x", yref="y", showarrow=False,
            font=dict(size=10, color=cfg["color"]), align="left", xanchor="left",
        )
    fig.update_layout(xaxis=dict(range=[-5,110]), margin=dict(l=0,r=0,t=0,b=0))
    return fig


def _cross_df(df_raw_team):
    """Open-play crosses detected by zone (excludes set pieces).

    Uses _CZONES origin zones + destination constraints to match exactly what
    _fig_crosses draws, so the benchmark bars stay consistent with the graphic.
    Returns DataFrame with columns: px, py, ex, ey, zone, outcome.
    """
    sp = df_raw_team[df_raw_team["event"] == "Pass"].copy() if not df_raw_team.empty else pd.DataFrame()
    if sp.empty:
        return pd.DataFrame(columns=["px", "py", "ex", "ey", "zone", "outcome"])

    def _assign_czone(px, py):
        for zn, zd in _CZONES.items():
            if zd["x0"] <= px <= zd["x1"] and zd["y0"] <= py <= zd["y1"]:
                return zn
        return None

    _recs = []
    for _, row in sp.iterrows():
        if not (pd.isna(row.get("Free kick taken")) and
                pd.isna(row.get("Throw In")) and
                pd.isna(row.get("Corner taken"))):
            continue
        _px, _py = _tv(row["x"], row["y"])
        _zone = _assign_czone(_px, _py)
        if _zone is None:
            continue
        _ex, _ey = _tv(row["Pass End X"], row["Pass End Y"])
        if _ey <= _BOX_Y0_V:
            continue
        if _zone == "Left Wide"  and not (_HS_X0_V   <= _ex <= _WIDE_X1_V): continue
        if _zone == "Right Wide" and not (_WIDE_X0_V <= _ex <= _HS_X1_V):  continue
        if _zone in _HS_ZONES   and not (_HS_X0_V   <= _ex <= _HS_X1_V):   continue
        _recs.append(dict(px=_px, py=_py, ex=_ex, ey=_ey, zone=_zone, outcome=int(row["outcome"])))
    return pd.DataFrame(_recs) if _recs else pd.DataFrame(columns=["px", "py", "ex", "ey", "zone", "outcome"])


def _fig_crosses(df_raw_team, color):
    """Open-play crosses — vertical pitch (team always attacking upward)."""
    _df_p = _cross_df(df_raw_team)

    def _row_color(r):
        if r["outcome"] == 0: return _C_FAIL
        return _C_SUC_HS if r["zone"] in _HS_ZONES else _C_SUC_WD

    fig = make_pitch_v_top_zones()
    for _suc in [0, 1]:
        _sub = _df_p[_df_p["outcome"] == _suc]
        for _, r in _sub.iterrows():
            fig.add_annotation(
                x=r["ex"], y=r["ey"], ax=r["px"], ay=r["py"],
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=2, arrowsize=0.8, arrowwidth=1.5,
                arrowcolor=_row_color(r), opacity=0.1,
            )
    for _suc in [0, 1]:
        _sub = _df_p[_df_p["outcome"] == _suc]
        if _sub.empty: continue
        fig.add_trace(go.Scatter(
            x=_sub["px"].tolist(), y=_sub["py"].tolist(), mode="markers",
            marker=dict(size=10, color=_sub.apply(_row_color, axis=1).tolist(),
                        line=dict(color="white", width=1.5)),
            showlegend=False, hoverinfo="skip",
        ))
    n_lhs = len(_df_p[_df_p["zone"] == "Left HS"])
    n_rhs = len(_df_p[_df_p["zone"] == "Right HS"])
    n_lw  = len(_df_p[_df_p["zone"] == "Left Wide"])
    n_rw  = len(_df_p[_df_p["zone"] == "Right Wide"])
    for ann_txt, ann_col, ann_y in [
        (f"<b>Half Spaces:</b><br>L: {n_lhs}    R: {n_rhs}", "#00BCD4", 68.0),
        (f"<b>Wide Areas:</b><br>L: {n_lw}    R: {n_rw}",   "#D2691E", 58.0),
    ]:
        fig.add_annotation(x=34, y=ann_y, xref="x", yref="y", text=ann_txt,
                           showarrow=False, font=dict(size=11, color=ann_col),
                           xanchor="center", yanchor="middle")
    fig.add_annotation(
        xref="x", yref="y", x=34, y=52.2, xanchor="center", yanchor="top",
        text=(f"<span style='color:rgba(160,160,160,0.90); font-size:18px'>●</span> Attempted"
              f"&nbsp;&nbsp;&nbsp;<span style='color:rgba(0,188,212,0.90); font-size:18px'>●</span>"
              f"<span style='color:rgba(210,105,30,0.90); font-size:18px'>●</span> Completed"),
        showarrow=False, font=dict(size=10, color="#222222"),
    )
    fig.update_layout(margin=dict(l=0,r=0,t=3,b=20))
    return fig


def _fig_receive_hm(pass_df, color):
    """Pass receive 30-zone heatmap."""
    if pass_df.empty:
        return make_pitch_30zones()

    recv = pass_df[pass_df["pass_recipient_id"].notna() &
                   pass_df["plot_end_x"].notna() &
                   pass_df["plot_end_y"].notna()].copy()
    recv["zone"] = recv.apply(lambda r: get_zone(r["plot_end_x"], r["plot_end_y"]), axis=1)
    zone_counts  = recv["zone"].value_counts().to_dict()
    total        = len(recv)
    max_cnt      = max(zone_counts.values()) if zone_counts else 1
    r_, g_, b_   = _rgb(_darken(color) if _bright(color) else color)

    fig = make_pitch_30zones()
    fig.layout.annotations = []
    for c in range(6):
        x0, x1 = _COL_EDGES_HM[c], _COL_EDGES_HM[c+1]
        for r in range(5):
            zone  = c*5 + r + 1
            y1    = 68 - _ROW_H_HM * r
            y0    = 68 - _ROW_H_HM * (r+1)
            cnt   = zone_counts.get(zone, 0)
            pct   = 100 * cnt / total if total > 0 else 0
            alpha = 0.08 + 0.72 * (cnt / max_cnt)
            tcol  = "white" if alpha > 0.7 else "black"
            fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                          fillcolor=f"rgba({r_},{g_},{b_},{alpha:.2f})",
                          line=dict(width=0), layer="below")
            fig.add_annotation(text=f"{cnt}<br>{pct:.1f}%",
                               x=(x0+x1)/2, xref="x", y=(y0+y1)/2, yref="y",
                               showarrow=False, font=dict(size=10, color=tcol))
    fig.add_annotation(text="Attacking Direction →", x=52.5, xref="x", y=-5, yref="y",
                       showarrow=False, font=dict(size=12, color="#222222", family="Arial"))
    fig.update_layout(margin=dict(l=0,r=0,t=0,b=0))
    return fig


def _fig_shots(shot_df, color, name_lkp, arrows=True, goal_illustration=True, opp_lkp=None):
    """Shot map — vertical attacking-half pitch (team attacking upward).

    arrows=False            → drop the goal-scoring arrows.
    goal_illustration=False → drop the goal-frame drawing above the pitch
                              (used in the multi-match report, where the goal
                              frame is shown separately in box 2).
    opp_lkp                 → match_id → opponent code, for the goal tooltip.
    """
    opp_lkp = opp_lkp or {}
    _col  = color
    _dark = _darken(color) if _bright(color) else color

    # Y-range: trim the area above the pitch when the goal frame is hidden.
    _yrange = [52, 130] if goal_illustration else [52, 108]

    if shot_df.empty:
        fig = make_pitch_v_top()
        fig.update_layout(yaxis=dict(range=_yrange), margin=dict(l=0,r=0,t=0,b=32))
        return fig

    _mn  = (shot_df["on_target"] == 0) & (shot_df["event"] != "Goal")
    _mt  = (shot_df["on_target"] == 1) & (shot_df["event"] != "Goal")
    _mg  = (shot_df["event"] == "Goal")

    def _hover(row):
        j = int(row["Jersey Number"]) if pd.notna(row.get("Jersey Number")) else "?"
        p = _abbrev_name(name_lkp.get(row["player_id"], "?"))
        m = row["time_min"]
        opp = opp_lkp.get(row.get("match_id"), "?")
        return f"v {opp} {int(m)+1}' #{j} {p}"

    fig = make_pitch_v_top()
    fig.update_shapes(layer="below")

    if not shot_df[_mn].empty:
        fig.add_trace(go.Scatter(
            x=shot_df[_mn]["plot_vx"], y=shot_df[_mn]["plot_vy"], mode="markers",
            marker=dict(size=6, color="#888888", symbol="x"),
            showlegend=False, hoverinfo="skip"))
    if not shot_df[_mt].empty:
        fig.add_trace(go.Scatter(
            x=shot_df[_mt]["plot_vx"], y=shot_df[_mt]["plot_vy"], mode="markers",
            marker=dict(size=7, color="white", symbol="circle",
                        line=dict(color="#888888", width=1)),
            showlegend=False, hoverinfo="skip"))

    # Goals: optional arrows + circles
    if not shot_df[_mg].empty:
        _df_g = shot_df[_mg]
        if arrows:
            for _, r in _df_g.iterrows():
                fig.add_annotation(
                    x=r["plot_end_vx"], y=r["plot_end_vy"], ax=r["plot_vx"], ay=r["plot_vy"],
                    xref="x", yref="y", axref="x", ayref="y",
                    text="", showarrow=True, arrowhead=2, arrowsize=1,
                    arrowwidth=1.5, arrowcolor=_dark,
                )
        _gh = [_hover(r) for _, r in _df_g.iterrows()]
        fig.add_trace(go.Scatter(
            x=_df_g["plot_vx"].tolist(), y=_df_g["plot_vy"].tolist(), mode="markers",
            marker=dict(size=8, color=_col, symbol="circle", line=dict(color="white",width=1.5)),
            showlegend=False, customdata=_gh, hovertemplate="%{customdata}<extra></extra>"))

    if goal_illustration:
        # Goalpost rectangle on pitch
        fig.add_shape(type="rect", x0=34-3.66, y0=105, x1=34+3.66, y1=105.5,
                      line=dict(color="#888888", width=1.5), fillcolor="rgba(0,0,0,0)")
        # Goal frame illustration with shot placement
        _GP_W=30; _GP_H=_GP_W*(2.44/7.32); _GP_X0=34-_GP_W/2; _GP_X1=34+_GP_W/2
        _GP_Y0=112; _GP_Y1=_GP_Y0+_GP_H; _GP_GL=5
        fig.add_shape(type="line", x0=_GP_X0-_GP_GL, y0=_GP_Y0, x1=_GP_X1+_GP_GL, y1=_GP_Y0,
                      line=dict(color="black",width=2))
        fig.add_shape(type="rect", x0=_GP_X0, y0=_GP_Y0, x1=_GP_X1, y1=_GP_Y1,
                      line=dict(color="#AAAAAA",width=1.5), fillcolor="rgba(0,0,0,0)")
        _sx = (_GP_W/2)/3.66; _sz = _GP_H/38
        for mask, sym, c, sz in [(_mn,"x","#888888",5),(_mt,"circle","white",7),(_mg,"circle",_col,8)]:
            _s = shot_df[mask & shot_df["Goal Mouth Z Coordinate"].notna()]
            if _s.empty: continue
            ix = 34 + (_s["plot_end_vx"] - 34) * _sx
            iy = _GP_Y0 + _s["Goal Mouth Z Coordinate"].clip(0,50)*_sz
            kw = dict(size=sz, color=c, symbol=sym)
            if sym == "circle" and c != "white":
                kw["line"] = dict(color="white", width=1.5)
            elif sym == "circle":
                kw["line"] = dict(color="#888888", width=1)
            fig.add_trace(go.Scatter(x=ix.tolist(), y=iy.tolist(), mode="markers",
                                     marker=kw, showlegend=False, hoverinfo="skip"))

    fig.add_annotation(
        xref="x", yref="y", x=70, y=105, xanchor="left", yanchor="top",
        text=(f"<span style='color:{_col}; font-size:18px'>●</span> Goal"
              f"<br><span style='color:#888888; font-size:18px'>○</span> On Target"
              f"<br><span style='color:#888888; font-size:14px'>✕</span> Off Target"),
        showarrow=False, align="left", font=dict(size=10, color="#222222"),
    )
    if not goal_illustration:
        _add_goalpost(fig)            # thin goalpost on the goal line
    fig.update_layout(yaxis=dict(range=_yrange), margin=dict(l=40,r=40,t=0,b=8))
    return fig


def _fig_goalmouth(shot_df, color, name_lkp=None, opp_lkp=None):
    """Standalone goal-frame illustration showing where shots ended up on goal."""
    name_lkp = name_lkp or {}
    opp_lkp  = opp_lkp or {}
    _col = color

    def _hover(row):
        j = int(row["Jersey Number"]) if pd.notna(row.get("Jersey Number")) else "?"
        p = _abbrev_name(name_lkp.get(row["player_id"], "?"))
        m = row["time_min"]
        opp = opp_lkp.get(row.get("match_id"), "?")
        return f"v {opp} {int(m)+1}' #{j} {p}"

    fig = go.Figure()
    _GP_W=30; _GP_H=_GP_W*(2.44/7.32); _GP_X0=34-_GP_W/2; _GP_X1=34+_GP_W/2
    _GP_Y0=0; _GP_Y1=_GP_Y0+_GP_H; _GP_GL=5
    # Ground line + posts/crossbar
    fig.add_shape(type="line", x0=_GP_X0-_GP_GL, y0=_GP_Y0, x1=_GP_X1+_GP_GL, y1=_GP_Y0,
                  line=dict(color="black", width=2))
    fig.add_shape(type="rect", x0=_GP_X0, y0=_GP_Y0, x1=_GP_X1, y1=_GP_Y1,
                  line=dict(color="#AAAAAA", width=1.5), fillcolor="rgba(0,0,0,0)")
    if not shot_df.empty:
        _mn = (shot_df["on_target"] == 0) & (shot_df["event"] != "Goal")
        _mt = (shot_df["on_target"] == 1) & (shot_df["event"] != "Goal")
        _mg = (shot_df["event"] == "Goal")
        _sx = (_GP_W/2)/3.66; _sz = _GP_H/38
        for mask, sym, c, sz, is_goal in [(_mn,"x","#888888",6,False),
                                          (_mt,"circle","white",8,False),
                                          (_mg,"circle",_col,9,True)]:
            _s = shot_df[mask & shot_df["Goal Mouth Z Coordinate"].notna()]
            if _s.empty: continue
            ix = 34 + (_s["plot_end_vx"] - 34) * _sx
            iy = _GP_Y0 + _s["Goal Mouth Z Coordinate"].clip(0,50)*_sz
            kw = dict(size=sz, color=c, symbol=sym)
            if sym == "circle" and c != "white":
                kw["line"] = dict(color="white", width=1.5)
            elif sym == "circle":
                kw["line"] = dict(color="#888888", width=1)
            if is_goal:
                _gh = [_hover(r) for _, r in _s.iterrows()]
                fig.add_trace(go.Scatter(x=ix.tolist(), y=iy.tolist(), mode="markers",
                                         marker=kw, showlegend=False, customdata=_gh,
                                         hovertemplate="%{customdata}<extra></extra>"))
            else:
                fig.add_trace(go.Scatter(x=ix.tolist(), y=iy.tolist(), mode="markers",
                                         marker=kw, showlegend=False, hoverinfo="skip"))
    fig.update_layout(
        plot_bgcolor=BG_COLOUR, paper_bgcolor="white", showlegend=False,
        xaxis=dict(range=[_GP_X0-_GP_GL-2, _GP_X1+_GP_GL+2], showgrid=False,
                   zeroline=False, visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[0, _GP_H+2], showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=2, b=2),
    )
    return fig


def _fig_recovery_fb(df_all, code, color):
    """Recovery coords scatter + fast-break overlays on one horizontal pitch."""
    _col  = color
    _dark = _darken(color) if _bright(color) else color

    fig = make_pitch_simple()
    if df_all.empty:
        return fig

    team_ev = df_all[df_all["team_code"] == code].copy()

    # Ball recovery scatter
    rec = team_ev[team_ev["event"] == "Ball recovery"].copy()
    if not rec.empty:
        rec["px"] = rec["x"] / 100 * 105
        rec["py"] = rec["y"] / 100 * 68
        fig.add_trace(go.Scatter(
            x=rec["px"], y=rec["py"], mode="markers",
            marker=dict(size=5, color="rgba(150,150,150,0.45)", symbol="circle",
                        line=dict(color="rgba(100,100,100,0.3)", width=0.5)),
            showlegend=False, hoverinfo="skip",
        ))

    # Fast-break sequences
    _FB_SHOT  = {"Goal","Miss","Post","Saved Shot"}
    _FB_START = {"Ball recovery","Keeper pick-up","Claim"}
    _FB_KEEP  = _FB_START | {"Pass","Take On"} | _FB_SHOT
    _fb_cols  = [c for c in ["event","period_id","time_min","time_sec","team_code","match_id",
                              "Jersey Number","player_id","x","y","Fast break",
                              "Goal Mouth Y Coordinate"] if c in df_all.columns]
    _df_fb = df_all[_fb_cols].reset_index(drop=True)

    _fb_seqs = []
    for _mid, _mdf in _df_fb.groupby("match_id") if "match_id" in _df_fb.columns else [(None, _df_fb)]:
        _mdf = _mdf.reset_index(drop=True)
        if "Fast break" not in _mdf.columns:
            continue
        _shot_idx = _mdf[_mdf["event"].isin(_FB_SHOT) & (_mdf.get("Fast break","") == "Si")].index.tolist()
        for _sid, _shot_i in enumerate(_shot_idx, 1):
            if _mdf.at[_shot_i,"team_code"] != code:
                continue
            _per = _mdf.at[_shot_i,"period_id"]
            _start = _shot_i
            for _j in range(_shot_i-1, -1, -1):
                if _mdf.at[_j,"period_id"] != _per: break
                if _mdf.at[_j,"event"] in _FB_START and _mdf.at[_j,"team_code"] == code:
                    _start = _j; break
            _chunk = _mdf.loc[_start:_shot_i].copy()
            _chunk = _chunk[_chunk["event"].isin(_FB_KEEP) & (_chunk["team_code"] == code)].copy()
            _chunk.insert(0, "fb_seq_id", f"{_mid}_{_sid}")
            _fb_seqs.append(_chunk)

    df_fb_seq = (pd.concat(_fb_seqs, ignore_index=True) if _fb_seqs else pd.DataFrame())

    if not df_fb_seq.empty:
        for _seqid, _grp in df_fb_seq.groupby("fb_seq_id"):
            _grp = _grp.reset_index(drop=True)
            _n   = len(_grp)
            _px  = [r["x"]/100*105 for _, r in _grp.iterrows()]
            _py  = [r["y"]/100*68  for _, r in _grp.iterrows()]
            # initiation
            fig.add_trace(go.Scatter(x=[_px[0]], y=[_py[0]], mode="markers",
                                     marker=dict(symbol="circle", size=9, color="#CCCCCC",
                                                 line=dict(color="white",width=1)),
                                     showlegend=False, hoverinfo="skip"))
            if _n > 1 and _grp.iloc[1]["event"] not in _FB_SHOT:
                fig.add_annotation(x=_px[1], y=_py[1], ax=_px[0], ay=_py[0],
                                   xref="x", yref="y", axref="x", ayref="y",
                                   arrowhead=2, arrowsize=1.2, arrowwidth=2,
                                   arrowcolor="#CCCCCC", showarrow=True, text="")
            for _i in range(1, _n-1):
                fig.add_shape(type="line", x0=_px[_i], y0=_py[_i], x1=_px[_i+1], y1=_py[_i+1],
                              line=dict(color="#999999",width=1.5,dash="dot"))
            for _i in range(1, _n):
                _row = _grp.iloc[_i]; _ev = _row["event"]
                if _ev not in _FB_SHOT: continue
                _sx, _sy = _px[_i], _py[_i]
                if _ev == "Goal":
                    fig.add_trace(go.Scatter(x=[_sx], y=[_sy], mode="markers",
                                             marker=dict(symbol="circle", size=11, color=_col,
                                                         line=dict(color="white",width=2)),
                                             showlegend=False, hoverinfo="skip"))
                elif _ev == "Saved Shot":
                    fig.add_trace(go.Scatter(x=[_sx], y=[_sy], mode="markers",
                                             marker=dict(symbol="circle-open", size=8, color="#777777",
                                                         line=dict(color="#777777",width=2)),
                                             showlegend=False, hoverinfo="skip"))
                else:
                    fig.add_trace(go.Scatter(x=[_sx], y=[_sy], mode="markers",
                                             marker=dict(symbol="x", size=8, color="#777777"),
                                             showlegend=False, hoverinfo="skip"))

    # Right-side legend / summary — always shown (counts are 0 when no sequences).
    _n_rec = int(len(rec))
    if not df_fb_seq.empty:
        _sr    = df_fb_seq[df_fb_seq["event"].isin(_FB_SHOT)]
        _n_seq = int(df_fb_seq["fb_seq_id"].nunique())
        _n_g   = int((_sr["event"] == "Goal").sum())
        _n_ot  = int(_sr["event"].isin({"Goal", "Saved Shot"}).sum())
    else:
        _n_seq = _n_g = _n_ot = 0
    fig.add_annotation(
        text=(f"<b>Recoveries:</b> {_n_rec}<br><b>Fast Breaks</b><br>"
              f"Seq: {_n_seq}<br>Goals: {_n_g}<br>SoT: {_n_ot}<br><br>"
              f"<span style='color:#AAAAAA;font-size:18px'>●</span> Recovery<br>"
              f"<span style='color:{_col};font-size:18px'>●</span> Goal<br>"
              f"<span style='color:#777777;font-size:18px'>○</span> SoT<br>"
              f"<span style='color:#777777;font-size:14px'>✕</span> Miss"),
        x=107, y=34, xref="x", yref="y",
        showarrow=False, align="left", xanchor="left",
        font=dict(size=10, color="#222222"),
    )
    fig.add_annotation(text="Attacking Direction →", x=52.5, y=-5,
                       xref="x", yref="y", showarrow=False,
                       font=dict(size=12,color="#222222",family="Arial"))
    fig.update_layout(xaxis=dict(range=[-5,150]), margin=dict(l=0,r=0,t=0,b=0))
    return fig


def _fig_def_hm(def_df, color):
    """Defensive actions 30-zone heatmap."""
    if def_df.empty:
        return make_pitch_30zones()

    def_df2 = def_df.copy()
    def_df2["zone"] = def_df2.apply(lambda r: get_zone(r["plot_x"], r["plot_y"]), axis=1)
    r_, g_, b_ = _rgb(_darken(color) if _bright(color) else color)

    zone_stats = {}
    for z in range(1, 31):
        zd = def_df2[def_df2["zone"] == z]
        zone_stats[z] = {"succ": int((zd["outcome"]==1).sum()), "total": len(zd)}
    max_succ = max(s["succ"] for s in zone_stats.values()) if zone_stats else 1

    fig = make_pitch_30zones()
    fig.layout.annotations = []
    for c in range(6):
        x0, x1 = _COL_EDGES_DEF[c], _COL_EDGES_DEF[c+1]
        for r in range(5):
            zone  = c*5 + r + 1
            y1    = 68 - 68/5 * r
            y0    = 68 - 68/5 * (r+1)
            st    = zone_stats[zone]
            alpha = (0.08 + 0.72*(st["succ"]/max_succ)) if max_succ > 0 else 0.08
            tcol  = "white" if alpha > 0.7 else "black"
            fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                          fillcolor=f"rgba({r_},{g_},{b_},{alpha:.2f})",
                          line=dict(width=0), layer="below")
            fig.add_annotation(text=f"{st['total']}",
                               x=(x0+x1)/2, xref="x", y=(y0+y1)/2, yref="y",
                               showarrow=False, font=dict(size=12,color=tcol), align="center")
    for label, cols, lcol in [
        ("Defensive Third",[0,1],"red"),("Midfield Third",[2,3],"#B8860B"),("Attacking Third",[4,5],"green")
    ]:
        xm = (_COL_EDGES_DEF[cols[0]] + _COL_EDGES_DEF[cols[-1]+1]) / 2
        total_t = sum(zone_stats[ci*5+ri+1]["total"] for ci in cols for ri in range(5))
        fig.add_annotation(text=f"<b>{label}</b><br>{total_t}",
                           x=xm, xref="x", y=75, yref="y",
                           showarrow=False, font=dict(size=10.5,color=lcol), align="center")
    fig.add_annotation(text="Attacking Direction →", x=52.5, xref="x", y=-5, yref="y",
                       showarrow=False, font=dict(size=12,color="#222222",family="Arial"))
    fig.update_layout(
        xaxis=dict(range=[-5,110], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[-10,83], showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0,r=0,t=0,b=0),
    )
    return fig


def _fig_def_line(def_df, color):
    """Horizontal pitch with defensive engagement line (mean X of def actions in own half)."""
    fig = make_pitch4()
    if def_df.empty:
        fig.update_layout(margin=dict(l=0,r=0,t=0,b=0))
        return fig

    own_half = def_df[def_df["x"] < 50]
    if own_half.empty:
        fig.update_layout(margin=dict(l=0,r=0,t=0,b=0))
        return fig

    mean_x_100 = own_half["x"].mean()
    mean_plot_x = mean_x_100 * 105 / 100
    mean_m      = round(mean_plot_x, 1)

    _col = _darken(color) if _bright(color) else color
    fig.add_shape(type="line", x0=mean_plot_x, y0=0, x1=mean_plot_x, y1=68,
                  line=dict(color=_col, width=2.5, dash="dash"))
    fig.add_annotation(
        text=f"<b>Def. Line</b><br>{mean_m}m",
        x=mean_plot_x, y=70, xref="x", yref="y",
        showarrow=False, font=dict(size=11, color=_col),
        xanchor="center", yanchor="bottom",
    )
    # scatter of def events in own half
    fig.add_trace(go.Scatter(
        x=(own_half["x"]/100*105).tolist(),
        y=(own_half["y"]/100*68).tolist(),
        mode="markers",
        marker=dict(size=5, color=_col, opacity=0.35,
                    line=dict(color=_col, width=0.5)),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_annotation(text="Attacking Direction →", x=52.5, xref="x", y=-5, yref="y",
                       showarrow=False, font=dict(size=12,color="#222222",family="Arial"))
    fig.update_layout(xaxis=dict(range=[-5,110]), margin=dict(l=0,r=0,t=0,b=0))
    return fig


def _fig_setpiece_atk(df_raw_team, color):
    """Attacking set pieces (corners + free kicks) on vertical pitch."""
    sp = df_raw_team[df_raw_team["event"] == "Pass"].copy() if not df_raw_team.empty else pd.DataFrame()
    return _build_sp_fig(sp, color)


def _fig_setpiece_def(df_all, code, color):
    """Defensive set pieces — opponent's corners/FK against us on vertical pitch."""
    if df_all.empty:
        return _build_sp_fig(pd.DataFrame(), color)
    # Get opponent events in the same matches
    opp_ev = df_all[df_all["team_code"] != code].copy()
    if opp_ev.empty:
        return _build_sp_fig(pd.DataFrame(), color)
    # Flip coords to show from our perspective: (100-x, y) → goal is at vy=0
    opp_sp = opp_ev[opp_ev["event"] == "Pass"].copy()
    opp_sp["x"]          = 100 - opp_sp["x"]
    opp_sp["y"]          = opp_sp["y"]
    opp_sp["Pass End X"] = 100 - opp_sp["Pass End X"]
    return _build_sp_fig(opp_sp, "#888888")


def _build_sp_fig(sp, color):
    """Shared set-piece figure builder."""
    _recs_sp = []
    if not sp.empty:
        for _, row in sp.iterrows():
            for tname, cfg in _SP_TYPE_CFG.items():
                if pd.isna(row.get(cfg["col"])):
                    continue
                _px, _py = _tv(row["x"], row["y"])
                _ex, _ey = _tv(row.get("Pass End X",0), row.get("Pass End Y",0))
                if _py < _PH_V or _ey < _PH_V:
                    break
                _dist = math.sqrt(((row.get("Pass End X",0)-row["x"])*1.05)**2 +
                                  ((row.get("Pass End Y",0)-row["y"])*0.68)**2)
                _scat = ("Short" if _dist < _SP_CORNER_SHORT or _ey < 88.5
                         else ("Front" if _px < _CX_V and _ex < _CX_V
                               else "Far" if _px < _CX_V else "Front")
                         ) if tname == "Corner" else ("Short" if _dist < _SP_SHORT_M else "Long")
                _recs_sp.append(dict(type=tname, color=cfg["color"],
                                     px=_px, py=_py, ex=_ex, ey=_ey,
                                     outcome=int(row["outcome"]), sub_cat=_scat,
                                     inswinger=not pd.isna(row.get("Inswinger")),
                                     outswinger=not pd.isna(row.get("Outswinger"))))
                break
    _df_sp = pd.DataFrame(_recs_sp) if _recs_sp else pd.DataFrame(
        columns=["type","color","px","py","ex","ey","outcome","sub_cat","inswinger","outswinger"])

    fig = make_pitch_v_top()
    for tname, cfg in _SP_TYPE_CFG.items():
        _sub_t = _df_sp[_df_sp["type"] == tname] if not _df_sp.empty else pd.DataFrame()
        if _sub_t.empty: continue
        _tc = cfg["color"]
        for _out, _dash in [(1,"solid"),(0,"dot")]:
            _grp = _sub_t[_sub_t["outcome"] == _out]
            if _grp.empty: continue
            _xs, _ys = [], []
            for _, r in _grp.iterrows():
                _xs += [r["px"], r["ex"], None]; _ys += [r["py"], r["ey"], None]
            fig.add_trace(go.Scatter(x=_xs, y=_ys, mode="lines",
                                     line=dict(color=_tc,width=1.5,dash=_dash),
                                     opacity=0.4, showlegend=False, hoverinfo="skip"))
        _suc = _sub_t[_sub_t["outcome"]==1]
        if not _suc.empty:
            fig.add_trace(go.Scatter(x=_suc["ex"].tolist(), y=_suc["ey"].tolist(), mode="markers",
                                     marker=dict(size=8,color="white",symbol="triangle-up",
                                                 line=dict(color=_tc,width=1.5)),
                                     showlegend=False, hoverinfo="skip"))
        _uns = _sub_t[_sub_t["outcome"]==0]
        if not _uns.empty:
            fig.add_trace(go.Scatter(x=_uns["ex"].tolist(), y=_uns["ey"].tolist(), mode="markers",
                                     marker=dict(size=7,color=_tc,symbol="x"),
                                     showlegend=False, hoverinfo="skip"))

    if not _df_sp.empty:
        _cor = _df_sp[_df_sp["type"] == "Corner"] if "type" in _df_sp.columns else pd.DataFrame()
        _cor_color = _SP_TYPE_CFG["Corner"]["color"]
        for _is_left, _cl in [(True,"Left Corners"),(False,"Right Corners")]:
            _sc = _cor[_cor["px"] < _CX_V] if _is_left else _cor[_cor["px"] >= _CX_V]
            _text = (f"<b>{_cl}</b><br>"
                     f"Short: {int((_sc['sub_cat']=='Short').sum())}<br>"
                     f"Front: {int((_sc['sub_cat']=='Front').sum())}<br>"
                     f"Far: {int((_sc['sub_cat']=='Far').sum())}<br>────<br>"
                     f"Inswing: {int(_sc['inswinger'].sum())}<br>"
                     f"Outswing: {int(_sc['outswinger'].sum())}")
            fig.add_annotation(x=-2 if _is_left else 70, y=105, xref="x", yref="y",
                               text=_text, showarrow=False, font=dict(size=9.5,color=_cor_color),
                               xanchor="right" if _is_left else "left", yanchor="top",
                               align="right" if _is_left else "left")

    fig.add_annotation(
        xref="x", yref="y", x=34, y=52.3, xanchor="center", yanchor="top",
        text=("<span style='color:#666666;font-size:14px'>--✕</span> Attempted"
              "&nbsp;&nbsp;&nbsp;<span style='color:#666666;font-size:14px'>—△</span> Completed"),
        showarrow=False, font=dict(size=10,color="#222222"),
    )
    fig.update_layout(showlegend=False, margin=dict(t=0,l=40,r=40,b=12))
    return fig


_RADAR_CATS = [
    ("Finishing", [
        ("Goals/90",        "goals_for",                                    "matches", False),
        ("Shot Conv %",     "goals_for",                                    "shots",   False),
        ("Shots on Tgt %",  "shots_on_target",                              "shots",   False),
    ]),
    ("Creativity", [
        ("Crosses/90",      ("crosses_wide", "crosses_hs"),                 "matches", False),
        ("Prog OH/90",      "progressive_passes_opp_half",                  "matches", False),
        ("Take-ons/90",     "progressive_take_ons",                         "matches", False),
    ]),
    ("Progression", [
        ("Prog Pass/90",    "progressive_passes",                           "matches", False),
        ("GK Long/90",      "gk_long",                                      "matches", False),
        ("Passes/90",       "passes",                                       "matches", False),
    ]),
    ("Transitions", [
        ("Fast Breaks/90",  "fast_break_seq",                               "matches", False),
        ("FB Goals/90",     "fast_break_goals",                             "matches", False),
        ("FB SoT/90",       "fast_break_shots_on_target",                   "matches", False),
    ]),
    ("Pressing", [
        ("PPDA",            "ppda",                                         None,      True),
        ("High Press/90",   "_def_actions_high",                            "matches", False),
        ("Ball Rec/90",     "ball_recoveries",                              "matches", False),
    ]),
    ("Defending", [
        ("Goals Conc/90",   "goals_against",                                "matches", True),
        ("Clean Sheet %",   "clean_sheet",                                  "matches", False),
        ("Def Actions/90",  "def_actions",                                  "matches", False),
    ]),
    ("Set Pieces", [
        ("SP Shots/90",     ("sp_direct_to_shot", "sp_sequence_to_shot"),   "matches", False),
        ("SP Goals/90",     ("sp_direct_to_goal", "sp_sequence_to_goal"),   "matches", False),
        ("Corners/90",      "corners",                                      "matches", False),
    ]),
    ("Ball Control", [
        ("Possession %",    "possession_pct",                               None,      False),
        ("Pass Comp %",     "passes_completed",                             "passes",  False),
        ("Passes/90",       "passes",                                       "matches", False),
    ]),
]


def _cat_percentiles(code, ts_season_df):
    """Returns list of (cat_label, cat_pct, [(metric_label, pct, raw_val)]).

    cat_pct = mean of sub-metric league percentiles (0–100, higher always = better).
    """
    if ts_season_df is None or ts_season_df.empty:
        return [(cat, 50.0, [(m[0], 50.0, None) for m in metrics])
                for cat, metrics in _RADAR_CATS]

    results = []
    for cat_label, metrics in _RADAR_CATS:
        sub = []
        for m_label, num_col, den_col, invert in metrics:
            try:
                if isinstance(num_col, tuple):
                    if any(c not in ts_season_df.columns for c in num_col):
                        sub.append((m_label, 50.0, None)); continue
                    num = ts_season_df[[*num_col]].sum(axis=1)
                else:
                    if num_col not in ts_season_df.columns:
                        sub.append((m_label, 50.0, None)); continue
                    num = ts_season_df[num_col]

                if den_col is None:
                    ratios = num.copy().astype(float)
                else:
                    if den_col not in ts_season_df.columns:
                        sub.append((m_label, 50.0, None)); continue
                    den = ts_season_df[den_col].replace(0, np.nan)
                    ratios = num / den

                if invert:
                    ratios = 1.0 / ratios.replace(0, np.nan)

                team_rows = ts_season_df[ts_season_df["team_code"] == code]
                if team_rows.empty:
                    sub.append((m_label, 50.0, None)); continue
                raw = float(ratios.loc[team_rows.index[0]])
                if np.isnan(raw):
                    sub.append((m_label, 50.0, None)); continue

                all_vals = ratios.dropna()
                n = len(all_vals)
                if n == 0:
                    pct = 50.0
                else:
                    below = float((all_vals < raw).sum())
                    equal = float((all_vals == raw).sum())
                    pct = (below + 0.5 * equal) / n * 100.0

                sub.append((m_label, round(pct, 1), round(raw, 3)))
            except Exception:
                sub.append((m_label, 50.0, None))

        cat_pct = round(float(np.mean([s[1] for s in sub])), 1)
        results.append((cat_label, cat_pct, sub))

    return results


def _cat_percentiles_match(code, match_ids, ts_season_df):
    """Same structure as _cat_percentiles but values come from the selected matches.

    Each metric is computed from per-match data for those match_ids, then
    percentiled against the same season-wide league distribution so the two
    radars share a common scale.
    """
    fallback = [(cat, 50.0, [(m[0], 50.0, None) for m in metrics])
                for cat, metrics in _RADAR_CATS]
    if not match_ids or not os.path.exists(_TEAM_STATS_MATCH):
        return fallback

    pm  = pd.read_csv(_TEAM_STATS_MATCH)
    sel = pm[(pm["team_code"] == code) & (pm["match_id"].isin(match_ids))]
    if sel.empty:
        return fallback

    n_sel = len(sel)
    results = []
    for cat_label, metrics in _RADAR_CATS:
        sub = []
        for m_label, num_col, den_col, invert in metrics:
            try:
                # ── value for selected matches ────────────────────────────────
                if isinstance(num_col, tuple):
                    if any(c not in sel.columns for c in num_col):
                        sub.append((m_label, 50.0, None)); continue
                    num_series = sel[[*num_col]].sum(axis=1)
                else:
                    if num_col not in sel.columns:
                        sub.append((m_label, 50.0, None)); continue
                    num_series = sel[num_col]

                if den_col is None:
                    raw = float(num_series.mean())
                elif den_col == "matches":
                    raw = float(num_series.sum()) / n_sel
                else:
                    if den_col not in sel.columns:
                        sub.append((m_label, 50.0, None)); continue
                    den_sum = float(sel[den_col].sum())
                    raw = float(num_series.sum()) / den_sum if den_sum > 0 else float("nan")

                if np.isnan(raw):
                    sub.append((m_label, 50.0, None)); continue

                # ── percentile against season league distribution ──────────────
                if ts_season_df is None or ts_season_df.empty:
                    sub.append((m_label, 50.0, round(raw, 3))); continue

                if isinstance(num_col, tuple):
                    if any(c not in ts_season_df.columns for c in num_col):
                        sub.append((m_label, 50.0, round(raw, 3))); continue
                    league_num = ts_season_df[[*num_col]].sum(axis=1)
                else:
                    if num_col not in ts_season_df.columns:
                        sub.append((m_label, 50.0, round(raw, 3))); continue
                    league_num = ts_season_df[num_col]

                if den_col is None:
                    league_ratios = league_num.copy().astype(float)
                elif den_col == "matches":
                    if "matches" not in ts_season_df.columns:
                        sub.append((m_label, 50.0, round(raw, 3))); continue
                    league_ratios = league_num / ts_season_df["matches"].replace(0, np.nan)
                else:
                    if den_col not in ts_season_df.columns:
                        sub.append((m_label, 50.0, round(raw, 3))); continue
                    league_ratios = league_num / ts_season_df[den_col].replace(0, np.nan)

                raw_cmp = raw
                if invert:
                    league_ratios = 1.0 / league_ratios.replace(0, np.nan)
                    raw_cmp = (1.0 / raw) if raw != 0 else float("nan")

                if np.isnan(raw_cmp):
                    sub.append((m_label, 50.0, round(raw, 3))); continue

                all_vals = league_ratios.dropna()
                n = len(all_vals)
                if n == 0:
                    pct = 50.0
                else:
                    below = float((all_vals < raw_cmp).sum())
                    equal = float((all_vals == raw_cmp).sum())
                    pct = (below + 0.5 * equal) / n * 100.0

                sub.append((m_label, round(pct, 1), round(raw, 3)))
            except Exception:
                sub.append((m_label, 50.0, None))

        cat_pct = round(float(np.mean([s[1] for s in sub])), 1)
        results.append((cat_label, cat_pct, sub))

    return results


def _fig_radar_cat(match_cat_data, season_cat_data, code, color):
    """8-spoke tactical radar: full-season (grey) vs selected matches (team colour)."""
    labels      = [d[0] for d in match_cat_data]
    match_vals  = [d[1] for d in match_cat_data]
    season_vals = [d[1] for d in season_cat_data]

    lbl_closed = labels + [labels[0]]
    m_closed   = match_vals  + [match_vals[0]]
    s_closed   = season_vals + [season_vals[0]]

    r, g, b = _rgb(color)
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=s_closed, theta=lbl_closed,
        fill="toself", fillcolor="rgba(160,160,160,0.15)",
        line=dict(color="#888888", width=1.5),
        name="Season", showlegend=True,
    ))
    fig.add_trace(go.Scatterpolar(
        r=m_closed, theta=lbl_closed,
        fill="toself", fillcolor=f"rgba({r},{g},{b},0.25)",
        line=dict(color=color, width=2),
        name="Selected", showlegend=True,
    ))
    fig.update_layout(
        polar=dict(
            bgcolor=CARD_BG,
            radialaxis=dict(
                visible=True, range=[0, 108],
                tickvals=[25, 50, 75, 100],
                ticktext=["25", "50", "75", "100"],
                tickfont=dict(size=8, color=SECONDARY_COL),
                gridcolor="#B9B2A6", gridwidth=1,
                linecolor="#B9B2A6",
            ),
            angularaxis=dict(
                tickfont=dict(size=10, color=SECONDARY_COL),
                gridcolor="#B9B2A6", gridwidth=1,
                linecolor="#B9B2A6",
            ),
        ),
        showlegend=True,
        legend=dict(x=0.5, y=-0.12, xanchor="center", orientation="h",
                    font=dict(size=10, color=SECONDARY_COL)),
        margin=dict(l=55, r=55, t=34, b=52),
        paper_bgcolor=CARD_BG,
    )
    return fig


def _fig_cat_breakdown(match_cat_data, season_cat_data, color):
    """Clustered horizontal bar chart: season (grey) vs selected matches (team colour)."""
    rev_m = list(reversed(match_cat_data))
    rev_s = list(reversed(season_cat_data))
    labels      = [d[0] for d in rev_m]
    match_vals  = [d[1] for d in rev_m]
    season_vals = [d[1] for d in rev_s]

    def _sub_str(sub):
        return f"{sub[0]}: {sub[1]:.0f}th pct" if sub[2] is not None else f"{sub[0]}: —"

    match_cd  = [[_sub_str(d[2][i]) if i < len(d[2]) else "" for i in range(3)] for d in rev_m]
    season_cd = [[_sub_str(d[2][i]) if i < len(d[2]) else "" for i in range(3)] for d in rev_s]

    r, g, b = _rgb(color)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        orientation="h", name="Season",
        x=season_vals, y=labels,
        marker_color="#9A9A9A",
        text=[f"{v:.0f}" for v in season_vals],
        textposition="inside",
        textfont=dict(size=9, color="white"),
        customdata=season_cd,
        hovertemplate=(
            "<b>%{y}</b> Season: %{x:.1f}th pct<br>"
            "%{customdata[0]}<br>%{customdata[1]}<br>%{customdata[2]}"
            "<extra></extra>"
        ),
    ))
    fig.add_trace(go.Bar(
        orientation="h", name="Selected",
        x=match_vals, y=labels,
        marker_color=[f"rgba({r},{g},{b},{0.35 + 0.55 * v / 100:.2f})" for v in match_vals],
        text=[f"{v:.0f}" for v in match_vals],
        textposition="inside",
        textfont=dict(size=9, color="white"),
        customdata=match_cd,
        hovertemplate=(
            "<b>%{y}</b> Selected: %{x:.1f}th pct<br>"
            "%{customdata[0]}<br>%{customdata[1]}<br>%{customdata[2]}"
            "<extra></extra>"
        ),
    ))
    fig.add_vline(x=50, line=dict(color="#AAAAAA", width=1.2, dash="dot"))
    fig.update_layout(
        barmode="group",
        xaxis=dict(range=[0, 100], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False,
                   tickfont=dict(size=10, color=SECONDARY_COL)),
        margin=dict(l=5, r=8, t=4, b=20),
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        showlegend=True,
        legend=dict(x=0.5, y=-0.05, xanchor="center", orientation="h",
                    font=dict(size=9, color=SECONDARY_COL)),
        bargap=0.15,
        bargroupgap=0.05,
    )
    return fig



# ══════════════════════════════════════════════════════════════════════════════
# Lane / zone helpers
# ══════════════════════════════════════════════════════════════════════════════

def _lcr(plot_y):
    """Classify a horizontal-pitch y-coord (0–68) into Left / Center / Right lane.

    Matches the lane convention used by _fig_prog_passes:
      y <  ROW_H            → Right
      ROW_H ≤ y ≤ 2·ROW_H   → Center
      y >  2·ROW_H          → Left
    """
    if plot_y < ROW_H:
        return "R"
    if plot_y <= ROW_H * 2:
        return "C"
    return "L"


def _wide_hs(plot_y):
    """Classify a horizontal-pitch y-coord into Wide ('W') / Half-space ('HS') / None."""
    if plot_y < 68 / 6 or plot_y > 68 * 5 / 6:
        return "W"
    if (68 / 6 <= plot_y <= 68 / 3) or (68 * 2 / 3 <= plot_y <= 68 * 5 / 6):
        return "HS"
    return None


def _wide_hs_lr(plot_y):
    """Wide / half-space split by side → 'W-R','W-L','HS-R','HS-L' / None.

    Right side = low y (matches the L/C/R lane convention), Left = high y.
    """
    if plot_y < 68 / 6:
        return "W-R"
    if plot_y > 68 * 5 / 6:
        return "W-L"
    if 68 / 6 <= plot_y <= 68 / 3:
        return "HS-R"
    if 68 * 2 / 3 <= plot_y <= 68 * 5 / 6:
        return "HS-L"
    return None


def _name_jersey(df_raw_team):
    """player_id → jersey number lookup from the raw team events."""
    jersey = {}
    if not df_raw_team.empty and "Jersey Number" in df_raw_team.columns:
        for pid, g in df_raw_team.groupby("player_id"):
            jv = g["Jersey Number"].dropna()
            jersey[pid] = int(jv.iloc[0]) if not jv.empty else None
    return jersey


def _prog_passes(pass_df):
    """Completed progressive passes whose destination is in the opponent half (Pass End X > 50).

    Single source of truth shared by the heatmap, the leader table and the
    player-to-watch card so all three stay consistent.
    """
    if pass_df.empty:
        return pass_df
    return pass_df[
        (pass_df["progressive"] == 1) &
        (pass_df["Pass End X"] > 50) &
        (pass_df["event"] == "Pass") &
        (pass_df["outcome"] == 1)
    ]


def _add_goalpost(fig, y0=105.0, h=0.5):
    """Draw a thin goalpost rectangle (0.5 high) on the goal line of a vertical-top pitch."""
    fig.add_shape(type="rect", x0=34 - 3.66, y0=y0, x1=34 + 3.66, y1=y0 + h,
                  line=dict(color="#888888", width=1.5), fillcolor="rgba(0,0,0,0)",
                  layer="above")


# ══════════════════════════════════════════════════════════════════════════════
# Benchmark bar charts (replace the old pill rows)
# ══════════════════════════════════════════════════════════════════════════════

_SEASON_C = "#9A9A9A"
_LEAGUE_C = "#CFCABB"


def _bench_fig(bars, fmt="{:.1f}", note=None):
    """Tiny horizontal bar chart for a benchmark strip.

    bars : list of (label, value, color); None values are skipped.
    note : optional string shown on the right (e.g. league rank).
    Light-themed with a small left margin so the bar labels stay readable.
    """
    _txt = SECONDARY_COL
    bars = [(l, v, c) for (l, v, c) in bars if v is not None]
    fig = go.Figure()
    if not bars:
        fig.add_annotation(text="No data", x=0.5, y=0.5, xref="paper", yref="paper",
                           showarrow=False, font=dict(size=9, color=TEXT_MUTED))
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0),
                          paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
                          xaxis=dict(visible=False), yaxis=dict(visible=False))
        return fig

    labels = [b[0] for b in bars][::-1]
    vals   = [b[1] for b in bars][::-1]
    cols   = [b[2] for b in bars][::-1]
    texts  = [fmt.format(v) for v in vals]
    fig.add_trace(go.Bar(
        x=vals, y=labels, orientation="h", marker=dict(color=cols,
                                                       line=dict(color=BORDER, width=0.5)),
        text=texts, textposition="outside", cliponaxis=False,
        textfont=dict(size=9, color=_txt), hoverinfo="skip", showlegend=False,
    ))
    _xmax = max(vals) * 1.40 if max(vals) > 0 else 1
    if note:
        fig.add_annotation(text=note, x=1, y=1.08, xref="paper", yref="paper",
                           showarrow=False, font=dict(size=8.5, color=_txt),
                           xanchor="right", yanchor="bottom")
    fig.update_layout(
        margin=dict(l=58, r=8, t=2, b=2),
        paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
        bargap=0.22,
        xaxis=dict(range=[0, _xmax], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False,
                   tickfont=dict(size=8.5, color=_txt)),
    )
    return fig


def _season_per_match(ts_season_df, code, col, per_match=True):
    """(team_value, league_value, rank, n_teams) from season stats.

    per_match=True  → divide totals by the team's matches (counts).
    per_match=False → use the column value as-is (ratios, e.g. PPDA).
    Returns Nones when the column / team is unavailable.
    """
    if (ts_season_df is None or ts_season_df.empty
            or col not in ts_season_df.columns
            or "team_code" not in ts_season_df.columns):
        return (None, None, None, None)
    if per_match and "matches" not in ts_season_df.columns:
        return (None, None, None, None)
    df = ts_season_df.copy()
    if per_match:
        df = df[df["matches"] > 0].copy()
        if df.empty:
            return (None, None, None, None)
        df["_v"] = df[col] / df["matches"]
        ascending = False
    else:
        df["_v"] = df[col]
        ascending = True   # lower PPDA = better
    df = df[df["_v"].notna()]
    if df.empty:
        return (None, None, None, None)
    league_v = float(df["_v"].mean())
    row = df[df["team_code"] == code]
    if row.empty:
        return (None, league_v, None, len(df))
    team_v = float(row["_v"].iloc[0])
    order = df.sort_values("_v", ascending=ascending).reset_index(drop=True)
    rank = int(order.index[order["team_code"] == code][0]) + 1
    return (team_v, league_v, rank, len(df))


def _season_metric(ts_season_df, code, key):
    """Resolve a logical metric to the first matching column in _SEASON_COLS."""
    per_match = key not in _SEASON_RATIO
    for col in _SEASON_COLS.get(key, [key]):
        res = _season_per_match(ts_season_df, code, col, per_match=per_match)
        if res[0] is not None or res[1] is not None:
            return res
    return (None, None, None, None)


def _rank_note(rank, n_teams):
    return f"Rank {rank}/{n_teams}" if rank and n_teams else None


def _bench(title, code, sel, szn, league, color, fmt="{:.1f}", note=None,
           height=MM_BENCH_H):
    """Uniform benchmark strip: a metric title above 3 bars (Avg / <code> Szn / League)."""
    bars = [("Avg", sel, color),
            (f"{code} Szn", szn, _SEASON_C),
            ("League", league, _LEAGUE_C)]
    return html.Div([
        html.Div(title, style={"fontSize": "0.6rem", "fontWeight": "700",
                               "color": SECONDARY_COL, "textAlign": "center",
                               "lineHeight": "1.05", "flexShrink": "0"}),
        html.Div(_make_graph_raw(_bench_fig(bars, fmt=fmt, note=note), height - 14),
                 style={"flexShrink": "0"}),
    ], style={"display": "flex", "flexDirection": "column",
              "height": f"{height}px", "flexShrink": "0"})


def _bench_2col(left, right, height=MM_BENCH_H):
    """Two uniform benchmark strips side by side.  Each arg is a kwargs dict for _bench."""
    def _cell(d):
        return html.Div(_bench(height=height, **d),
                        style={"flex": "1", "minWidth": "0", "padding": "0 2px"})
    return html.Div([_cell(left), _cell(right)],
                    style={"display": "flex", "height": f"{height}px", "flexShrink": "0"})


# ══════════════════════════════════════════════════════════════════════════════
# New figures
# ══════════════════════════════════════════════════════════════════════════════

def _fig_prog_hm_v(pass_df, color, name_lkp=None):
    """Progressive-pass destination heatmap on a vertical pitch (attacking upward).

    Two dotted lines split the pitch into Left / Center / Right lanes; the per-lane
    progressive-pass counts and lane leader are printed just below the halfway line.
    """
    name_lkp = name_lkp or {}
    fig = make_pitch_v()
    if pass_df.empty:
        return fig

    prog = _prog_passes(pass_df).copy()
    if prog.empty:
        return fig

    # Vertical-pitch coords for destinations (attacking upward)
    prog["vx1"] = 68 - prog["plot_end_y"]
    prog["vy1"] = prog["plot_end_x"]
    prog["lane"] = prog["plot_end_y"].apply(_lcr)  # lane from destination, matching heatmap

    # Destination heatmap
    _col = _darken(color) if _bright(color) else color
    _xg = np.linspace(0, 68, 51); _yg = np.linspace(0, 105, 81)
    _h, _, _ = np.histogram2d(prog["vx1"].values, prog["vy1"].values, bins=[_xg, _yg])
    _sigma = 4; _r = int(round(3 * _sigma))
    _k = np.exp(-np.arange(-_r, _r + 1) ** 2 / (2 * _sigma ** 2)); _k /= _k.sum()
    _h = np.apply_along_axis(lambda v: np.convolve(v, _k, mode="same"), 0, _h.astype(float))
    _h = np.apply_along_axis(lambda v: np.convolve(v, _k, mode="same"), 1, _h)
    fig.add_trace(go.Heatmap(
        x=(_xg[:-1] + _xg[1:]) / 2, y=(_yg[:-1] + _yg[1:]) / 2, z=_h.T,
        colorscale=[[0, "white"], [0.3, "yellow"], [1, "red"]],
        opacity=0.35, showscale=False, zsmooth="best", hoverinfo="skip",
    ))

    # Lane dividers
    for _vx in (68 / 3, 68 * 2 / 3):
        fig.add_shape(type="line", x0=_vx, y0=0, x1=_vx, y1=105,
                      line=dict(color="#888888", width=1.2, dash="dot"), layer="above")

    # Structured summary in the lower (own) half.  vx = 68 - y, so Left (high y)
    # maps to the low-vx side and Right (low y) to the high-vx side.
    counts = prog["lane"].value_counts().to_dict()
    _lanes = [("L", 68 / 6, "Left"), ("C", 34, "Center"), ("R", 68 * 5 / 6, "Right")]

    fig.add_annotation(text="<b>Prog Pass into Opp. Half</b>", x=34, y=50, xref="x", yref="y",
                       showarrow=False, font=dict(size=10, color=SECONDARY_COL),
                       xanchor="center", yanchor="middle")
    for _ln, _vx, _lab in _lanes:
        fig.add_annotation(text=f"{_lab}<br>{counts.get(_ln, 0)}", x=_vx, y=43,
                           xref="x", yref="y", showarrow=False,
                           font=dict(size=9.5, color=SECONDARY_COL),
                           xanchor="center", yanchor="middle")

    fig.add_annotation(text="<b>Prog Pass into Opp. Half Leader</b>", x=34, y=31, xref="x", yref="y",
                       showarrow=False, font=dict(size=10, color=SECONDARY_COL),
                       xanchor="center", yanchor="middle")
    for _ln, _vx, _lab in _lanes:
        _ld = prog[prog["lane"] == _ln]
        if not _ld.empty:
            _top = _ld["player_id"].value_counts()
            _name = _abbrev_name(name_lkp.get(_top.index[0], str(_top.index[0])))
            _cnt = int(_top.iloc[0])
            _txt = f"{_name}<br>{_cnt}"
        else:
            _txt = "–<br>0"
        fig.add_annotation(text=_txt, x=_vx, y=23, xref="x", yref="y", showarrow=False,
                           font=dict(size=9, color=SECONDARY_COL),
                           xanchor="center", yanchor="middle")

    fig.add_annotation(text="Attacking Direction →", x=-3, y=52.5, xref="x", yref="y",
                       showarrow=False, textangle=-90,
                       font=dict(size=11, color="#222222", family="Arial"),
                       xanchor="center", yanchor="middle")
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
    return fig


def _fig_setpiece_box(df_raw_team, color):
    """Attacking set-pieces (corners + free kicks) whose pass ENDS inside the box.

    Top-3 takers (with inswing/outswing split) are listed just inside the pitch
    near the halfway line.
    """
    fig = make_pitch_v_top()
    _add_goalpost(fig)
    sp = df_raw_team[df_raw_team["event"] == "Pass"].copy() if not df_raw_team.empty else pd.DataFrame()
    if sp.empty:
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
        return fig

    recs = []
    for _, row in sp.iterrows():
        for tname, cfg in _SP_TYPE_CFG.items():
            if tname == "Throw In":
                continue
            if pd.isna(row.get(cfg["col"])):
                continue
            _ex, _ey = _tv(row.get("Pass End X", 0), row.get("Pass End Y", 0))
            # destination inside the penalty box
            if not (_BOX_X0_SP <= _ex <= _BOX_X1_SP and _ey >= _BOX_Y_SP):
                break
            _px, _py = _tv(row["x"], row["y"])
            recs.append(dict(
                type=tname, color=cfg["color"], px=_px, py=_py, ex=_ex, ey=_ey,
                outcome=int(row["outcome"]), player_id=row.get("player_id"),
                inswinger=not pd.isna(row.get("Inswinger")),
                outswinger=not pd.isna(row.get("Outswinger")),
            ))
            break

    df_sp = pd.DataFrame(recs)
    if df_sp.empty:
        fig.add_annotation(x=34, y=80, xref="x", yref="y", text="No box set-pieces",
                           showarrow=False, font=dict(size=12, color=TEXT_MUTED), xanchor="center")
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
        return fig

    for tname, cfg in _SP_TYPE_CFG.items():
        sub = df_sp[df_sp["type"] == tname]
        if sub.empty:
            continue
        for out, dash in [(1, "solid"), (0, "dot")]:
            grp = sub[sub["outcome"] == out]
            if grp.empty:
                continue
            xs, ys = [], []
            for _, r in grp.iterrows():
                xs += [r["px"], r["ex"], None]; ys += [r["py"], r["ey"], None]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
                                     line=dict(color=cfg["color"], width=1.5, dash=dash),
                                     opacity=0.45, showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=sub["ex"].tolist(), y=sub["ey"].tolist(), mode="markers",
                                 marker=dict(size=7, color=cfg["color"], symbol="circle",
                                             line=dict(color="white", width=1)),
                                 showlegend=False, hoverinfo="skip"))

    # Top-3 takers near the halfway line
    taker = (df_sp.groupby("player_id")
             .agg(att=("type", "size"), insw=("inswinger", "sum"), outsw=("outswinger", "sum"))
             .sort_values("att", ascending=False).head(3))
    lines = ["<b>Top Takers</b>"]
    for pid, r in taker.iterrows():
        nm = DISP_NAME.get(pid, str(pid))
        lines.append(f"{nm}: {int(r['att'])}  (In {int(r['insw'])}/Out {int(r['outsw'])})")
    fig.add_annotation(x=34, y=55, xref="x", yref="y", text="<br>".join(lines),
                       showarrow=False, font=dict(size=9.5, color=SECONDARY_COL),
                       xanchor="center", yanchor="bottom", align="center")
    fig.update_layout(yaxis=dict(range=[52, 108]), margin=dict(l=0, r=0, t=0, b=4))
    return fig


def _fig_short_corner_seq(df_all, code, color):
    """Attacking sequences that follow SHORT corners (corner pass ending OUTSIDE box).

    Each subsequent team touch is linked by a grey dotted line; shots are drawn as
    arrows toward goal.
    """
    fig = make_pitch_v_top()
    _add_goalpost(fig)
    if df_all.empty:
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
        return fig

    _shot_ev = {"Goal", "Miss", "Post", "Saved Shot"}
    cols = [c for c in ["event", "period_id", "team_code", "match_id", "x", "y",
                        "Pass End X", "Pass End Y", "Corner taken", "outcome",
                        "Goal Mouth Y Coordinate"] if c in df_all.columns]
    d = df_all[cols].reset_index(drop=True)

    n_seq = 0
    for _mid, mdf in (d.groupby("match_id") if "match_id" in d.columns else [(None, d)]):
        mdf = mdf.reset_index(drop=True)
        if "Corner taken" not in mdf.columns:
            continue
        corner_idx = mdf[(mdf["event"] == "Pass") & mdf["Corner taken"].notna()
                         & (mdf["team_code"] == code)].index.tolist()
        for ci in corner_idx:
            row = mdf.loc[ci]
            _ex, _ey = _tv(row.get("Pass End X", 0), row.get("Pass End Y", 0))
            # short corner = pass ends OUTSIDE the box
            if (_BOX_X0_SP <= _ex <= _BOX_X1_SP and _ey >= _BOX_Y_SP):
                continue
            per = mdf.at[ci, "period_id"]
            seq_x, seq_y, shots = [], [], []
            for j in range(ci, len(mdf)):
                if mdf.at[j, "period_id"] != per:
                    break
                if mdf.at[j, "team_code"] != code:
                    break  # possession lost
                vx, vy = _tv(mdf.at[j, "x"], mdf.at[j, "y"])
                seq_x.append(vx); seq_y.append(vy)
                if mdf.at[j, "event"] in _shot_ev:
                    shots.append((vx, vy, mdf.at[j, "event"]))
                    break
            if len(seq_x) < 2:
                continue
            n_seq += 1
            fig.add_trace(go.Scatter(x=seq_x, y=seq_y, mode="lines+markers",
                                     line=dict(color="#999999", width=1.4, dash="dot"),
                                     marker=dict(size=4, color="#bbbbbb"),
                                     showlegend=False, hoverinfo="skip"))
            for vx, vy, ev in shots:
                _c = color if ev == "Goal" else "#777777"
                fig.add_annotation(x=34, y=105, ax=vx, ay=vy, xref="x", yref="y",
                                   axref="x", ayref="y", showarrow=True, arrowhead=2,
                                   arrowsize=1, arrowwidth=2, arrowcolor=_c)

    if n_seq == 0:
        fig.add_annotation(x=34, y=80, xref="x", yref="y", text="No short-corner sequences",
                           showarrow=False, font=dict(size=12, color=TEXT_MUTED), xanchor="center")
    else:
        fig.add_annotation(x=34, y=55, xref="x", yref="y",
                           text=f"<b>Short Corners</b><br>Sequences: {n_seq}",
                           showarrow=False, font=dict(size=10, color=SECONDARY_COL),
                           xanchor="center", yanchor="bottom")
    fig.update_layout(yaxis=dict(range=[52, 108]), margin=dict(l=0, r=0, t=0, b=4))
    return fig


def _fig_attacking_corners(pass_df, color):
    """All corner endpoints: triangle-up=successful, x=unsuccessful, no lines."""
    fig = make_pitch_v_top()
    _add_goalpost(fig)

    # Zone highlights (figure space: vx = 68 - y_m, vy = x_m)
    # six_yard_box: orange  |  penalty_spot: green  |  front+far post: cyan (two wings)
    # SP_SIXYD boundary in figure-vx: 68-28.5=39.5 … 68-39.5=28.5 → strip vx=[28.5,39.5]
    for _zx0, _zx1, _zy0, _zy1, _zfc in [
        (_BOX_X0_SP, 28.5,        88.5, 105.0, "rgba(0,210,210,0.15)"),   # left wing  (cyan)
        (39.5,        _BOX_X1_SP, 88.5, 105.0, "rgba(0,210,210,0.15)"),   # right wing (cyan)
        (28.5,        39.5,       88.5,  99.5,  "rgba(46,204,113,0.22)"),  # penalty_spot (green)
        (28.5,        39.5,       99.5, 105.0,  "rgba(230,126,34,0.28)"),  # six_yard_box (orange)
    ]:
        fig.add_shape(type="rect", xref="x", yref="y",
                      x0=_zx0, x1=_zx1, y0=_zy0, y1=_zy1,
                      fillcolor=_zfc, line=dict(width=0), layer="below")

    if pass_df.empty or "Corner taken" not in pass_df.columns:
        fig.update_layout(yaxis=dict(range=[52, 108]), margin=dict(l=0, r=0, t=0, b=4))
        return fig

    cors = pass_df[(pass_df["event"] == "Pass") & pass_df["Corner taken"].notna()].copy()
    if cors.empty:
        fig.add_annotation(x=34, y=80, xref="x", yref="y", text="No corners",
                           showarrow=False, font=dict(size=12, color=TEXT_MUTED),
                           xanchor="center")
        fig.update_layout(yaxis=dict(range=[52, 108]), margin=dict(l=0, r=0, t=0, b=4))
        return fig

    # Figure-space end coords
    cors["_vx"] = 68.0 - cors["plot_end_y"]
    cors["_vy"] = cors["plot_end_x"]

    # Side: left = origin's figure-x < 34 (plot_y > 34, i.e. y_m > 34)
    cors["_side"] = np.where(cors["plot_y"] > 34, "left", "right")

    # Corner zones (metre coords = plot_end_x / plot_end_y, matching laliga_stats_6.py)
    _x0, _y0 = cors["plot_x"],     cors["plot_y"]
    _ex, _ey = cors["plot_end_x"], cors["plot_end_y"]
    _has  = _ex.notna() & _ey.notna()
    _dist = np.sqrt((_ex - _x0) ** 2 + (_ey - _y0) ** 2)
    _short = _has & ((_dist < 25.0) | (_ex < 88.5))
    _6yd   = (_ex > 99.5) & _ey.between(28.5, 39.5)
    _pen   = _ex.between(88.5, 99.5) & _ey.between(28.5, 39.5)
    _other = (_ex > 88.5) & _ey.between(13.84, 54.16) & ~_6yd & ~_pen
    _near_low = _y0 < 34.0
    _front = pd.Series(np.where(_near_low, _ey < 34.0, _ey >= 34.0), index=cors.index)
    zone = pd.Series(np.nan, index=cors.index, dtype="object")
    zone = zone.mask(_has & _short, "short")
    zone = zone.mask(zone.isna() & _6yd,                "six_yard_box")
    zone = zone.mask(zone.isna() & _pen,                "penalty_spot")
    zone = zone.mask(zone.isna() & _other & _front,     "front_post")
    zone = zone.mask(zone.isna() & _other & ~_front,    "far_post")
    cors["_zone"] = zone

    _latt_col = "Leading to attempt" in cors.columns
    _lgol_col = "Leading to goal"    in cors.columns
    cors["_latt"] = cors["Leading to attempt"].notna() if _latt_col else False
    cors["_lgol"] = cors["Leading to goal"].notna()    if _lgol_col else False

    _cor_col = _SP_TYPE_CFG["Corner"]["color"]   # red

    # Markers — no lines
    _suc = cors[cors["outcome"] == 1]
    _uns = cors[cors["outcome"] == 0]
    if not _suc.empty:
        fig.add_trace(go.Scatter(x=_suc["_vx"].tolist(), y=_suc["_vy"].tolist(),
                                 mode="markers",
                                 marker=dict(size=8, color="white", symbol="triangle-up",
                                             line=dict(color=_cor_col, width=1.5)),
                                 showlegend=False, hoverinfo="skip"))
    if not _uns.empty:
        fig.add_trace(go.Scatter(x=_uns["_vx"].tolist(), y=_uns["_vy"].tolist(),
                                 mode="markers",
                                 marker=dict(size=7, color=_C_FAIL, symbol="x"),
                                 showlegend=False, hoverinfo="skip"))

    # Side annotations
    for side, x_ann, xanchor, label in [
        ("left",  2,  "left",  "Left Corners"),
        ("right", 66, "right", "Right Corners"),
    ]:
        s = cors[cors["_side"] == side]
        if s.empty:
            continue
        z = s["_zone"]
        ann_lines = [
            f"<b>{label}: {len(s)}</b>",
            f"Front Post: {int((z == 'front_post').sum())}",
            f"6-yard box: {int((z == 'six_yard_box').sum())}",
            f"Penalty Spot: {int((z == 'penalty_spot').sum())}",
            f"Far Post: {int((z == 'far_post').sum())}",
            f"Short: {int((z == 'short').sum())}",
            "",
            f"Lead to Attempt: {int(s['_latt'].sum())}",
            f"Lead to Goal: {int(s['_lgol'].sum())}",
        ]
        fig.add_annotation(
            x=x_ann, y=78, xref="x", yref="y",
            text="<br>".join(ann_lines), showarrow=False,
            xanchor=xanchor, yanchor="top", align=xanchor,
            font=dict(size=8, color=_cor_col))

    fig.update_layout(yaxis=dict(range=[52, 108]), margin=dict(l=0, r=0, t=0, b=4))
    return fig


def _fig_fk_throw_box(pass_df, color):
    """FK and throw-in deliveries into the penalty box: triangle-up=success, x=miss."""
    fig = make_pitch_v_top()
    _add_goalpost(fig)
    if pass_df.empty:
        fig.update_layout(yaxis=dict(range=[52, 108]), margin=dict(l=0, r=0, t=0, b=4))
        return fig

    def _qmask(col):
        return pass_df[col].notna() if col in pass_df.columns else pd.Series(False, index=pass_df.index)

    _in_box = (pass_df["plot_end_x"] >= 88.5) & pass_df["plot_end_y"].between(13.84, 54.16)
    fk = pass_df[(pass_df["event"] == "Pass") & _qmask("Free kick taken") & _in_box].copy()
    ti = pass_df[(pass_df["event"] == "Pass") & _qmask("Throw In")         & _in_box].copy()

    for df_sub, col in [(fk, _SP_TYPE_CFG["Free Kick"]["color"]),
                        (ti, _SP_TYPE_CFG["Throw In"]["color"])]:
        if df_sub.empty:
            continue
        _vx = (68.0 - df_sub["plot_end_y"]).tolist()
        _vy = df_sub["plot_end_x"].tolist()
        _suc = df_sub[df_sub["outcome"] == 1]
        _uns = df_sub[df_sub["outcome"] == 0]
        if not _suc.empty:
            fig.add_trace(go.Scatter(
                x=(68.0 - _suc["plot_end_y"]).tolist(), y=_suc["plot_end_x"].tolist(),
                mode="markers",
                marker=dict(size=8, color="white", symbol="triangle-up",
                            line=dict(color=col, width=1.5)),
                showlegend=False, hoverinfo="skip"))
        if not _uns.empty:
            fig.add_trace(go.Scatter(
                x=(68.0 - _uns["plot_end_y"]).tolist(), y=_uns["plot_end_x"].tolist(),
                mode="markers",
                marker=dict(size=7, color=_C_FAIL, symbol="x"),
                showlegend=False, hoverinfo="skip"))

    def _ann(df_sub, x_ann, xanchor, title, ann_color):
        if df_sub.empty:
            return
        latt = int(df_sub["Leading to attempt"].notna().sum()) if "Leading to attempt" in df_sub.columns else 0
        lgol = int(df_sub["Leading to goal"].notna().sum())    if "Leading to goal"    in df_sub.columns else 0
        lines = [
            f"<b>{title}: {len(df_sub)}</b>",
            f"Lead to Attempt: {latt}",
            f"Lead to Goal: {lgol}",
        ]
        fig.add_annotation(
            x=x_ann, y=53, xref="x", yref="y",
            text="<br>".join(lines), showarrow=False,
            xanchor=xanchor, yanchor="bottom", align=xanchor,
            font=dict(size=8.5, color=ann_color))

    _ann(fk, 2,  "left",  "FK into Box",      _SP_TYPE_CFG["Free Kick"]["color"])
    _ann(ti, 66, "right", "Throw-In into Box", _SP_TYPE_CFG["Throw In"]["color"])

    if fk.empty and ti.empty:
        fig.add_annotation(x=34, y=80, xref="x", yref="y",
                           text="No deliveries into box", showarrow=False,
                           font=dict(size=12, color=TEXT_MUTED), xanchor="center")

    fig.update_layout(yaxis=dict(range=[52, 108]), margin=dict(l=0, r=0, t=0, b=4))
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Leader tables (sortable)
# ══════════════════════════════════════════════════════════════════════════════

def _sortable_table(df, sort_col, height_px, ascending=False, fmt_pct=None):
    if df is None or df.empty:
        return html.Div("No data", style={"color": TEXT_MUTED, "fontSize": "10px", "padding": "4px"})
    _cols = sort_col if isinstance(sort_col, list) else [sort_col]
    _asc  = ascending if isinstance(ascending, list) else [ascending] * len(_cols)
    df = df.sort_values(_cols, ascending=_asc).reset_index(drop=True)
    if "#" in df.columns:
        df["#"] = range(1, len(df) + 1)
    return dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        sort_action="native",
        sort_by=[{"column_id": _cols[0], "direction": "asc" if _asc[0] else "desc"}],
        style_table={"height": f"{height_px}px", "overflowY": "auto", "overflowX": "auto"},
        style_header={**TABLE_STYLE_HEADER, "fontSize": "12px", "padding": "1px 4px"},
        style_cell={**TABLE_STYLE_CELL, "fontSize": "12px", "padding": "1px 4px",
                    "height": f"{MM_TABLE_ROW_H}px",
                    "lineHeight": f"{MM_TABLE_ROW_H - 2}px"},
        style_data={**TABLE_STYLE_DATA, "height": f"{MM_TABLE_ROW_H}px"},
        page_action="none",
    )


def _zone_table(df, key_col, lane_fn, lanes, plot_y_col, name_lkp, jersey,
                lane_labels=None):
    """Generic player × lane count table → DataFrame with #, Player, <lanes>, Total."""
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    d["_lane"] = d[plot_y_col].apply(lane_fn)
    d = d[d["_lane"].isin(lanes)]
    if d.empty:
        return pd.DataFrame()
    piv = (d.groupby([key_col, "_lane"]).size().unstack(fill_value=0))
    for ln in lanes:
        if ln not in piv.columns:
            piv[ln] = 0
    piv = piv[lanes]
    piv["Total"] = piv.sum(axis=1)
    piv = piv.reset_index().rename(columns={key_col: "player_id"})
    piv["Player"] = piv["player_id"].map(lambda p: _player_label(p, name_lkp, jersey))
    rename = dict(zip(lanes, lane_labels)) if lane_labels else {}
    piv = piv.rename(columns=rename)
    out_lanes = lane_labels if lane_labels else lanes
    piv.insert(0, "#", range(1, len(piv) + 1))
    return piv[["#", "Player"] + list(out_lanes) + ["Total"]]


def _tbl_prog_pass(pass_df, name_lkp, jersey):
    prog = _prog_passes(pass_df)
    return _zone_table(prog, "player_id", _lcr, ["L", "C", "R"], "plot_end_y", name_lkp, jersey,
                       lane_labels=["Left", "Center", "Right"])


def _tbl_passes_chance(ps_df, name_lkp, jersey):
    """Passes, completion %, chance created and assists per player from per-match stats."""
    if ps_df.empty:
        return pd.DataFrame()
    need = {"player_id", "passes", "passes_completed", "chances_created", "assists"}
    if not need.issubset(ps_df.columns):
        return pd.DataFrame()
    g = ps_df.groupby("player_id").agg(
        Passes=("passes",           "sum"),
        Cmpld= ("passes_completed", "sum"),
        CC=    ("chances_created",  "sum"),
        Ast=   ("assists",          "sum"),
    ).reset_index()
    g["Cmp%"] = (g["Cmpld"] / g["Passes"].replace(0, float("nan")) * 100).round(1)
    g["Player"] = g["player_id"].map(lambda pid: _player_label(pid, name_lkp, jersey))
    g.insert(0, "#", range(1, len(g) + 1))
    return g[["#", "Player", "Passes", "Cmpld", "Cmp%", "CC", "Ast"]]


def _tbl_opp_half_receive(pass_df, name_lkp, jersey):
    recv = pass_df[pass_df["pass_recipient_id"].notna() &
                   (pass_df["plot_end_x"] > 52.5) &
                   pass_df["plot_end_y"].notna()]
    return _zone_table(recv, "pass_recipient_id", _lcr, ["L", "C", "R"],
                       "plot_end_y", name_lkp, jersey)


def _tbl_wide_hs(pass_df, name_lkp, jersey):
    recv = pass_df[pass_df["pass_recipient_id"].notna() &
                   (pass_df["plot_end_x"] > 70) &
                   pass_df["plot_end_y"].notna()]
    return _zone_table(recv, "pass_recipient_id", _wide_hs_lr,
                       ["W-L", "W-R", "HS-L", "HS-R"],
                       "plot_end_y", name_lkp, jersey)


def _tbl_def_actions(def_df, name_lkp, jersey):
    if def_df.empty:
        return pd.DataFrame()
    d = def_df.copy()
    d["_third"] = np.select(
        [d["plot_x"] < 35, d["plot_x"] <= 70], ["Def 3rd", "Mid 3rd"], default="Att 3rd")
    piv = d.groupby(["player_id", "_third"]).size().unstack(fill_value=0)
    for c in ["Def 3rd", "Mid 3rd", "Att 3rd"]:
        if c not in piv.columns:
            piv[c] = 0
    piv = piv[["Def 3rd", "Mid 3rd", "Att 3rd"]]
    piv["Total"] = piv.sum(axis=1)
    piv = piv.reset_index()
    piv["Player"] = piv["player_id"].map(lambda p: _player_label(p, name_lkp, jersey))
    piv.insert(0, "#", range(1, len(piv) + 1))
    return piv[["#", "Player", "Def 3rd", "Mid 3rd", "Att 3rd", "Total"]]


def _tbl_shot_leaders(shot_df, name_lkp, jersey):
    if shot_df.empty:
        return pd.DataFrame()
    d = shot_df.copy()
    d["_sot"] = ((d["on_target"] == 1) | (d["event"] == "Goal")).astype(int)
    d["_goal"] = (d["event"] == "Goal").astype(int)
    g = d.groupby("player_id").agg(Shots=("event", "size"), SoT=("_sot", "sum"),
                                   Goals=("_goal", "sum")).reset_index()
    g["Player"] = g["player_id"].map(lambda p: _player_label(p, name_lkp, jersey))
    g["SoT%"] = (g["SoT"] / g["Shots"] * 100).round(0).astype(int)
    g["Conv%"] = (g["Goals"] / g["Shots"] * 100).round(0).astype(int)
    return g[["Player", "Shots", "SoT", "Goals", "SoT%", "Conv%"]]


def _tbl_sp_receiver(pass_df, shot_df, name_lkp, jersey):
    """Set-piece receivers: attempts received off corners/FKs + set-piece goals."""
    sp = pass_df[(pass_df["event"] == "Pass") & (pass_df["outcome"] == 1) &
                 pass_df["pass_recipient_id"].notna() &
                 (pass_df["Corner taken"].notna() | pass_df["Free kick taken"].notna())]
    att = (sp.groupby("pass_recipient_id").size()
           .reset_index(name="Attempts").rename(columns={"pass_recipient_id": "player_id"}))
    # set-piece goals by scorer
    if not shot_df.empty:
        _spgoal = shot_df[(shot_df["event"] == "Goal")]
        _qual = pd.Series(False, index=_spgoal.index)
        for c in ["Set piece", "From corner", "Free kick"]:
            if c in _spgoal.columns:
                _qual = _qual | _spgoal[c].notna()
        goals = (_spgoal[_qual].groupby("player_id").size()
                 .reset_index(name="Goals"))
    else:
        goals = pd.DataFrame(columns=["player_id", "Goals"])
    out = att.merge(goals, on="player_id", how="outer").fillna(0)
    if out.empty:
        return pd.DataFrame()
    out["Attempts"] = out["Attempts"].astype(int)
    out["Goals"] = out["Goals"].astype(int)
    out["Player"] = out["player_id"].map(lambda p: _player_label(p, name_lkp, jersey))
    out.insert(0, "#", range(1, len(out) + 1))
    return out[["#", "Player", "Attempts", "Goals"]]


def _tbl_sp_taker(pass_df, name_lkp, jersey):
    """Set-piece takers: deliveries into the penalty box only."""
    def _qmask(col):
        return pass_df[col].notna() if col in pass_df.columns else pd.Series(False, index=pass_df.index)

    _in_box = ((pass_df["plot_end_x"] >= 88.5) &
               pass_df["plot_end_y"].between(_BOX_X0_SP, _BOX_X1_SP))
    sp = pass_df[(pass_df["event"] == "Pass") &
                 (_qmask("Corner taken") | _qmask("Free kick taken") | _qmask("Throw In")) &
                 pass_df["player_id"].notna() &
                 _in_box].copy()
    if sp.empty:
        return pd.DataFrame()

    sp["_suc"] = (sp["outcome"] == 1).astype(int)
    sp["_ast"] = (_qmask("Leading to goal").reindex(sp.index, fill_value=False)).astype(int)

    g = sp.groupby("player_id").agg(
        Taken=("event", "size"),
        Suc=  ("_suc",  "sum"),
        Ast=  ("_ast",  "sum"),
    ).reset_index()
    g["Player"] = g["player_id"].map(lambda p: _player_label(p, name_lkp, jersey))
    g.insert(0, "#", range(1, len(g) + 1))
    return g[["#", "Player", "Taken", "Suc", "Ast"]]


def _tbl_sp_recv_box(pass_df, name_lkp, jersey):
    """Set-piece passes ending in the penalty box: receptions, attempts led, goals led."""
    def _qmask(col):
        return pass_df[col].notna() if col in pass_df.columns else pd.Series(False, index=pass_df.index)

    _in_box = ((pass_df["plot_end_x"] >= 88.5) &
               pass_df["plot_end_y"].between(_BOX_X0_SP, _BOX_X1_SP))
    sp_box = pass_df[
        (pass_df["event"] == "Pass") &
        (_qmask("Corner taken") | _qmask("Free kick taken") | _qmask("Throw In")) &
        pass_df["pass_recipient_id"].notna() &
        _in_box
    ].copy()
    if sp_box.empty:
        return pd.DataFrame()

    sp_box["_att"] = (_qmask("Leading to attempt").reindex(sp_box.index, fill_value=False)).astype(int)
    sp_box["_gol"] = (_qmask("Leading to goal").reindex(sp_box.index, fill_value=False)).astype(int)

    g = sp_box.groupby("pass_recipient_id").agg(
        Receive=("event",  "size"),
        Attempt=("_att",   "sum"),
        Goal=   ("_gol",   "sum"),
    ).reset_index().rename(columns={"pass_recipient_id": "player_id"})
    g["Player"] = g["player_id"].map(lambda p: _player_label(p, name_lkp, jersey))
    g.insert(0, "#", range(1, len(g) + 1))
    return g[["#", "Player", "Receive"]]


# ══════════════════════════════════════════════════════════════════════════════
# Compact lineup pieces (Row 1–2)
# ══════════════════════════════════════════════════════════════════════════════

_MM_TBL_HDR_BG = "#EEECE3"
_MM_ROW_ALT_BG = "#F5F3EE"
_MM_SEC_HDR_BG = "#C8C4B8"


def _compact_xi_table(lineup_df):
    """Pos | # | Player table for the predicted XI (small text)."""
    hdr = html.Div([
        html.Div(h, style={"width": w, "fontWeight": "700", "padding": "3px 6px",
                           "fontSize": "0.68rem", "color": TEXT_MUTED})
        for h, w in [("Pos", "24%"), ("#", "14%"), ("Player", "62%")]
    ], style={"display": "flex", "background": _MM_TBL_HDR_BG, "borderBottom": f"1px solid {BORDER}"})

    if lineup_df is None or lineup_df.empty:
        return html.Div([hdr], style={"border": f"1px solid {BORDER}", "borderRadius": "4px"})

    rows = [hdr]
    for i, (_, r) in enumerate(lineup_df.iterrows()):
        bg = _MM_ROW_ALT_BG if i % 2 else CARD_BG
        jv = r["Jersey Number"]
        jstr = str(int(jv)) if (jv is not None and jv == jv) else "-"
        pid = r["player_id"]
        name = DISP_NAME.get(pid, str(pid)) if (pid is not None and pid == pid) else "-"
        rows.append(html.Div([
            html.Div(str(r["pos"]), style={"width": "24%", "padding": "3px 6px", "fontSize": "0.7rem"}),
            html.Div(jstr,          style={"width": "14%", "padding": "3px 6px", "fontSize": "0.7rem"}),
            html.Div(name,          style={"width": "62%", "padding": "3px 6px", "fontSize": "0.7rem",
                                            "overflow": "hidden", "textOverflow": "ellipsis",
                                            "whiteSpace": "nowrap"}),
        ], style={"display": "flex", "alignItems": "center", "background": bg,
                  "borderBottom": f"1px solid {BORDER}"}))
    return html.Div(rows, style={"border": f"1px solid {BORDER}", "borderRadius": "4px",
                                 "overflow": "hidden"})


_MM_MIN_COLS = ["#", "Player", "Games", "Pos", "Alt", "Mins"]
_MM_MIN_W    = ["8%", "34%", "16%", "12%", "18%", "12%"]


def _compact_minutes_table(code, match_ids):
    """Squad minutes table for the selected matches (small text, scrollable)."""
    _, _, all_players, _ = prepare_team_data(code, match_ids)
    sections = get_squad_sections(code, all_players)

    def _hdr():
        return html.Div([
            html.Div(h, style={"width": w, "fontWeight": "700", "padding": "3px 6px",
                               "fontSize": "0.66rem", "color": TEXT_MUTED})
            for h, w in zip(_MM_MIN_COLS, _MM_MIN_W)
        ], style={"display": "flex", "background": _MM_TBL_HDR_BG,
                  "borderBottom": f"1px solid {BORDER}", "position": "sticky",
                  "top": "0", "zIndex": "1"})

    def _sec(label):
        return html.Div(label, style={"background": _MM_SEC_HDR_BG, "color": "#FFFFFF",
                                       "fontWeight": "700", "padding": "3px 8px",
                                       "fontSize": "0.66rem", "letterSpacing": "0.3px",
                                       "borderBottom": f"1px solid {BORDER}"})

    def _row(player, alt):
        jv = player.get("Jersey Number")
        jstr = str(int(jv)) if (jv is not None and str(jv) != "nan") else "-"
        name = DISP_NAME.get(player["player_id"], str(player["player_id"]))
        vals = [jstr, name, player.get("Games Played") or "0(0)",
                player.get("Position") or "-", player.get("Secondary Position") or "-",
                str(int(player.get("Mins", 0)) if str(player.get("Mins", 0)) != "nan" else 0)]
        return html.Div([
            html.Div(v, style={"width": w, "padding": "3px 6px", "fontSize": "0.68rem",
                               "overflow": "hidden", "textOverflow": "ellipsis",
                               "whiteSpace": "nowrap"})
            for v, w in zip(vals, _MM_MIN_W)
        ], style={"display": "flex", "alignItems": "center",
                  "background": _MM_ROW_ALT_BG if alt else CARD_BG,
                  "borderBottom": f"1px solid {BORDER}"})

    rows = [_hdr()]
    for label, df in sections:
        rows.append(_sec(label))
        for i, (_, p) in enumerate(df.iterrows()):
            rows.append(_row(p, i % 2 == 1))

    return html.Div(rows, style={"border": f"1px solid {BORDER}", "borderRadius": "4px",
                                 "overflow": "hidden"})


# ══════════════════════════════════════════════════════════════════════════════
# Match selector (Row 1, cols 1–2)
# ══════════════════════════════════════════════════════════════════════════════

_MM_SEL_ROW_H = 26
_MM_SEL_ROWS  = 6
_MM_MAX       = 5


def _build_selector(code, options):
    default_ids = [options[0]["value"]] if options else []

    _btn = dict(background="transparent", border=f"1px solid {BORDER}", color=TEXT_MUTED,
                padding="4px 10px", borderRadius="5px", cursor="pointer",
                fontSize="0.7rem", fontWeight="500")
    _submit = {**_btn, "background": LALIGA_RED, "border": f"1px solid {LALIGA_RED}",
               "color": "#ffffff", "marginLeft": "auto"}

    return html.Div([
        dcc.Checklist(
            id={"type": "mm-sel", "team": code},
            options=options, value=default_ids,
            inputStyle={"marginRight": "6px", "cursor": "pointer", "flexShrink": "0"},
            labelStyle={"display": "flex", "alignItems": "center", "padding": "2px 6px",
                        "borderBottom": f"1px solid {BORDER}", "fontSize": "0.68rem",
                        "cursor": "pointer", "color": TEXT_MAIN, "whiteSpace": "nowrap"},
            style={"height": f"{_MM_SEL_ROWS * _MM_SEL_ROW_H}px", "overflowY": "auto",
                   "overflowX": "auto", "background": CARD_BG,
                   "border": f"1px solid {BORDER}", "borderRadius": "5px 5px 0 0"},
        ),
        html.Div([
            html.Div(id={"type": "mm-count", "team": code},
                     style={"fontSize": "0.68rem", "color": TEXT_MUTED, "alignSelf": "center"}),
            dcc.Dropdown(
                id={"type": "mm-preset", "team": code},
                options=get_opponent_options(code),
                placeholder="Preset: last 5 before…",
                clearable=True,
                style={"width": "190px", "fontSize": "0.66rem"},
            ),
            html.Button("Unselect All", id={"type": "mm-none", "team": code}, style=_btn),
            html.Button("Submit", id={"type": "mm-submit", "team": code}, style=_submit,
                        disabled=False),
        ], style={"display": "flex", "gap": "6px", "alignItems": "center", "padding": "5px 6px",
                  "background": _MM_TBL_HDR_BG, "border": f"1px solid {BORDER}",
                  "borderTop": "none", "borderRadius": "0 0 5px 5px"}),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# Grid helpers
# ══════════════════════════════════════════════════════════════════════════════

def _box(*children):
    return html.Div(list(children), style={
        "display": "flex", "flexDirection": "column", "height": "100%",
        "minWidth": "0", "overflow": "hidden", "boxSizing": "border-box"})


def _grid_row(header, b1, b2, b3, height):
    cells = []
    for box, basis in [(b1, "32%"), (b2, "32%"), (b3, "36%")]:
        cells.append(html.Div(box, style={
            "flexBasis": basis, "maxWidth": basis, "flexShrink": "0", "minWidth": "0",
            "boxSizing": "border-box", "padding": "0 2px"}))
    children = []
    if header:
        children.append(make_section_label(header))
    children.append(html.Div(cells, style={"display": "flex", "height": f"{height}px"}))
    return html.Div(children, style={"marginBottom": "6px"})


def _sub(label):
    return make_section_label(label)


def _cap(text):
    return html.Div(text, style={
        "fontSize": "0.66rem", "fontWeight": "600", "color": SECONDARY_COL,
        "textAlign": "center", "padding": "2px", "flexShrink": "0"})


def _fb_seq_count(df_all, code):
    """Count fast-break shot sequences for the team (proxy for fast-break seq)."""
    if df_all.empty or "Fast break" not in df_all.columns:
        return 0
    _shot_ev = {"Goal", "Miss", "Post", "Saved Shot"}
    sub = df_all[(df_all["team_code"] == code) &
                 df_all["event"].isin(_shot_ev) &
                 (df_all["Fast break"] == "Si")]
    return int(len(sub))


def _ppda(df_all, def_df, code):
    """Rough PPDA = opponent passes in their own 60% ÷ our def. actions in our high 60%."""
    if df_all.empty:
        return None
    opp_pass = df_all[(df_all["team_code"] != code) &
                      (df_all["event"] == "Pass") & (df_all["x"] < 60)]
    high_def = def_df[def_df["x"] > 40] if not def_df.empty else def_df
    n_def = len(high_def)
    if n_def == 0:
        return None
    return round(len(opp_pass) / n_def, 1)


# ── Row 1–2 dynamic blocks ────────────────────────────────────────────────────

def _selected_matches_list(code, match_ids):
    """Read-only list of the selected matches (same label format as the selector)."""
    options, _ = get_match_options(code)
    lbl = {o["value"]: o["label"] for o in options}
    sel = [m for m in (match_ids or []) if m in lbl]
    if not sel:
        body = [html.Div("No matches selected", style={"padding": "6px 8px",
                "fontSize": "0.66rem", "color": TEXT_MUTED})]
    else:
        body = [html.Div(lbl[m], style={
            "padding": "3px 8px", "borderBottom": f"1px solid {BORDER}",
            "fontSize": "0.55rem", "color": TEXT_MAIN, "whiteSpace": "nowrap",
            "overflow": "hidden", "textOverflow": "ellipsis",
            "background": _MM_ROW_ALT_BG if i % 2 else CARD_BG})
            for i, m in enumerate(sel)]
    return html.Div(body, style={"border": f"1px solid {BORDER}", "borderRadius": "4px",
                                 "overflow": "auto", "height": "205px"})


def _mm_lineup_pitch(formation, hex1, hext, lineup_df, name_lkp):
    """Predicted-formation pitch (small markers) + right-side Pos/#/Player list."""
    fig     = make_pitch_v_bottom()
    coords  = formation_coords.get(formation, {})
    pos_map = formation_position_mapping.get(formation, {})

    jersey_by_pos, name_by_pos = {}, {}
    if lineup_df is not None and not lineup_df.empty:
        for _, row in lineup_df.iterrows():
            jv   = row["Jersey Number"]
            jstr = str(int(jv)) if (jv is not None and jv == jv) else ""
            pid  = row["player_id"]
            name = DISP_NAME.get(pid, "") if (pid is not None and pid == pid) else ""
            jersey_by_pos.setdefault(row["pos"], []).append(jstr)
            name_by_pos.setdefault(row["pos"], []).append(name)

    cursor = {}
    for slot, (xc, yc) in coords.items():
        pos    = pos_map.get(slot, "")
        idx    = cursor.get(pos, 0)
        jersey = jersey_by_pos.get(pos, [""])[idx] if idx < len(jersey_by_pos.get(pos, [])) else ""
        cursor[pos] = idx + 1
        px_v = 68 - yc
        py_v = xc * 1.25
        fig.add_trace(go.Scatter(
            x=[px_v], y=[py_v], mode="markers+text",
            marker=dict(size=22, color=hex1, line=dict(color=hext, width=1.5)),
            text=[jersey], textposition="middle center",
            textfont=dict(color=hext, size=9, family="Arial"),
            showlegend=False, hoverinfo="skip",
        ))

    # Right-side Pos / # / Player list, sorted by POS_ORDER
    if lineup_df is not None and not lineup_df.empty:
        _po = {p: i for i, p in enumerate(POS_ORDER)}
        _ld = lineup_df.copy()
        _ld["_o"] = _ld["pos"].map(lambda p: _po.get(p, 99))
        _ld = _ld.sort_values("_o")
        lines = ["<b>Pos   #   Player</b>"]
        for _, r in _ld.iterrows():
            jv = r["Jersey Number"]
            jstr = str(int(jv)) if (jv is not None and jv == jv) else "-"
            nm = _abbrev_name(name_lkp.get(r["player_id"], DISP_NAME.get(r["player_id"], "")))
            lines.append(f"{str(r['pos']):<4} {jstr:>2}  {nm}")
        fig.add_annotation(
            x=71, y=66, xref="x", yref="y", text="<br>".join(lines),
            showarrow=False, align="left", xanchor="left", yanchor="top",
            font=dict(size=9, color="#333333", family="Arial"),
        )
    fig.update_layout(xaxis=dict(range=[-2, 90]), margin=dict(l=0, r=0, t=0, b=0))
    return fig


def build_mm_row2(code, match_ids):
    """Row 2: selected-matches list (box1) + annotated predicted-formation pitch (box2)."""
    td   = TEAM_DATA.get(code, {})
    hex1 = td.get("bg", "#333333")
    hext = td.get("text", "#FFFFFF")

    formation_df1, _, _, mins = prepare_team_data(code, match_ids)
    formation = get_default_formation(formation_df1)
    lineup_df = get_predicted_lineup(formation_df1, mins)
    name_lkp  = _load_player_names()

    if formation:
        pitch_fig = _mm_lineup_pitch(formation, hex1, hext, lineup_df, name_lkp)
        pitch = _mg(pitch_fig, MM_R2_PITCH_H)
        ptitle = f"Predicted Formation — {fmt_formation(formation)}"
    else:
        pitch = html.Div("No formation data", style={"color": TEXT_MUTED,
                         "fontSize": "0.7rem", "padding": "8px"})
        ptitle = "Predicted Formation"

    return html.Div([
        html.Div(_box(_cap("Selected Matches"), _selected_matches_list(code, match_ids)),
                 style={"flexBasis": "50%", "maxWidth": "50%", "flexShrink": "0",
                        "minWidth": "0", "padding": "0 2px", "boxSizing": "border-box"}),
        html.Div(_box(_cap(ptitle), pitch),
                 style={"flexBasis": "50%", "maxWidth": "50%", "flexShrink": "0",
                        "minWidth": "0", "padding": "0 2px", "boxSizing": "border-box"}),
    ], style={"display": "flex", "height": f"{MM_ROW2_H}px"})


def build_mm_minutes(code, match_ids):
    """Row 1–2 right column (col 3): squad minutes table."""
    return html.Div([
        make_section_label("Minutes Played — Selected Matches"),
        html.Div(_compact_minutes_table(code, match_ids),
                 style={"overflowY": "auto", "height": "404px"}),
    ])


# ── Body (Rows 3–8) ───────────────────────────────────────────────────────────

def _player_watch_cards(shot_df, pass_df, ps_df, name_lkp, jersey, color):
    """Two cards: Top Attacking Threat | Top Creation Threat (circle badge + stats)."""
    td_text = "#FFFFFF"

    def _card(role, pid, stat_lines):
        nm = _abbrev_name(name_lkp.get(pid, str(pid))) if pid is not None else "–"
        j  = jersey.get(pid) if pid is not None else None
        jstr = str(int(j)) if (j is not None and j == j) else "-"
        badge = html.Div(jstr, style={
            "width": "34px", "height": "34px", "borderRadius": "50%",
            "background": color, "color": td_text, "fontWeight": "700",
            "fontSize": "0.8rem", "display": "flex", "alignItems": "center",
            "justifyContent": "center", "flexShrink": "0",
            "border": f"1.5px solid {BORDER}"})
        stat_block = html.Div([
            html.Div(s, style={"fontSize": "0.62rem", "color": SECONDARY_COL,
                               "lineHeight": "1.25"})
            for s in stat_lines])
        return html.Div([
            html.Div(role, style={"fontSize": "0.58rem", "fontWeight": "700",
                                  "color": TEXT_MUTED, "textTransform": "uppercase",
                                  "letterSpacing": "0.3px", "textAlign": "center",
                                  "marginBottom": "5px"}),
            html.Div([
                badge,
                html.Div(nm, style={"fontSize": "0.74rem", "fontWeight": "700",
                                    "color": SECONDARY_COL, "marginLeft": "6px",
                                    "overflow": "hidden", "textOverflow": "ellipsis",
                                    "whiteSpace": "nowrap"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "5px"}),
            stat_block,
        ], style={"flex": "1", "minWidth": "0", "border": f"1px solid {BORDER}",
                  #"borderTop": f"3px solid {color}", "borderRadius": "5px",
                  "padding": "6px 8px", "margin": "0 3px"})

    # aggregate per-match stats across selected matches
    _agg = pd.DataFrame()
    if not ps_df.empty:
        _num = ps_df.select_dtypes(include="number").columns.difference(["match_id", "week"])
        _agg = ps_df.groupby("player_id")[_num].sum()

    def _g(pid, col, default=0):
        if _agg.empty or pid is None or col not in _agg.columns or pid not in _agg.index:
            return default
        v = _agg.at[pid, col]
        return int(v) if pd.notna(v) else default

    def _col(name):
        return _agg[name] if (not _agg.empty and name in _agg.columns) else pd.Series(0, index=_agg.index)

    # Top Attacking Threat: ranked by goals then shots
    sh_pid, sh_lines = None, ["No data"]
    if not _agg.empty:
        _score = _col("goals") * 1000 + _col("shots")
        if not _score.empty:
            sh_pid  = _score.idxmax()
            _goals  = _g(sh_pid, "goals")
            _shots  = _g(sh_pid, "shots")
            _sot    = _g(sh_pid, "shots_on_target")
            _conv   = f"{_goals / _shots * 100:.0f}%" if _shots > 0 else "–"
            _to     = _g(sh_pid, "take_ons")
            _tow    = _g(sh_pid, "take_ons_won")
            _pto    = _g(sh_pid, "progressive_take_ons")
            sh_lines = [
                f"Goals: {_goals}",
                f"Shots: {_shots}  (SoT: {_sot})",
                f"Conv%: {_conv}",
                f"Take-On: {_tow}/{_to}",
                f"Prog Take-On: {_pto}",
            ]

    # Top Creation Threat: ranked by assists then chances_created then prog passes
    cr_pid, cr_lines = None, ["No data"]
    if not _agg.empty:
        _score2 = (_col("assists") * 1000
                   + _col("chances_created") * 100
                   + _col("progressive_passes_opp_half"))
        if not _score2.empty:
            cr_pid = _score2.idxmax()
            _ast   = _g(cr_pid, "assists")
            _cc    = _g(cr_pid, "chances_created")
            _ppoh  = _g(cr_pid, "progressive_passes_opp_half")
            _crs   = _g(cr_pid, "crosses")
            _sp    = _g(cr_pid, "corners_taken") + _g(cr_pid, "fk_taken")
            cr_lines = [
                f"Assists: {_ast}",
                f"CC: {_cc}",
                f"Prog Pass (Opp Half): {_ppoh}",
                f"Crosses: {_crs}",
                f"Set Pieces: {_sp}",
            ]

    return html.Div([
        _card("Top Attacking Threat", sh_pid, sh_lines),
        _card("Top Creation Threat", cr_pid, cr_lines),
    ], style={"display": "flex", "height": "100%"})




def build_multi_match_body(code, match_ids):
    """Rows 3–8 of the report (everything below the lineup block)."""
    if not match_ids:
        return html.Div("Select at least one match (max 5) and press Submit.",
                        style={"color": TEXT_MUTED, "padding": "16px", "fontSize": "0.9rem"})

    n_matches = max(len(match_ids), 1)
    td    = TEAM_DATA.get(code, {})
    color = td.get("bg", "#333333")

    df_all = _load_event_csvs(match_ids)
    pass_df, shot_df, carry_df, def_df, df_raw_team = _preprocess(df_all, code)
    team_avgs, league_avgs, ps_df = _load_benchmarks(code, match_ids)
    ts_season_df = _load_season_stats()
    name_lkp     = _load_player_names()
    jersey       = _name_jersey(df_raw_team)
    opp_lkp      = _opp_lookup(df_all, code)

    # ── Row 3 — Build-up & Chance Creation ────────────────────────────────────
    gk_fig   = _fig_gk(pass_df, color, arrows=False)
    gk_df    = _gk_pass_df(pass_df)
    sel_gk_short = int((gk_df["dist_group"] == "short").sum()) if not gk_df.empty else 0
    sel_gk_long  = int((gk_df["dist_group"] == "long").sum())  if not gk_df.empty else 0
    gks_t, gks_l, _, _ = _season_metric(ts_season_df, code, "gk_short")
    gkl_t, gkl_l, _, _ = _season_metric(ts_season_df, code, "gk_long")
    gk_bench = _bench_2col(
        dict(title="Short GK Pass", code=code, sel=sel_gk_short / n_matches,
             szn=gks_t, league=gks_l, color=color),
        dict(title="Long GK Pass", code=code, sel=sel_gk_long / n_matches,
             szn=gkl_t, league=gkl_l, color=color))

    prog_hm  = _fig_prog_hm_v(pass_df, color, name_lkp)
    _prog_mask = (pass_df["progressive"] == 1) & (pass_df["event"] == "Pass") & (pass_df["outcome"] == 1)
    sel_prog_total    = len(pass_df[_prog_mask])
    sel_prog_opp_half = len(pass_df[_prog_mask & (pass_df["Pass End X"] > 50)])
    pp_t,   pp_l,   pp_r,   pp_n   = _season_metric(ts_season_df, code, "progressive_passes")
    ppoh_t, ppoh_l, ppoh_r, ppoh_n = _season_metric(ts_season_df, code, "progressive_passes_opp_half")

    t_prog     = _tbl_prog_pass(pass_df, name_lkp, jersey)
    t_recv     = _tbl_opp_half_receive(pass_df, name_lkp, jersey)
    t_pass_cc  = _tbl_passes_chance(ps_df, name_lkp, jersey)

    row3 = _grid_row(
        "Build-up & Chance Creation",
        _box(_cap("Goalkeeper Distribution"),
             html.Div(_mg(gk_fig, MM_R3_GK_H), style={"flexShrink": "0"}),
             gk_bench),
        _box(_cap("Prog. Passes into Opp. Half"),
             html.Div(_mg(prog_hm, MM_R3_PROG_H), style={"flexShrink": "0"}),
             _bench_2col(
                 dict(title="Total Prog. Passes", code=code,
                      sel=sel_prog_total / n_matches, szn=pp_t, league=pp_l,
                      color=color, fmt="{:.0f}", note=_rank_note(pp_r, pp_n)),
                 dict(title="Prog. Passes into Opp. Half", code=code,
                      sel=sel_prog_opp_half / n_matches, szn=ppoh_t, league=ppoh_l,
                      color=color, fmt="{:.0f}", note=_rank_note(ppoh_r, ppoh_n)),
             )),
        _box(_cap("Passes and Chance Creation Leaders"), _sortable_table(t_pass_cc, ["Ast", "CC", "Cmp%"], MM_R3_TBL_H),
             _cap("Prog Pass into Opp. Half Leaders"), _sortable_table(t_prog, "Total", MM_R3_TBL_H)),
        height=MM_ROW3_H,
    )

    # ── Row 4 — Pass Receive | Crosses (no header) ────────────────────────────
    recv_hm = _fig_receive_hm(pass_df, color)
    _df_cross   = _cross_df(df_raw_team)
    cross_fig   = _fig_crosses(df_raw_team, color)
    sel_cr_wide = int(_df_cross["zone"].isin({"Left Wide", "Right Wide"}).sum())
    sel_cr_hs   = int(_df_cross["zone"].isin({"Left HS", "Right HS"}).sum())
    crw_t, crw_l, _, _ = _season_metric(ts_season_df, code, "crosses_wide")
    crh_t, crh_l, _, _ = _season_metric(ts_season_df, code, "crosses_hs")
    cross_bench = _bench_2col(
        dict(title="HS Cross", code=code, sel=sel_cr_hs / n_matches,
             szn=crh_t, league=crh_l, color=color),
        dict(title="Wide Cross", code=code, sel=sel_cr_wide / n_matches,
             szn=crw_t, league=crw_l, color=color))
    t_widehs = _tbl_wide_hs(pass_df, name_lkp, jersey)

    row4 = _grid_row(
        None,
        _box(_cap("Pass Receive Heatmap"), _mg(recv_hm, MM_R4_RECV_H)),
        _box(_cap("Open Play Crosses"),
             html.Div(_mg(cross_fig, MM_R4_CROSS_H), style={"flexShrink": "0"}),
             cross_bench),
        _box(_cap("Opp-Half Pass Receive Leaders"), _sortable_table(t_recv, "Total", MM_R4_TBL2_H),
             _cap("Crosses — Wide / Half-Space Leaders"), _sortable_table(t_widehs, "Total", MM_R4_TBL2_H)),
        height=MM_ROW4_H,
    )

    # ── Row 5 — Shots ─────────────────────────────────────────────────────────
    shot_fig = _fig_shots(shot_df, color, name_lkp, arrows=False,
                          goal_illustration=False, opp_lkp=opp_lkp)
    goal_fig = _fig_goalmouth(shot_df, color, name_lkp, opp_lkp)

    n_shots = len(shot_df)
    n_sot   = int(((shot_df["on_target"] == 1) | (shot_df["event"] == "Goal")).sum()) if n_shots else 0
    n_goals = int((shot_df["event"] == "Goal").sum()) if n_shots else 0
    if n_shots:
        _ib = int((shot_df["x"] >= 83).sum())   # inside box ≈ x ≥ 83 (Opta 0–100)
        _ob = n_shots - _ib
    else:
        _ib = _ob = 0

    def _stat_at(label, val, x, top):
        return html.Div([
            html.Div(label, style={"fontSize": "0.5rem", "color": TEXT_MUTED, "lineHeight": "1"}),
            html.Div(str(val), style={"fontSize": "0.72rem", "fontWeight": "700",
                                      "lineHeight": "1.1"}),
        ], style={"position": "absolute", "left": f"{x}%", "top": top,
                  "transform": "translateX(-50%)", "textAlign": "center",
                  "color": SECONDARY_COL})

    stats_html = html.Div([
        _stat_at("Shots", n_shots, 10, "2px"),
        _stat_at("SoT", n_sot, 50, "2px"),
        _stat_at("Goals", n_goals, 90, "2px"),
        _stat_at("Inside Box", _ib, 30, "32px"),
        _stat_at("Outside Box", _ob, 70, "32px"),
    ], style={"position": "relative", "height": f"{MM_R5_STATS_H}px", "flexShrink": "0"})

    sh_t, sh_l, sh_r, sh_n = _season_metric(ts_season_df, code, "shots")
    shot_bench = _bench("Shots", code, n_shots / n_matches, sh_t, sh_l, color,
                        fmt="{:.1f}", note=_rank_note(sh_r, sh_n))

    sot_t, sot_l, sot_r, sot_n = _season_metric(ts_season_df, code, "shots_on_target")
    sot_bench = _bench("Shots on Target", code, n_sot / n_matches, sot_t, sot_l, color,
                       fmt="{:.1f}", note=_rank_note(sot_r, sot_n))

    t_shooters = _tbl_shot_leaders(shot_df, name_lkp, jersey)

    row5 = _grid_row(
        "Shots",
        _box(_cap("Shot Map"),
             html.Div(_mg(shot_fig, MM_R5_SHOT_H), style={"flexShrink": "0"}),
             shot_bench),
        _box(_cap("Goal Placement"),
             html.Div(_mg(goal_fig, MM_R5_GOAL_H), style={"flexShrink": "0"}),
             stats_html,
             sot_bench),
        _box(_cap("Shot Leaders"), _sortable_table(t_shooters, "Shots", MM_R5_TBL_H)),
        height=MM_ROW5_H,
    )

    # ── Row 6 — Defensive & Transitions ───────────────────────────────────────
    fb_fig  = _fig_recovery_fb(df_all, code, color)
    sel_fb  = _fb_seq_count(df_all, code)
    sel_rec = int(((df_all["team_code"] == code) &
                   (df_all["event"] == "Ball recovery")).sum()) if not df_all.empty else 0
    rec_t, rec_l, _, _ = _season_metric(ts_season_df, code, "ball_recoveries")
    fb_t, fb_l, fb_r, fb_n = _season_metric(ts_season_df, code, "fast_break_seq")
    fb_bench = _bench_2col(
        dict(title="Ball Recovery", code=code, sel=sel_rec / n_matches,
             szn=rec_t, league=rec_l, color=color),
        dict(title="Fast Break Seq", code=code, sel=sel_fb / n_matches,
             szn=fb_t, league=fb_l, color=color, note=_rank_note(fb_r, fb_n)))

    defhm_fig = _fig_def_hm(def_df, color)
    sel_ppda  = _ppda(df_all, def_df, code)
    sel_defa  = int(len(def_df))
    pd_t, pd_l, pd_r, pd_n = _season_metric(ts_season_df, code, "ppda")
    da_t, da_l, _, _ = _season_metric(ts_season_df, code, "def_actions")
    def_bench = _bench_2col(
        dict(title="PPDA", code=code, sel=sel_ppda, szn=pd_t, league=pd_l, color=color,
             note=_rank_note(pd_r, pd_n)),
        dict(title="Def Action", code=code, sel=sel_defa / n_matches,
             szn=da_t, league=da_l, color=color))

    t_def = _tbl_def_actions(def_df, name_lkp, jersey)

    row6 = _grid_row(
        "Defensive & Transitions",
        _box(_cap("Ball Recovery & Fast Break Sequences"),
             html.Div(_mg(fb_fig, MM_R6_FB_H), style={"flexShrink": "0"}),
             fb_bench),
        _box(_cap("Defensive Action Heatmap"),
             html.Div(_mg(defhm_fig, MM_R6_DEFHM_H), style={"flexShrink": "0"}),
             def_bench),
        _box(_cap("Defensive Actions"),
             _sortable_table(t_def, "Total", MM_R6_TBL_H)),
        height=MM_ROW6_H,
    )

    # ── Row 7 — Attacking Set Pieces ──────────────────────────────────────────
    sp_corner_fig = _fig_attacking_corners(pass_df, color)
    sp_fkthr_fig  = _fig_fk_throw_box(pass_df, color)
    t_sp_taker    = _tbl_sp_taker(pass_df, name_lkp, jersey)
    t_sp_recv_box = _tbl_sp_recv_box(pass_df, name_lkp, jersey)

    row7 = _grid_row(
        "Attacking Set Pieces",
        _box(_cap("Attacking Corners"), _mg(sp_corner_fig, MM_R7_GRAPH_H)),
        _box(_cap("Attacking Free Kicks and Throw Ins"), _mg(sp_fkthr_fig, MM_R7_GRAPH_H)),
        _box(_cap("Set Piece Taker (Deliveries into Box)"), _sortable_table(t_sp_taker, "Taken", MM_R7_TBL_H),
             _cap("Set Piece Target (Penalty Box)"),
             _sortable_table(t_sp_recv_box, "Receive", MM_R7_TBL_H)),
        height=MM_ROW7_H,
    )

    # ── Row 8 — Tactical Profile ───────────────────────────────────────────────
    cat_data_season = _cat_percentiles(code, ts_season_df)
    cat_data_match  = _cat_percentiles_match(code, match_ids, ts_season_df)
    radar_fig = _fig_radar_cat(cat_data_match, cat_data_season, code, color)
    breakdown = _fig_cat_breakdown(cat_data_match, cat_data_season, color)
    row8 = _grid_row(
        "Tactical Profile",
        _box(_cap("Player to Watch"),
             _player_watch_cards(shot_df, pass_df, ps_df, name_lkp, jersey, color)),
        _box(_cap("Tactical Radar"),    _mg(radar_fig, MM_R8_RADAR_H)),
        _box(_cap("Category Breakdown"), _mg(breakdown, MM_R8_RADAR_H)),
        height=MM_ROW8_H,
    )

    return html.Div([row3, row4, row5, row6, row7, row8],
                    style={"backgroundColor": 'BG_COLOUR'}) 


# ══════════════════════════════════════════════════════════════════════════════
# Layout builder (called from pages/team.py)
# ══════════════════════════════════════════════════════════════════════════════

def build_multi_match_layout(code):
    """8-row × 3-column (32% / 32% / 36%) scouting-report layout.

    Rows 1–2 hold the match selector, predicted formation/XI and squad minutes;
    rows 3–8 hold the tactical analysis.  The selector is static; the predicted
    XI / minutes / body are pattern-matched containers rebuilt on Submit.
    """
    options, all_ids = get_match_options(code)
    default_ids = [options[0]["value"]] if options else []

    selector = _build_selector(code, options)

    left_region = html.Div([
        selector,
        html.Div(style={"height": "8px"}),
        html.Div(build_mm_row2(code, default_ids),
                 id={"type": "mm-row2", "team": code}),
    ], style={"width": "64%", "flexShrink": "0", "paddingRight": "4px", "boxSizing": "border-box"})

    minutes_region = html.Div(
        build_mm_minutes(code, default_ids),
        id={"type": "mm-minutes", "team": code},
        style={"width": "36%", "flexShrink": "0", "boxSizing": "border-box"},
    )

    top = html.Div([left_region, minutes_region],
                   style={"display": "flex", "alignItems": "flex-start", "marginBottom": "6px"})

    body = html.Div(build_multi_match_body(code, default_ids),
                    id={"type": "mm-body", "team": code})

    return html.Div([top, body],
                    style={"backgroundColor": BG_COLOUR, "padding": "4px"})
