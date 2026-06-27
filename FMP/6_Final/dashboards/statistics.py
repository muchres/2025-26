"""
Statistics page — team full-season profile.

Row 1  : Tactical Radar (season percentiles) + Category Breakdown bar chart.
Rows 2–9: one row per _RADAR_CATS category.
  Left  55% — vertical grouped bar chart: team vs league (index, league = 100).
  Right 45% — player leaderboard for the category's relevant metrics.
"""

import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html, dash_table

from utils.constants import (
    BG_COLOUR, CARD_BG, BORDER,
    PRIMARY_COL, SECONDARY_COL, TERTIARY_COL, TEXT_MUTED,
)
from utils.data_loader import TEAM_DATA
from dashboards.match_analysis import (
    make_section_label, make_graph,
    TABLE_STYLE_HEADER, TABLE_STYLE_CELL, TABLE_STYLE_DATA,
)
from dashboards.multi_match_report import (
    _cat_percentiles, _RADAR_CATS, _load_season_stats, _rgb,
)
from dashboards.pitch import make_pitch_v

_HERE  = os.path.dirname(os.path.abspath(__file__))
_APP   = os.path.dirname(_HERE)
_DATA  = os.path.join(os.path.dirname(_APP), "2_Data")
_STATS = os.path.join(_DATA, "laliga_stats")
_PLAYER_STATS_SEASON = os.path.join(_STATS, "player_stats_season.csv")
_PLAYER_LIST         = os.path.join(_DATA, "laliga_player_list.csv")
_SWOT_PM_FILE        = os.path.join(_DATA, "laliga_swot", "swot_stats_team_per_match.csv")

_ROW1_H    = 310   # tactical radar + breakdown row
_PITCH_ROW_H = 460  # zone-pitch distribution row
_CAT_ROW_H = 290   # each of the 8 category rows

_LEAGUE_GREY = "#CFCABB"

# make_pitch_v coordinate system: x=0..68 (width), y=0..105 (length)
_PMW      = 68.0
_PML      = 105.0
_FLANK_OF = {z: "LCR"[(z - 1) % 3] for z in range(1, 19)}


# ── Player leaderboard config ─────────────────────────────────────────────────

_CAT_PLAYER_CFG = {
    "Finishing": {
        "sort": "goals", "ascending": False,
        "cols": [("Player","player_name"), ("Goals","goals"),
                 ("Shots","shots"), ("SoT","shots_on_target")],
    },
    "Creativity": {
        "sort": "chances_created", "ascending": False,
        "cols": [("Player","player_name"), ("CC","chances_created"),
                 ("Prog OH","progressive_passes_opp_half"), ("Take-ons","take_ons")],
    },
    "Progression": {
        "sort": "progressive_passes", "ascending": False,
        "cols": [("Player","player_name"), ("Prog P","progressive_passes"),
                 ("Prog OH","progressive_passes_opp_half"), ("Passes","passes")],
    },
    "Transitions": {
        "sort": "fast_break_shots", "ascending": False,
        "cols": [("Player","player_name"), ("FB Shots","fast_break_shots"),
                 ("Goals","goals"), ("Take-ons W","take_ons_won")],
    },
    "Pressing": {
        "sort": "recoveries", "ascending": False,
        "cols": [("Player","player_name"), ("Recoveries","recoveries"),
                 ("Tackles W","tackles_won"), ("Intercept","interceptions")],
    },
    "Defending": {
        "sort": "_def_total", "ascending": False,
        "cols": [("Player","player_name"), ("Tackles","tackles"),
                 ("Intercept","interceptions"), ("Clear","clearances")],
    },
    "Set Pieces": {
        "sort": "_sp_total", "ascending": False,
        "cols": [("Player","player_name"), ("SP Shots","_sp_shots"),
                 ("SP Goals","_sp_goals"), ("Corners","corners_taken")],
    },
    "Ball Control": {
        "sort": "passes_completed", "ascending": False,
        "cols": [("Player","player_name"), ("Pass Acc%","pass_accuracy_pct"),
                 ("Prog P","progressive_passes"), ("Passes","passes")],
    },
}


# ── Data helpers ──────────────────────────────────────────────────────────────

def _load_player_stats():
    """Load player season stats, deduplicated and named via the player list.

    player_stats_season.csv has one row per (player × formation), so the same
    player can appear up to 30 times.  We sum all count-stats across formations,
    recompute derived ratios, then replace player_name with Display Name from
    laliga_player_list.csv.
    """
    if not os.path.exists(_PLAYER_STATS_SEASON):
        return pd.DataFrame()

    ps = pd.read_csv(_PLAYER_STATS_SEASON)

    # Columns that should NOT be summed across formations
    _SKIP = {
        "Team Formation", "Team Player Formation", "Jersey Number",
        "pass_accuracy_pct", "shot_accuracy_pct",
        "tackle_success_pct", "take_on_success_pct", "goals_per90",
    }
    sum_cols = [
        c for c in ps.select_dtypes(include="number").columns
        if c not in _SKIP
    ]

    ps_agg = ps.groupby(["player_id", "team_code"], as_index=False)[sum_cols].sum()

    # Recompute derived ratios on the aggregated totals
    def _safe_ratio(num, den, scale=100):
        return (ps_agg[num] / ps_agg[den].replace(0, np.nan) * scale).round(1)

    ps_agg["pass_accuracy_pct"]  = _safe_ratio("passes_completed", "passes")
    ps_agg["shot_accuracy_pct"]  = _safe_ratio("shots_on_target",  "shots")
    ps_agg["tackle_success_pct"] = _safe_ratio("tackles_won",      "tackles")
    ps_agg["take_on_success_pct"]= _safe_ratio("take_ons_won",     "take_ons")
    ps_agg["goals_per90"]        = (
        ps_agg["goals"] / ps_agg["minutes_played"].replace(0, np.nan) * 90
    ).round(2)

    # Replace player_name with Display Name from the player list
    if os.path.exists(_PLAYER_LIST):
        pl = pd.read_csv(_PLAYER_LIST, encoding="utf-8-sig")
        name_map = (pl.drop_duplicates("player_id")
                     .set_index("player_id")["Display Name"]
                     .to_dict())
        ps_agg["player_name"] = ps_agg["player_id"].map(name_map).fillna(ps_agg["player_id"])
    else:
        ps_agg["player_name"] = ps_agg["player_id"]

    return ps_agg


def _cat_ranks(code, ts_df):
    """Rank of each category for the team (1 = best in league).

    Calls _cat_percentiles for every team, builds a cross-team score matrix,
    then returns (ranks_dict, n_teams).
    """
    if ts_df is None or ts_df.empty or "team_code" not in ts_df.columns:
        return {}, 20

    teams = ts_df["team_code"].dropna().unique()
    # cat_label -> {team_code: category_pct}
    all_scores: dict[str, dict] = {}
    for tc in teams:
        for cat_label, cat_pct, _ in _cat_percentiles(tc, ts_df):
            all_scores.setdefault(cat_label, {})[tc] = cat_pct

    n = len(teams)
    ranks = {}
    for cat_label, team_scores in all_scores.items():
        ordered = sorted(team_scores, key=lambda tc: team_scores[tc], reverse=True)
        ranks[cat_label] = (ordered.index(code) + 1) if code in ordered else None
    return ranks, n


def _metric_index(ts_df, code, num_col, den_col, invert):
    """Per-match average for the team and league, plus an index where league=100.

    For invert=True metrics (lower is better) the index is inverted so that
    values above 100 always mean "better than average".

    Returns (team_raw, league_raw, team_index).  Any may be None on missing data.
    """
    if ts_df is None or ts_df.empty:
        return None, None, None

    if isinstance(num_col, tuple):
        if any(c not in ts_df.columns for c in num_col):
            return None, None, None
        nums = ts_df[[*num_col]].sum(axis=1)
    else:
        if num_col not in ts_df.columns:
            return None, None, None
        nums = ts_df[num_col]

    if den_col is None:
        ratios = nums.astype(float)
    elif den_col == "matches":
        if "matches" not in ts_df.columns:
            return None, None, None
        ratios = nums / ts_df["matches"].replace(0, np.nan)
    else:
        if den_col not in ts_df.columns:
            return None, None, None
        ratios = nums / ts_df[den_col].replace(0, np.nan)

    league_raw = float(ratios.mean()) if not ratios.isna().all() else None
    team_rows  = ts_df[ts_df["team_code"] == code]
    if team_rows.empty:
        return None, league_raw, None
    team_raw = float(ratios.loc[team_rows.index[0]])

    if (league_raw is None or league_raw == 0
            or np.isnan(team_raw) or np.isnan(league_raw)):
        return team_raw, league_raw, None

    idx = (league_raw / team_raw * 100) if invert else (team_raw / league_raw * 100)
    return team_raw, league_raw, round(idx, 1)


def _fmt(v):
    if v is None or np.isnan(v):
        return "—"
    if abs(v) >= 100:
        return f"{v:.1f}"
    if abs(v) >= 10:
        return f"{v:.2f}"
    return f"{v:.3f}"


# ── SWOT zone-pitch data helpers ──────────────────────────────────────────────

def _load_swot_pm():
    if not os.path.exists(_SWOT_PM_FILE):
        return pd.DataFrame()
    return pd.read_csv(_SWOT_PM_FILE)


def _sum_team(swot_df, code):
    rows = swot_df[swot_df["team_code"] == code]
    return rows.sum(numeric_only=True) if not rows.empty else pd.Series(dtype=float)


def _sum_opp(swot_df, code):
    mids = swot_df.loc[swot_df["team_code"] == code, "match_id"]
    rows = swot_df[(swot_df["match_id"].isin(mids)) & (swot_df["team_code"] != code)]
    return rows.sum(numeric_only=True) if not rows.empty else pd.Series(dtype=float)


def _build_team_avgs(swot_df):
    """Per-team per-match average of each team's own stats."""
    n = swot_df.groupby("team_code").size()
    return swot_df.groupby("team_code").sum(numeric_only=True).div(n, axis=0)


def _build_opp_avgs(swot_df):
    """Per-team per-match average of what opponents produced against each team."""
    tc_list = swot_df["team_code"].unique()
    rows, nm = {}, {}
    for tc in tc_list:
        mids    = swot_df.loc[swot_df["team_code"] == tc, "match_id"]
        opp     = swot_df[(swot_df["match_id"].isin(mids)) & (swot_df["team_code"] != tc)]
        nm[tc]  = len(mids)
        rows[tc] = opp.sum(numeric_only=True)
    return pd.DataFrame(rows).T.div(pd.Series(nm), axis=0)


def _pct_series(series):
    """Percentile rank (0–100) for every value in series; 50 = median."""
    n = len(series)
    return (series.rank(method="average") - 0.5) / n * 100


def _col_avg(avgs, prefix, zones):
    """Sum of per-match averages for the given stat prefix × zone list."""
    cols = [f"{prefix}_z{z}" for z in zones if f"{prefix}_z{z}" in avgs.columns]
    return avgs[cols].sum(axis=1) if cols else pd.Series(0.0, index=avgs.index)


def _pos_play_lcr_pct(avgs, code):
    """
    Per-flank avg percentile of [pp, to_suc, shot, cross_suc].
    cross_suc only for L/R (no wide-cross zones in the central column).
    Returns {flank: {'pct', 'rank', 'n', 'metrics': [(label, pct), ...]}} .
    """
    _L = [1, 4, 7, 10, 13, 16]
    _C = [2, 5, 8, 11, 14, 17]
    _R = [3, 6, 9, 12, 15, 18]
    OPP  = set(range(10, 19))
    WIDE = {10, 12, 13, 15, 16, 18}
    n = len(avgs)
    result = {}
    for flank, zones in (("L", _L), ("C", _C), ("R", _R)):
        opp_z  = [z for z in zones if z in OPP]
        wide_z = [z for z in zones if z in WIDE]
        metric_map = {
            "Prog Pass":   _pct_series(_col_avg(avgs, "pp",     zones)),
            "Take-On Won": _pct_series(_col_avg(avgs, "to_suc", opp_z)),
            "Shot":        _pct_series(_col_avg(avgs, "shot",   opp_z)),
            "Goal":        _pct_series(_col_avg(avgs, "goal",   opp_z)),
        }
        if wide_z:
            metric_map["Cross Suc"] = _pct_series(_col_avg(avgs, "cross_suc", wide_z))
        avg_all  = pd.DataFrame(metric_map).mean(axis=1)
        team_pct = float(avg_all.get(code, 50.0))
        team_rank = int(avg_all.rank(ascending=False, method="min").get(code, n // 2))
        result[flank] = {
            "pct": team_pct,
            "rank": team_rank,
            "n": n,
            "metrics": [(lbl, float(s.get(code, 50.0))) for lbl, s in metric_map.items()],
        }
    return result


def _fb_lcr_pct(avgs, code):
    """
    Per-direction avg percentile of [fb_seq, fb_goal].
    Returns {dir: {'pct', 'rank', 'n', 'metrics': [(label, pct), ...]}} .
    """
    n = len(avgs)
    result = {}
    for d in "LCR":
        metric_map = {}
        for col, lbl in ((f"fb_seq_{d}", "FB Sequences"), (f"fb_goal_{d}", "FB Goals")):
            if col in avgs.columns:
                metric_map[lbl] = _pct_series(avgs[col])
        if not metric_map:
            result[d] = {"pct": 50.0, "rank": n // 2, "n": n, "metrics": []}
            continue
        avg_all   = pd.DataFrame(metric_map).mean(axis=1)
        team_pct  = float(avg_all.get(code, 50.0))
        team_rank = int(avg_all.rank(ascending=False, method="min").get(code, n // 2))
        result[d] = {
            "pct": team_pct,
            "rank": team_rank,
            "n": n,
            "metrics": [(lbl, float(s.get(code, 50.0))) for lbl, s in metric_map.items()],
        }
    return result


# ── Figure builders ───────────────────────────────────────────────────────────

def _fig_radar_season(cat_data, code, color):
    """Single-trace radar: team season percentiles vs league average (50)."""
    labels     = [d[0] for d in cat_data]
    values     = [d[1] for d in cat_data]
    league_ref = [50.0] * len(labels)

    lbl_closed = labels + [labels[0]]
    v_closed   = values + [values[0]]
    l_closed   = league_ref + [league_ref[0]]

    r, g, b = _rgb(color)
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=l_closed, theta=lbl_closed,
        mode="lines", line=dict(color="#AAAAAA", width=1.5, dash="dot"),
        name="League Avg", showlegend=True,
    ))
    fig.add_trace(go.Scatterpolar(
        r=v_closed, theta=lbl_closed,
        fill="toself", fillcolor=f"rgba({r},{g},{b},0.25)",
        line=dict(color=color, width=2),
        name=f"{code} Season", showlegend=True,
    ))
    fig.update_layout(
        polar=dict(
            bgcolor=CARD_BG,
            radialaxis=dict(
                visible=True, range=[0, 108],
                tickvals=[25, 50, 75, 100],
                ticktext=["25", "50", "75", "100"],
                tickfont=dict(size=8, color=SECONDARY_COL),
                gridcolor="#B9B2A6", gridwidth=1, linecolor="#B9B2A6",
            ),
            angularaxis=dict(
                tickfont=dict(size=10, color=SECONDARY_COL),
                gridcolor="#B9B2A6", gridwidth=1, linecolor="#B9B2A6",
            ),
        ),
        showlegend=True,
        legend=dict(x=0.5, y=-0.10, xanchor="center", orientation="h",
                    font=dict(size=10, color=SECONDARY_COL)),
        margin=dict(l=55, r=55, t=34, b=46),
        paper_bgcolor=CARD_BG,
    )
    return fig


def _fig_breakdown_season(cat_data, color, ranks=None, n_teams=20):
    """Horizontal bar chart: 8 category season percentile scores.

    When ranks is provided (cat_label -> rank int) the bar text also shows
    the league rank, e.g. "74  #4/20".
    """
    rev    = list(reversed(cat_data))
    labels = [d[0] for d in rev]
    values = [d[1] for d in rev]

    def _sub_str(sub):
        return f"{sub[0]}: {sub[1]:.0f}th pct" if sub[2] is not None else f"{sub[0]}: —"

    customdata = [
        [_sub_str(d[2][i]) if i < len(d[2]) else "" for i in range(3)]
        for d in rev
    ]

    r, g, b  = _rgb(color)
    bar_cols = [f"rgba({r},{g},{b},{0.35 + 0.55 * v / 100:.2f})" for v in values]

    if ranks:
        bar_text = [
            f"{v:.0f}  #{ranks[lbl]}/{n_teams}" if ranks.get(lbl) is not None else f"{v:.0f}"
            for lbl, v in zip(labels, values)
        ]
        x_max = 130
    else:
        bar_text = [f"{v:.0f}" for v in values]
        x_max = 100

    fig = go.Figure()
    fig.add_trace(go.Bar(
        orientation="h",
        x=values, y=labels,
        marker_color=bar_cols,
        text=bar_text,
        textposition="outside",
        textfont=dict(size=10, color=SECONDARY_COL),
        customdata=customdata,
        hovertemplate=(
            "<b>%{y}</b>: %{x:.1f}th pct<br>"
            "%{customdata[0]}<br>%{customdata[1]}<br>%{customdata[2]}"
            "<extra></extra>"
        ),
        cliponaxis=False,
    ))
    fig.add_vline(x=50, line=dict(color="#AAAAAA", width=1.2, dash="dot"))
    fig.update_layout(
        xaxis=dict(range=[0, x_max], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False,
                   tickfont=dict(size=10, color=SECONDARY_COL)),
        margin=dict(l=5, r=8, t=4, b=4),
        paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
        showlegend=False, bargap=0.25,
    )
    return fig


def _fig_cat_bars(cat_label, metrics, ts_df, code, color, cat_pct=50.0):
    """Vertical grouped bar chart: team vs league per-match average.

    Four groups: Total (category-level percentile index) then the 3 sub-metrics.
    All values are expressed as an index where league average = 100.
    For inverted metrics (lower=better, marked with ↓) the index is flipped so
    that above-100 always means better than league average.
    Hover tooltips show actual per-match values.
    """
    r, g, b = _rgb(color)

    # ── Total bar (leftmost) ──────────────────────────────────────────────────
    total_idx = round((cat_pct / 50.0) * 100, 1)
    x_labels  = [f"Total {cat_label}"]
    team_idxs = [total_idx]
    league_idxs = [100.0]
    hovers = [
        f"<b>Total {cat_label}</b><br>"
        f"Category percentile: {cat_pct:.1f}<br>"
        f"Index: {total_idx:.1f}"
    ]

    # ── Three sub-metric bars ─────────────────────────────────────────────────
    for m_label, num_col, den_col, invert in metrics:
        team_raw, league_raw, idx = _metric_index(ts_df, code, num_col, den_col, invert)

        lbl = m_label + (" ↓" if invert else "")
        x_labels.append(lbl)
        team_idxs.append(idx)
        league_idxs.append(100.0 if idx is not None else None)

        if idx is not None:
            hovers.append(
                f"<b>{m_label}</b>{'  (↓ = better)' if invert else ''}<br>"
                f"{code}: {_fmt(team_raw)}<br>"
                f"League Avg: {_fmt(league_raw)}<br>"
                f"Index: {idx:.1f}"
            )
        else:
            hovers.append(f"<b>{m_label}</b><br>No data")

    fig = go.Figure()

    # League avg bars (always 100)
    fig.add_trace(go.Bar(
        name="League Avg",
        x=x_labels, y=league_idxs,
        marker_color=_LEAGUE_GREY,
        text=["100" if v is not None else "" for v in league_idxs],
        textposition="inside",
        textfont=dict(size=9, color=SECONDARY_COL),
        hoverinfo="skip",
        showlegend=True,
    ))

    # Team bars — Total bar uses full opacity to stand out
    bar_cols = []
    for i, v in enumerate(team_idxs):
        if v is None:
            bar_cols.append("#CCCCCC")
        elif i == 0:
            bar_cols.append(f"rgba({r},{g},{b},1.0)")   # Total: solid
        else:
            bar_cols.append(f"rgba({r},{g},{b},0.75)")  # sub-metrics: slightly transparent

    fig.add_trace(go.Bar(
        name=code,
        x=x_labels, y=team_idxs,
        marker_color=bar_cols,
        text=[f"{v:.0f}" if v is not None else "N/A" for v in team_idxs],
        textposition="outside",
        textfont=dict(size=10, color=SECONDARY_COL),
        customdata=hovers,
        hovertemplate="%{customdata}<extra></extra>",
        showlegend=True,
    ))

    valid = [v for v in team_idxs if v is not None]
    ymax  = max(valid + [100], default=120) * 1.22
    ymin  = min(valid + [100], default=60) * 0.80
    ymin  = min(ymin, 75)

    fig.add_hline(y=100, line=dict(color="#888888", width=1, dash="dot"))
    fig.update_layout(
        barmode="group",
        xaxis=dict(tickfont=dict(size=10, color=SECONDARY_COL),
                   showgrid=False, zeroline=False),
        yaxis=dict(
            range=[ymin, ymax], showgrid=False, zeroline=False,
            tickfont=dict(size=9, color=SECONDARY_COL),
            title=dict(text="Index  (League = 100)",
                       font=dict(size=9, color=SECONDARY_COL)),
        ),
        margin=dict(l=44, r=8, t=8, b=8),
        paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
        bargap=0.25, bargroupgap=0.08,
        legend=dict(x=0.5, y=1.06, xanchor="center", orientation="h",
                    font=dict(size=9, color=SECONDARY_COL)),
    )
    return fig


def _fig_zone_pitch(color, data, sub_text=None, defending=False):
    """make_pitch_v base + L/C/R bars overlaid.

    data      : {flank: {'pct', 'rank', 'n', 'metrics': [(label, pct), ...]}}
    defending : if True, bars hang DOWN from y=105 and L/R columns are mirrored
                (opponent L = our R). Rank is also inverted so 1 = best defence.
    """
    col_w = _PMW / 3
    r, g, b = _rgb(color)
    if defending:
        r, g, b = 136, 136, 136  # #888888

    fig = make_pitch_v()
    fig.update_layout(plot_bgcolor=CARD_BG, paper_bgcolor=CARD_BG)

    # Column dividers — always above traces
    for x in (col_w, 2 * col_w):
        fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=_PML,
                      line=dict(color="rgba(150,150,150,0.55)", width=1.0, dash="dot"),
                      layer="above")

    # Column order: defending mirrors L/R (opponent's L attacks our R side)
    if defending:
        col_order = [("L", "R", 0, col_w), ("C", "C", col_w, 2*col_w), ("R", "L", 2*col_w, _PMW)]
    else:
        col_order = [("L", "L", 0, col_w), ("C", "C", col_w, 2*col_w), ("R", "R", 2*col_w, _PMW)]

    for disp_lbl, data_key, x0, x1 in col_order:
        d       = data.get(data_key, {})
        pct     = d.get("pct",  50.0)
        rank    = d.get("rank", 10)
        n_teams = d.get("n",    20)
        metrics = d.get("metrics", [])
        bar_h   = pct / 100 * _PML
        opacity = 0.35 + 0.55 * pct / 100
        xm      = (x0 + x1) / 2

        # Defending: rank 1 = best defence (least opp activity → lowest pct)
        display_rank = (n_teams - rank + 1) if defending else rank

        # Hover tooltip
        metric_lines = "<br>".join(f"  {lbl}: {p:.0f}th pct" for lbl, p in metrics)
        hover = (f"<b>{disp_lbl} Flank</b><br>"
                 f"Score: {pct:.0f}  #{display_rank}/{n_teams}<br>"
                 f"<br>{metric_lines}"
                 f"<extra></extra>")

        # Bar: attacking rises from y=0; defending hangs from y=_PML
        bar_base = (_PML - bar_h) if defending else 0.0
        fig.add_trace(go.Bar(
            x=[xm], y=[bar_h],
            base=bar_base,
            width=col_w - 3.0,
            marker_color=f"rgba({r},{g},{b},{opacity:.2f})",
            marker_line_width=0,
            hovertemplate=hover,
            showlegend=False,
            name="",
        ))

        # Rank label: inside bar when tall enough, outside (tip side) when short
        lbl_text = f"<b>{pct:.0f}</b><br>#{display_rank}/{n_teams}"
        short = bar_h < 7
        if defending:
            lbl_y      = (_PML - bar_h - 2) if short else (_PML - bar_h / 2)
            lbl_anchor = "top"    if short else "middle"
        else:
            lbl_y      = (bar_h + 2) if short else (bar_h / 2)
            lbl_anchor = "bottom" if short else "middle"
        lbl_color = SECONDARY_COL if short else "white"

        fig.add_annotation(x=xm, y=lbl_y, text=lbl_text,
                           showarrow=False, xanchor="center", yanchor=lbl_anchor,
                           font=dict(size=9, color=lbl_color))

        # FB sub-label (raw seq · goals), keyed by data_key (opponent's perspective)
        if sub_text and data_key in sub_text:
            fig.add_annotation(x=xm, y=-9, text=sub_text[data_key],
                               showarrow=False, xanchor="center", yanchor="top",
                               font=dict(size=8, color=SECONDARY_COL))

        fig.add_annotation(x=xm, y=_PML + 2, text=disp_lbl,
                           showarrow=False, xanchor="center", yanchor="bottom",
                           font=dict(size=10, color=SECONDARY_COL))

    fig.add_annotation(x=_PMW / 2, y=_PML + 7, text="▲ ATK",
                       showarrow=False, xanchor="center", yanchor="bottom",
                       font=dict(size=8, color=TEXT_MUTED))

    fig.update_layout(
        barmode="overlay",
        yaxis_range=[-14, _PML + 12],
        margin=dict(l=2, r=2, t=6, b=40),
    )
    return fig


# ── Player leaderboard ────────────────────────────────────────────────────────

def _player_tbl(code, cat_label, ps_df, height_px=240):
    """Top-12 player leaderboard for a category."""
    if ps_df is None or ps_df.empty:
        return html.Div("No player data.",
                        style={"color": TEXT_MUTED, "fontSize": "0.8rem", "padding": "8px"})

    cfg = _CAT_PLAYER_CFG.get(cat_label)
    if cfg is None:
        return html.Div()

    team_ps = ps_df[ps_df["team_code"] == code].copy()
    if team_ps.empty:
        return html.Div("No player data.",
                        style={"color": TEXT_MUTED, "fontSize": "0.8rem", "padding": "8px"})

    # Derived columns
    team_ps["_def_total"] = (
        team_ps.get("tackles",       pd.Series(0, index=team_ps.index)).fillna(0) +
        team_ps.get("interceptions", pd.Series(0, index=team_ps.index)).fillna(0) +
        team_ps.get("clearances",    pd.Series(0, index=team_ps.index)).fillna(0)
    )
    team_ps["_sp_shots"] = (
        team_ps.get("sp_direct_to_shot",    pd.Series(0, index=team_ps.index)).fillna(0) +
        team_ps.get("sp_sequence_to_shot",  pd.Series(0, index=team_ps.index)).fillna(0)
    )
    team_ps["_sp_goals"] = (
        team_ps.get("sp_direct_to_goal",    pd.Series(0, index=team_ps.index)).fillna(0) +
        team_ps.get("sp_sequence_to_goal",  pd.Series(0, index=team_ps.index)).fillna(0)
    )
    team_ps["_sp_total"] = (
        team_ps["_sp_shots"] + team_ps["_sp_goals"] +
        team_ps.get("corners_taken", pd.Series(0, index=team_ps.index)).fillna(0)
    )

    sort_col = cfg["sort"]
    if sort_col not in team_ps.columns:
        return html.Div("No data for this category.",
                        style={"color": TEXT_MUTED, "fontSize": "0.8rem", "padding": "8px"})

    team_ps = (team_ps[team_ps["minutes_played"] >= 90]
               .sort_values(sort_col, ascending=cfg["ascending"])
               .head(12))

    display_cols = cfg["cols"]
    rows = []
    for _, r in team_ps.iterrows():
        row = {}
        for disp_name, src_col in display_cols:
            val = r.get(src_col, "")
            if disp_name == "Player":
                row[disp_name] = str(val) if pd.notna(val) else "?"
            elif disp_name == "Pass Acc%":
                row[disp_name] = f"{val:.1f}%" if pd.notna(val) else "—"
            elif pd.isna(val):
                row[disp_name] = 0
            else:
                row[disp_name] = int(val) if float(val) == int(float(val)) else round(float(val), 1)
        rows.append(row)

    if not rows:
        return html.Div("No data.", style={"color": TEXT_MUTED, "fontSize": "0.8rem", "padding": "8px"})

    df_disp  = pd.DataFrame(rows)
    col_names = [c[0] for c in display_cols]
    col_widths = [
        {"if": {"column_id": c},
         "width": "110px" if c == "Player" else "60px",
         "minWidth": "110px" if c == "Player" else "60px",
         "maxWidth": "110px" if c == "Player" else "60px",
         "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis"}
        for c in col_names
    ]

    return dash_table.DataTable(
        data=df_disp.to_dict("records"),
        columns=[{"name": c, "id": c} for c in col_names],
        style_header={**TABLE_STYLE_HEADER, "fontSize": "11px", "padding": "2px 4px"},
        style_cell={**TABLE_STYLE_CELL, "fontSize": "11px", "padding": "2px 4px", "height": "18px"},
        style_data=TABLE_STYLE_DATA,
        style_cell_conditional=col_widths,
        style_as_list_view=True,
        sort_action="native",
        page_size=12,
        style_table={"overflowY": "auto", "maxHeight": f"{height_px}px"},
    )


# ── Layout helpers ────────────────────────────────────────────────────────────

def _cap(text):
    return html.Div(text, style={
        "fontSize": "0.66rem", "fontWeight": "600", "color": SECONDARY_COL,
        "textAlign": "center", "padding": "2px 0", "flexShrink": "0",
    })


def _mg(fig, height):
    try:
        fig.update_layout(plot_bgcolor=CARD_BG, paper_bgcolor=CARD_BG)
    except Exception:
        pass
    return make_graph(fig, height)


def _cell(content, basis):
    return html.Div(content, style={
        "flexBasis": basis, "maxWidth": basis, "flexShrink": "0", "minWidth": "0",
        "boxSizing": "border-box", "padding": "0 3px",
        "display": "flex", "flexDirection": "column",
    })


# ── Main entry point ──────────────────────────────────────────────────────────

def build_statistics_layout(code):
    """Season statistics page for the given team code."""
    td    = TEAM_DATA.get(code, {})
    color = td.get("bg", "#333333")

    ts_df    = _load_season_stats()
    ps_df    = _load_player_stats()
    cat_data = _cat_percentiles(code, ts_df)
    ranks, n_teams = _cat_ranks(code, ts_df)

    # ── Row 1: Tactical Radar + Category Breakdown ────────────────────────────
    radar_fig     = _fig_radar_season(cat_data, code, color)
    breakdown_fig = _fig_breakdown_season(cat_data, color, ranks=ranks, n_teams=n_teams)
    graph_h1      = _ROW1_H - 28

    row1 = html.Div([
        make_section_label("Season Tactical Profile"),
        html.Div([
            _cell([_cap("Tactical Radar"),     _mg(radar_fig,     graph_h1)], "42%"),
            _cell([_cap("Category Breakdown"), _mg(breakdown_fig, graph_h1)], "58%"),
        ], style={"display": "flex", "height": f"{_ROW1_H}px"}),
    ], style={"marginBottom": "6px"})

    # ── Row 1b: Zone Pitch Distribution ──────────────────────────────────────
    swot_df = _load_swot_pm()
    pitch_h = _PITCH_ROW_H - 58

    if not swot_df.empty:
        team_avgs = _build_team_avgs(swot_df)
        opp_avgs  = _build_opp_avgs(swot_df)

        pp_att = _pos_play_lcr_pct(team_avgs, code)
        pp_def = _pos_play_lcr_pct(opp_avgs,  code)
        fb_att = _fb_lcr_pct(team_avgs, code)
        fb_def = _fb_lcr_pct(opp_avgs,  code)

        # Raw season totals for sub-labels
        team_s = _sum_team(swot_df, code)
        opp_s  = _sum_opp(swot_df, code)

        _OPP_ZONES = {"L": [10,13,16], "C": [11,14,17], "R": [12,15,18]}
        pp_att_sub = {
            fl: (f"shots: {sum(int(team_s.get(f'shot_z{z}',0) or 0) for z in zs)}"
                 f"<br>goals: {sum(int(team_s.get(f'goal_z{z}',0) or 0) for z in zs)}")
            for fl, zs in _OPP_ZONES.items()
        }
        pp_def_sub = {
            fl: (f"allowed: {sum(int(opp_s.get(f'shot_z{z}',0) or 0) for z in zs)}"
                 f"<br>conceded: {sum(int(opp_s.get(f'goal_z{z}',0) or 0) for z in zs)}")
            for fl, zs in _OPP_ZONES.items()
        }

        fb_att_sub = {d: f"{int(team_s.get(f'fb_seq_{d}',0) or 0)} seq · "
                         f"{int(team_s.get(f'fb_goal_{d}',0) or 0)}G" for d in "LCR"}
        fb_def_sub = {d: f"{int(opp_s.get(f'fb_seq_{d}',0) or 0)} seq · "
                         f"{int(opp_s.get(f'fb_goal_{d}',0) or 0)}G" for d in "LCR"}

        pitches = [
            (f"{code} Attacking Actions", _fig_zone_pitch(color, pp_att, pp_att_sub)),
            ("Attacking Actions Allowed", _fig_zone_pitch(color, pp_def, pp_def_sub, defending=True)),
            (f"{code} Fast Break Attack", _fig_zone_pitch(color, fb_att,  fb_att_sub)),
            ("Fast Break Allowed",        _fig_zone_pitch(color, fb_def,  fb_def_sub, defending=True)),
        ]
        pitch_cells = [_cell([_cap(ttl), _mg(fig, pitch_h)], "25%") for ttl, fig in pitches]

        row_zones = html.Div([
            make_section_label("Zone Distribution — Pos Play & Fast Break"),
            html.Div(pitch_cells, style={"display": "flex", "height": f"{_PITCH_ROW_H}px"}),
        ], style={"marginBottom": "6px"})
    else:
        row_zones = html.Div()

    # ── Rows 2–9: One row per category ───────────────────────────────────────
    bar_h   = _CAT_ROW_H - 40
    tbl_h   = _CAT_ROW_H - 44

    # Build a lookup from cat_data for quick access to cat_pct per category
    cat_pct_map = {d[0]: d[1] for d in cat_data}

    cat_rows = []
    for cat_label, metrics in _RADAR_CATS:
        cat_pct    = cat_pct_map.get(cat_label, 50.0)
        bar_fig    = _fig_cat_bars(cat_label, metrics, ts_df, code, color, cat_pct=cat_pct)
        player_tbl = _player_tbl(code, cat_label, ps_df, height_px=tbl_h)

        cat_rows.append(html.Div([
            make_section_label(cat_label),
            html.Div([
                _cell(
                    [_cap(f"Team vs League — Index (League = 100)"),
                     _mg(bar_fig, bar_h)],
                    "55%",
                ),
                _cell(
                    [_cap("Player Leaderboard"), player_tbl],
                    "45%",
                ),
            ], style={"display": "flex", "height": f"{_CAT_ROW_H}px"}),
        ], style={"marginBottom": "6px"}))

    return html.Div([row1, row_zones] + cat_rows,
                    style={"backgroundColor": BG_COLOUR, "padding": "4px 0"})
