#!/usr/bin/env python3
"""
laliga_stats.py
===============
Calculate team and individual player statistics from a season's worth of
LaLiga match event files (Opta / Stats Perform F24-style event data), where
each CSV looks like:

    PRD_20260208_ATM_BET_2d48hhckok4yi8bluy55trf2s.csv

Drop all 380 match CSVs into a folder and run:

    python laliga_stats.py --input ./matches --output ./out

It produces four CSV files in the output folder:

    player_stats_season.csv   one row per player / team / position-slot
    team_stats_season.csv     one row per team, aggregated over all matches
    team_stats_per_match.csv  one row per team per match (long format)
    player_stats_per_match.csv one row per player per match per position-slot

------------------------------------------------------------------------------
PLAYER STATS GRAIN
------------------------------------------------------------------------------
Player rows are identified by the Opta-native columns
    week, match_id, team_code, Jersey Number, player_id,
    Team Formation, Team Player Formation
so a player is split per match AND per position-slot (Team Player Formation).
A player who changes formation slot mid-match — or whose team changes shape —
produces one row per slot, with minutes and stats attributed to each. The
Opta 'Team Formation' / 'Team Player Formation' fields are used rather than the
'formation' / 'position' columns, which can come from a wrong mapping.

------------------------------------------------------------------------------
DATA NOTES (how this feed is structured)
------------------------------------------------------------------------------
* Each row is one *event* (a pass, shot, tackle, card, etc.).
* `type_id` identifies the event kind (Opta codes, see TYPE_* constants below).
* `outcome` is 1 for a "successful" event, 0 otherwise. Its meaning depends on
  the event type (a successful pass reached a team-mate; a successful tackle
  won the ball; foul outcome 1 = foul won, 0 = foul committed; etc.).
* Coordinates `x`,`y` are on a 0-100 pitch (attacking left->right per event).
* The many trailing columns are *qualifiers*. A qualifier is "present" on an
  event when its cell is non-empty (usually the string "Si"). We treat any
  non-null / non-empty value as "qualifier present".
* The `Assist` column on a pass holds the type_id of the shot it created:
      16 -> the pass assisted a GOAL          (=> an assist)
      13/14/15 -> the pass created a shot      (=> a chance created / key pass)
* Own goals carry the `own goal` qualifier and are credited to the opponent.

Everything here is computed defensively: missing columns are tolerated so the
script keeps working if a particular file omits some qualifier columns.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from typing import Dict, List

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Opta event type_id constants
# ---------------------------------------------------------------------------
TYPE_PASS = 1
TYPE_OFFSIDE_PASS = 2
TYPE_TAKE_ON = 3          # dribble; outcome 1 = beat opponent
TYPE_FOUL = 4             # outcome 1 = foul won, 0 = foul committed
TYPE_CORNER_AWARDED = 6
TYPE_TACKLE = 7           # outcome 1 = won possession
TYPE_INTERCEPTION = 8
TYPE_SAVE = 10            # goalkeeper save
TYPE_CLAIM = 11
TYPE_CLEARANCE = 12
TYPE_MISS = 13           # shot off target
TYPE_POST = 14           # shot hit woodwork
TYPE_SAVED_SHOT = 15     # shot on target, saved/blocked
TYPE_GOAL = 16
TYPE_CARD = 17
TYPE_PLAYER_OFF = 18
TYPE_PLAYER_ON = 19
TYPE_TEAM_SET_UP = 34    # lineup / formation declaration (not a real action)
TYPE_FORMATION_CHANGE = 40  # in-match formation/slot reassignment
TYPE_AERIAL = 44         # outcome 1 = aerial duel won
TYPE_CHALLENGE = 45      # 50/50 challenge for the ball
TYPE_BALL_RECOVERY = 49
TYPE_DISPOSSESSED = 50
TYPE_ERROR = 51
TYPE_KEEPER_PICKUP = 52
TYPE_BALL_TOUCH = 61     # outcome 0 = bad touch / miscontrol
TYPE_BLOCKED_PASS = 74

SHOT_TYPES = {TYPE_MISS, TYPE_POST, TYPE_SAVED_SHOT, TYPE_GOAL}
SHOT_ON_TARGET_TYPES = {TYPE_SAVED_SHOT, TYPE_GOAL}
# Events that are real on-ball actions (exclude administrative markers)
NON_ACTION_TYPES = {TYPE_TEAM_SET_UP, 30, 32, 37, 40, 27, 28, 70}

# Metre-scaled pitch dimensions (Opta x/y are 0-100; multiply by these /100
# to get real-world metres). Used throughout for distance/geometry logic.
PITCH_LEN_M, PITCH_WID_M = 105.0, 68.0

# Defensive-action event set used for team def_actions counts and player stats.
DEF_ACTION_TYPES = {TYPE_BALL_RECOVERY, TYPE_BLOCKED_PASS, TYPE_CHALLENGE,
                    TYPE_FOUL, TYPE_INTERCEPTION, TYPE_TACKLE}

# PPDA-specific defensive action set — mirrors match_analysis.py's _DEF_EVT:
# ['Ball recovery', 'Blocked Pass', 'Challenge', 'Clearance', 'Interception', 'Tackle']
# Clearance replaces Foul so the calculation matches the per-match dashboard.
PPDA_DEF_ACTION_TYPES = {TYPE_BALL_RECOVERY, TYPE_BLOCKED_PASS, TYPE_CHALLENGE,
                         TYPE_CLEARANCE, TYPE_INTERCEPTION, TYPE_TACKLE}

# GK pass distance thresholds (metres), per match_analysis.py's fig_gk_pass:
# short < 25, medium in [25,40], long > 40.
GK_SHORT_THRESHOLD_M = 25
GK_LONG_THRESHOLD_M = 40

# Cross origin channel thresholds, on a 0-68 (metre) pitch-width scale.
WIDE_Y_LOW, WIDE_Y_HIGH = 68 / 6, 68 * 5 / 6        # wide channel: y<11.33 or y>56.67
HS_LOW1, HS_HIGH1 = 68 / 6, 68 / 3                  # half-space band 1: 11.33-22.67
HS_LOW2, HS_HIGH2 = 68 * 2 / 3, 68 * 5 / 6          # half-space band 2: 45.33-56.67

# PPDA x-thresholds — mirrors match_analysis.py: own-half boundary at x=50.
# Opponent passes: x <= 50 (all passes, not just completed, in their own half).
# Own defensive actions: x > 50 (pressing actions in the opponent's half).
PPDA_OPP_PASS_X_MAX = 50     # opponent passes (all) with x <= 50 (their own half)
PPDA_DEF_ACTION_X_MIN = 50   # own defensive actions with x > 50 (opponent's half)

# ---------------------------------------------------------------------------
# Set-piece zone geometry, on the metre-scaled (105 x 68) attacking pitch with
# the attacking goal at x=105, centre line at y=34. Boundaries as specified:
#   short corner:    y < 34-20.16 (taken from the left) or y > 34+20.16 (right)
#   6-yard box mid:  x > 105-5.5  and  28.5 <= y <= 39.5
#   penalty spot:    88.5 <= x <= 99.5  and  28.5 <= y <= 39.5
#   front/far post:  remaining in-box deliveries, split by which post (near
#                    side of y=34 relative to the corner's own taken-from side)
#                    the end point lands nearer to
#   edge of box:     remaining deliveries that land around / outside the box
# ---------------------------------------------------------------------------
SP_BOX_X0 = PITCH_LEN_M - 16.5        # 88.5 — penalty box front edge
SP_SIXYD_X0 = PITCH_LEN_M - 5.5       # 99.5 — six-yard box front edge
SP_BOX_Y0, SP_BOX_Y1 = 34 - 20.16, 34 + 20.16     # 13.84 / 54.16 — box width
SP_SIXYD_Y0, SP_SIXYD_Y1 = 34 - 5.5, 34 + 5.5     # 28.5 / 39.5 — six-yard width
SP_GOAL_Y = 34.0


def _sp_meters(g: pd.DataFrame):
    """Origin/end coordinates of every row, in metres on the 105x68 pitch."""
    x = num(g, "x") * (PITCH_LEN_M / 100.0)
    y = num(g, "y") * (PITCH_WID_M / 100.0)
    ex = num(g, "Pass End X") * (PITCH_LEN_M / 100.0)
    ey = num(g, "Pass End Y") * (PITCH_WID_M / 100.0)
    return x, y, ex, ey


SP_SHORT_CORNER_DIST_M = 25.0   # short corner: delivery travels < 25m...
SP_SHORT_CORNER_END_X = SP_BOX_X0  # ...OR doesn't even reach the penalty box


def _corner_zone(x0: pd.Series, y0: pd.Series, ex: pd.Series, ey: pd.Series) -> pd.Series:
    """6-way corner end-zone, vectorised: short, six_yard_box, penalty_spot,
    front_post, far_post, edge_of_box (or NaN if no end point).

    x0/y0 = the corner's own ORIGIN coordinates. y0 decides which post counts
    as "near"/front for that corner's taken-from side. "Short" is judged from
    the DELIVERY itself (travel distance and/or end point not reaching the
    box) -- a corner's origin is always at the flag, so origin y can never be
    used to detect a short corner.
    """
    has_end = ex.notna() & ey.notna()
    dist = np.sqrt((ex - x0) ** 2 + (ey - y0) ** 2)
    short = has_end & ((dist < SP_SHORT_CORNER_DIST_M) | (ex < SP_SHORT_CORNER_END_X))

    in_six_y = ey.between(SP_SIXYD_Y0, SP_SIXYD_Y1)
    in_box_y = ey.between(SP_BOX_Y0, SP_BOX_Y1)
    six_yard_box = (ex > SP_SIXYD_X0) & in_six_y
    penalty_spot = ex.between(SP_BOX_X0, SP_SIXYD_X0) & in_six_y
    in_box_other = (ex > SP_BOX_X0) & in_box_y & ~six_yard_box & ~penalty_spot
    edge_of_box = ~short & ~six_yard_box & ~penalty_spot & ~in_box_other & has_end

    # Front post = the end point sits on the SAME side of the goal-mouth
    # (y=34) as the corner was taken from; far post = the opposite side.
    near_side_low = y0 < SP_GOAL_Y           # corner taken from the "low-y" flag
    front = np.where(near_side_low, ey < SP_GOAL_Y, ey >= SP_GOAL_Y)

    zone = pd.Series(np.where(has_end, np.nan, np.nan), index=ex.index, dtype="object")
    zone = zone.mask(has_end & short, "short")
    zone = zone.mask(zone.isna() & six_yard_box, "six_yard_box")
    zone = zone.mask(zone.isna() & penalty_spot, "penalty_spot")
    zone = zone.mask(zone.isna() & in_box_other & front, "front_post")
    zone = zone.mask(zone.isna() & in_box_other & ~front, "far_post")
    zone = zone.mask(zone.isna() & edge_of_box, "edge_of_box")
    return zone


def classify_set_pieces(g: pd.DataFrame) -> pd.DataFrame:
    """Tag every event-row with set-piece attributes (g-indexed columns):

      sp_type        'corner' | 'free_kick' | 'throw_in' | NaN
      sp_side        'left' | 'right'  (taken-from side, corners & throw-ins)
      sp_swing       'inswing' | 'outswing' | 'straight'  (corners; foot-based
                     fallback for free kicks when no swing qualifier is set)
      corner_zone    6-way end zone (corners only) — see _corner_zone
      is_direct_fk_shot   shot taken directly from a free kick (no pass in between)
      is_fk_cross_box     free-kick PASS whose end point lands inside the box
      is_throwin_box      throw-in PASS whose end point lands inside the box

    Side convention: 'left' = taken from the y<34 (near y=0) side of the
    pitch when attacking towards x=105; 'right' = the y>34 (near y=68) side.
    """
    g = g.copy()
    x, y, ex, ey = _sp_meters(g)
    is_pass = g["type_id"] == TYPE_PASS

    is_corner = is_pass & qualifier_present(g, "Corner taken")
    is_fk_pass = is_pass & qualifier_present(g, "Free kick taken")
    is_throwin = is_pass & qualifier_present(g, "Throw In")

    sp_type = pd.Series(np.select(
        [is_corner, is_fk_pass, is_throwin],
        ["corner", "free_kick", "throw_in"], default=None), index=g.index, dtype="object")

    # Side: corners/throw-ins are taken from a touchline, so origin y tells us
    # which side. y<34 -> 'left', y>=34 -> 'right' (attacking towards x=105).
    side = np.where(y < SP_GOAL_Y, "left", "right")
    sp_side = pd.Series(np.where(sp_type.isin(["corner", "throw_in"]), side, None),
                        index=g.index, dtype="object")

    inswing = qualifier_present(g, "Inswinger")
    outswing = qualifier_present(g, "Outswinger")
    straight = qualifier_present(g, "Straight")
    swing = pd.Series(np.select(
        [inswing, outswing, straight], ["inswing", "outswing", "straight"], default=None),
        index=g.index, dtype="object")
    # Fallback for corners with no explicit swing qualifier: infer from
    # kicking foot + side (right-footed from the left, or left-footed from
    # the right, curls the ball IN towards goal = inswinger; the converse
    # foot/side pairing curls it away = outswinger).
    rfoot = qualifier_present(g, "Right footed")
    lfoot = qualifier_present(g, "Left footed")
    inferred_in = ((side == "left") & rfoot) | ((side == "right") & lfoot)
    inferred_out = ((side == "left") & lfoot) | ((side == "right") & rfoot)
    swing = swing.mask(swing.isna() & is_corner & inferred_in, "inswing")
    swing = swing.mask(swing.isna() & is_corner & inferred_out, "outswing")
    sp_swing = swing.where(sp_type.isin(["corner", "free_kick"]))

    corner_zone = _corner_zone(x.where(is_corner), y.where(is_corner), ex, ey).where(is_corner)

    # Direct free-kick shot: a shot event (not a pass) carrying the
    # 'Free kick taken' qualifier -- i.e. the free kick itself was the shot.
    is_shot = g["type_id"].isin(SHOT_TYPES)
    is_direct_fk_shot = is_shot & qualifier_present(g, "Free kick taken")

    in_box = ex.between(SP_BOX_X0, PITCH_LEN_M) & ey.between(SP_BOX_Y0, SP_BOX_Y1)
    is_fk_cross_box = is_fk_pass & in_box
    is_throwin_box = is_throwin & in_box

    return pd.DataFrame({
        "sp_type": sp_type, "sp_side": sp_side, "sp_swing": sp_swing,
        "corner_zone": corner_zone,
        "is_direct_fk_shot": is_direct_fk_shot.fillna(False),
        "is_fk_cross_box": is_fk_cross_box.fillna(False),
        "is_throwin_box": is_throwin_box.fillna(False),
    }, index=g.index)


# Events that hand the opponent clear, controlled possession -- used to decide
# when a set-piece SEQUENCE has been "interrupted by the opponent team."
OPPONENT_GAIN_TYPES = {
    TYPE_TACKLE, TYPE_INTERCEPTION, TYPE_CLEARANCE, TYPE_SAVE, TYPE_CLAIM,
    TYPE_KEEPER_PICKUP, TYPE_BALL_RECOVERY,
}
SEQUENCE_DEAD_TYPES = {5}   # 'Out' -- ball is dead


def set_piece_sequence_outcomes(g: pd.DataFrame) -> pd.DataFrame:
    """For every set-piece delivery (corner / free-kick pass / throw-in into
    the box), determine whether it leads to a shot/goal, two ways:

      direct_to_shot / direct_to_goal:
          the delivery itself is the pass annotated as leading to a shot, via
          Opta's own 'Assist' qualifier on the pass (Assist == a shot type_id,
          or == TYPE_GOAL). This is the single ball-playing action; no chain
          walking needed since Opta already links it.

      sequence_to_shot / sequence_to_goal:
          starting at the set-piece event, walk forward through subsequent
          rows (chronological row order) while the ball stays with the taking
          team (their own events, or neutral/dead-ball events) and stop at the
          first of: (a) a shot/goal by the taking team -> success: True,
                    (b) an OPPONENT_GAIN_TYPES event by the opponent -> failure,
                    (c) a SEQUENCE_DEAD_TYPES event (ball out of play, no
                        resulting shot) -> failure,
                    (d) reaching another set-piece / restart -> failure.
          An opponent event that is itself a contest (Aerial/Challenge/Tackle/
          Take On) but FAILED (outcome != 1) does not end the sequence -- the
          ball is still live/contested, not cleanly won by the opponent.

    Returns a DataFrame indexed like g's set-piece rows (one row per
    set-piece event) with columns: sp_type, direct_to_shot, direct_to_goal,
    sequence_to_shot, sequence_to_goal.
    """
    g = g.reset_index(drop=True)
    sp = classify_set_pieces(g)
    sp_idx = sp.index[sp["sp_type"].notna()]  # delivery rows: corner/FK-pass/throw-in

    assist_to = num(g, "Assist")
    direct_to_shot = assist_to.loc[sp_idx].isin(list(SHOT_TYPES)).to_numpy()
    direct_to_goal = (assist_to.loc[sp_idx] == TYPE_GOAL).to_numpy()

    seq_shot, seq_goal = [], []
    contestant = g["contestant_id"].to_numpy()
    type_id = g["type_id"].to_numpy()
    outcome = g["outcome"].to_numpy()
    # Contest-type events where a FAILED outcome (0) means the player did NOT
    # win the ball -- so the sequence isn't actually interrupted by them.
    CONTEST_TYPES = {TYPE_AERIAL, TYPE_CHALLENGE, TYPE_TACKLE, TYPE_TAKE_ON}
    n = len(g)
    for i in sp_idx:
        team = contestant[i]
        shot_found = goal_found = False
        for j in range(i + 1, n):
            tid_j, t_j, out_j = contestant[j], type_id[j], outcome[j]
            if tid_j == team:
                if t_j in SHOT_TYPES:
                    shot_found = True
                    if t_j == TYPE_GOAL:
                        goal_found = True
                    break
                if t_j in (TYPE_CORNER_AWARDED, TYPE_TEAM_SET_UP, TYPE_FORMATION_CHANGE):
                    break
                continue  # own team keeps the ball -- sequence continues
            else:
                if t_j in CONTEST_TYPES and out_j != 1:
                    # opponent contested but did NOT win it -- ball still live
                    continue
                if t_j in OPPONENT_GAIN_TYPES:
                    break
                if t_j in SEQUENCE_DEAD_TYPES:
                    break
                if t_j in (TYPE_PLAYER_OFF, TYPE_PLAYER_ON, TYPE_CARD, 43):
                    continue  # administrative / deleted event, doesn't touch the ball
                # Any other opponent on-ball action (pass, take-on, etc.)
                # means the opponent has the ball -> sequence over.
                break
        seq_shot.append(shot_found)
        seq_goal.append(goal_found)

    out = pd.DataFrame({
        "sp_type": sp.loc[sp_idx, "sp_type"].to_numpy(),
        "direct_to_shot": direct_to_shot,
        "direct_to_goal": direct_to_goal,
        "sequence_to_shot": seq_shot,
        "sequence_to_goal": seq_goal,
    }, index=sp_idx)
    return out

# Progressive-action geometry (Opta coords are 0-100, single attacking direction
# toward x=100). Definition mirrors match_analysis.py: a *forward* move that
# brings the ball >= 10% closer to the attacking goal.
GOAL_X, GOAL_Y = 100.0, 50.0
PROG_REDUCTION_PCT = 10.0
CARRY_MAX_GAP_SEC = 15.0   # max time linking a take-on to the player's next touch


def _dist_to_goal(x: pd.Series, y: pd.Series) -> pd.Series:
    return np.sqrt((x - GOAL_X) ** 2 + (y - GOAL_Y) ** 2)


def _is_forward(x, y, ex, ey) -> pd.Series:
    """Forward = end point within +/-60 deg of straight toward goal.

    Angle computed on metric-scaled deltas (x*1.05, y*0.68) exactly as the
    pass_type classification in match_analysis.py.
    """
    dx = (ex - x) * 1.05
    dy = (ey - y) * 0.68
    ang = (np.degrees(np.arctan2(dy, dx)) + 360) % 360
    return (ang >= 300) | (ang <= 60)


def _progressive(x, y, ex, ey) -> pd.Series:
    """True where moving (x,y)->(ex,ey) is forward and >=10% closer to goal."""
    ori = _dist_to_goal(x, y)
    fin = _dist_to_goal(ex, ey)
    red = (ori - fin) / ori.replace(0, np.nan) * 100
    prog = _is_forward(x, y, ex, ey) & (red >= PROG_REDUCTION_PCT)
    return (prog & ex.notna() & ey.notna()).fillna(False).astype(bool)


def _progressive_pass_mask(g: pd.DataFrame) -> pd.Series:
    """g-indexed bool: completed passes that are progressive."""
    x, y = num(g, "x"), num(g, "y")
    ex, ey = num(g, "Pass End X"), num(g, "Pass End Y")
    completed = (g["type_id"] == TYPE_PASS) & (g["outcome"] == 1)
    return (completed & _progressive(x, y, ex, ey)).fillna(False).astype(bool)


def _progressive_takeon_mask(g: pd.DataFrame) -> pd.Series:
    """g-indexed bool: successful take-ons whose follow-up carry is progressive.

    A take-on has no end coordinate, so the carry endpoint is the same player's
    next touch (within CARRY_MAX_GAP_SEC, to avoid linking across a turnover).
    """
    a = g[g["player_id"].notna()].copy()
    if a.empty:
        return pd.Series(False, index=g.index)
    x, y = num(a, "x"), num(a, "y")
    abs_sec = num(a, "time_min").fillna(0) * 60 + num(a, "time_sec").fillna(0)
    a = a.assign(_x=x, _y=y, _t=abs_sec)
    nx = a.groupby("player_id")["_x"].shift(-1)
    ny = a.groupby("player_id")["_y"].shift(-1)
    gap = a.groupby("player_id")["_t"].shift(-1) - a["_t"]
    mask = (
        (a["type_id"] == TYPE_TAKE_ON) & (a["outcome"] == 1)
        & _progressive(x, y, nx, ny) & gap.between(0, CARRY_MAX_GAP_SEC)
    )
    return mask.reindex(g.index, fill_value=False).fillna(False).astype(bool)



# ---------------------------------------------------------------------------
# Helpers for the "Si"-style qualifier columns
# ---------------------------------------------------------------------------
def qualifier_present(df: pd.DataFrame, col: str) -> pd.Series:
    """Boolean Series: True where the qualifier column has a real value.

    Cells may be "Si", a number, or an id string; blanks/NaN/empty mean absent.
    Returns an all-False series if the column does not exist in this file.
    """
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    s = df[col]
    present = s.notna()
    # Treat empty strings and a literal "0" / "nan" as "not present".
    as_str = s.astype("string").str.strip().str.lower()
    present &= ~as_str.isin(["", "0", "nan", "none", "n/a"])
    return present.fillna(False).astype(bool)


def num(df: pd.DataFrame, col: str) -> pd.Series:
    """Numeric view of a column (NaN where missing/blank); 0-length-safe."""
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[col], errors="coerce")


# ---------------------------------------------------------------------------
# Per-match computation
# ---------------------------------------------------------------------------
def _parse_aligned_slots(rq) -> List[tuple]:
    """Parse 'Involved' + 'Team Player Formation' aligned lists from a
    Team-set-up / Formation-change qualifier string.

    Returns [(player_id, slot), ...] for slots != 0 (i.e. the 11 on the pitch).
    """
    inv = re.search(r"Involved:\s*(.*?)(?:;|$)", str(rq))
    tpf = re.search(r"Team Player Formation:\s*(.*?)(?:;|$)", str(rq))
    if not (inv and tpf):
        return []
    pids = [p.strip() for p in inv.group(1).split(",")]
    slots = [s.strip() for s in tpf.group(1).split(",")]
    out = []
    for pid, s in zip(pids, slots):
        try:
            sv = int(float(s))
        except (ValueError, TypeError):
            continue
        if sv != 0 and pid:
            out.append((pid, sv))
    return out


def _reconstruct_slots(g: pd.DataFrame) -> pd.DataFrame:
    """Stamp the correct (Team Formation, Team Player Formation) onto every event.

    The per-event 'Team Player Formation' column is unreliable for substitutes
    (often 0 or stale). Following player_minutes_formations.py, each player's slot
    is taken from:
      * Team set up  -> starters' slots (parsed 'Team Player Formation' list),
      * Player on    -> the 'Formation slot' qualifier,
      * Formation change -> reassigned slots (parsed list),
    and held from that moment until the next change. Each event is then assigned
    the slot in force at its timestamp (cumulative match time).
    """
    g = g.copy()
    abs_sec = (num(g, "time_min").fillna(0) * 60 + num(g, "time_sec").fillna(0))
    g["_abs_sec"] = abs_sec

    rows = []  # (player_id, eff_sec, tf, slot, prio)  prio orders ties
    for _, r in g[g.type_id == TYPE_TEAM_SET_UP].iterrows():
        tf = r.get("Team Formation")
        for pid, slot in _parse_aligned_slots(r.get("represented_qualifiers")):
            rows.append((pid, 0.0, tf, slot, 0))
    for _, r in g[g.type_id == TYPE_FORMATION_CHANGE].iterrows():
        tf = r.get("Team Formation")
        for pid, slot in _parse_aligned_slots(r.get("represented_qualifiers")):
            rows.append((pid, float(r["_abs_sec"]), tf, slot, 1))
    for _, r in g[g.type_id == TYPE_PLAYER_ON].iterrows():
        m = re.search(r"Formation slot:\s*(\d+)", str(r.get("represented_qualifiers")))
        if m and pd.notna(r.get("player_id")):
            rows.append((r["player_id"], float(r["_abs_sec"]),
                         r.get("Team Formation"), int(m.group(1)), 2))

    if not rows:
        return g.drop(columns=["_abs_sec"])

    # Sort so that, at equal timestamps, a 'Player on' slot wins over a
    # simultaneous formation change (matches the reference's ordering).
    adf = (pd.DataFrame(rows, columns=["player_id", "eff_sec", "tf", "slot", "prio"])
           .sort_values(["eff_sec", "prio"]).reset_index(drop=True))
    adf["player_id"] = adf["player_id"].astype(str)
    adf["eff_sec"] = adf["eff_sec"].astype(float)
    adf = adf.sort_values("eff_sec", kind="stable")

    ev = g.reset_index()[["index", "player_id", "_abs_sec"]].dropna(subset=["player_id"]).copy()
    ev["player_id"] = ev["player_id"].astype(str)
    ev["_abs_sec"] = ev["_abs_sec"].astype(float)
    ev = ev.sort_values("_abs_sec", kind="stable")
    merged = pd.merge_asof(ev, adf, left_on="_abs_sec", right_on="eff_sec",
                           by="player_id", direction="backward")

    ok = merged["slot"].notna()
    ridx = merged.loc[ok, "index"].to_numpy()
    g.loc[ridx, "Team Player Formation"] = merged.loc[ok, "slot"].to_numpy()
    g.loc[ridx, "Team Formation"] = merged.loc[ok, "tf"].to_numpy()
    return g.drop(columns=["_abs_sec"])


def _match_end_minute(g: pd.DataFrame) -> int:
    """Best-effort full-time minute for the match (max event minute)."""
    try:
        return int(num(g, "time_min").max())
    except (ValueError, TypeError):
        return 90


def _team_lookup(g: pd.DataFrame) -> Dict[str, dict]:
    """Map contestant_id -> {team_name, team_code, opponent_id}."""
    info = (g[["contestant_id", "team_name", "team_code"]]
            .dropna(subset=["contestant_id"])
            .drop_duplicates("contestant_id"))
    ids = info["contestant_id"].tolist()
    out = {}
    for _, r in info.iterrows():
        opp = [i for i in ids if i != r["contestant_id"]]
        out[r["contestant_id"]] = {
            "team_name": r["team_name"],
            "team_code": r["team_code"],
            "opponent_id": opp[0] if opp else None,
        }
    return out


def _goal_credits(g: pd.DataFrame, teams: Dict[str, dict]):
    """Return (team_goals_for, scorer_goals, own_goals_by_player).

    Own goals count toward the opponent's 'goals_for' and are NOT credited as
    a goal to the scorer (tracked separately as own_goals).
    """
    team_goals = {tid: 0 for tid in teams}
    scorer_goals: Dict[str, int] = {}
    own_goals: Dict[str, int] = {}

    goals = g[g.type_id == TYPE_GOAL]
    og_flag = qualifier_present(g, "own goal")
    for idx, r in goals.iterrows():
        tid = r["contestant_id"]
        pid = r["player_id"]
        if og_flag.get(idx, False):
            opp = teams.get(tid, {}).get("opponent_id")
            if opp in team_goals:
                team_goals[opp] += 1
            if pd.notna(pid):
                own_goals[pid] = own_goals.get(pid, 0) + 1
        else:
            if tid in team_goals:
                team_goals[tid] += 1
            if pd.notna(pid):
                scorer_goals[pid] = scorer_goals.get(pid, 0) + 1
    return team_goals, scorer_goals, own_goals


# Columns that identify a player-segment row (per match, per player, per
# position). Team Formation / Team Player Formation are Opta-native fields and
# are preferred over the (possibly mis-mapped) 'formation' / 'position' columns.
PLAYER_ID_COLS = [
    "week", "match_id", "team_code", "Jersey Number", "player_id",
    "Team Formation", "Team Player Formation",
]


def _segment_minutes(g: pd.DataFrame, end_min: int) -> pd.DataFrame:
    """Minutes played per (player_id, Team Formation, Team Player Formation).

    A player's pitch time (sub-on -> sub-off, or 0 -> full-time for a starter)
    is split across the formation slots they occupied. Slot boundaries are taken
    from the moment the per-event 'Team Player Formation' value changes, so no
    qualifier-string parsing is needed.
    """
    a = g[g.player_id.notna()].copy()
    a["abs_sec"] = (pd.to_numeric(a.get("time_sec"), errors="coerce").fillna(0)
                    + pd.to_numeric(a.get("time_min"), errors="coerce").fillna(0) * 60)
    end_sec = end_min * 60

    on = (g[g.type_id == TYPE_PLAYER_ON].dropna(subset=["player_id"]).copy())
    on["abs_sec"] = (pd.to_numeric(on.get("time_sec"), errors="coerce").fillna(0)
                     + pd.to_numeric(on.get("time_min"), errors="coerce").fillna(0) * 60)
    on_map = on.groupby("player_id")["abs_sec"].min().to_dict()
    off = (g[g.type_id == TYPE_PLAYER_OFF].dropna(subset=["player_id"]).copy())
    off["abs_sec"] = (pd.to_numeric(off.get("time_sec"), errors="coerce").fillna(0)
                      + pd.to_numeric(off.get("time_min"), errors="coerce").fillna(0) * 60)
    off_map = off.groupby("player_id")["abs_sec"].min().to_dict()

    # Only events that carry a real slot define on-pitch presence
    a = a[a["Team Player Formation"].notna() & (a.type_id != TYPE_TEAM_SET_UP)]

    rows = []
    for pid, pe in a.groupby("player_id"):
        pe = pe.sort_values("abs_sec")
        start = float(on_map.get(pid, 0))
        end = float(off_map.get(pid, end_sec))
        # Build contiguous slot runs along the event timeline
        keys = list(zip(pe["Team Formation"], pe["Team Player Formation"]))
        times = pe["abs_sec"].tolist()
        seg_start = start
        cur_key = keys[0]
        durations: Dict[tuple, float] = {}
        for i in range(1, len(keys)):
            if keys[i] != cur_key:
                boundary = times[i]
                durations[cur_key] = durations.get(cur_key, 0.0) + max(boundary - seg_start, 0)
                seg_start = boundary
                cur_key = keys[i]
        durations[cur_key] = durations.get(cur_key, 0.0) + max(end - seg_start, 0)
        for (tf, tpf), secs in durations.items():
            rows.append({"player_id": pid, "Team Formation": tf,
                         "Team Player Formation": tpf,
                         "minutes_played": round(secs / 60, 1)})
    return pd.DataFrame(rows, columns=["player_id", "Team Formation",
                                       "Team Player Formation", "minutes_played"])


# ----- the core per-player-per-position aggregation for a single match -------
def _player_event_stats(g: pd.DataFrame) -> pd.DataFrame:
    """One row per (match, player, position-slot) with raw counting stats.

    Grouped by PLAYER_ID_COLS so a player who switches formation slot mid-match
    produces a separate row per slot.
    """
    a = g[g.player_id.notna()].copy()
    a["is_pass"] = a.type_id == TYPE_PASS
    a["pass_ok"] = (a.type_id == TYPE_PASS) & (a.outcome == 1)
    a["is_shot"] = a.type_id.isin(SHOT_TYPES)
    a["shot_on_target"] = a.type_id.isin(SHOT_ON_TARGET_TYPES)
    a["take_on"] = a.type_id == TYPE_TAKE_ON
    a["take_on_ok"] = (a.type_id == TYPE_TAKE_ON) & (a.outcome == 1)
    a["tackle"] = a.type_id == TYPE_TACKLE
    a["tackle_ok"] = (a.type_id == TYPE_TACKLE) & (a.outcome == 1)
    a["interception"] = a.type_id == TYPE_INTERCEPTION
    a["clearance"] = a.type_id == TYPE_CLEARANCE
    a["recovery"] = a.type_id == TYPE_BALL_RECOVERY
    a["dispossessed"] = a.type_id == TYPE_DISPOSSESSED
    a["error"] = a.type_id == TYPE_ERROR
    a["save"] = a.type_id == TYPE_SAVE
    a["aerial"] = a.type_id == TYPE_AERIAL
    a["aerial_ok"] = (a.type_id == TYPE_AERIAL) & (a.outcome == 1)
    a["offside"] = a.type_id == TYPE_OFFSIDE_PASS
    a["fouls_won"] = (a.type_id == TYPE_FOUL) & (a.outcome == 1)
    a["fouls_committed"] = (a.type_id == TYPE_FOUL) & (a.outcome == 0)

    # Qualifier-derived flags
    pres = lambda c: qualifier_present(g, c).reindex(a.index, fill_value=False)
    a["yellow"] = (a.type_id == TYPE_CARD) & pres("Yellow Card")
    a["second_yellow"] = (a.type_id == TYPE_CARD) & qualifier_present(g, "Second yellow").reindex(a.index, fill_value=False)
    a["red"] = (a.type_id == TYPE_CARD) & (
        qualifier_present(g, "Red Card").reindex(a.index, fill_value=False)
        | a["second_yellow"]
    )
    a["cross"] = a["is_pass"] & pres("Cross")
    a["long_ball"] = a["is_pass"] & pres("Long ball")
    a["through_ball"] = a["is_pass"] & pres("Through ball")

    # Assist column on a pass = the type of shot it produced
    assist_to = num(g, "Assist").reindex(a.index)
    a["assist"] = a["is_pass"] & (assist_to == TYPE_GOAL)
    a["chance_created"] = a["is_pass"] & assist_to.isin(list(SHOT_TYPES))
    a["pen_won"] = (a.type_id == TYPE_FOUL) & (a.outcome == 1) & pres("Penalty")

    # Goals credited to the scorer's segment; own goals tracked separately
    og = qualifier_present(g, "own goal").reindex(a.index, fill_value=False)
    a["goal"] = (a.type_id == TYPE_GOAL) & (~og)
    a["own_goal"] = (a.type_id == TYPE_GOAL) & og

    # Fast-break involvement at player level (shots taken on a fast break)
    fb = qualifier_present(g, "Fast break").reindex(a.index, fill_value=False)
    a["fast_break_shot"] = a["is_shot"] & fb

    # Progressive passes (completed) & progressive take-on carries (successful).
    a["progressive_pass"] = _progressive_pass_mask(g).reindex(a.index, fill_value=False)
    a["progressive_pass_opp_half"] = (
        a["progressive_pass"] & (num(g, "Pass End X") > 50).reindex(a.index, fill_value=False)
    )
    a["progressive_take_on"] = _progressive_takeon_mask(g).reindex(a.index, fill_value=False)

    # --- Set pieces -----------------------------------------------------------
    sp = classify_set_pieces(g).reindex(a.index)
    a["corner_taken"] = sp["sp_type"] == "corner"
    a["corner_left"] = a["corner_taken"] & (sp["sp_side"] == "left")
    a["corner_right"] = a["corner_taken"] & (sp["sp_side"] == "right")
    a["corner_inswing"] = a["corner_taken"] & (sp["sp_swing"] == "inswing")
    a["corner_outswing"] = a["corner_taken"] & (sp["sp_swing"] == "outswing")
    a["corner_short"] = a["corner_taken"] & (sp["corner_zone"] == "short")
    a["corner_six_yard_box"] = a["corner_taken"] & (sp["corner_zone"] == "six_yard_box")
    a["corner_penalty_spot"] = a["corner_taken"] & (sp["corner_zone"] == "penalty_spot")
    a["corner_front_post"] = a["corner_taken"] & (sp["corner_zone"] == "front_post")
    a["corner_far_post"] = a["corner_taken"] & (sp["corner_zone"] == "far_post")
    a["corner_edge_of_box"] = a["corner_taken"] & (sp["corner_zone"] == "edge_of_box")

    a["fk_taken"] = sp["sp_type"] == "free_kick"
    a["fk_inswing"] = a["fk_taken"] & (sp["sp_swing"] == "inswing")
    a["fk_outswing"] = a["fk_taken"] & (sp["sp_swing"] == "outswing")
    a["fk_direct_shot"] = sp["is_direct_fk_shot"].fillna(False)
    a["fk_cross_box"] = sp["is_fk_cross_box"].fillna(False)

    a["throwin_taken"] = sp["sp_type"] == "throw_in"
    a["throwin_left"] = a["throwin_taken"] & (sp["sp_side"] == "left")
    a["throwin_right"] = a["throwin_taken"] & (sp["sp_side"] == "right")
    a["throwin_box"] = sp["is_throwin_box"].fillna(False)

    sp_out = set_piece_sequence_outcomes(g).reindex(a.index)
    a["sp_direct_to_shot"] = sp_out["direct_to_shot"].fillna(False)
    a["sp_direct_to_goal"] = sp_out["direct_to_goal"].fillna(False)
    a["sp_sequence_to_shot"] = sp_out["sequence_to_shot"].fillna(False)
    a["sp_sequence_to_goal"] = sp_out["sequence_to_goal"].fillna(False)

    keys = PLAYER_ID_COLS
    agg = a.groupby(keys, dropna=False).agg(
        player_name=("player_name", "first"),
        contestant_id=("contestant_id", "first"),
        team_name=("team_name", "first"),
        events=("type_id", "size"),
        goals=("goal", "sum"),
        own_goals=("own_goal", "sum"),
        assists=("assist", "sum"),
        chances_created=("chance_created", "sum"),
        shots=("is_shot", "sum"),
        shots_on_target=("shot_on_target", "sum"),
        fast_break_shots=("fast_break_shot", "sum"),
        passes=("is_pass", "sum"),
        passes_completed=("pass_ok", "sum"),
        progressive_passes=("progressive_pass", "sum"),
        progressive_passes_opp_half=("progressive_pass_opp_half", "sum"),
        crosses=("cross", "sum"),
        long_balls=("long_ball", "sum"),
        through_balls=("through_ball", "sum"),
        take_ons=("take_on", "sum"),
        take_ons_won=("take_on_ok", "sum"),
        progressive_take_ons=("progressive_take_on", "sum"),
        tackles=("tackle", "sum"),
        tackles_won=("tackle_ok", "sum"),
        interceptions=("interception", "sum"),
        clearances=("clearance", "sum"),
        recoveries=("recovery", "sum"),
        dispossessed=("dispossessed", "sum"),
        errors=("error", "sum"),
        saves=("save", "sum"),
        aerials=("aerial", "sum"),
        aerials_won=("aerial_ok", "sum"),
        offsides=("offside", "sum"),
        fouls_won=("fouls_won", "sum"),
        fouls_committed=("fouls_committed", "sum"),
        penalties_won=("pen_won", "sum"),
        yellow_cards=("yellow", "sum"),
        red_cards=("red", "sum"),
        corners_taken=("corner_taken", "sum"),
        corners_left=("corner_left", "sum"),
        corners_right=("corner_right", "sum"),
        corners_inswing=("corner_inswing", "sum"),
        corners_outswing=("corner_outswing", "sum"),
        corners_short=("corner_short", "sum"),
        corners_six_yard_box=("corner_six_yard_box", "sum"),
        corners_penalty_spot=("corner_penalty_spot", "sum"),
        corners_front_post=("corner_front_post", "sum"),
        corners_far_post=("corner_far_post", "sum"),
        corners_edge_of_box=("corner_edge_of_box", "sum"),
        fk_taken=("fk_taken", "sum"),
        fk_inswing=("fk_inswing", "sum"),
        fk_outswing=("fk_outswing", "sum"),
        fk_direct_shots=("fk_direct_shot", "sum"),
        fk_crosses_box=("fk_cross_box", "sum"),
        throwins_taken=("throwin_taken", "sum"),
        throwins_left=("throwin_left", "sum"),
        throwins_right=("throwin_right", "sum"),
        throwins_box=("throwin_box", "sum"),
        sp_direct_to_shot=("sp_direct_to_shot", "sum"),
        sp_direct_to_goal=("sp_direct_to_goal", "sum"),
        sp_sequence_to_shot=("sp_sequence_to_shot", "sum"),
        sp_sequence_to_goal=("sp_sequence_to_goal", "sum"),
    )
    return agg.reset_index()


def _gk_pass_distance_m(g: pd.DataFrame) -> pd.Series:
    """Straight-line GK pass distance in metres, scaled to a 105x68 pitch.

    g-indexed Series, NaN where not a GK pass with valid end coordinates.
    Mirrors match_analysis.py's fig_gk_pass distance formula (the box-relative
    axis rotation there is distance-preserving, so plain Euclidean distance on
    metre-scaled x/y gives the identical magnitude).
    """
    is_gk_pass = (g["type_id"] == TYPE_PASS) & (g.get("position") == "GK")
    x = num(g, "x") * (PITCH_LEN_M / 100.0)
    y = num(g, "y") * (PITCH_WID_M / 100.0)
    ex = num(g, "Pass End X") * (PITCH_LEN_M / 100.0)
    ey = num(g, "Pass End Y") * (PITCH_WID_M / 100.0)
    dist = np.sqrt((ex - x) ** 2 + (ey - y) ** 2)
    return dist.where(is_gk_pass & ex.notna() & ey.notna())


def _team_extra_stats(g: pd.DataFrame, teams: Dict[str, dict]) -> Dict[str, dict]:
    """Per-team season-style counts that need cross-team (PPDA) or pitch-zone
    logic: gk_short, gk_long, crosses_wide, crosses_hs, ball_recoveries,
    def_actions, set-piece counts/outcomes, plus the season PPDA's two raw
    ingredients (opp_passes_def_third, def_actions_high_third) for later
    season division.
    """
    gk_dist = _gk_pass_distance_m(g)
    y68 = num(g, "y") * (PITCH_WID_M / 100.0)
    in_wide_y = (y68 < WIDE_Y_LOW) | (y68 > WIDE_Y_HIGH)
    in_hs_y   = ((y68 >= HS_LOW1) & (y68 <= HS_HIGH1)) | ((y68 >= HS_LOW2) & (y68 <= HS_HIGH2))
    is_def_action = g["type_id"].isin(DEF_ACTION_TYPES)
    is_ppda_def = g["type_id"].isin(PPDA_DEF_ACTION_TYPES)
    x100 = num(g, "x")
    all_passes = g["type_id"] == TYPE_PASS
    passes_completed = all_passes & (g["outcome"] == 1)

    # Open-play cross detection — mirrors dashboard._cross_df:
    # pass from attacking-half wide/HS zone whose end point enters the box,
    # excluding set pieces. Consistent with the per-match "Avg" benchmark bars.
    _ex_m = num(g, "Pass End X") * (PITCH_LEN_M / 100.0)
    _ey_m = num(g, "Pass End Y") * (PITCH_WID_M / 100.0)
    _is_sp = (qualifier_present(g, "Corner taken")
              | qualifier_present(g, "Free kick taken")
              | qualifier_present(g, "Throw In"))
    _open_play_to_box = (all_passes & ~_is_sp
                         & (_ex_m > SP_BOX_X0)
                         & _ey_m.between(SP_BOX_Y0, SP_BOX_Y1))
    in_wide_orig = (x100 > 50.0)              & in_wide_y
    in_hs_orig   = (x100 > 200.0 / 3)         & in_hs_y   # final third ≈ x > 66.7

    sp = classify_set_pieces(g)
    is_corner = sp["sp_type"] == "corner"
    is_fk = sp["sp_type"] == "free_kick"
    is_throwin = sp["sp_type"] == "throw_in"
    sp_out = set_piece_sequence_outcomes(g)  # indexed by the delivery rows only

    out = {}
    for tid, meta in teams.items():
        tev_mask = g["contestant_id"] == tid
        sp_out_team = sp_out[g.loc[sp_out.index, "contestant_id"] == tid]
        out[tid] = {
            "gk_short": int(((gk_dist < GK_SHORT_THRESHOLD_M) & tev_mask).sum()),
            "gk_long": int(((gk_dist > GK_LONG_THRESHOLD_M) & tev_mask).sum()),
            "crosses_wide": int((_open_play_to_box & in_wide_orig & tev_mask).sum()),
            "crosses_hs": int((_open_play_to_box & in_hs_orig & tev_mask).sum()),
            "ball_recoveries": int(((g["type_id"] == TYPE_BALL_RECOVERY) & tev_mask).sum()),
            "def_actions": int((is_def_action & tev_mask).sum()),
            # PPDA ingredients — mirrors match_analysis.py per-match logic.
            # Own pressing actions (Clearance included) in the opponent's half (x>50).
            "def_actions_high": int((is_ppda_def & tev_mask & (x100 > PPDA_DEF_ACTION_X_MIN)).sum()),
            # All passes (not just completed) by this team in their own half (x<=50).
            # Used as the numerator when the OPPONENT reads this team's opp_passes_def_third.
            "opp_passes_def_third": int((all_passes & tev_mask & (x100 <= PPDA_OPP_PASS_X_MAX)).sum()),
            # --- set pieces ---
            "corners_taken": int((is_corner & tev_mask).sum()),
            "corners_left": int((is_corner & tev_mask & (sp["sp_side"] == "left")).sum()),
            "corners_right": int((is_corner & tev_mask & (sp["sp_side"] == "right")).sum()),
            "corners_inswing": int((is_corner & tev_mask & (sp["sp_swing"] == "inswing")).sum()),
            "corners_outswing": int((is_corner & tev_mask & (sp["sp_swing"] == "outswing")).sum()),
            "corners_short": int((is_corner & tev_mask & (sp["corner_zone"] == "short")).sum()),
            "corners_six_yard_box": int((is_corner & tev_mask & (sp["corner_zone"] == "six_yard_box")).sum()),
            "corners_penalty_spot": int((is_corner & tev_mask & (sp["corner_zone"] == "penalty_spot")).sum()),
            "corners_front_post": int((is_corner & tev_mask & (sp["corner_zone"] == "front_post")).sum()),
            "corners_far_post": int((is_corner & tev_mask & (sp["corner_zone"] == "far_post")).sum()),
            "corners_edge_of_box": int((is_corner & tev_mask & (sp["corner_zone"] == "edge_of_box")).sum()),
            "fk_taken": int((is_fk & tev_mask).sum()),
            "fk_inswing": int((is_fk & tev_mask & (sp["sp_swing"] == "inswing")).sum()),
            "fk_outswing": int((is_fk & tev_mask & (sp["sp_swing"] == "outswing")).sum()),
            "fk_direct_shots": int((sp["is_direct_fk_shot"] & tev_mask).sum()),
            "fk_crosses_box": int((sp["is_fk_cross_box"] & tev_mask).sum()),
            "throwins_taken": int((is_throwin & tev_mask).sum()),
            "throwins_left": int((is_throwin & tev_mask & (sp["sp_side"] == "left")).sum()),
            "throwins_right": int((is_throwin & tev_mask & (sp["sp_side"] == "right")).sum()),
            "throwins_box": int((sp["is_throwin_box"] & tev_mask).sum()),
            "sp_direct_to_shot": int(sp_out_team["direct_to_shot"].sum()),
            "sp_direct_to_goal": int(sp_out_team["direct_to_goal"].sum()),
            "sp_sequence_to_shot": int(sp_out_team["sequence_to_shot"].sum()),
            "sp_sequence_to_goal": int(sp_out_team["sequence_to_goal"].sum()),
        }
    return out


def process_match(g: pd.DataFrame, match_id: str):
    """Return (player_df, team_df) of per-match stats for one match group."""
    g = _reconstruct_slots(g)   # fix Team Player Formation for subs/starters
    teams = _team_lookup(g)
    end_min = _match_end_minute(g)

    # --- player stats: one row per (match, player, position-slot) ---
    pstats = _player_event_stats(g)
    minutes = _segment_minutes(g, end_min)
    pstats = pstats.merge(
        minutes, on=["player_id", "Team Formation", "Team Player Formation"], how="left")
    pstats["minutes_played"] = pstats["minutes_played"].fillna(0.0)
    # Order: identifying columns first, then a few headline stats
    head = PLAYER_ID_COLS + ["player_name", "team_name", "contestant_id",
                             "minutes_played", "goals", "assists"]
    pstats = pstats[head + [c for c in pstats.columns if c not in head]]

    # --- team stats ---
    team_goals, _scorer, _og = _goal_credits(g, teams)
    fb_flag = qualifier_present(g, "Fast break")
    prog_pass_flag = _progressive_pass_mask(g)
    prog_takeon_flag = _progressive_takeon_mask(g)
    extra = _team_extra_stats(g, teams)
    team_rows = []
    for tid, meta in teams.items():
        tev = g[g.contestant_id == tid]
        opp = meta["opponent_id"]
        gf = team_goals.get(tid, 0)
        ga = team_goals.get(opp, 0) if opp else 0
        result = "W" if gf > ga else ("L" if gf < ga else "D")
        passes = int((tev.type_id == TYPE_PASS).sum())
        passes_ok = int(((tev.type_id == TYPE_PASS) & (tev.outcome == 1)).sum())
        shots = int(tev.type_id.isin(SHOT_TYPES).sum())
        sot = int(tev.type_id.isin(SHOT_ON_TARGET_TYPES).sum())
        # Fast-break sequences = shots taken on a fast break (Opta 'Fast break'
        # qualifier on a Goal / Miss / Post / Saved Shot), per match_analysis.py.
        tfb = fb_flag.reindex(tev.index, fill_value=False)
        fb_shots = tev.type_id.isin(SHOT_TYPES) & tfb
        fast_break_seq = int(fb_shots.sum())
        fast_break_goals = int(((tev.type_id == TYPE_GOAL) & tfb).sum())
        fast_break_sot = int(((tev.type_id.isin(SHOT_ON_TARGET_TYPES)) & tfb).sum())
        team_rows.append({
            "match_id": match_id,
            "contestant_id": tid,
            "team_name": meta["team_name"],
            "team_code": meta["team_code"],
            "opponent": teams.get(opp, {}).get("team_name") if opp else None,
            "is_home": (tev["team_position"].dropna().iloc[0] == "home")
                        if "team_position" in tev and tev["team_position"].notna().any() else np.nan,
            "goals_for": gf,
            "goals_against": ga,
            "result": result,
            "win": int(result == "W"),
            "draw": int(result == "D"),
            "loss": int(result == "L"),
            "points": 3 if result == "W" else (1 if result == "D" else 0),
            "clean_sheet": int(ga == 0),
            "passes": passes,
            "passes_completed": passes_ok,
            "progressive_passes": int(prog_pass_flag.reindex(tev.index, fill_value=False).sum()),
            "progressive_passes_opp_half": int(
                (prog_pass_flag & (num(g, "Pass End X") > 50))
                .reindex(tev.index, fill_value=False).sum()
            ),
            "progressive_take_ons": int(prog_takeon_flag.reindex(tev.index, fill_value=False).sum()),
            "shots": shots,
            "shots_on_target": sot,
            "fast_break_seq": fast_break_seq,
            "fast_break_shots_on_target": fast_break_sot,
            "fast_break_goals": fast_break_goals,
            "corners": int((tev.type_id == TYPE_CORNER_AWARDED).sum()),
            "offsides": int((tev.type_id == TYPE_OFFSIDE_PASS).sum()),
            "tackles": int((tev.type_id == TYPE_TACKLE).sum()),
            "interceptions": int((tev.type_id == TYPE_INTERCEPTION).sum()),
            "clearances": int((tev.type_id == TYPE_CLEARANCE).sum()),
            "saves": int((tev.type_id == TYPE_SAVE).sum()),
            "fouls_committed": int(((tev.type_id == TYPE_FOUL) & (tev.outcome == 0)).sum()),
            "fouls_won": int(((tev.type_id == TYPE_FOUL) & (tev.outcome == 1)).sum()),
            "yellow_cards": int(((tev.type_id == TYPE_CARD) & qualifier_present(g, "Yellow Card").reindex(tev.index, fill_value=False)).sum()),
            "red_cards": int(((tev.type_id == TYPE_CARD) & (qualifier_present(g, "Red Card") | qualifier_present(g, "Second yellow")).reindex(tev.index, fill_value=False)).sum()),
            "gk_short": extra[tid]["gk_short"],
            "gk_long": extra[tid]["gk_long"],
            "crosses_wide": extra[tid]["crosses_wide"],
            "crosses_hs": extra[tid]["crosses_hs"],
            "ball_recoveries": extra[tid]["ball_recoveries"],
            "def_actions": extra[tid]["def_actions"],
            "corners_taken": extra[tid]["corners_taken"],
            "corners_left": extra[tid]["corners_left"],
            "corners_right": extra[tid]["corners_right"],
            "corners_inswing": extra[tid]["corners_inswing"],
            "corners_outswing": extra[tid]["corners_outswing"],
            "corners_short": extra[tid]["corners_short"],
            "corners_six_yard_box": extra[tid]["corners_six_yard_box"],
            "corners_penalty_spot": extra[tid]["corners_penalty_spot"],
            "corners_front_post": extra[tid]["corners_front_post"],
            "corners_far_post": extra[tid]["corners_far_post"],
            "corners_edge_of_box": extra[tid]["corners_edge_of_box"],
            "fk_taken": extra[tid]["fk_taken"],
            "fk_inswing": extra[tid]["fk_inswing"],
            "fk_outswing": extra[tid]["fk_outswing"],
            "fk_direct_shots": extra[tid]["fk_direct_shots"],
            "fk_crosses_box": extra[tid]["fk_crosses_box"],
            "throwins_taken": extra[tid]["throwins_taken"],
            "throwins_left": extra[tid]["throwins_left"],
            "throwins_right": extra[tid]["throwins_right"],
            "throwins_box": extra[tid]["throwins_box"],
            "sp_direct_to_shot": extra[tid]["sp_direct_to_shot"],
            "sp_direct_to_goal": extra[tid]["sp_direct_to_goal"],
            "sp_sequence_to_shot": extra[tid]["sp_sequence_to_shot"],
            "sp_sequence_to_goal": extra[tid]["sp_sequence_to_goal"],
            # Per-match PPDA = opponent's all-passes in their own half / own
            # pressing actions in opponent's half. Mirrors match_analysis.py.
            "ppda": (round(_opp_pm / extra[tid]["def_actions_high"], 2)
                     if (_opp_pm := extra.get(opp, {}).get("opp_passes_def_third", 0) if opp else 0)
                     and extra[tid]["def_actions_high"] else np.nan),
            # Raw ingredients kept for season-level PPDA (sum then divide once).
            "_def_actions_high": extra[tid]["def_actions_high"],
            "_opp_passes_def_third": extra.get(opp, {}).get("opp_passes_def_third", 0) if opp else 0,
        })
    team_df = pd.DataFrame(team_rows)

    # Possession proxy = share of total completed passes in the match
    total_ok = team_df["passes_completed"].sum()
    team_df["possession_pct"] = (
        (team_df["passes_completed"] / total_ok * 100).round(1) if total_ok else np.nan
    )
    return pstats, team_df


# ---------------------------------------------------------------------------
# Season aggregation
# ---------------------------------------------------------------------------
PLAYER_SUM_COLS = [
    "minutes_played", "events",
    "goals", "own_goals", "assists", "chances_created",
    "shots", "shots_on_target", "fast_break_shots",
    "passes", "passes_completed", "progressive_passes", "progressive_passes_opp_half",
    "crosses", "long_balls", "through_balls",
    "take_ons", "take_ons_won", "progressive_take_ons",
    "tackles", "tackles_won", "interceptions",
    "clearances", "recoveries", "dispossessed", "errors", "saves",
    "aerials", "aerials_won", "offsides", "fouls_won", "fouls_committed",
    "penalties_won", "yellow_cards", "red_cards",
    "corners_taken", "corners_left", "corners_right",
    "corners_inswing", "corners_outswing",
    "corners_short", "corners_six_yard_box", "corners_penalty_spot",
    "corners_front_post", "corners_far_post", "corners_edge_of_box",
    "fk_taken", "fk_inswing", "fk_outswing", "fk_direct_shots", "fk_crosses_box",
    "throwins_taken", "throwins_left", "throwins_right", "throwins_box",
    "sp_direct_to_shot", "sp_direct_to_goal",
    "sp_sequence_to_shot", "sp_sequence_to_goal",
]

# Season grain for players: per player, per team, per position slot. Mirrors the
# per-match identifying columns (minus week/match_id) so a player's output is
# split by the clubs and formation slots they actually occupied.
PLAYER_SEASON_KEYS = ["player_id", "team_code", "contestant_id",
                      "Team Formation", "Team Player Formation"]


def aggregate_players(per_match: pd.DataFrame) -> pd.DataFrame:
    for c in PLAYER_SUM_COLS:
        if c not in per_match:
            per_match[c] = 0
    season = (per_match.groupby(PLAYER_SEASON_KEYS, dropna=False)
              .agg({**{c: "sum" for c in PLAYER_SUM_COLS},
                    "match_id": "nunique",
                    "player_name": "last",
                    "team_name": "first",
                    "Jersey Number": lambda s: s.dropna().mode().iat[0] if not s.dropna().empty else np.nan})
              .rename(columns={"match_id": "matches"})
              .reset_index())
    season["pass_accuracy_pct"] = np.where(
        season["passes"] > 0, (season["passes_completed"] / season["passes"] * 100).round(1), 0.0)
    season["shot_accuracy_pct"] = np.where(
        season["shots"] > 0, (season["shots_on_target"] / season["shots"] * 100).round(1), 0.0)
    season["tackle_success_pct"] = np.where(
        season["tackles"] > 0, (season["tackles_won"] / season["tackles"] * 100).round(1), 0.0)
    season["take_on_success_pct"] = np.where(
        season["take_ons"] > 0, (season["take_ons_won"] / season["take_ons"] * 100).round(1), 0.0)
    season["goals_per90"] = np.where(
        season["minutes_played"] > 0, (season["goals"] / season["minutes_played"] * 90).round(2), 0.0)
    season["goal_contributions"] = season["goals"] + season["assists"]
    season["minutes_played"] = season["minutes_played"].round(1)

    front = ["player_id", "player_name", "team_code", "contestant_id",
             "Team Formation", "Team Player Formation", "Jersey Number",
             "matches", "minutes_played", "goals", "assists", "goal_contributions"]
    cols = front + [c for c in season.columns if c not in front]
    return (season[cols]
            .sort_values(["goals", "assists", "minutes_played"], ascending=False)
            .reset_index(drop=True))


TEAM_SUM_COLS = [
    "win", "draw", "loss", "points", "clean_sheet",
    "goals_for", "goals_against", "passes", "passes_completed",
    "progressive_passes", "progressive_passes_opp_half", "progressive_take_ons",
    "shots", "shots_on_target",
    "fast_break_seq", "fast_break_shots_on_target", "fast_break_goals",
    "corners", "offsides", "tackles",
    "interceptions", "clearances", "saves", "fouls_committed", "fouls_won",
    "yellow_cards", "red_cards",
    "gk_short", "gk_long", "crosses_wide", "crosses_hs",
    "ball_recoveries", "def_actions",
    "corners_taken", "corners_left", "corners_right",
    "corners_inswing", "corners_outswing",
    "corners_short", "corners_six_yard_box", "corners_penalty_spot",
    "corners_front_post", "corners_far_post", "corners_edge_of_box",
    "fk_taken", "fk_inswing", "fk_outswing", "fk_direct_shots", "fk_crosses_box",
    "throwins_taken", "throwins_left", "throwins_right", "throwins_box",
    "sp_direct_to_shot", "sp_direct_to_goal",
    "sp_sequence_to_shot", "sp_sequence_to_goal",
    "_def_actions_high", "_opp_passes_def_third",
]


def aggregate_teams(per_match: pd.DataFrame) -> pd.DataFrame:
    season = (per_match.groupby(["contestant_id"])
              .agg({**{c: "sum" for c in TEAM_SUM_COLS},
                    "team_name": "first", "team_code": "first",
                    "match_id": "nunique"})
              .rename(columns={"match_id": "matches"})
              .reset_index())
    season["goal_difference"] = season["goals_for"] - season["goals_against"]
    season["pass_accuracy_pct"] = np.where(
        season["passes"] > 0, (season["passes_completed"] / season["passes"] * 100).round(1), 0.0)
    season["shot_accuracy_pct"] = np.where(
        season["shots"] > 0, (season["shots_on_target"] / season["shots"] * 100).round(1), 0.0)
    season["goals_per_match"] = (season["goals_for"] / season["matches"]).round(2)

    # Season PPDA = season_total(opponent all-passes, x<=50) / season_total(own
    # pressing actions, x>50). Summed first, divided once — not an average of
    # per-match PPDA values. Matches match_analysis.py per-match logic.
    season["ppda"] = np.where(
        season["_def_actions_high"] > 0,
        (season["_opp_passes_def_third"] / season["_def_actions_high"]).round(2),
        np.nan,
    )
    season = season.drop(columns=["_def_actions_high", "_opp_passes_def_third"])

    front = ["contestant_id", "team_name", "team_code", "matches", "points",
             "win", "draw", "loss", "goals_for", "goals_against",
             "goal_difference", "clean_sheet"]
    cols = front + [c for c in season.columns if c not in front]
    return (season[cols]
            .sort_values(["points", "goal_difference", "goals_for"], ascending=False)
            .reset_index(drop=True))


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def load_and_process(paths: List[str]):
    all_players, all_teams = [], []
    for i, path in enumerate(paths, 1):
        try:
            df = pd.read_csv(path, low_memory=False)
        except Exception as e:  # noqa: BLE001
            print(f"  [skip] {os.path.basename(path)}: {e}", file=sys.stderr)
            continue
        if "match_id" not in df.columns or "type_id" not in df.columns:
            print(f"  [skip] {os.path.basename(path)}: missing required columns", file=sys.stderr)
            continue
        df["type_id"] = pd.to_numeric(df["type_id"], errors="coerce")
        df["outcome"] = pd.to_numeric(df.get("outcome"), errors="coerce")
        df["time_min"] = pd.to_numeric(df.get("time_min"), errors="coerce")
        for mid, g in df.groupby("match_id"):
            p, t = process_match(g, str(mid))
            all_players.append(p)
            all_teams.append(t)
        if i % 25 == 0 or i == len(paths):
            print(f"  processed {i}/{len(paths)} files...")

    if not all_players:
        raise SystemExit("No valid match data found.")
    players_pm = pd.concat(all_players, ignore_index=True)
    teams_pm = pd.concat(all_teams, ignore_index=True)
    return players_pm, teams_pm


def main():
    ap = argparse.ArgumentParser(description="Compute LaLiga team & player stats from match event CSVs.")
    ap.add_argument("--input", "-i", default="2_Data/LaLiga", help="Folder containing the match CSV files.")
    ap.add_argument("--output", "-o", default="./out", help="Folder to write result CSVs.")
    ap.add_argument("--pattern", "-p", default="*.csv", help="Glob pattern for match files (default *.csv).")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.input, args.pattern)))
    if not paths:
        raise SystemExit(f"No files matching {args.pattern!r} in {args.input!r}")
    print(f"Found {len(paths)} file(s) in {args.input!r}")

    players_pm, teams_pm = load_and_process(paths)
    player_season = aggregate_players(players_pm)
    team_season = aggregate_teams(teams_pm)

    os.makedirs(args.output, exist_ok=True)
    out = {
        "player_stats_season.csv": player_season,
        "team_stats_season.csv": team_season,
        "team_stats_per_match.csv": teams_pm,
        "player_stats_per_match.csv": players_pm,
    }
    for name, frame in out.items():
        dest = os.path.join(args.output, name)
        frame.to_csv(dest, index=False)
        print(f"  wrote {dest}  ({len(frame)} rows)")

    print("\nTop scorers:")
    print(player_season[["player_name", "team_name", "matches", "goals", "assists"]]
          .head(10).to_string(index=False))
    print("\nTeam table:")
    print(team_season[["team_name", "matches", "points", "goals_for", "goals_against", "goal_difference"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
