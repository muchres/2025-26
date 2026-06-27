"""
Sports Analytics Dashboard — 2025/26  (entry point)

Run from inside the 6_Final/ folder:

    python app.py

Architecture: all navigation callbacks use pattern-matched IDs so they are
always registered, even when the matched components are not in the current
layout.  Static-ID inputs are limited to components that live permanently in
the layout (store-nav, store-sidebar, sidebar, toggle-sidebar, page-content).

The heavy lifting lives in packages:
    utils/       constants, helpers, data loading
    components/  reusable UI + sidebar
    pages/       laliga / team / match page builders
    dashboards/  pitch geometry + the match-analysis dashboard
"""

import json

import dash
from dash import dcc, html, Input, Output, State, callback_context, no_update, ALL, MATCH
import dash_bootstrap_components as dbc
from flask import send_from_directory

from utils.constants import (
    LALIGA_LOGO_DIR, LOGOS_ROOT, EPL_LOGO_DIR, SIDEBAR_BG, CARD_BG, BORDER, TEXT_MAIN, TEXT_MUTED,
)
from components.sidebar import (
    sidebar_inner_content, SIDEBAR_EXPANDED_STYLE, SIDEBAR_COLLAPSED_STYLE,
)
from components.ui import placeholder_page
from pages.laliga import page_laliga
from pages.team import page_team
from pages.match import page_match
from pages.premier_league import page_premier_league, page_epl_team
from pages.lineup import build_pitch_content, build_right_col_content
from dashboards.multi_match_report import (
    build_multi_match_body, build_mm_row2, build_mm_minutes, build_mm_pitch,
    _MM_MAX, get_preset_matches,
)
from dashboards.player_active_zones import (
    get_position_options, build_paz_col_pitch, build_paz_col_table,
    build_paz_selected_list,
)
from utils.lineup_data import get_match_options

# ── App init ──────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap",
    ],
    suppress_callback_exceptions=True,
)
app.title = "Game Analysis | 2025/26"

# ── Asset serving ─────────────────────────────────────────────────────────────
@app.server.route("/logos/<path:filename>")
def serve_logo(filename):
    return send_from_directory(LALIGA_LOGO_DIR, filename)

@app.server.route("/epl-logos/<path:filename>")
def serve_epl_logo(filename):
    return send_from_directory(EPL_LOGO_DIR, filename)

@app.server.route("/site-logos/<path:filename>")
def serve_site_logo(filename):
    return send_from_directory(LOGOS_ROOT, filename)

# ── Navigation store schema ───────────────────────────────────────────────────
NAV_INIT = {
    "page":         "laliga",   # laliga | team | match | premier-league | premier-league-team | wsl | ucl | match-analysis | player-matchup
    "laliga_tab":   "teams",    # teams | team-statistics | player-statistics
    "team":         None,       # LaLiga team_code (e.g. "RMA")
    "team_tab":     "matches",  # matches | overview | statistics | multiple-matches
    "match":        None,       # match_id string
    "epl_tab":      "teams",    # teams | team-statistics | player-statistics
    "epl_team":     None,       # EPL team_code (e.g. "ARS")
    "epl_team_tab": "matches",  # matches | overview | statistics | multiple-matches
}

# ── Layout roots ──────────────────────────────────────────────────────────────
ROOT_STYLE = {
    "fontFamily": "'DM Sans', sans-serif", "background": CARD_BG,
    "color": TEXT_MAIN, "height": "100vh", "display": "flex", "overflow": "hidden",
}
MAIN_STYLE = {
    "flex": "1", "minWidth": "0", "display": "flex", "flexDirection": "column",
    "overflow": "hidden", "background": CARD_BG,
}
CONTENT_STYLE = {"flex": "1", "overflowY": "auto", "padding": "28px"}

# ── Layout — only permanent components here ───────────────────────────────────
app.layout = html.Div([
    # Permanent stores
    dcc.Store(id="store-nav",     data=NAV_INIT),
    dcc.Store(id="store-sidebar", data=False),

    # Sidebar (logo + nav links; toggle button is outside)
    html.Div([
        html.Div(sidebar_inner_content(False), id="sidebar-inner"),
    ], id="sidebar", style=SIDEBAR_COLLAPSED_STYLE),

    # Main content area
    html.Div(
        html.Div(id="page-content", style=CONTENT_STYLE),
        style=MAIN_STYLE,
    ),

    # Sidebar toggle — fixed, always in DOM
    html.Button("▶", id="toggle-sidebar", style={
        "position": "fixed", "bottom": "0", "left": "0", "zIndex": "1000",
        "background": SIDEBAR_BG, "border": f"1px solid {BORDER}",
        "borderLeft": "none", "borderBottom": "none",
        "color": TEXT_MUTED, "padding": "8px 14px", "cursor": "pointer",
        "fontSize": "0.75rem", "borderRadius": "0 6px 0 0",
    }),
], style=ROOT_STYLE)


# ═══════════════════════════════════════════════════════════════════════════════
# Callbacks
#
# Rule: every Input must reference either
#   (a) a component that is permanently in app.layout, OR
#   (b) a pattern-matched ID (ALL / MATCH) — these are always registered and
#       receive [] when no matching components exist in the current layout.
#
# store-nav is the single source of navigation truth.
# cb_nav_page is the primary owner (no allow_duplicate).
# All other navigation callbacks use allow_duplicate=True.
# ═══════════════════════════════════════════════════════════════════════════════

# ── CB-1: Sidebar collapse / expand ───────────────────────────────────────────
@app.callback(
    Output("store-sidebar",  "data"),
    Output("sidebar",        "style"),
    Output("sidebar-inner",  "children"),
    Output("toggle-sidebar", "children"),
    Input("toggle-sidebar",  "n_clicks"),
    State("store-sidebar",   "data"),
    prevent_initial_call=True,
)
def cb_sidebar_toggle(_, is_expanded):
    new = not is_expanded
    return (
        new,
        SIDEBAR_EXPANDED_STYLE if new else SIDEBAR_COLLAPSED_STYLE,
        sidebar_inner_content(new),
        "◀" if new else "▶",
    )


# ── CB-2: Sidebar navigation (primary owner of store-nav) ─────────────────────
@app.callback(
    Output("store-nav", "data"),
    Input({"type": "nav-btn", "page": ALL}, "n_clicks"),
    State("store-nav", "data"),
    prevent_initial_call=True,
)
def cb_nav_page(_, nav):
    ctx = callback_context
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    page = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])["page"]
    return {**nav, "page": page, "team": None, "match": None,
            "laliga_tab": "teams", "team_tab": "matches",
            "epl_team": None, "epl_tab": "teams", "epl_team_tab": "matches"}


# ── CB-3: LaLiga tab selection ────────────────────────────────────────────────
@app.callback(
    Output("store-nav", "data", allow_duplicate=True),
    Input({"type": "laliga-tab", "tab": ALL}, "n_clicks"),
    State("store-nav", "data"),
    prevent_initial_call=True,
)
def cb_laliga_tab(_, nav):
    ctx = callback_context
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    label = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])["tab"]
    _MAP  = {"Teams": "teams", "Team Statistics": "team-statistics",
             "Player Statistics": "player-statistics"}
    return {**nav, "laliga_tab": _MAP.get(label, "teams")}


# ── CB-4: Team selection ──────────────────────────────────────────────────────
@app.callback(
    Output("store-nav", "data", allow_duplicate=True),
    Input({"type": "team-card", "code": ALL}, "n_clicks"),
    State("store-nav", "data"),
    prevent_initial_call=True,
)
def cb_team_select(_, nav):
    ctx = callback_context
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    code = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])["code"]
    return {**nav, "page": "team", "team": code, "team_tab": "matches", "match": None}


# ── CB-5: Team tab selection ──────────────────────────────────────────────────
@app.callback(
    Output("store-nav", "data", allow_duplicate=True),
    Input({"type": "team-tab", "tab": ALL}, "n_clicks"),
    State("store-nav", "data"),
    prevent_initial_call=True,
)
def cb_team_tab(_, nav):
    ctx = callback_context
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    label = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])["tab"]
    _MAP  = {"Matches": "matches", "Lineup": "overview",
             "Tactical Profile": "statistics", "Multiple Matches Analysis": "multiple-matches",
             "Set Piece Analysis": "set-pieces", "Player Active Zones": "player-active-zones"}
    return {**nav, "team_tab": _MAP.get(label, "matches")}


# ── CB-6: Match selection ─────────────────────────────────────────────────────
@app.callback(
    Output("store-nav", "data", allow_duplicate=True),
    Input({"type": "match-row", "match_id": ALL}, "n_clicks"),
    State("store-nav", "data"),
    prevent_initial_call=True,
)
def cb_match_select(_, nav):
    ctx = callback_context
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    match_id = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])["match_id"]
    return {**nav, "page": "match", "match": match_id}


# ── CB-7: Back navigation ─────────────────────────────────────────────────────
@app.callback(
    Output("store-nav", "data", allow_duplicate=True),
    Input({"type": "back-btn", "action": ALL}, "n_clicks"),
    State("store-nav", "data"),
    prevent_initial_call=True,
)
def cb_back_nav(_, nav):
    ctx = callback_context
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    action = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])["action"]
    if action == "teams":
        return {**nav, "page": "laliga", "team": None,
                "laliga_tab": "teams", "team_tab": "matches"}
    if action == "matches":
        # Route back to EPL or LaLiga team page based on which team is active
        if nav.get("epl_team"):
            return {**nav, "page": "premier-league-team", "match": None, "epl_team_tab": "matches"}
        return {**nav, "page": "team", "match": None, "team_tab": "matches"}
    if action == "epl-teams":
        return {**nav, "page": "premier-league", "epl_team": None,
                "epl_tab": "teams", "epl_team_tab": "matches"}
    return no_update


# ── CB-9: EPL tab selection ───────────────────────────────────────────────────
@app.callback(
    Output("store-nav", "data", allow_duplicate=True),
    Input({"type": "epl-tab", "tab": ALL}, "n_clicks"),
    State("store-nav", "data"),
    prevent_initial_call=True,
)
def cb_epl_tab(_, nav):
    ctx = callback_context
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    label = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])["tab"]
    _MAP  = {"Teams": "teams", "Team Statistics": "team-statistics",
             "Player Statistics": "player-statistics"}
    return {**nav, "epl_tab": _MAP.get(label, "teams")}


# ── CB-10: EPL team card selection ────────────────────────────────────────────
@app.callback(
    Output("store-nav", "data", allow_duplicate=True),
    Input({"type": "epl-team-card", "code": ALL}, "n_clicks"),
    State("store-nav", "data"),
    prevent_initial_call=True,
)
def cb_epl_team_select(_, nav):
    ctx = callback_context
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    code = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])["code"]
    return {**nav, "page": "premier-league-team", "epl_team": code,
            "epl_team_tab": "matches", "match": None}


# ── CB-11: EPL team tab selection ─────────────────────────────────────────────
@app.callback(
    Output("store-nav", "data", allow_duplicate=True),
    Input({"type": "epl-team-tab", "tab": ALL}, "n_clicks"),
    State("store-nav", "data"),
    prevent_initial_call=True,
)
def cb_epl_team_tab(_, nav):
    ctx = callback_context
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return no_update
    label = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])["tab"]
    _MAP  = {"Matches": "matches", "Lineup": "overview",
             "Statistics": "statistics", "Multiple Matches Analysis": "multiple-matches"}
    return {**nav, "epl_team_tab": _MAP.get(label, "matches")}


# ── CB-8: Page renderer ───────────────────────────────────────────────────────
# Reads store-nav (always present) and renders the appropriate page.
# This is the ONLY callback that writes to page-content.
@app.callback(
    Output("page-content", "children"),
    Input("store-nav", "data"),
)
def cb_render(nav):
    page = nav.get("page", "laliga")

    if page == "team" and nav.get("team"):
        return page_team(nav)
    if page == "match" and nav.get("match"):
        return page_match(nav)
    if page == "premier-league":
        return page_premier_league(nav)
    if page == "premier-league-team" and nav.get("epl_team"):
        return page_epl_team(nav)
    if page == "wsl":
        return placeholder_page("Women's Super League", "England · 2025/26")
    if page == "ucl":
        return placeholder_page("Champions League", "UEFA · 2025/26")
    if page == "match-analysis":
        return placeholder_page("Match Analysis", "Cross-competition match reports")
    if page == "player-matchup":
        return placeholder_page("Player Positional Matchup", "Head-to-head positional analysis")
    return page_laliga(nav)


# ── Global CSS ────────────────────────────────────────────────────────────────
app.index_string = '''
<!DOCTYPE html>
<html>
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
{%css%}
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #FAF9F6; overflow: hidden; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #EEECE3; }
::-webkit-scrollbar-thumb { background: #BCB6A3; border-radius: 3px; }
</style>
</head>
<body>
{%app_entry%}
<footer>
{%config%}
{%scripts%}
{%renderer%}
</footer>
</body>
</html>'''

# ── CB-12: Lineup — disable Submit when no matches selected ───────────────────
@app.callback(
    Output({"type": "lineup-submit", "code": MATCH}, "disabled"),
    Input({"type": "lineup-match-sel", "code": MATCH}, "value"),
)
def cb_lineup_submit_disabled(value):
    return not bool(value)


# ── CB-13: Lineup — Select All ────────────────────────────────────────────────
@app.callback(
    Output({"type": "lineup-match-sel", "code": MATCH}, "value"),
    Input({"type": "lineup-sel-all",   "code": MATCH}, "n_clicks"),
    State({"type": "lineup-match-sel", "code": MATCH}, "options"),
    prevent_initial_call=True,
)
def cb_lineup_select_all(_, options):
    return [o["value"] for o in options] if options else []


# ── CB-14: Lineup — Unselect All ──────────────────────────────────────────────
@app.callback(
    Output({"type": "lineup-match-sel", "code": MATCH}, "value", allow_duplicate=True),
    Input({"type": "lineup-sel-none",  "code": MATCH}, "n_clicks"),
    prevent_initial_call=True,
)
def cb_lineup_unselect_all(_):
    return []


# ── CB-15: Lineup — Submit (filter by selected matches) ───────────────────────
@app.callback(
    Output({"type": "lineup-pitch-area",  "code": MATCH}, "children"),
    Output({"type": "lineup-right-area",  "code": MATCH}, "children"),
    Input({"type": "lineup-submit",       "code": MATCH}, "n_clicks"),
    State({"type": "lineup-match-sel",    "code": MATCH}, "value"),
    prevent_initial_call=True,
)
def cb_lineup_submit(_, selected_ids):
    code      = callback_context.triggered_id["code"]
    match_ids = selected_ids if selected_ids else None
    return (
        build_pitch_content(code, match_ids),
        build_right_col_content(code, match_ids),
    )


# ── CB-A: Multi-match — Unselect All ──────────────────────────────────────────
@app.callback(
    Output({"type": "mm-sel", "team": MATCH}, "value", allow_duplicate=True),
    Input({"type": "mm-none", "team": MATCH}, "n_clicks"),
    prevent_initial_call=True,
)
def cb_mm_unselect_all(_):
    return []


# ── CB-B: Multi-match — Preset (last 5 before latest meeting with opponent) ───
@app.callback(
    Output({"type": "mm-sel", "team": MATCH}, "value", allow_duplicate=True),
    Input({"type": "mm-preset", "team": MATCH}, "value"),
    prevent_initial_call=True,
)
def cb_mm_preset(opp_code):
    if not opp_code:
        return no_update
    code = callback_context.triggered_id["team"]
    match_ids = get_preset_matches(code, opp_code)
    if not match_ids:
        return no_update
    return match_ids


# ── CB-C: Multi-match — selection count + Submit enable/disable ────────────────
@app.callback(
    Output({"type": "mm-count",  "team": MATCH}, "children"),
    Output({"type": "mm-submit", "team": MATCH}, "disabled"),
    Input({"type": "mm-sel",     "team": MATCH}, "value"),
    prevent_initial_call=False,
)
def cb_mm_count(selected_ids):
    n = len(selected_ids or [])
    too_many = n > _MM_MAX
    invalid  = (n == 0) or too_many
    if too_many:
        label = f"{n} selected — max {_MM_MAX}"
    else:
        label = f"{n} / {_MM_MAX} selected"
    return label, invalid


# ── CB-D: Multi-match — Submit (rebuild lineup, minutes, body) ────────────────
@app.callback(
    Output({"type": "mm-row2",    "team": MATCH}, "children"),
    Output({"type": "mm-minutes", "team": MATCH}, "children"),
    Output({"type": "mm-body",    "team": MATCH}, "children"),
    Output({"type": "mm-unavail", "team": MATCH}, "value"),
    Input({"type": "mm-submit",   "team": MATCH}, "n_clicks"),
    State({"type": "mm-sel",      "team": MATCH}, "value"),
    prevent_initial_call=True,
)
def cb_mm_submit(_, selected_ids):
    code      = callback_context.triggered_id["team"]
    match_ids = (selected_ids or [])[:_MM_MAX]
    if not match_ids:
        return no_update, no_update, no_update, no_update
    return (
        build_mm_row2(code, match_ids),
        build_mm_minutes(code, match_ids),
        build_multi_match_body(code, match_ids),
        [],
    )


# ── CB-E: Multi-match — Unavailable players → update pitch only ───────────────
@app.callback(
    Output({"type": "mm-pitch",    "team": MATCH}, "children"),
    Input({"type":  "mm-unavail",  "team": MATCH}, "value"),
    State({"type":  "mm-sel",      "team": MATCH}, "value"),
    prevent_initial_call=True,
)
def cb_mm_unavail(unavailable_ids, selected_ids):
    code      = callback_context.triggered_id["team"]
    match_ids = (selected_ids or [])[:_MM_MAX]
    if not match_ids:
        return no_update
    return build_mm_pitch(code, match_ids, unavailable_ids=unavailable_ids or [])


# ── CB-PAZ-0: Player Active Zones — Select All / Unselect All ────────────────
@app.callback(
    Output({"type": "paz-sel",  "team": MATCH}, "value", allow_duplicate=True),
    Input({"type": "paz-all",   "team": MATCH}, "n_clicks"),
    State({"type": "paz-sel",   "team": MATCH}, "options"),
    prevent_initial_call=True,
)
def cb_paz_select_all(_, options):
    return [o["value"] for o in options] if options else []


@app.callback(
    Output({"type": "paz-sel",   "team": MATCH}, "value", allow_duplicate=True),
    Input({"type":  "paz-none",  "team": MATCH}, "n_clicks"),
    prevent_initial_call=True,
)
def cb_paz_unselect_all(_):
    return []


# ── CB-PAZ-1: Player Active Zones — preset → fill checklist ─────────────────
@app.callback(
    Output({"type": "paz-sel",    "team": MATCH}, "value", allow_duplicate=True),
    Input({"type": "paz-preset",  "team": MATCH}, "value"),
    prevent_initial_call=True,
)
def cb_paz_preset(opp_code):
    if not opp_code:
        return no_update
    code      = callback_context.triggered_id["team"]
    match_ids = get_preset_matches(code, opp_code)
    return match_ids if match_ids else no_update


# ── CB-PAZ-2: Player Active Zones — match count label ────────────────────────
@app.callback(
    Output({"type": "paz-count", "team": MATCH}, "children"),
    Input({"type": "paz-sel",    "team": MATCH}, "value"),
)
def cb_paz_count(selected):
    return f"{len(selected or [])} selected"


# ── CB-PAZ-3: Player Active Zones — live selected-matches panel ───────────────
@app.callback(
    Output({"type": "paz-sel-list", "team": MATCH}, "children"),
    Input({"type": "paz-sel",       "team": MATCH}, "value"),
    State({"type": "paz-sel",       "team": MATCH}, "options"),
)
def cb_paz_sel_list(selected_ids, options):
    return build_paz_selected_list(selected_ids, options)


# ── CB-PAZ-R: Player Active Zones — Reset (clear all player dropdowns) ───────
@app.callback(
    Output({"type": "paz-player", "team": MATCH, "col": ALL}, "value"),
    Input({"type": "paz-reset",   "team": MATCH}, "n_clicks"),
    prevent_initial_call=True,
)
def cb_paz_reset(_):
    return [None, None, None, None]


# ── CB-PAZ-4: Player Active Zones — player → position options + visibility ────
@app.callback(
    Output({"type": "paz-pos",   "team": MATCH, "col": ALL}, "options"),
    Output({"type": "paz-pos",   "team": MATCH, "col": ALL}, "value"),
    Output({"type": "paz-lower", "team": MATCH, "col": ALL}, "style"),
    Input({"type": "paz-player", "team": MATCH, "col": ALL}, "value"),
    State({"type": "paz-sel",    "team": MATCH}, "value"),
)
def cb_paz_player(players, match_ids):
    code = callback_context.triggered_id["team"] if isinstance(callback_context.triggered_id, dict) else None
    opts_list, vals_list, styles_list = [], [], []
    for pid in (players or []):
        if pid and code:
            pos_opts = get_position_options(pid, code, match_ids)
            opts_list.append(pos_opts)
            vals_list.append(None)
            styles_list.append({"display": "block"})
        else:
            opts_list.append([])
            vals_list.append(None)
            styles_list.append({"display": "none"})
    return opts_list, vals_list, styles_list


# ── CB-PAZ-5: Player Active Zones — submit → refresh position options ─────────
@app.callback(
    Output({"type": "paz-pos",    "team": MATCH, "col": ALL}, "options",
           allow_duplicate=True),
    Input({"type": "paz-submit",  "team": MATCH}, "n_clicks"),
    State({"type": "paz-player",  "team": MATCH, "col": ALL}, "value"),
    State({"type": "paz-sel",     "team": MATCH}, "value"),
    prevent_initial_call=True,
)
def cb_paz_submit_pos(_, players, match_ids):
    code = callback_context.triggered_id["team"]
    return [
        get_position_options(pid, code, match_ids) if pid else []
        for pid in (players or [])
    ]


# ── CB-PAZ-6: Player Active Zones — rebuild pitch + table ────────────────────
@app.callback(
    Output({"type": "paz-pitch",  "team": MATCH, "col": ALL}, "children"),
    Output({"type": "paz-table",  "team": MATCH, "col": ALL}, "children"),
    Input({"type": "paz-pos",     "team": MATCH, "col": ALL}, "value"),
    Input({"type": "paz-action",  "team": MATCH, "col": ALL}, "value"),
    Input({"type": "paz-submit",  "team": MATCH}, "n_clicks"),
    State({"type": "paz-sel",     "team": MATCH}, "value"),
    State({"type": "paz-player",  "team": MATCH, "col": ALL}, "value"),
    prevent_initial_call=True,
)
def cb_paz_chart(pos_vals, action_vals, _submit, match_ids, players):
    code    = callback_context.triggered_id["team"]
    pitches, tables = [], []
    for i, pid in enumerate(players or []):
        positions   = pos_vals[i]   if pos_vals   and i < len(pos_vals)   else None
        action_type = action_vals[i] if action_vals and i < len(action_vals) else "all"
        pitches.append(build_paz_col_pitch(code, match_ids, pid, positions, action_type))
        tables.append(build_paz_col_table(code, match_ids, pid, positions))
    return pitches, tables


if __name__ == "__main__":
    app.run(debug=True, port=8050)
