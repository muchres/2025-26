import pandas as pd
import json

df = pd.read_json("2043670_tracking_extrapolated.jsonl", lines=True)

df_home_possession = df[(df['possession'].apply(lambda x: x['group'] == 'home team')) & (df['period'] == 1)]

from collections import defaultdict

player_stats = defaultdict(lambda: {'x_total': 0, 'y_total': 0, 'count': 0})

for player_list in df_home_possession['player_data']:
    for player in player_list:
        pid = player['player_id']
        player_stats[pid]['x_total'] += player['x']
        player_stats[pid]['y_total'] += player['y']
        player_stats[pid]['count'] += 1

rows = []
for pid, stats in player_stats.items():
    count = stats['count']
    x_avg = stats['x_total'] / count if count > 0 else float('nan')
    y_avg = stats['y_total'] / count if count > 0 else float('nan')
    rows.append({'player_id': pid, 'avg_x': x_avg, 'avg_y': y_avg, 'count': count})
    
player_avg_df = pd.DataFrame(rows)
print(player_avg_df.sort_values('player_id').to_string(index=False))