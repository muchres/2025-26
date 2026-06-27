"""
Set Piece Analysis dashboard — "Set Piece Analysis" tab in the team page.

Data source: 2_Data/all_sp_laliga.csv (pre-computed across all LaLiga matches).
Coordinates in the CSV are 0-100 in the team's own reference frame:
  x=0 = own goal end, x=100 = opponent's goal end.
All figures use the vertical pitch (68x105), attacking end at top:
  vx = 68 - (y/100 * 68),  vy = x/100 * 105
"""

import os
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html, dash_table

from utils.constants import (
    BG_COLOUR, CARD_BG, BORDER, SECONDARY_COL, TEXT_MUTED,
    LALIGA_RED,
)
from utils.data_loader import MATCHES_DESC, TEAM_DATA
from utils.lineup_data import DISP_NAME, JERSEY_NUM, SHORT_NAME
from dashboards.pitch import make_pitch_v_top
from dashboards.match_analysis import (
    make_section_label, TABLE_STYLE_HEADER, TABLE_STYLE_CELL, TABLE_STYLE_DATA,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
_HERE   = os.path.dirname(os.path.abspath(__file__))
_APP    = os.path.dirname(_HERE)
_SP_CSV = os.path.join(os.path.dirname(_APP), "2_Data", "all_sp_laliga.csv")

# ── Set-piece thresholds (0-100 scale matching extraction script) ─────────────
FK_X_MIN = 88.5 / 105 * 100      # ≈ 84.29
FK_Y_MIN = (34 - 20.16) / 68 * 100   # ≈ 20.35
FK_Y_MAX = (34 + 20.16) / 68 * 100   # ≈ 79.65

_SHOT_EV = {"Goal", "Miss", "Saved Shot", "Post"}

# Vertical-pitch penalty box boundaries
_BOX_X0 = 34 - 20.16   # 13.84
_BOX_X1 = 34 + 20.16   # 54.16

# Marker colours
_C_FAIL   = "rgba(160,160,160,0.85)"
_C_CORNER = "#E74C3C"
_C_FK     = "#27AE60"
_C_THROW  = "#2980B9"
_C_GOLD   = "#F1C40F"

# Zone fills (vx ranges for cyan/green/orange highlights)
_ZONE_FILLS = [
    (_BOX_X0, 28.5,   88.5, 105.0, "rgba(0,210,210,0.15)"),
    (39.5,    _BOX_X1, 88.5, 105.0, "rgba(0,210,210,0.15)"),
    (28.5,    39.5,    88.5,  99.5, "rgba(46,204,113,0.22)"),
    (28.5,    39.5,    99.5, 105.0, "rgba(230,126,34,0.28)"),
]

_TABLE_ROW_H = 16

# ── Row heights & pitch fraction — adjust these to resize rows/graphs ─────────
_R1_H = 310   # Left Side Corners
_R2_H = 310   # Right Side Corners
_R3_H = 340   # Other Corner Sequences
_R4_H = 360   # Free Kicks into Box
_R5_H = 340   # Other FK Sequences
_R6_H = 530   # Direct FK & Penalties (includes goalpost panels)
_R0_H = 310   # Set Piece Radar + Breakdown
_R7_H = 360   # Long Throw-ins

# ── Goalpost visualisation constants (metres) ─────────────────────────────────
_GOAL_W  = 7.32    # goal width in metres
_GOAL_H  = 2.44    # goal height in metres
_GY_MIN  = 44.62   # pitch-y (0-100) at one post:  (68-37.66)/68*100
_GY_MAX  = 55.38   # pitch-y (0-100) at other post: (68-30.34)/68*100
_GZ_MAX  = 38.0    # data scale for Goal Mouth Z Coordinate (38 = crossbar)
_R6_GP_H = 165     # goalpost panel height in pixels
_PITCH_H_FRAC = 0.90  # pitch graph height as fraction of row height

# ── Data loading ──────────────────────────────────────────────────────────────
_SP_DF: Optional[pd.DataFrame] = None

# match_id + team_code → opponent team code
_MATCH_OPP: dict = {
    k: v
    for m in MATCHES_DESC
    for k, v in [((m["id"], m["home"]), m["away"]),
                 ((m["id"], m["away"]), m["home"])]
}


def _load_sp() -> pd.DataFrame:
    global _SP_DF
    if _SP_DF is None:
        try:
            _SP_DF = pd.read_csv(_SP_CSV, low_memory=False)
        except FileNotFoundError:
            _SP_DF = pd.DataFrame()
    return _SP_DF


def _team_df(code: str) -> pd.DataFrame:
    df = _load_sp()
    if df.empty:
        return df
    df = df[df["team_code"] == code].copy()
    if "event" in df.columns:
        df = df[df["event"] != "Deleted event"]
    return df


# ── Coordinate + name helpers ─────────────────────────────────────────────────
def _tv(x100, y100):
    return 68 - (y100 / 100 * 68), x100 / 100 * 105


def _abbrev(pid) -> str:
    nm = DISP_NAME.get(str(pid), str(pid))
    if not nm or (isinstance(nm, float) and np.isnan(nm)):
        return str(pid)
    parts = str(nm).split()
    return nm if len(parts) <= 1 else f"{parts[0][0]}. {parts[-1]}"


def _shooter_label(pid) -> str:
    """Return '#8 P.Fornals' format for dropdown buttons."""
    num = JERSEY_NUM.get(str(pid), "")
    nm  = _abbrev(pid)
    return f"#{num} {nm}" if num else nm


# ── Pitch builders ────────────────────────────────────────────────────────────
def _make_top_pitch(y_min: float = 73.5) -> go.Figure:
    fig = make_pitch_v_top()
    fig.update_layout(
        plot_bgcolor=CARD_BG, paper_bgcolor=CARD_BG,
        yaxis=dict(range=[y_min, 108]),
        xaxis=dict(range=[0, 68]),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def _make_half_pitch() -> go.Figure:
    fig = make_pitch_v_top()
    fig.update_layout(
        plot_bgcolor=CARD_BG, paper_bgcolor=CARD_BG,
        yaxis=dict(range=[49, 108]),
        xaxis=dict(range=[0, 68]),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def _add_box_zones(fig: go.Figure):
    for x0, x1, y0, y1, fc in _ZONE_FILLS:
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      fillcolor=fc, line=dict(width=0), layer="below")


def _add_goalpost(fig: go.Figure):
    fig.add_shape(type="rect", x0=34 - 3.66, y0=105.0, x1=34 + 3.66, y1=105.5,
                  line=dict(color="#888888", width=1.5),
                  fillcolor="rgba(0,0,0,0)", layer="above")


def _shot_arrow(fig: go.Figure, sx, sy, gmy, color: str = "#E74C3C"):
    vx_s, vy_s = _tv(sx, sy)
    vx_g = (68 - (gmy / 100 * 68)) if (not pd.isna(gmy) and gmy == gmy) else 34.0
    fig.add_annotation(
        x=vx_g, y=105.5, ax=vx_s, ay=vy_s,
        xref="x", yref="y", axref="x", ayref="y",
        showarrow=True, arrowhead=2, arrowsize=0.9,
        arrowwidth=1.5, arrowcolor=color, text="",
    )


# ── Layout helpers ────────────────────────────────────────────────────────────
def _graph(fig: go.Figure, height_px: int) -> dcc.Graph:
    return dcc.Graph(figure=fig, config={"displayModeBar": False},
                     style={"height": f"{height_px}px"})


def _cap(text: str) -> html.Div:
    return html.Div(text, style={
        "fontSize": "0.66rem", "fontWeight": "600", "color": SECONDARY_COL,
        "textAlign": "center", "padding": "2px 0", "flexShrink": "0",
    })


def _sortable(df: Optional[pd.DataFrame], sort_col, height_px: int,
              ascending: bool = False) -> html.Div:
    if df is None or df.empty:
        return html.Div("No data", style={
            "color": TEXT_MUTED, "fontSize": "10px", "padding": "4px"})
    _cols = sort_col if isinstance(sort_col, list) else [sort_col]
    _asc  = ascending if isinstance(ascending, list) else [ascending] * len(_cols)
    df    = df.sort_values(_cols, ascending=_asc).reset_index(drop=True)
    if "#" in df.columns:
        df["#"] = range(1, len(df) + 1)
    return dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        sort_action="native",
        sort_by=[{"column_id": _cols[0], "direction": "asc" if _asc[0] else "desc"}],
        style_table={"height": f"{height_px}px", "overflowY": "auto", "overflowX": "auto"},
        style_header={**TABLE_STYLE_HEADER, "fontSize": "11px", "padding": "1px 4px"},
        style_cell={**TABLE_STYLE_CELL, "fontSize": "11px", "padding": "1px 4px",
                    "height": f"{_TABLE_ROW_H}px",
                    "lineHeight": f"{_TABLE_ROW_H - 2}px"},
        style_data={**TABLE_STYLE_DATA, "height": f"{_TABLE_ROW_H}px"},
        page_action="none",
    )


def _two_col(col1, col2, height_px: int) -> html.Div:
    return html.Div([
        html.Div(col1, style={
            "width": "60%", "flexShrink": "0", "minWidth": "0",
            "boxSizing": "border-box",
        }),
        html.Div(col2, style={
            "width": "40%", "flexShrink": "0", "minWidth": "0",
            "boxSizing": "border-box",
            "display": "flex", "flexDirection": "column", "overflow": "hidden",
        }),
    ], style={"display": "flex", "height": f"{height_px}px"})


def _row_wrap(label: str, children) -> html.Div:
    return html.Div([make_section_label(label), children],
                    style={"marginBottom": "6px"})


# ══════════════════════════════════════════════════════════════════════════════
# Corner sequence summarisation
# ══════════════════════════════════════════════════════════════════════════════

def _summarise_corners(df_team: pd.DataFrame) -> pd.DataFrame:
    df_c = df_team[df_team["sp_type"] == "corner"].copy()
    if df_c.empty:
        return pd.DataFrame()

    records = []
    for (match_id, seq_id), grp in df_c.groupby(["match_id", "corner_seq_id"], dropna=True):
        grp = grp.reset_index(drop=True)
        pm  = grp["Corner taken"] == "Si"
        if not pm.any():
            continue

        pr     = grp[pm].iloc[0]
        pr_idx = int(grp[pm].index[0])

        px_end = pr.get("Pass End X", np.nan)
        py_end = pr.get("Pass End Y", np.nan)
        in_box = (
            not pd.isna(px_end) and not pd.isna(py_end)
            and float(px_end) > FK_X_MIN
            and FK_Y_MIN <= float(py_end) <= FK_Y_MAX
        )

        vx_end = vy_end = np.nan
        if not (pd.isna(px_end) or pd.isna(py_end)):
            vx_end, vy_end = _tv(float(px_end), float(py_end))

        taker_vx, taker_vy = np.nan, np.nan
        try:
            taker_vx, taker_vy = _tv(float(pr["x"]), float(pr["y"]))
        except (TypeError, ValueError):
            pass

        y_val = pr.get("y", np.nan)
        side  = "left" if (not pd.isna(y_val) and float(y_val) > 50) else "right"
        p_out = int(pr["outcome"]) if not pd.isna(pr["outcome"]) else 0

        own_team  = str(grp.iloc[0]["team_code"])
        shot_rows = grp[(grp["event"].isin(_SHOT_EV)) & (grp["team_code"] == own_team)]
        has_goal  = not grp[(grp["event"] == "Goal") & (grp["team_code"] == own_team)].empty
        has_shot  = not shot_rows.empty
        otype     = "goal" if has_goal else ("shot" if has_shot else "no_shot")

        if p_out == 0:
            marker = "grey_x"
        elif otype == "goal":
            marker = "gold_circle"
        elif otype == "shot":
            marker = "red_triangle"
        else:
            marker = "hollow_triangle"

        shot_x = shot_y = gmy = np.nan
        if has_shot:
            sr     = shot_rows.iloc[-1]
            shot_x = sr["x"]; shot_y = sr["y"]
            gmy    = sr.get("Goal Mouth Y Coordinate", np.nan)

        after    = grp[(grp.index > pr_idx) & (grp["team_code"] == own_team)]
        recv_pid = after.iloc[0]["player_id"] if not after.empty else np.nan

        shot_head = shot_feet = False
        if has_shot:
            sr        = shot_rows.iloc[-1]
            shot_head = sr.get("Head", np.nan) == "Si"
            shot_feet = not shot_head

        records.append({
            "match_id": match_id, "seq_id": seq_id, "side": side, "in_box": in_box,
            "taker_pid": pr["player_id"],
            "taker_vx": taker_vx, "taker_vy": taker_vy,
            "inswing":  pr.get("Inswinger", np.nan) == "Si",
            "outswing": pr.get("Outswinger", np.nan) == "Si",
            "p_out": p_out, "vx_end": vx_end, "vy_end": vy_end,
            "marker": marker, "otype": otype,
            "shot_x": shot_x, "shot_y": shot_y, "gmy": gmy,
            "recv_pid": recv_pid,
            "shot_head": shot_head, "shot_feet": shot_feet,
        })

    return pd.DataFrame(records)


# ══════════════════════════════════════════════════════════════════════════════
# Rows 1 & 2 — Corner deliveries into box (left / right)
# ══════════════════════════════════════════════════════════════════════════════

def _fig_corners_box(seq_sum: pd.DataFrame, side: str, df_team: pd.DataFrame) -> go.Figure:
    fig = _make_top_pitch(y_min=78.5)
    _add_box_zones(fig)
    _add_goalpost(fig)

    sub = seq_sum[(seq_sum["in_box"]) & (seq_sum["side"] == side)] if not seq_sum.empty else pd.DataFrame()
    if sub.empty:
        fig.add_annotation(x=34, y=90, text="No data", showarrow=False,
                           font=dict(size=11, color=TEXT_MUTED), xanchor="center")
        return fig

    # Delivery arrows: all successful deliveries at opacity 0.1
    has_taker = "taker_vx" in sub.columns
    if has_taker:
        suc_arr = sub[(sub["p_out"] == 1) & sub["taker_vx"].notna() & sub["vx_end"].notna()]
        for _, r in suc_arr.iterrows():
            fig.add_annotation(
                x=r["vx_end"], y=r["vy_end"], ax=r["taker_vx"], ay=r["taker_vy"],
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=2, arrowsize=0.7, arrowwidth=1.0,
                arrowcolor="rgba(231,76,60,0.1)", text="",
            )

    # Non-goal markers at reduced opacity so goal sequences stand out
    non_goal = sub[sub["otype"] != "goal"]
    gx = non_goal[non_goal["marker"] == "grey_x"]
    ht = non_goal[non_goal["marker"] == "hollow_triangle"]
    rt = non_goal[non_goal["marker"] == "red_triangle"]

    if not gx.empty:
        fig.add_trace(go.Scatter(
            x=gx["vx_end"].tolist(), y=gx["vy_end"].tolist(), mode="markers",
            marker=dict(size=7, color="rgba(160,160,160,0.4)", symbol="x"),
            showlegend=False, hoverinfo="skip"))
    if not ht.empty:
        fig.add_trace(go.Scatter(
            x=ht["vx_end"].tolist(), y=ht["vy_end"].tolist(), mode="markers",
            marker=dict(size=8, color="rgba(255,255,255,0.4)", symbol="triangle-up",
                        line=dict(color="rgba(231,76,60,0.4)", width=1.5)),
            showlegend=False, hoverinfo="skip"))
    if not rt.empty:
        fig.add_trace(go.Scatter(
            x=rt["vx_end"].tolist(), y=rt["vy_end"].tolist(), mode="markers",
            marker=dict(size=9, color="rgba(231,76,60,0.4)", symbol="triangle-up"),
            showlegend=False, hoverinfo="skip"))

    # Goal sequences: full path black dotted, shot black circle, arrow black solid
    df_c = df_team[df_team["sp_type"] == "corner"]
    for _, row in sub[sub["otype"] == "goal"].iterrows():
        grp = df_c[
            (df_c["match_id"] == row["match_id"]) &
            (df_c["corner_seq_id"] == row["seq_id"])
        ].copy()
        if not grp.empty:
            _draw_goal_seq(fig, grp, str(grp.iloc[0]["team_code"]),
                           row["shot_x"], row["shot_y"], row["gmy"])

    # Zone stats + delivery method (left corner: top-left; right corner: top-right)
    fp, syb, ps, farp = _zone_counts(sub, side)
    ins   = int(sub["inswing"].sum())
    outs  = int(sub["outswing"].sum())
    zone_txt = (f"<b>Delivery Zones</b><br>"
                f"Front Post: {fp}<br>6-Yard Box: {syb}<br>"
                f"Pen. Spot:  {ps}<br>Far Post:   {farp}<br>"
                f"<b>Delivery Method</b><br>"
                f"Inswing: {ins}<br>Outswing: {outs}")
    if side == "left":
        fig.add_annotation(x=2, y=98, text=zone_txt,
                           showarrow=False, xanchor="left", yanchor="top",
                           align="left", font=dict(size=9, color=SECONDARY_COL),
                           bgcolor=CARD_BG, borderwidth=0)
    else:
        fig.add_annotation(x=66, y=98, text=zone_txt,
                           showarrow=False, xanchor="right", yanchor="top",
                           align="right", font=dict(size=9, color=SECONDARY_COL),
                           bgcolor=CARD_BG, borderwidth=0)

    n     = len(sub)
    suc   = int((sub["p_out"] == 1).sum())
    goals = int((sub["otype"] == "goal").sum())
    shots = int(sub["otype"].isin(["goal", "shot"]).sum())
    label = "Left" if side == "left" else "Right"
    fig.add_annotation(
        x=34, y=84,
        text=(f"<b>{label} Corners into Box</b><br>"
              f"Total: {n}  Received: {suc}  Attempts: {shots}  Goals: {goals}"),
        showarrow=False, xanchor="center", yanchor="top",
        align="center", font=dict(size=9, color=SECONDARY_COL),
    )
    _add_sp_legend(fig, y=80.5, c_mk=_C_CORNER)
    return fig


def _tbl_corner_takers(seq_sum: pd.DataFrame, side: str) -> pd.DataFrame:
    sub = seq_sum[(seq_sum["in_box"]) & (seq_sum["side"] == side)] if not seq_sum.empty else pd.DataFrame()
    if sub.empty:
        return pd.DataFrame()
    g = sub.groupby("taker_pid").agg(
        Taken=("p_out", "count"),
        Suc=("p_out", "sum"),
        Inswing=("inswing", "sum"),
        Outswing=("outswing", "sum"),
    ).reset_index()
    g["Suc%"]   = (g["Suc"] / g["Taken"].replace(0, np.nan) * 100).round(0).fillna(0).astype(int).astype(str) + "%"
    g["Inswing"]  = g["Inswing"].astype(int)
    g["Outswing"] = g["Outswing"].astype(int)
    g["Player"]   = g["taker_pid"].map(_abbrev)
    g.insert(0, "#", range(1, len(g) + 1))
    return g[["#", "Player", "Taken", "Suc", "Suc%", "Inswing", "Outswing"]]


def _tbl_corner_receivers(seq_sum: pd.DataFrame, df_team: pd.DataFrame, side: str) -> pd.DataFrame:
    sub = seq_sum[(seq_sum["in_box"]) & (seq_sum["side"] == side)] if not seq_sum.empty else pd.DataFrame()
    if sub.empty:
        return pd.DataFrame()

    recv = (sub[sub["recv_pid"].notna()]
            .groupby("recv_pid").size().rename("Received")
            .reset_index().rename(columns={"recv_pid": "pid"}))

    df_c      = df_team[df_team["sp_type"] == "corner"]
    sub_pairs = sub[["match_id", "seq_id"]].rename(columns={"seq_id": "corner_seq_id"})
    shots     = df_c[df_c["event"].isin(_SHOT_EV)].merge(sub_pairs, on=["match_id", "corner_seq_id"])

    if shots.empty:
        for c in ["Att Hdr", "Att Feet", "Goal Hdr", "Goal Feet"]:
            recv[c] = 0
    else:
        shots["is_head"]      = (shots["Head"] == "Si")
        shots["is_goal"]      = (shots["event"] == "Goal")
        shots["is_goal_head"] = shots["is_goal"] & shots["is_head"]
        shots["is_goal_feet"] = shots["is_goal"] & ~shots["is_head"]
        sa = shots.groupby("player_id").agg(
            att_hdr=("is_head",      "sum"),
            att_feet=("is_head",     lambda x: int((~x.astype(bool)).sum())),
            goal_hdr=("is_goal_head", "sum"),
            goal_feet=("is_goal_feet", "sum"),
        ).reset_index().rename(columns={"player_id": "pid"})
        recv = recv.merge(sa, on="pid", how="left").fillna(0)
        recv = recv.rename(columns={
            "att_hdr": "Att Hdr", "att_feet": "Att Feet",
            "goal_hdr": "Goal Hdr", "goal_feet": "Goal Feet",
        })
        for c in ["Att Hdr", "Att Feet", "Goal Hdr", "Goal Feet"]:
            recv[c] = recv[c].astype(int)

    recv["Player"] = recv["pid"].map(_abbrev)
    recv.insert(0, "#", range(1, len(recv) + 1))
    cols = ["#", "Player", "Received", "Att Hdr", "Att Feet", "Goal Hdr", "Goal Feet"]
    return recv[[c for c in cols if c in recv.columns]]


# ── Zone counting (delivery endpoints) ───────────────────────────────────────
def _zone_counts(sub: pd.DataFrame, side: str):
    """Count delivery endpoints in each zone. side='left'/'right' determines near/far post."""
    v = sub.dropna(subset=["vx_end", "vy_end"])
    if v.empty:
        return 0, 0, 0, 0
    if side == "left":
        front = (v["vx_end"] < 28.5)  & (v["vy_end"] > 88.5)
        farpo = (v["vx_end"] >= 39.5) & (v["vy_end"] > 88.5)
    else:
        front = (v["vx_end"] >= 39.5) & (v["vy_end"] > 88.5)
        farpo = (v["vx_end"] < 28.5)  & (v["vy_end"] > 88.5)
    six_y = (v["vx_end"] >= 28.5) & (v["vx_end"] < 39.5) & (v["vy_end"] > 99.5)
    pen   = (v["vx_end"] >= 28.5) & (v["vx_end"] < 39.5) & \
            (v["vy_end"] > 88.5)  & (v["vy_end"] <= 99.5)
    return int(front.sum()), int(six_y.sum()), int(pen.sum()), int(farpo.sum())


# ── Goal-sequence overlay ─────────────────────────────────────────────────────
def _draw_goal_seq(fig: go.Figure, grp: pd.DataFrame, own_team: str,
                   shot_x, shot_y, gmy):
    """Draw full own-team sequence as black dotted line, shot as black circle, arrow black solid."""
    # Exclude "Corner Awarded" — its x,y is the deflection point, not the corner flag,
    # which creates a spurious segment back to the corner before the actual delivery.
    own_ev = grp[
        (grp["team_code"] == own_team) & (grp["event"] != "Corner Awarded")
    ].reset_index(drop=True)
    if len(own_ev) >= 2:
        xs, ys = [], []
        for _, r in own_ev.iterrows():
            try:
                vx, vy = _tv(float(r["x"]), float(r["y"]))
                xs.append(vx); ys.append(vy)
            except (TypeError, ValueError):
                pass
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
                                     line=dict(color="black", width=1.5, dash="dot"),
                                     showlegend=False, hoverinfo="skip"))
    if not (pd.isna(shot_x) or pd.isna(shot_y)):
        vx_s, vy_s = _tv(float(shot_x), float(shot_y))
        fig.add_trace(go.Scatter(x=[vx_s], y=[vy_s], mode="markers",
                                 marker=dict(size=10, color="black", symbol="circle"),
                                 showlegend=False, hoverinfo="skip"))
        _shot_arrow(fig, float(shot_x), float(shot_y), gmy, color="black")


# ── Standard set-piece legend ─────────────────────────────────────────────────
def _add_sp_legend(fig: go.Figure, y: float, c_mk: str,
                   att_sym: str = "▲", goal_col: str = "black"):
    for lx, txt, col in [
        (4,  "✕ Unsuccessful", _C_FAIL),
        (19, "△ Delivered",    c_mk),
        (36, f"{att_sym} Attempts", c_mk),
        (52, "● Goals",        goal_col),
    ]:
        fig.add_annotation(x=lx, y=y, text=txt, showarrow=False,
                           xanchor="left", yanchor="top",
                           font=dict(size=10, color=col))


# ── Next-action buckets for rows 3 & 5 ───────────────────────────────────────
def _bucket_next_action(event: str, row) -> str:
    if event in _SHOT_EV:
        return "Shot"
    if event == "Pass":
        nex = row.get("Pass End X", np.nan)
        ney = row.get("Pass End Y", np.nan)
        try:
            if not (pd.isna(nex) or pd.isna(ney)):
                if float(nex) > FK_X_MIN and FK_Y_MIN <= float(ney) <= FK_Y_MAX:
                    return "Cross into Box"
        except (TypeError, ValueError):
            pass
        return "Another Pass outside Box"
    return "Other"


# ══════════════════════════════════════════════════════════════════════════════
# Row 3 — Other corner sequences (short / not into box)
# ══════════════════════════════════════════════════════════════════════════════

def _fig_other_corners(df_team: pd.DataFrame, seq_sum: pd.DataFrame) -> go.Figure:
    fig = _make_half_pitch()
    _add_goalpost(fig)

    other = seq_sum[~seq_sum["in_box"]] if not seq_sum.empty else pd.DataFrame()
    df_c  = df_team[df_team["sp_type"] == "corner"]

    if other.empty or df_c.empty:
        fig.add_annotation(x=34, y=75, text="No data", showarrow=False,
                           font=dict(size=11, color=TEXT_MUTED), xanchor="center")
        return fig

    own_team    = str(df_c["team_code"].iloc[0])
    other_pairs = other[["match_id", "seq_id"]].rename(columns={"seq_id": "corner_seq_id"})
    relevant    = df_c.merge(other_pairs, on=["match_id", "corner_seq_id"])

    # Endpoint markers at 0.3 opacity (non-goal only)
    non_goal = other[other["otype"] != "goal"]
    gx = non_goal[non_goal["p_out"] == 0]
    ht = non_goal[non_goal["p_out"] == 1]
    if not gx.empty:
        fig.add_trace(go.Scatter(
            x=gx["vx_end"].tolist(), y=gx["vy_end"].tolist(), mode="markers",
            marker=dict(size=6, color="rgba(160,160,160,0.3)", symbol="x"),
            showlegend=False, hoverinfo="skip"))
    if not ht.empty:
        fig.add_trace(go.Scatter(
            x=ht["vx_end"].tolist(), y=ht["vy_end"].tolist(), mode="markers",
            marker=dict(size=7, color="rgba(255,255,255,0.3)", symbol="triangle-up",
                        line=dict(color="rgba(231,76,60,0.3)", width=1.5)),
            showlegend=False, hoverinfo="skip"))

    # Purple cross arrows for next pass into box (corner outcome=1 only)
    for (_, __), grp in relevant.groupby(["match_id", "corner_seq_id"], dropna=True):
        grp = grp.reset_index(drop=True)
        pm  = grp["Corner taken"] == "Si"
        if not pm.any():
            continue
        pr    = grp[pm].iloc[0]
        p_out = int(pr["outcome"]) if not pd.isna(pr.get("outcome", np.nan)) else 0
        if p_out != 1:
            continue
        pi    = int(grp[pm].index[0])
        after = grp[(grp.index > pi) & (grp["team_code"] == own_team)]
        if after.empty:
            continue
        nr = after.iloc[0]
        if nr["event"] == "Pass":
            nex = nr.get("Pass End X", np.nan)
            ney = nr.get("Pass End Y", np.nan)
            if not (pd.isna(nex) or pd.isna(ney)):
                if float(nex) > FK_X_MIN and FK_Y_MIN <= float(ney) <= FK_Y_MAX:
                    vx0, vy0 = _tv(float(nr["x"]), float(nr["y"]))
                    vx1, vy1 = _tv(float(nex), float(ney))
                    fig.add_annotation(
                        x=vx1, y=vy1, ax=vx0, ay=vy0,
                        xref="x", yref="y", axref="x", ayref="y",
                        showarrow=True, arrowhead=2, arrowsize=0.9,
                        arrowwidth=1.5, arrowcolor="rgba(142,68,173,0.5)", text="",
                    )

    # Non-goal shot circles at 0.3 opacity + red shot arrow
    for _, r in non_goal[non_goal["otype"] == "shot"].iterrows():
        if not pd.isna(r.get("shot_x")):
            vx_s, vy_s = _tv(float(r["shot_x"]), float(r["shot_y"]))
            fig.add_trace(go.Scatter(x=[vx_s], y=[vy_s], mode="markers",
                                     marker=dict(size=9, color="rgba(231,76,60,0.3)", symbol="circle"),
                                     showlegend=False, hoverinfo="skip"))
            _shot_arrow(fig, float(r["shot_x"]), float(r["shot_y"]),
                        r.get("gmy", np.nan), color="rgba(231,76,60,0.3)")

    # Goal sequences: black dotted path + black circle + black arrow
    for _, row in other[other["otype"] == "goal"].iterrows():
        grp = df_c[
            (df_c["match_id"] == row["match_id"]) &
            (df_c["corner_seq_id"] == row["seq_id"])
        ].copy()
        if not grp.empty:
            _draw_goal_seq(fig, grp, str(grp.iloc[0]["team_code"]),
                           row["shot_x"], row["shot_y"], row["gmy"])

    # Stats
    n_left  = int((other["side"] == "left").sum())
    n_right = int((other["side"] == "right").sum())
    n_att   = int(other["otype"].isin(["shot", "goal"]).sum())
    n_goal  = int((other["otype"] == "goal").sum())
    fig.add_annotation(
        x=34, y=62,
        text=(f"<b>Other Corner Sequences</b><br>"
              f"Left: {n_left}  Right: {n_right}  Attempts: {n_att}  Goals: {n_goal}"),
        showarrow=False, xanchor="center", yanchor="top",
        align="center", font=dict(size=9, color=SECONDARY_COL),
    )
    _add_sp_legend(fig, y=56, c_mk=_C_CORNER, att_sym="●", goal_col="black")
    return fig


def _tbl_other_corners(df_team: pd.DataFrame, seq_sum: pd.DataFrame) -> pd.DataFrame:
    other = seq_sum[~seq_sum["in_box"]] if not seq_sum.empty else pd.DataFrame()
    df_c  = df_team[df_team["sp_type"] == "corner"]
    if other.empty or df_c.empty:
        return pd.DataFrame()

    own_team    = str(df_c["team_code"].iloc[0])
    other_pairs = other[["match_id", "seq_id"]].rename(columns={"seq_id": "corner_seq_id"})
    relevant    = df_c.merge(other_pairs, on=["match_id", "corner_seq_id"])
    rows = []
    for (_, __), grp in relevant.groupby(["match_id", "corner_seq_id"], dropna=True):
        grp = grp.reset_index(drop=True)
        pm  = grp["Corner taken"] == "Si"
        if not pm.any():
            continue
        pi    = int(grp[pm].index[0])
        after = grp[(grp.index > pi) & (grp["team_code"] == own_team)]
        next_ev  = _bucket_next_action(after.iloc[0]["event"], after.iloc[0]) if not after.empty else "Other"
        has_shot = not grp[(grp["event"].isin(_SHOT_EV)) & (grp["team_code"] == own_team)].empty
        has_goal = not grp[(grp["event"] == "Goal") & (grp["team_code"] == own_team)].empty
        rows.append({"Next Action": next_ev, "_att": has_shot, "_goal": has_goal})

    if not rows:
        return pd.DataFrame()
    tmp = pd.DataFrame(rows)
    g = tmp.groupby("Next Action").agg(Count=("_att", "count")).reset_index()
    att_map  = tmp.groupby("Next Action")["_att"].sum()
    goal_map = tmp.groupby("Next Action")["_goal"].sum()
    g["Lead to Attempt"] = g["Next Action"].map(att_map).fillna(0).astype(int)
    g["Lead to Goal"]    = g["Next Action"].map(goal_map).fillna(0).astype(int)
    return g.sort_values("Count", ascending=False)


# ══════════════════════════════════════════════════════════════════════════════
# Row 4 — Free kicks delivering into box
# ══════════════════════════════════════════════════════════════════════════════

def _summarise_fk_box(df_team: pd.DataFrame) -> pd.DataFrame:
    df_fk = df_team[df_team["sp_type"] == "fk_deliver_box"].copy()
    if df_fk.empty:
        return pd.DataFrame()

    records = []
    for (match_id, seq_id), grp in df_fk.groupby(["match_id", "fk_seq_id"], dropna=True):
        grp = grp.reset_index(drop=True)
        pm  = grp["Free kick taken"] == "Si"
        if not pm.any():
            continue
        pr     = grp[pm].iloc[0]
        pr_idx = int(grp[pm].index[0])

        px_end = pr.get("Pass End X", np.nan)
        py_end = pr.get("Pass End Y", np.nan)
        vx_end = vy_end = np.nan
        if not (pd.isna(px_end) or pd.isna(py_end)):
            vx_end, vy_end = _tv(float(px_end), float(py_end))

        taker_vx, taker_vy = np.nan, np.nan
        try:
            taker_vx, taker_vy = _tv(float(pr["x"]), float(pr["y"]))
        except (TypeError, ValueError):
            pass

        p_out    = int(pr["outcome"]) if not pd.isna(pr["outcome"]) else 0
        own_team = str(grp.iloc[0]["team_code"])
        shot_rows = grp[(grp["event"].isin(_SHOT_EV)) & (grp["team_code"] == own_team)]
        has_goal  = not grp[(grp["event"] == "Goal") & (grp["team_code"] == own_team)].empty
        has_shot  = not shot_rows.empty
        otype     = "goal" if has_goal else ("shot" if has_shot else "no_shot")

        marker = (
            "grey_x"          if p_out == 0       else
            "gold_circle"     if otype == "goal"   else
            "red_triangle"    if otype == "shot"   else
            "hollow_triangle"
        )

        shot_x = shot_y = gmy = np.nan
        if has_shot:
            sr     = shot_rows.iloc[-1]
            shot_x = sr["x"]; shot_y = sr["y"]
            gmy    = sr.get("Goal Mouth Y Coordinate", np.nan)

        after    = grp[(grp.index > pr_idx) & (grp["team_code"] == own_team)]
        recv_pid = after.iloc[0]["player_id"] if not after.empty else np.nan
        shot_head = shot_feet = False
        if has_shot:
            sr        = shot_rows.iloc[-1]
            shot_head = sr.get("Head", np.nan) == "Si"
            shot_feet = not shot_head

        records.append({
            "match_id": match_id, "seq_id": seq_id, "taker_pid": pr["player_id"],
            "taker_vx": taker_vx, "taker_vy": taker_vy,
            "inswing":  pr.get("Inswinger", np.nan) == "Si",
            "outswing": pr.get("Outswinger", np.nan) == "Si",
            "p_out": p_out, "vx_end": vx_end, "vy_end": vy_end,
            "marker": marker, "otype": otype,
            "shot_x": shot_x, "shot_y": shot_y, "gmy": gmy,
            "recv_pid": recv_pid,
            "shot_head": shot_head, "shot_feet": shot_feet,
        })

    return pd.DataFrame(records)


def _fig_fk_box(fk_sum: pd.DataFrame, df_team: pd.DataFrame) -> go.Figure:
    fig = _make_top_pitch(y_min=52.5)
    _add_box_zones(fig)
    _add_goalpost(fig)

    if fk_sum.empty:
        fig.add_annotation(x=34, y=90, text="No data", showarrow=False,
                           font=dict(size=11, color=TEXT_MUTED), xanchor="center")
        return fig

    # Pass origin circles + arrows: successful deliveries only at 10% opacity
    has_tvx = "taker_vx" in fk_sum.columns
    if has_tvx:
        suc_arr = fk_sum[(fk_sum["p_out"] == 1) & fk_sum["taker_vx"].notna() & fk_sum["vx_end"].notna()]
        for _, row in suc_arr.iterrows():
            fig.add_trace(go.Scatter(x=[row["taker_vx"]], y=[row["taker_vy"]], mode="markers",
                                     marker=dict(size=5, color="rgba(39,174,96,0.5)", symbol="circle"),
                                     showlegend=False, hoverinfo="skip"))
            fig.add_annotation(
                x=row["vx_end"], y=row["vy_end"], ax=row["taker_vx"], ay=row["taker_vy"],
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=2, arrowsize=0.7,
                arrowwidth=1.0, arrowcolor="rgba(39,174,96,0.1)", text="",
            )

    # Endpoint markers at 0.1 opacity (non-goal sequences only)
    non_goal = fk_sum[fk_sum["otype"] != "goal"]
    gx = non_goal[non_goal["marker"] == "grey_x"]
    ht = non_goal[non_goal["marker"] == "hollow_triangle"]
    rt = non_goal[non_goal["marker"] == "red_triangle"]

    if not gx.empty:
        fig.add_trace(go.Scatter(x=gx["vx_end"].tolist(), y=gx["vy_end"].tolist(),
                                 mode="markers",
                                 marker=dict(size=7, color="rgba(160,160,160,0.1)", symbol="x"),
                                 showlegend=False, hoverinfo="skip"))
    if not ht.empty:
        fig.add_trace(go.Scatter(x=ht["vx_end"].tolist(), y=ht["vy_end"].tolist(),
                                 mode="markers",
                                 marker=dict(size=8, color="rgba(255,255,255,0.5)", symbol="triangle-up",
                                             line=dict(color="rgba(39,174,96,0.3)", width=1.5)),
                                 showlegend=False, hoverinfo="skip"))
    if not rt.empty:
        fig.add_trace(go.Scatter(x=rt["vx_end"].tolist(), y=rt["vy_end"].tolist(),
                                 mode="markers",
                                 marker=dict(size=9, color="rgba(39,174,96,0.5)", symbol="triangle-up"),
                                 showlegend=False, hoverinfo="skip"))

    # Goal sequences: black dotted path + black circle + black arrow
    df_fk = df_team[df_team["sp_type"] == "fk_deliver_box"]
    for _, row in fk_sum[fk_sum["otype"] == "goal"].iterrows():
        grp = df_fk[
            (df_fk["match_id"] == row["match_id"]) &
            (df_fk["fk_seq_id"] == row["seq_id"])
        ].copy()
        if not grp.empty:
            own_team = str(grp["team_code"].iloc[0])
            _draw_goal_seq(fig, grp, own_team,
                           row["shot_x"], row["shot_y"], row["gmy"])

    # Split stats: left-side FKs on left, right-side on right
    valid = fk_sum["taker_vx"].notna() if has_tvx else pd.Series(False, index=fk_sum.index)
    left_fk  = fk_sum[valid & (fk_sum["taker_vx"] < 34)]  if has_tvx else pd.DataFrame()
    right_fk = fk_sum[valid & (fk_sum["taker_vx"] >= 34)] if has_tvx else pd.DataFrame()

    def _fk_stat_txt(sub, side):
        lbl = "Left" if side == "left" else "Right"
        if sub.empty:
            return f"<b>{lbl} Side FKs</b><br>No data"
        fp, syb, ps, farp = _zone_counts(sub, side)
        n     = len(sub)
        suc   = int((sub["p_out"] == 1).sum())
        n_att = int(sub["otype"].isin(["shot", "goal"]).sum())
        n_g   = int((sub["otype"] == "goal").sum())
        return (f"<b>{lbl} Side FKs</b><br>"
                f"Front Post: {fp}<br>6-Yd Box: {syb}<br>Pen. Spot: {ps}<br>"
                f"Far Post: {farp}<br><br>"
                f"Total: {n}<br>Received: {suc}<br>"
                f"Attempts: {n_att}<br>Goals: {n_g}")

    fig.add_annotation(x=1, y=75, text=_fk_stat_txt(left_fk, "left"),
                       showarrow=False, xanchor="left", yanchor="top",
                       align="left", font=dict(size=8.5, color=SECONDARY_COL),
                       bgcolor=CARD_BG, borderwidth=0)
    fig.add_annotation(x=67, y=75, text=_fk_stat_txt(right_fk, "right"),
                       showarrow=False, xanchor="right", yanchor="top",
                       align="right", font=dict(size=8.5, color=SECONDARY_COL),
                       bgcolor=CARD_BG, borderwidth=0)
    return fig


def _tbl_fk_takers(fk_sum: pd.DataFrame) -> pd.DataFrame:
    if fk_sum.empty:
        return pd.DataFrame()
    g = fk_sum.groupby("taker_pid").agg(
        Taken=("p_out", "count"),
        Suc=("p_out", "sum"),
        Inswing=("inswing", "sum"),
        Outswing=("outswing", "sum"),
    ).reset_index()
    g["Suc%"]     = (g["Suc"] / g["Taken"].replace(0, np.nan) * 100).round(0).fillna(0).astype(int).astype(str) + "%"
    g["Inswing"]  = g["Inswing"].astype(int)
    g["Outswing"] = g["Outswing"].astype(int)
    g["Player"]   = g["taker_pid"].map(_abbrev)
    g.insert(0, "#", range(1, len(g) + 1))
    return g[["#", "Player", "Taken", "Suc", "Suc%", "Inswing", "Outswing"]]


def _tbl_fk_receivers(fk_sum: pd.DataFrame, df_team: pd.DataFrame) -> pd.DataFrame:
    if fk_sum.empty:
        return pd.DataFrame()
    recv = (fk_sum[fk_sum["recv_pid"].notna()]
            .groupby("recv_pid").size().rename("Received")
            .reset_index().rename(columns={"recv_pid": "pid"}))

    df_fk     = df_team[df_team["sp_type"] == "fk_deliver_box"]
    fk_pairs  = fk_sum[["match_id", "seq_id"]].rename(columns={"seq_id": "fk_seq_id"})
    shots     = df_fk[df_fk["event"].isin(_SHOT_EV)].merge(fk_pairs, on=["match_id", "fk_seq_id"])

    if shots.empty:
        for c in ["Att Hdr", "Att Feet", "Goal Hdr", "Goal Feet"]:
            recv[c] = 0
    else:
        shots["is_head"]      = (shots["Head"] == "Si")
        shots["is_goal"]      = (shots["event"] == "Goal")
        shots["is_goal_head"] = shots["is_goal"] & shots["is_head"]
        shots["is_goal_feet"] = shots["is_goal"] & ~shots["is_head"]
        sa = shots.groupby("player_id").agg(
            att_hdr=("is_head",       "sum"),
            att_feet=("is_head",      lambda x: int((~x.astype(bool)).sum())),
            goal_hdr=("is_goal_head", "sum"),
            goal_feet=("is_goal_feet", "sum"),
        ).reset_index().rename(columns={"player_id": "pid"})
        recv = recv.merge(sa, on="pid", how="left").fillna(0)
        recv = recv.rename(columns={
            "att_hdr": "Att Hdr", "att_feet": "Att Feet",
            "goal_hdr": "Goal Hdr", "goal_feet": "Goal Feet",
        })
        for c in ["Att Hdr", "Att Feet", "Goal Hdr", "Goal Feet"]:
            recv[c] = recv[c].astype(int)

    recv["Player"] = recv["pid"].map(_abbrev)
    recv.insert(0, "#", range(1, len(recv) + 1))
    cols = ["#", "Player", "Received", "Att Hdr", "Att Feet", "Goal Hdr", "Goal Feet"]
    return recv[[c for c in cols if c in recv.columns]]


# ══════════════════════════════════════════════════════════════════════════════
# Row 5 — Short / other free kick sequences
# ══════════════════════════════════════════════════════════════════════════════

def _fig_short_fk(df_team: pd.DataFrame) -> go.Figure:
    fig = _make_half_pitch()
    _add_goalpost(fig)

    df_sfk = df_team[df_team["sp_type"] == "fk_short"].copy()
    if df_sfk.empty:
        fig.add_annotation(x=34, y=75, text="No data", showarrow=False,
                           font=dict(size=11, color=TEXT_MUTED), xanchor="center")
        return fig

    own_team = str(df_sfk["team_code"].iloc[0])
    n_left = n_right = n_att = n_goal = 0

    for (_, __), grp in df_sfk.groupby(["match_id", "short_fk_seq_id"], dropna=True):
        grp = grp.reset_index(drop=True)
        pm  = grp["Free kick taken"] == "Si"
        if not pm.any():
            continue
        pr = grp[pm].iloc[0]
        pi = int(grp[pm].index[0])

        try:
            side_left = float(pr["y"]) > 50
        except (TypeError, ValueError):
            side_left = False
        if side_left:
            n_left += 1
        else:
            n_right += 1

        own_shots = grp[(grp["event"].isin(_SHOT_EV)) & (grp["team_code"] == own_team)]
        is_goal   = not grp[(grp["event"] == "Goal") & (grp["team_code"] == own_team)].empty
        if is_goal:
            n_att += 1; n_goal += 1
        elif not own_shots.empty:
            n_att += 1

        # Goal sequence: black dotted path + black circle + black arrow
        if is_goal and not own_shots.empty:
            sr = own_shots.iloc[-1]
            _draw_goal_seq(fig, grp, own_team, float(sr["x"]), float(sr["y"]),
                           sr.get("Goal Mouth Y Coordinate", np.nan))
            continue

        # Pass origin: green filled circle + green pass route arrow (opacity 0.1)
        p_out = int(pr["outcome"]) if not pd.isna(pr["outcome"]) else 0
        try:
            vx_orig, vy_orig = _tv(float(pr["x"]), float(pr["y"]))
        except (TypeError, ValueError):
            continue
        fig.add_trace(go.Scatter(x=[vx_orig], y=[vy_orig], mode="markers",
                                 marker=dict(size=5, color="rgba(39,174,96,0.5)", symbol="circle"),
                                 showlegend=False, hoverinfo="skip"))
        px_end = pr.get("Pass End X", np.nan)
        py_end = pr.get("Pass End Y", np.nan)
        if not (pd.isna(px_end) or pd.isna(py_end)):
            vx_e, vy_e = _tv(float(px_end), float(py_end))
            fig.add_annotation(
                x=vx_e, y=vy_e, ax=vx_orig, ay=vy_orig,
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=2, arrowsize=0.7,
                arrowwidth=1.0, arrowcolor="rgba(39,174,96,0.1)", text="",
            )

        # Purple cross arrows for next cross into box (outcome=1 only)
        if p_out == 1:
            after = grp[(grp.index > pi) & (grp["team_code"] == own_team)]
            if not after.empty:
                nr  = after.iloc[0]
                nex = nr.get("Pass End X", np.nan)
                ney = nr.get("Pass End Y", np.nan)
                if nr["event"] == "Pass" and not (pd.isna(nex) or pd.isna(ney)):
                    if float(nex) > FK_X_MIN and FK_Y_MIN <= float(ney) <= FK_Y_MAX:
                        vx0, vy0 = _tv(float(nr["x"]), float(nr["y"]))
                        vx1, vy1 = _tv(float(nex), float(ney))
                        fig.add_annotation(
                            x=vx1, y=vy1, ax=vx0, ay=vy0,
                            xref="x", yref="y", axref="x", ayref="y",
                            showarrow=True, arrowhead=2, arrowsize=0.9,
                            arrowwidth=1.5, arrowcolor="rgba(142,68,173,0.5)", text="",
                        )

        # Shot attempt: grey filled circle + grey shot arrow
        if not own_shots.empty:
            sr = own_shots.iloc[-1]
            vx_sh, vy_sh = _tv(float(sr["x"]), float(sr["y"]))
            fig.add_trace(go.Scatter(x=[vx_sh], y=[vy_sh], mode="markers",
                                     marker=dict(size=9, color="rgba(160,160,160,0.8)", symbol="circle"),
                                     showlegend=False, hoverinfo="skip"))
            _shot_arrow(fig, float(sr["x"]), float(sr["y"]),
                        sr.get("Goal Mouth Y Coordinate", np.nan), color="rgba(160,160,160,0.3)")

    fig.add_annotation(
        x=34, y=62,
        text=(f"<b>Other FK Sequences</b><br>"
              f"Left: {n_left}  Right: {n_right}  Attempts: {n_att}  Goals: {n_goal}"),
        showarrow=False, xanchor="center", yanchor="top",
        align="center", font=dict(size=9, color=SECONDARY_COL),
    )
    for lx, txt, col in [
        (2,  "● Pass Origin",    "rgba(39,174,96,0.8)"),
        (17, "→ Cross into Box", "rgba(142,68,173,0.8)"),
        (34, "● Shot",           "rgba(160,160,160,0.8)"),
        (49, "● Goal",           "black"),
    ]:
        fig.add_annotation(x=lx, y=56, text=txt, showarrow=False,
                           xanchor="left", yanchor="top",
                           font=dict(size=10, color=col))
    return fig


def _tbl_short_fk_next(df_team: pd.DataFrame) -> pd.DataFrame:
    df_sfk = df_team[df_team["sp_type"] == "fk_short"].copy()
    if df_sfk.empty:
        return pd.DataFrame()

    own_team = str(df_sfk["team_code"].iloc[0])
    rows = []
    for (_, __), grp in df_sfk.groupby(["match_id", "short_fk_seq_id"], dropna=True):
        grp = grp.reset_index(drop=True)
        pm  = grp["Free kick taken"] == "Si"
        if not pm.any():
            continue
        pi    = int(grp[pm].index[0])
        after = grp[(grp.index > pi) & (grp["team_code"] == own_team)]
        next_ev  = _bucket_next_action(after.iloc[0]["event"], after.iloc[0]) if not after.empty else "Other"
        has_shot = not grp[(grp["event"].isin(_SHOT_EV)) & (grp["team_code"] == own_team)].empty
        has_goal = not grp[(grp["event"] == "Goal") & (grp["team_code"] == own_team)].empty
        rows.append({"Next Action": next_ev, "_att": has_shot, "_goal": has_goal})

    if not rows:
        return pd.DataFrame()
    tmp = pd.DataFrame(rows)
    g = tmp.groupby("Next Action").agg(Count=("_att", "count")).reset_index()
    att_map  = tmp.groupby("Next Action")["_att"].sum()
    goal_map = tmp.groupby("Next Action")["_goal"].sum()
    g["Lead to Attempt"] = g["Next Action"].map(att_map).fillna(0).astype(int)
    g["Lead to Goal"]    = g["Next Action"].map(goal_map).fillna(0).astype(int)
    return g.sort_values("Count", ascending=False)


# ══════════════════════════════════════════════════════════════════════════════
# Row 6 — Direct free kicks & penalties
# ══════════════════════════════════════════════════════════════════════════════

def _fig_dfk_pk(df_team: pd.DataFrame) -> go.Figure:
    fig = _make_top_pitch(y_min=60)
    _add_box_zones(fig)
    _add_goalpost(fig)

    # Goalpost illustration: two posts + crossbar above pitch end line
    #_GP_L, _GP_R, _GP_BASE, _GP_TOP = 34 - 3.66, 34 + 3.66, 105.0, 107.2
    #for vx in [_GP_L, _GP_R]:
    #    fig.add_shape(type="line", x0=vx, y0=_GP_BASE, x1=vx, y1=_GP_TOP,
    #                  line=dict(color="#666666", width=2.5), layer="above")
    #fig.add_shape(type="line", x0=_GP_L, y0=_GP_TOP, x1=_GP_R, y1=_GP_TOP,
    #              line=dict(color="#666666", width=2.5), layer="above")

    df_d = df_team[df_team["sp_type"] == "dfk_pk"].copy()
    if df_d.empty:
        fig.add_annotation(x=34, y=80, text="No data", showarrow=False,
                           font=dict(size=11, color=TEXT_MUTED), xanchor="center")
        return fig

    df_d["vx"] = 68 - (df_d["y"] / 100 * 68)
    df_d["vy"] = df_d["x"] / 100 * 105
    df_d["_is_pen"] = df_d["Penalty"].fillna("") == "Si"

    on_tgt  = df_d[df_d["event"] == "Saved Shot"]
    off_tgt = df_d[df_d["event"].isin({"Miss", "Post"})]
    fk_goals  = df_d[(df_d["event"] == "Goal") & ~df_d["_is_pen"]]
    pen_goals = df_d[(df_d["event"] == "Goal") &  df_d["_is_pen"]]

    if not off_tgt.empty:
        fig.add_trace(go.Scatter(x=off_tgt["vx"].tolist(), y=off_tgt["vy"].tolist(),
                                 mode="markers", marker=dict(size=8, color=_C_FAIL, symbol="x"),
                                 showlegend=False, hoverinfo="skip"))
    if not on_tgt.empty:
        fig.add_trace(go.Scatter(x=on_tgt["vx"].tolist(), y=on_tgt["vy"].tolist(),
                                 mode="markers",
                                 marker=dict(size=8, color="white", symbol="triangle-up",
                                             line=dict(color=LALIGA_RED, width=1.5)),
                                 showlegend=False, hoverinfo="skip"))
    if not fk_goals.empty:
        fig.add_trace(go.Scatter(x=fk_goals["vx"].tolist(), y=fk_goals["vy"].tolist(),
                                 mode="markers",
                                 marker=dict(size=10, color=_C_GOLD, symbol="circle",
                                             line=dict(color="white", width=1)),
                                 showlegend=False, hoverinfo="skip"))
        for _, r in fk_goals.iterrows():
            _shot_arrow(fig, float(r["x"]), float(r["y"]),
                        r.get("Goal Mouth Y Coordinate", np.nan), _C_GOLD)
    if not pen_goals.empty:
        fig.add_trace(go.Scatter(x=pen_goals["vx"].tolist(), y=pen_goals["vy"].tolist(),
                                 mode="markers",
                                 marker=dict(size=10, color=_C_FK, symbol="circle",
                                             line=dict(color="white", width=1)),
                                 showlegend=False, hoverinfo="skip"))
        for _, r in pen_goals.iterrows():
            _shot_arrow(fig, float(r["x"]), float(r["y"]),
                        r.get("Goal Mouth Y Coordinate", np.nan), _C_FK)

    n       = len(df_d)
    s_cnt   = len(on_tgt) + len(fk_goals) + len(pen_goals)
    fk_g    = len(fk_goals)
    pen_g   = len(pen_goals)
    fig.add_annotation(
        x=34, y=64,
        text=(f"<b>DFKs & Penalties</b><br>Shots: {n}  On Target: {s_cnt}<br>"
              f"FK Goals: {fk_g}  Pen Goals: {pen_g}"),
        showarrow=False, xanchor="center", yanchor="bottom",
        align="center", font=dict(size=9, color=SECONDARY_COL),
    )
    return fig


def _tbl_pk_takers(df_team: pd.DataFrame) -> pd.DataFrame:
    df_d = df_team[df_team["sp_type"] == "dfk_pk"].copy()
    if df_d.empty:
        return pd.DataFrame()
    pens = df_d[df_d["Penalty"].fillna("") == "Si"]
    if pens.empty:
        return pd.DataFrame()
    pens = pens.copy()
    pens["_goal"] = (pens["event"] == "Goal").astype(int)
    g = pens.groupby("player_id").agg(
        PK_Taken=("event", "count"),
        Goals=("_goal", "sum"),
    ).reset_index()
    g["Conv%"]  = (g["Goals"] / g["PK_Taken"].replace(0, np.nan) * 100).round(0).fillna(0).astype(int).astype(str) + "%"
    g["Player"] = g["player_id"].map(_abbrev)
    g = g.rename(columns={"PK_Taken": "PK Taken"})
    g.insert(0, "#", range(1, len(g) + 1))
    return g[["#", "Player", "PK Taken", "Goals", "Conv%"]]


def _tbl_dfk_takers(df_team: pd.DataFrame) -> pd.DataFrame:
    df_d = df_team[df_team["sp_type"] == "dfk_pk"].copy()
    if df_d.empty:
        return pd.DataFrame()
    dfks = df_d[df_d["Penalty"].fillna("") != "Si"]
    if dfks.empty:
        return pd.DataFrame()
    dfks = dfks.copy()
    dfks["_sot"]  = dfks["event"].isin({"Saved Shot", "Goal"}).astype(int)
    dfks["_goal"] = (dfks["event"] == "Goal").astype(int)
    g = dfks.groupby("player_id").agg(
        DFK_Taken=("event", "count"),
        SoT=("_sot", "sum"),
        Goals=("_goal", "sum"),
    ).reset_index()
    g["SoT%"]   = (g["SoT"]   / g["DFK_Taken"].replace(0, np.nan) * 100).round(0).fillna(0).astype(int).astype(str) + "%"
    g["Conv%"]  = (g["Goals"] / g["DFK_Taken"].replace(0, np.nan) * 100).round(0).fillna(0).astype(int).astype(str) + "%"
    g["Player"] = g["player_id"].map(_abbrev)
    g = g.rename(columns={"DFK_Taken": "DFK Taken"})
    g.insert(0, "#", range(1, len(g) + 1))
    return g[["#", "Player", "DFK Taken", "SoT", "Goals", "SoT%", "Conv%"]]


# ── Goalpost face helpers ─────────────────────────────────────────────────────

def _gxy(gmy: float, gmz: float):
    """Pitch goal-mouth coords (0-100 scale) → goal-face metres (x=horiz, y=height).
    X is mirrored because vx = 68 − y/100×68 flips the pitch-y axis left/right,
    so higher pitch-y = attacker's left post (gx=0), lower = right post (gx=7.32)."""
    gx = (_GY_MAX - gmy) / (_GY_MAX - _GY_MIN) * _GOAL_W
    gy = gmz / _GZ_MAX * _GOAL_H
    return gx, gy


def _fig_goalpost_shots(shots_df: pd.DataFrame, goal_color: str) -> go.Figure:
    """
    Goalpost face (7.32 × 2.44 m) with all shots as circles and a
    Plotly updatemenu dropdown to filter by shooter (default = All).
    Filled circle = goal; open circle = saved / missed / post.
    """
    fig = go.Figure()
    _px, _pyt, _pyb = 1.0, 0.35, 0.55

    fig.update_layout(
        plot_bgcolor=CARD_BG, paper_bgcolor=CARD_BG,
        xaxis=dict(range=[-_px, _GOAL_W + _px], showgrid=False,
                   zeroline=False, showticklabels=False, fixedrange=True),
        yaxis=dict(range=[-_pyb, _GOAL_H + _pyt], showgrid=False,
                   zeroline=False, showticklabels=False, fixedrange=True),
        margin=dict(l=4, r=4, t=34, b=4),
        showlegend=False,
    )

    # Goal frame
    fig.add_shape(type="rect", x0=0, y0=0, x1=_GOAL_W, y1=_GOAL_H,
                  line=dict(color="#aaaaaa", width=2.5),
                  fillcolor="rgba(255,255,255,0.04)", layer="below")
    # Ground line
    fig.add_shape(type="line", x0=-_px, y0=0, x1=_GOAL_W + _px, y1=0,
                  line=dict(color="#666666", width=1.5))
    # Post stubs below ground
    for px_ in [0.0, _GOAL_W]:
        fig.add_shape(type="line", x0=px_, y0=0, x1=px_, y1=-_pyb,
                      line=dict(color="#666666", width=1.5, dash="dot"))

    gmy_col = "Goal Mouth Y Coordinate"
    gmz_col = "Goal Mouth Z Coordinate"

    if shots_df.empty or gmy_col not in shots_df.columns:
        fig.add_annotation(x=_GOAL_W / 2, y=_GOAL_H / 2, text="No data",
                           showarrow=False, font=dict(size=10, color=TEXT_MUTED),
                           xanchor="center", yanchor="middle")
        return fig

    has_z = gmz_col in shots_df.columns
    valid = shots_df.dropna(subset=[gmy_col]).copy()

    if valid.empty:
        fig.add_annotation(x=_GOAL_W / 2, y=_GOAL_H / 2, text="No data",
                           showarrow=False, font=dict(size=10, color=TEXT_MUTED),
                           xanchor="center", yanchor="middle")
        return fig

    # Default = player with most goals; fallback = most shots
    goal_rows = valid[valid["event"] == "Goal"]
    top_pid = (goal_rows.groupby("player_id").size().idxmax()
               if not goal_rows.empty
               else valid.groupby("player_id").size().idxmax())

    players = list(valid["player_id"].unique())
    players = [top_pid] + [p for p in players if p != top_pid]

    views = [("All", valid)] + [(p, valid[valid["player_id"] == p]) for p in players]
    default_idx = 0  # default = All

    def _xy_goals(s):
        xs, ys, txts = [], [], []
        for _, r in s.iterrows():
            try:
                gx, gy = _gxy(
                    float(r[gmy_col]),
                    float(r[gmz_col]) if has_z and not pd.isna(r.get(gmz_col)) else 19.0,
                )
                opp  = _MATCH_OPP.get((r["match_id"], r["team_code"]), "?")
                mins = str(int(float(r["time_min"]))) if not pd.isna(r.get("time_min")) else "?"
                jn_  = r.get("Jersey Number", np.nan)
                jn   = str(int(float(jn_))) if not pd.isna(jn_) else "?"
                name = SHORT_NAME.get(str(r["player_id"]), _abbrev(r["player_id"]))
                xs.append(gx); ys.append(gy)
                txts.append(f"v {opp} {mins}' #{jn} {name}")
            except (TypeError, ValueError):
                pass
        return xs, ys, txts

    def _xy_non(s):
        xs, ys = [], []
        for _, r in s.iterrows():
            try:
                gx, gy = _gxy(
                    float(r[gmy_col]),
                    float(r[gmz_col]) if has_z and not pd.isna(r.get(gmz_col)) else 19.0,
                )
                xs.append(gx); ys.append(gy)
            except (TypeError, ValueError):
                pass
        return xs, ys

    for i, (_, sub) in enumerate(views):
        vis = (i == default_idx)
        goals = sub[sub["event"] == "Goal"]
        non_g = sub[sub["event"] != "Goal"]
        gx, gy, gt = _xy_goals(goals)
        nx, ny     = _xy_non(non_g)

        fig.add_trace(go.Scatter(
            x=gx, y=gy, mode="markers", text=gt,
            hovertemplate="%{text}<extra></extra>", visible=vis,
            marker=dict(size=10, color=goal_color, symbol="circle",
                        line=dict(color="white", width=1.5)),
            showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=nx, y=ny, mode="markers",
            hoverinfo="skip", visible=vis,
            marker=dict(size=8, color=_C_FAIL, symbol="circle-open",
                        line=dict(color=_C_FAIL, width=2)),
            showlegend=False,
        ))

    n_total = len(views) * 2
    buttons = []
    for i, (lbl_or_pid, _) in enumerate(views):
        vis_arr = [False] * n_total
        vis_arr[i * 2] = True
        vis_arr[i * 2 + 1] = True
        lbl = lbl_or_pid if lbl_or_pid == "All" else _shooter_label(lbl_or_pid)
        buttons.append(dict(label=lbl, method="update", args=[{"visible": vis_arr}]))

    fig.update_layout(updatemenus=[dict(
        type="dropdown",
        buttons=buttons,
        direction="down",
        showactive=True,
        active=default_idx,
        x=0.0, xanchor="left",
        y=1.0, yanchor="bottom",
        bgcolor=CARD_BG, bordercolor=BORDER,
        font=dict(size=9, color=SECONDARY_COL),
        pad=dict(r=2, t=2, b=2, l=2),
    )])

    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Row 7 — Long throw-ins
# ══════════════════════════════════════════════════════════════════════════════

def _summarise_longthrows(df_team: pd.DataFrame) -> pd.DataFrame:
    df_lt = df_team[df_team["sp_type"] == "longthrow"].copy()
    if df_lt.empty:
        return pd.DataFrame()

    records = []
    for (match_id, seq_id), grp in df_lt.groupby(["match_id", "longthrow_seq_id"], dropna=True):
        grp = grp.reset_index(drop=True)
        pm  = grp["Throw In"] == "Si"
        if not pm.any():
            continue
        pr     = grp[pm].iloc[0]
        pr_idx = int(grp[pm].index[0])

        px_end = pr.get("Pass End X", np.nan)
        py_end = pr.get("Pass End Y", np.nan)
        vx_end = vy_end = np.nan
        if not (pd.isna(px_end) or pd.isna(py_end)):
            vx_end, vy_end = _tv(float(px_end), float(py_end))

        taker_vx, taker_vy = np.nan, np.nan
        try:
            taker_vx, taker_vy = _tv(float(pr["x"]), float(pr["y"]))
        except (TypeError, ValueError):
            pass

        p_out    = int(pr["outcome"]) if not pd.isna(pr["outcome"]) else 0
        own_team = str(grp.iloc[0]["team_code"])
        shot_rows = grp[(grp["event"].isin(_SHOT_EV)) & (grp["team_code"] == own_team)]
        has_goal  = not grp[(grp["event"] == "Goal") & (grp["team_code"] == own_team)].empty
        has_shot  = not shot_rows.empty
        otype     = "goal" if has_goal else ("shot" if has_shot else "no_shot")

        marker = (
            "grey_x"          if p_out == 0       else
            "gold_circle"     if otype == "goal"   else
            "red_triangle"    if otype == "shot"   else
            "hollow_triangle"
        )

        shot_x = shot_y = gmy = np.nan
        if has_shot:
            sr     = shot_rows.iloc[-1]
            shot_x = sr["x"]; shot_y = sr["y"]
            gmy    = sr.get("Goal Mouth Y Coordinate", np.nan)

        after    = grp[(grp.index > pr_idx) & (grp["team_code"] == own_team)]
        recv_pid = after.iloc[0]["player_id"] if not after.empty else np.nan
        shot_head = shot_feet = False
        if has_shot:
            sr        = shot_rows.iloc[-1]
            shot_head = sr.get("Head", np.nan) == "Si"
            shot_feet = not shot_head

        records.append({
            "match_id": match_id, "seq_id": seq_id, "taker_pid": pr["player_id"],
            "taker_vx": taker_vx, "taker_vy": taker_vy,
            "p_out": p_out, "vx_end": vx_end, "vy_end": vy_end,
            "marker": marker, "otype": otype,
            "shot_x": shot_x, "shot_y": shot_y, "gmy": gmy,
            "recv_pid": recv_pid,
            "shot_head": shot_head, "shot_feet": shot_feet,
        })

    return pd.DataFrame(records)


def _fig_longthrow(lt_sum: pd.DataFrame, df_team: pd.DataFrame) -> go.Figure:
    fig = _make_top_pitch(y_min=73.5)
    _add_box_zones(fig)
    _add_goalpost(fig)

    if lt_sum.empty:
        fig.add_annotation(x=34, y=90, text="No data", showarrow=False,
                           font=dict(size=11, color=TEXT_MUTED), xanchor="center")
        return fig

    non_goal = lt_sum[lt_sum["otype"] != "goal"]
    gx = non_goal[non_goal["marker"] == "grey_x"]
    ht = non_goal[non_goal["marker"] == "hollow_triangle"]
    rt = non_goal[non_goal["marker"] == "red_triangle"]

    if not gx.empty:
        fig.add_trace(go.Scatter(x=gx["vx_end"].tolist(), y=gx["vy_end"].tolist(),
                                 mode="markers", marker=dict(size=7, color=_C_FAIL, symbol="x"),
                                 showlegend=False, hoverinfo="skip"))
    if not ht.empty:
        fig.add_trace(go.Scatter(x=ht["vx_end"].tolist(), y=ht["vy_end"].tolist(),
                                 mode="markers",
                                 marker=dict(size=8, color="white", symbol="triangle-up",
                                             line=dict(color=_C_THROW, width=1.5)),
                                 showlegend=False, hoverinfo="skip"))
    if not rt.empty:
        fig.add_trace(go.Scatter(x=rt["vx_end"].tolist(), y=rt["vy_end"].tolist(),
                                 mode="markers",
                                 marker=dict(size=9, color=_C_THROW, symbol="triangle-up"),
                                 showlegend=False, hoverinfo="skip"))

    # Goal sequences: black dotted path + black circle + black solid arrow
    df_lt = df_team[df_team["sp_type"] == "longthrow"]
    for _, row in lt_sum[lt_sum["otype"] == "goal"].iterrows():
        grp = df_lt[
            (df_lt["match_id"] == row["match_id"]) &
            (df_lt["longthrow_seq_id"] == row["seq_id"])
        ].copy()
        if not grp.empty:
            _draw_goal_seq(fig, grp, str(grp.iloc[0]["team_code"]),
                           row["shot_x"], row["shot_y"], row["gmy"])

    has_tvx = "taker_vx" in lt_sum.columns
    if has_tvx:
        valid    = lt_sum["taker_vx"].notna()
        left_lt  = lt_sum[valid & (lt_sum["taker_vx"] < 34)]
        right_lt = lt_sum[valid & (lt_sum["taker_vx"] >= 34)]
    else:
        left_lt = right_lt = pd.DataFrame()

    def _lt_txt(sub, lbl):
        if sub.empty:
            return f"<b>{lbl} Side</b><br>No data"
        n = len(sub)
        s = int((sub["p_out"] == 1).sum())
        a = int(sub["otype"].isin(["shot", "goal"]).sum())
        g = int((sub["otype"] == "goal").sum())
        return (f"<b>{lbl} Side Throws</b><br>"
                f"Total: {n}<br>Received: {s}<br>"
                f"Shots: {a}<br>Goals: {g}")

    fig.add_annotation(x=1, y=83, text=_lt_txt(left_lt, "Left"),
                       showarrow=False, xanchor="left", yanchor="top",
                       align="left", font=dict(size=10, color=SECONDARY_COL),
                       bgcolor=CARD_BG, borderwidth=0)
    fig.add_annotation(x=67, y=83, text=_lt_txt(right_lt, "Right"),
                       showarrow=False, xanchor="right", yanchor="top",
                       align="right", font=dict(size=10, color=SECONDARY_COL),
                       bgcolor=CARD_BG, borderwidth=0)
    return fig


def _tbl_lt_takers(lt_sum: pd.DataFrame) -> pd.DataFrame:
    if lt_sum.empty:
        return pd.DataFrame()
    g = lt_sum.groupby("taker_pid").agg(
        Throws=("p_out", "count"),
        Suc=("p_out", "sum"),
    ).reset_index()
    g["Suc%"]   = (g["Suc"] / g["Throws"].replace(0, np.nan) * 100).round(0).fillna(0).astype(int).astype(str) + "%"
    g["Player"] = g["taker_pid"].map(_abbrev)
    g.insert(0, "#", range(1, len(g) + 1))
    return g[["#", "Player", "Throws", "Suc", "Suc%"]]


def _tbl_lt_receivers(lt_sum: pd.DataFrame, df_team: pd.DataFrame) -> pd.DataFrame:
    if lt_sum.empty:
        return pd.DataFrame()
    recv = (lt_sum[lt_sum["recv_pid"].notna()]
            .groupby("recv_pid").size().rename("Received")
            .reset_index().rename(columns={"recv_pid": "pid"}))

    df_lt    = df_team[df_team["sp_type"] == "longthrow"]
    lt_pairs = lt_sum[["match_id", "seq_id"]].rename(columns={"seq_id": "longthrow_seq_id"})
    shots    = df_lt[df_lt["event"].isin(_SHOT_EV)].merge(lt_pairs, on=["match_id", "longthrow_seq_id"])

    if shots.empty:
        for c in ["Att Hdr", "Att Feet", "Goal Hdr", "Goal Feet"]:
            recv[c] = 0
    else:
        shots["is_head"]      = (shots["Head"] == "Si")
        shots["is_goal"]      = (shots["event"] == "Goal")
        shots["is_goal_head"] = shots["is_goal"] & shots["is_head"]
        shots["is_goal_feet"] = shots["is_goal"] & ~shots["is_head"]
        sa = shots.groupby("player_id").agg(
            att_hdr=("is_head",       "sum"),
            att_feet=("is_head",      lambda x: int((~x.astype(bool)).sum())),
            goal_hdr=("is_goal_head", "sum"),
            goal_feet=("is_goal_feet", "sum"),
        ).reset_index().rename(columns={"player_id": "pid"})
        recv = recv.merge(sa, on="pid", how="left").fillna(0)
        recv = recv.rename(columns={
            "att_hdr": "Att Hdr", "att_feet": "Att Feet",
            "goal_hdr": "Goal Hdr", "goal_feet": "Goal Feet",
        })
        for c in ["Att Hdr", "Att Feet", "Goal Hdr", "Goal Feet"]:
            recv[c] = recv[c].astype(int)

    recv["Player"] = recv["pid"].map(_abbrev)
    recv.insert(0, "#", range(1, len(recv) + 1))
    cols = ["#", "Player", "Received", "Att Hdr", "Att Feet", "Goal Hdr", "Goal Feet"]
    return recv[[c for c in cols if c in recv.columns]]


# ══════════════════════════════════════════════════════════════════════════════
# Set Piece Radar
# ══════════════════════════════════════════════════════════════════════════════

_SP_RADAR_LABELS = [
    "Corners (into box)",
    "Free Kicks (into box)",
    "PK",
    "Throw Ins (into box)",
    "Other Corners",
    "Other FK",
    "Direct FK",
]


def _rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _sp_component_stats(tdf: pd.DataFrame) -> dict:
    """3 sub-metrics per SP radar axis for one team.

    Sequence axes → {suc_rate, attempt_rate, goal_rate}
    DFK / PK      → {goal_count, goal_pct, sot_pct}
    """
    own_team = str(tdf["team_code"].iloc[0]) if not tdf.empty else ""

    def _seq_rates(df):
        n = len(df) if df is not None else 0
        if n == 0:
            return {"suc_rate": 0.0, "attempt_rate": 0.0, "goal_rate": 0.0}
        return {
            "suc_rate":     float((df["p_out"] == 1).sum()) / n,
            "attempt_rate": float(df["otype"].isin(["shot", "goal"]).sum()) / n,
            "goal_rate":    float((df["otype"] == "goal").sum()) / n,
        }

    # Sequence-based axes via existing summarise helpers
    c_sum   = _summarise_corners(tdf)
    c_box   = c_sum[c_sum["in_box"]]  if not c_sum.empty else pd.DataFrame()
    c_other = c_sum[~c_sum["in_box"]] if not c_sum.empty else pd.DataFrame()
    fk_sum  = _summarise_fk_box(tdf)
    lt_sum  = _summarise_longthrows(tdf)

    # Short FK — lightweight groupby
    sfk_rows = []
    for (_, __), grp in tdf[tdf["sp_type"] == "fk_short"].groupby(
            ["match_id", "short_fk_seq_id"], dropna=True):
        grp = grp.reset_index(drop=True)
        if "Free kick taken" not in grp.columns:
            continue
        pm = grp["Free kick taken"] == "Si"
        if not pm.any():
            continue
        pr      = grp[pm].iloc[0]
        p_out   = int(pr["outcome"]) if not pd.isna(pr.get("outcome", np.nan)) else 0
        own     = grp["team_code"] == own_team
        is_goal = ((grp["event"] == "Goal") & own).any()
        is_shot = (grp["event"].isin(_SHOT_EV) & own).any()
        sfk_rows.append({
            "p_out": p_out,
            "otype": "goal" if is_goal else ("shot" if is_shot else "no_shot"),
        })
    sfk_sum = pd.DataFrame(sfk_rows) if sfk_rows else pd.DataFrame(columns=["p_out", "otype"])

    # DFK + PK: event-level shot rows
    dfk_df  = tdf[tdf["sp_type"] == "dfk_pk"]
    pen_col = (dfk_df["Penalty"].fillna("") if "Penalty" in dfk_df.columns and not dfk_df.empty
               else pd.Series("", index=dfk_df.index))

    dfk_ev  = dfk_df[(pen_col != "Si") & dfk_df["event"].isin(_SHOT_EV)]
    dfk_n   = len(dfk_ev)
    dfk_g   = int((dfk_ev["event"] == "Goal").sum())                  if dfk_n else 0
    dfk_sot = int(dfk_ev["event"].isin({"Goal", "Saved Shot"}).sum()) if dfk_n else 0

    pk_ev  = dfk_df[(pen_col == "Si") & dfk_df["event"].isin(_SHOT_EV)]
    pk_n   = len(pk_ev)
    pk_g   = int((pk_ev["event"] == "Goal").sum())                    if pk_n else 0
    pk_sot = int(pk_ev["event"].isin({"Goal", "Saved Shot"}).sum())   if pk_n else 0

    return {
        "Corners (into box)":    _seq_rates(c_box),
        "Free Kicks (into box)": _seq_rates(fk_sum),
        "PK": {
            "goal_count": float(pk_g),
            "goal_pct":   pk_g   / max(pk_n, 1),
            "sot_pct":    pk_sot / max(pk_n, 1),
        },
        "Throw Ins (into box)":  _seq_rates(lt_sum),
        "Other Corners":         _seq_rates(c_other),
        "Other FK":              _seq_rates(sfk_sum),
        "Direct FK": {
            "goal_count": float(dfk_g),
            "goal_pct":   dfk_g   / max(dfk_n, 1),
            "sot_pct":    dfk_sot / max(dfk_n, 1),
        },
    }


def _sp_percentile_scores(code: str, sp_df: pd.DataFrame) -> list:
    """Return list of (label, percentile_0_100) for the 7 SP radar axes.

    Each axis score = average of 3 sub-metric percentile ranks across all teams.
    Sequence axes: suc_rate, attempt_rate, goal_rate.
    DFK / PK:      goal_count, goal_pct, sot_pct.
    """
    if sp_df is None or sp_df.empty:
        return [(lbl, 50.0) for lbl in _SP_RADAR_LABELS]

    teams     = sp_df["team_code"].dropna().unique()
    all_stats = {tc: _sp_component_stats(sp_df[sp_df["team_code"] == tc]) for tc in teams}
    n         = len(teams)

    result = []
    for lbl in _SP_RADAR_LABELS:
        tc_vals  = {tc: all_stats[tc].get(lbl, {}) for tc in teams}
        mk_keys  = list(next(iter(tc_vals.values()), {}).keys())
        sub_pcts = []
        for mk in mk_keys:
            vals       = [tc_vals[tc].get(mk, 0.0) for tc in teams]
            my_val     = tc_vals.get(code, {}).get(mk, 0.0)
            rank_below = sum(1 for v in vals if v < my_val)
            sub_pcts.append(rank_below / max(n - 1, 1) * 100)
        avg_pct = round(sum(sub_pcts) / len(sub_pcts), 1) if sub_pcts else 50.0
        result.append((lbl, avg_pct))
    return result


def _fig_sp_radar(pct_scores: list, code: str, color: str) -> go.Figure:
    labels     = [d[0] for d in pct_scores]
    values     = [d[1] for d in pct_scores]
    league_ref = [50.0] * len(labels)

    lbl_c = labels + [labels[0]]
    v_c   = values + [values[0]]
    l_c   = league_ref + [league_ref[0]]

    r, g, b = _rgb(color)
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=l_c, theta=lbl_c, mode="lines",
        line=dict(color="#AAAAAA", width=1.5, dash="dot"),
        name="League Avg", showlegend=True,
    ))
    fig.add_trace(go.Scatterpolar(
        r=v_c, theta=lbl_c, fill="toself",
        fillcolor=f"rgba({r},{g},{b},0.25)",
        line=dict(color=color, width=2),
        name=f"{code} Set Pieces", showlegend=True,
    ))
    fig.update_layout(
        polar=dict(
            bgcolor=CARD_BG,
            radialaxis=dict(
                visible=True, range=[0, 108],
                tickvals=[25, 50, 75, 100],
                ticktext=["25", "50", "75", "100"],
                tickfont=dict(size=8, color=SECONDARY_COL),
                gridcolor="#B9B2A6", gridwidth=1, linecolor="#B9B2A6",
            ),
            angularaxis=dict(
                tickfont=dict(size=8, color=SECONDARY_COL),
                gridcolor="#B9B2A6", gridwidth=1, linecolor="#B9B2A6",
            ),
        ),
        showlegend=True,
        legend=dict(x=0.5, y=-0.10, xanchor="center", orientation="h",
                    font=dict(size=10, color=SECONDARY_COL)),
        margin=dict(l=70, r=70, t=30, b=42),
        paper_bgcolor=CARD_BG,
    )
    return fig


def _fig_sp_breakdown(pct_scores: list, color: str) -> go.Figure:
    rev    = list(reversed(pct_scores))
    labels = [d[0] for d in rev]
    values = [d[1] for d in rev]

    r, g, b  = _rgb(color)
    bar_cols = [f"rgba({r},{g},{b},{0.35 + 0.55 * v / 100:.2f})" for v in values]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        orientation="h",
        x=values, y=labels,
        marker_color=bar_cols,
        text=[f"{v:.0f}" for v in values],
        textposition="outside",
        textfont=dict(size=10, color=SECONDARY_COL),
        hovertemplate="<b>%{y}</b>: %{x:.1f}th pct<extra></extra>",
        cliponaxis=False,
    ))
    fig.add_vline(x=50, line=dict(color="#AAAAAA", width=1.2, dash="dot"))
    fig.update_layout(
        xaxis=dict(range=[0, 115], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False,
                   tickfont=dict(size=10, color=SECONDARY_COL)),
        margin=dict(l=5, r=8, t=4, b=4),
        paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG,
        showlegend=False, bargap=0.25,
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Main layout builder
# ══════════════════════════════════════════════════════════════════════════════

def build_set_piece_layout(code: str) -> html.Div:
    td    = TEAM_DATA.get(code, {})
    color = td.get("bg", "#333333")

    df_team = _team_df(code)
    if df_team.empty:
        return html.Div("No set piece data available.",
                        style={"padding": "16px", "color": TEXT_MUTED})

    corner_sum = _summarise_corners(df_team)
    fk_sum     = _summarise_fk_box(df_team)
    lt_sum     = _summarise_longthrows(df_team)

    def _pitch_graph(fig, row_h):
        return _graph(fig, int(row_h * _PITCH_H_FRAC))

    def _col2_two_tables(cap1, tbl1, cap2, tbl2, row_h):
        tbl_h = int(row_h * 0.44)
        return html.Div([
            _cap(cap1), _sortable(tbl1, list(tbl1.columns)[2] if tbl1 is not None and not tbl1.empty else "#", tbl_h),
            _cap(cap2), _sortable(tbl2, list(tbl2.columns)[2] if tbl2 is not None and not tbl2.empty else "#", tbl_h),
        ], style={"display": "flex", "flexDirection": "column", "overflow": "hidden"})

    def _col2_one_table(cap, tbl, row_h, sort_col=None, ascending=False):
        sc = sort_col if sort_col is not None else (list(tbl.columns)[1] if tbl is not None and not tbl.empty else "#")
        return html.Div([
            _cap(cap),
            _sortable(tbl, sc, int(row_h * 0.88), ascending=ascending),
        ], style={"display": "flex", "flexDirection": "column", "overflow": "hidden"})

    # ── Row 1 — Left Side Corners ─────────────────────────────────────────────
    row1 = _row_wrap(
        "Left Side Corners (Deliver into Box)",
        _two_col(
            _pitch_graph(_fig_corners_box(corner_sum, "left", df_team), _R1_H),
            _col2_two_tables(
                "Corner Takers",    _tbl_corner_takers(corner_sum, "left"),
                "Corner Receivers", _tbl_corner_receivers(corner_sum, df_team, "left"),
                _R1_H,
            ),
            _R1_H,
        ),
    )

    # ── Row 2 — Right Side Corners ───────────────────────────────────────────
    row2 = _row_wrap(
        "Right Side Corners (Deliver into Box)",
        _two_col(
            _pitch_graph(_fig_corners_box(corner_sum, "right", df_team), _R2_H),
            _col2_two_tables(
                "Corner Takers",    _tbl_corner_takers(corner_sum, "right"),
                "Corner Receivers", _tbl_corner_receivers(corner_sum, df_team, "right"),
                _R2_H,
            ),
            _R2_H,
        ),
    )

    # ── Row 3 — Other Corner Sequences ───────────────────────────────────────
    row3 = _row_wrap(
        "Other Corner Sequences",
        _two_col(
            _pitch_graph(_fig_other_corners(df_team, corner_sum), _R3_H),
            _col2_one_table("Next Action after Corner",
                            _tbl_other_corners(df_team, corner_sum), _R3_H),
            _R3_H,
        ),
    )

    # ── Row 4 — Free Kicks into Box ──────────────────────────────────────────
    row4 = _row_wrap(
        "Free Kicks (Deliver into Box)",
        _two_col(
            _pitch_graph(_fig_fk_box(fk_sum, df_team), _R4_H),
            _col2_two_tables(
                "FK Takers",    _tbl_fk_takers(fk_sum),
                "FK Receivers", _tbl_fk_receivers(fk_sum, df_team),
                _R4_H,
            ),
            _R4_H,
        ),
    )

    # ── Row 5 — Short / Other FK Sequences ──────────────────────────────────
    row5 = _row_wrap(
        "Other Free Kick Sequences",
        _two_col(
            _pitch_graph(_fig_short_fk(df_team), _R5_H),
            _col2_one_table("Next Action after FK",
                            _tbl_short_fk_next(df_team), _R5_H),
            _R5_H,
        ),
    )

    # ── Row 6 — Direct FK & Penalties (pitch + shooters table + goalpost panels)
    _df_d_raw = df_team[df_team["sp_type"] == "dfk_pk"].copy()
    if not _df_d_raw.empty:
        _df_d_raw["_is_pen"] = _df_d_raw["Penalty"].fillna("") == "Si"
        _pk_shots  = _df_d_raw[_df_d_raw["_is_pen"]]
        _dfk_shots = _df_d_raw[~_df_d_raw["_is_pen"]]
    else:
        _pk_shots = _dfk_shots = _df_d_raw

    _tbl_h6 = int(_R6_H * 0.26)
    _row6_right = html.Div([
        _cap("Penalty Takers"),
        _sortable(_tbl_pk_takers(df_team),  "Goals", _tbl_h6),
        _cap("DFK Takers"),
        _sortable(_tbl_dfk_takers(df_team), "Goals", _tbl_h6),
        html.Div([
            html.Div([
                _cap("Penalty Kicks"),
                _graph(_fig_goalpost_shots(_pk_shots,  _C_FK),   _R6_GP_H),
            ], style={"width": "50%", "boxSizing": "border-box", "paddingRight": "2px"}),
            html.Div([
                _cap("Direct Free Kicks"),
                _graph(_fig_goalpost_shots(_dfk_shots, _C_GOLD), _R6_GP_H),
            ], style={"width": "50%", "boxSizing": "border-box", "paddingLeft": "2px"}),
        ], style={"display": "flex", "flexShrink": "0", "marginTop": "3px"}),
    ], style={
        "width": "40%", "flexShrink": "0", "minWidth": "0",
        "boxSizing": "border-box", "display": "flex",
        "flexDirection": "column", "overflow": "hidden",
    })

    row6 = _row_wrap(
        "Direct Free Kicks & Penalty Kicks",
        html.Div([
            html.Div(
                _pitch_graph(_fig_dfk_pk(df_team), _R6_H),
                style={"width": "60%", "flexShrink": "0", "minWidth": "0",
                       "boxSizing": "border-box"},
            ),
            _row6_right,
        ], style={"display": "flex", "height": f"{_R6_H}px"}),
    )

    # ── Row 7 — Long Throw-ins ────────────────────────────────────────────────
    row7 = _row_wrap(
        "Long Throw Ins",
        _two_col(
            _pitch_graph(_fig_longthrow(lt_sum, df_team), _R7_H),
            _col2_two_tables(
                "Throwers",   _tbl_lt_takers(lt_sum),
                "Receivers",  _tbl_lt_receivers(lt_sum, df_team),
                _R7_H,
            ),
            _R7_H,
        ),
    )

    # ── Row 0 — Set Piece Radar + Breakdown ──────────────────────────────────
    sp_pct   = _sp_percentile_scores(code, _load_sp())
    graph_h0 = _R0_H - 28
    row0 = _row_wrap(
        "Set Piece Profile",
        html.Div([
            html.Div([
                _cap("Set Piece Radar"),
                _graph(_fig_sp_radar(sp_pct, code, color), graph_h0),
            ], style={"width": "42%", "flexShrink": "0", "boxSizing": "border-box",
                      "padding": "0 3px", "display": "flex", "flexDirection": "column"}),
            html.Div([
                _cap("Breakdown"),
                _graph(_fig_sp_breakdown(sp_pct, color), graph_h0),
            ], style={"width": "58%", "flexShrink": "0", "boxSizing": "border-box",
                      "padding": "0 3px", "display": "flex", "flexDirection": "column"}),
        ], style={"display": "flex", "height": f"{_R0_H}px"}),
    )

    return html.Div(
        [row0, row1, row2, row3, row4, row5, row6, row7],
        style={"backgroundColor": BG_COLOUR, "padding": "4px"},
    )
