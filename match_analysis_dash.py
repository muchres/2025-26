import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc


def pick_first_column(columns, candidates):
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def bool_like(series):
    if series is None:
        return pd.Series(False, index=df.index)
    normalized = series.astype(str).str.strip().str.lower()
    return normalized.isin({"1", "1.0", "true", "yes", "y", "t"})


def empty_figure(title, message):
    fig = go.Figure()
    fig.update_layout(
        title=title,
        template="plotly_white",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[
            dict(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(size=14))
        ],
        height=500,
    )
    return fig


def in_final_third(x_series):
    return (x_series >= 66.7) | (x_series <= 33.3)


def in_zone_14(x_series, y_series):
    right_zone = (x_series >= 75) & (x_series <= 88) & (y_series >= 22.67) & (y_series <= 45.33)
    left_zone = (x_series >= 12) & (x_series <= 25) & (y_series >= 22.67) & (y_series <= 45.33)
    return right_zone | left_zone


def get_match_date_label(value):
    if pd.isna(value):
        return "Unknown date"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return str(value)


def get_home_away_names(match_data):
    if TEAM_POSITION_COL and TEAM_POSITION_COL in match_data.columns:
        home = match_data[match_data[TEAM_POSITION_COL].astype(str).str.lower() == "home"][TEAM_NAME_COL].dropna()
        away = match_data[match_data[TEAM_POSITION_COL].astype(str).str.lower() == "away"][TEAM_NAME_COL].dropna()
        if not home.empty and not away.empty:
            return home.iloc[0], away.iloc[0]
    unique_teams = match_data[TEAM_NAME_COL].dropna().unique().tolist()
    if len(unique_teams) >= 2:
        return unique_teams[0], unique_teams[1]
    team = unique_teams[0] if unique_teams else "Team"
    return team, "Opponent"


def get_end_coordinates(frame):
    end_x = pd.Series(float("nan"), index=frame.index, dtype="float64")
    end_y = pd.Series(float("nan"), index=frame.index, dtype="float64")

    if PASS_END_X_COL and PASS_END_X_COL in frame.columns:
        end_x = frame[PASS_END_X_COL].copy()
    if PASS_END_Y_COL and PASS_END_Y_COL in frame.columns:
        end_y = frame[PASS_END_Y_COL].copy()

    if CARRY_END_X_COL and CARRY_END_X_COL in frame.columns:
        end_x = end_x.fillna(frame[CARRY_END_X_COL])
    if CARRY_END_Y_COL and CARRY_END_Y_COL in frame.columns:
        end_y = end_y.fillna(frame[CARRY_END_Y_COL])

    return end_x, end_y


def chance_creator_table(match_data):
    if not EVENT_COL or not PLAYER_COL:
        return pd.DataFrame(columns=["team", "player", "chances_created"])

    events = match_data[EVENT_COL].astype(str).str.lower()
    pass_rows = match_data[events == "pass"].copy()
    if pass_rows.empty:
        return pd.DataFrame(columns=["team", "player", "chances_created"])

    pass_rows = pass_rows[pass_rows[PLAYER_COL].notna()]
    if TEAM_NAME_COL:
        pass_rows = pass_rows[pass_rows[TEAM_NAME_COL].notna()]

    score = pd.Series(0, index=pass_rows.index, dtype="float64")

    available_flags = [col for col in CHANCE_FLAG_COLUMNS if col in pass_rows.columns]
    if available_flags:
        explicit_mask = pd.Series(False, index=pass_rows.index)
        for col in available_flags:
            explicit_mask = explicit_mask | bool_like(pass_rows[col])
        score = score + explicit_mask.astype(int)

    if EVENT_ID_COL and RELATED_EVENT_COL and EVENT_ID_COL in pass_rows.columns and RELATED_EVENT_COL in match_data.columns:
        shot_like = events.str.contains("shot|goal|miss|post|bar", na=False)
        related = pd.to_numeric(match_data.loc[shot_like, RELATED_EVENT_COL], errors="coerce").dropna()
        if not related.empty:
            linked_ids = set(related.astype(float).astype(int).tolist())
            pass_ids = pd.to_numeric(pass_rows[EVENT_ID_COL], errors="coerce").fillna(-1).astype(int)
            score = score + pass_ids.isin(linked_ids).astype(int)

    if PASS_END_X_COL and OUTCOME_COL and PASS_END_X_COL in pass_rows.columns and OUTCOME_COL in pass_rows.columns:
        successful = pd.to_numeric(pass_rows[OUTCOME_COL], errors="coerce").fillna(0) == 1
        penalty_zone = (pass_rows[PASS_END_X_COL] >= 83) | (pass_rows[PASS_END_X_COL] <= 17)
        score = score + (successful & penalty_zone).astype(int) * 0.5

    pass_rows["chance_score"] = score
    pass_rows = pass_rows[pass_rows["chance_score"] > 0]
    if pass_rows.empty:
        return pd.DataFrame(columns=["team", "player", "chances_created"])

    grouped = (
        pass_rows.groupby([TEAM_NAME_COL, PLAYER_COL], dropna=False)["chance_score"]
        .sum()
        .reset_index()
        .rename(columns={TEAM_NAME_COL: "team", PLAYER_COL: "player", "chance_score": "chances_created"})
    )
    grouped["chances_created"] = grouped["chances_created"].round(2)
    return grouped.sort_values("chances_created", ascending=False)


def entry_table(match_data):
    if not TEAM_NAME_COL or not X_COL or not Y_COL:
        return pd.DataFrame(columns=["team", "final_third_entries", "zone14_entries"])

    rows = match_data.copy()
    if EVENT_COL:
        rows = rows[rows[EVENT_COL].astype(str).str.lower().isin(["pass", "carry", "take on", "dribble"])]

    if rows.empty:
        return pd.DataFrame(columns=["team", "final_third_entries", "zone14_entries"])

    end_x, end_y = get_end_coordinates(rows)
    valid = rows[X_COL].notna() & rows[Y_COL].notna() & end_x.notna() & end_y.notna() & rows[TEAM_NAME_COL].notna()
    rows = rows[valid].copy()
    end_x = end_x[valid]
    end_y = end_y[valid]

    if rows.empty:
        return pd.DataFrame(columns=["team", "final_third_entries", "zone14_entries"])

    start_final = in_final_third(rows[X_COL])
    end_final = in_final_third(end_x)
    start_z14 = in_zone_14(rows[X_COL], rows[Y_COL])
    end_z14 = in_zone_14(end_x, end_y)

    rows["final_third_entry"] = (~start_final & end_final).astype(int)
    rows["zone14_entry"] = (~start_z14 & end_z14).astype(int)

    grouped = (
        rows.groupby(TEAM_NAME_COL)[["final_third_entry", "zone14_entry"]]
        .sum()
        .reset_index()
        .rename(
            columns={
                TEAM_NAME_COL: "team",
                "final_third_entry": "final_third_entries",
                "zone14_entry": "zone14_entries",
            }
        )
    )
    return grouped


# Load and preprocess data
df = pd.read_csv("Sporting_Matches_1.csv", low_memory=False)

DATE_COL = pick_first_column(df.columns, ["local_date", "match_date", "date"])
TIMESTAMP_COL = pick_first_column(df.columns, ["timeStamp", "timestamp"])
MATCH_ID_COL = pick_first_column(df.columns, ["match_id"])
TEAM_NAME_COL = pick_first_column(df.columns, ["team_name", "team"])
TEAM_CODE_COL = pick_first_column(df.columns, ["team_code", "team_short_name"])
TEAM_POSITION_COL = pick_first_column(df.columns, ["team_position"])
EVENT_COL = pick_first_column(df.columns, ["event", "event_type"])
PLAYER_COL = pick_first_column(df.columns, ["player_name", "player"])
X_COL = pick_first_column(df.columns, ["x", "start_x"])
Y_COL = pick_first_column(df.columns, ["y", "start_y"])
PASS_END_X_COL = pick_first_column(df.columns, ["Pass End X", "pass_end_x", "end_x"])
PASS_END_Y_COL = pick_first_column(df.columns, ["Pass End Y", "pass_end_y", "end_y"])
CARRY_END_X_COL = pick_first_column(df.columns, ["Carry End X", "carry_end_x"])
CARRY_END_Y_COL = pick_first_column(df.columns, ["Carry End Y", "carry_end_y"])
OUTCOME_COL = pick_first_column(df.columns, ["outcome", "result"])
EVENT_ID_COL = pick_first_column(df.columns, ["event_id", "id"])
RELATED_EVENT_COL = pick_first_column(df.columns, ["Related event ID", "related_event_id"])
RECEIVER_COL = pick_first_column(df.columns, ["receiver_name", "pass_recipient", "recipient_name"])

CHANCE_FLAG_COLUMNS = [
    "Intentional Assist",
    "Assist",
    "Assisted",
    "Big Chance",
    "Leading to attempt",
    "Leading to goal",
]

for col in [
    X_COL,
    Y_COL,
    PASS_END_X_COL,
    PASS_END_Y_COL,
    CARRY_END_X_COL,
    CARRY_END_Y_COL,
    OUTCOME_COL,
    EVENT_ID_COL,
    RELATED_EVENT_COL,
    "time_min",
    "time_sec",
]:
    if col and col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

if TIMESTAMP_COL and TIMESTAMP_COL in df.columns:
    df[TIMESTAMP_COL] = pd.to_datetime(df[TIMESTAMP_COL], format="mixed", utc=True, errors="coerce")
if DATE_COL and DATE_COL in df.columns:
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], format="mixed", utc=True, errors="coerce")


# Extract basic match information
agg_spec = {
    TEAM_NAME_COL: lambda x: [team for team in x.dropna().unique()][:2],
}
if DATE_COL:
    agg_spec[DATE_COL] = "first"
if TEAM_CODE_COL:
    agg_spec[TEAM_CODE_COL] = lambda x: [code for code in x.dropna().unique()][:2]

matches = df.groupby(MATCH_ID_COL).agg(agg_spec).reset_index()


def build_match_label(row):
    codes = row.get(TEAM_CODE_COL) if TEAM_CODE_COL else None
    names = row.get(TEAM_NAME_COL) if TEAM_NAME_COL else None
    teams = []
    if isinstance(codes, list) and len(codes) >= 2:
        teams = codes[:2]
    elif isinstance(names, list) and len(names) >= 2:
        teams = names[:2]
    elif isinstance(names, list) and len(names) == 1:
        teams = [names[0], "Opponent"]
    else:
        teams = ["Home", "Away"]

    date_value = row.get(DATE_COL) if DATE_COL else None
    return f"{teams[0]} vs {teams[1]} ({get_match_date_label(date_value)})"


matches["match_label"] = matches.apply(build_match_label, axis=1)

# Initialize Dash app
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Define app layout
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.H1("⚽ Match Analysis Dashboard", className="mb-4 mt-4 text-center")
        ])
    ]),

    dbc.Row([
        dbc.Col([
            dcc.Dropdown(
                id="match-selector",
                options=[{"label": label, "value": mid} for mid, label in zip(matches[MATCH_ID_COL], matches["match_label"])],
                value=matches[MATCH_ID_COL].iloc[0],
                clearable=False,
                className="mb-4",
            )
        ], width=12)
    ]),

    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-1",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Match Overview", className="card-title"),
                            html.Div(id="match-overview"),
                        ])
                    ])
                ],
            )
        ], width=12)
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-2",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Pass Statistics by Team", className="card-title"),
                            dcc.Graph(id="pass-stats-graph"),
                        ])
                    ])
                ],
            )
        ], width=12)
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-3",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Event Timeline", className="card-title"),
                            dcc.Graph(id="event-timeline-graph"),
                        ])
                    ])
                ],
            )
        ], width=12)
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-4",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Event Type Distribution", className="card-title"),
                            dcc.Graph(id="event-distribution-graph"),
                        ])
                    ])
                ],
            )
        ], width=6),
        dbc.Col([
            dcc.Loading(
                id="loading-5",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Top Players by Actions", className="card-title"),
                            dcc.Graph(id="top-players-graph"),
                        ])
                    ])
                ],
            )
        ], width=6),
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-6",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Pass Map - Home Team", className="card-title"),
                            dcc.Graph(id="pass-map-home"),
                        ])
                    ])
                ],
            )
        ], width=6),
        dbc.Col([
            dcc.Loading(
                id="loading-7",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Pass Map - Away Team", className="card-title"),
                            dcc.Graph(id="pass-map-away"),
                        ])
                    ])
                ],
            )
        ], width=6),
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-8",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Passing Network", className="card-title"),
                            dcc.Graph(id="passing-network-graph"),
                        ])
                    ])
                ],
            )
        ], width=12),
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-9",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Chance Creation Leaders", className="card-title"),
                            dcc.Graph(id="chance-creation-graph"),
                        ])
                    ])
                ],
            )
        ], width=6),
        dbc.Col([
            dcc.Loading(
                id="loading-10",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Final Third & Zone 14 Entries", className="card-title"),
                            dcc.Graph(id="zone-entries-graph"),
                        ])
                    ])
                ],
            )
        ], width=6),
    ], className="mb-4"),

], fluid=True)


# Callback for match overview
@app.callback(
    Output("match-overview", "children"),
    Input("match-selector", "value"),
)
def update_overview(match_id):
    match_data = df[df[MATCH_ID_COL] == match_id]
    teams = match_data[TEAM_NAME_COL].dropna().unique()

    team_stats = []
    for team in teams:
        team_data = match_data[match_data[TEAM_NAME_COL] == team]
        event_values = team_data[EVENT_COL].astype(str)
        passes = len(team_data[event_values == "Pass"])
        shots = len(team_data[event_values.isin(["Saved Shot", "Miss", "Goal"])])
        fouls = len(team_data[event_values == "Foul"])

        team_stats.append({"team": team, "passes": passes, "shots": shots, "fouls": fouls})

    return dbc.Row([
        dbc.Col([
            html.Div([
                html.H5(stat["team"]),
                html.P(f"Passes: {stat['passes']}"),
                html.P(f"Shots: {stat['shots']}"),
                html.P(f"Fouls: {stat['fouls']}"),
            ])
        ], width=6)
        for stat in team_stats
    ])


# Callback for pass statistics
@app.callback(
    Output("pass-stats-graph", "figure"),
    Input("match-selector", "value"),
)
def update_pass_stats(match_id):
    match_data = df[df[MATCH_ID_COL] == match_id]
    pass_data = match_data[match_data[EVENT_COL].astype(str).str.lower() == "pass"]

    if pass_data.empty:
        return empty_figure("Pass Statistics by Team", "No pass events available for this match")

    stats = pass_data.groupby(TEAM_NAME_COL).agg({
        OUTCOME_COL: lambda x: (x == 1).sum(),
        MATCH_ID_COL: "count",
    }).rename(columns={MATCH_ID_COL: "total_passes", OUTCOME_COL: "successful_passes"})

    stats["pass_accuracy"] = (stats["successful_passes"] / stats["total_passes"] * 100).round(2)
    stats = stats.reset_index()

    fig = go.Figure(data=[
        go.Bar(x=stats[TEAM_NAME_COL], y=stats["total_passes"], name="Total Passes", marker_color="lightblue"),
        go.Bar(x=stats[TEAM_NAME_COL], y=stats["successful_passes"], name="Successful Passes", marker_color="green"),
    ])

    fig.update_layout(
        barmode="group",
        title="Pass Statistics by Team",
        xaxis_title="Team",
        yaxis_title="Number of Passes",
        hovermode="x unified",
        template="plotly_white",
    )

    return fig


# Callback for event timeline
@app.callback(
    Output("event-timeline-graph", "figure"),
    Input("match-selector", "value"),
)
def update_event_timeline(match_id):
    match_data = df[df[MATCH_ID_COL] == match_id]

    if "time_min" not in match_data.columns:
        return empty_figure("Cumulative Events Timeline", "No time column available")

    match_data_sorted = match_data.sort_values("time_min")
    home_team, away_team = get_home_away_names(match_data)

    home_events = match_data_sorted[match_data_sorted[TEAM_NAME_COL] == home_team]
    away_events = match_data_sorted[match_data_sorted[TEAM_NAME_COL] == away_team]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=home_events["time_min"],
        y=range(len(home_events)),
        mode="lines+markers",
        name=home_team,
        line=dict(color="blue", width=2),
        marker=dict(size=6),
    ))

    fig.add_trace(go.Scatter(
        x=away_events["time_min"],
        y=range(len(away_events)),
        mode="lines+markers",
        name=away_team,
        line=dict(color="red", width=2),
        marker=dict(size=6),
    ))

    fig.update_layout(
        title="Cumulative Events Timeline",
        xaxis_title="Match Time (minutes)",
        yaxis_title="Cumulative Events",
        hovermode="x unified",
        template="plotly_white",
    )

    return fig


# Callback for event distribution
@app.callback(
    Output("event-distribution-graph", "figure"),
    Input("match-selector", "value"),
)
def update_event_distribution(match_id):
    match_data = df[df[MATCH_ID_COL] == match_id]
    event_counts = match_data[EVENT_COL].value_counts().head(10)

    fig = px.bar(
        x=event_counts.index,
        y=event_counts.values,
        title="Top 10 Event Types",
        labels={"x": "Event Type", "y": "Count"},
        color=event_counts.values,
        color_continuous_scale="Viridis",
    )

    fig.update_layout(showlegend=False, template="plotly_white")

    return fig


# Callback for top players
@app.callback(
    Output("top-players-graph", "figure"),
    Input("match-selector", "value"),
)
def update_top_players(match_id):
    match_data = df[df[MATCH_ID_COL] == match_id]
    match_data = match_data[match_data[PLAYER_COL].notna()]

    player_actions = match_data[PLAYER_COL].value_counts().head(10)

    fig = px.bar(
        y=player_actions.index,
        x=player_actions.values,
        orientation="h",
        title="Top 10 Players by Actions",
        labels={"x": "Number of Actions", "y": "Player Name"},
        color=player_actions.values,
        color_continuous_scale="Plasma",
    )

    fig.update_layout(showlegend=False, template="plotly_white")

    return fig


# Callback for pass map - home team
@app.callback(
    Output("pass-map-home", "figure"),
    Input("match-selector", "value"),
)
def update_pass_map_home(match_id):
    match_data = df[df[MATCH_ID_COL] == match_id]
    home_team, _ = get_home_away_names(match_data)

    home_passes = match_data[
        (match_data[TEAM_NAME_COL] == home_team)
        & (match_data[EVENT_COL].astype(str).str.lower() == "pass")
        & (match_data[X_COL].notna())
        & (match_data[PASS_END_X_COL].notna())
    ]

    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=68, line=dict(color="white", width=2), fillcolor="green", opacity=0.1)

    successful = home_passes[home_passes[OUTCOME_COL] == 1]
    fig.add_trace(go.Scatter(
        x=successful[X_COL],
        y=successful[Y_COL],
        mode="markers",
        name="Pass Start",
        marker=dict(size=5, color="blue", opacity=0.6),
        text=successful[PLAYER_COL],
        hoverinfo="text",
    ))

    unsuccessful = home_passes[home_passes[OUTCOME_COL] == 0]
    fig.add_trace(go.Scatter(
        x=unsuccessful[X_COL],
        y=unsuccessful[Y_COL],
        mode="markers",
        name="Failed Pass",
        marker=dict(size=5, color="red", opacity=0.6),
        text=unsuccessful[PLAYER_COL],
        hoverinfo="text",
    ))

    for _, row in successful.head(50).iterrows():
        if pd.notna(row[PASS_END_X_COL]) and pd.notna(row[PASS_END_Y_COL]):
            fig.add_annotation(
                x=row[PASS_END_X_COL],
                y=row[PASS_END_Y_COL],
                ax=row[X_COL],
                ay=row[Y_COL],
                xref="x",
                yref="y",
                axref="x",
                ayref="y",
                arrowhead=2,
                arrowsize=1,
                arrowwidth=0.5,
                arrowcolor="lightblue",
                opacity=0.3,
            )

    fig.update_layout(
        title=f"{home_team} - Pass Map",
        xaxis=dict(range=[0, 100], scaleanchor="y", scaleratio=100 / 68),
        yaxis=dict(range=[0, 68]),
        hovermode="closest",
        height=500,
        template="plotly_white",
    )

    return fig


# Callback for pass map - away team
@app.callback(
    Output("pass-map-away", "figure"),
    Input("match-selector", "value"),
)
def update_pass_map_away(match_id):
    match_data = df[df[MATCH_ID_COL] == match_id]
    _, away_team = get_home_away_names(match_data)

    away_passes = match_data[
        (match_data[TEAM_NAME_COL] == away_team)
        & (match_data[EVENT_COL].astype(str).str.lower() == "pass")
        & (match_data[X_COL].notna())
        & (match_data[PASS_END_X_COL].notna())
    ]

    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=68, line=dict(color="white", width=2), fillcolor="green", opacity=0.1)

    successful = away_passes[away_passes[OUTCOME_COL] == 1]
    fig.add_trace(go.Scatter(
        x=successful[X_COL],
        y=successful[Y_COL],
        mode="markers",
        name="Pass Start",
        marker=dict(size=5, color="blue", opacity=0.6),
        text=successful[PLAYER_COL],
        hoverinfo="text",
    ))

    unsuccessful = away_passes[away_passes[OUTCOME_COL] == 0]
    fig.add_trace(go.Scatter(
        x=unsuccessful[X_COL],
        y=unsuccessful[Y_COL],
        mode="markers",
        name="Failed Pass",
        marker=dict(size=5, color="red", opacity=0.6),
        text=unsuccessful[PLAYER_COL],
        hoverinfo="text",
    ))

    for _, row in successful.head(50).iterrows():
        if pd.notna(row[PASS_END_X_COL]) and pd.notna(row[PASS_END_Y_COL]):
            fig.add_annotation(
                x=row[PASS_END_X_COL],
                y=row[PASS_END_Y_COL],
                ax=row[X_COL],
                ay=row[Y_COL],
                xref="x",
                yref="y",
                axref="x",
                ayref="y",
                arrowhead=2,
                arrowsize=1,
                arrowwidth=0.5,
                arrowcolor="lightcoral",
                opacity=0.3,
            )

    fig.update_layout(
        title=f"{away_team} - Pass Map",
        xaxis=dict(range=[0, 100], scaleanchor="y", scaleratio=100 / 68),
        yaxis=dict(range=[0, 68]),
        hovermode="closest",
        height=500,
        template="plotly_white",
    )

    return fig


@app.callback(
    Output("passing-network-graph", "figure"),
    Input("match-selector", "value"),
)
def update_passing_network(match_id):
    match_data = df[df[MATCH_ID_COL] == match_id]

    if not RECEIVER_COL:
        return empty_figure("Passing Network", "Receiver column not found in dataset")

    passes = match_data[
        (match_data[EVENT_COL].astype(str).str.lower() == "pass")
        & (match_data[OUTCOME_COL] == 1)
        & (match_data[PLAYER_COL].notna())
        & (match_data[RECEIVER_COL].notna())
        & (match_data[X_COL].notna())
        & (match_data[Y_COL].notna())
    ].copy()

    passes = passes[passes[PLAYER_COL] != passes[RECEIVER_COL]]
    if passes.empty:
        return empty_figure("Passing Network", "No complete passer-receiver links available")

    edge_counts = (
        passes.groupby([TEAM_NAME_COL, PLAYER_COL, RECEIVER_COL])
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .head(30)
    )

    involvement = pd.concat([
        edge_counts[[TEAM_NAME_COL, PLAYER_COL, "count"]].rename(columns={PLAYER_COL: "player"}),
        edge_counts[[TEAM_NAME_COL, RECEIVER_COL, "count"]].rename(columns={RECEIVER_COL: "player"}),
    ])
    top_players = (
        involvement.groupby([TEAM_NAME_COL, "player"])["count"]
        .sum()
        .reset_index()
        .sort_values("count", ascending=False)
        .head(14)
    )

    valid_players = set(top_players["player"])
    edge_counts = edge_counts[
        edge_counts[PLAYER_COL].isin(valid_players) & edge_counts[RECEIVER_COL].isin(valid_players)
    ].copy()
    if edge_counts.empty:
        return empty_figure("Passing Network", "No high-volume pass links for top players")

    node_points = (
        passes[passes[PLAYER_COL].isin(valid_players)]
        .groupby(PLAYER_COL)
        .agg({X_COL: "mean", Y_COL: "mean"})
        .reset_index()
        .rename(columns={PLAYER_COL: "player", X_COL: "x", Y_COL: "y"})
    )

    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=68, line=dict(color="#444", width=1), fillcolor="#f3f8f2")
    fig.add_shape(type="line", x0=50, y0=0, x1=50, y1=68, line=dict(color="#cccccc", width=1))

    pos = {row["player"]: (row["x"], row["y"]) for _, row in node_points.iterrows()}
    max_edge = max(edge_counts["count"].max(), 1)

    for _, edge in edge_counts.iterrows():
        passer = edge[PLAYER_COL]
        receiver = edge[RECEIVER_COL]
        if passer not in pos or receiver not in pos:
            continue
        x0, y0 = pos[passer]
        x1, y1 = pos[receiver]
        width = 1 + (edge["count"] / max_edge) * 5
        fig.add_trace(go.Scatter(
            x=[x0, x1],
            y=[y0, y1],
            mode="lines",
            line=dict(width=width, color="rgba(0,90,160,0.35)"),
            hoverinfo="text",
            text=f"{passer} → {receiver}: {int(edge['count'])}",
            showlegend=False,
        ))

    player_strength = top_players.set_index("player")["count"].to_dict()
    node_size = [12 + player_strength.get(name, 1) for name in node_points["player"]]

    fig.add_trace(go.Scatter(
        x=node_points["x"],
        y=node_points["y"],
        mode="markers+text",
        marker=dict(size=node_size, color="#1f77b4", opacity=0.85, line=dict(color="white", width=1)),
        text=node_points["player"],
        textposition="top center",
        hovertemplate="%{text}<extra></extra>",
        showlegend=False,
    ))

    fig.update_layout(
        title="Passing Network (Top links)",
        xaxis=dict(range=[0, 100], visible=False),
        yaxis=dict(range=[0, 68], visible=False, scaleanchor="x", scaleratio=68 / 100),
        template="plotly_white",
        height=560,
        margin=dict(l=10, r=10, t=60, b=10),
    )
    return fig


@app.callback(
    Output("chance-creation-graph", "figure"),
    Input("match-selector", "value"),
)
def update_chance_creation(match_id):
    match_data = df[df[MATCH_ID_COL] == match_id]
    creators = chance_creator_table(match_data).head(10)

    if creators.empty:
        return empty_figure("Chance Creation Leaders", "No chance creation signals found")

    creators["label"] = creators["player"] + " (" + creators["team"] + ")"
    fig = px.bar(
        creators.sort_values("chances_created", ascending=True),
        x="chances_created",
        y="label",
        orientation="h",
        color="team",
        title="Who creates the most chances?",
        labels={"chances_created": "Chance creation score", "label": "Player"},
    )
    fig.update_layout(template="plotly_white", height=500, legend_title_text="Team")
    return fig


@app.callback(
    Output("zone-entries-graph", "figure"),
    Input("match-selector", "value"),
)
def update_zone_entries(match_id):
    match_data = df[df[MATCH_ID_COL] == match_id]
    entries = entry_table(match_data)

    if entries.empty:
        return empty_figure("Final Third & Zone 14 Entries", "No entries can be computed from available coordinates")

    fig = go.Figure(data=[
        go.Bar(name="Final Third Entries", x=entries["team"], y=entries["final_third_entries"], marker_color="#2a9d8f"),
        go.Bar(name="Zone 14 Entries", x=entries["team"], y=entries["zone14_entries"], marker_color="#e76f51"),
    ])
    fig.update_layout(
        barmode="group",
        template="plotly_white",
        title="Final Third & Zone 14 Entries by Team",
        xaxis_title="Team",
        yaxis_title="Entries",
        height=500,
    )
    return fig


if __name__ == "__main__":
    app.run(debug=True)
