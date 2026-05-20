import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc
from datetime import datetime

# Load and preprocess data
df = pd.read_csv('Sporting_Matches_1.csv')

# Convert timestamp columns with mixed format handling
df['timeStamp'] = pd.to_datetime(df['timeStamp'], format='mixed', utc=True)
df['local_date'] = pd.to_datetime(df['local_date'], format='mixed', utc=True)

# Extract basic match information
matches = df.groupby('match_id').agg({
    'local_date': 'first',
    'team_name': lambda x: list(x.unique())[:2],
    'team_code': lambda x: list(x.unique())[:2],
}).reset_index()

matches['match_label'] = matches.apply(
    lambda x: f"{x['team_code'][0]} vs {x['team_code'][1]} ({x['local_date'].strftime('%Y-%m-%d')})",
    axis=1
)

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
                id='match-selector',
                options=[{'label': label, 'value': mid} for mid, label in zip(matches['match_id'], matches['match_label'])],
                value=matches['match_id'].iloc[0],
                clearable=False,
                className="mb-4"
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
                            html.Div(id='match-overview')
                        ])
                    ])
                ]
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
                            dcc.Graph(id='pass-stats-graph')
                        ])
                    ])
                ]
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
                            dcc.Graph(id='event-timeline-graph')
                        ])
                    ])
                ]
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
                            dcc.Graph(id='event-distribution-graph')
                        ])
                    ])
                ]
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
                            dcc.Graph(id='top-players-graph')
                        ])
                    ])
                ]
            )
        ], width=6)
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
                            dcc.Graph(id='pass-map-home')
                        ])
                    ])
                ]
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
                            dcc.Graph(id='pass-map-away')
                        ])
                    ])
                ]
            )
        ], width=6)
    ], className="mb-4"),

], fluid=True)

# Callback for match overview
@app.callback(
    Output('match-overview', 'children'),
    Input('match-selector', 'value')
)
def update_overview(match_id):
    match_data = df[df['match_id'] == match_id]
    teams = match_data['team_name'].unique()
    
    team_stats = []
    for team in teams:
        team_data = match_data[match_data['team_name'] == team]
        passes = len(team_data[team_data['event'] == 'Pass'])
        shots = len(team_data[team_data['event'].isin(['Saved Shot', 'Miss', 'Goal'])])
        fouls = len(team_data[team_data['event'] == 'Foul'])
        
        team_stats.append({
            'team': team,
            'passes': passes,
            'shots': shots,
            'fouls': fouls
        })
    
    return dbc.Row([
        dbc.Col([
            html.Div([
                html.H5(stat['team']),
                html.P(f"Passes: {stat['passes']}"),
                html.P(f"Shots: {stat['shots']}"),
                html.P(f"Fouls: {stat['fouls']}")
            ])
        ], width=6) for stat in team_stats
    ])

# Callback for pass statistics
@app.callback(
    Output('pass-stats-graph', 'figure'),
    Input('match-selector', 'value')
)
def update_pass_stats(match_id):
    match_data = df[df['match_id'] == match_id]
    pass_data = match_data[match_data['event'] == 'Pass']
    
    stats = pass_data.groupby('team_name').agg({
        'outcome': lambda x: (x == 1).sum(),
        'match_id': 'count'
    }).rename(columns={'match_id': 'total_passes'})
    stats['pass_accuracy'] = (stats['outcome'] / stats['total_passes'] * 100).round(2)
    stats = stats.reset_index()
    
    fig = go.Figure(data=[
        go.Bar(x=stats['team_name'], y=stats['total_passes'], name='Total Passes', marker_color='lightblue'),
        go.Bar(x=stats['team_name'], y=stats['outcome'], name='Successful Passes', marker_color='green')
    ])
    
    fig.update_layout(
        barmode='group',
        title='Pass Statistics by Team',
        xaxis_title='Team',
        yaxis_title='Number of Passes',
        hovermode='x unified'
    )
    
    return fig

# Callback for event timeline
@app.callback(
    Output('event-timeline-graph', 'figure'),
    Input('match-selector', 'value')
)
def update_event_timeline(match_id):
    match_data = df[df['match_id'] == match_id]
    
    # Calculate cumulative events by time
    match_data_sorted = match_data.sort_values('time_min')
    
    home_team = match_data[match_data['team_position'] == 'home']['team_name'].iloc[0]
    away_team = match_data[match_data['team_position'] == 'away']['team_name'].iloc[0]
    
    home_events = match_data_sorted[match_data_sorted['team_position'] == 'home']
    away_events = match_data_sorted[match_data_sorted['team_position'] == 'away']
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=home_events['time_min'],
        y=range(len(home_events)),
        mode='lines+markers',
        name=home_team,
        line=dict(color='blue', width=2),
        marker=dict(size=6)
    ))
    
    fig.add_trace(go.Scatter(
        x=away_events['time_min'],
        y=range(len(away_events)),
        mode='lines+markers',
        name=away_team,
        line=dict(color='red', width=2),
        marker=dict(size=6)
    ))
    
    fig.update_layout(
        title='Cumulative Events Timeline',
        xaxis_title='Match Time (minutes)',
        yaxis_title='Cumulative Events',
        hovermode='x unified'
    )
    
    return fig

# Callback for event distribution
@app.callback(
    Output('event-distribution-graph', 'figure'),
    Input('match-selector', 'value')
)
def update_event_distribution(match_id):
    match_data = df[df['match_id'] == match_id]
    event_counts = match_data['event'].value_counts().head(10)
    
    fig = px.bar(
        x=event_counts.index,
        y=event_counts.values,
        title='Top 10 Event Types',
        labels={'x': 'Event Type', 'y': 'Count'},
        color=event_counts.values,
        color_continuous_scale='Viridis'
    )
    
    fig.update_layout(showlegend=False)
    
    return fig

# Callback for top players
@app.callback(
    Output('top-players-graph', 'figure'),
    Input('match-selector', 'value')
)
def update_top_players(match_id):
    match_data = df[df['match_id'] == match_id]
    match_data = match_data[match_data['player_name'].notna()]
    
    player_actions = match_data['player_name'].value_counts().head(10)
    
    fig = px.bar(
        y=player_actions.index,
        x=player_actions.values,
        orientation='h',
        title='Top 10 Players by Actions',
        labels={'x': 'Number of Actions', 'y': 'Player Name'},
        color=player_actions.values,
        color_continuous_scale='Plasma'
    )
    
    fig.update_layout(showlegend=False)
    
    return fig

# Callback for pass map - home team
@app.callback(
    Output('pass-map-home', 'figure'),
    Input('match-selector', 'value')
)
def update_pass_map_home(match_id):
    match_data = df[df['match_id'] == match_id]
    home_passes = match_data[
        (match_data['team_position'] == 'home') & 
        (match_data['event'] == 'Pass') &
        (match_data['x'].notna()) &
        (match_data['Pass End X'].notna())
    ]
    
    fig = go.Figure()
    
    # Add field background
    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=68,
                  line=dict(color="white", width=2),
                  fillcolor="green", opacity=0.1)
    
    # Add successful passes
    successful = home_passes[home_passes['outcome'] == 1]
    fig.add_trace(go.Scatter(
        x=successful['x'],
        y=successful['y'],
        mode='markers',
        name='Pass Start',
        marker=dict(size=5, color='blue', opacity=0.6),
        text=successful['player_name'],
        hoverinfo='text'
    ))
    
    # Add unsuccessful passes
    unsuccessful = home_passes[home_passes['outcome'] == 0]
    fig.add_trace(go.Scatter(
        x=unsuccessful['x'],
        y=unsuccessful['y'],
        mode='markers',
        name='Failed Pass',
        marker=dict(size=5, color='red', opacity=0.6),
        text=unsuccessful['player_name'],
        hoverinfo='text'
    ))
    
    # Add pass arrows for successful passes only (limit to avoid clutter)
    for _, row in successful.head(50).iterrows():
        if pd.notna(row['Pass End X']) and pd.notna(row['Pass End Y']):
            fig.add_annotation(
                x=row['Pass End X'], y=row['Pass End Y'],
                ax=row['x'], ay=row['y'],
                xref="x", yref="y",
                axref="x", ayref="y",
                arrowhead=2, arrowsize=1, arrowwidth=0.5,
                arrowcolor="lightblue", opacity=0.3
            )
    
    home_team = match_data[match_data['team_position'] == 'home']['team_name'].iloc[0]
    fig.update_layout(
        title=f'{home_team} - Pass Map',
        xaxis=dict(range=[0, 100], scaleanchor="y", scaleratio=100/68),
        yaxis=dict(range=[0, 68]),
        hovermode='closest',
        height=500
    )
    
    return fig

# Callback for pass map - away team
@app.callback(
    Output('pass-map-away', 'figure'),
    Input('match-selector', 'value')
)
def update_pass_map_away(match_id):
    match_data = df[df['match_id'] == match_id]
    away_passes = match_data[
        (match_data['team_position'] == 'away') & 
        (match_data['event'] == 'Pass') &
        (match_data['x'].notna()) &
        (match_data['Pass End X'].notna())
    ]
    
    fig = go.Figure()
    
    # Add field background
    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=68,
                  line=dict(color="white", width=2),
                  fillcolor="green", opacity=0.1)
    
    # Add successful passes
    successful = away_passes[away_passes['outcome'] == 1]
    fig.add_trace(go.Scatter(
        x=successful['x'],
        y=successful['y'],
        mode='markers',
        name='Pass Start',
        marker=dict(size=5, color='blue', opacity=0.6),
        text=successful['player_name'],
        hoverinfo='text'
    ))
    
    # Add unsuccessful passes
    unsuccessful = away_passes[away_passes['outcome'] == 0]
    fig.add_trace(go.Scatter(
        x=unsuccessful['x'],
        y=unsuccessful['y'],
        mode='markers',
        name='Failed Pass',
        marker=dict(size=5, color='red', opacity=0.6),
        text=unsuccessful['player_name'],
        hoverinfo='text'
    ))
    
    # Add pass arrows for successful passes only (limit to avoid clutter)
    for _, row in successful.head(50).iterrows():
        if pd.notna(row['Pass End X']) and pd.notna(row['Pass End Y']):
            fig.add_annotation(
                x=row['Pass End X'], y=row['Pass End Y'],
                ax=row['x'], ay=row['y'],
                xref="x", yref="y",
                axref="x", ayref="y",
                arrowhead=2, arrowsize=1, arrowwidth=0.5,
                arrowcolor="lightcoral", opacity=0.3
            )
    
    away_team = match_data[match_data['team_position'] == 'away']['team_name'].iloc[0]
    fig.update_layout(
        title=f'{away_team} - Pass Map',
        xaxis=dict(range=[0, 100], scaleanchor="y", scaleratio=100/68),
        yaxis=dict(range=[0, 68]),
        hovermode='closest',
        height=500
    )
    
    return fig

if __name__ == '__main__':
    app.run(debug=True)
