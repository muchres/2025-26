"""
Match page.

Renders the match header card, then embeds the full match-analysis dashboard
below it.  If the per-match analysis data can't be loaded (e.g. the CSV for
this match_id isn't available yet) it falls back to the placeholder grid so the
page never errors out.
"""

from dash import html

from utils.constants import CARD_BG, BORDER, LALIGA_RED, TEXT_MUTED
from utils.data_loader import MATCH_BY_ID, team_name
from utils.epl_data_loader import EPL_MATCH_BY_ID, epl_team_name
from components.ui import card, back_button, logo_img


def _resolve_match(match_id):
    """Return (match_dict, is_epl) for the given match_id, or (None, False)."""
    m = MATCH_BY_ID.get(match_id)
    if m:
        return m, False
    m = EPL_MATCH_BY_ID.get(match_id)
    return m, True


def _match_header(m, is_epl=False):
    name_fn = epl_team_name if is_epl else team_name
    subtitle = m["date"] if is_epl else f"Matchweek {m['matchweek']} · {m['date']}"
    return card(
        html.Div([
            html.Div([
                html.Span(name_fn(m["home"]), style={
                    "fontFamily": "'Bebas Neue', sans-serif", "fontSize": "2rem", "letterSpacing": "1px",
                }),
                logo_img(m["home"], 52),
            ], style={"flex": "1", "display": "flex", "alignItems": "center",
                      "justifyContent": "flex-end", "gap": "12px"}),
            html.Div([
                html.Div(m["score"], style={
                    "fontFamily": "'Bebas Neue', sans-serif", "fontSize": "2.8rem",
                    "letterSpacing": "4px", "color": "black", "lineHeight": "1",
                }),
                html.Div(subtitle, style={
                    "textAlign": "center", "color": 'TEXT_MUTED',
                    "fontSize": "0.72rem", "marginTop": "4px",
                }),
            ], style={"textAlign": "center", "padding": "0 24px", "flexShrink": "0"}),
            html.Div([
                logo_img(m["away"], 52),
                html.Span(name_fn(m["away"]), style={
                    "fontFamily": "'Bebas Neue', sans-serif", "fontSize": "2rem", "letterSpacing": "1px",
                }),
            ], style={"flex": "1", "display": "flex", "alignItems": "center", "gap": "12px"}),
        ], style={"display": "flex", "alignItems": "center", "padding": "8px 0"}),
        style={"marginBottom": "8px"},
    )


def _placeholder_grid():
    return [
        html.Div([
            html.Div(str(row * 3 + col + 1), style={
                "background": 'CARD_BG', "border": f"2px dashed {BORDER}",
                "borderRadius": "10px", "flex": "1", "minHeight": "200px",
                "display": "flex", "alignItems": "center", "justifyContent": "center",
                "fontSize": "2rem", "fontFamily": "'Bebas Neue', sans-serif",
                "color": TEXT_MUTED, "letterSpacing": "2px",
            })
            for col in range(3)
        ], style={"display": "flex", "gap": "16px", "marginBottom": "16px"})
        for row in range(6)
    ]


def page_match(nav):
    match_id = nav.get("match")
    m, is_epl = _resolve_match(match_id)
    if not m:
        return html.Div("Match not found.", style={"color": LALIGA_RED})

    # Try to embed the real analysis dashboard; fall back to placeholders.
    try:
        from dashboards.match_analysis import build_match_analysis_layout
        body = build_match_analysis_layout(match_id=match_id)
    except Exception as exc:  # noqa: BLE001 — page must never hard-fail
        print(f"[page_match] analysis unavailable for {match_id}: {exc}")
        body = html.Div(_placeholder_grid())

    return html.Div([
        back_button("← Back to Match Selection", "matches"),
        _match_header(m, is_epl=is_epl),
        body,
    ])
