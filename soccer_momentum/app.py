import os

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output

# ---------------------------------------------------------------------------
# Layout constants — must match figure margins so the slider lines up with
# the plot area when it is positioned absolutely inside the graph container.
# ---------------------------------------------------------------------------
GRAPH_HEIGHT = 500
MARGIN_L = 60   # left margin (px) — start of x-axis
MARGIN_R = 20   # right margin (px)
MARGIN_T = 60   # top margin (px)  — title only (timer is now an HTML element)
MARGIN_B = 30   # bottom margin (px) — reduced: slider lives inside the graph
PLOT_HEIGHT = GRAPH_HEIGHT - MARGIN_T - MARGIN_B   # 410 px
SLIDER_TOP_PX = MARGIN_T + PLOT_HEIGHT // 2        # pixel row of y=0  (265)

# ---------------------------------------------------------------------------
# Load match DataFrame from CSV.
# Period 1 (period_id=1): time_min 0-46 (45 regular + extra time up to 46)
# Period 2 (period_id=2): time_min 45-95 (starts at 45; 45 regular + extra time)
# Overlap at minutes 45-46 is intentional: period 1 extra time coincides with
# the minute labels at which period 2 kicks off.
# ---------------------------------------------------------------------------
_CSV_PATH = os.path.join(os.path.dirname(__file__), "momentum_df.csv")
df = pd.read_csv(_CSV_PATH)

# Derived values — recompute whenever the DataFrame changes
MAX_MINUTE = int(df["time_min"].max())
# Half-time separator: just after the last minute of period 1
HALFTIME_X = float(df.loc[df["period_id"] == 1, "time_min"].max()) + 0.5

# Slider marks: standard milestones + highlight when extra time extends past 90
_slider_marks: dict = {
    0:  {"label": "0'",  "style": {"color": "#aaa", "fontSize": "11px"}},
    45: {"label": "45'", "style": {"color": "#aaa", "fontSize": "11px"}},
    90: {"label": "90'", "style": {"color": "#aaa", "fontSize": "11px"}},
}
if MAX_MINUTE > 90:
    _slider_marks[MAX_MINUTE] = {
        "label": f"{MAX_MINUTE}'",
        "style": {"color": "yellow", "fontSize": "11px"},
    }


def format_timer(minute: int) -> str:
    """Return match time as mm:ss:mmm — slider is in whole minutes so ss=00, mmm=000."""
    return f"{minute:02d}:00:000"


# ---------------------------------------------------------------------------
# Helper: build figure for a given slider value
# ---------------------------------------------------------------------------

def build_figure(slider_value: int) -> go.Figure:
    fig = go.Figure()

    def to_rgba(is_positive: bool, opacity: float) -> str:
        return (
            f"rgba(220,50,50,{opacity})" if is_positive
            else f"rgba(50,168,82,{opacity})"
        )

    # One bar trace per period so the two halves can be styled independently.
    # barmode="overlay" draws them on top of each other at the shared
    # minutes 45-46 at the period junction.
    for period, grp in df.groupby("period_id"):
        time_vals   = grp["time_min"].values
        threat_vals = grp["Threats"].values

        marker_colors = [
            to_rgba(t >= 0, 1.0 if m <= slider_value else 0.3)
            for t, m in zip(threat_vals, time_vals)
        ]

        fig.add_trace(
            go.Bar(
                x=time_vals,
                y=threat_vals,
                marker_color=marker_colors,
                hoverinfo="skip",       # no tooltip — graph is background
                name=f"Period {period}",
                showlegend=False,
            )
        )

    # Half-time dashed line (position derived from data to support extra time)
    fig.add_vline(
        x=HALFTIME_X,
        line_dash="dash",
        line_color="gray",
        line_width=2,
        annotation_text="Half-Time",
        annotation_position="top",
        annotation_font_color="gray",
    )

    # Goal markers:
    #   home goal → fixed at top of graph  (y = +0.85)
    #   away goal → fixed at bottom of graph (y = -0.85)
    goal_rows = df[(df["home_goal"] == 1) | (df["away_goal"] == 1)]
    for _, grow in goal_rows.iterrows():
        is_home = grow["home_goal"] == 1
        label   = "⚽ Home Goal" if is_home else "⚽ Away Goal"
        y_pos   = 0.85 if is_home else -0.85
        fig.add_trace(
            go.Scatter(
                x=[grow["time_min"]],
                y=[y_pos],
                mode="markers+text",
                marker=dict(
                    symbol="star", size=18, color="gold",
                    line=dict(color="orange", width=1),
                ),
                text=[label],
                textposition="top center" if is_home else "bottom center",
                hoverinfo="skip",       # no tooltip — graph is background
                name=label,
                showlegend=True,
            )
        )

    # Current-time indicator line
    if slider_value > 0:
        fig.add_vline(
            x=slider_value,
            line_color="white",
            line_width=2,
            line_dash="solid",
            opacity=0.6,
        )

    fig.update_layout(
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#16213e",
        font_color="white",
        title=dict(text="Match Momentum", x=0.5, font=dict(size=20, color="white")),
        xaxis=dict(
            title="Match Time (minutes)",
            range=[0, MAX_MINUTE + 1],
            tickvals=list(range(0, MAX_MINUTE + 2, 5)),
            gridcolor="#2a2a4a",
            zerolinecolor="#2a2a4a",
            fixedrange=True,    # disable zoom/pan
        ),
        yaxis=dict(
            title="Threat Index",
            range=[-1, 1],      # fixed y-axis so graph height is stable
            fixedrange=True,    # disable zoom/pan
            gridcolor="#2a2a4a",
            zerolinecolor="#555",
        ),
        hovermode=False,        # disable all hover interactions
        barmode="overlay",      # periods share the same x positions at minute junction
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(t=MARGIN_T, r=MARGIN_R, b=MARGIN_B, l=MARGIN_L),
        bargap=0.05,
    )

    return fig


# ---------------------------------------------------------------------------
# Dash application layout
# ---------------------------------------------------------------------------
app = Dash(__name__)

app.layout = html.Div(
    style={"backgroundColor": "#16213e", "padding": "20px", "fontFamily": "Arial, sans-serif"},
    children=[
        html.H2(
            "⚽ Soccer Match Momentum Dashboard",
            style={"color": "white", "textAlign": "center", "marginBottom": "10px"},
        ),
        # Timer — lives outside the figure so it stays legible regardless of
        # graph render mode; synced with the slider via the callback below.
        html.Div(
            id="timer-display",
            style={
                "color": "cyan",
                "textAlign": "right",
                "fontFamily": "Courier New, monospace",
                "fontSize": "24px",
                "paddingRight": f"{MARGIN_R + 4}px",
                "marginBottom": "4px",
                "letterSpacing": "2px",
            },
            children=format_timer(MAX_MINUTE),
        ),
        # Relative-positioned container: graph fills it, slider sits on top at y=0
        html.Div(
            style={"position": "relative", "height": f"{GRAPH_HEIGHT}px"},
            children=[
                dcc.Graph(
                    id="momentum-graph",
                    figure=build_figure(MAX_MINUTE),
                    style={"height": f"{GRAPH_HEIGHT}px", "width": "100%"},
                    config={
                        "staticPlot": True,     # render as background image: no hover,
                        "displayModeBar": False, # no toolbar, no interactivity
                    },
                ),
                # Slider overlaid at y=0 (centre of graph)
                html.Div(
                    style={
                        "position": "absolute",
                        "top": f"{SLIDER_TOP_PX}px",
                        "left": f"{MARGIN_L}px",
                        "right": f"{MARGIN_R}px",
                        "transform": "translateY(-50%)",
                        "zIndex": 10,
                    },
                    children=[
                        dcc.Slider(
                            id="time-slider",
                            min=0,
                            max=MAX_MINUTE,
                            step=1,
                            value=MAX_MINUTE,
                            marks=_slider_marks,
                            tooltip={"placement": "top", "always_visible": True},
                            updatemode="drag",
                        ),
                    ],
                ),
            ],
        ),
        html.Div(
            style={"color": "#aaa", "textAlign": "center", "marginTop": "10px", "fontSize": "13px"},
            children=[
                "🔴 Offensive momentum  |  "
                "🟢 Defensive momentum  |  "
                "⭐ Home goal (top) / Away goal (bottom)  |  "
                "Dimmed bars = future momentum"
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Callback: update graph and timer when slider moves
# ---------------------------------------------------------------------------
@app.callback(
    Output("momentum-graph", "figure"),
    Output("timer-display", "children"),
    Input("time-slider", "value"),
)
def update_graph(slider_value):
    return build_figure(slider_value), format_timer(slider_value)


if __name__ == "__main__":
    app.run(debug=True)
