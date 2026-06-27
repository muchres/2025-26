"""Sidebar component — navigation links, collapse/expand styles."""

from dash import html

from utils.constants import SIDEBAR_BG, BORDER, TEXT_MAIN

# ── Sidebar styles ────────────────────────────────────────────────────────────
SIDEBAR_EXPANDED_STYLE = {
    "width": "230px", "minWidth": "230px",
    "background": SIDEBAR_BG, "borderRight": f"1px solid {BORDER}",
    "display": "flex", "flexDirection": "column",
    "transition": "width 0.3s ease", "overflow": "hidden", "flexShrink": "0",
}
SIDEBAR_COLLAPSED_STYLE = {
    "width": "50px", "minWidth": "50px",
    "background": SIDEBAR_BG, "borderRight": f"1px solid {BORDER}",
    "display": "flex", "flexDirection": "column",
    "transition": "width 0.3s ease", "overflow": "hidden", "flexShrink": "0",
}

# ── Navigation items: (key, label, icon_type, icon_value) ────────────────────
# icon_type: "img" → html.Img with src=icon_value; "emoji" → text span
_NAV_ITEMS = [
    ("laliga",         "LaLiga",                    "img",   "/site-logos/LaLiga/spain_la-liga--no-text_64x64.football-logos.cc.png"),
    ("premier-league", "Premier League",            "img",   "/site-logos/EPL/england_english-premier-league--no-text_64x64.football-logos.cc.png"),
    #("wsl",            "Women's Super League",       "img",   "/site-logos/WSL/FA_Women%27s_Super_League64.png"),
    #("ucl",            "Champions League",           "img",   "/site-logos/UCL/tournaments_uefa-champions-league--no-text_64x64.football-logos.cc.png"),
    #("match-analysis", "Match Analysis",             "emoji", "\U0001f4ca"),
    #("player-matchup", "Player Positional Matchup",  "emoji", "\U0001f464"),
]

_LOGO_EXPANDED  = "/site-logos/ma_logo.PNG"
_LOGO_COLLAPSED = "/site-logos/ma_logo.PNG"


def sidebar_inner_content(is_expanded=True):
    """Returns the children of #sidebar-inner (logo + nav links)."""
    if is_expanded:
        logo = html.Div(
            html.Img(
                src=_LOGO_EXPANDED,
                style={"height": "80px", "width": "auto", "objectFit": "contain"},
            ),
            style={"padding": "16px 20px", "borderBottom": f"1px solid {BORDER}",
                   "display": "flex", "alignItems": "center", "justifyContent": "center"},
        )
    else:
        logo = html.Div(
            html.Img(
                src=_LOGO_COLLAPSED,
                style={"height": "34px", "width": "auto", "objectFit": "contain"},
            ),
            style={"padding": "10px 0", "borderBottom": f"1px solid {BORDER}",
                   "display": "flex", "alignItems": "center", "justifyContent": "center"},
        )

    nav = html.Div([
        html.Button(
            [
                # Icon — image or emoji
                html.Img(src=icon_val, style={
                    "width": "20px", "height": "20px", "objectFit": "contain",
                    "minWidth": "20px", "display": "block",
                }) if icon_type == "img" else html.Span(icon_val, style={
                    "fontSize": "1rem", "minWidth": "20px", "textAlign": "center",
                    "display": "flex", "alignItems": "center", "justifyContent": "center",
                }),
                # Label — hidden when collapsed
                html.Span(label, style={
                    "fontSize":   "0.72rem", "fontWeight": "500", "marginLeft": "10px",
                    "display":    "none" if not is_expanded else "inline",
                    "whiteSpace": "nowrap",
                }),
            ],
            id={"type": "nav-btn", "page": key},
            style={
                "display":        "flex",
                "alignItems":     "center",
                "width":          "100%",
                "background":     "transparent",
                "border":         "none",
                "color":          TEXT_MAIN,
                "padding":        "12px 0" if not is_expanded else "10px 18px",
                "cursor":         "pointer",
                "textAlign":      "left",
                "borderRadius":   "0",
                "justifyContent": "center" if not is_expanded else "flex-start",
            }
        )
        for key, label, icon_type, icon_val in _NAV_ITEMS
    ], style={"padding": "12px 0"})

    return html.Div([logo, nav], style={"flex": "1", "overflow": "hidden"})
