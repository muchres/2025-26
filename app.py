import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Colour palette & constants
# ---------------------------------------------------------------------------

TEAM_HOME = "Atletico Madrid"
TEAM_AWAY = "Real Betis"
SCORE_HOME = 0
SCORE_AWAY = 1

COLOR_HOME = "#E63946"   # red  – Atletico Madrid
COLOR_AWAY = "#52B788"   # green – Real Betis
BG_COLOR = "#141414"
PITCH_FILL = "#2D6A4F"   # grass green
PITCH_LINE = "#FFFFFF"
CARD_BG = "#1E1E1E"
TEXT_COLOR = "#FFFFFF"
SUB_COLOR = "#9E9E9E"

# ---------------------------------------------------------------------------
# Placeholder data
# ---------------------------------------------------------------------------

SAMPLE_EVENTS = [
    {"type": "Pass",  "team": TEAM_AWAY, "time": 12,  "player": "P. Formals",   "x": 60.1, "y": 34.2, "success": True},
    {"type": "Pass",  "team": TEAM_HOME, "time": 23,  "player": "K. Llorente",  "x": 45.3, "y": 22.7, "success": True},
    {"type": "Shot",  "team": TEAM_AWAY, "time": 38,  "player": "I. Williams",  "x": 85.4, "y": 34.0, "success": False},
    {"type": "Pass",  "team": TEAM_HOME, "time": 51,  "player": "A. Griezmann", "x": 70.2, "y": 40.1, "success": True},
    {"type": "Pass",  "team": TEAM_AWAY, "time": 67,  "player": "S. Canales",   "x": 55.6, "y": 28.3, "success": True},
    {"type": "Shot",  "team": TEAM_HOME, "time": 74,  "player": "M. Morata",    "x": 88.1, "y": 35.5, "success": False},
    {"type": "Shot",  "team": TEAM_AWAY, "time": 82,  "player": "B. Iglesias",  "x": 90.3, "y": 32.8, "success": True},
    {"type": "Pass",  "team": TEAM_HOME, "time": 90,  "player": "T. Lemar",     "x": 50.0, "y": 30.0, "success": False},
    {"type": "Pass",  "team": TEAM_AWAY, "time": 96,  "player": "A. Guardado",  "x": 62.4, "y": 25.6, "success": True},
    {"type": "Shot",  "team": TEAM_HOME, "time": 103, "player": "L. Suarez",    "x": 87.5, "y": 36.0, "success": False},
]

# Momentum time-series (placeholder, 0-90 min)
_t = np.linspace(0, 90, 91)
np.random.seed(42)
_home_mom = np.clip(np.cumsum(np.random.randn(91) * 0.3) + 50, 20, 80)
_away_mom = 100 - _home_mom

# ---------------------------------------------------------------------------
# Aggregate match stats
# ---------------------------------------------------------------------------

def _compute_stats():
    df = pd.DataFrame(SAMPLE_EVENTS)
    shots_h = int(len(df[(df.team == TEAM_HOME) & (df.type == "Shot")]))
    shots_a = int(len(df[(df.team == TEAM_AWAY) & (df.type == "Shot")]))
    sot_h = int(len(df[(df.team == TEAM_HOME) & (df.type == "Shot") & df.success]))
    sot_a = int(len(df[(df.team == TEAM_AWAY) & (df.type == "Shot") & df.success]))
    pass_h = int(len(df[df.team == TEAM_HOME]))
    pass_a = int(len(df[df.team == TEAM_AWAY]))
    total = pass_h + pass_a
    poss_h = round(pass_h / total * 100) if total else 50
    poss_a = 100 - poss_h
    return dict(
        shots_h=shots_h, shots_a=shots_a,
        sot_h=sot_h, sot_a=sot_a,
        poss_h=poss_h, poss_a=poss_a,
    )


STATS = _compute_stats()

# ---------------------------------------------------------------------------
# Styling helpers  (defined BEFORE layout so they can be called inline)
# ---------------------------------------------------------------------------

def btn_style(primary=False):
    return {
        "background": COLOR_HOME if primary else "#2A2A2A",
        "color": TEXT_COLOR,
        "border": "none",
        "borderRadius": "6px",
        "padding": "6px 16px",
        "cursor": "pointer",
        "fontSize": "13px",
        "fontWeight": "600" if primary else "400",
        "transition": "opacity .15s",
    }


def pct_bar(value, color, direction="left"):
    grad = (
        f"linear-gradient(to right, {color} {value}%, #333 {value}%)"
        if direction == "left"
        else f"linear-gradient(to left, {color} {value}%, #333 {value}%)"
    )
    return html.Div(style={
        "flex": "1",
        "height": "6px",
        "borderRadius": "3px",
        "background": grad,
        "margin": "0 6px",
    })


def stat_row(label, home_val, away_val, home_pct, away_pct):
    return html.Div([
        html.Span(str(home_val),
                  style={"color": COLOR_HOME, "fontWeight": "700",
                         "fontSize": "15px", "minWidth": "30px",
                         "textAlign": "right"}),
        pct_bar(home_pct, COLOR_HOME, "left"),
        html.Span(label,
                  style={"color": SUB_COLOR, "fontSize": "12px",
                         "whiteSpace": "nowrap", "textAlign": "center",
                         "minWidth": "110px"}),
        pct_bar(away_pct, COLOR_AWAY, "right"),
        html.Span(str(away_val),
                  style={"color": COLOR_AWAY, "fontWeight": "700",
                         "fontSize": "15px", "minWidth": "30px"}),
    ], style={"display": "flex", "alignItems": "center",
              "gap": "4px", "padding": "5px 0"})


def event_card(ev):
    team_color = COLOR_HOME if ev["team"] == TEAM_HOME else COLOR_AWAY
    status_label = "✓ Successful" if ev["success"] else "✗ Unsuccessful"
    status_color = "#52B788" if ev["success"] else "#E63946"
    half_label = "1st Half" if ev["time"] <= 45 else "2nd Half"
    display_min = ev["time"] if ev["time"] <= 45 else ev["time"] - 45

    return html.Div([
        html.Div(style={
            "width": "4px", "borderRadius": "2px",
            "background": team_color, "flexShrink": "0",
        }),
        html.Div([
            html.Div([
                html.Span(
                    f"{ev['type']}: {ev['team']} {display_min}'",
                    style={"color": team_color, "fontWeight": "600",
                           "fontSize": "13px"},
                ),
                html.Span(half_label,
                          style={"color": SUB_COLOR, "fontSize": "11px",
                                 "marginLeft": "8px"}),
            ], style={"display": "flex", "alignItems": "center",
                      "justifyContent": "space-between"}),
            html.Div(ev["player"],
                     style={"color": TEXT_COLOR, "fontSize": "13px",
                            "marginTop": "3px"}),
            html.Div([
                html.Span(f"({ev['x']:.1f}, {ev['y']:.1f})  •  ",
                          style={"color": SUB_COLOR, "fontSize": "11px"}),
                html.Span(status_label,
                          style={"color": status_color, "fontSize": "11px"}),
            ], style={"marginTop": "2px"}),
        ], style={"flex": "1", "minWidth": "0"}),
    ], style={
        "display": "flex", "gap": "10px",
        "background": CARD_BG,
        "borderRadius": "6px",
        "padding": "10px 12px",
        "borderLeft": f"4px solid {team_color}",
    })


# ---------------------------------------------------------------------------
# Pitch figure
# ---------------------------------------------------------------------------

def build_pitch_fig(width=680, height=420):
    """Return a Plotly figure with a standard 105 × 68 m football pitch."""
    PW, PH = 105.0, 68.0

    def sx(x):
        return x / PW * width

    def sy(y):
        return y / PH * height

    line_kw = dict(
        xref="x", yref="y",
        line=dict(color=PITCH_LINE, width=1.5),
        fillcolor="rgba(0,0,0,0)",
    )
    shapes = []

    # Outer boundary
    shapes.append(dict(type="rect", x0=0, y0=0, x1=width, y1=height, **line_kw))

    # Half-way line
    shapes.append(dict(type="line", xref="x", yref="y",
                       x0=sx(PW / 2), y0=0, x1=sx(PW / 2), y1=height,
                       line=dict(color=PITCH_LINE, width=1.5)))

    # Centre circle
    r_x = sx(9.15)
    r_y = sy(9.15)
    cx, cy = sx(PW / 2), sy(PH / 2)
    shapes.append(dict(type="circle", xref="x", yref="y",
                       x0=cx - r_x, y0=cy - r_y, x1=cx + r_x, y1=cy + r_y,
                       line=dict(color=PITCH_LINE, width=1.5),
                       fillcolor="rgba(0,0,0,0)"))

    # Centre spot
    shapes.append(dict(type="circle", xref="x", yref="y",
                       x0=cx - 2, y0=cy - 2, x1=cx + 2, y1=cy + 2,
                       line=dict(color=PITCH_LINE, width=1),
                       fillcolor=PITCH_LINE))

    def add_end(left):
        ox = 0.0 if left else PW
        sign = 1 if left else -1

        # Penalty area (40.32 × 16.5 m)
        pa_y0 = sy((PH - 40.32) / 2)
        pa_y1 = sy((PH + 40.32) / 2)
        pa_x1 = sx(ox + sign * 16.5)
        shapes.append(dict(type="rect", x0=sx(ox), y0=pa_y0,
                           x1=pa_x1, y1=pa_y1, **line_kw))

        # Goal area (18.32 × 5.5 m)
        ga_y0 = sy((PH - 18.32) / 2)
        ga_y1 = sy((PH + 18.32) / 2)
        ga_x1 = sx(ox + sign * 5.5)
        shapes.append(dict(type="rect", x0=sx(ox), y0=ga_y0,
                           x1=ga_x1, y1=ga_y1, **line_kw))

        # Penalty spot
        ps_x = sx(ox + sign * 11)
        ps_y = sy(PH / 2)
        shapes.append(dict(type="circle", xref="x", yref="y",
                           x0=ps_x - 2, y0=ps_y - 2,
                           x1=ps_x + 2, y1=ps_y + 2,
                           line=dict(color=PITCH_LINE, width=1),
                           fillcolor=PITCH_LINE))

        # Goal posts (7.32 × ~2 m depth)
        g_y0 = sy((PH - 7.32) / 2)
        g_y1 = sy((PH + 7.32) / 2)
        g_x1 = sx(ox - sign * 2)
        shapes.append(dict(type="rect", x0=sx(ox), y0=g_y0,
                           x1=g_x1, y1=g_y1, **line_kw))

    add_end(left=True)
    add_end(left=False)

    fig = go.Figure()
    fig.update_layout(
        width=width,
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=BG_COLOR,
        plot_bgcolor=PITCH_FILL,
        xaxis=dict(range=[0, width], showgrid=False,
                   zeroline=False, visible=False),
        yaxis=dict(range=[0, height], showgrid=False,
                   zeroline=False, visible=False),
        shapes=shapes,
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# Momentum chart
# ---------------------------------------------------------------------------

def build_momentum_fig():
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=_t, y=_home_mom,
        fill="tozeroy", mode="none",
        fillcolor="rgba(230,57,70,0.40)",
        name=TEAM_HOME,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=_t, y=_away_mom,
        fill="tozeroy", mode="none",
        fillcolor="rgba(82,183,136,0.40)",
        name=TEAM_AWAY,
        hoverinfo="skip",
    ))
    fig.update_layout(
        height=70,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=BG_COLOR,
        plot_bgcolor=BG_COLOR,
        xaxis=dict(range=[0, 90], showgrid=False,
                   zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False),
        showlegend=False,
        hovermode=False,
    )
    return fig


# ---------------------------------------------------------------------------
# App layout
# ---------------------------------------------------------------------------

app = dash.Dash(__name__, title="LaLiga Match Viewer")
server = app.server   # WSGI entry-point for deployment

PITCH_FIG = build_pitch_fig()
MOMENTUM_FIG = build_momentum_fig()

app.layout = html.Div([

    # ── Top-level 70/30 flex container ──────────────────────────────────────
    html.Div([

        # ═══════════════════════════════════════════════════════════════════
        # LEFT COLUMN  (70 %)
        # ═══════════════════════════════════════════════════════════════════
        html.Div([

            # 1 ── Match header ──────────────────────────────────────────
            html.Div([
                html.H2(
                    [
                        html.Span(TEAM_HOME,
                                  style={"color": COLOR_HOME}),
                        html.Span(f"  {SCORE_HOME}  –  {SCORE_AWAY}  ",
                                  style={"color": TEXT_COLOR}),
                        html.Span(TEAM_AWAY,
                                  style={"color": COLOR_AWAY}),
                    ],
                    style={"textAlign": "center", "margin": "0",
                           "fontSize": "20px", "fontWeight": "700",
                           "letterSpacing": "0.5px"},
                ),
                html.P("LaLiga 2024/25  ·  Matchday 12",
                       style={"color": SUB_COLOR, "textAlign": "center",
                              "margin": "4px 0 0", "fontSize": "12px"}),
            ], style={"padding": "16px 0 10px"}),

            # 2 ── Controls row ──────────────────────────────────────────
            html.Div([

                # Half selector
                html.Div([
                    html.Label("Half",
                               style={"color": SUB_COLOR, "fontSize": "11px",
                                      "marginBottom": "4px",
                                      "display": "block"}),
                    dcc.RadioItems(
                        id="half-selector",
                        options=[
                            {"label": " 1st Half", "value": 1},
                            {"label": " 2nd Half", "value": 2},
                        ],
                        value=1,
                        inline=True,
                        inputStyle={"marginRight": "4px", "cursor": "pointer",
                                    "accentColor": COLOR_HOME},
                        labelStyle={"color": TEXT_COLOR, "fontSize": "13px",
                                    "marginRight": "14px", "cursor": "pointer"},
                    ),
                ]),

                # Camera angle
                html.Div([
                    html.Label("Camera Angle",
                               style={"color": SUB_COLOR, "fontSize": "11px",
                                      "marginBottom": "4px",
                                      "display": "block"}),
                    dcc.Dropdown(
                        id="camera-angle",
                        options=[
                            {"label": "Top-Down",  "value": "top"},
                            {"label": "Side View", "value": "side"},
                            {"label": "Tactical",  "value": "tactical"},
                        ],
                        value="top",
                        clearable=False,
                        style={"width": "150px"},
                        className="dark-dropdown",
                    ),
                ]),

                # Playback buttons
                html.Div([
                    html.Label("Playback",
                               style={"color": SUB_COLOR, "fontSize": "11px",
                                      "marginBottom": "4px",
                                      "display": "block"}),
                    html.Div([
                        html.Button("⏮", id="btn-rewind", n_clicks=0,
                                    style=btn_style()),
                        html.Button("▶  Play", id="btn-play", n_clicks=0,
                                    style=btn_style(primary=True)),
                        html.Button("⏭", id="btn-ff", n_clicks=0,
                                    style=btn_style()),
                        dcc.Interval(id="play-interval", interval=500,
                                     n_intervals=0, disabled=True),
                    ], style={"display": "flex", "gap": "6px"}),
                ]),

            ], style={
                "display": "flex", "gap": "24px", "alignItems": "flex-end",
                "padding": "0 0 12px",
                "borderBottom": "1px solid #2A2A2A",
            }),

            # 3 ── Pitch ─────────────────────────────────────────────────
            html.Div([
                dcc.Graph(
                    id="pitch-graph",
                    figure=PITCH_FIG,
                    config={"displayModeBar": False},
                    style={"width": "100%"},
                ),
            ], style={
                "borderRadius": "8px",
                "overflow": "hidden",
                "margin": "14px 0",
            }),

            # 4 ── Time slider + momentum ─────────────────────────────────
            html.Div([
                # Time / half label row
                html.Div([
                    html.Span(id="current-time-label", children="0'",
                              style={"color": TEXT_COLOR, "fontSize": "13px",
                                     "fontWeight": "600"}),
                    html.Span(id="current-half-label", children="1st Half",
                              style={"color": SUB_COLOR, "fontSize": "12px",
                                     "marginLeft": "8px"}),
                    html.Span("90'",
                              style={"color": TEXT_COLOR, "fontSize": "13px",
                                     "fontWeight": "600", "marginLeft": "auto"}),
                ], style={"display": "flex", "alignItems": "center",
                          "marginBottom": "2px"}),

                # Momentum chart (decorative, behind slider)
                html.Div([
                    dcc.Graph(
                        id="momentum-graph",
                        figure=MOMENTUM_FIG,
                        config={"displayModeBar": False},
                        style={"width": "100%", "pointerEvents": "none"},
                    ),
                    # Slider overlaid
                    html.Div([
                        dcc.Slider(
                            id="time-slider",
                            min=0, max=90, step=1, value=0,
                            marks={0: "0'", 45: "45'", 90: "90'"},
                            tooltip={"placement": "top",
                                     "always_visible": False},
                            updatemode="drag",
                        ),
                    ], style={
                        "position": "absolute",
                        "bottom": "4px",
                        "left": "0", "right": "0",
                        "padding": "0 10px",
                    }),
                ], style={"position": "relative"}),

            ], style={
                "background": BG_COLOR,
                "border": "1px solid #2A2A2A",
                "borderRadius": "8px",
                "padding": "10px 12px 30px",
                "marginBottom": "14px",
            }),

            # 5 ── Match stats ────────────────────────────────────────────
            html.Div([
                # Teams header
                html.Div([
                    html.Span(TEAM_HOME,
                              style={"color": COLOR_HOME, "fontWeight": "600",
                                     "fontSize": "13px"}),
                    html.Span("Match Stats",
                              style={"color": SUB_COLOR, "fontSize": "13px"}),
                    html.Span(TEAM_AWAY,
                              style={"color": COLOR_AWAY, "fontWeight": "600",
                                     "fontSize": "13px"}),
                ], style={"display": "flex", "justifyContent": "space-between",
                          "marginBottom": "8px"}),

                stat_row("Possession %",
                         f"{STATS['poss_h']}%", f"{STATS['poss_a']}%",
                         STATS["poss_h"], STATS["poss_a"]),
                stat_row("Shots",
                         STATS["shots_h"], STATS["shots_a"],
                         min(STATS["shots_h"] * 15, 100),
                         min(STATS["shots_a"] * 15, 100)),
                stat_row("Shots on Target",
                         STATS["sot_h"], STATS["sot_a"],
                         min(STATS["sot_h"] * 20, 100),
                         min(STATS["sot_a"] * 20, 100)),

            ], style={
                "background": CARD_BG,
                "borderRadius": "8px",
                "padding": "12px 16px",
                "marginBottom": "14px",
            }),

        ], style={
            "flex": "7",
            "display": "flex", "flexDirection": "column",
            "padding": "0 20px",
            "borderRight": "1px solid #2A2A2A",
            "minWidth": "0",
            "overflowY": "auto",
        }),

        # ═══════════════════════════════════════════════════════════════════
        # RIGHT COLUMN  (30 %)
        # ═══════════════════════════════════════════════════════════════════
        html.Div([

            # Events header
            html.Div([
                html.H3("Events",
                        style={"color": TEXT_COLOR, "margin": "0",
                               "fontSize": "16px", "fontWeight": "700"}),
                html.Span(f"{len(SAMPLE_EVENTS)} total",
                          style={"color": SUB_COLOR, "fontSize": "12px"}),
            ], style={
                "display": "flex", "justifyContent": "space-between",
                "alignItems": "center",
                "padding": "16px 0 12px",
                "borderBottom": "1px solid #2A2A2A",
                "marginBottom": "10px",
            }),

            # Scrollable event cards
            html.Div(
                id="events-list",
                children=[event_card(ev) for ev in SAMPLE_EVENTS],
                style={
                    "display": "flex", "flexDirection": "column",
                    "gap": "8px",
                    "overflowY": "auto",
                    "flex": "1",
                    "paddingRight": "4px",
                },
            ),

        ], style={
            "flex": "3",
            "display": "flex", "flexDirection": "column",
            "padding": "0 16px 16px 20px",
            "minWidth": "0",
            "height": "100vh",
        }),

    ], style={
        "display": "flex",
        "height": "100vh",
        "overflow": "hidden",
        "maxWidth": "1600px",
        "margin": "0 auto",
    }),

], style={
    "background": BG_COLOR,
    "fontFamily": "'Inter', 'Segoe UI', sans-serif",
    "minHeight": "100vh",
    "color": TEXT_COLOR,
})

# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


@app.callback(
    Output("btn-play", "children"),
    Output("btn-play", "style"),
    Output("play-interval", "disabled"),
    Input("btn-play", "n_clicks"),
    State("play-interval", "disabled"),
    prevent_initial_call=True,
)
def toggle_play(n_clicks, is_disabled):
    if is_disabled:
        return "⏸  Pause", btn_style(primary=True), False
    return "▶  Play", btn_style(primary=True), True


@app.callback(
    Output("time-slider", "value"),
    Input("play-interval", "n_intervals"),
    Input("btn-rewind", "n_clicks"),
    State("time-slider", "value"),
    State("play-interval", "disabled"),
    prevent_initial_call=True,
)
def advance_or_rewind(n_intervals, rewind_clicks, current_time, is_disabled):
    from dash import ctx
    if ctx.triggered_id == "btn-rewind":
        return 0
    if not is_disabled:
        return min(current_time + 1, 90)
    return current_time


@app.callback(
    Output("current-time-label", "children"),
    Output("current-half-label", "children"),
    Input("time-slider", "value"),
)
def update_time_label(t):
    half = "1st Half" if t <= 45 else "2nd Half"
    display = t if t <= 45 else t - 45
    return f"{display}'", half


@app.callback(
    Output("events-list", "children"),
    Input("time-slider", "value"),
    Input("half-selector", "value"),
)
def filter_events(current_time, half):
    offset = 0 if half == 1 else 45
    visible = [
        ev for ev in SAMPLE_EVENTS
        if (half == 1 and ev["time"] <= 45 and ev["time"] <= current_time)
        or (half == 2 and ev["time"] > 45 and ev["time"] <= current_time + 45)
    ]
    if not visible:
        return html.Div("No events yet.",
                        style={"color": SUB_COLOR, "fontSize": "13px",
                               "textAlign": "center", "marginTop": "20px"})
    return [event_card(ev) for ev in reversed(visible)]


# ---------------------------------------------------------------------------
# Inject global dark-theme CSS
# ---------------------------------------------------------------------------

app.index_string = (
    "<!DOCTYPE html>\n"
    "<html>\n"
    "  <head>\n"
    "    {%metas%}\n"
    "    <title>{%title%}</title>\n"
    "    {%favicon%}\n"
    "    {%css%}\n"
    "    <style>\n"
    "      * { box-sizing: border-box; margin: 0; padding: 0; }\n"
    "      html, body { height: 100%; }\n"
    f"      body {{ background: {BG_COLOR}; color: {TEXT_COLOR}; }}\n"
    "      ::-webkit-scrollbar { width: 6px; }\n"
    "      ::-webkit-scrollbar-track { background: #1E1E1E; }\n"
    "      ::-webkit-scrollbar-thumb { background: #444; border-radius: 3px; }\n"
    "      /* Dropdown */\n"
    "      .dark-dropdown .Select-control { background: #2A2A2A !important; border-color: #444 !important; }\n"
    "      .dark-dropdown .Select-menu-outer { background: #2A2A2A !important; border-color: #444 !important; }\n"
    "      .dark-dropdown .Select-option { background: #2A2A2A !important; color: #fff !important; }\n"
    "      .dark-dropdown .Select-option.is-focused { background: #3A3A3A !important; }\n"
    "      .dark-dropdown .Select-value-label { color: #fff !important; }\n"
    "      .dark-dropdown .Select-arrow { border-top-color: #9E9E9E !important; }\n"
    "      /* Slider track & handle */\n"
    f"      .rc-slider-track {{ background: {COLOR_HOME} !important; }}\n"
    f"      .rc-slider-handle {{ border-color: {COLOR_HOME} !important; background: {COLOR_HOME} !important; }}\n"
    "      .rc-slider-mark-text { color: #9E9E9E !important; font-size: 11px; }\n"
    "      /* Plotly graph containers */\n"
    "      .js-plotly-plot .plotly { background: transparent !important; }\n"
    "    </style>\n"
    "  </head>\n"
    "  <body>\n"
    "    {%app_entry%}\n"
    "    <footer>\n"
    "      {%config%}\n"
    "      {%scripts%}\n"
    "      {%renderer%}\n"
    "    </footer>\n"
    "  </body>\n"
    "</html>\n"
)

if __name__ == "__main__":
    app.run(debug=True, port=8050)
