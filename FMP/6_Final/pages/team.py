"""Team page: banner, tabbed sections, and matches list."""

from dash import html

from utils.constants import LALIGA_RED, SIDEBAR_BG, CARD_BG, BORDER, TEXT_MAIN, TEXT_MUTED
from utils.data_loader import TEAM_DATA, get_team_matches, team_name
from components.ui import card, back_button, tab_bar, logo_img, dashed_box
from pages.lineup import build_lineup_tab
from dashboards.multi_match_report import build_multi_match_layout
from dashboards.set_piece_analysis import build_set_piece_layout
from dashboards.statistics import build_statistics_layout
from dashboards.player_active_zones import build_player_active_zones_layout


def _result_color(m, code):
    home, away = m["score"].split("-")
    hg, ag = int(home), int(away)
    if hg == ag:
        return "#D0D0D0"
    won = (m["home"] == code and hg > ag) or (m["away"] == code and ag > hg)
    return "#25ef58" if won else "#f85b5b"


def team_banner(code):
    td = TEAM_DATA.get(code, {"display": code, "full_name": code, "bg": SIDEBAR_BG,
                              "text": TEXT_MAIN, "b1": BORDER, "b2": BORDER})
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


def page_team(nav):
    code    = nav.get("team")
    tab_key = nav.get("team_tab", "matches")

    _TABS = [
        ("matches",              "Matches"),
        ("statistics",           "Tactical Profile"),
        ("overview",             "Lineup"),
        ("multiple-matches",     "Multiple Matches Analysis"),
        ("set-pieces",           "Set Piece Analysis"),
        ("player-active-zones",  "Player Active Zones"),
    ]
    labels = [label for _, label in _TABS]
    keys   = [k     for k, _    in _TABS]
    active = labels[keys.index(tab_key)] if tab_key in keys else "Matches"

    if tab_key == "matches":
        matches = get_team_matches(code)
        rows = [
            html.Div([
                html.Div(m["date"], style={
                    "width": "100px", "color": TEXT_MUTED, "fontSize": "0.78rem", "flexShrink": "0",
                }),
                html.Div([
                    html.Span(team_name(m["home"]), style={
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
                        "background": _result_color(m, code), "border": f"1px solid {BORDER}", "color": 'TEXT_MAIN',
                        "padding": "3px 12px", "borderRadius": "6px", "cursor": "pointer",
                        "fontSize": "0.85rem", "fontWeight": "400", "width": "80px",
                        "margin": "0 8px", "flexShrink": "0",
                    }
                ),
                html.Div([
                    logo_img(m["away"], 26),
                    html.Span(team_name(m["away"]), style={
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
    elif tab_key == "statistics":
        content = build_statistics_layout(code)
    elif tab_key == "overview":
        content = build_lineup_tab(code)
    elif tab_key == "multiple-matches":
        content = build_multi_match_layout(code)
    elif tab_key == "set-pieces":
        content = build_set_piece_layout(code)
    elif tab_key == "player-active-zones":
        content = build_player_active_zones_layout(code)
    else:
        content = dashed_box()

    return html.Div([
        team_banner(code),
        back_button("← Back to Team Selection", "teams"),
        tab_bar(labels, active, "team-tab"),
        content,
    ])
