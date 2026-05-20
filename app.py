from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html, dash_table


DATA_PATH = Path(__file__).with_name("Sporting_Matches.csv")
SHOT_EVENTS = {"Goal", "Miss", "Post", "Saved Shot"}
POSSESSION_EVENTS = {"Pass", "Carry"}
STAT_DEFS = [
    ("Goals", lambda d: (d["event"] == "Goal").sum()),
    ("Shots", lambda d: d["event"].isin(SHOT_EVENTS).sum()),
    ("Passes", lambda d: (d["event"] == "Pass").sum()),
    ("Carries", lambda d: (d["event"] == "Carry").sum()),
    ("Fouls", lambda d: (d["event"] == "Foul").sum()),
    ("Corners", lambda d: (d["event"] == "Corner Awarded").sum()),
    ("Recoveries", lambda d: (d["event"] == "Ball recovery").sum()),
]


def load_data() -> pd.DataFrame:
    usecols = [
        "match_id",
        "description",
        "local_date",
        "team_name",
        "team_position",
        "event",
        "time_min",
    ]
    df = pd.read_csv(DATA_PATH, usecols=usecols, low_memory=False)
    df["event"] = df["event"].fillna("")
    df["team_name"] = df["team_name"].fillna("")
    df["team_position"] = df["team_position"].fillna("")
    df["time_min"] = pd.to_numeric(df["time_min"], errors="coerce")
    df["local_date"] = df["local_date"].fillna("")
    df["description"] = df["description"].fillna("")
    return df


def team_order(df_match: pd.DataFrame) -> list[str]:
    teams = (
        df_match[["team_name", "team_position"]]
        .dropna(subset=["team_name"])
        .drop_duplicates()
    )
    order: list[str] = []
    if "team_position" in teams.columns:
        teams["team_position"] = teams["team_position"].str.lower()
        for position in ("home", "away"):
            order.extend(
                teams.loc[teams["team_position"] == position, "team_name"].tolist()
            )
    for team in teams["team_name"].tolist():
        if team and team not in order:
            order.append(team)
    return order


def match_labels(df: pd.DataFrame) -> pd.DataFrame:
    meta = (
        df[["match_id", "description", "local_date"]]
        .dropna(subset=["match_id"])
        .drop_duplicates(subset=["match_id"])
    )
    meta["label"] = meta.apply(
        lambda row: f"{row['local_date']} — {row['description']}".strip(" —"),
        axis=1,
    )
    return meta.sort_values(["local_date", "description"]).reset_index(drop=True)


def build_stats(df_match: pd.DataFrame, order: list[str]) -> pd.DataFrame:
    rows = []
    for team in order:
        team_df = df_match[df_match["team_name"] == team]
        stats = {"Team": team}
        for label, func in STAT_DEFS:
            stats[label] = int(func(team_df))
        rows.append(stats)
    return pd.DataFrame(rows)


def build_scoreline(df_match: pd.DataFrame, order: list[str]) -> str:
    goals = (
        df_match[df_match["event"] == "Goal"]
        .groupby("team_name")
        .size()
        .to_dict()
    )
    if len(order) >= 2:
        left, right = order[0], order[1]
        return f"{left} {goals.get(left, 0)} - {goals.get(right, 0)} {right}"
    if order:
        return f"{order[0]} {goals.get(order[0], 0)}"
    return "Scoreline unavailable"


def build_stats_bar(stats_df: pd.DataFrame) -> go.Figure:
    melted = stats_df.melt(id_vars="Team", var_name="Stat", value_name="Value")
    fig = px.bar(
        melted,
        x="Stat",
        y="Value",
        color="Team",
        barmode="group",
        title="Key stats by team",
    )
    fig.update_layout(template="plotly_white")
    return fig


def build_shot_timeline(df_match: pd.DataFrame, order: list[str]) -> go.Figure:
    shots = df_match[df_match["event"].isin(SHOT_EVENTS)].copy()
    shots = shots[shots["time_min"].notna()]
    if shots.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No shots recorded",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
        fig.update_layout(
            title="Shots by minute",
            xaxis_title="Minute",
            yaxis_title="Shots",
            template="plotly_white",
        )
        return fig
    fig = px.histogram(
        shots,
        x="time_min",
        color="team_name",
        nbins=18,
        category_orders={"team_name": order},
        title="Shots by minute",
    )
    fig.update_layout(
        barmode="group",
        xaxis_title="Minute",
        yaxis_title="Shots",
        template="plotly_white",
    )
    return fig


def build_possession_pie(df_match: pd.DataFrame, order: list[str]) -> go.Figure:
    possession = df_match[df_match["event"].isin(POSSESSION_EVENTS)]
    counts = (
        possession.groupby("team_name")
        .size()
        .reindex(order, fill_value=0)
        .reset_index()
    )
    fig = px.pie(
        counts,
        names="team_name",
        values=0,
        hole=0.4,
        title="Possession actions (passes + carries)",
    )
    fig.update_layout(template="plotly_white")
    return fig


df_all = load_data()
labels_df = match_labels(df_all)
default_match_id = labels_df["match_id"].iloc[0]

match_summaries = []
for match_id in labels_df["match_id"]:
    df_match = df_all[df_all["match_id"] == match_id]
    order = team_order(df_match)
    scoreline = build_scoreline(df_match, order)
    match_summaries.append(
        {
            "Match": labels_df.loc[labels_df["match_id"] == match_id, "label"].iloc[0],
            "Scoreline": scoreline,
        }
    )

summary_table = dash_table.DataTable(
    data=match_summaries,
    columns=[{"name": "Match", "id": "Match"}, {"name": "Scoreline", "id": "Scoreline"}],
    style_table={"overflowX": "auto"},
    style_cell={"textAlign": "left", "padding": "6px"},
)

app = Dash(__name__)
app.title = "Sporting Match Analysis"

app.layout = html.Div(
    [
        html.H1("Sporting Match Analysis"),
        html.P(
            "Select a match to review scorelines, key stats, and event trends from Sporting_Matches.csv."
        ),
        html.H2("Scorelines (all matches)"),
        summary_table,
        html.H2("Match analysis"),
        dcc.Dropdown(
            id="match-select",
            options=[
                {"label": row["label"], "value": row["match_id"]}
                for _, row in labels_df.iterrows()
            ],
            value=default_match_id,
            clearable=False,
        ),
        html.H3(id="scoreline"),
        dash_table.DataTable(
            id="stats-table",
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "padding": "6px"},
        ),
        html.Div(
            [
                dcc.Graph(id="stats-bar"),
                dcc.Graph(id="shots-timeline"),
                dcc.Graph(id="possession-pie"),
            ]
        ),
    ],
    style={"maxWidth": "1200px", "margin": "0 auto", "padding": "16px"},
)


@app.callback(
    Output("scoreline", "children"),
    Output("stats-table", "data"),
    Output("stats-table", "columns"),
    Output("stats-bar", "figure"),
    Output("shots-timeline", "figure"),
    Output("possession-pie", "figure"),
    Input("match-select", "value"),
)
def update_match(match_id: str):
    df_match = df_all[df_all["match_id"] == match_id]
    order = team_order(df_match)
    stats_df = build_stats(df_match, order)
    scoreline = build_scoreline(df_match, order)
    stats_data = stats_df.to_dict("records")
    stats_columns = [{"name": col, "id": col} for col in stats_df.columns]
    return (
        scoreline,
        stats_data,
        stats_columns,
        build_stats_bar(stats_df),
        build_shot_timeline(df_match, order),
        build_possession_pie(df_match, order),
    )


if __name__ == "__main__":
    app.run_server(debug=True)
