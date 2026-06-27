"""Premier League landing page and team detail page."""

from dash import html

from utils.constants import CARD_BG, BORDER, SIDEBAR_BG, TEXT_MAIN, TEXT_MUTED
from utils.epl_data_loader import (
    EPL_ALL_TEAM_CODES, EPL_TEAM_DATA,
    epl_get_team_matches, epl_team_name,
)
from components.ui import page_header, tab_bar, dashed_box, card, back_button, logo_img


# ── Teams grid ────────────────────────────────────────────────────────────────
def _teams_grid():
    return html.Div([
        html.Button(
            [
                html.Img(
                    src=EPL_TEAM_DATA[code]["logo_src"],
                    style={"width": "80px", "height": "80px", "objectFit": "contain"},
                ),
                html.Div(EPL_TEAM_DATA[code]["display"], style={
                    "fontSize":      "1rem",
                    "fontWeight":    "600",
                    "textAlign":     "center",
                    "lineHeight":    "1.3",
                    "marginTop":     "10px",
                    "color":         TEXT_MUTED,
                    "fontFamily":    "'Bebas Neue', sans-serif",
                    "letterSpacing": "1px",
                }),
            ],
            id={"type": "epl-team-card", "code": code},
            style={
                "background":     CARD_BG,
                "border":         f"2px solid {BORDER}",
                "borderRadius":   "10px",
                "minHeight":      "140px",
                "display":        "flex",
                "flexDirection":  "column",
                "alignItems":     "center",
                "justifyContent": "center",
                "cursor":         "pointer",
                "transition":     "all 0.2s",
                "width":          "100%",
                "padding":        "16px 8px",
            },
        )
        for code in EPL_ALL_TEAM_CODES
    ], style={"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": "16px"})


# ── Team banner ───────────────────────────────────────────────────────────────
def _epl_team_banner(code):
    td = EPL_TEAM_DATA.get(code, {
        "display": code, "full_name": code,
        "bg": SIDEBAR_BG, "text": TEXT_MAIN, "b1": BORDER, "b2": BORDER,
    })
    return html.Div([
        html.Div([
            logo_img(code, 90),
            html.Span(td["full_name"].upper(), style={
                "fontFamily": "'Bebas Neue', sans-serif", "fontSize": "2.4rem",
                "letterSpacing": "3px", "color": td["text"], "marginLeft": "20px",
            }),
        ], style={"height": "150px", "background": td["bg"],
                  "display": "flex", "alignItems": "center", "padding": "0 28px"}),
        html.Div(style={"height": "6px", "background": td["b1"]}),
        html.Div(style={"height": "6px", "background": td["b2"]}),
    ], style={"margin": "-28px -28px 24px -28px"})


# ── Page builders ─────────────────────────────────────────────────────────────
def page_premier_league(nav):
    tab_key = nav.get("epl_tab", "teams")
    content = _teams_grid() if tab_key == "teams" else dashed_box()
    return html.Div([
        page_header("PREMIER LEAGUE", "2025/26 Season · England · Top Flight"),
        content,
    ])


def page_epl_team(nav):
    code    = nav.get("epl_team")
    tab_key = nav.get("epl_team_tab", "matches")

    _TABS = [
        ("matches",          "Matches"),
        ("overview",         "Lineup"),
        ("statistics",       "Statistics"),
        ("multiple-matches", "Multiple Matches Analysis"),
    ]
    labels = [label for _, label in _TABS]
    keys   = [k     for k, _    in _TABS]
    active = labels[keys.index(tab_key)] if tab_key in keys else "Matches"

    if tab_key == "matches":
        matches = epl_get_team_matches(code)
        rows = [
            html.Div([
                html.Div(m["date"], style={
                    "width": "100px", "color": TEXT_MUTED, "fontSize": "0.78rem", "flexShrink": "0",
                }),
                html.Div([
                    html.Span(epl_team_name(m["home"]), style={
                        "fontSize":   "0.85rem",
                        "fontWeight": "900" if m["home"] == code else "300",
                        "color":      TEXT_MAIN if m["home"] == code else "#888888",
                    }),
                    logo_img(m["home"], 26),
                ], style={"flex": "1", "display": "flex", "alignItems": "center",
                          "justifyContent": "flex-end", "gap": "6px"}),
                html.Button(
                    m["score"],
                    id={"type": "match-row", "match_id": m["id"]},
                    style={
                        "background": CARD_BG, "border": f"1px solid {BORDER}",
                        "color": TEXT_MAIN, "padding": "3px 12px", "borderRadius": "6px",
                        "cursor": "pointer", "fontSize": "0.85rem", "fontWeight": "400",
                        "width": "80px", "margin": "0 8px", "flexShrink": "0",
                    },
                ),
                html.Div([
                    logo_img(m["away"], 26),
                    html.Span(epl_team_name(m["away"]), style={
                        "fontSize":   "0.85rem",
                        "fontWeight": "900" if m["away"] == code else "300",
                        "color":      TEXT_MAIN if m["away"] == code else "#888888",
                    }),
                ], style={"flex": "1", "display": "flex", "alignItems": "center", "gap": "6px"}),
            ], style={
                "display": "flex", "alignItems": "center",
                "padding": "10px 12px", "borderBottom": f"1px solid {BORDER}", "gap": "8px",
            })
            for m in matches
        ]
        content = html.Div([
            html.H3("All Matches", style={"fontSize": "1rem", "fontWeight": "600", "marginBottom": "16px"}),
            card(rows or [html.P("No matches found.", style={"color": TEXT_MUTED})]),
        ])
    else:
        content = dashed_box()

    return html.Div([
        _epl_team_banner(code),
        back_button("← Back to Team Selection", "epl-teams"),
        tab_bar(labels, active, "epl-team-tab"),
        content,
    ])
