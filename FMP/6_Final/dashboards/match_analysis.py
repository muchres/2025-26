"""
Match-analysis dashboard.

`build_match_analysis_layout()` loads a single match's event data, builds every
figure (starting XI, momentum, pass network, progressive passes, final-third
entries, shot map, receive heatmaps) and returns a self-contained Dash layout
(an html.Div) ready to drop into the main app's page-content.

Static styling/helpers live at module level; everything data-dependent lives
inside the build function so it runs fresh per match.
"""

import base64
import math
import os
import re
from itertools import combinations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc, dash_table

from utils.constants import (
    BG_COLOUR, PRIMARY_COL, SECONDARY_COL, TERTIARY_COL, SIDEBAR_BG, BORDER,
    ROW_H, ATT_X0, ATT_MIDX, LW_SPLIT, RW_SPLIT,
    KEY_ZONES, ARROW_COLORS, GOAL_X, GOAL_Y, MAX_DIST, POS_ORDER,
    formation_position_mapping,
    MATCH_DEFAULT_CSV, MATCH_PLAYERS_CSV, MATCH_TEAMS_CSV, MATCH_LOGO_DIR,
    EPL_DATA_DIR, EPL_PLAYERS_CSV,
    LALIGA_DATA_DIR, LALIGA_PLAYERS_CSV, LALIGA_TEAMS_CSV, LALIGA_MATCH_LOGO_DIR,
)
from utils.helpers import rgba
from dashboards.pitch import (
    make_pitch5, make_pitch_v, make_pitch4, make_pitch_zones_v2,
    make_pitch_simple, make_pitch_30zones, get_zone,
    make_pitch_v_top, make_pitch_v_top_zones,
)
from dashboards.carry_progressive import build_carry_df

# ── Table styles ──────────────────────────────────────────────────────────────
TABLE_STYLE_HEADER = {
    "backgroundColor": PRIMARY_COL, "color": SECONDARY_COL, "fontWeight": "600",
    "fontSize": "11px", "textAlign": "center", "padding": "2px",
    "border": "none", "letterSpacing": "0.2px",
}
TABLE_STYLE_CELL = {
    "backgroundColor": "white", "color": SECONDARY_COL, "fontSize": "11px",
    "fontFamily": "Inter, Segoe UI, Arial", "textAlign": "center",
    "border": "none", "whiteSpace": "nowrap", "height": "12px",
    "padding": "1px 2px", "lineHeight": "12px",
}
TABLE_STYLE_DATA = {
    "borderTop": f"1px solid {TERTIARY_COL}", "borderBottom": f"1px solid {TERTIARY_COL}",
    "borderLeft": f"1px solid {TERTIARY_COL}", "borderRight": f"1px solid {TERTIARY_COL}",
}

LINEUP_ROW_H_PX = 20
LINEUP_CSS = [
    {"selector": "tr", "rule": f"height: {LINEUP_ROW_H_PX}px !important; min-height: unset !important;"},
    {"selector": "td", "rule": f"padding-top: 1px !important; padding-bottom: 1px !important; line-height: {LINEUP_ROW_H_PX}px !important;"},
]

_NARROW = "36px"
_SUB_W  = "48px"
_GOAL_W = "72px"
LINEUP_COL_WIDTHS = (
    [{"if": {"column_id": c},
      "width": _NARROW, "minWidth": _NARROW, "maxWidth": _NARROW, "textAlign": "center",
      "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis"}
     for c in ["Pos", "No.", "🟨", "🟨🟥", "🟥"]]
    + [{"if": {"column_id": "Sub"},
        "width": _SUB_W, "minWidth": _SUB_W, "maxWidth": _SUB_W, "textAlign": "center",
        "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis"}]
    + [{"if": {"column_id": "Goal"},
        "width": _GOAL_W, "minWidth": _GOAL_W, "maxWidth": _GOAL_W, "textAlign": "center",
        "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis"}]
    + [{"if": {"column_id": "Player Name"}, "minWidth": "88px"}]
)

LINEUP_SUB_COLORS = [
    {"if": {"filter_query": '{Pos} = "Sub"', "column_id": "Sub"},
     "color": "#27AE60", "fontWeight": "600"},
    {"if": {"filter_query": '{Pos} != "Sub" && {Sub} != ""', "column_id": "Sub"},
     "color": "#E74C3C", "fontWeight": "600"},
    {"if": {"filter_query": '{Goal} contains "(OG)"', "column_id": "Goal"},
     "color": "#E74C3C", "fontWeight": "600"},
    {"if": {"filter_query": '{Pos} = "Sub"', "column_id": "Pos"},
     "color": "#aaaaaa"},
    {"if": {"filter_query": '{Pos} = "Sub"', "column_id": "No."},
     "color": "#aaaaaa"},
    {"if": {"filter_query": '{Pos} = "Sub"', "column_id": "Player Name"},
     "color": "#aaaaaa"},
]


# ── Layout helpers ────────────────────────────────────────────────────────────
def make_section_label(text):
    return html.Div(
        text,
        style={
            "fontSize": "14px", "fontWeight": "600", "color": SECONDARY_COL,
            "fontFamily": "Inter, Segoe UI, Arial", "backgroundColor": PRIMARY_COL,
            "padding": "6px 5px", "letterSpacing": "0.3px", "flexShrink": "0",
            "display": "flex", "alignItems": "center", "justifyContent": "center",
        }
    )


def make_table(df, height_px=None, style_cell_conditional=None,
               style_data_conditional=None, css=None):
    style_table = {"overflowX": "auto"}
    if height_px:
        style_table["height"] = f"{height_px}px"
        style_table["overflowY"] = "auto"
    return dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        style_table=style_table,
        style_header=TABLE_STYLE_HEADER,
        style_cell=TABLE_STYLE_CELL,
        style_data=TABLE_STYLE_DATA,
        style_cell_conditional=style_cell_conditional or [],
        style_data_conditional=style_data_conditional or [],
        css=css or [],
        page_action="none",
    )


def make_graph(fig, height_px):
    return dcc.Graph(
        figure=fig,
        style={"height": f"{height_px}px", "flexShrink": "0"},
        config={"displayModeBar": False},
    )


def make_graph_auto(fig):
    """Auto-height: lets Plotly compute height from scaleanchor aspect ratio."""
    return dcc.Graph(
        figure=fig,
        style={"width": "100%"},
        config={"displayModeBar": False, "responsive": True},
    )


def make_col(items):
    return html.Div(
        items,
        style={
            "display": "flex", "flexDirection": "column",
            "overflowY": "auto", "height": "100%",
            "backgroundColor": "white", "boxSizing": "border-box",
            "padding": "4px",
        }
    )


# ══════════════════════════════════════════════════════════════════════════════
# Main builder
# ══════════════════════════════════════════════════════════════════════════════
def build_match_analysis_layout(match_csv=None,
                                match_id=None,
                                players_csv=None,
                                teams_csv=None,
                                logo_dir=None):
    """
    Load one match's data and return a self-contained html.Div dashboard.

    Pass `match_id` (from the LaLiga navigation) to auto-resolve the CSV in
    2_Data/LaLiga/ and apply LaLiga support files (players, teams, logos).
    Pass `match_csv` directly to override with any specific file.
    Falls back to the EPL sample match when neither is provided.
    """
    if match_id and not match_csv:
        for _fname in os.listdir(LALIGA_DATA_DIR):
            if _fname.endswith(f'_{match_id}.csv'):
                match_csv   = os.path.join(LALIGA_DATA_DIR, _fname)
                players_csv = players_csv or LALIGA_PLAYERS_CSV
                teams_csv   = teams_csv   or LALIGA_TEAMS_CSV
                logo_dir    = logo_dir    or LALIGA_MATCH_LOGO_DIR
                break
        if not match_csv:
            for _fname in os.listdir(EPL_DATA_DIR):
                if _fname.endswith(f'_{match_id}.csv'):
                    match_csv   = os.path.join(EPL_DATA_DIR, _fname)
                    players_csv = players_csv or EPL_PLAYERS_CSV
                    teams_csv   = teams_csv   or MATCH_TEAMS_CSV
                    logo_dir    = logo_dir    or MATCH_LOGO_DIR
                    break

    match_csv   = match_csv   or MATCH_DEFAULT_CSV
    players_csv = players_csv or MATCH_PLAYERS_CSV
    teams_csv   = teams_csv   or MATCH_TEAMS_CSV
    logo_dir    = logo_dir    or MATCH_LOGO_DIR

    # ── Data loading ──────────────────────────────────────────────────────────
    df         = pd.read_csv(match_csv)
    players_df = pd.read_csv(players_csv)

    df1 = df[['week','match_id',
        'event','period_id',
        'time_min','time_sec',
        'team_code','team_position','Team Formation','Team Player Formation',
        'formation','position','Jersey Number','player_id',
        'x','y','outcome',
        'own goal',
        'Cross','Through ball',
        'Free kick taken','Corner taken','Throw In',
        'Pass End X','Pass End Y',
        'Penalty','Six Yard Blocked','Saved Off Line',
        'Set piece','From corner','Free kick',
        'Left footed','Right footed','Head','Other body part',
        'Goal Mouth Y Coordinate','Goal Mouth Z Coordinate',
        'Blocked X Coordinate','Blocked Y Coordinate',
        'Def block','Blocked cross',
        'Keeper Throw','Goal Kick',
        'Yellow Card','Second yellow','Red Card',
        'Leading to attempt','Leading to goal']]

    # ── Shot DataFrame ────────────────────────────────────────────────────────
    shot_df = df1[df1['event'].isin(['Goal', 'Miss', 'Saved Shot', 'Post'])].reset_index(drop=True).copy()

    _is_home_shot = shot_df['team_position'] == 'home'
    shot_df['plot_x']     = np.where(_is_home_shot, 105 - (shot_df['x'] / 100) * 105, (shot_df['x'] / 100) * 105)
    shot_df['plot_y']     = np.where(_is_home_shot, 68  - (shot_df['y'] / 100) * 68,  (shot_df['y'] / 100) * 68)
    shot_df['plot_end_x'] = np.where(_is_home_shot, 0, 105)
    shot_df['plot_end_y'] = np.where(
        _is_home_shot,
        68 - (shot_df['Goal Mouth Y Coordinate'] / 100) * 68,
        (shot_df['Goal Mouth Y Coordinate'] / 100) * 68,
    )
    _gmy_lo = (34 - 7.32 / 2) / 68 * 100   # ≈ 44.62  (left post in GoalMouthY space)
    _gmy_hi = (34 + 7.32 / 2) / 68 * 100   # ≈ 55.38  (right post)
    shot_df['on_target'] = (
        shot_df['Goal Mouth Y Coordinate'].between(_gmy_lo, _gmy_hi) &
        (shot_df['Goal Mouth Z Coordinate'] <= 38)
    ).astype(int)
    shot_df['plot_vx']     = 68 - (shot_df['y'] / 100) * 68
    shot_df['plot_vy']     = (shot_df['x'] / 100) * 105
    shot_df['plot_end_vx'] = 68 - (shot_df['Goal Mouth Y Coordinate'] / 100) * 68
    shot_df['plot_end_vy'] = 105.0

    # ── Pass DataFrame ────────────────────────────────────────────────────────
    pass_df = df1.copy()

    is_pass        = (pass_df['event'] == 'Pass') & (pass_df['outcome'] == 1)
    same_team_next = pass_df['team_code'] == pass_df['team_code'].shift(-1)

    pass_df['pass_recipient_id'] = np.where(
        is_pass & same_team_next,
        pass_df['player_id'].shift(-1),
        np.nan
    )

    pass_df['plot_x']     = pass_df['x']          * 105 / 100
    pass_df['plot_y']     = pass_df['y']          * 68  / 100
    pass_df['plot_end_x'] = pass_df['Pass End X'] * 105 / 100
    pass_df['plot_end_y'] = pass_df['Pass End Y'] * 68  / 100

    dx = pass_df['plot_end_x'] - pass_df['plot_x']
    dy = pass_df['plot_end_y'] - pass_df['plot_y']
    pass_df['pass_angle'] = (np.degrees(np.arctan2(dy, dx)) + 360) % 360

    a = pass_df['pass_angle']
    conditions = [
        (a >= 300) | (a <= 60),
        ((a > 60) & (a <= 90))  | ((a >= 270) & (a < 300)),
        ((a > 90) & (a <= 120)) | ((a >= 240) & (a < 270)),
        (a > 120) & (a < 240),
    ]
    choices = ['Forward', 'Sideway Forward', 'Sideway Backward', 'Backward']
    pass_df['pass_type'] = np.select(conditions, choices, default='')
    pass_df['pass_type'] = pass_df['pass_type'].replace('', np.nan)

    pass_df['ori_dist_to_goal'] = np.sqrt(
        (pass_df['x']          - GOAL_X) ** 2 +
        (pass_df['y']          - GOAL_Y) ** 2
    )
    pass_df['fin_dist_to_goal'] = np.sqrt(
        (pass_df['Pass End X'] - GOAL_X) ** 2 +
        (pass_df['Pass End Y'] - GOAL_Y) ** 2
    )

    reduction_pct  = (
        (pass_df['ori_dist_to_goal'] - pass_df['fin_dist_to_goal'])
        / pass_df['ori_dist_to_goal']
    ) * 100
    is_progressive = (pass_df['pass_type'] == 'Forward') & (reduction_pct >= 10)
    pass_df['progressive'] = is_progressive.astype(int)
    pass_df['dist_threat'] = (1 - (pass_df['ori_dist_to_goal'] / MAX_DIST)).round(2)

    # ── Carry DataFrame ───────────────────────────────────────────────────────
    carry_df = build_carry_df(df1)

    # ── Team codes ────────────────────────────────────────────────────────────
    home_code = pass_df[pass_df['team_position'] == 'home']['team_code'].iloc[0]
    away_code = pass_df[pass_df['team_position'] == 'away']['team_code'].iloc[0]

    # ── Team colours, display names & logos ───────────────────────────────────
    _teams_df = pd.read_csv(teams_csv).set_index('team_code')

    def _team_info(code):
        row = _teams_df.loc[code]
        colour    = row['HEX1']
        hext      = row['HEXT']
        display   = row['team_display_name']
        logo_path = os.path.join(logo_dir, row['team_logo'])
        with open(logo_path, 'rb') as _f:
            logo_src = 'data:image/png;base64,' + base64.b64encode(_f.read()).decode()
        return colour, hext, display, logo_src

    HOME_COLOUR, HOME_HEXT, home_display, home_logo_src = _team_info(home_code)
    AWAY_COLOUR, AWAY_HEXT, away_display, away_logo_src = _team_info(away_code)

    if _teams_df.loc[home_code, 'Colour1'] == _teams_df.loc[away_code, 'Colour1']:
        AWAY_COLOUR = _teams_df.loc[away_code, 'HEX3']

    def _darken_hex(hex_color, factor=0.6):
        h = hex_color.lstrip('#')
        r, g, b = (int(int(h[i:i+2], 16) * factor) for i in (0, 2, 4))
        return f'#{r:02x}{g:02x}{b:02x}'

    def _hex_brightness(hex_color):
        h = hex_color.lstrip('#')
        r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
        return 0.299*r + 0.587*g + 0.114*b

    HOME_BRIGHT = _hex_brightness(HOME_COLOUR) > 180
    AWAY_BRIGHT = _hex_brightness(AWAY_COLOUR) > 180
    HOME_DARK   = _darken_hex(HOME_COLOUR) if HOME_BRIGHT else HOME_COLOUR
    AWAY_DARK   = _darken_hex(AWAY_COLOUR) if AWAY_BRIGHT else AWAY_COLOUR

    # ── Name lookup ───────────────────────────────────────────────────────────
    name_lookup = (
        players_df
        .drop_duplicates('player_id')
        .set_index('player_id')['Display Name']
        .to_dict()
    )

    # ── Lineup processing ─────────────────────────────────────────────────────
    lineup = df[['week','match_id','event','period_id','time_min','time_sec','team_code','team_position',
                 'represented_qualifiers','Team Formation','Team Player Formation','formation','position',
                 'Jersey Number','player_id',"Yellow Card","Second yellow","Red Card","own goal"]]
    lineup = lineup[lineup['event'].isin(['Team setp up', 'Player on', 'Player Off','Card','Goal'])].reset_index(drop=True)

    def expand_setup_row(row, rq):
        involved_m  = re.search(r'Involved:\s*(.*?)(?:;|$)', str(rq))
        formation_m = re.search(r'Team Player Formation:\s*(.*?)(?:;|$)', str(rq))
        jersey_m    = re.search(r'Jersey Number:\s*(.*?)(?:;|$)', str(rq))
        if not (involved_m and formation_m and jersey_m):
            return [row]
        player_ids     = [p.strip() for p in involved_m.group(1).split(',')]
        slots          = [int(f.strip()) for f in formation_m.group(1).split(',')]
        jersey_numbers = [int(j.strip()) for j in jersey_m.group(1).split(',')]
        rows = []
        for pid, slot, jersey in zip(player_ids, slots, jersey_numbers):
            if slot == 0:
                continue
            r = row.copy()
            r['player_id']             = pid
            r['Team Player Formation'] = slot
            r['Jersey Number']         = jersey
            _fmt_key = str(int(float(r['formation']))) if pd.notna(r['formation']) else ''
            r['position']              = formation_position_mapping.get(_fmt_key, {}).get(str(slot))
            rows.append(r)
        return rows

    setup_mask = lineup['event'] == 'Team setp up'
    expanded   = []
    for _, row in lineup[setup_mask].iterrows():
        expanded.extend(expand_setup_row(row, row['represented_qualifiers']))

    lineup = pd.concat(
        [lineup[~setup_mask], pd.DataFrame(expanded)],
        ignore_index=True
    ).sort_values(['time_min', 'time_sec']).reset_index(drop=True)

    starting11 = lineup[lineup['event'] == 'Team setp up'].copy()

    pos_rank = {p: i for i, p in enumerate(POS_ORDER)}

    def fmt_min(time_min, period_id):
        t = int(time_min)
        if period_id == 1:
            return f"45+{t - 44}'" if t >= 45 else f"{t + 1}'"
        elif period_id == 2:
            return f"90+{t - 89}'" if t >= 90 else f"{t + 1}'"
        return f"{t + 1}'"

    # ── Home lineup table ─────────────────────────────────────────────────────
    home_all = lineup[lineup['team_position'] == 'home'].copy()
    starters = (home_all[home_all['event'] == 'Team setp up']
                .assign(_rank=lambda d: d['position'].map(lambda p: pos_rank.get(p, 99)))
                .sort_values(['_rank', 'Jersey Number']).reset_index(drop=True))
    subs_on  = (home_all[home_all['event'] == 'Player on']
                .sort_values(['time_min', 'Jersey Number']).reset_index(drop=True))
    home_goals_df = home_all[home_all['event'] == 'Goal'][['player_id', 'time_min', 'period_id', 'own goal']]

    def _card_time(pid, col):
        rows = home_all[(home_all['event'] == 'Card') & (home_all['player_id'] == pid) &
                        (home_all[col].notna()) & (home_all[col] != '')]
        if rows.empty: return ''
        r = rows.iloc[0]
        return fmt_min(r['time_min'], r['period_id'])

    def _sub_off(pid):
        rows = home_all[(home_all['event'] == 'Player Off') & (home_all['player_id'] == pid)]
        if rows.empty: return ''
        r = rows.iloc[0]
        return f"{fmt_min(r['time_min'], r['period_id'])}⬊"

    def _sub_on(pid):
        rows = subs_on[subs_on['player_id'] == pid]
        if rows.empty: return ''
        r = rows.iloc[0]
        return f"⬉{fmt_min(r['time_min'], r['period_id'])}"

    def _goals(pid):
        rows = home_goals_df[home_goals_df['player_id'] == pid]
        if rows.empty: return ''
        parts = []
        for _, r in rows.iterrows():
            m = fmt_min(r['time_min'], r['period_id'])
            parts.append(f"{m} (OG)" if (pd.notna(r['own goal']) and r['own goal'] != '') else m)
        return ', '.join(parts)

    def build_row(pid, pos, jersey, is_sub=False):
        return {'Pos': pos, 'No.': int(jersey) if pd.notna(jersey) else '',
                'Player Name': name_lookup.get(pid, pid), 'Goal': _goals(pid),
                'Yellow': _card_time(pid, 'Yellow Card'), '2nd Yellow': _card_time(pid, 'Second yellow'),
                'Red': _card_time(pid, 'Red Card'), 'Sub': _sub_on(pid) if is_sub else _sub_off(pid)}

    _EMPTY = {c: '' for c in ['Pos','No.','Player Name','Goal','Yellow','2nd Yellow','Red','Sub']}

    lineup_home = pd.DataFrame(
        [build_row(r['player_id'], r['position'], r['Jersey Number']) for _, r in starters.iterrows()]
        #+ [_EMPTY]
        + [build_row(r['player_id'], 'Sub', r['Jersey Number'], is_sub=True) for _, r in subs_on.iterrows()],
        columns=['Pos','No.','Player Name','Goal','Yellow','2nd Yellow','Red','Sub']
    )
    lineup_home = lineup_home.rename(columns={'Yellow': '🟨', '2nd Yellow': '🟨🟥', 'Red': '🟥'})

    # ── Away lineup table ─────────────────────────────────────────────────────
    away_all      = lineup[lineup['team_position'] == 'away'].copy()
    starters_away = (away_all[away_all['event'] == 'Team setp up']
                     .assign(_rank=lambda d: d['position'].map(lambda p: pos_rank.get(p, 99)))
                     .sort_values(['_rank', 'Jersey Number']).reset_index(drop=True))
    subs_on_away  = (away_all[away_all['event'] == 'Player on']
                     .sort_values(['time_min', 'Jersey Number']).reset_index(drop=True))
    away_goals_df = away_all[away_all['event'] == 'Goal'][['player_id', 'time_min', 'period_id', 'own goal']]

    def _card_time_away(pid, col):
        rows = away_all[(away_all['event'] == 'Card') & (away_all['player_id'] == pid) &
                        (away_all[col].notna()) & (away_all[col] != '')]
        if rows.empty: return ''
        r = rows.iloc[0]
        return fmt_min(r['time_min'], r['period_id'])

    def _sub_off_away(pid):
        rows = away_all[(away_all['event'] == 'Player Off') & (away_all['player_id'] == pid)]
        if rows.empty: return ''
        r = rows.iloc[0]
        return f"{fmt_min(r['time_min'], r['period_id'])}⬊"

    def _sub_on_away(pid):
        rows = subs_on_away[subs_on_away['player_id'] == pid]
        if rows.empty: return ''
        r = rows.iloc[0]
        return f"⬉{fmt_min(r['time_min'], r['period_id'])}"

    def _goals_away(pid):
        rows = away_goals_df[away_goals_df['player_id'] == pid]
        if rows.empty: return ''
        parts = []
        for _, r in rows.iterrows():
            m = fmt_min(r['time_min'], r['period_id'])
            parts.append(f"{m} (OG)" if (pd.notna(r['own goal']) and r['own goal'] != '') else m)
        return ', '.join(parts)

    def build_row_away(pid, pos, jersey, is_sub=False):
        return {'Pos': pos, 'No.': int(jersey) if pd.notna(jersey) else '',
                'Player Name': name_lookup.get(pid, pid), 'Goal': _goals_away(pid),
                'Yellow': _card_time_away(pid, 'Yellow Card'), '2nd Yellow': _card_time_away(pid, 'Second yellow'),
                'Red': _card_time_away(pid, 'Red Card'), 'Sub': _sub_on_away(pid) if is_sub else _sub_off_away(pid)}

    lineup_away = pd.DataFrame(
        [build_row_away(r['player_id'], r['position'], r['Jersey Number']) for _, r in starters_away.iterrows()]
        #+ [_EMPTY]
        + [build_row_away(r['player_id'], 'Sub', r['Jersey Number'], is_sub=True) for _, r in subs_on_away.iterrows()],
        columns=['Pos','No.','Player Name','Goal','Yellow','2nd Yellow','Red','Sub']
    )
    lineup_away = lineup_away.rename(columns={'Yellow': '🟨', '2nd Yellow': '🟨🟥', 'Red': '🟥'})

    # ── Momentum data ─────────────────────────────────────────────────────────
    MOMENTUM_EVENTS = ['Pass', 'Take on', 'Goal', 'Miss', 'Saved Shot', 'Ball touch', 'Ball recovery']
    mom_raw = pass_df[pass_df['event'].isin(MOMENTUM_EVENTS)].copy()
    mom_raw['signed_threat'] = np.where(
        mom_raw['team_position'] == 'home', mom_raw['dist_threat'], -mom_raw['dist_threat']
    )

    momentum = (mom_raw.groupby(['period_id', 'time_min'], sort=True)['signed_threat']
                .mean().reset_index().rename(columns={'signed_threat': 'momentum'}))
    momentum['momentum'] = momentum['momentum'].round(3)
    momentum['label']    = momentum.apply(lambda r: fmt_min(r['time_min'], int(r['period_id'])), axis=1)

    # Offset period-2 time_min so added-time bars from period 1 don't overlap
    _p1_mom = momentum[momentum['period_id'] == 1]
    _p2_mom = momentum[momentum['period_id'] == 2]
    if not _p1_mom.empty and not _p2_mom.empty:
        _p2_offset = int(_p1_mom['time_min'].max()) + 1 - int(_p2_mom['time_min'].min())
    else:
        _p2_offset = 0
    momentum['plot_x'] = np.where(
        momentum['period_id'] == 1,
        momentum['time_min'],
        momentum['time_min'] + _p2_offset,
    )

    sep_x      = (momentum[momentum['period_id'] == 1]['plot_x'].max() +
                  momentum[momentum['period_id'] == 2]['plot_x'].min()) / 2
    bar_colors = [HOME_COLOUR if m >= 0 else AWAY_COLOUR for m in momentum['momentum']]
    p1_mins    = sorted(momentum[momentum['period_id'] == 1]['plot_x'].unique())
    p2_mins    = sorted(momentum[momentum['period_id'] == 2]['plot_x'].unique())

    # ── Pass network data ─────────────────────────────────────────────────────
    s11_meta = (starting11[['player_id', 'team_code', 'team_position', 'position']]
                .drop_duplicates('player_id'))

    pass_df['time_s'] = pass_df['time_min'] * 60 + pass_df['time_sec']

    # Events used to compute average player positions in the pass network
    _POS_EVTS = {'Pass', 'Take On', 'Ball touch', 'Ball recovery',
                 'Goal', 'Miss', 'Post', 'Saved Shot', 'Good Skill'}

    # All match players (starters + subs-on) with position metadata
    _pn_all_meta = (
        lineup[lineup['event'].isin(['Team setp up', 'Player on'])]
        [['player_id', 'team_code', 'team_position', 'position']]
        .drop_duplicates('player_id')
    )
    _pn_display = players_df[['player_id', 'Display Name']].drop_duplicates('player_id')
    _pn_jersey  = (
        lineup[lineup['event'].isin(['Team setp up', 'Player on'])]
        [['player_id', 'Jersey Number']]
        .drop_duplicates('player_id')
    )

    # Overall avg position for all match players (fallback for periods with sparse events)
    _pn_avg_all = (
        pass_df[pass_df['event'].isin(_POS_EVTS)]
        .groupby('player_id', as_index=False).agg(x=('x', 'mean'), y=('y', 'mean'))
    )

    avg_pass_pos = (
        _pn_avg_all
        .merge(s11_meta, on='player_id', how='inner')
        .merge(_pn_display, on='player_id', how='left')
        [['player_id', 'Display Name', 'team_code', 'team_position', 'position', 'x', 'y']]
        .sort_values(['team_code', 'x']).reset_index(drop=True)
    )

    # Substitution events for pass-network period building
    _pn_match_end_s = int(df['time_min'].max()) * 60 + int(df['time_sec'].max())
    _pn_subs = lineup[lineup['event'].isin(['Player on', 'Player Off'])].copy()
    _pn_subs['time_s'] = _pn_subs['time_min'] * 60 + _pn_subs['time_sec']

    _rc_mask = (lineup['event'] == 'Card') & (
        (lineup['Red Card'].notna() & (lineup['Red Card'].astype(str) != '')) |
        (lineup['Second yellow'].notna() & (lineup['Second yellow'].astype(str) != ''))
    )
    _pn_reds = lineup[_rc_mask].copy()
    _pn_reds['time_s'] = _pn_reds['time_min'] * 60 + _pn_reds['time_sec']

    # ── Progressive pass data ─────────────────────────────────────────────────
    prog_pass_df = pass_df[['event','outcome','team_code','team_position','player_id','progressive',
                            'Pass End X','plot_x','plot_y','plot_end_x','plot_end_y']]
    prog_pass_df = prog_pass_df[
        (prog_pass_df['progressive'] == 1) & (prog_pass_df['Pass End X'] > 50) &
        (prog_pass_df['event'] == 'Pass') & (prog_pass_df['outcome'] == 1)
    ].reset_index(drop=True)

    f3_entries = pass_df[['event','outcome','team_code','team_position','player_id','progressive',
                          'Pass End X','plot_x','plot_y','plot_end_x','plot_end_y']]
    f3_entries = f3_entries[
        (f3_entries['Pass End X'] > 200/3) & (f3_entries['event'] == 'Pass') & (f3_entries['outcome'] == 1)
    ].reset_index(drop=True)

    def _zone(x, y):
        if x >= ATT_X0:
            if ROW_H <= y <= 2 * ROW_H and x <= ATT_MIDX:
                return 'Z14'
            if 2 * ROW_H <= y <= LW_SPLIT:
                return 'LHS'
            if RW_SPLIT <= y <= ROW_H:
                return 'RHS'
        return 'n/a'

    f3_entries['ori_zone'] = f3_entries.apply(lambda r: _zone(r['plot_x'],     r['plot_y']),     axis=1)
    f3_entries['fin_zone'] = f3_entries.apply(lambda r: _zone(r['plot_end_x'], r['plot_end_y']), axis=1)
    f3_entries['to_plot']  = (f3_entries['ori_zone'] != f3_entries['fin_zone']).astype(int)

    carry_f3 = carry_df.copy()
    carry_f3['ori_zone'] = carry_f3.apply(lambda r: _zone(r['plot_x'],     r['plot_y']),     axis=1)
    carry_f3['fin_zone'] = carry_f3.apply(lambda r: _zone(r['plot_end_x'], r['plot_end_y']), axis=1)
    carry_f3['to_plot']  = (carry_f3['ori_zone'] != carry_f3['fin_zone']).astype(int)

    # ── Pass receive DataFrame ────────────────────────────────────────────────
    pass_receive = pass_df[pass_df['pass_recipient_id'].notna()][
        ['event','outcome','team_code','team_position','x','y','plot_end_x','plot_end_y',
         'pass_type','progressive','dist_threat']
    ].reset_index(drop=True)

    # ── Defensive action DataFrame ────────────────────────────────────────────
    def_action_df = df1[df1['event'].isin([
        'Ball recovery', 'Blocked Pass', 'Challenge', 'Foul', 'Interception', 'Tackle'
    ])].copy().reset_index(drop=True)
    _is_away_def = def_action_df['team_position'] == 'away'
    def_action_df['plot_x'] = np.where(
        _is_away_def,
        105 - (def_action_df['x'] / 100) * 105,
        (def_action_df['x'] / 100) * 105,
    )
    def_action_df['plot_y'] = np.where(
        _is_away_def,
        68 - (def_action_df['y'] / 100) * 68,
        (def_action_df['y'] / 100) * 68,
    )

    # ── Goal times (for momentum annotations) ─────────────────────────────────
    _goal_evts = lineup[lineup['event'] == 'Goal'].copy()
    _goal_evts['display_name'] = _goal_evts['player_id'].map(name_lookup)

    _og_mask        = _goal_evts['own goal'].notna() & (_goal_evts['own goal'] != '')
    _home_goals     = _goal_evts[~_og_mask & (_goal_evts['team_position'] == 'home')]
    _away_goals     = _goal_evts[~_og_mask & (_goal_evts['team_position'] == 'away')]
    _home_og        = _goal_evts[ _og_mask & (_goal_evts['team_position'] == 'away')]
    _away_og        = _goal_evts[ _og_mask & (_goal_evts['team_position'] == 'home')]

    def _goal_plot_x(time_min, period_id):
        return int(time_min) if int(period_id) == 1 else int(time_min) + _p2_offset

    home_goal_mins = [_goal_plot_x(r['time_min'], r['period_id']) for _, r in _home_goals.iterrows()]
    away_goal_mins = [_goal_plot_x(r['time_min'], r['period_id']) for _, r in _away_goals.iterrows()]
    home_og_mins   = [_goal_plot_x(r['time_min'], r['period_id']) for _, r in _home_og.iterrows()]
    away_og_mins   = [_goal_plot_x(r['time_min'], r['period_id']) for _, r in _away_og.iterrows()]

    def _goal_hover(row):
        jersey  = int(row['Jersey Number']) if pd.notna(row['Jersey Number']) else '?'
        min_str = fmt_min(row['time_min'], int(row['period_id']))
        return f"⚽︎ {min_str} {row['team_code']} #{jersey} {row['display_name']}"

    def _og_hover(row):
        jersey  = int(row['Jersey Number']) if pd.notna(row['Jersey Number']) else '?'
        min_str = fmt_min(row['time_min'], int(row['period_id']))
        return f"⚽︎ {min_str} {row['team_code']} #{jersey} {row['display_name']} (OG)"

    home_goal_labels = [_goal_hover(r) for _, r in _home_goals.iterrows()]
    away_goal_labels = [_goal_hover(r) for _, r in _away_goals.iterrows()]
    home_og_labels   = [_og_hover(r) for _, r in _home_og.iterrows()]
    away_og_labels   = [_og_hover(r) for _, r in _away_og.iterrows()]

    # ── Red card times (for momentum annotations) ─────────────────────────────
    _rc_evts = lineup[
        (lineup['event'] == 'Card') &
        (
            (lineup['Red Card'].notna() & (lineup['Red Card'].astype(str) != '')) |
            (lineup['Second yellow'].notna() & (lineup['Second yellow'].astype(str) != ''))
        )
    ].copy()
    _rc_evts['display_name'] = _rc_evts['player_id'].map(name_lookup)

    _home_reds = _rc_evts[_rc_evts['team_position'] == 'home']
    _away_reds = _rc_evts[_rc_evts['team_position'] == 'away']

    home_red_mins = [_goal_plot_x(r['time_min'], r['period_id']) for _, r in _home_reds.iterrows()]
    away_red_mins = [_goal_plot_x(r['time_min'], r['period_id']) for _, r in _away_reds.iterrows()]

    def _rc_hover(row):
        jersey   = int(row['Jersey Number']) if pd.notna(row['Jersey Number']) else '?'
        min_str  = fmt_min(row['time_min'], int(row['period_id']))
        icon     = '🟥' if (pd.notna(row['Red Card']) and str(row['Red Card']) != '') else '🟨🟥'
        return f"{icon} {min_str} {row['team_code']} #{jersey} {row['display_name']}"

    home_red_labels = [_rc_hover(r) for _, r in _home_reds.iterrows()]
    away_red_labels = [_rc_hover(r) for _, r in _away_reds.iterrows()]

    # ── Match statistics data ─────────────────────────────────────────────────
    _all_p = df1[df1['event'] == 'Pass']
    _hm_p  = _all_p[_all_p['team_position'] == 'home']
    _aw_p  = _all_p[_all_p['team_position'] == 'away']
    _tot_p = len(_hm_p) + len(_aw_p)

    _ms_poss_h = round(len(_hm_p) / _tot_p * 100, 1) if _tot_p else 50.0
    _ms_poss_a = round(100 - _ms_poss_h, 1)

    _hm_sh = shot_df[shot_df['team_position'] == 'home']
    _aw_sh = shot_df[shot_df['team_position'] == 'away']
    _ms_shots_h, _ms_shots_a       = len(_hm_sh), len(_aw_sh)
    _ms_shots_ot_h, _ms_shots_ot_a = int(_hm_sh['on_target'].sum()), int(_aw_sh['on_target'].sum())

    _ft_p = df1[(df1['event'] == 'Pass') & (df1['Pass End X'] > 200/3) & (df1['outcome'] == 1)]
    _ms_ft_h   = len(_ft_p[_ft_p['team_position'] == 'home'])
    _ms_ft_a   = len(_ft_p[_ft_p['team_position'] == 'away'])
    _ms_ft_tot = _ms_ft_h + _ms_ft_a
    _ms_ft_h_pct = round(_ms_ft_h / _ms_ft_tot * 100, 1) if _ms_ft_tot else 50.0
    _ms_ft_a_pct = round(100 - _ms_ft_h_pct, 1)

    _DEF_EVT    = ['Ball recovery', 'Blocked Pass', 'Challenge', 'Foul', 'Interception', 'Tackle']
    _aw_own_p   = len(df1[(df1['event'] == 'Pass') & (df1['team_position'] == 'away') & (df1['x'] < 60)])
    _hm_def_att = len(df1[df1['event'].isin(_DEF_EVT) & (df1['team_position'] == 'home') & (df1['x'] > 40)])
    _ms_ppda_h  = round(_aw_own_p / _hm_def_att, 1) if _hm_def_att else None

    _hm_own_p   = len(df1[(df1['event'] == 'Pass') & (df1['team_position'] == 'home') & (df1['x'] < 60)])
    _aw_def_att = len(df1[df1['event'].isin(_DEF_EVT) & (df1['team_position'] == 'away') & (df1['x'] > 40)])
    _ms_ppda_a  = round(_hm_own_p / _aw_def_att, 1) if _aw_def_att else None

    _ms_oph_h = len(df1[(df1['event'] == 'Pass') & (df1['team_position'] == 'home') & (df1['x'] > 50)])
    _ms_oph_a = len(df1[(df1['event'] == 'Pass') & (df1['team_position'] == 'away') & (df1['x'] > 50)])

    _ms_hr_h = len(df1[(df1['event'] == 'Ball recovery') & (df1['team_position'] == 'home') & (df1['x'] > 50)])
    _ms_hr_a = len(df1[(df1['event'] == 'Ball recovery') & (df1['team_position'] == 'away') & (df1['x'] > 50)])

    _ms_cross_h  = int(df1[(df1['team_position'] == 'home') & df1['Cross'].notna() & (df1['Cross'].astype(str) != '')].shape[0])
    _ms_cross_a  = int(df1[(df1['team_position'] == 'away') & df1['Cross'].notna() & (df1['Cross'].astype(str) != '')].shape[0])

    _ms_corner_h = int(df1[(df1['team_position'] == 'home') & df1['Corner taken'].notna() & (df1['Corner taken'].astype(str) != '')].shape[0])
    _ms_corner_a = int(df1[(df1['team_position'] == 'away') & df1['Corner taken'].notna() & (df1['Corner taken'].astype(str) != '')].shape[0])

    _fb_shot_ev_ms = {'Goal', 'Miss', 'Post', 'Saved Shot'}
    _ms_fb_h = (int(df[(df['team_position'] == 'home') & df['event'].isin(_fb_shot_ev_ms) & (df['Fast break'] == 'Si')].shape[0])
                if 'Fast break' in df.columns else 0)
    _ms_fb_a = (int(df[(df['team_position'] == 'away') & df['event'].isin(_fb_shot_ev_ms) & (df['Fast break'] == 'Si')].shape[0])
                if 'Fast break' in df.columns else 0)

    # ── fig_match_stats ───────────────────────────────────────────────────────
    _SLIVER = 0.1  # minimum bar length when a stat value is 0

    def _pct_share(h, a):
        t = h + a
        if t == 0:
            return _SLIVER, _SLIVER
        h_pct = round(h / t * 100, 1)
        a_pct = round(100 - h_pct, 1)
        return max(h_pct, _SLIVER), max(a_pct, _SLIVER)

    def _capped(h, a, cap=4):
        return (min(max(round(h / cap * 100, 1), _SLIVER), 100.0),
                min(max(round(a / cap * 100, 1), _SLIVER), 100.0))

    def _ppda_share(h, a):
        if not h and not a:
            return _SLIVER, _SLIVER
        if not h:
            return _SLIVER, 100.0
        if not a:
            return 100.0, _SLIVER
        hi, ai = 1 / h, 1 / a
        t = hi + ai
        h_pct = round(hi / t * 100, 1)
        a_pct = round(ai / t * 100, 1)
        return max(h_pct, _SLIVER), max(a_pct, _SLIVER)

    _ms_labels = [
        'Possession %', 'Shots (On Target)', 'Field Tilt',
        'Pass in Opp. Half', 'Fast Break Seq.', 'Cross',
        'PPDA', 'High Recovery', 'Corner',
    ]

    # PPDA uses inverse so lower value = longer bar = better pressing
    _raw_pairs = [
        (max(_ms_poss_h, _SLIVER),    max(_ms_poss_a, _SLIVER)),
        _pct_share(_ms_shots_h,        _ms_shots_a),
        (max(_ms_ft_h_pct, _SLIVER),   max(_ms_ft_a_pct, _SLIVER)),
        _pct_share(_ms_oph_h,          _ms_oph_a),
        _capped(_ms_fb_h,              _ms_fb_a),
        _pct_share(_ms_cross_h,        _ms_cross_a),
        _ppda_share(_ms_ppda_h,        _ms_ppda_a),
        _pct_share(_ms_hr_h,           _ms_hr_a),
        _pct_share(_ms_corner_h,       _ms_corner_a),
    ]
    _bar_h_vals = [-h for h, _ in _raw_pairs]
    _bar_a_vals = [ a for _, a in _raw_pairs]

    _text_h = [
        f'{_ms_poss_h}%',
        f'{_ms_shots_h} ({_ms_shots_ot_h})',
        f'{_ms_ft_h_pct}%',
        str(_ms_oph_h), str(_ms_fb_h), str(_ms_cross_h),
        str(_ms_ppda_h) if _ms_ppda_h is not None else '-',
        str(_ms_hr_h), str(_ms_corner_h),
    ]
    _text_a = [
        f'{_ms_poss_a}%',
        f'{_ms_shots_a} ({_ms_shots_ot_a})',
        f'{_ms_ft_a_pct}%',
        str(_ms_oph_a), str(_ms_fb_a), str(_ms_cross_a),
        str(_ms_ppda_a) if _ms_ppda_a is not None else '-',
        str(_ms_hr_a), str(_ms_corner_a),
    ]

    def _cmp(h, a, lower_better=False):
        if h == 0 and a == 0: return 'neither'
        if h == a: return 'tie'
        return ('home' if h < a else 'away') if lower_better else ('home' if h > a else 'away')

    def _shots_cmp(sh, sa, oh, oa):
        if sh == 0 and sa == 0: return 'neither'
        if sh != sa: return 'home' if sh > sa else 'away'
        if oh != oa: return 'home' if oh > oa else 'away'
        return 'tie'

    _ppda_h_raw = _ms_ppda_h or float('inf')
    _ppda_a_raw = _ms_ppda_a or float('inf')
    _winners = [
        _cmp(_ms_poss_h,   _ms_poss_a),
        _shots_cmp(_ms_shots_h, _ms_shots_a, _ms_shots_ot_h, _ms_shots_ot_a),
        _cmp(_ms_ft_h_pct, _ms_ft_a_pct),
        _cmp(_ms_oph_h,    _ms_oph_a),
        _cmp(_ms_fb_h,     _ms_fb_a),
        _cmp(_ms_cross_h,  _ms_cross_a),
        'neither' if (_ms_ppda_h is None and _ms_ppda_a is None)
            else _cmp(_ppda_h_raw, _ppda_a_raw, lower_better=True),
        _cmp(_ms_hr_h,     _ms_hr_a),
        _cmp(_ms_corner_h, _ms_corner_a),
    ]

    _BOX_W     = 32
    _opacity_h = [1.0 if w in ('home', 'tie') else 0.3 for w in _winners]
    _opacity_a = [1.0 if w in ('away', 'tie') else 0.3 for w in _winners]
    _tfcol_h   = [SECONDARY_COL if w in ('home', 'tie') else '#aaaaaa' for w in _winners]
    _tfcol_a   = [SECONDARY_COL if w in ('away', 'tie') else '#aaaaaa' for w in _winners]

    fig_match_stats = go.Figure()

    # Fixed-width label boxes (same width for every row, rendered below bars)
    for _i in range(len(_ms_labels)):
        fig_match_stats.add_shape(
            type='rect',
            x0=-_BOX_W, x1=_BOX_W,
            y0=_i - 0.3, y1=_i + 0.3,
            xref='x', yref='y',
            fillcolor= SIDEBAR_BG,
            line=dict(color='#dedede', width=0),
            layer='below',
        )

    fig_match_stats.add_trace(go.Bar(
        name=home_display, x=_bar_h_vals, y=_ms_labels, orientation='h',
        base=[-_BOX_W] * len(_ms_labels),
        marker=dict(color=HOME_COLOUR, opacity=_opacity_h, line_width=0),
        text=_text_h, textposition='outside', cliponaxis=False,
        textfont=dict(color=_tfcol_h, size=12, weight=400, family='Inter, Segoe UI, Arial'),
        showlegend=False,
        hoverinfo='skip',
    ))
    fig_match_stats.add_trace(go.Bar(
        name=away_display, x=_bar_a_vals, y=_ms_labels, orientation='h',
        base=[+_BOX_W] * len(_ms_labels),
        marker=dict(color=AWAY_COLOUR, opacity=_opacity_a, line_width=0),
        text=_text_a, textposition='outside', cliponaxis=False,
        textfont=dict(color=_tfcol_a, size=12, weight=400, family='Inter, Segoe UI, Arial'),
        showlegend=False,
        hoverinfo='skip',
    ))

    for _lbl in _ms_labels:
        fig_match_stats.add_annotation(
            x=0, y=_lbl, text=_lbl, showarrow=False,
            xanchor='center', yanchor='middle',
            font=dict(size=10, weight=800, color=SECONDARY_COL, family='Inter, Segoe UI, Arial'),
        )

    fig_match_stats.update_layout(
        barmode='overlay',
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, range=[-145, 145]),
        yaxis=dict(showticklabels=False, autorange='reversed'),
        plot_bgcolor='white', paper_bgcolor='white',
        margin=dict(l=24, r=24, t=4, b=4),
        bargap=0.2,
        showlegend=False,
    )

    # ── fig_match_momentum ────────────────────────────────────────────────────
    fig_match_momentum = go.Figure()
    fig_match_momentum.add_trace(go.Bar(
        x=momentum['plot_x'], y=momentum['momentum'],
        marker_color=bar_colors, marker_line_width=0,
        customdata=momentum['label'],
        hovertemplate='<b>%{customdata}</b><br>Momentum: %{y:.3f}<extra></extra>',
        showlegend=False,
    ))
    fig_match_momentum.add_shape(
        type='line', x0=sep_x, x1=sep_x, y0=0, y1=1, yref='paper',
        line=dict(color='#333333', width=1.5, dash='dot'),
    )
    for period_id, mins, label in [(1, p1_mins, '1st Half'), (2, p2_mins, '2nd Half')]:
        fig_match_momentum.add_annotation(
            text=label, x=(min(mins) + max(mins)) / 2, y=1.15, yref='paper',
            showarrow=False, font=dict(size=12, color='#555555'),
        )
    if home_goal_mins:
        fig_match_momentum.add_trace(go.Scatter(
            x=home_goal_mins, y=[1.1] * len(home_goal_mins),
            mode='text', text=['⚽︎'] * len(home_goal_mins),
            textfont=dict(size=14), textposition='top center',
            customdata=home_goal_labels,
            hovertemplate='%{customdata}<extra></extra>',
            hoverlabel=dict(bgcolor=HOME_COLOUR, font=dict(color=HOME_HEXT)),
            showlegend=False,
        ))
    if away_goal_mins:
        fig_match_momentum.add_trace(go.Scatter(
            x=away_goal_mins, y=[-1.1] * len(away_goal_mins),
            mode='text', text=['⚽︎'] * len(away_goal_mins),
            textfont=dict(size=14), textposition='bottom center',
            customdata=away_goal_labels,
            hovertemplate='%{customdata}<extra></extra>',
            hoverlabel=dict(bgcolor=AWAY_COLOUR, font=dict(color=AWAY_HEXT)),
            showlegend=False,
        ))
    if home_og_mins:
        fig_match_momentum.add_trace(go.Scatter(
            x=home_og_mins, y=[1.1] * len(home_og_mins),
            mode='text', text=['⚽︎'] * len(home_og_mins),
            textfont=dict(size=14, color='#E74C3C'), textposition='top center',
            customdata=home_og_labels,
            hovertemplate='%{customdata}<extra></extra>',
            hoverlabel=dict(bgcolor='#E74C3C', font=dict(color='white')),
            showlegend=False,
        ))
    if away_og_mins:
        fig_match_momentum.add_trace(go.Scatter(
            x=away_og_mins, y=[-1.1] * len(away_og_mins),
            mode='text', text=['⚽︎'] * len(away_og_mins),
            textfont=dict(size=14, color='#E74C3C'), textposition='bottom center',
            customdata=away_og_labels,
            hovertemplate='%{customdata}<extra></extra>',
            hoverlabel=dict(bgcolor='#E74C3C', font=dict(color='white')),
            showlegend=False,
        ))
    if home_red_mins:
        fig_match_momentum.add_trace(go.Scatter(
            x=home_red_mins, y=[1.1] * len(home_red_mins),
            mode='text', text=['▉'] * len(home_red_mins),
            textfont=dict(size=11,color='#E74C3C'), textposition='top center',
            customdata=home_red_labels,
            hovertemplate='%{customdata}<extra></extra>',
            hoverlabel=dict(bgcolor='#E74C3C', font=dict(color='white')),
            showlegend=False,
        ))
    if away_red_mins:
        fig_match_momentum.add_trace(go.Scatter(
            x=away_red_mins, y=[-1.1] * len(away_red_mins),
            mode='text', text=['▉'] * len(away_red_mins),
            textfont=dict(size=11,color='#E74C3C'), textposition='bottom center',
            customdata=away_red_labels,
            hovertemplate='%{customdata}<extra></extra>',
            hoverlabel=dict(bgcolor='#E74C3C', font=dict(color='white')),
            showlegend=False,
        ))
    fig_match_momentum.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
        yaxis=dict(showticklabels=False, zeroline=True, range=[-1.5, 1.5],
                   zerolinecolor='black', zerolinewidth=1.5, gridcolor='#eeeeee', showgrid=True),
        bargap=0.15, plot_bgcolor='white', paper_bgcolor='white',
        margin=dict(l=40, r=0, t=18, b=0), showlegend=False,
    )
    # Team badges: home above x-axis, away below — on the left margin
    for _src, _y in [(home_logo_src, 0.78), (away_logo_src, 0.22)]:
        fig_match_momentum.add_layout_image(dict(
            source=_src,
            xref='paper', yref='paper',
            x=0, y=_y,
            sizex=0.10, sizey=0.3,
            xanchor='right', yanchor='middle',
            layer='above',
        ))

    # ── fig_starting_xi ───────────────────────────────────────────────────────
    _hf = starting11[starting11['team_position'] == 'home']
    _af = starting11[starting11['team_position'] == 'away']
    _home_fmt = '-'.join(str(int(_hf['formation'].iloc[0]))) if not _hf.empty else ''
    _away_fmt = '-'.join(str(int(_af['formation'].iloc[0]))) if not _af.empty else ''

    fig_starting_xi = make_pitch5(lineup, players_df, HOME_COLOUR, AWAY_COLOUR, name_lookup,
                                   home_hext=HOME_HEXT, away_hext=AWAY_HEXT)
    _PL = 105 * 1.35
    if _home_fmt:
        fig_starting_xi.add_annotation(
            text=f"<b>{_home_fmt}</b>",
            x=0, y=69, xref='x', yref='y',
            showarrow=False,
            font=dict(size=12, color=HOME_COLOUR, family='Inter, Segoe UI, Arial'),
            xanchor='left', yanchor='bottom',
        )
    if _away_fmt:
        fig_starting_xi.add_annotation(
            text=f"<b>{_away_fmt}</b>",
            x=_PL, y=69, xref='x', yref='y',
            showarrow=False,
            font=dict(size=12, color=AWAY_COLOUR, family='Inter, Segoe UI, Arial'),
            xanchor='right', yanchor='bottom',
        )

    # ── fig_pass_network (per-period, per-team) ───────────────────────────────

    def _pn_fmt_ts(s):
        return f"{int(s) // 60}:{int(s) % 60:02d}"

    def _pn_ordinal(n):
        return {1: '1st', 2: '2nd', 3: '3rd'}.get(n, f'{n}th')

    def _pn_build_periods(team_pos):
        on_df = _pn_subs[
            (_pn_subs['team_position'] == team_pos) & (_pn_subs['event'] == 'Player on')
        ].sort_values('time_s')
        raw_times = sorted(on_df['time_s'].unique())

        _ht_times = set(
            on_df[
                (on_df['period_id'] == 2) &
                (on_df['time_min'] == 45) &
                (on_df['time_sec'] == 0)
            ]['time_s'].tolist()
        )

        # Group sub times within 60 s of the first sub in the wave
        wave_groups = []
        if raw_times:
            cur = [raw_times[0]]
            for t in raw_times[1:]:
                if t - cur[0] <= 60:
                    cur.append(t)
                else:
                    wave_groups.append(cur)
                    cur = [t]
            wave_groups.append(cur)

        # Red card events for this team
        team_reds = _pn_reds[_pn_reds['team_position'] == team_pos].sort_values('time_s')
        rc_times  = sorted(team_reds['time_s'].unique())

        # No changes at all → single full-match period
        if not wave_groups and not rc_times:
            return [(0, _pn_match_end_s,
                     f'Starting XI ({_pn_fmt_ts(0)} - {_pn_fmt_ts(_pn_match_end_s)})', -1)]

        # Build change-point list: ('sub', first, last, n) or ('red', t, t, 1)
        change_points = []
        for grp in wave_groups:
            n = sum(int((on_df['time_s'] == t).sum()) for t in grp)
            change_points.append(('sub', grp[0], grp[-1], n))
        for rc_t in rc_times:
            change_points.append(('red', rc_t, rc_t, 1))
        change_points.sort(key=lambda cp: cp[1])

        def _lbl(cs, cr, le):
            if cs == 0 and cr == 0:
                return 'Starting XI'
            if le == 'red':
                return f'After {_pn_ordinal(cr)} Red Card'
            return f'After {_pn_ordinal(cs)} Sub'

        periods = []
        prev_s, cum_subs, cum_reds, prev_snap, last_ev = 0, 0, 0, -1, None
        for cp_type, cp_first, cp_last, cp_n in change_points:
            lbl = _lbl(cum_subs, cum_reds, last_ev)
            end_str = ('HT' if cp_type == 'sub' and cp_first in _ht_times
                       else _pn_fmt_ts(cp_first - 1))
            periods.append((prev_s, cp_first - 1,
                            f'{lbl} ({_pn_fmt_ts(prev_s)} - {end_str})',
                            prev_snap))
            if cp_type == 'sub':
                cum_subs += cp_n
                last_ev = 'sub'
            else:
                cum_reds += 1
                last_ev = 'red'
            prev_s    = cp_first
            prev_snap = cp_last

        lbl = _lbl(cum_subs, cum_reds, last_ev)
        periods.append((prev_s, _pn_match_end_s,
                        f'{lbl} ({_pn_fmt_ts(prev_s)} - {_pn_fmt_ts(_pn_match_end_s)})',
                        prev_snap))
        return periods

    def _pn_active_pids(team_pos, snapshot_s):
        """Players on the pitch after all subs and red cards up to snapshot_s."""
        starters = set(s11_meta[s11_meta['team_position'] == team_pos]['player_id'])
        team_subs = _pn_subs[_pn_subs['team_position'] == team_pos].sort_values('time_s')
        active = set(starters)
        for _, r in team_subs[team_subs['time_s'] <= snapshot_s].iterrows():
            if r['event'] == 'Player on':
                active.add(r['player_id'])
            else:
                active.discard(r['player_id'])
        # Remove red-carded players (sent off, not replaced)
        team_reds = _pn_reds[
            (_pn_reds['team_position'] == team_pos) & (_pn_reds['time_s'] <= snapshot_s)
        ]
        for _, r in team_reds.iterrows():
            active.discard(r['player_id'])
        return active

    def _pn_period_data(team_pos, start_s, end_s, snapshot_s):
        active = _pn_active_pids(team_pos, snapshot_s)

        # Average position from _POS_EVTS in the period; fall back to overall
        pos_events = pass_df[
            (pass_df['team_position'] == team_pos) &
            (pass_df['event'].isin(_POS_EVTS)) &
            (pass_df['time_s'] >= start_s) &
            (pass_df['time_s'] <= end_s)
        ]
        pos_period = (pos_events.groupby('player_id', as_index=False)
                      .agg(x=('x', 'mean'), y=('y', 'mean')))
        pos_merged = (pd.concat([pos_period, _pn_avg_all], ignore_index=True)
                      .drop_duplicates('player_id', keep='first'))
        pos_merged = (pos_merged[pos_merged['player_id'].isin(active)]
                      .merge(_pn_all_meta, on='player_id', how='left')
                      .merge(_pn_display,  on='player_id', how='left')
                      .merge(_pn_jersey,   on='player_id', how='left'))

        pos_lookup = {
            r['player_id']: (68 - r['y'] * 68 / 100, r['x'] * 105 / 100)
            for _, r in pos_merged.iterrows()
        }

        # Directed pass counts
        suc_passes = pass_df[
            (pass_df['team_position'] == team_pos) &
            (pass_df['event'] == 'Pass') &
            (pass_df['outcome'] == 1) &
            (pass_df['time_s'] >= start_s) &
            (pass_df['time_s'] <= end_s)
        ]
        ids = list(pos_lookup.keys())
        if len(ids) < 2 or suc_passes.empty:
            return pos_lookup, pos_merged, pd.DataFrame(
                columns=['Player_ID_A', 'Player_ID_B', 'A -> B', 'B -> A'])

        pivot = (
            suc_passes[suc_passes['player_id'].isin(ids) &
                       suc_passes['pass_recipient_id'].isin(ids)]
            .pivot_table(index='player_id', columns='pass_recipient_id',
                         values='event', aggfunc='count', fill_value=0)
            .reindex(index=ids, columns=ids, fill_value=0)
        )
        arr   = pivot.values
        im    = {pid: i for i, pid in enumerate(ids)}
        pairs = pd.DataFrame(list(combinations(ids, 2)), columns=['Player_ID_A', 'Player_ID_B'])
        ai    = pairs['Player_ID_A'].map(im).values
        bi    = pairs['Player_ID_B'].map(im).values
        pairs['A -> B'] = arr[ai, bi].astype(int)
        pairs['B -> A'] = arr[bi, ai].astype(int)
        summary = pairs[(pairs['A -> B'] > 0) | (pairs['B -> A'] > 0)].reset_index(drop=True)
        return pos_lookup, pos_merged, summary

    def _build_pn_fig(team_pos, colour):
        h = colour.lstrip('#')
        r_c, g_c, b_c = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        _pn_bright = 0.299*r_c + 0.587*g_c + 0.114*b_c > 180
        node_fill  = rgba(colour, 1)
        if _pn_bright:
            _dr, _dg, _db = int(r_c*0.6), int(g_c*0.6), int(b_c*0.6)
            arrow_col = f'rgba({_dr},{_dg},{_db},0.75)'
        else:
            arrow_col  = f'rgba({r_c},{g_c},{b_c},0.75)'
        _node_txt_col = 'black' if _pn_bright else 'white'

        periods      = _pn_build_periods(team_pos)
        fig          = make_pitch_v()
        if team_pos == 'home':
            fig.add_annotation(
                text='Attacking Direction →', x=-3, y=52.5,
                xref='x', yref='y', showarrow=False,
                font=dict(size=11, color='#222222', family='Arial'),
                textangle=-90, xanchor='center', yanchor='middle',
            )
        else:
            fig.add_annotation(
                text='← Attacking Direction', x=71, y=52.5,
                xref='x', yref='y', showarrow=False,
                font=dict(size=11, color='#222222', family='Arial'),
                textangle=90, xanchor='center', yanchor='middle',
            )
        n_pitch      = len(fig.data)
        trace_ranges = []

        for p_idx, (start_s, end_s, label, snap_s) in enumerate(periods):
            pos_lookup_p, pos_df_p, summary_p = _pn_period_data(
                team_pos, start_s, end_s, snap_s)
            vis   = (p_idx == 0)
            first = len(fig.data)

            # ── Directed pass arrows ──────────────────────────────────────────
            if not summary_p.empty:
                dur_s = end_s - start_s
                thresh = (3 if dur_s > 3600 else
                          2 if dur_s > 2700 else
                          1 if dur_s > 1800 else 0)

                all_counts = ([c for c in summary_p['A -> B'] if c > thresh] +
                              [c for c in summary_p['B -> A'] if c > thresh])
                c_max = max(all_counts) if all_counts else 1
                c_min = min(all_counts) if all_counts else 0
                c_rng = max(c_max - c_min, 1)

                def _aw(c): return 0.5 + (c - c_min) / c_rng * 5.0

                lbl_xs, lbl_ys, lbl_txts = [], [], []

                for _, edge in summary_p.iterrows():
                    pid_a, pid_b = edge['Player_ID_A'], edge['Player_ID_B']
                    if pid_a not in pos_lookup_p or pid_b not in pos_lookup_p:
                        continue
                    ax, ay   = pos_lookup_p[pid_a]
                    bx, by   = pos_lookup_p[pid_b]
                    cnt_ab   = int(edge['A -> B'])
                    cnt_ba   = int(edge['B -> A'])
                    seg_len  = math.hypot(bx - ax, by - ay)
                    if seg_len < 0.001:
                        continue
                    bidir = cnt_ab > thresh and cnt_ba > thresh
                    off   = 0.25 if bidir else 0.0
                    # Perpendicular unit vector (left of A→B direction)
                    px = -(by - ay) / seg_len * off
                    py =  (bx - ax) / seg_len * off

                    if cnt_ab > thresh:
                        x1, y1, x2, y2 = ax + px, ay + py, bx + px, by + py
                        fig.add_trace(go.Scatter(
                            x=[x1, x2], y=[y1, y2], mode='lines+markers',
                            line=dict(color=arrow_col, width=_aw(cnt_ab)),
                            marker=dict(symbol='arrow', size=[0, 9],
                                        color=arrow_col, angleref='previous'),
                            showlegend=False, hoverinfo='skip', visible=vis,
                        ))
                        lbl_xs.append((x1 + x2) / 2)
                        lbl_ys.append((y1 + y2) / 2)
                        lbl_txts.append(str(cnt_ab))

                    if cnt_ba > thresh:
                        x1, y1, x2, y2 = bx - px, by - py, ax - px, ay - py
                        fig.add_trace(go.Scatter(
                            x=[x1, x2], y=[y1, y2], mode='lines+markers',
                            line=dict(color=arrow_col, width=_aw(cnt_ba)),
                            marker=dict(symbol='arrow', size=[0, 9],
                                        color=arrow_col, angleref='previous'),
                            showlegend=False, hoverinfo='skip', visible=vis,
                        ))
                        lbl_xs.append((x1 + x2) / 2)
                        lbl_ys.append((y1 + y2) / 2)
                        lbl_txts.append(str(cnt_ba))

                if lbl_xs:
                    fig.add_trace(go.Scatter(
                        x=lbl_xs, y=lbl_ys, mode='text',
                        text=lbl_txts,
                        textfont=dict(size=1, color='black'),
                        showlegend=False, hoverinfo='skip', visible=vis,
                    ))

            # ── Player nodes (jersey number) ──────────────────────────────────
            node_xs, node_ys, node_lbls = [], [], []
            player_entries = []
            for _, row in pos_df_p.iterrows():
                pid = row['player_id']
                if pid not in pos_lookup_p:
                    continue
                vx, vy = pos_lookup_p[pid]
                jersey  = row.get('Jersey Number', '')
                jersey_lbl = str(int(jersey)) if pd.notna(jersey) else ''
                disp    = row['Display Name'] if pd.notna(row.get('Display Name')) else ''
                node_xs.append(vx); node_ys.append(vy); node_lbls.append(jersey_lbl)
                if pd.notna(jersey):
                    player_entries.append((int(jersey), disp))

            if node_xs:
                fig.add_trace(go.Scatter(
                    x=node_xs, y=node_ys, mode='markers+text',
                    marker=dict(size=18, color=node_fill, line=dict(color='black', width=1.5)),
                    text=node_lbls, textposition='middle center',
                    textfont=dict(color=_node_txt_col, size=9, family='Arial Bold'),
                    showlegend=False, hoverinfo='skip', visible=vis,
                ))

            # ── Player list below the pitch ───────────────────────────────────
            if player_entries:
                player_entries.sort(key=lambda e: e[0])
                n_left    = math.ceil(len(player_entries) / 2)
                left_col  = player_entries[:n_left]
                right_col = player_entries[n_left:]
                list_xs, list_ys, list_txts = [], [], []
                for i in range(n_left):
                    y = -5 - i * 5
                    j, name = left_col[i]
                    list_xs.append(2);  list_ys.append(y)
                    list_txts.append(f"<b>{j}</b> {name}")
                    if i < len(right_col):
                        j2, name2 = right_col[i]
                        list_xs.append(36); list_ys.append(y)
                        list_txts.append(f"<b>{j2}</b> {name2}")
                fig.add_trace(go.Scatter(
                    x=list_xs, y=list_ys, mode='text',
                    text=list_txts, textposition='middle right',
                    textfont=dict(size=9, color='#333333', family='Arial'),
                    showlegend=False, hoverinfo='skip', visible=vis,
                ))

            trace_ranges.append((first, len(fig.data) - 1, label))

        # Dropdown buttons toggle period traces; pitch traces are always visible
        n_total = len(fig.data)
        buttons = []
        for first, last, label in trace_ranges:
            vis_list = [True] * n_pitch + [
                (first <= i <= last) for i in range(n_pitch, n_total)
            ]
            buttons.append(dict(label=label, method='update',
                                args=[{'visible': vis_list}]))

        fig.update_layout(
            updatemenus=[dict(
                type='dropdown', direction='down',
                x=0.5, xanchor='center', y=1.01, yanchor='bottom',
                bgcolor='white', bordercolor='#cccccc', borderwidth=1,
                font=dict(size=11),
                buttons=buttons, active=0,
            )],
            plot_bgcolor='white', paper_bgcolor='white', showlegend=False,
            xaxis=dict(range=[-5, 70] if team_pos == 'home' else [-2, 73],
                       showgrid=False, zeroline=False, visible=False,
                       scaleanchor='y', scaleratio=1),
            yaxis=dict(range=[-36, 105], showgrid=False, zeroline=False, visible=False),
            margin=dict(l=0, r=0, t=0, b=0),
        )
        return fig

    fig_pn_home = _build_pn_fig('home', HOME_COLOUR)
    fig_pn_away = _build_pn_fig('away', AWAY_COLOUR)

    def _add_carry_traces(fig, df_c, color, opacity=1,
                          xcol='plot_x', ycol='plot_y',
                          xend='plot_end_x', yend='plot_end_y'):
        """Dotted arrow traces for carries, layered on top of pass arrows."""
        if df_c.empty:
            return
        xs, ys, hx, hy, angs = [], [], [], [], []
        for _, r in df_c.iterrows():
            x0, y0, x1, y1 = r[xcol], r[ycol], r[xend], r[yend]
            xs += [x0, x1, None]; ys += [y0, y1, None]
            hx.append(x1); hy.append(y1)
            angs.append((90 - np.degrees(np.arctan2(y1 - y0, x1 - x0))) % 360)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode='lines',
            line=dict(color=color, width=2, dash='dot'),
            opacity=opacity, showlegend=False, hoverinfo='skip',
        ))
        fig.add_trace(go.Scatter(
            x=hx, y=hy, mode='markers',
            marker=dict(symbol='arrow', size=10, color=color, angle=angs),
            opacity=opacity, showlegend=False, hoverinfo='skip',
        ))

    # ── fig_prog_passes_home ──────────────────────────────────────────────────
    prog = prog_pass_df[prog_pass_df['team_position'] == 'home'].copy()
    prog['zone'] = np.select(
        [prog['plot_y'] < ROW_H,
         (prog['plot_y'] >= ROW_H) & (prog['plot_y'] <= ROW_H * 2),
         prog['plot_y'] > ROW_H * 2],
        ['Right', 'Center', 'Left'], default='Center',
    )
    zone_stats = (prog.groupby('zone', sort=False).size()
                  .reset_index(name='count')
                  .set_index('zone').reindex(['Right', 'Center', 'Left']).reset_index())

    prog_carry_home = carry_df[
        (carry_df['team_position'] == 'home') &
        (carry_df['progressive'] == 1) &
        (carry_df['plot_end_x'] > 52.5)
    ].copy()
    prog_carry_home['zone'] = np.select(
        [prog_carry_home['plot_y'] < ROW_H,
         (prog_carry_home['plot_y'] >= ROW_H) & (prog_carry_home['plot_y'] <= ROW_H * 2),
         prog_carry_home['plot_y'] > ROW_H * 2],
        ['Right', 'Center', 'Left'], default='Center',
    )
    carry_zone_h = prog_carry_home.groupby('zone').size().to_dict()

    zone_y_centers = {'Right': ROW_H * 0.5, 'Center': ROW_H * 1.5, 'Left': ROW_H * 2.5}
    zone_colors    = {'Right': '#27AE60',   'Center': '#2980B9',    'Left': '#C0392B'}

    fig_prog_passes_home = make_pitch4()
    for _, r in prog.iterrows():
        fig_prog_passes_home.add_annotation(
            x=r['plot_end_x'], y=r['plot_end_y'], ax=r['plot_x'], ay=r['plot_y'],
            xref='x', yref='y', axref='x', ayref='y',
            text='', showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
            arrowcolor=zone_colors.get(r['zone'], HOME_DARK), opacity=0.5,
        )
    _add_carry_traces(fig_prog_passes_home, prog_carry_home, 'black')
    for _, zr in zone_stats.iterrows():
        z = zr['zone']
        fig_prog_passes_home.add_annotation(
            text=f"<b>{z}:</b><br>P: {int(zr['count'])}<br>C: {carry_zone_h.get(z, 0)}",
            x=107, y=zone_y_centers[z], xref='x', yref='y', showarrow=False,
            font=dict(size=11, color=zone_colors[z]), align='left', xanchor='left',
        )
    fig_prog_passes_home.add_annotation(
        text='— Passes  -- Carries     Attacking Direction →',
        x=52.5, xref='x', y=-5, yref='y',
        showarrow=False, font=dict(size=12, color='#222222', family='Arial'))
    fig_prog_passes_home.update_layout(
        xaxis=dict(range=[-5, 140]), margin=dict(l=0, r=0, t=0, b=0),
    )

    # ── fig_prog_passes_away ──────────────────────────────────────────────────
    prog_away = prog_pass_df[prog_pass_df['team_position'] == 'away'].copy()
    prog_away['plot_x_m']     = 105 - prog_away['plot_x']
    prog_away['plot_y_m']     = 68  - prog_away['plot_y']
    prog_away['plot_end_x_m'] = 105 - prog_away['plot_end_x']
    prog_away['plot_end_y_m'] = 68  - prog_away['plot_end_y']

    y_m_plot = 68 - prog_away['plot_y']
    prog_away['zone'] = np.select(
        [y_m_plot < ROW_H,
         (y_m_plot >= ROW_H) & (y_m_plot <= ROW_H * 2),
         y_m_plot > ROW_H * 2],
        ['Left', 'Center', 'Right'], default='Center',
    )
    zone_stats_away = (prog_away.groupby('zone', sort=False).size()
                       .reset_index(name='count')
                       .set_index('zone').reindex(['Left', 'Center', 'Right']).reset_index())
    zone_stats_away['count'] = zone_stats_away['count'].fillna(0).astype(int)

    prog_carry_away = carry_df[
        (carry_df['team_position'] == 'away') &
        (carry_df['progressive'] == 1) &
        (carry_df['plot_end_x'] > 52.5)
    ].copy()
    prog_carry_away['plot_x_m']     = 105 - prog_carry_away['plot_x']
    prog_carry_away['plot_y_m']     = 68  - prog_carry_away['plot_y']
    prog_carry_away['plot_end_x_m'] = 105 - prog_carry_away['plot_end_x']
    prog_carry_away['plot_end_y_m'] = 68  - prog_carry_away['plot_end_y']
    _y_m_carry_a = 68 - prog_carry_away['plot_y']
    prog_carry_away['zone'] = np.select(
        [_y_m_carry_a < ROW_H,
         (_y_m_carry_a >= ROW_H) & (_y_m_carry_a <= ROW_H * 2),
         _y_m_carry_a > ROW_H * 2],
        ['Left', 'Center', 'Right'], default='Center',
    )
    carry_zone_a = prog_carry_away.groupby('zone').size().to_dict()

    zone_y_centers_away = {'Left': ROW_H * 0.5, 'Center': ROW_H * 1.5, 'Right': ROW_H * 2.5}
    zone_colors_away    = {'Left': '#C0392B',    'Center': '#2980B9',    'Right': '#27AE60'}

    fig_prog_passes_away = make_pitch4()
    for _, r in prog_away.iterrows():
        fig_prog_passes_away.add_annotation(
            x=r['plot_end_x_m'], y=r['plot_end_y_m'], ax=r['plot_x_m'], ay=r['plot_y_m'],
            xref='x', yref='y', axref='x', ayref='y',
            text='', showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
            arrowcolor=zone_colors_away.get(r['zone'], AWAY_DARK), opacity=0.5,
        )
    _add_carry_traces(fig_prog_passes_away, prog_carry_away, 'black',
                      xcol='plot_x_m', ycol='plot_y_m', xend='plot_end_x_m', yend='plot_end_y_m')
    for _, zr in zone_stats_away.iterrows():
        z = zr['zone']
        fig_prog_passes_away.add_annotation(
            text=f"<b>{z}:</b><br>P: {int(zr['count'])}<br>C: {carry_zone_a.get(z, 0)}",
            x=-2, y=zone_y_centers_away[z], xref='x', yref='y', showarrow=False,
            font=dict(size=11, color=zone_colors_away[z]), align='right', xanchor='right',
        )
    fig_prog_passes_away.add_annotation(
        text='← Attacking Direction     — Passes  -- Carries',
        x=52.5, xref='x', y=-5, yref='y',
        showarrow=False, font=dict(size=12, color='#222222', family='Arial'))
    fig_prog_passes_away.update_layout(
        xaxis=dict(range=[-35, 110]), margin=dict(l=0, r=0, t=0, b=0),
    )

    # ── fig_final_third_home ──────────────────────────────────────────────────
    ent   = f3_entries[(f3_entries['team_position'] == 'home') &
                       (f3_entries['to_plot'] == 1) &
                       (f3_entries['fin_zone'].isin(KEY_ZONES))].copy()
    zone_stats_f3 = (ent.groupby('fin_zone', sort=False).size()
                     .reset_index(name='count')
                     .set_index('fin_zone').reindex(KEY_ZONES, fill_value=0).reset_index())

    carry_ent_h = carry_f3[(carry_f3['team_position'] == 'home') &
                            (carry_f3['fin_zone'].isin(KEY_ZONES))].copy()
    carry_f3_zone_h = carry_ent_h.groupby('fin_zone').size().to_dict()

    zone_cfg = {
        'Z14': {'y': 1.5 * ROW_H,                 'label': 'Zone 14',          'color': '#27AE60'},
        'LHS': {'y': (2 * ROW_H + LW_SPLIT) / 2,  'label': 'Left Half Space',  'color': '#B8860B'},
        'RHS': {'y': (RW_SPLIT + ROW_H) / 2,       'label': 'Right Half Space', 'color': '#B8860B'},
    }

    fig_final_third_home = make_pitch_zones_v2()
    _anns_f3h = []
    for _a in fig_final_third_home.layout.annotations:
        _d = _a.to_plotly_json()
        if _d.get('text') == 'Attacking Direction →':
            _d['text'] = '— Passes  -- Carries     Attacking Direction →'
        _anns_f3h.append(_d)
    fig_final_third_home.update_layout(annotations=_anns_f3h)
    for _, r in ent.iterrows():
        fig_final_third_home.add_annotation(
            x=r['plot_end_x'], y=r['plot_end_y'], ax=r['plot_x'], ay=r['plot_y'],
            xref='x', yref='y', axref='x', ayref='y',
            text='', showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
            arrowcolor=ARROW_COLORS[r['fin_zone']], opacity=0.5,
        )
    _add_carry_traces(fig_final_third_home, carry_ent_h, 'black')
    for _, zr in zone_stats_f3.iterrows():
        z   = zr['fin_zone']
        cfg = zone_cfg[z]
        fig_final_third_home.add_annotation(
            text=f"<b>{cfg['label']}:</b><br>P: {int(zr['count'])}<br>C: {carry_f3_zone_h.get(z, 0)}",
            x=1, y=cfg['y'], xref='x', yref='y', showarrow=False,
            font=dict(size=10, color=cfg['color']), align='left', xanchor='left',
        )
    fig_final_third_home.update_layout(
        xaxis=dict(range=[-5, 110]), margin=dict(l=0, r=0, t=0, b=0),
    )

    # ── fig_final_third_away ──────────────────────────────────────────────────
    ent_a = f3_entries[(f3_entries['team_position'] == 'away') &
                       (f3_entries['to_plot'] == 1) &
                       (f3_entries['fin_zone'].isin(KEY_ZONES))].copy()
    ent_a['plot_x_m']     = 105 - ent_a['plot_x']
    ent_a['plot_y_m']     = 68  - ent_a['plot_y']
    ent_a['plot_end_x_m'] = 105 - ent_a['plot_end_x']
    ent_a['plot_end_y_m'] = 68  - ent_a['plot_end_y']

    zone_stats_f3a = (ent_a.groupby('fin_zone', sort=False).size()
                      .reset_index(name='count')
                      .set_index('fin_zone').reindex(KEY_ZONES, fill_value=0).reset_index())

    carry_ent_a = carry_f3[(carry_f3['team_position'] == 'away') &
                            (carry_f3['fin_zone'].isin(KEY_ZONES))].copy()
    carry_ent_a['plot_x_m']     = 105 - carry_ent_a['plot_x']
    carry_ent_a['plot_y_m']     = 68  - carry_ent_a['plot_y']
    carry_ent_a['plot_end_x_m'] = 105 - carry_ent_a['plot_end_x']
    carry_ent_a['plot_end_y_m'] = 68  - carry_ent_a['plot_end_y']
    carry_f3_zone_a = carry_ent_a.groupby('fin_zone').size().to_dict()

    def _mx(x): return 105 - x
    def _my(y): return 68  - y

    fig_final_third_away = make_pitch_zones_v2()

    new_shapes = []
    for s in fig_final_third_away.layout.shapes:
        d = s.to_plotly_json()
        if d.get('type') == 'rect':
            d['x0'], d['x1'] = _mx(d['x1']), _mx(d['x0'])
            d['y0'], d['y1'] = _my(d['y1']), _my(d['y0'])
        elif d.get('type') == 'line':
            d['x0'], d['x1'] = _mx(d['x0']), _mx(d['x1'])
            d['y0'], d['y1'] = _my(d['y0']), _my(d['y1'])
        new_shapes.append(d)
    fig_final_third_away.update_layout(shapes=new_shapes)

    for trace in fig_final_third_away.data:
        if trace.x is not None:
            trace.x = tuple(_mx(xi) for xi in trace.x)
        if trace.y is not None:
            trace.y = tuple(_my(yi) for yi in trace.y)

    new_anns = []
    for ann in fig_final_third_away.layout.annotations:
        d = ann.to_plotly_json()
        if d.get('xref', '') == 'x':
            d['x'] = _mx(d['x'])
        ann_y = d.get('y', 0)
        if d.get('yref', '') == 'y' and 0 <= ann_y <= 68:
            d['y'] = _my(ann_y)
        if d.get('text') == 'Attacking Direction →':
            d['text'] = '← Attacking Direction     — Passes  -- Carries'
        new_anns.append(d)
    fig_final_third_away.update_layout(annotations=new_anns)

    zone_cfg_a = {
        'Z14': {'y': 1.5 * ROW_H,                'label': 'Zone 14',          'color': '#27AE60'},
        'LHS': {'y': (RW_SPLIT + ROW_H) / 2,     'label': 'Left Half Space',  'color': '#B8860B'},
        'RHS': {'y': (2 * ROW_H + LW_SPLIT) / 2, 'label': 'Right Half Space', 'color': '#B8860B'},
    }

    for _, r in ent_a.iterrows():
        fig_final_third_away.add_annotation(
            x=r['plot_end_x_m'], y=r['plot_end_y_m'], ax=r['plot_x_m'], ay=r['plot_y_m'],
            xref='x', yref='y', axref='x', ayref='y',
            text='', showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
            arrowcolor=ARROW_COLORS[r['fin_zone']], opacity=0.5,
        )
    _add_carry_traces(fig_final_third_away, carry_ent_a, 'black',
                      xcol='plot_x_m', ycol='plot_y_m', xend='plot_end_x_m', yend='plot_end_y_m')
    for _, zr in zone_stats_f3a.iterrows():
        z   = zr['fin_zone']
        cfg = zone_cfg_a[z]
        fig_final_third_away.add_annotation(
            text=f"<b>{cfg['label']}:</b><br>P: {int(zr['count'])}<br>C: {carry_f3_zone_a.get(z, 0)}",
            x=104, y=cfg['y'], xref='x', yref='y', showarrow=False,
            font=dict(size=10, color=cfg['color']), align='right', xanchor='right',
        )
    fig_final_third_away.update_layout(
        xaxis=dict(range=[-5, 110], showgrid=False, zeroline=False, visible=False,
                   scaleanchor='y', scaleratio=1),
        margin=dict(l=0, r=0, t=0, b=0),
    )

    # ── fig_shots ─────────────────────────────────────────────────────────────
    def _shot_arrow_traces(df_sub, color, line_width=1.5, arrow_size=8,
                           xcol='plot_x', ycol='plot_y', xend='plot_end_x', yend='plot_end_y'):
        """Shot arrows as scatter traces so layer order can be controlled."""
        if df_sub.empty:
            return []
        xs, ys = [], []
        for _, r in df_sub.iterrows():
            xs += [r[xcol], r[xend], None]
            ys += [r[ycol], r[yend], None]
        shaft = go.Scatter(
            x=xs, y=ys, mode='lines',
            line=dict(color=color, width=line_width),
            showlegend=False, hoverinfo='skip',
        )
        dx = (df_sub[xend] - df_sub[xcol]).values
        dy = (df_sub[yend] - df_sub[ycol]).values
        angles = (90 - np.degrees(np.arctan2(dy, dx))) % 360
        head = go.Scatter(
            x=df_sub[xend].tolist(), y=df_sub[yend].tolist(),
            mode='markers',
            marker=dict(symbol='arrow', size=arrow_size, color=color,
                        angle=angles.tolist(), line=dict(width=0)),
            showlegend=False, hoverinfo='skip',
        )
        return [shaft, head]

    def _add_shot_circles(fig, df_sub, fill_color, outline_color,
                          size=8.5, line_width=1.5,
                          customdata=None, hovertemplate=None,
                          xcol='plot_x', ycol='plot_y'):
        if df_sub.empty:
            return
        hover_kw = (dict(customdata=customdata, hovertemplate=hovertemplate)
                    if customdata is not None else dict(hoverinfo='skip'))
        fig.add_trace(go.Scatter(
            x=df_sub[xcol], y=df_sub[ycol], mode='markers',
            marker=dict(size=size, color=fill_color,
                        line=dict(color=outline_color, width=line_width), symbol='circle'),
            showlegend=False, **hover_kw,
        ))

    def _shot_goal_hover(row):
        jersey = int(row['Jersey Number']) if pd.notna(row['Jersey Number']) else '?'
        player = name_lookup.get(row['player_id'], '?')
        return f"{fmt_min(int(row['time_min']), int(row['period_id']))} #{jersey} {player}"

    def _build_shots_fig(team_pos):
        _color       = HOME_COLOUR if team_pos == 'home' else AWAY_COLOUR
        _arrow_color = HOME_DARK   if team_pos == 'home' else AWAY_DARK
        _df    = shot_df[shot_df['team_position'] == team_pos].copy()
        _mo    = _df['own goal'].notna() & (_df['own goal'] != '')
        _mn    = (_df['on_target'] == 0) & (_df['event'] != 'Goal')
        _mt    = (_df['on_target'] == 1) & (_df['event'] != 'Goal')
        _mg    = (_df['event'] == 'Goal') & ~_mo
        _gh    = [_shot_goal_hover(r) for _, r in _df[_mg].iterrows()]
        _vc    = dict(xcol='plot_vx', ycol='plot_vy', xend='plot_end_vx', yend='plot_end_vy')

        # Stats counts
        _n_shots = len(_df)
        _n_ot    = int(_mt.sum()) + int(_mg.sum())
        _n_goals = int(_mg.sum())
        _n_ww    = int((_df['event'] == 'Post').sum())

        fig = make_pitch_v_top()
        fig.update_shapes(layer='below')

        # ── shots on pitch ────────────────────────────────────────────────────
        if not _df[_mn].empty:
            fig.add_trace(go.Scatter(
                x=_df[_mn]['plot_vx'], y=_df[_mn]['plot_vy'], mode='markers',
                marker=dict(size=6, color='#888888', symbol='x',
                            #line=dict(color='#888888', width=1.5)
                            ),
                showlegend=False, hoverinfo='skip'))
        _add_shot_circles(fig, _df[_mt], 'white', '#888888',
                          size=7, line_width=1,
                          xcol='plot_vx', ycol='plot_vy')
        for _t in _shot_arrow_traces(_df[_mg], _arrow_color, **_vc):
            fig.add_trace(_t)
        _add_shot_circles(fig, _df[_mg], _color, 'white',
                          size=8, line_width=1.5,
                          customdata=_gh, hovertemplate='%{customdata}<extra></extra>',
                          xcol='plot_vx', ycol='plot_vy')

        # ── goalpost rectangle on pitch ───────────────────────────────────────
        fig.add_shape(type='rect', x0=34-3.66, y0=105, x1=34+3.66, y1=105.5,
                      line=dict(color='#888888', width=1.5),
                      fillcolor='rgba(0,0,0,0)')

        # ── goalpost illustration + stats panel ───────────────────────────────
        _GP_W  = 30                           # illustration width (data units)
        _GP_H  = _GP_W * (2.44 / 7.32)       # ≈ 10  (maintains 7.32:2.44 ratio)
        _GP_X0 = 34 - _GP_W / 2              # 19
        _GP_X1 = 34 + _GP_W / 2              # 49
        _GP_Y0 = 112                          # ground line
        _GP_Y1 = _GP_Y0 + _GP_H              # ≈ 122  (crossbar)
        _GP_GL = 5                            # ground-line extension beyond posts
        _xl    = _GP_X0 - _GP_GL - 1         # 13  – right-anchor x for left labels
        _xr    = _GP_X1 + _GP_GL + 1         # 55  – left-anchor x for right labels

        # ground line (black, longer)
        fig.add_shape(type='line',
                      x0=_GP_X0 - _GP_GL, y0=_GP_Y0,
                      x1=_GP_X1 + _GP_GL, y1=_GP_Y0,
                      line=dict(color='black', width=2))
        # goalpost frame (#AAAAAA)
        fig.add_shape(type='rect',
                      x0=_GP_X0, y0=_GP_Y0, x1=_GP_X1, y1=_GP_Y1,
                      line=dict(color='#AAAAAA', width=1.5),
                      fillcolor='rgba(0,0,0,0)')

        # shot markers in the goalpost illustration
        _sx = (_GP_W / 2) / 3.66             # horizontal scale (goal half-width → illus units)
        _sz = _GP_H / 38                      # vertical scale   (Z coord 38 ≈ crossbar → illus height)

        def _illus_xy(sub):
            ix = 34 + (sub['plot_end_vx'] - 34) * _sx
            iy = _GP_Y0 + sub['Goal Mouth Z Coordinate'].clip(0, 50) * _sz
            return ix.values, iy.values

        _mn_v = _df[_mn & _df['Goal Mouth Z Coordinate'].notna()]
        if not _mn_v.empty:
            ix, iy = _illus_xy(_mn_v)
            fig.add_trace(go.Scatter(
                x=ix, y=iy, mode='markers',
                marker=dict(size=5, color='#888888', symbol='x',
                            #line=dict(color='#888888', width=1)
                            ),
                showlegend=False, hoverinfo='skip'))

        _mt_v = _df[_mt & _df['Goal Mouth Z Coordinate'].notna()]
        if not _mt_v.empty:
            ix, iy = _illus_xy(_mt_v)
            fig.add_trace(go.Scatter(
                x=ix, y=iy, mode='markers',
                marker=dict(size=7, color='white', symbol='circle',
                            line=dict(color="#888888", width=1)),
                showlegend=False, hoverinfo='skip'))

        _mg_v = _df[_mg & _df['Goal Mouth Z Coordinate'].notna()]
        if not _mg_v.empty:
            ix, iy = _illus_xy(_mg_v)
            _gh_v = [_shot_goal_hover(r) for _, r in _mg_v.iterrows()]
            fig.add_trace(go.Scatter(
                x=ix, y=iy, mode='markers',
                marker=dict(size=8, color=_color, symbol='circle',
                            line=dict(color='white', width=1.5)),
                showlegend=False,
                customdata=_gh_v,
                hovertemplate='%{customdata}<extra></extra>'))

        fig.add_annotation(
            xref='x', yref='y',
            x=34, y=52.5, xanchor='center', yanchor='top',
            text=(f"<span style='color:{_color}; font-size:18px'>●</span> Goal"
                  f"&nbsp;&nbsp;&nbsp;<span style='color:#888888; font-size:18px'>○</span> On Target"
                  f"&nbsp;&nbsp;&nbsp;<span style='color:#888888; font-size:14px'>✕</span> Off Target"),
            showarrow=False, font=dict(size=10, color='#222222'),
        )
        fig.update_layout(
            yaxis=dict(range=[52, 130]),
            margin=dict(l=0, r=0, t=0, b=32),
        )
        return fig

    fig_shots_home = _build_shots_fig('home')
    fig_shots_away = _build_shots_fig('away')

    # ── fig_receive_hm ────────────────────────────────────────────────────────
    _col_edges_hm = [0, 17.5, 35, 52.5, 70, 87.5, 105]
    _row_h_hm     = 68 / 5

    home_receive = pass_receive[
        (pass_receive['team_position'] == 'home') &
        pass_receive['plot_end_x'].notna() &
        pass_receive['plot_end_y'].notna()
    ].copy()
    home_receive['zone'] = home_receive.apply(lambda r: get_zone(r['plot_end_x'], r['plot_end_y']), axis=1)

    _zone_counts_hm = home_receive['zone'].value_counts().to_dict()
    _total_hm       = len(home_receive)
    _max_hm         = max(_zone_counts_hm.values()) if _zone_counts_hm else 1
    _hr, _hg, _hb   = (int((HOME_DARK if HOME_BRIGHT else HOME_COLOUR).lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

    fig_receive_hm = make_pitch_30zones()
    fig_receive_hm.layout.annotations = []

    for _c in range(6):
        _x0, _x1 = _col_edges_hm[_c], _col_edges_hm[_c + 1]
        for _r in range(5):
            _zone  = _c * 5 + _r + 1
            _y1    = 68 - _row_h_hm * _r
            _y0    = 68 - _row_h_hm * (_r + 1)
            _count = _zone_counts_hm.get(_zone, 0)
            _pct   = 100 * _count / _total_hm if _total_hm > 0 else 0
            _alpha = 0.08 + 0.72 * (_count / _max_hm)
            _txt_color = 'white' if _alpha > 0.7 else 'black'
            fig_receive_hm.add_shape(type='rect', x0=_x0, y0=_y0, x1=_x1, y1=_y1,
                                     fillcolor=f'rgba({_hr},{_hg},{_hb},{_alpha:.2f})',
                                     line=dict(width=0), layer='below')
            fig_receive_hm.add_annotation(
                text=f'{_count}<br>{_pct:.1f}%', x=(_x0+_x1)/2, xref='x',
                y=(_y0+_y1)/2, yref='y', showarrow=False,
                font=dict(size=10, color=_txt_color, weight=500),
            )
    fig_receive_hm.add_annotation(text='Attacking Direction →', x=52.5, xref='x', y=-5, yref='y',
                                  showarrow=False, font=dict(size=12, color='#222222', family='Arial'))
    fig_receive_hm.update_layout(margin=dict(l=0, r=0, t=0, b=0))

    # ── fig_receive_hm_a ──────────────────────────────────────────────────────
    away_receive = pass_receive[
        (pass_receive['team_position'] == 'away') &
        pass_receive['plot_end_x'].notna() &
        pass_receive['plot_end_y'].notna()
    ].copy()
    away_receive['plot_end_x'] = 105 - away_receive['plot_end_x']
    away_receive['plot_end_y'] = 68  - away_receive['plot_end_y']
    away_receive['zone'] = away_receive.apply(lambda r: get_zone(r['plot_end_x'], r['plot_end_y']), axis=1)

    _zone_counts_hm_a = away_receive['zone'].value_counts().to_dict()
    _total_hm_a       = len(away_receive)
    _max_hm_a         = max(_zone_counts_hm_a.values()) if _zone_counts_hm_a else 1
    _ar, _ag, _ab     = (int((AWAY_DARK if AWAY_BRIGHT else AWAY_COLOUR).lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

    fig_receive_hm_a = make_pitch_30zones()
    fig_receive_hm_a.layout.annotations = []

    for _c in range(6):
        _x0, _x1 = _col_edges_hm[_c], _col_edges_hm[_c + 1]
        for _r in range(5):
            _zone  = _c * 5 + _r + 1
            _y1    = 68 - _row_h_hm * _r
            _y0    = 68 - _row_h_hm * (_r + 1)
            _count = _zone_counts_hm_a.get(_zone, 0)
            _pct   = 100 * _count / _total_hm_a if _total_hm_a > 0 else 0
            _alpha = 0.08 + 0.72 * (_count / _max_hm_a)
            _txt_color_a = 'white' if _alpha > 0.7 else 'black'
            fig_receive_hm_a.add_shape(type='rect', x0=_x0, y0=_y0, x1=_x1, y1=_y1,
                                       fillcolor=f'rgba({_ar},{_ag},{_ab},{_alpha:.2f})',
                                       line=dict(width=0), layer='below')
            fig_receive_hm_a.add_annotation(
                text=f'{_count}<br>{_pct:.1f}%', x=(_x0+_x1)/2, xref='x',
                y=(_y0+_y1)/2, yref='y', showarrow=False,
                font=dict(size=10, color=_txt_color_a, weight=500),
            )
    fig_receive_hm_a.add_annotation(text='← Attacking Direction', x=52.5, xref='x', y=-5, yref='y',
                                    showarrow=False, font=dict(size=12, color='#222222', family='Arial'))
    fig_receive_hm_a.update_layout(margin=dict(l=0, r=0, t=0, b=0))

    # ── fig_def_action_home ───────────────────────────────────────────────────
    _col_edges_def = [0, 17.5, 35, 52.5, 70, 87.5, 105]
    _row_h_def     = 68 / 5

    home_def = def_action_df[def_action_df['team_position'] == 'home'].copy()
    home_def['zone'] = home_def.apply(lambda r: get_zone(r['plot_x'], r['plot_y']), axis=1)

    _total_succ_hd = int((home_def['outcome'] == 1).sum())

    _zone_stats_hd = {}
    for _z in range(1, 31):
        _zd = home_def[home_def['zone'] == _z]
        _zone_stats_hd[_z] = {'succ': int((_zd['outcome'] == 1).sum()), 'total': len(_zd)}

    _max_succ_hd = max(s['succ'] for s in _zone_stats_hd.values()) if _zone_stats_hd else 1

    fig_def_action_home = make_pitch_30zones()
    fig_def_action_home.layout.annotations = []

    for _c in range(6):
        _x0, _x1 = _col_edges_def[_c], _col_edges_def[_c + 1]
        for _r in range(5):
            _zone  = _c * 5 + _r + 1
            _y1    = 68 - _row_h_def * _r
            _y0    = 68 - _row_h_def * (_r + 1)
            _st    = _zone_stats_hd[_zone]
            _alpha = (0.08 + 0.72 * (_st['succ'] / _max_succ_hd)) if _max_succ_hd > 0 else 0.08
            _txt_color_hd = 'white' if _alpha > 0.7 else 'black'
            fig_def_action_home.add_shape(
                type='rect', x0=_x0, y0=_y0, x1=_x1, y1=_y1,
                fillcolor=f'rgba({_hr},{_hg},{_hb},{_alpha:.2f})',
                line=dict(width=0), layer='below',
            )
            fig_def_action_home.add_annotation(
                text=f"{_st['total']}",
                x=(_x0 + _x1) / 2, xref='x',
                y=(_y0 + _y1) / 2, yref='y',
                showarrow=False,
                font=dict(size=12, color=_txt_color_hd),
                align='center',
            )

    for _label, _cols, _color in [
        ('Defensive Third', [0, 1], 'red'),
        ('Midfield Third',  [2, 3], '#B8860B'),
        ('Attacking Third', [4, 5], 'green'),
    ]:
        _x_mid   = (_col_edges_def[_cols[0]] + _col_edges_def[_cols[-1] + 1]) / 2
        _succ_t  = sum(_zone_stats_hd[ci * 5 + ri + 1]['succ']  for ci in _cols for ri in range(5))
        _total_t = sum(_zone_stats_hd[ci * 5 + ri + 1]['total'] for ci in _cols for ri in range(5))
        fig_def_action_home.add_annotation(
            text=f'<b>{_label}</b><br>{_total_t}',
            x=_x_mid, xref='x', y=75, yref='y',
            showarrow=False, font=dict(size=10.5, color=_color), align='center',
        )

    fig_def_action_home.add_annotation(
        text='Attacking Direction →', x=52.5, xref='x', y=-5, yref='y',
        showarrow=False, font=dict(size=12, color='#222222', family='Arial'),
    )
    fig_def_action_home.update_layout(
        xaxis=dict(range=[-5, 110], showgrid=False, zeroline=False, visible=False,
                   scaleanchor='y', scaleratio=1),
        yaxis=dict(range=[-10, 83],  showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=0, b=0),
    )

    # ── fig_def_action_away ───────────────────────────────────────────────────
    away_def = def_action_df[def_action_df['team_position'] == 'away'].copy()
    away_def['zone'] = away_def.apply(lambda r: get_zone(r['plot_x'], r['plot_y']), axis=1)

    _total_succ_ad = int((away_def['outcome'] == 1).sum())

    _zone_stats_ad = {}
    for _z in range(1, 31):
        _zd = away_def[away_def['zone'] == _z]
        _zone_stats_ad[_z] = {'succ': int((_zd['outcome'] == 1).sum()), 'total': len(_zd)}

    _max_succ_ad = max(s['succ'] for s in _zone_stats_ad.values()) if _zone_stats_ad else 1

    fig_def_action_away = make_pitch_30zones()
    fig_def_action_away.layout.annotations = []

    for _c in range(6):
        _x0, _x1 = _col_edges_def[_c], _col_edges_def[_c + 1]
        for _r in range(5):
            _zone  = _c * 5 + _r + 1
            _y1    = 68 - _row_h_def * _r
            _y0    = 68 - _row_h_def * (_r + 1)
            _st    = _zone_stats_ad[_zone]
            _alpha = (0.08 + 0.72 * (_st['succ'] / _max_succ_ad)) if _max_succ_ad > 0 else 0.08
            _txt_color_ad = 'white' if _alpha > 0.7 else 'black'
            fig_def_action_away.add_shape(
                type='rect', x0=_x0, y0=_y0, x1=_x1, y1=_y1,
                fillcolor=f'rgba({_ar},{_ag},{_ab},{_alpha:.2f})',
                line=dict(width=0), layer='below',
            )
            fig_def_action_away.add_annotation(
                text=f"{_st['total']}",
                x=(_x0 + _x1) / 2, xref='x',
                y=(_y0 + _y1) / 2, yref='y',
                showarrow=False,
                font=dict(size=12, color=_txt_color_ad),
                align='center',
            )

    for _label, _cols, _color in [
        ('Attacking Third', [0, 1], 'green'),
        ('Midfield Third',  [2, 3], '#B8860B'),
        ('Defensive Third', [4, 5], 'red'),
    ]:
        _x_mid   = (_col_edges_def[_cols[0]] + _col_edges_def[_cols[-1] + 1]) / 2
        _succ_t  = sum(_zone_stats_ad[ci * 5 + ri + 1]['succ']  for ci in _cols for ri in range(5))
        _total_t = sum(_zone_stats_ad[ci * 5 + ri + 1]['total'] for ci in _cols for ri in range(5))
        fig_def_action_away.add_annotation(
            text=f'<b>{_label}</b><br>{_total_t}',
            x=_x_mid, xref='x', y=75, yref='y',
            showarrow=False, font=dict(size=10.5, color=_color), align='center',
        )

    for _r in range(5):
        _y_mid   = 68 - _row_h_def * _r - _row_h_def / 2
        _succ_r  = sum(_zone_stats_ad[ci * 5 + _r + 1]['succ']  for ci in range(6))
        _total_r = sum(_zone_stats_ad[ci * 5 + _r + 1]['total'] for ci in range(6))
        #fig_def_action_away.add_annotation(
        #    text=f'{_succ_r}/{_total_r}',
        #    x=-8, xref='x', y=_y_mid, yref='y',
        #    showarrow=False, font=dict(size=12, color='black', family='Arial Bold'), align='center',
        #)

    fig_def_action_away.add_annotation(
        text='← Attacking Direction', x=52.5, xref='x', y=-5, yref='y',
        showarrow=False, font=dict(size=12, color='#222222', family='Arial'),
    )
    fig_def_action_away.update_layout(
        xaxis=dict(range=[-5, 110], showgrid=False, zeroline=False, visible=False,
                   scaleanchor='y', scaleratio=1),
        yaxis=dict(range=[-10, 83],   showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=0, b=0),
    )

    # ── fig_gk_pass ───────────────────────────────────────────────────────────
    _GK_SHORT_THRESHOLD = 25  # metres — short: < 25
    _GK_LONG_THRESHOLD  = 40  # metres — long:  > 40, medium: in between

    def _gk_prep(team_pos):
        _df = pass_df[
            (pass_df['event'] == 'Pass') &
            (pass_df['position'] == 'GK') &
            (pass_df['team_position'] == team_pos) &
            (pass_df['plot_x'] <= 16.5) &
            (pass_df['plot_y'] >= 13.84) &
            (pass_df['plot_y'] <= 54.16) &
            pass_df['plot_end_x'].notna() &
            pass_df['plot_end_y'].notna()
        ].copy()
        _df['vx0'] = 68 - _df['plot_y']
        _df['vy0'] = _df['plot_x']
        _df['vx1'] = 68 - _df['plot_end_y']
        _df['vy1'] = _df['plot_end_x']
        _df['dist'] = np.sqrt((_df['vx1'] - _df['vx0'])**2 + (_df['vy1'] - _df['vy0'])**2)
        _df['dist_group'] = pd.cut(
            _df['dist'],
            bins=[0, _GK_SHORT_THRESHOLD, _GK_LONG_THRESHOLD, float('inf')],
            labels=['short', 'medium', 'long'],
            right=False,
        )
        return _df

    def _gk_stats(df_):
        _tot = max(len(df_), 1)
        _out = {}
        for _g in ['short', 'medium', 'long']:
            _sub = df_[df_['dist_group'] == _g]
            _out[_g] = {
                'suc': int((_sub['outcome'] == 1).sum()),
                'tot': len(_sub),
                'pct': round(len(_sub) / _tot * 100),
            }
        return _out

    gk_home = _gk_prep('home')
    gk_away = _gk_prep('away')
    _gks_h  = _gk_stats(gk_home)
    _gks_a  = _gk_stats(gk_away)

    _GK_GREY = '#cccccc'

    def _gk_heatmap(xs, ys):
        """Return a smoothed go.Heatmap trace for GK pass target zones."""
        _NX, _NY = 50, 80
        _xg = np.linspace(0, 68, _NX + 1)
        _yg = np.linspace(0, 105, _NY + 1)
        if len(xs) == 0:
            return None
        _h, _, _ = np.histogram2d(xs, ys, bins=[_xg, _yg])
        # separable Gaussian blur (sigma ≈ 4 bins ≈ 5–6 m)
        _sigma = 4
        _r = int(round(3 * _sigma))
        _k = np.exp(-np.arange(-_r, _r + 1) ** 2 / (2 * _sigma ** 2))
        _k /= _k.sum()
        _h = np.apply_along_axis(lambda v: np.convolve(v, _k, mode='same'), 0, _h.astype(float))
        _h = np.apply_along_axis(lambda v: np.convolve(v, _k, mode='same'), 1, _h)
        _xc = (_xg[:-1] + _xg[1:]) / 2
        _yc = (_yg[:-1] + _yg[1:]) / 2
        return go.Heatmap(
            x=_xc, y=_yc, z=_h.T,
            colorscale=[[0, 'white'],[0.3, 'yellow'], [1, 'red']],
            opacity=0.3,
            showscale=False,
            zsmooth='best',
            hoverinfo='skip',
        )

    def _make_gk_fig(df_gk, stats, colour, is_home):
        _gk_arrow_col = _darken_hex(colour) if (HOME_BRIGHT if is_home else AWAY_BRIGHT) else colour
        fig = make_pitch_v()

        # smooth target-zone heatmap (rendered below arrows via trace ordering)
        _hm = _gk_heatmap(df_gk['vx1'].values, df_gk['vy1'].values)
        if _hm is not None:
            fig.add_trace(_hm)

        for _, _r in df_gk[df_gk['outcome'] != 1].iterrows():
            fig.add_annotation(
                x=_r['vx1'], y=_r['vy1'], ax=_r['vx0'], ay=_r['vy0'],
                xref='x', yref='y', axref='x', ayref='y',
                text='', showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
                arrowcolor=_GK_GREY,
            )
        for _, _r in df_gk[df_gk['outcome'] == 1].iterrows():
            fig.add_annotation(
                x=_r['vx1'], y=_r['vy1'], ax=_r['vx0'], ay=_r['vy0'],
                xref='x', yref='y', axref='x', ayref='y',
                text='', showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
                arrowcolor=_gk_arrow_col, opacity=0.7,
            )

        for _g, _label, _xpos in [
            ('short',  'Short',  11),
            ('medium', 'Medium', 34),
            ('long',   'Long',   57),
        ]:
            _s = stats[_g]
            fig.add_annotation(
                text=(f"<b>{_label}</b><br>"
                      f"{_s['suc']}/{_s['tot']}<br>"
                      f"{_s['pct']}%"),
                x=_xpos, y=88, xref='x', yref='y',
                showarrow=False, font=dict(size=11, color=SECONDARY_COL),
                xanchor='center', yanchor='bottom', align='center',
            )

        if is_home:
            fig.add_annotation(
                text='Attacking Direction →', x=-3, y=52.5,
                xref='x', yref='y', showarrow=False,
                font=dict(size=11, color='#222222', family='Arial'),
                textangle=-90, xanchor='center', yanchor='middle',
            )
        else:
            fig.add_annotation(
                text='← Attacking Direction', x=71, y=52.5,
                xref='x', yref='y', showarrow=False,
                font=dict(size=11, color='#222222', family='Arial'),
                textangle=90, xanchor='center', yanchor='middle',
            )
        _x_range = [-5, 70] if is_home else [-2, 73]
        fig.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', showlegend=False,
            xaxis=dict(range=_x_range, showgrid=False, zeroline=False, visible=False,
                       scaleanchor='y', scaleratio=1),
            yaxis=dict(range=[-1, 106], showgrid=False, zeroline=False, visible=False),
            margin=dict(l=0, r=0, t=0, b=0),
        )
        return fig

    fig_gk_pass_home = _make_gk_fig(gk_home, _gks_h, HOME_COLOUR, is_home=True)
    fig_gk_pass_away = _make_gk_fig(gk_away, _gks_a, AWAY_COLOUR, is_home=False)

    # ── Crosses from open play & set-pieces ──────────────────────────────────
    _cross_cols_needed = ['event','team_position','x','y','outcome',
                          'Free kick taken','Corner taken','Throw In',
                          'Inswinger','Outswinger','Pass End X','Pass End Y']
    _df_cross_raw = df[[c for c in _cross_cols_needed if c in df.columns]].copy()
    for _cc in ['Inswinger', 'Outswinger']:
        if _cc not in _df_cross_raw.columns:
            _df_cross_raw[_cc] = float('nan')
    _df_sp_passes = _df_cross_raw[_df_cross_raw['event'] == 'Pass'].reset_index(drop=True)

    _PW_V, _PL_V, _PH_V, _CX_V = 68.0, 105.0, 52.5, 34.0
    _CZONES = {
        'Left Wide':  dict(x0=0,                  x1=_PW_V/6,         y0=_PH_V, y1=_PL_V),
        'Left HS':    dict(x0=_PW_V/6,            x1=_PW_V/3,         y0=70,    y1=_PL_V),
        'Right HS':   dict(x0=_PW_V-_PW_V/3,     x1=_PW_V-_PW_V/6,  y0=70,    y1=_PL_V),
        'Right Wide': dict(x0=_PW_V-_PW_V/6,     x1=_PW_V,           y0=_PH_V, y1=_PL_V),
    }
    _CZONE_CENTRES = {
        'Left Wide':  ((0 + _PW_V/6) / 2,                          (_PH_V + _PL_V) / 2),
        'Left HS':    ((_PW_V/6 + _PW_V/3) / 2,                    (70 + _PL_V) / 2),
        'Right HS':   ((_PW_V-_PW_V/3 + _PW_V-_PW_V/6) / 2,       (70 + _PL_V) / 2),
        'Right Wide': ((_PW_V-_PW_V/6 + _PW_V) / 2,                (_PH_V + _PL_V) / 2),
    }
    _WIDE_X0_V = _CX_V - 20.16          # 13.84 — full box left edge
    _WIDE_X1_V = _CX_V + 20.16          # 54.16 — full box right edge
    _HS_X0_V   = _PW_V / 3              # 22.67 — middle-box left edge
    _HS_X1_V   = _PW_V - _PW_V / 3     # 45.33 — middle-box right edge
    _BOX_Y0_V, _BOX_Y1_V = 88.5, 105.0
    _BOX_X0_SP, _BOX_X1_SP, _BOX_Y_SP = _CX_V - 20.16, _CX_V + 20.16, 88.5

    def _tv(x100, y100):
        return 68 - (y100 / 100 * 68), x100 / 100 * 105

    def _assign_czone(px, py):
        for _zn, _zd in _CZONES.items():
            if _zd['x0'] <= px <= _zd['x1'] and _zd['y0'] <= py <= _zd['y1']:
                return _zn
        return None

    _C_FAIL   = 'rgba(160,160,160,0.80)'
    _C_SUC_HS = 'rgba(0,188,212,0.90)'   # cyan — successful half-space cross
    _C_SUC_WD = 'rgba(210,105,30,0.90)'  # orange — successful wide-area cross
    _HS_ZONES = {'Left HS', 'Right HS'}
    _WD_ZONES = {'Left Wide', 'Right Wide'}

    def _build_crosses_fig(team_pos):
        _mask = (
            (_df_sp_passes['team_position'] == team_pos) &
            _df_sp_passes['Free kick taken'].isna() &
            _df_sp_passes['Throw In'].isna() &
            _df_sp_passes['Corner taken'].isna()
        )
        _recs = []
        for _, _row in _df_sp_passes[_mask].iterrows():
            _px, _py = _tv(_row['x'], _row['y'])
            _zone = _assign_czone(_px, _py)
            if _zone is None:
                continue
            _ex, _ey = _tv(_row['Pass End X'], _row['Pass End Y'])
            if _ey <= _BOX_Y0_V:
                continue
            if _zone == 'Left Wide'  and not (_HS_X0_V   <= _ex <= _WIDE_X1_V):
                continue
            if _zone == 'Right Wide' and not (_WIDE_X0_V <= _ex <= _HS_X1_V):
                continue
            if _zone in _HS_ZONES and not (_HS_X0_V <= _ex <= _HS_X1_V):
                continue
            _recs.append(dict(px=_px, py=_py, ex=_ex, ey=_ey, zone=_zone, outcome=int(_row['outcome'])))
        _df_p = (pd.DataFrame(_recs) if _recs
                 else pd.DataFrame(columns=['px','py','ex','ey','zone','outcome']))

        def _row_color(r):
            if r['outcome'] == 0:
                return _C_FAIL
            return _C_SUC_HS if r['zone'] in _HS_ZONES else _C_SUC_WD

        _fig = make_pitch_v_top_zones()
        # unsuccessful first, successful on top
        for _suc in [0, 1]:
            _sub = _df_p[_df_p['outcome'] == _suc]
            for _, _r in _sub.iterrows():
                _col = _row_color(_r)
                _fig.add_annotation(
                    x=_r['ex'], y=_r['ey'], ax=_r['px'], ay=_r['py'],
                    xref='x', yref='y', axref='x', ayref='y',
                    showarrow=True, arrowhead=2, arrowsize=0.8, arrowwidth=1.5, arrowcolor=_col,
                )
        for _suc in [0, 1]:
            _sub = _df_p[_df_p['outcome'] == _suc]
            if _sub.empty:
                continue
            _colors = _sub.apply(_row_color, axis=1).tolist()
            _fig.add_trace(go.Scatter(
                x=_sub['px'].tolist(), y=_sub['py'].tolist(), mode='markers',
                marker=dict(size=10, color=_colors, line=dict(color='white', width=1.5)),
                showlegend=False, hoverinfo='skip',
            ))
        _n_lhs = len(_df_p[_df_p['zone'] == 'Left HS'])
        _n_rhs = len(_df_p[_df_p['zone'] == 'Right HS'])
        _n_lw  = len(_df_p[_df_p['zone'] == 'Left Wide'])
        _n_rw  = len(_df_p[_df_p['zone'] == 'Right Wide'])
        _cx_ann = 34.0
        for _ann_txt, _ann_col, _ann_y in [
            (f'<b>Half Spaces:</b><br>L: {_n_lhs}    R: {_n_rhs}', '#00BCD4', 68.0),
            (f'<b>Wide Areas:</b><br>L: {_n_lw}    R: {_n_rw}',   '#D2691E', 58.0),
        ]:
            _fig.add_annotation(
                x=_cx_ann, y=_ann_y, xref='x', yref='y',
                text=_ann_txt,
                showarrow=False, font=dict(size=11, color=_ann_col),
                xanchor='center', yanchor='middle',
                bgcolor='rgba(0,0,0,0)', borderwidth=0,
            )
        _fig.add_annotation(
            xref='x', yref='y',
            x=34, y=52.4, xanchor='center', yanchor='top',
            text=(f"<span style='color:rgba(160,160,160,0.90); font-size:18px'>●</span> Attempted"
                  f"&nbsp;&nbsp;&nbsp;<span style='color:rgba(0,188,212,0.90); font-size:18px'>●</span>"
                  f"<span style='color:rgba(210,105,30,0.90); font-size:18px'>●</span> Completed"),
            showarrow=False, font=dict(size=10, color='#222222'),
        )
        _fig.update_layout(margin=dict(l=0, r=0, t=3, b=20))
        return _fig

    fig_crosses_home = _build_crosses_fig('home')
    fig_crosses_away = _build_crosses_fig('away')

    _SP_TYPE_CFG = {
        'Free Kick': dict(col='Free kick taken', color='#27AE60'),
        'Corner':    dict(col='Corner taken',    color='#E74C3C'),
        'Throw In':  dict(col='Throw In',        color='#2980B9'),
    }
    _SP_SHORT_M, _SP_CORNER_SHORT = 32, 25

    def _sp_dist(x, y, ex, ey):
        return np.sqrt(((ex - x) * 1.05)**2 + ((ey - y) * 0.68)**2)

    def _corner_type(px, ex, ey, dist):
        if dist < _SP_CORNER_SHORT or ey < 88.5:
            return 'Short'
        return ('Front' if ex < _CX_V else 'Far') if px < _CX_V else ('Front' if ex >= _CX_V else 'Far')

    def _build_setpiece_fig(team_pos):
        _recs_sp = []
        for _, _row in _df_sp_passes[_df_sp_passes['team_position'] == team_pos].iterrows():
            for _tname, _cfg in _SP_TYPE_CFG.items():
                if pd.isna(_row[_cfg['col']]):
                    continue
                _px, _py = _tv(_row['x'], _row['y'])
                _ex, _ey = _tv(_row['Pass End X'], _row['Pass End Y'])
                if _py < _PH_V or _ey < _PH_V:
                    break
                _dist = _sp_dist(_row['x'], _row['y'], _row['Pass End X'], _row['Pass End Y'])
                _sub_cat = (_corner_type(_px, _ex, _ey, _dist) if _tname == 'Corner'
                            else ('Short' if _dist < _SP_SHORT_M else 'Long'))
                _recs_sp.append(dict(
                    type=_tname, color=_cfg['color'],
                    px=_px, py=_py, ex=_ex, ey=_ey,
                    outcome=int(_row['outcome']), sub_cat=_sub_cat,
                    inswinger=not pd.isna(_row.get('Inswinger', float('nan'))),
                    outswinger=not pd.isna(_row.get('Outswinger', float('nan'))),
                ))
                break
        _df_sp = (pd.DataFrame(_recs_sp) if _recs_sp
                  else pd.DataFrame(columns=['type','color','px','py','ex','ey',
                                             'outcome','sub_cat','inswinger','outswinger']))
        _fig = make_pitch_v_top()
        for _tname, _cfg in _SP_TYPE_CFG.items():
            _color = _cfg['color']
            _sub_t = _df_sp[_df_sp['type'] == _tname]
            if _sub_t.empty:
                continue
            for _out, _dash in [(1, 'solid'), (0, 'dot')]:
                _grp = _sub_t[_sub_t['outcome'] == _out]
                if _grp.empty:
                    continue
                _xs, _ys = [], []
                for _, _r in _grp.iterrows():
                    _xs += [_r['px'], _r['ex'], None]
                    _ys += [_r['py'], _r['ey'], None]
                _fig.add_trace(go.Scatter(
                    x=_xs, y=_ys, mode='lines',
                    line=dict(color=_color, width=1.5, dash=_dash),
                    opacity=0.4, showlegend=False, hoverinfo='skip',
                ))
            _suc = _sub_t[_sub_t['outcome'] == 1]
            if not _suc.empty:
                _fig.add_trace(go.Scatter(
                    x=_suc['ex'].tolist(), y=_suc['ey'].tolist(), mode='markers',
                    marker=dict(size=8, color='white', symbol='triangle-up',
                                line=dict(color=_color, width=1.5)),
                    showlegend=False, hoverinfo='skip',
                ))
            _unsuc = _sub_t[_sub_t['outcome'] == 0]
            if not _unsuc.empty:
                _fig.add_trace(go.Scatter(
                    x=_unsuc['ex'].tolist(), y=_unsuc['ey'].tolist(), mode='markers',
                    marker=dict(size=7, color=_color, symbol='x'),
                    showlegend=False, hoverinfo='skip',
                ))
        _corner_sub   = _df_sp[_df_sp['type'] == 'Corner']
        _corner_color = _SP_TYPE_CFG['Corner']['color']
        for _is_left, _c_label in [(True, 'Left Corners'), (False, 'Right Corners')]:
            _sc = (_corner_sub[_corner_sub['px'] < _CX_V] if _is_left
                   else _corner_sub[_corner_sub['px'] >= _CX_V])
            _text = (f"<b>{_c_label}</b><br>"
                     f"Short: {int((_sc['sub_cat']=='Short').sum())}<br>"
                     f"Front Post: {int((_sc['sub_cat']=='Front').sum())}<br>"
                     f"Far Post: {int((_sc['sub_cat']=='Far').sum())}<br>────────<br>"
                     f"Inswinger: {int(_sc['inswinger'].sum())}<br>"
                     f"Outswinger: {int(_sc['outswinger'].sum())}")
            _fig.add_annotation(
                x=-2 if _is_left else 70, y=105,
                xref='x', yref='y',
                text=_text, showarrow=False,
                font=dict(size=9.5, color=_corner_color),
                xanchor='right' if _is_left else 'left',
                yanchor='top',
                align='right' if _is_left else 'left',
            )
        for _tname, _is_left in [('Free Kick', True), ('Throw In', False)]:
            _sub_t = _df_sp[_df_sp['type'] == _tname]
            _color = _SP_TYPE_CFG[_tname]['color']
            _n_in  = int(((_sub_t['ey'] >= _BOX_Y_SP) &
                          (_sub_t['ex'] >= _BOX_X0_SP) &
                          (_sub_t['ex'] <= _BOX_X1_SP)).sum())
            _label = 'Free Kicks' if _tname == 'Free Kick' else 'Throw Ins'
            _text  = (f'<b>{_label}</b><br>'
                      f'Inside Box: {_n_in}<br>'
                      f'Outside Box: {len(_sub_t) - _n_in}')
            _fig.add_annotation(
                x=-2 if _is_left else 70, y=52.5,
                xref='x', yref='y',
                text=_text, showarrow=False,
                font=dict(size=9.5, color=_color),
                xanchor='right' if _is_left else 'left',
                yanchor='bottom',
                align='right' if _is_left else 'left',
            )
        _fig.add_annotation(
            xref='x', yref='y',
            x=34, y=52.3, xanchor='center', yanchor='top',
            text=("<span style='color:#666666; font-size:14px'>--✕</span> Attempted"
                  "&nbsp;&nbsp;&nbsp;<span style='color:#666666; font-size:14px'>—△</span> Completed"),
            showarrow=False, font=dict(size=10, color='#222222'),
        )
        _fig.update_layout(showlegend=False, margin=dict(t=0, l=40, r=40, b=12))
        return _fig

    fig_setpiece_home = _build_setpiece_fig('home')
    fig_setpiece_away = _build_setpiece_fig('away')

    # ── df_fastbreak_seq ──────────────────────────────────────────────────────
    _fb_shot_ev  = {'Goal', 'Miss', 'Post', 'Saved Shot'}
    _fb_seq_str  = {'Ball recovery', 'Keeper pick-up', 'Claim'}
    _fb_seq_keep = _fb_seq_str | {'Pass', 'Take On'} | _fb_shot_ev

    _df_fb = df[['event', 'period_id', 'time_min', 'time_sec', 'team_code', 'team_position',
                 'Jersey Number', 'player_id', 'x', 'y', 'Fast break',
                 'Goal Mouth Y Coordinate', 'Goal Mouth Z Coordinate']].reset_index(drop=True)

    _fb_seqs = []
    for _sid, _shot_i in enumerate(
        _df_fb[_df_fb['event'].isin(_fb_shot_ev) & (_df_fb['Fast break'] == 'Si')].index.tolist(),
        start=1,
    ):
        _team, _period = _df_fb.at[_shot_i, 'team_code'], _df_fb.at[_shot_i, 'period_id']
        _start = _shot_i
        for _j in range(_shot_i - 1, -1, -1):
            if _df_fb.at[_j, 'period_id'] != _period:
                break
            if _df_fb.at[_j, 'event'] in _fb_seq_str and _df_fb.at[_j, 'team_code'] == _team:
                _start = _j
                break
        _chunk = _df_fb.loc[_start:_shot_i].copy()
        _chunk = _chunk[_chunk['event'].isin(_fb_seq_keep) & (_chunk['team_code'] == _team)].copy()
        _chunk.insert(0, 'fb_seq_id', _sid)
        _fb_seqs.append(_chunk)

    df_fastbreak_seq = (
        pd.concat(_fb_seqs, ignore_index=True) if _fb_seqs
        else pd.DataFrame(columns=['fb_seq_id', 'event', 'period_id', 'time_min', 'time_sec',
                                   'team_code', 'team_position', 'Jersey Number', 'player_id',
                                   'x', 'y', 'Goal Mouth Y Coordinate', 'Goal Mouth Z Coordinate'])
    )

    def _fb_tip(row, extra=''):
        _j = int(row['Jersey Number']) if pd.notna(row['Jersey Number']) else '?'
        _n = name_lookup.get(row['player_id'], '')
        _lbl = f"{fmt_min(row['time_min'], int(row['period_id']))} #{_j} {_n}"
        return _lbl + (f'<br>{extra}' if extra else '')

    def _fb_avg(lst): return sum(lst) / len(lst) if lst else 0

    # ── fig_fastbreak_h / fig_fastbreak_a ────────────────────────────────────
    def _build_fb_fig(team_pos):
        _is_home  = team_pos == 'home'
        _colour   = HOME_COLOUR if _is_home else AWAY_COLOUR
        _goal_x   = 105.0 if _is_home else 0.0
        _stat_x   = 107   if _is_home else -2
        _stat_anc = 'left' if _is_home else 'right'
        _dir_txt  = 'Attacking Direction →' if _is_home else '← Attacking Direction'
        _x_range  = [-5, 150] if _is_home else [-45, 110]

        def _pmx(v): return v / 100 * 105 if _is_home else 105 - v / 100 * 105
        def _pmy(v): return v / 100 * 68 if _is_home else 68 - v / 100 * 68

        _df = df_fastbreak_seq[df_fastbreak_seq['team_position'] == team_pos].copy()
        _fig = make_pitch_simple()

        if not _df.empty:
            for _seqid, _grp in _df.groupby('fb_seq_id'):
                _grp = _grp.reset_index(drop=True)
                _n   = len(_grp)
                _px  = [_pmx(r['x']) for _, r in _grp.iterrows()]
                _py  = [_pmy(r['y']) for _, r in _grp.iterrows()]

                # initiation circle with hover
                _init = _grp.iloc[0]
                _fig.add_trace(go.Scatter(
                    x=[_px[0]], y=[_py[0]], mode='markers',
                    marker=dict(symbol='circle', size=10, color="#CCCCCC",
                                line=dict(color='white', width=1)),
                    showlegend=False,
                    hovertemplate=_fb_tip(_init, _init['event']) + '<extra></extra>',
                ))

                # initiation pass arrow (event 0 → 1)
                if _n > 1 and _grp.iloc[1]['event'] not in _fb_shot_ev:
                    _fig.add_annotation(
                        x=_px[1], y=_py[1], ax=_px[0], ay=_py[0],
                        xref='x', yref='y', axref='x', ayref='y',
                        arrowhead=2, arrowsize=1.2, arrowwidth=2, arrowcolor="#CCCCCC",
                        showarrow=True, text='',
                    )

                # intermediate passes / take-ons: grey dotted
                for _i in range(1, _n - 1):
                    _fig.add_shape(type='line',
                                   x0=_px[_i], y0=_py[_i], x1=_px[_i + 1], y1=_py[_i + 1],
                                   line=dict(color='#999999', width=1.5, dash='dot'))

                # shot markers
                for _i in range(1, _n):
                    _row = _grp.iloc[_i]
                    _ev  = _row['event']
                    if _ev not in _fb_shot_ev:
                        continue
                    _sx, _sy = _px[_i], _py[_i]
                    if _ev == 'Goal':
                        _raw_gmy = _row['Goal Mouth Y Coordinate']
                        if pd.notna(_raw_gmy):
                            _gmy = _raw_gmy / 100 * 68 if _is_home else 68 - _raw_gmy / 100 * 68
                        else:
                            _gmy = 34.0
                        _fig.add_annotation(
                            x=_goal_x, y=_gmy, ax=_sx, ay=_sy,
                            xref='x', yref='y', axref='x', ayref='y',
                            arrowhead=2, arrowsize=1, arrowwidth=2, arrowcolor=_colour,
                            showarrow=True, text='',
                        )
                        _fig.add_trace(go.Scatter(
                            x=[_sx], y=[_sy], mode='markers',
                            marker=dict(symbol='circle', size=11, color=_colour,
                                        line=dict(color='white', width=2)),
                            showlegend=False,
                            hovertemplate=_fb_tip(_row) + '<extra></extra>',
                        ))
                    elif _ev == 'Saved Shot':
                        _fig.add_trace(go.Scatter(
                            x=[_sx], y=[_sy], mode='markers',
                            marker=dict(symbol='circle-open', size=8, color='#777777',
                                        line=dict(color='#777777', width=2)),
                            showlegend=False, hoverinfo='skip',
                        ))
                    else:  # Miss, Post
                        _fig.add_trace(go.Scatter(
                            x=[_sx], y=[_sy], mode='markers',
                            marker=dict(symbol='x', size=8, color='#777777',
                                        line=dict(color='#777777', width=1)),
                            showlegend=False, hoverinfo='skip',
                        ))

            # stats annotation
            _sr   = _df[_df['event'].isin(_fb_shot_ev)]
            _n_seq = _df['fb_seq_id'].nunique()
            _n_g   = int((_sr['event'] == 'Goal').sum())
            _n_ot  = int(_sr['event'].isin({'Goal', 'Saved Shot'}).sum())
            _dur, _pc, _dc = [], [], []
            for _, _g in _df.groupby('fb_seq_id'):
                _s = _g['time_min'] * 60 + _g['time_sec']
                _dur.append(int(_s.iloc[-1]) - int(_s.iloc[0]))
                _pc.append(int(_g['event'].isin({'Pass', 'Take On'}).sum()))
                _xs = _g['x'].values / 100 * 105
                _ys = _g['y'].values / 100 * 68
                _dc.append(sum(math.hypot(_xs[i + 1] - _xs[i], _ys[i + 1] - _ys[i])
                               for i in range(len(_xs) - 1)))
            _fig.add_annotation(
                text=(f"<b>Fast Break Seq.</b><br>Count  {_n_seq}<br>"
                      f"Goals  {_n_g}<br>"
                      f"Shots on Target  {_n_ot}<br>"
                      f"Avg Duration  {_fb_avg(_dur):.1f} s<br>"
                      f"Avg Passes  {_fb_avg(_pc):.1f}<br>"
                      f"Avg Distance  {_fb_avg(_dc):.1f} m<br>"
                      f"<br>"
                      f"<span style='color:#AAAAAA; font-size:18px'>●</span> Initiation<br>"
                      f"<span style='color:{_colour}; font-size:18px'>●</span> Goal<br>"
                      f"<span style='color:#777777; font-size:18px'>○</span> SoT<br>"
                      f"<span style='color:#777777; font-size:14px'>✕</span> Miss"),
                x=_stat_x, y=34, xref='x', yref='y',
                showarrow=False, align=_stat_anc, xanchor=_stat_anc,
                font=dict(size=10, color='#222222'),
            )

        if _df.empty:
            _fig.add_annotation(
                x=52.5, y=34, xref='x', yref='y',
                text='No fast break sequences',
                showarrow=False,
                font=dict(size=14, color='#AAAAAA', family='Arial'),
                xanchor='center',
            )

        _fig.add_annotation(
            text=_dir_txt, x=52.5, y=-5, xref='x', yref='y',
            showarrow=False, font=dict(size=12, color='#222222', family='Arial'),
        )
        _fig.update_layout(xaxis=dict(range=_x_range), margin=dict(l=0, r=0, t=0, b=0))
        return _fig

    fig_fastbreak_h = _build_fb_fig('home')
    fig_fastbreak_a = _build_fb_fig('away')

    # ── Scoreline ─────────────────────────────────────────────────────────────
    _og_lineup = lineup['own goal'].notna() & (lineup['own goal'] != '')
    home_goals = (
        len(lineup[~_og_lineup & (lineup['event'] == 'Goal') & (lineup['team_position'] == 'home')]) +
        len(lineup[ _og_lineup & (lineup['event'] == 'Goal') & (lineup['team_position'] == 'away')])
    )
    away_goals = (
        len(lineup[~_og_lineup & (lineup['event'] == 'Goal') & (lineup['team_position'] == 'away')]) +
        len(lineup[ _og_lineup & (lineup['event'] == 'Goal') & (lineup['team_position'] == 'home')])
    )

    LINEUP_H = 426 #max(len(lineup_home), len(lineup_away)) * LINEUP_ROW_H_PX * 1.25

    # ── Layout ────────────────────────────────────────────────────────────────
    return html.Div(
        style={
            'display': 'grid',
            'gridTemplateColumns': '32% 36% 32%',
            'gridTemplateRows': '2140px',
            'padding': '2px',
            'backgroundColor': BG_COLOUR,
            'boxSizing': 'border-box',
        },
        children=[
            # ── Row 2 — left column ────────────────────────────────────────────
            make_col([
                make_table(lineup_home, height_px=LINEUP_H, style_cell_conditional=LINEUP_COL_WIDTHS,
                           style_data_conditional=LINEUP_SUB_COLORS, css=LINEUP_CSS),
                make_section_label('Home Team Progressive Passes & Carries'),
                make_graph(fig_prog_passes_home, 240),
                make_section_label('Home Team Z14 & Half-Spaces Entries'),
                make_graph(fig_final_third_home, 280),
                make_section_label('Home Team Pass Receive Heatmap'),
                make_graph(fig_receive_hm, 260),
                make_section_label('Home Team Defensive Actions Heatmap'),
                make_graph(fig_def_action_home, 300),
                make_section_label('Home Team Fast Break Sequences'),
                make_graph(fig_fastbreak_h, 230),
                make_section_label('Home Team Set-Pieces'),
                make_graph(fig_setpiece_home, 190),
                #make_section_label('====='),
            ]),

            # ── Row 2 — centre column ──────────────────────────────────────────
            make_col([
                make_section_label('Starting Lineup'),
                make_graph(fig_starting_xi, 240),
                make_section_label('Match Momentum'),
                make_graph(fig_match_momentum, 120),
                make_section_label('Match Statistics'),
                make_graph(fig_match_stats, 240),
                make_section_label('Shot Map'),
                html.Div(
                    [
                        html.Div([make_graph(fig_shots_home, 280)], style={'width': '50%'}),
                        html.Div([make_graph(fig_shots_away, 280)], style={'width': '50%'}),
                    ],
                    style={'display': 'flex', 'flexDirection': 'row'},
                ),
                make_section_label('Pass Network & Average Positions'),
                html.Div(
                    [
                        html.Div([make_graph(fig_pn_home, 478)], style={'width': '50%'}),
                        html.Div([make_graph(fig_pn_away, 478)], style={'width': '50%'}),
                    ],
                    style={'display': 'flex', 'flexDirection': 'row'},
                ),
                make_section_label('Crosses from Open Play'),
                html.Div(
                    [
                        html.Div([make_graph(fig_crosses_home, 190)], style={'width': '50%'}),
                        html.Div([make_graph(fig_crosses_away, 190)], style={'width': '50%'}),
                    ],
                    style={'display': 'flex', 'flexDirection': 'row'},
                ),
                make_section_label('Goalkeeper Build-up Distribution'),
                html.Div(
                    [
                        html.Div([make_graph(fig_gk_pass_home, 345)], style={'width': '50%'}),
                        html.Div([make_graph(fig_gk_pass_away, 345)], style={'width': '50%'}),
                    ],
                    style={'display': 'flex', 'flexDirection': 'row'},
                ),
                #make_section_label('======'),
            ]),

            # ── Row 2 — right column ───────────────────────────────────────────
            make_col([
                make_table(lineup_away, height_px=LINEUP_H, style_cell_conditional=LINEUP_COL_WIDTHS,
                           style_data_conditional=LINEUP_SUB_COLORS, css=LINEUP_CSS),
                make_section_label('Away Team Progressive Passes & Carries'),
                make_graph(fig_prog_passes_away, 240),
                make_section_label('Away Team Z14 & Half-Spaces Entries'),
                make_graph(fig_final_third_away, 280),
                make_section_label('Away Team Pass Receive Heatmap'),
                make_graph(fig_receive_hm_a, 260),
                make_section_label('Away Team Defensive Actions Heatmap'),
                make_graph(fig_def_action_away, 300),
                make_section_label('Away Team Fast Break Sequences'),
                make_graph(fig_fastbreak_a, 230),
                make_section_label('Away Team Set-Pieces'),
                make_graph(fig_setpiece_away, 190),
                #make_section_label('====='),
            ]),
        ],
    )
