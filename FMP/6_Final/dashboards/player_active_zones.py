"""Player Active Zones — subtab of the Team page.

Shows per-player action heatmaps across 18 pitch zones, filtered by match
selection and playing position, across four side-by-side columns.
"""

import os

import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html, dash_table

from utils.constants import (
    BG_COLOUR, PRIMARY_COL, SECONDARY_COL, TERTIARY_COL,
    BORDER, CARD_BG, TEXT_MUTED, TEXT_MAIN, LALIGA_RED,
    formation_mapping, formation_position_mapping,
)
from utils.data_loader import TEAM_DATA, team_name
from utils.lineup_data import get_match_options
from dashboards.pitch import make_pitch_v
from dashboards.match_analysis import TABLE_STYLE_HEADER, TABLE_STYLE_CELL, TABLE_STYLE_DATA

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_APP  = os.path.dirname(_HERE)
_DATA = os.path.join(os.path.dirname(_APP), "2_Data")
_SWOT_CSV   = os.path.join(_DATA, "laliga_swot",  "swot_stats_player_per_match.csv")
_PLAYER_CSV = os.path.join(_DATA, "laliga_player_list.csv")
_STATS_CSV  = os.path.join(_DATA, "laliga_stats", "player_stats_per_match.csv")

# ── Module-level data (loaded once) ───────────────────────────────────────────
_SWOT_DF   = pd.read_csv(_SWOT_CSV)                        if os.path.exists(_SWOT_CSV)   else pd.DataFrame()
_PLAYER_DF = pd.read_csv(_PLAYER_CSV, encoding="utf-8-sig") if os.path.exists(_PLAYER_CSV) else pd.DataFrame()
_STATS_DF  = pd.read_csv(_STATS_CSV)                        if os.path.exists(_STATS_CSV)  else pd.DataFrame()

# ── Zone geometry (vertical pitch: x = width 0-68, y = length 0-105) ─────────
_ZONE_W  = 68.0 / 3   # ≈ 22.67 m per column
_ZONE_H  = 105.0 / 6  # = 17.5 m per row

_ZONES_L    = [1, 4, 7, 10, 13, 16]
_ZONES_C    = [2, 5, 8, 11, 14, 17]
_ZONES_R    = [3, 6, 9, 12, 15, 18]
_ZONES_DEF3 = list(range(1, 7))
_ZONES_MID3 = list(range(7, 13))
_ZONES_ATT3 = list(range(13, 19))
_ZONES_ALL  = list(range(1, 19))

# ── Action prefix groups ───────────────────────────────────────────────────────
_ATK_PREFIXES = ["pp", "to_ttl", "cross_ttl", "shot"]
_DEF_PREFIXES = ["tackle_ttl", "int", "chall", "recovery"]
_ALL_PREFIXES = _ATK_PREFIXES + _DEF_PREFIXES

# ── Selector layout constants ──────────────────────────────────────────────────
_SEL_ROWS    = 6
_SEL_ROW_H   = 26
_SEL_HDR_BG  = "#EEECE3"
_ROW_ALT_BG  = "#F5F3EE"

_ACTION_OPTIONS = [
    {"label": "All",               "value": "all"},
    {"label": "Attacking Actions", "value": "attacking"},
    {"label": "Defensive Actions", "value": "defensive"},
]


# ══════════════════════════════════════════════════════════════════════════════
# Data helpers
# ══════════════════════════════════════════════════════════════════════════════

def _get_position(formation_num, slot_num):
    """Position label (e.g. 'CAM') from numeric formation code + slot number.

    Uses formation_mapping (num→str) then formation_position_mapping (str→pos),
    both from utils.constants — no extra CSV load required.
    """
    try:
        form_str = formation_mapping.get(str(int(float(formation_num))), "")
        if not form_str:
            return ""
        return formation_position_mapping.get(form_str, {}).get(str(int(float(slot_num))), "")
    except (ValueError, TypeError):
        return ""


def get_player_options(code):
    """All players for a team, sorted by jersey number asc."""
    if _PLAYER_DF.empty:
        return []
    df = _PLAYER_DF[_PLAYER_DF["team_code"] == code].drop_duplicates("player_id").copy()
    df["_jn"] = pd.to_numeric(df["Jersey Number"], errors="coerce")
    df = df.dropna(subset=["_jn"]).sort_values("_jn")
    opts = []
    for _, row in df.iterrows():
        jersey = int(row["_jn"])
        name   = row.get("Display Name") or row.get("player_name") or str(row["player_id"])
        opts.append({"label": f"#{jersey} {name}", "value": row["player_id"]})
    return opts


def get_opponent_options(code):
    """All other La Liga teams as dropdown options (sorted by name)."""
    opts = [{"label": team_name(c), "value": c} for c in TEAM_DATA if c != code]
    return sorted(opts, key=lambda o: o["label"])


def get_position_options(player_id, code, match_ids=None):
    """Positions a player appeared in, sorted by minutes desc."""
    if _SWOT_DF.empty or not player_id:
        return []

    df = _SWOT_DF[
        (_SWOT_DF["player_id"] == player_id) & (_SWOT_DF["team_code"] == code)
    ].copy()
    if match_ids:
        df = df[df["match_id"].isin(match_ids)]
    if df.empty:
        return []

    df["pos"] = df.apply(
        lambda r: _get_position(r["Team Formation"], r["Team Player Formation"]), axis=1
    )
    df = df[df["pos"] != ""]

    # Minutes per match from player_stats CSV
    match_minutes: dict = {}
    if not _STATS_DF.empty:
        stats = _STATS_DF[
            (_STATS_DF["player_id"] == player_id) & (_STATS_DF["team_code"] == code)
        ]
        if match_ids:
            stats = stats[stats["match_id"].isin(match_ids)]
        match_minutes = stats.groupby("match_id")["minutes_played"].sum().to_dict()

    pos_minutes: dict = {}
    for mid, grp in df.groupby("match_id"):
        mins      = match_minutes.get(mid, 0)
        positions = grp["pos"].unique()
        per_pos   = mins / max(len(positions), 1)
        for pos in positions:
            pos_minutes[pos] = pos_minutes.get(pos, 0) + per_pos

    return [
        {"label": f"{pos} ({int(mins)} min)", "value": pos}
        for pos, mins in sorted(pos_minutes.items(), key=lambda x: -x[1])
        if pos
    ]


def _filter_swot(player_id, code, match_ids, positions):
    """SWOT rows for a player, optionally filtered to specific positions."""
    if _SWOT_DF.empty or not player_id:
        return pd.DataFrame()
    df = _SWOT_DF[
        (_SWOT_DF["player_id"] == player_id) & (_SWOT_DF["team_code"] == code)
    ].copy()
    if match_ids:
        df = df[df["match_id"].isin(match_ids)]
    if positions:
        df["pos"] = df.apply(
            lambda r: _get_position(r["Team Formation"], r["Team Player Formation"]), axis=1
        )
        df = df[df["pos"].isin(positions)]
    return df


def _zone_val(df, prefix, zone):
    col = f"{prefix}_z{zone}"
    return int(df[col].fillna(0).sum()) if (col in df.columns and not df.empty) else 0


def _zsum(df, prefix, zones):
    return sum(_zone_val(df, prefix, z) for z in zones)


# ══════════════════════════════════════════════════════════════════════════════
# Figure / table builders
# ══════════════════════════════════════════════════════════════════════════════

def _build_heatmap_fig(df, action_type, team_code):
    """18-zone heatmap overlaid on make_pitch_v (attacking direction = up)."""
    prefixes = (
        _ATK_PREFIXES if action_type == "attacking"
        else _DEF_PREFIXES if action_type == "defensive"
        else _ALL_PREFIXES
    )
    zone_counts = {z: sum(_zone_val(df, p, z) for p in prefixes) for z in _ZONES_ALL}
    max_cnt     = max(zone_counts.values()) if any(zone_counts.values()) else 1

    td  = TEAM_DATA.get(team_code, {})
    hex_col = td.get("bg", "#2c5f2e").lstrip("#")
    try:
        r_, g_, b_ = (int(hex_col[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        r_, g_, b_ = 44, 95, 62

    fig = make_pitch_v()

    for z in _ZONES_ALL:
        row = (z - 1) // 3   # 0 = bottom (defensive), 5 = top (attacking)
        col = (z - 1) % 3    # 0 = left, 1 = centre, 2 = right
        x0, x1 = col * _ZONE_W,       (col + 1) * _ZONE_W
        y0, y1 = row * _ZONE_H,       (row + 1) * _ZONE_H
        cnt   = zone_counts.get(z, 0)
        alpha = 0.07 + 0.73 * (cnt / max_cnt) if max_cnt > 0 else 0.07
        tcol  = "white" if alpha > 0.55 else "#333333"

        fig.add_shape(
            type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
            fillcolor=f"rgba({r_},{g_},{b_},{alpha:.2f})",
            line=dict(width=0.5, color="#CCCCCC"), layer="below",
        )
        fig.add_annotation(
            text=str(cnt), x=(x0 + x1) / 2, y=(y0 + y1) / 2,
            xref="x", yref="y", showarrow=False,
            font=dict(size=10, color=tcol),
        )

    fig.add_annotation(
        text="↑ Attacking", x=34, y=109, xref="x", yref="y",
        showarrow=False, font=dict(size=8, color="#888888"), xanchor="center",
    )
    fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                      margin=dict(l=0, r=0, t=14, b=0))
    return fig


def _build_table(df):
    """Actions × (L / C / R / Def3 / Mid3 / Att3) summary table."""
    action_rows = [
        ("Prog. Pass",   [("pp",         _ZONES_ALL)]),
        ("Take-on",      [("to_ttl",     _ZONES_ALL)]),
        ("Cross",        [("cross_ttl",  _ZONES_ALL)]),
        ("Shot",         [("shot",       _ZONES_ALL)]),
        ("Tackle",       [("tackle_ttl", _ZONES_ALL), ("chall", _ZONES_ALL)]),
        ("Interception", [("int",        _ZONES_ALL)]),
        ("Recovery",     [("recovery",   _ZONES_ALL)]),
    ]
    cols_def = [
        ("L",    _ZONES_L),
        ("C",    _ZONES_C),
        ("R",    _ZONES_R),
        ("Def3", _ZONES_DEF3),
        ("Mid3", _ZONES_MID3),
        ("Att3", _ZONES_ATT3),
    ]

    data = []
    for label, prefixes in action_rows:
        row_dict = {"Actions": label}
        for col_label, zones in cols_def:
            row_dict[col_label] = sum(_zsum(df, pfx, zones) for pfx, _ in prefixes)
        data.append(row_dict)

    columns = [{"name": "Actions", "id": "Actions"}] + [
        {"name": c, "id": c} for c, _ in cols_def
    ]
    return dash_table.DataTable(
        data=data,
        columns=columns,
        style_header={**TABLE_STYLE_HEADER, "fontSize": "10px"},
        style_cell={**TABLE_STYLE_CELL,   "fontSize": "10px"},
        style_data=TABLE_STYLE_DATA,
        style_cell_conditional=[
            {"if": {"column_id": "Actions"},
             "textAlign": "left", "width": "80px", "minWidth": "80px", "maxWidth": "80px"},
        ] + [
            {"if": {"column_id": c}, "width": "32px", "minWidth": "32px", "maxWidth": "32px"}
            for c in ["L", "C", "R", "Def3", "Mid3", "Att3"]
        ],
        style_as_list_view=True,
        cell_selectable=False,
        page_action="none",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Public content builders (called from callbacks)
# ══════════════════════════════════════════════════════════════════════════════

def build_paz_col_pitch(code, match_ids, player_id, positions, action_type):
    """Pitch heatmap Graph for one column."""
    if not player_id:
        return html.Div()
    df  = _filter_swot(player_id, code, match_ids or [], positions or [])
    fig = _build_heatmap_fig(df, action_type or "all", code)
    return dcc.Graph(figure=fig, config={"displayModeBar": False},
                     style={"height": "360px"})


def build_paz_col_table(code, match_ids, player_id, positions):
    """Action summary table for one column."""
    if not player_id:
        return html.Div()
    df = _filter_swot(player_id, code, match_ids or [], positions or [])
    return _build_table(df)


def build_paz_selected_list(selected_ids, all_options):
    """Read-only list of currently selected matches (right panel of selector)."""
    lbl = {o["value"]: o["label"] for o in (all_options or [])}
    sel = [m for m in (selected_ids or []) if m in lbl]
    if not sel:
        return [html.Div("No matches selected",
                         style={"padding": "6px 8px", "fontSize": "0.66rem",
                                "color": TEXT_MUTED})]
    return [
        html.Div(lbl[m], style={
            "padding": "3px 8px", "borderBottom": f"1px solid {BORDER}",
            "fontSize": "0.62rem", "color": TEXT_MAIN,
            "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis",
            "background": _ROW_ALT_BG if i % 2 else CARD_BG,
        })
        for i, m in enumerate(sel)
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Layout builders
# ══════════════════════════════════════════════════════════════════════════════

def _build_paz_selector(code, options):
    """70 % match checklist | 30 % selected-matches panel, with preset dropdown."""
    default_ids = [options[0]["value"]] if options else []
    opp_opts    = get_opponent_options(code)
    _list_h     = f"{_SEL_ROWS * _SEL_ROW_H}px"

    _btn    = dict(background="transparent", border=f"1px solid {BORDER}",
                   color=TEXT_MUTED, padding="4px 10px", borderRadius="5px",
                   cursor="pointer", fontSize="0.7rem", fontWeight="500")
    _submit = {**_btn, "background": LALIGA_RED, "border": f"1px solid {LALIGA_RED}",
               "color": "#ffffff", "marginLeft": "auto"}

    left = html.Div([
        dcc.Checklist(
            id={"type": "paz-sel", "team": code},
            options=options, value=default_ids,
            inputStyle={"marginRight": "6px", "cursor": "pointer", "flexShrink": "0"},
            labelStyle={"display": "flex", "alignItems": "center",
                        "padding": "2px 6px", "borderBottom": f"1px solid {BORDER}",
                        "fontSize": "0.68rem", "cursor": "pointer",
                        "color": TEXT_MAIN, "whiteSpace": "nowrap"},
            style={"height": _list_h, "overflowY": "auto", "overflowX": "auto",
                   "background": CARD_BG, "border": f"1px solid {BORDER}",
                   "borderRadius": "5px 5px 0 0"},
        ),
        # ── Footer bar ────────────────────────────────────────────────────────
        html.Div([
            html.Div(id={"type": "paz-count", "team": code},
                     style={"fontSize": "0.68rem", "color": TEXT_MUTED,
                            "alignSelf": "center", "flexShrink": "0"}),
            dcc.Dropdown(
                id={"type": "paz-preset", "team": code},
                options=opp_opts,
                placeholder="Preset: last 5 before…",
                clearable=True,
                style={"width": "200px", "flexShrink": "0", "fontSize": "0.66rem"},
            ),
            html.Button("Select All",   id={"type": "paz-all",    "team": code}, style=_btn),
            html.Button("Unselect All", id={"type": "paz-none",   "team": code}, style=_btn),
            html.Button("Submit",       id={"type": "paz-submit", "team": code},
                        style=_submit, disabled=False),
            html.Button("Reset",        id={"type": "paz-reset",  "team": code}, style=_btn),
        ], style={"display": "flex", "gap": "6px", "alignItems": "center",
                  "padding": "5px 6px", "background": _SEL_HDR_BG,
                  "border": f"1px solid {BORDER}", "borderTop": "none",
                  "borderRadius": "0 0 5px 5px"}),
    ], style={"width": "60%", "flexShrink": "0", "boxSizing": "border-box",
              "paddingRight": "8px"})

    right = html.Div([
        html.Div("Selected Matches", style={
            "fontSize": "0.68rem", "fontWeight": "600", "color": SECONDARY_COL,
            "padding": "4px 8px", "background": _SEL_HDR_BG,
            "border": f"1px solid {BORDER}", "borderRadius": "5px 5px 0 0",
        }),
        html.Div(
            id={"type": "paz-sel-list", "team": code},
            children=build_paz_selected_list(default_ids, options),
            style={"height": _list_h, "overflowY": "auto",
                   "border": f"1px solid {BORDER}", "borderTop": "none",
                   "borderRadius": "0 0 5px 5px"},
        ),
    ], style={"width": "40%", "flexShrink": "0", "boxSizing": "border-box"})

    return html.Div([left, right],
                    style={"display": "flex", "marginBottom": "12px"})


def _build_column(code, col_idx, player_options):
    """Static per-column DOM structure; dynamic parts filled by callbacks."""
    return html.Div([
        # 1. Player dropdown
        dcc.Dropdown(
            id={"type": "paz-player", "team": code, "col": col_idx},
            options=player_options,
            placeholder="–",
            clearable=True,
            style={"fontSize": "0.74rem", "marginBottom": "24px"},
        ),
        # Lower section — hidden until a player is chosen
        html.Div([
            # 2. Position multi-select
            dcc.Dropdown(
                id={"type": "paz-pos", "team": code, "col": col_idx},
                options=[], value=None, multi=True,
                placeholder="All positions",
                style={"fontSize": "0.7rem", "marginBottom": "6px"},
            ),
            # 3. Pitch heatmap container (rebuilt by callback)
            html.Div(id={"type": "paz-pitch", "team": code, "col": col_idx}),
            # 4. Action type selector
            dcc.Dropdown(
                id={"type": "paz-action", "team": code, "col": col_idx},
                options=_ACTION_OPTIONS, value="all", clearable=False,
                style={"fontSize": "0.7rem", "marginTop": "6px", "marginBottom": "4px"},
            ),
            # 5. Summary table container (rebuilt by callback)
            html.Div(id={"type": "paz-table", "team": code, "col": col_idx}),
        ],
        id={"type": "paz-lower", "team": code, "col": col_idx},
        style={"display": "none"}),
    ], style={"flex": "1", "minWidth": "0", "padding": "0 4px", "boxSizing": "border-box"})


def build_player_active_zones_layout(code):
    """Full Player Active Zones tab layout."""
    options, _  = get_match_options(code)
    player_opts = get_player_options(code)
    selector    = _build_paz_selector(code, options)
    columns_row = html.Div(
        [_build_column(code, i, player_opts) for i in range(4)],
        style={"display": "flex", "gap": "0", "alignItems": "flex-start"},
    )
    return html.Div(
        [selector, columns_row],
        style={"backgroundColor": BG_COLOUR, "padding": "4px"},
    )
