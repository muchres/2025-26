"""
Lineup tab — layout and style only.
All data processing is in utils/lineup_data.py.
"""

from collections import defaultdict

import plotly.graph_objects as go
from dash import html, dcc

from utils.constants import (
    CARD_BG, BORDER, TEXT_MAIN, TEXT_MUTED, LALIGA_RED,
    formation_coords, formation_position_mapping,
)
from utils.data_loader import TEAM_DATA
from utils.lineup_data import (
    DISP_NAME,
    POS_ORDER,
    get_match_options,
    prepare_team_data,
    get_default_formation,
    get_predicted_lineup,
    get_squad_sections,
    fmt_formation,
)
from dashboards.pitch import make_pitch_v_bottom

# ── Checklist dimensions ───────────────────────────────────────────────────────
_SEL_ROW_H = 26   # px per checklist row
_SEL_ROWS  = 6    # visible rows before scrolling

# ── Formation table: first 3 rows visible, then scroll ────────────────────────
_F_ROW_H   = 35
_F_SCROLL_H = 3 * _F_ROW_H

# ── Minutes table columns ─────────────────────────────────────────────────────
_COL_WIDTHS  = ["7%", "32%", "14%", "11%", "16%", "10%"]
_COL_HEADERS = ["#", "Player", "Games", "Pos", "Alt Pos", "Mins"]

# ── Colour tokens ─────────────────────────────────────────────────────────────
_SEC_HDR_BG = "#C8C4B8"
_TBL_HDR_BG = "#EEECE3"
_ROW_ALT_BG = "#F5F3EE"
_DEFAULT_HL = "#FFF8E7"


# ═══════════════════════════════════════════════════════════════════════════════
# Pitch
# ═══════════════════════════════════════════════════════════════════════════════

def _build_lineup_pitch(formation, hex1, hext="#FFFFFF", lineup_df=None):
    """
    Overlay predicted lineup on make_pitch_v_bottom().

    Each slot shows the jersey number inside the circle and the player name
    below it. Coordinate transform from formation_coords:
      vert_x = 68 - yc
      vert_y = xc * 1.25
    """
    fig     = make_pitch_v_bottom()
    coords  = formation_coords.get(formation, {})
    pos_map = formation_position_mapping.get(formation, {})

    jersey_by_pos = defaultdict(list)
    name_by_pos   = defaultdict(list)
    if lineup_df is not None and not lineup_df.empty:
        for _, row in lineup_df.iterrows():
            jv   = row["Jersey Number"]
            jstr = str(int(jv)) if (jv is not None and jv == jv) else ""
            pid  = row["player_id"]
            name = DISP_NAME.get(pid, "") if (pid is not None and pid == pid) else ""
            jersey_by_pos[row["pos"]].append(jstr)
            name_by_pos[row["pos"]].append(name)
    pos_cursor = defaultdict(int)

    for slot, (xc, yc) in coords.items():
        pos    = pos_map.get(slot, "")
        idx    = pos_cursor[pos]
        jersey = jersey_by_pos[pos][idx] if idx < len(jersey_by_pos[pos]) else ""
        name   = name_by_pos[pos][idx]   if idx < len(name_by_pos[pos])   else ""
        pos_cursor[pos] += 1

        px_v = 68 - yc
        py_v = xc * 1.25

        fig.add_trace(go.Scatter(
            x=[px_v], y=[py_v],
            mode="markers+text",
            marker=dict(size=36, color=hex1, line=dict(color=hext, width=2)),
            text=[jersey],
            textposition="middle center",
            textfont=dict(color=hext, size=14, family="Arial"),
            showlegend=False,
            hoverinfo="skip",
        ))

        if name:
            fig.add_annotation(
                x=px_v, y=py_v - 2.8,
                text=name,
                showarrow=False,
                font=dict(size=12, color="#333333", family="Arial"),
                xanchor="center",
                yanchor="top",
            )

    return fig


def _render_pitch_area(formation, hex1, hext="#FFFFFF", lineup_df=None):
    title = f"Predicted Formation — {fmt_formation(formation) if formation else '—'}"
    if formation and formation_coords.get(formation):
        fig = _build_lineup_pitch(formation, hex1, hext, lineup_df)
        pitch_block = dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "500px"})
    else:
        pitch_block = html.Div("No formation data for selected matches.",
                               style={"color": TEXT_MUTED, "padding": "20px 0"})

    return html.Div([
        html.H3(title, style={"fontSize": "0.95rem", "fontWeight": "600", "marginBottom": "12px"}),
        pitch_block,
        _build_predicted_lineup_table(lineup_df),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# Formation tables
# ═══════════════════════════════════════════════════════════════════════════════

def _tbl_header_row(labels, widths):
    return html.Div([
        html.Div(lbl, style={
            "width": w, "fontWeight": "700", "padding": "6px 8px",
            "fontSize": "0.78rem", "color": TEXT_MUTED,
        })
        for lbl, w in zip(labels, widths)
    ], style={
        "display": "flex",
        "background": _TBL_HDR_BG,
        "borderBottom": f"1px solid {BORDER}",
    })


def _build_formation_table(formation_df1):
    """Formation counts; scrollable with 3 rows visible. Default row highlighted."""
    header = _tbl_header_row(["Formation", "Matches"], ["55%", "45%"])

    rows = []
    for _, r in formation_df1.iterrows():
        is_default = r["default"] == 1
        bg     = _DEFAULT_HL if is_default else CARD_BG
        weight = "700"       if is_default else "400"
        rows.append(html.Div([
            html.Div(str(r["formation"]), style={
                "width": "55%", "padding": "5px 8px",
                "fontSize": "0.82rem", "fontWeight": weight,
            }),
            html.Div(str(int(r["count"])), style={
                "width": "45%", "padding": "5px 8px", "fontSize": "0.82rem",
            }),
        ], style={
            "display": "flex", "background": bg,
            "borderBottom": f"1px solid {BORDER}",
        }))

    return html.Div([
        header,
        html.Div(rows, style={"overflowY": "auto", "maxHeight": f"{_F_SCROLL_H}px"}),
    ], style={
        "border": f"1px solid {BORDER}", "borderRadius": "5px", "overflow": "hidden",
    })


def _build_two_col_summary_table(header_label, row_defs, formation_summary):
    """Generic 2-column summary table (Backline or Frontline)."""
    fs  = formation_summary.iloc[0] if not formation_summary.empty else None
    hdr = _tbl_header_row([header_label, "Matches"], ["55%", "45%"])
    rows = []
    for i, (label, col) in enumerate(row_defs):
        val = int(fs.get(col, 0)) if fs is not None else 0
        bg  = _ROW_ALT_BG if i % 2 == 1 else CARD_BG
        rows.append(html.Div([
            html.Div(label, style={"width": "55%", "padding": "5px 8px", "fontSize": "0.82rem"}),
            html.Div(str(val), style={"width": "45%", "padding": "5px 8px", "fontSize": "0.82rem"}),
        ], style={"display": "flex", "background": bg, "borderBottom": f"1px solid {BORDER}"}))

    return html.Div([hdr] + rows, style={
        "border": f"1px solid {BORDER}", "borderRadius": "5px", "overflow": "hidden",
    })


def _build_backline_table(formation_summary):
    return _build_two_col_summary_table(
        "Backline",
        [("Back 3", "back3"), ("Back 4", "back4"), ("Back 5", "back5")],
        formation_summary,
    )


def _build_frontline_table(formation_summary):
    return _build_two_col_summary_table(
        "Frontline",
        [("Front 1", "front1"), ("Front 2", "front2"), ("Front 3", "front3")],
        formation_summary,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Minutes played table
# ═══════════════════════════════════════════════════════════════════════════════

def _section_header(label):
    return html.Div(label, style={
        "background":    _SEC_HDR_BG,
        "color":         "#FFFFFF",
        "fontWeight":    "700",
        "padding":       "6px 10px",
        "fontSize":      "0.78rem",
        "letterSpacing": "0.4px",
        "borderBottom":  f"1px solid {BORDER}",
    })


def _player_row(row, alt_bg=False):
    bg      = _ROW_ALT_BG if alt_bg else CARD_BG
    jersey  = int(row["Jersey Number"]) if row.get("Jersey Number") and str(row["Jersey Number"]) != "nan" else "-"
    name    = DISP_NAME.get(row["player_id"], str(row["player_id"]))
    games   = row.get("Games Played") or "0(0)"
    pos     = row.get("Position")     or "-"
    sec_pos = row.get("Secondary Position") or "-"
    mins    = int(row.get("Mins", 0)) if str(row.get("Mins", 0)) != "nan" else 0

    return html.Div([
        html.Div(v, style={
            "width": w, "padding": "5px 8px", "fontSize": "0.82rem",
            "overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap",
        })
        for v, w in zip(
            [str(jersey), name, games, pos, sec_pos, str(mins)],
            _COL_WIDTHS,
        )
    ], style={
        "display": "flex", "background": bg,
        "borderBottom": f"1px solid {BORDER}", "alignItems": "center",
    })


def _minutes_table_header():
    return html.Div([
        html.Div(h, style={
            "width": w, "fontWeight": "700", "padding": "6px 8px",
            "fontSize": "0.78rem", "color": TEXT_MUTED,
        })
        for h, w in zip(_COL_HEADERS, _COL_WIDTHS)
    ], style={
        "display": "flex", "background": _TBL_HDR_BG,
        "borderBottom": f"1px solid {BORDER}",
        "position": "sticky", "top": "0", "zIndex": "1",
    })


def _build_predicted_lineup_table(lineup_df):
    """Pos | # | Player table for the predicted starting XI."""
    if lineup_df is None or lineup_df.empty:
        return html.Div()

    header = html.Div([
        html.Div(h, style={
            "width": w, "fontWeight": "700", "padding": "6px 8px",
            "fontSize": "0.78rem", "color": TEXT_MUTED,
        })
        for h, w in [("Pos", "22%"), ("#", "13%"), ("Player", "65%")]
    ], style={"display": "flex", "background": _TBL_HDR_BG, "borderBottom": f"1px solid {BORDER}"})

    rows = [header]
    for i, (_, r) in enumerate(lineup_df.iterrows()):
        bg  = _ROW_ALT_BG if i % 2 == 1 else CARD_BG
        pid = r["player_id"]
        jv  = r["Jersey Number"]
        jstr = str(int(jv)) if (jv is not None and jv == jv) else "-"
        name = DISP_NAME.get(pid, str(pid)) if (pid is not None and pid == pid) else "-"
        rows.append(html.Div([
            html.Div(str(r["pos"]), style={"width": "22%", "padding": "5px 8px", "fontSize": "0.82rem"}),
            html.Div(jstr,          style={"width": "13%", "padding": "5px 8px", "fontSize": "0.82rem"}),
            html.Div(name,          style={
                "width": "65%", "padding": "5px 8px", "fontSize": "0.82rem",
                "overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap",
            }),
        ], style={
            "display": "flex", "background": bg, "alignItems": "center",
            "borderBottom": f"1px solid {BORDER}",
        }))

    return html.Div([
        html.H3("Predicted Starting XI", style={
            "fontSize": "0.95rem", "fontWeight": "600",
            "marginTop": "16px", "marginBottom": "12px",
        }),
        html.Div(rows, style={
            "border": f"1px solid {BORDER}", "borderRadius": "5px", "overflow": "hidden",
        }),
    ])


def _build_minutes_table(code, all_players):
    """Render the squad minutes table from pre-computed sections."""
    sections = get_squad_sections(code, all_players)
    rows = [_minutes_table_header()]
    for label, df in sections:
        rows.append(_section_header(label))
        for i, (_, player) in enumerate(df.iterrows()):
            rows.append(_player_row(player, alt_bg=(i % 2 == 1)))

    return html.Div(rows, style={
        "border": f"1px solid {BORDER}", "borderRadius": "5px", "overflow": "hidden",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Match selector
# ═══════════════════════════════════════════════════════════════════════════════

def _build_match_selector(code):
    """
    Fixed-height scrollable checklist of team matches with formation info.
    Buttons (Select All / Unselect All / Submit) appear below the checklist.
    Submit is initially enabled (all matches pre-selected) and is disabled via
    callback cb_lineup_submit_disabled when the checklist becomes empty.
    """
    options, all_ids = get_match_options(code)

    _btn = dict(
        background="transparent",
        border=f"1px solid {BORDER}",
        color=TEXT_MUTED,
        padding="5px 12px",
        borderRadius="6px",
        cursor="pointer",
        fontSize="0.78rem",
        fontWeight="500",
    )
    _submit_btn = {
        **_btn,
        "background":  LALIGA_RED,
        "border":      f"1px solid {LALIGA_RED}",
        "color":       "#ffffff",
        "marginLeft":  "auto",
    }

    return html.Div([
        dcc.Checklist(
            id={"type": "lineup-match-sel", "code": code},
            options=options,
            value=all_ids,
            inputStyle={"marginRight": "7px", "cursor": "pointer", "flexShrink": "0"},
            labelStyle={
                "display":    "flex",
                "alignItems": "center",
                "padding":    "3px 8px",
                "borderBottom": f"1px solid {BORDER}",
                "fontSize":   "0.75rem",
                "cursor":     "pointer",
                "color":      TEXT_MAIN,
                "whiteSpace": "nowrap",
            },
            style={
                "height":       f"{_SEL_ROWS * _SEL_ROW_H}px",
                "overflowY":    "auto",
                "overflowX":    "auto",
                "background":   CARD_BG,
                "border":       f"1px solid {BORDER}",
                "borderRadius": "5px 5px 0 0",
            },
        ),
        html.Div([
            html.Button("Select All",   id={"type": "lineup-sel-all",  "code": code}, style=_btn),
            html.Button("Unselect All", id={"type": "lineup-sel-none", "code": code}, style=_btn),
            html.Button("Submit",       id={"type": "lineup-submit",   "code": code},
                        style=_submit_btn, disabled=False),
        ], style={
            "display":        "flex",
            "gap":            "8px",
            "alignItems":     "center",
            "padding":        "6px 8px",
            "background":     _TBL_HDR_BG,
            "border":         f"1px solid {BORDER}",
            "borderTop":      "none",
            "borderRadius":   "0 0 5px 5px",
        }),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# Column renderers
# ═══════════════════════════════════════════════════════════════════════════════

def _render_right_col(code, formation_df1, formation_summary, all_players):
    return html.Div([
        html.Div([
            html.Div(_build_formation_table(formation_df1), style={"flex": "1", "minWidth": "0"}),
            html.Div(_build_backline_table(formation_summary),  style={"flex": "1", "minWidth": "0"}),
            html.Div(_build_frontline_table(formation_summary), style={"flex": "1", "minWidth": "0"}),
        ], style={"display": "flex", "gap": "12px", "marginBottom": "16px"}),
        html.H3("Minutes Played", style={
            "fontSize": "0.95rem", "fontWeight": "600", "marginBottom": "12px",
        }),
        _build_minutes_table(code, all_players),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# Public refresh functions (called by callbacks in app.py)
# ═══════════════════════════════════════════════════════════════════════════════

def build_pitch_content(code, match_ids=None):
    """Recompute and re-render the pitch area for the selected matches."""
    td   = TEAM_DATA.get(code, {})
    hex1 = td.get("bg", "#333333")
    hext = td.get("text", "#FFFFFF")

    formation_df1, _, _, mins = prepare_team_data(code, match_ids)
    formation  = get_default_formation(formation_df1)
    lineup_df  = get_predicted_lineup(formation_df1, mins)
    return _render_pitch_area(formation, hex1, hext, lineup_df)


def build_right_col_content(code, match_ids=None):
    """Recompute and re-render the right column for the selected matches."""
    formation_df1, formation_summary, all_players, _ = prepare_team_data(code, match_ids)
    return _render_right_col(code, formation_df1, formation_summary, all_players)


# ═══════════════════════════════════════════════════════════════════════════════
# Public entry point
# ═══════════════════════════════════════════════════════════════════════════════

def build_lineup_tab(code):
    """
    Full Lineup tab layout (two equal columns).

    Left  — match selector + pitch container (pattern-matched ID)
    Right — formation tables + minutes table (pattern-matched ID)

    The pattern-matched IDs are rebuilt by callbacks on Submit.
    """
    td   = TEAM_DATA.get(code, {})
    hex1 = td.get("bg", "#333333")
    hext = td.get("text", "#FFFFFF")

    formation_df1, formation_summary, all_players, mins = prepare_team_data(code)
    formation = get_default_formation(formation_df1)
    lineup_df = get_predicted_lineup(formation_df1, mins)

    left_col = html.Div([
        _build_match_selector(code),
        html.Div(style={"height": "12px"}),
        html.Div(
            _render_pitch_area(formation, hex1, hext, lineup_df),
            id={"type": "lineup-pitch-area", "code": code},
        ),
    ], style={"flex": "1", "minWidth": "0"})

    right_col = html.Div(
        html.Div(
            _render_right_col(code, formation_df1, formation_summary, all_players),
            id={"type": "lineup-right-area", "code": code},
        ),
        style={"flex": "1", "minWidth": "0"},
    )

    return html.Div([
        html.Div([left_col, right_col], style={
            "display": "flex", "gap": "24px", "alignItems": "flex-start",
        }),
    ])
