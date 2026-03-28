import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output

# ---------------------------------------------------------------------------
# Sample match DataFrame
# ---------------------------------------------------------------------------
data = {
    "period_id": [1] * 45 + [2] * 45,
    "time_min": list(range(1, 46)) + list(range(46, 91)),
    "Threats": [
        # First half (minutes 1-45)
        0.3, -0.1, 0.5, 0.2, -0.3, 0.4, 0.1, -0.2, 0.6, 0.3,
        -0.4, 0.2, 0.5, 0.1, -0.1, 0.3, 0.4, -0.5, 0.2, 0.6,
        0.1, -0.3, 0.4, 0.2, -0.2, 0.5, -0.1, 0.3, -0.4, 0.2,
        0.6, -0.2, 0.4, 0.1, -0.3, 0.5, 0.2, -0.1, 0.3, 0.4,
        -0.2, 0.6, 0.1, -0.3, 0.5,
        # Second half (minutes 46-90)
        -0.2, 0.4, 0.3, -0.1, 0.5, 0.2, -0.3, 0.6, 0.1, -0.4,
        0.3, 0.5, -0.2, 0.4, 0.1, -0.3, 0.6, 0.2, -0.1, 0.5,
        0.3, -0.4, 0.2, 0.4, -0.2, 0.5, 0.1, -0.3, 0.6, 0.2,
        -0.1, 0.4, 0.3, -0.5, 0.2, 0.6, -0.2, 0.4, 0.1, -0.3,
        0.5, 0.2, -0.1, 0.3, 0.4,
    ],
    "home_goal": [0] * 90,
    "away_goal": [0] * 90,
}

df = pd.DataFrame(data)

# Goals at specific minutes — use loc to make the minute-to-row mapping explicit
df.loc[df["time_min"] == 27, "away_goal"] = 1
df.loc[df["time_min"] == 72, "home_goal"] = 1

# ---------------------------------------------------------------------------
# Helper: build figure for a given slider value
# ---------------------------------------------------------------------------

def build_figure(slider_value: int) -> go.Figure:
    fig = go.Figure()

    # Vectorized color and opacity computation
    time_vals = df["time_min"].values
    threat_vals = df["Threats"].values

    def to_rgba(is_positive: bool, opacity: float) -> str:
        if is_positive:
            return f"rgba(220,50,50,{opacity})"
        return f"rgba(50,168,82,{opacity})"

    marker_colors = [
        to_rgba(t >= 0, 1.0 if m <= slider_value else 0.3)
        for t, m in zip(threat_vals, time_vals)
    ]

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

    # ------------------------------------------------------------------
    # Half-time vertical line at 45 minutes
    # ------------------------------------------------------------------
    fig.add_vline(
        x=45.5,
        line_dash="dash",
        line_color="gray",
        line_width=2,
        annotation_text="Half-Time",
        annotation_position="top",
        annotation_font_color="gray",
    )

    # ------------------------------------------------------------------
    # Goal markers
    # ------------------------------------------------------------------
    goal_rows = df[(df["home_goal"] == 1) | (df["away_goal"] == 1)]
    for _, grow in goal_rows.iterrows():
        label = (
            "⚽ Home Goal"
            if grow["home_goal"] == 1
            else "⚽ Away Goal"
        )
        fig.add_trace(
            go.Scatter(
                x=[grow["time_min"]],
                y=[grow["Threats"] + (0.05 if grow["Threats"] >= 0 else -0.05)],
                mode="markers+text",
                marker=dict(symbol="star", size=18, color="gold", line=dict(color="orange", width=1)),
                text=[label],
                textposition="top center" if grow["Threats"] >= 0 else "bottom center",
                hovertemplate=f"{label} at minute {int(grow['time_min'])}<extra></extra>",
                name=label,
                showlegend=True,
            )
        )

    # ------------------------------------------------------------------
    # Current time indicator (vertical line at slider position)
    # ------------------------------------------------------------------
    fig.add_vline(
        x=slider_value,
        line_color="white",
        line_width=2,
        line_dash="solid",
        opacity=0.6,
    )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    # Timer: slider is in whole minutes, so ss and ms are always 00
    mm = slider_value
    timer_text = f"{mm:02d}:00:00"

    fig.update_layout(
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#16213e",
        font_color="white",
        title=dict(
            text="Match Momentum",
            x=0.5,
            font=dict(size=20, color="white"),
        ),
        xaxis=dict(
            title="Match Time (minutes)",
            range=[0, 91],
            tickvals=list(range(0, 91, 5)),
            gridcolor="#2a2a4a",
            zerolinecolor="#2a2a4a",
        ),
        yaxis=dict(
            title="Threat Index",
            gridcolor="#2a2a4a",
            zerolinecolor="#888",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
        annotations=[
            dict(
                text=timer_text,
                xref="paper",
                yref="paper",
                x=1.0,
                y=1.08,
                showarrow=False,
                font=dict(size=20, color="cyan", family="Courier New, monospace"),
                align="right",
            )
        ],
        margin=dict(t=80, r=20, b=60, l=60),
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
        dcc.Graph(
            id="momentum-graph",
            figure=build_figure(90),
            style={"height": "500px"},
        ),
        html.Div(
            style={"padding": "10px 30px"},
            children=[
                html.Label(
                    "Match Time Slider",
                    style={"color": "white", "fontWeight": "bold", "marginBottom": "5px"},
                ),
                dcc.Slider(
                    id="time-slider",
                    min=0,
                    max=90,
                    step=1,
                    value=90,
                    marks={
                        0: {"label": "0'", "style": {"color": "white"}},
                        15: {"label": "15'", "style": {"color": "white"}},
                        30: {"label": "30'", "style": {"color": "white"}},
                        45: {"label": "45'", "style": {"color": "white"}},
                        60: {"label": "60'", "style": {"color": "white"}},
                        75: {"label": "75'", "style": {"color": "white"}},
                        90: {"label": "90'", "style": {"color": "white"}},
                    },
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ],
        ),
        html.Div(
            style={"color": "#aaa", "textAlign": "center", "marginTop": "10px", "fontSize": "13px"},
            children=[
                "🔴 Offensive momentum (positive Threats)  |  "
                "🟢 Defensive momentum (negative Threats)  |  "
                "⭐ Goal event  |  "
                "Bars after slider position are dimmed to 30% opacity"
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Callback: update graph on slider change
# ---------------------------------------------------------------------------
@app.callback(
    Output("momentum-graph", "figure"),
    Input("time-slider", "value"),
)
def update_graph(slider_value):
    return build_figure(slider_value)


if __name__ == "__main__":
    app.run(debug=True)
