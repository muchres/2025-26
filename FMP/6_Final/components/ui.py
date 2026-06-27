"""Reusable UI building blocks (cards, headers, tabs, buttons, logos)."""

from dash import html

from utils.constants import (
    LALIGA_RED, CARD_BG, BORDER, TEXT_MAIN, TEXT_MUTED,
)
from utils.data_loader import TEAM_DATA


def card(children, style=None):
    base = {"background": CARD_BG, "border": f"1px solid {BORDER}",
            "borderRadius": "5px", "padding": "10px"}
    if style:
        base.update(style)
    return html.Div(children, style=base)


def page_header(title, subtitle=None):
    els = [html.H1(title, style={
        "fontFamily": "'Bebas Neue', sans-serif", "fontSize": "2.2rem",
        "letterSpacing": "2px", "margin": "0 0 4px 0", "color": TEXT_MAIN,
    })]
    if subtitle:
        els.append(html.P(subtitle, style={
            "color": TEXT_MUTED, "margin": "0", "fontSize": "0.85rem"}))
    return html.Div(els, style={"marginBottom": "24px"})


def tab_bar(tabs, active, id_type):
    """Renders a row of tab buttons; active tab uses LALIGA_RED fill."""
    return html.Div([
        html.Button(
            t,
            id={"type": id_type, "tab": t},
            style={
                "background":    LALIGA_RED if t == active else "transparent",
                "border":        f"1px solid {LALIGA_RED if t == active else BORDER}",
                "color":         "#fff" if t == active else TEXT_MAIN,
                "padding":       "6px 16px",
                "borderRadius":  "6px",
                "cursor":        "pointer",
                "fontSize":      "0.82rem",
                "fontWeight":    "500",
                "letterSpacing": "0.5px",
                "transition":    "all 0.2s",
                "whiteSpace":    "nowrap",
            }
        )
        for t in tabs
    ], style={"display": "flex", "gap": "8px", "marginBottom": "16px", "flexWrap": "wrap"})


def dashed_box(content=None, min_height="200px"):
    """Reusable dashed placeholder box."""
    return html.Div(content or "Coming Soon", style={
        "background":     CARD_BG,
        "border":         f"2px dashed {BORDER}",
        "borderRadius":   "10px",
        "flex":           "1",
        "minHeight":      min_height,
        "display":        "flex",
        "alignItems":     "center",
        "justifyContent": "center",
        "fontSize":       "1rem",
        "fontFamily":     "'DM Sans', sans-serif",
        "color":          TEXT_MUTED,
        "fontWeight":     "500",
    })


def placeholder_page(title, subtitle=None):
    return html.Div([page_header(title.upper(), subtitle), dashed_box()])


def logo_img(code, size=20):
    td = TEAM_DATA.get(code)
    if td:
        src = f"/logos/{td['logo']}"
    else:
        from utils.epl_data_loader import EPL_TEAM_DATA
        td = EPL_TEAM_DATA.get(code)
        if not td:
            return html.Span(style={
                "width": f"{size}px", "display": "inline-block", "flexShrink": "0"})
        src = td["logo_src"]
    return html.Img(src=src, style={
        "width": f"{size}px", "height": f"{size}px",
        "objectFit": "contain", "verticalAlign": "middle", "flexShrink": "0",
    })


def back_button(label, action):
    """
    Back button with pattern-matched ID.
    `action` is the key used in cb_back_nav to decide where to go.
    id = {"type": "back-btn", "action": action}
    """
    return html.Button(label, id={"type": "back-btn", "action": action}, style={
        "background":   "transparent",
        "border":       f"1px solid {BORDER}",
        "color":        TEXT_MUTED,
        "padding":      "5px 12px",
        "borderRadius": "6px",
        "cursor":       "pointer",
        "fontSize":     "0.78rem",
        "marginBottom": "10px",
        "display":      "inline-block",
    })
