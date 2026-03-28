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
MARGIN_T = 80   # top margin (px)  — room for title + timer
MARGIN_B = 30   # bottom margin (px) — reduced: slider lives inside the graph
PLOT_HEIGHT = GRAPH_HEIGHT - MARGIN_T - MARGIN_B   # 390 px
SLIDER_TOP_PX = MARGIN_T + PLOT_HEIGHT // 2        # pixel row of y=0  (275)

# ---------------------------------------------------------------------------
# Sample match DataFrame — includes additional time (common in soccer)
# Period 1: minutes 1-47  (45 regular + 2 extra-time minutes)
# Period 2: minutes 48-95 (45 regular + 3 extra-time minutes; 48 total minute-bins)
# ---------------------------------------------------------------------------
_p1 = list(range(1, 48))    # 47 minutes
_p2 = list(range(48, 96))   # 48 minutes

data = {
    "period_id": [1] * len(_p1) + [2] * len(_p2),
    "time_min":  _p1 + _p2,
    "Threats": [
        # Period 1 — 47 values
        0.3, -0.1, 0.5, 0.2, -0.3, 0.4, 0.1, -0.2, 0.6, 0.3,
        -0.4, 0.2, 0.5, 0.1, -0.1, 0.3, 0.4, -0.5, 0.2, 0.6,
        0.1, -0.3, 0.4, 0.2, -0.2, 0.5, -0.1, 0.3, -0.4, 0.2,
        0.6, -0.2, 0.4, 0.1, -0.3, 0.5, 0.2, -0.1, 0.3, 0.4,
        -0.2, 0.6, 0.1, -0.3, 0.5, -0.4, 0.3,
        # Period 2 — 48 values
        -0.2, 0.4, 0.3, -0.1, 0.5, 0.2, -0.3, 0.6, 0.1, -0.4,
        0.3, 0.5, -0.2, 0.4, 0.1, -0.3, 0.6, 0.2, -0.1, 0.5,
        0.3, -0.4, 0.2, 0.4, -0.2, 0.5, 0.1, -0.3, 0.6, 0.2,
        -0.1, 0.4, 0.3, -0.5, 0.2, 0.6, -0.2, 0.4, 0.1, -0.3,
        0.5, 0.2, -0.1, 0.3, 0.4, 0.3, -0.2, 0.1,
    ],
    "home_goal": [0] * (len(_p1) + len(_p2)),
    "away_goal": [0] * (len(_p1) + len(_p2)),
}

df = pd.DataFrame(data)

# Goals at specific minutes (use loc for explicit minute-to-row mapping)
df.loc[df["time_min"] == 27, "away_goal"] = 1
df.loc[df["time_min"] == 72, "home_goal"] = 1

# Derived values — recompute whenever the DataFrame changes
MAX_MINUTE = int(df["time_min"].max())
# Half-time separator: just after the last minute of period 1
HALFTIME_X = float(df.loc[df["period_id"] == 1, "time_min"].max()) + 0.5

# Slider marks: standard milestones + highlight if extra time extends past 90
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

# ---------------------------------------------------------------------------
# Helper: build figure for a given slider value
# ---------------------------------------------------------------------------

def build_figure(slider_value: int) -> go.Figure:
    fig = go.Figure()

    # Vectorized color + opacity computation
    time_vals   = df["time_min"].values
    threat_vals = df["Threats"].values

    def to_rgba(is_positive: bool, opacity: float) -> str:
        return (
            f"rgba(220,50,50,{opacity})" if is_positive
            else f"rgba(50,168,82,{opacity})"
        )

    marker_colors = [
        to_rgba(t >= 0, 1.0 if m <= slider_value else 0.3)
        for t, m in zip(threat_vals, time_vals)
    ]

    # Momentum bars
    fig.add_trace(
        go.Bar(
            x=df["time_min"],
            y=df["Threats"],
            marker_color=marker_colors,
            hovertemplate="Minute: %{x}<br>Threat Index: %{y:.2f}<extra></extra>",
            name="Momentum",
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
                hovertemplate=(
                    f"{label} at minute {int(grow['time_min'])}<extra></extra>"
                ),
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

    # Timer annotation: mm:ss:ms where mm = match minute, ss = seconds, ms = milliseconds.
    # Slider operates in whole-minute steps, so ss and ms are always 00.
    timer_text = f"{slider_value:02d}:00:00"

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
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        annotations=[
            dict(
                text=timer_text,
                xref="paper", yref="paper",
                x=1.0, y=1.08,
                showarrow=False,
                font=dict(size=20, color="cyan", family="Courier New, monospace"),
                align="right",
            )
        ],
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
        # Relative-positioned container: graph fills it, slider sits on top at y=0
        html.Div(
            style={"position": "relative", "height": f"{GRAPH_HEIGHT}px"},
            children=[
                dcc.Graph(
                    id="momentum-graph",
                    figure=build_figure(MAX_MINUTE),
                    style={"height": f"{GRAPH_HEIGHT}px", "width": "100%"},
                    config={
                        "scrollZoom": False,
                        "doubleClick": False,
                        "displayModeBar": False,
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
                "🔴 Offensive momentum (positive Threats)  |  "
                "🟢 Defensive momentum (negative Threats)  |  "
                "⭐ Home goal (top) / Away goal (bottom)  |  "
                "Dimmed bars = future momentum"
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Callback: update graph when slider moves
# ---------------------------------------------------------------------------
@app.callback(
    Output("momentum-graph", "figure"),
    Input("time-slider", "value"),
)
def update_graph(slider_value):
    return build_figure(slider_value)


if __name__ == "__main__":
    app.run(debug=True)
