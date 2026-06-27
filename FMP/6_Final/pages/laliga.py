"""LaLiga landing page: teams grid + tabbed sections."""

from dash import html

from utils.constants import CARD_BG, BORDER, TEXT_MUTED
from utils.data_loader import ALL_TEAM_CODES, TEAM_DATA
from components.ui import page_header, dashed_box


def page_teams_grid():
    """4 × 5 grid of team cards, each using the dashed-box visual language."""
    return html.Div([
        html.Button(
            [
                html.Img(
                    src=f"/logos/{TEAM_DATA[code]['logo']}",
                    style={"width": "80px", "height": "80px", "objectFit": "contain"},
                ),
                html.Div(TEAM_DATA[code]["display"], style={
                    "fontSize":      "1rem",
                    "fontWeight":    "600",
                    "textAlign":     "center",
                    "lineHeight":    "1.3",
                    "marginTop":     "10px",
                    "color":         TEXT_MUTED,
                    "fontFamily":    "'Bebas Neue', sans-serif",
                    "letterSpacing": "1px",
                }),
            ],
            id={"type": "team-card", "code": code},
            style={
                "background":     CARD_BG,
                "border":         f"2px solid {BORDER}",
                "borderRadius":   "10px",
                "minHeight":      "140px",
                "display":        "flex",
                "flexDirection":  "column",
                "alignItems":     "center",
                "justifyContent": "center",
                "cursor":         "pointer",
                "transition":     "all 0.2s",
                "width":          "100%",
                "padding":        "16px 8px",
            },
        )
        for code in ALL_TEAM_CODES
    ], style={"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": "16px"})


def page_laliga(nav):
    tab_key = nav.get("laliga_tab", "teams")
    content = page_teams_grid() if tab_key == "teams" else dashed_box()
    return html.Div([
        page_header("LALIGA", "2025/26 Season · Spain · Primera División"),
        content,
    ])
