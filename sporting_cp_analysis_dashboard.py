import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from dash import Dash, dcc, html, Input, Output, callback
import dash_bootstrap_components as dbc
import warnings
warnings.filterwarnings('ignore')

# Load and preprocess data
df = pd.read_csv('Sporting_Matches_1.csv', low_memory=False)

# Filter for Sporting CP only
sporting_cp_team_name = 'Sporting Clube de Portugal'
sporting_df = df[df['team_name'] == sporting_cp_team_name].copy()

# Get unique matches for Sporting CP
matches = sporting_df.groupby('match_id').agg({
    'local_date': 'first',
}).reset_index()

# Construct match labels with opponent info
def get_opponent(match_id):
    teams = df[df['match_id'] == match_id]['team_name'].unique()
    opponent = [t for t in teams if t != sporting_cp_team_name]
    return opponent[0] if opponent else 'Unknown'

matches['opponent'] = matches['match_id'].apply(get_opponent)
matches['match_date'] = pd.to_datetime(matches['local_date'])
matches['match_label'] = (
    'Sporting CP vs ' + matches['opponent'] + 
    ' (' + matches['match_date'].dt.strftime('%Y-%m-%d') + ')'
)

# Initialize Dash app
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Define app layout
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.H1("⚽ Sporting CP Match Analysis", className="mb-2 mt-4 text-center", style={'color': '#1CAC4D'})
        ])
    ]),
    
    dbc.Row([
        dbc.Col([
            dcc.Dropdown(
                id='match-selector',
                options=[{'label': label, 'value': mid} for mid, label in zip(matches['match_id'], matches['match_label'])],
                value=matches['match_id'].iloc[0] if len(matches) > 0 else None,
                clearable=False,
                className="mb-4"
            )
        ], width=12)
    ]),

    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-overview",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Match Summary", className="card-title"),
                            html.Div(id='match-summary')
                        ])
                    ])
                ]
            )
        ], width=12)
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-stats",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Key Statistics", className="card-title"),
                            html.Div(id='key-stats')
                        ])
                    ])
                ]
            )
        ], width=12)
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-attacking",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Attacking Pattern Heatmap", className="card-title"),
                            html.P("Pass Initiation Zones", className="text-muted small"),
                            dcc.Graph(id='attacking-heatmap')
                        ])
                    ])
                ]
            )
        ], width=6),
        dbc.Col([
            dcc.Loading(
                id="loading-receive",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Pass Receive Heatmap", className="card-title"),
                            html.P("Pass Reception Zones", className="text-muted small"),
                            dcc.Graph(id='receive-heatmap')
                        ])
                    ])
                ]
            )
        ], width=6)
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-chance",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Chance Creation Heatmap", className="card-title"),
                            html.P("Shot Attempts & Big Chances", className="text-muted small"),
                            dcc.Graph(id='chance-heatmap')
                        ])
                    ])
                ]
            )
        ], width=6),
        dbc.Col([
            dcc.Loading(
                id="loading-defense",
                type="default",
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Defensive Action Map", className="card-title"),
                            html.P("Tackles, Interceptions & Clearances", className="text-muted small"),
                            dcc.Graph(id='defense-heatmap')
                        ])
                    ])
                ]
            )
        ], width=6)
    ], className="mb-4"),

], fluid=True)


def create_heatmap(data, title, color_scale='Blues', height=500):
    """Helper function to create density heatmap from coordinate data"""
    if len(data) < 2:
        # Return empty figure if not enough data
        fig = go.Figure()
        fig.add_annotation(text="Insufficient data for this visualization")
        fig.update_layout(
            title=title,
            xaxis=dict(range=[0, 100], scaleanchor="y", scaleratio=100/68),
            yaxis=dict(range=[0, 68]),
            height=height
        )
        return fig

    # Create figure with field background
    fig = go.Figure()
    
    # Add field background
    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=68,
                  line=dict(color="white", width=2),
                  fillcolor="rgba(34, 139, 34, 0.1)", opacity=0.2)
    
    # Create 2D histogram (heatmap)
    fig.add_trace(go.Histogram2d(
        x=data['x'],
        y=data['y'],
        nbinsx=10,
        nbinsy=8,
        colorscale=color_scale,
        name='Density',
        colorbar=dict(title="Count"),
        hovertemplate='<b>Zone</b><br>X: %{x}<br>Y: %{y}<br>Count: %{z}<extra></extra>'
    ))
    
    # Add field markings (optional)
    fig.add_vline(x=50, line_dash="dash", line_color="white", opacity=0.3)
    
    fig.update_layout(
        title=title,
        xaxis=dict(
            title="Field Width",
            range=[0, 100],
            scaleanchor="y",
            scaleratio=100/68
        ),
        yaxis=dict(
            title="Field Height",
            range=[0, 68]
        ),
        height=height,
        hovermode='closest',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis_showgrid=False,
        yaxis_showgrid=False
    )
    
    return fig


@app.callback(
    [Output('match-summary', 'children'),
     Output('key-stats', 'children'),
     Output('attacking-heatmap', 'figure'),
     Output('receive-heatmap', 'figure'),
     Output('chance-heatmap', 'figure'),
     Output('defense-heatmap', 'figure')],
    Input('match-selector', 'value')
)
def update_all(match_id):
    if match_id is None:
        return [html.P("No match selected")]*6
    
    # Get match data
    match_data = sporting_df[sporting_df['match_id'] == match_id]
    if len(match_data) == 0:
        return [html.P("No data for this match")]*6
    
    # Get opponent
    opponent = get_opponent(match_id)
    
    # Basic stats
    total_events = len(match_data)
    passes = len(match_data[match_data['event'] == 'Pass'])
    successful_passes = len(match_data[(match_data['event'] == 'Pass') & (match_data['outcome'] == 1)])
    pass_accuracy = (successful_passes / passes * 100) if passes > 0 else 0
    
    shots = len(match_data[match_data['event'].isin(['Saved Shot', 'Miss', 'Goal', 'Post'])])
    goals = len(match_data[match_data['event'] == 'Goal'])
    
    # Defensive stats
    defensive_events = match_data[match_data['event'].isin(
        ['Tackle', 'Interception', 'Clearance', 'Challenge', 'Block']
    )]
    total_defensive_actions = len(defensive_events)
    
    # Calculate PPDA (Passes Per Defensive Action)
    ppda = passes / total_defensive_actions if total_defensive_actions > 0 else 0
    
    # Estimate match duration
    match_duration = match_data['period_length'].max() if 'period_length' in match_data.columns else 90
    defensive_actions_per_90 = (total_defensive_actions / match_duration) * 90 if match_duration > 0 else 0
    
    # Create summary
    summary = dbc.Row([
        dbc.Col([
            html.Div([
                html.H5(f"Sporting CP vs {opponent}"),
                html.P(f"Total Events: {total_events}")
            ], className="border-end pe-3")
        ], width=3),
        dbc.Col([
            html.Div([
                html.H5(f"{passes} Passes"),
                html.P(f"Accuracy: {pass_accuracy:.1f}%")
            ], className="border-end pe-3")
        ], width=3),
        dbc.Col([
            html.Div([
                html.H5(f"{shots} Shots"),
                html.P(f"Goals: {goals}")
            ], className="border-end pe-3")
        ], width=3),
        dbc.Col([
            html.Div([
                html.H5(f"{total_defensive_actions} Defensive"),
                html.P(f"Actions")
            ])
        ], width=3)
    ])
    
    # Create key stats
    shot_eff = goals / shots * 100 if shots > 0 else 0
    key_stats = dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("PPDA", className="card-title"),
                    html.H4(f"{ppda:.2f}", style={'color': '#1CAC4D'}),
                    html.P("Passes Per Defensive Action", className="small text-muted")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("Def Actions/90", className="card-title"),
                    html.H4(f"{defensive_actions_per_90:.1f}", style={'color': '#1CAC4D'}),
                    html.P("Defensive Actions per 90 min", className="small text-muted")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("Pass Accuracy", className="card-title"),
                    html.H4(f"{pass_accuracy:.1f}%", style={'color': '#1CAC4D'}),
                    html.P("Successful Pass Rate", className="small text-muted")
                ])
            ])
        ], width=3),
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H6("Shot Efficiency", className="card-title"),
                    html.H4(f"{shot_eff:.1f}%", style={'color': '#1CAC4D'}),
                    html.P("Goals per Shot", className="small text-muted")
                ])
            ])
        ], width=3)
    ])
    
    # ===== HEATMAP DATA EXTRACTION =====
    
    # 1. Attacking Pattern - Pass Initiation
    attacking_passes = match_data[
        (match_data['event'] == 'Pass') & 
        (match_data['x'].notna()) &
        (match_data['y'].notna())
    ][['x', 'y']].copy()
    
    attacking_heatmap = create_heatmap(
        attacking_passes,
        "Attacking Pattern - Pass Initiation",
        color_scale='Blues'
    )
    
    # 2. Pass Receive - Where passes are completed
    receive_passes = match_data[
        (match_data['event'] == 'Pass') & 
        (match_data['outcome'] == 1) &
        (match_data['Pass End X'].notna()) &
        (match_data['Pass End Y'].notna())
    ][['Pass End X', 'Pass End Y']].copy()
    receive_passes.columns = ['x', 'y']
    
    receive_heatmap = create_heatmap(
        receive_passes,
        "Pass Reception - Where Passes End",
        color_scale='Greens'
    )
    
    # 3. Chance Creation - Shots and Big Chances
    chance_events = match_data[
        (match_data['event'].isin(['Saved Shot', 'Miss', 'Goal', 'Post', 'Big Chance'])) &
        (match_data['x'].notna()) &
        (match_data['y'].notna())
    ][['x', 'y']].copy()
    
    chance_heatmap = create_heatmap(
        chance_events,
        "Chance Creation - Shot & Big Chance Zones",
        color_scale='Reds'
    )
    
    # 4. Defensive Action Map - Tackles, Interceptions, etc.
    defense_actions = match_data[
        (match_data['event'].isin(['Tackle', 'Interception', 'Clearance', 'Challenge', 'Block'])) &
        (match_data['x'].notna()) &
        (match_data['y'].notna())
    ][['x', 'y']].copy()
    
    defense_heatmap = create_heatmap(
        defense_actions,
        "Defensive Action Map - Pressure Zones",
        color_scale='Purples'
    )
    
    return summary, key_stats, attacking_heatmap, receive_heatmap, chance_heatmap, defense_heatmap


if __name__ == '__main__':
    app.run_server(debug=True, port=8050)
