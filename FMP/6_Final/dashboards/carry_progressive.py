"""
Progressive CARRIES, mirroring the progressive-PASS logic in match_analysis.py.

Drop-in: call build_carry_df(df1) right after the pass_df block. It uses the
same constants and the same maths (lines ~255-290 of match_analysis.py), with
the carry's start/end substituted for the pass's start / Pass End X/Y.

Carry definition:
  - a SUCCESSFUL take-on (event == 'Take On' & outcome == 1)
  - carry end = the SAME player's next event (x, y) in feed order, within
    `max_gap_sec` (skips the opponent's tackle/challenge that sits in between).

progressive == 1  <=>  carry_type == 'Forward'  AND  distance-to-goal reduced
>= min_reduction_pct  (default 5; the pass version uses 10).
"""
import numpy as np

# Import the SAME constants the pass code uses:
#   from utils.constants import GOAL_X, GOAL_Y, MAX_DIST
# Fallbacks below are Opta's attacking goal in raw 0-100 coords.
try:
    from utils.constants import GOAL_X, GOAL_Y, MAX_DIST
except Exception:
    GOAL_X, GOAL_Y, MAX_DIST = 100.0, 50.0, float(np.hypot(100, 50))


def build_carry_df(df1, max_gap_sec=5, min_reduction_pct=5,
                   GOAL_X=GOAL_X, GOAL_Y=GOAL_Y, MAX_DIST=MAX_DIST):
    """df1 must be in the feed's natural (chronological) order, like pass_df."""
    d = df1.reset_index(drop=True)
    d['_abs'] = d['time_min'] * 60 + d['time_sec']

    # --- carry end coordinate = next same-player event ---
    n = len(d)
    end_x = np.full(n, np.nan); end_y = np.full(n, np.nan)
    pid = d['player_id'].values; per = d['period_id'].values
    abss = d['_abs'].values;     xv = d['x'].values; yv = d['y'].values
    to_idx = np.where((d['event'].values == 'Take On') & (d['outcome'].values == 1))[0]
    for i in to_idx:
        for j in range(i + 1, n):
            if per[j] != per[i]:                  break
            if abss[j] - abss[i] > max_gap_sec:   break
            if pid[j] == pid[i]:
                end_x[i], end_y[i] = xv[j], yv[j]; break

    carry = d.loc[to_idx].copy()
    carry['carry_end_x'] = end_x[to_idx]
    carry['carry_end_y'] = end_y[to_idx]
    carry = carry[carry['carry_end_x'].notna()].copy()   # keep only resolved carries

    # --- identical to the pass block, start/end swapped for the carry ---
    carry['plot_x']     = carry['x']           * 105 / 100
    carry['plot_y']     = carry['y']           * 68  / 100
    carry['plot_end_x'] = carry['carry_end_x'] * 105 / 100
    carry['plot_end_y'] = carry['carry_end_y'] * 68  / 100

    dx = carry['plot_end_x'] - carry['plot_x']
    dy = carry['plot_end_y'] - carry['plot_y']
    carry['carry_angle'] = (np.degrees(np.arctan2(dy, dx)) + 360) % 360

    a = carry['carry_angle']
    conditions = [
        (a >= 300) | (a <= 60),
        ((a > 60) & (a <= 90))  | ((a >= 270) & (a < 300)),
        ((a > 90) & (a <= 120)) | ((a >= 240) & (a < 270)),
        (a > 120) & (a < 240),
    ]
    choices = ['Forward', 'Sideway Forward', 'Sideway Backward', 'Backward']
    carry['carry_type'] = np.select(conditions, choices, default='')
    carry['carry_type'] = carry['carry_type'].replace('', np.nan)

    carry['ori_dist_to_goal'] = np.sqrt((carry['x']           - GOAL_X) ** 2 +
                                        (carry['y']           - GOAL_Y) ** 2)
    carry['fin_dist_to_goal'] = np.sqrt((carry['carry_end_x'] - GOAL_X) ** 2 +
                                        (carry['carry_end_y'] - GOAL_Y) ** 2)

    reduction_pct = ((carry['ori_dist_to_goal'] - carry['fin_dist_to_goal'])
                     / carry['ori_dist_to_goal']) * 100
    is_progressive = (carry['carry_type'] == 'Forward') & (reduction_pct >= min_reduction_pct)
    carry['progressive'] = is_progressive.astype(int)
    carry['dist_threat'] = (1 - (carry['ori_dist_to_goal'] / MAX_DIST)).round(2)
    return carry.reset_index(drop=True)
