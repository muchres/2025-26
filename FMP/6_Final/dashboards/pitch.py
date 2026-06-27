"""
Pitch-drawing helpers — pure Plotly figure builders.

All functions here are stateless except for make_pitch5, which needs the two
team colours and the name lookup passed in explicitly (the original relied on
module-level globals).
"""

import math

import pandas as pd
import plotly.graph_objects as go

from utils.constants import ROW_H, formation_coords


def arc_xy(cx, cy, r, a_start_deg, a_end_deg, n=120):
    a0     = math.radians(a_start_deg)
    a1     = math.radians(a_end_deg)
    angles = [a0 + i * (a1 - a0) / n for i in range(n + 1)]
    return ([cx + r * math.cos(a) for a in angles],
            [cy + r * math.sin(a) for a in angles])


def make_pitch5(lineup_df, players_df, home_colour, away_colour, name_lookup,
                h_adj=1, w_adj=1.35, home_hext='#FFFFFF', away_hext='#FFFFFF'):
    """Starting XI pitch. Team colours + name lookup are passed in explicitly."""
    fig = go.Figure()
    PL  = 105 * w_adj
    PW  = 68  * h_adj
    def px(m): return m * w_adj
    def py(m): return m * h_adj
    lc  = "#888888"
    lw  = dict(color=lc, width=2)
    tkw = dict(mode="lines", line=lw, showlegend=False, hoverinfo="skip")
    def rect(x0, y0, x1, y1):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=lw, fillcolor="rgba(0,0,0,0)", layer="below")
    def seg(x0, y0, x1, y1):
        fig.add_shape(type="line", x0=x0, y0=y0, x1=x1, y1=y1, line=lw, layer="below")
    def arc(cx, cy, r, a0, a1):
        xs, ys = arc_xy(cx, cy, r, a0, a1)
        fig.add_trace(go.Scatter(x=xs, y=ys, **tkw))
    def dot(x, y, size=5):
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers",
                                 marker=dict(color=lc, size=size),
                                 showlegend=False, hoverinfo="skip"))
    cx_mid, cy_mid = PL / 2, PW / 2
    fig.add_shape(type="rect", x0=0, y0=0, x1=PL, y1=PW,
                  fillcolor="#4a7c3f", line=dict(width=0), layer="below")
    rect(0, 0, PL, PW)
    seg(cx_mid, 0, cx_mid, PW)
    arc(cx_mid, cy_mid, px(9.15), 0, 360)
    dot(cx_mid, cy_mid)
    rect(0,           cy_mid - py(20.16), px(16.5),    cy_mid + py(20.16))
    rect(PL-px(16.5), cy_mid - py(20.16), PL,          cy_mid + py(20.16))
    rect(0,           cy_mid - py(9.16),  px(5.5),     cy_mid + py(9.16))
    rect(PL-px(5.5),  cy_mid - py(9.16),  PL,          cy_mid + py(9.16))
    dot(px(11),    cy_mid)
    dot(PL-px(11), cy_mid)
    half_ang = math.degrees(math.acos(5.5 / 9.15))
    arc(px(11),    cy_mid, px(9.15), -half_ang,      half_ang)
    arc(PL-px(11), cy_mid, px(9.15), 180-half_ang, 180+half_ang)
    for _, row in lineup_df[lineup_df["event"] == "Team setp up"].iterrows():
        formation = str(int(float(row["formation"]))) if pd.notna(row["formation"]) else ""
        slot      = str(int(row["Team Player Formation"]))
        coords    = formation_coords.get(formation, {}).get(slot)
        if coords is None:
            continue
        xc, yc = coords
        if row["team_position"] == "home":
            xp, yp, color, hext = xc * w_adj, yc * h_adj, home_colour, home_hext
        else:
            xp, yp, color, hext = PL - xc * w_adj, PW - yc * h_adj, away_colour, away_hext
        jersey = str(int(row["Jersey Number"])) if pd.notna(row["Jersey Number"]) else ""
        fig.add_trace(go.Scatter(
            x=[xp], y=[yp], mode="markers+text",
            marker=dict(size=20, color=color, line=dict(color="white", width=1)),
            text=[jersey], textposition="middle center",
            textfont=dict(color=hext, size=10, family="Arial Bold"),
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_annotation(x=xp, y=yp - 3.8 * h_adj, text=name_lookup.get(row["player_id"], ""),
                           showarrow=False, font=dict(size=8, color="white", family="Arial"),
                           xanchor="center", yanchor="top")
    fig.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(range=[-3*w_adj, PL+3*w_adj], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[-1*h_adj, PW+5*h_adj], showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def make_pitch_v():
    fig = go.Figure()
    PW  = 68
    PL  = 105
    cx  = PW / 2
    cy  = PL / 2
    lw  = dict(color="#CCCCCC", width=2)
    def rect(x0, y0, x1, y1):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=lw, fillcolor="rgba(0,0,0,0)", layer="below")
    def arc(acx, acy, r, a0, a1):
        xs, ys = arc_xy(acx, acy, r, a0, a1)
        path = "M " + " L ".join(f"{x:.3f},{y:.3f}" for x, y in zip(xs, ys))
        fig.add_shape(type="path", path=path, line=lw, layer="below")
    def dot(x, y):
        fig.add_shape(type="circle", x0=x-1.5, y0=y-1.5, x1=x+1.5, y1=y+1.5,
                      fillcolor="#CCCCCC", line=dict(width=0), layer="below")
    rect(0, 0, PW, PL)
    fig.add_shape(type="line", x0=0, y0=cy, x1=PW, y1=cy, line=lw, layer="below")
    arc(cx, cy, 9.15, 0, 360)
    dot(cx, cy)
    rect(cx-20.16, 0,    cx+20.16, 16.5)
    rect(cx-20.16, 88.5, cx+20.16, PL)
    rect(cx-9.16,  0,    cx+9.16,  5.5)
    rect(cx-9.16,  99.5, cx+9.16,  PL)
    dot(cx, 11)
    dot(cx, 94)
    half_ang = math.degrees(math.acos(5.5 / 9.15))
    arc(cx, 11, 9.15,  90-half_ang,    90+half_ang)
    arc(cx, 94, 9.15, -(90+half_ang), -(90-half_ang))
    fig.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(range=[-5, 73], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[-12, 113], showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def make_pitch4():
    fig = go.Figure()
    lw  = dict(color="#CCCCCC", width=2)
    tkw = dict(mode="lines", line=lw, showlegend=False, hoverinfo="skip")
    def rect(x0, y0, x1, y1):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=lw, fillcolor="rgba(0,0,0,0)")
    def arc(cx, cy, r, a0, a1):
        xs, ys = arc_xy(cx, cy, r, a0, a1)
        fig.add_trace(go.Scatter(x=xs, y=ys, **tkw))
    def dot(x, y, size=5):
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers",
                                 marker=dict(color="#CCCCCC", size=size),
                                 showlegend=False, hoverinfo="skip"))
    rect(0, 0, 105, 68)
    fig.add_shape(type="line", x0=52.5, y0=0, x1=52.5, y1=68, line=lw)
    arc(52.5, 34, 9.15, 0, 360)
    dot(52.5, 34)
    rect(0,    34-20.16, 16.5,   34+20.16)
    rect(88.5, 34-20.16, 105,    34+20.16)
    rect(0,    34-9.16,  5.5,    34+9.16)
    rect(99.5, 34-9.16,  105,    34+9.16)
    rect(-0.5, 34-3.66, 0,     34+3.66)
    rect(105,  34-3.66, 105.5, 34+3.66)
    dot(11, 34)
    dot(94, 34)
    half_ang = math.degrees(math.acos(5.5 / 9.15))
    arc(11, 34, 9.15, -half_ang,      half_ang)
    arc(94, 34, 9.15, 180-half_ang, 180+half_ang)
    zl = dict(color="#CCCCCC", width=1.2, dash="dot")
    for r in range(1, 3):
        fig.add_shape(type="line", x0=0, y0=ROW_H * r, x1=105, y1=ROW_H * r, line=zl)
    fig.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(range=[-5, 110], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[-9, 72], showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def make_pitch_zones_v2():
    fig        = go.Figure()
    col_widths = [16.5, 16.5, 19.5, 19.5, 16.5, 16.5]
    col_edges  = [0]
    for w in col_widths:
        col_edges.append(col_edges[-1] + w)
    r0b, r0t = 0,        ROW_H
    r1b, r1t = ROW_H,    2 * ROW_H
    r2b, r2t = 2*ROW_H,  68
    att_x0   = col_edges[4]
    att_x1   = col_edges[6]
    att_midx = col_edges[5]
    lw_split = (r2b + r2t) / 2
    rw_split = (r0b + r0t) / 2
    def fill(x0, y0, x1, y1, color):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      fillcolor=color, line=dict(width=0))
    fill(att_x0, r1b,      att_midx, r1t,      "rgba(144,238,144,0.55)")
    fill(att_x0, r2b,      att_x1,   lw_split, "rgba(255,255,0,0.45)")
    fill(att_x0, rw_split, att_x1,   r0t,      "rgba(255,255,0,0.45)")
    lw  = dict(color="#CCCCCC", width=2)
    tkw = dict(mode="lines", line=lw, showlegend=False, hoverinfo="skip")
    def rect(x0, y0, x1, y1):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=lw, fillcolor="rgba(0,0,0,0)")
    def arc(cx, cy, r, a0, a1):
        xs, ys = arc_xy(cx, cy, r, a0, a1)
        fig.add_trace(go.Scatter(x=xs, y=ys, **tkw))
    def dot(x, y, size=5):
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers",
                                 marker=dict(color="#CCCCCC", size=size),
                                 showlegend=False, hoverinfo="skip"))
    rect(0, 0, 105, 68)
    fig.add_shape(type="line", x0=52.5, y0=0, x1=52.5, y1=68, line=lw)
    arc(52.5, 34, 9.15, 0, 360)
    dot(52.5, 34)
    rect(0,    34-20.16, 16.5,   34+20.16)
    rect(88.5, 34-20.16, 105,    34+20.16)
    rect(0,    34-9.16,  5.5,    34+9.16)
    rect(99.5, 34-9.16,  105,    34+9.16)
    rect(-0.5, 34-3.66, 0,     34+3.66)
    rect(105,  34-3.66, 105.5, 34+3.66)
    dot(11, 34)
    dot(94, 34)
    half_ang = math.degrees(math.acos(5.5 / 9.15))
    arc(11, 34, 9.15, -half_ang,      half_ang)
    arc(94, 34, 9.15, 180-half_ang, 180+half_ang)
    zl = dict(color="#CCCCCC", width=1.2, dash="dot")
    def dline(x0, y0, x1, y1):
        fig.add_shape(type="line", x0=x0, y0=y0, x1=x1, y1=y1, line=zl)
    dline(col_edges[2], 0,        col_edges[2], 68)
    dline(att_x0,       0,        att_x0,       68)
    dline(att_x0,  lw_split, att_x1,   lw_split)
    dline(att_x0,  r2b,      att_x1,   r2b)
    dline(att_x0,  r1b,      att_x1,   r1b)
    dline(att_x0,  rw_split, att_x1,   rw_split)
    dline(att_midx, r1b,     att_midx, r1t)
    def lbl(text, x, y, size=12, bold=False):
        fig.add_annotation(text=text, x=x, xref="x", y=y, yref="y", showarrow=False,
                           font=dict(size=size, color="black",
                                     family="Arial Bold" if bold else "Arial"))
    att_cx = (att_x0 + att_x1) / 2
    #lbl("Defensive Third",  (col_edges[0]+col_edges[2])/2, 34,           size=10)
    #lbl("Midfield Third",   (col_edges[2]+col_edges[4])/2, 34,           size=10)
    #lbl("Left Wide Space",  att_cx, (lw_split + r2t) / 2,                size=8)
    #lbl("Left Half Space",  att_cx, (r2b + lw_split) / 2,                size=8)
    #lbl("Zone 14",          (att_x0+att_midx)/2, (r1b+r1t)/2,            size=8)
    #lbl("Right Half Space", att_cx, (rw_split + r0t) / 2,               size=8)
    #lbl("Right Wide Space", att_cx, (r0b + rw_split) / 2,               size=8)
    lbl("Attacking Direction →", 52.5, -5,                              size=12)
    fig.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(range=[-5, 110], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[-9, 72],  showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=0, b=10),
    )
    return fig


def make_pitch_simple():
    fig = go.Figure()
    lw  = dict(color="#CCCCCC", width=2)
    tkw = dict(mode="lines", line=lw, showlegend=False, hoverinfo="skip")
    def rect(x0, y0, x1, y1):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=lw, fillcolor="rgba(0,0,0,0)", layer="below")
    def arc(cx, cy, r, a0, a1):
        xs, ys = arc_xy(cx, cy, r, a0, a1)
        fig.add_trace(go.Scatter(x=xs, y=ys, **tkw))
    def dot(x, y, size=5):
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers",
                                 marker=dict(color="#CCCCCC", size=size),
                                 showlegend=False, hoverinfo="skip"))
    rect(0, 0, 105, 68)
    fig.add_shape(type="line", x0=52.5, y0=0, x1=52.5, y1=68, line=lw)
    arc(52.5, 34, 9.15, 0, 360)
    dot(52.5, 34)
    rect(0,    34-20.16, 16.5,  34+20.16)
    rect(88.5, 34-20.16, 105,   34+20.16)
    rect(0,    34-9.16,  5.5,   34+9.16)
    rect(99.5, 34-9.16,  105,   34+9.16)
    rect(-0.5, 34-3.66,  0,     34+3.66)
    rect(105,  34-3.66,  105.5, 34+3.66)
    dot(11, 34)
    dot(94, 34)
    half_ang = math.degrees(math.acos(5.5 / 9.15))
    arc(11, 34, 9.15, -half_ang,      half_ang)
    arc(94, 34, 9.15, 180-half_ang, 180+half_ang)
    fig.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(range=[-5, 110], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[-9, 72], showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def make_pitch_30zones():
    fig = go.Figure()
    lw  = dict(color="#B0B0B0", width=1.5)
    tkw = dict(mode="lines", line=lw, showlegend=False, hoverinfo="skip")
    def rect(x0, y0, x1, y1):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=lw, fillcolor="rgba(0,0,0,0)")
    def arc(cx, cy, r, a0, a1):
        xs, ys = arc_xy(cx, cy, r, a0, a1)
        fig.add_trace(go.Scatter(x=xs, y=ys, **tkw))
    def dot(x, y, size=4):
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers",
                                 marker=dict(color="#B0B0B0", size=size),
                                 showlegend=False, hoverinfo="skip"))
    rect(0, 0, 105, 68)
    fig.add_shape(type="line", x0=52.5, y0=0, x1=52.5, y1=68, line=lw)
    arc(52.5, 34, 9.15, 0, 360)
    dot(52.5, 34)
    rect(0,    34-20.16, 16.5,   34+20.16)
    rect(88.5, 34-20.16, 105,    34+20.16)
    rect(0,    34-9.16,  5.5,    34+9.16)
    rect(99.5, 34-9.16,  105,    34+9.16)
    rect(-0.5, 34-3.66, 0,     34+3.66)
    rect(105,  34-3.66, 105.5, 34+3.66)
    dot(11, 34)
    dot(94, 34)
    half_ang = math.degrees(math.acos(5.5 / 9.15))
    arc(11, 34, 9.15, -half_ang,      half_ang)
    arc(94, 34, 9.15, 180-half_ang, 180+half_ang)
    _zl = dict(color="#CCCCCC", width=1.2, dash="dot")
    _ce = [0, 17.5, 35, 52.5, 70, 87.5, 105]
    _rh = 68 / 5
    for _x in _ce[1:-1]:
        fig.add_shape(type="line", x0=_x, y0=0, x1=_x, y1=68, line=_zl)
    for _r in range(1, 5):
        fig.add_shape(type="line", x0=0, y0=_rh * _r, x1=105, y1=_rh * _r, line=_zl)
    fig.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(range=[-5, 110], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[-9, 72], showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def make_pitch_v_bottom():
    """Vertical pitch showing the bottom 65% (y = 0 → 68.25). Open at the top."""
    fig = go.Figure()
    PW  = 68
    PL  = 105
    PH  = 68.25
    cx  = PW / 2
    cy  = PL / 2
    lw  = dict(color="#CCCCCC", width=2)
    tkw = dict(mode="lines", line=lw, showlegend=False, hoverinfo="skip")

    def line(x0, y0, x1, y1):
        fig.add_shape(type="line", x0=x0, y0=y0, x1=x1, y1=y1, line=lw, layer="below")

    def rect(x0, y0, x1, y1):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=lw, fillcolor="rgba(0,0,0,0)", layer="below")

    def arc(acx, acy, r, a0, a1):
        xs, ys = arc_xy(acx, acy, r, a0, a1)
        fig.add_trace(go.Scatter(x=xs, y=ys, **tkw))

    def dot(x, y, size=5):
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers",
                                 marker=dict(color="#CCCCCC", size=size),
                                 showlegend=False, hoverinfo="skip"))

    line(0, 0, PW, 0)
    line(0, 0, 0, PH)
    line(PW, 0, PW, PH)
    line(0, cy, PW, cy)
    arc(cx, cy, 9.15, 0, 360)
    dot(cx, cy)
    rect(cx-20.16, 0, cx+20.16, 16.5)
    rect(cx-9.16,  0, cx+9.16,  5.5)
    dot(cx, 11)
    half_ang = math.degrees(math.acos(5.5 / 9.15))
    arc(cx, 11, 9.15, 90-half_ang, 90+half_ang)

    fig.update_layout(
        plot_bgcolor="#FAF9F6", paper_bgcolor="#FAF9F6",
        xaxis=dict(range=[-5, 73], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[-5, PH+5], showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def get_zone(px, py):
    if pd.isna(px) or pd.isna(py):
        return float("nan")
    col_idx = min(max(int(px / 17.5), 0), 5)
    row_idx = min(max(int((68 - py) / (68 / 5)), 0), 4)
    return col_idx * 5 + row_idx + 1


def make_pitch_v_top():
    """Vertical pitch showing the attacking half only (y = 52.5 → 105). Open at bottom."""
    fig = go.Figure()
    PW  = 68
    PL  = 105
    PH  = PL / 2   # 52.5 — halfway line
    cx  = PW / 2
    lw  = dict(color="#CCCCCC", width=2)
    tkw = dict(mode="lines", line=lw, showlegend=False, hoverinfo="skip")

    def line(x0, y0, x1, y1):
        fig.add_shape(type="line", x0=x0, y0=y0, x1=x1, y1=y1, line=lw, layer="below")

    def rect(x0, y0, x1, y1):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=lw, fillcolor="rgba(0,0,0,0)", layer="below")

    def arc(acx, acy, r, a0, a1):
        xs, ys = arc_xy(acx, acy, r, a0, a1)
        fig.add_trace(go.Scatter(x=xs, y=ys, **tkw))

    def dot(x, y, size=5):
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers",
                                 marker=dict(color="#CCCCCC", size=size),
                                 showlegend=False, hoverinfo="skip"))

    line(0, PL, PW, PL)      # top goal line
    line(0, PH, 0,  PL)      # left touchline
    line(PW, PH, PW, PL)     # right touchline
    line(0, PH, PW, PH)      # halfway line
    arc(cx, PH, 9.15, 0, 180)
    dot(cx, PH)
    rect(cx-20.16, 88.5, cx+20.16, PL)
    rect(cx-9.16,  99.5, cx+9.16,  PL)
    dot(cx, 94)
    half_ang = math.degrees(math.acos(5.5 / 9.15))
    arc(cx, 94, 9.15, -(90+half_ang), -(90-half_ang))

    fig.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(range=[-2, 70], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[PH-5, PL+5], showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def make_pitch_v_top_zones():
    """Vertical attacking-half pitch with orange highlight zones (wide + half-spaces)."""
    fig = go.Figure()
    PW  = 68
    PL  = 105
    PH  = PL / 2   # 52.5
    cx  = PW / 2   # 34
    lw  = dict(color="#CCCCCC", width=2)
    tkw = dict(mode="lines", line=lw, showlegend=False, hoverinfo="skip")

    def line(x0, y0, x1, y1):
        fig.add_shape(type="line", x0=x0, y0=y0, x1=x1, y1=y1, line=lw, layer="below")

    def rect(x0, y0, x1, y1):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=lw, fillcolor="rgba(0,0,0,0)", layer="below")

    def zone(x0, y0, x1, y1, color="rgba(255,165,0,0.2)"):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      line=dict(width=0), fillcolor=color, layer="below")

    def arc(acx, acy, r, a0, a1):
        xs, ys = arc_xy(acx, acy, r, a0, a1)
        fig.add_trace(go.Scatter(x=xs, y=ys, **tkw))

    def dot(x, y, size=5):
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers",
                                 marker=dict(color="#CCCCCC", size=size),
                                 showlegend=False, hoverinfo="skip"))

    zone(0,          PH,   68/6,     PL)                                     # left wide
    zone(68/6,       70,   68/3,     PL, "rgba(0,255,255,0.2)")              # left half-space
    zone(68-68/3,    70,   68-68/6,  PL, "rgba(0,255,255,0.2)")              # right half-space
    zone(68-68/6,    PH,   PW,       PL)                                     # right wide

    line(0, PL, PW, PL)
    line(0, PH, 0,  PL)
    line(PW, PH, PW, PL)
    line(0, PH, PW, PH)
    arc(cx, PH, 9.15, 0, 180)
    dot(cx, PH)
    rect(cx-20.16, 88.5, cx+20.16, PL)
    rect(cx-9.16,  99.5, cx+9.16,  PL)
    dot(cx, 94)
    half_ang = math.degrees(math.acos(5.5 / 9.15))
    arc(cx, 94, 9.15, -(90+half_ang), -(90-half_ang))

    fig.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(range=[-2, 70], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="y", scaleratio=1),
        yaxis=dict(range=[PH-2, PL+2], showgrid=False, zeroline=False, visible=False),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig
