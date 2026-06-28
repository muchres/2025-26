import os
import glob
import pandas as pd

shot_events = ['Goal', 'Miss', 'Saved Shot', 'Post']

FK_X_MIN = 88.5 / 105 * 100
FK_Y_MIN = (34 - 20.16) / 68 * 100
FK_Y_MAX = (34 + 20.16) / 68 * 100

ALL_SP_COLS = [
    'week', 'match_id', 'event', 'period_id', 'time_min', 'time_sec',
    'team_code', 'team_position', 'Jersey Number', 'player_id', 'x', 'y', 'outcome',
    'Free kick taken', 'Corner taken', 'Throw In',
    'Pass End X', 'Pass End Y',
    'Penalty', 'Free kick', 'Inswinger', 'Outswinger',
    'Left footed', 'Right footed', 'Head', 'Other body part',
    'Goal Mouth Y Coordinate', 'Goal Mouth Z Coordinate',
    'Set piece', 'From corner',
]


def extract_corner_sequences(df, shot_events):
    df = df.reset_index(drop=True)
    sequences = []
    seq_id = 1
    i = 0
    n = len(df)

    while i < n:
        row = df.iloc[i]
        if row['event'] == 'Corner Awarded' and row['outcome'] == 1:
            own_team = row['team_code']
            seq_indices = [i]
            j = i + 1

            while j < n:
                r = df.iloc[j]
                if r['event'] == 'Deleted event':
                    j += 1
                    continue
                is_own = r['team_code'] == own_team
                seq_indices.append(j)

                if is_own and r['outcome'] == 0:
                    break
                elif not is_own and r['outcome'] == 1:
                    break
                elif is_own and r['event'] in shot_events:
                    break
                elif len(seq_indices) >= 8: #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
                    break

                j += 1

            seq_df = df.iloc[seq_indices].copy()
            seq_df.insert(0, 'corner_seq_id', seq_id)
            sequences.append(seq_df)
            seq_id += 1
            i = j + 1
        else:
            i += 1

    if sequences:
        return pd.concat(sequences).reset_index(drop=True)
    return pd.DataFrame(columns=['corner_seq_id'] + list(df.columns))


def extract_fk_sequences(df, shot_events):
    df = df.reset_index(drop=True)
    sequences = []
    seq_id = 1
    i = 0
    n = len(df)

    while i < n:
        row = df.iloc[i]
        is_fk_start = (
            row['Free kick taken'] == 'Si' and
            row['Pass End X'] > FK_X_MIN and
            FK_Y_MIN <= row['Pass End Y'] <= FK_Y_MAX
        )
        if is_fk_start:
            own_team = row['team_code']
            seq_indices = []
            j = i

            while j < n:
                r = df.iloc[j]
                if r['event'] == 'Deleted event':
                    j += 1
                    continue
                is_own = r['team_code'] == own_team
                seq_indices.append(j)

                if is_own and r['outcome'] == 0:
                    break
                elif not is_own and r['outcome'] == 1:
                    break
                elif is_own and r['event'] in shot_events:
                    break
                elif len(seq_indices) >= 8: #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
                    break

                j += 1

            seq_df = df.iloc[seq_indices].copy()
            seq_df.insert(0, 'fk_seq_id', seq_id)
            sequences.append(seq_df)
            seq_id += 1
            i = j + 1
        else:
            i += 1

    if sequences:
        return pd.concat(sequences).reset_index(drop=True)
    return pd.DataFrame(columns=['fk_seq_id'] + list(df.columns))


def extract_short_fk_sequences(df, shot_events):
    df = df.reset_index(drop=True)
    sequences = []
    seq_id = 1
    i = 0
    n = len(df)

    while i < n:
        row = df.iloc[i]
        in_box = (
            row['Pass End X'] > FK_X_MIN and
            FK_Y_MIN <= row['Pass End Y'] <= FK_Y_MAX
        )
        is_fk_start = (
            row['Free kick taken'] == 'Si' and
            row['x'] > 50 and
            not in_box
        )
        if is_fk_start:
            own_team = row['team_code']
            seq_indices = []
            j = i

            while j < n:
                r = df.iloc[j]
                if r['event'] == 'Deleted event':
                    j += 1
                    continue
                is_own = r['team_code'] == own_team
                seq_indices.append(j)

                if is_own and r['outcome'] == 0:
                    break
                elif not is_own and r['outcome'] == 1:
                    break
                elif is_own and r['event'] in shot_events:
                    break
                elif len(seq_indices) >= 8: #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
                    break

                j += 1

            seq_df = df.iloc[seq_indices].copy()
            seq_df.insert(0, 'short_fk_seq_id', seq_id)
            sequences.append(seq_df)
            seq_id += 1
            i = j + 1
        else:
            i += 1

    if sequences:
        return pd.concat(sequences).reset_index(drop=True)
    return pd.DataFrame(columns=['short_fk_seq_id'] + list(df.columns))


def extract_longthrow_sequences(df, shot_events):
    df = df.reset_index(drop=True)
    sequences = []
    seq_id = 1
    i = 0
    n = len(df)

    while i < n:
        row = df.iloc[i]
        is_longthrow_start = (
            row['Throw In'] == 'Si' and
            row['Pass End X'] > FK_X_MIN and
            FK_Y_MIN <= row['Pass End Y'] <= FK_Y_MAX
        )
        if is_longthrow_start:
            own_team = row['team_code']
            seq_indices = []
            j = i

            while j < n:
                r = df.iloc[j]
                if r['event'] == 'Deleted event':
                    j += 1
                    continue
                is_own = r['team_code'] == own_team
                seq_indices.append(j)

                if is_own and r['outcome'] == 0:
                    break
                elif not is_own and r['outcome'] == 1:
                    break
                elif is_own and r['event'] in shot_events:
                    break
                elif len(seq_indices) >= 8: #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
                    break

                j += 1

            seq_df = df.iloc[seq_indices].copy()
            seq_df.insert(0, 'longthrow_seq_id', seq_id)
            sequences.append(seq_df)
            seq_id += 1
            i = j + 1
        else:
            i += 1

    if sequences:
        return pd.concat(sequences).reset_index(drop=True)
    return pd.DataFrame(columns=['longthrow_seq_id'] + list(df.columns))


def process_match(filepath):
    df = pd.read_csv(filepath)
    all_sp_df = df[ALL_SP_COLS]

    corner_seq = extract_corner_sequences(all_sp_df, shot_events)
    if not corner_seq.empty:
        corner_seq.insert(0, 'sp_type', 'corner')

    fkpass_seq = extract_fk_sequences(all_sp_df, shot_events)
    if not fkpass_seq.empty:
        fkpass_seq.insert(0, 'sp_type', 'fk_deliver_box')

    short_fkpass_seq = extract_short_fk_sequences(all_sp_df, shot_events)
    if not short_fkpass_seq.empty:
        short_fkpass_seq.insert(0, 'sp_type', 'fk_short')

    dfk_pk_shot = all_sp_df[
        all_sp_df['event'].isin(shot_events) &
        (
            (all_sp_df['Free kick'] == 'Si') |
            (all_sp_df['Penalty'] == 'Si')
        )
    ].reset_index(drop=True)
    if not dfk_pk_shot.empty:
        dfk_pk_shot.insert(0, 'sp_type', 'dfk_pk')

    longthrow_seq = extract_longthrow_sequences(all_sp_df, shot_events)
    if not longthrow_seq.empty:
        longthrow_seq.insert(0, 'sp_type', 'longthrow')

    all_sp_seq = pd.concat(
        [corner_seq, fkpass_seq, short_fkpass_seq, dfk_pk_shot, longthrow_seq],
        ignore_index=True
    )

    seq_id_cols = [c for c in all_sp_seq.columns if 'seq_id' in c]
    other_cols  = [c for c in all_sp_seq.columns if 'seq_id' not in c]
    all_sp_seq  = all_sp_seq[other_cols + seq_id_cols]

    return all_sp_seq


if __name__ == '__main__':
    data_dir   = '2_Data/LaLiga'
    output_path = '2_Data/all_sp_laliga.csv'

    files = sorted(glob.glob(os.path.join(data_dir, 'PRD_*.csv')))
    print(f'Found {len(files)} matches')

    results = []
    for i, f in enumerate(files, 1):
        try:
            match_sp = process_match(f)
            if not match_sp.empty:
                results.append(match_sp)
            print(f'[{i:>3}/{len(files)}] {os.path.basename(f)} — {len(match_sp)} rows')
        except Exception as e:
            print(f'[{i:>3}/{len(files)}] ERROR {os.path.basename(f)}: {e}')

    if results:
        all_sp_laliga = pd.concat(results, ignore_index=True)
        all_sp_laliga.to_csv(output_path, index=False)
        print(f'\nDone — {len(all_sp_laliga):,} rows exported to {output_path}')
    else:
        print('No data to export.')
