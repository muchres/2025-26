# Sporting CP Match Analysis Dashboard

A comprehensive Plotly Dash application for analyzing Sporting Clube de Portugal's match performance across multiple dimensions including attacking patterns, pass distributions, chance creation, and defensive actions.

## Features

### 📊 Visualizations

1. **Attacking Pattern Heatmap**
   - Shows where Sporting CP initiates passes from
   - Identifies primary ball retention zones
   - Color intensity represents frequency of passes initiated

2. **Pass Receive Heatmap**
   - Displays where Sporting CP completes passes
   - Shows reception zones across the pitch
   - Helps identify team's passing connectivity patterns

3. **Chance Creation Heatmap**
   - Visualizes shot attempts and big chance locations
   - Shows where most dangerous opportunities are created
   - Includes goals, saved shots, misses, and posts

4. **Defensive Action Map**
   - Maps tackles, interceptions, clearances, challenges, and blocks
   - Shows defensive pressure zones
   - Identifies areas of defensive activity concentration

### 📈 Key Metrics

- **PPDA (Passes Per Defensive Action)**: Indicates how many passes team completes per defensive action
- **Defensive Actions/90**: Normalized defensive action rate per 90 minutes
- **Pass Accuracy**: Percentage of successful passes
- **Shot Efficiency**: Goals per shot (goals / total shots)

### 🎮 Interactive Features

- **Match Selector Dropdown**: Choose any of Sporting CP's matches in the dataset
- **Real-time Updates**: All visualizations update based on match selection
- **Hover Information**: Detailed tooltips on all heatmaps showing zone data

## Installation

### Requirements
```bash
pip install pandas plotly dash dash-bootstrap-components
```

### Setup

1. Ensure you have the data file `Sporting_Matches_1.csv` in the same directory
2. Install dependencies from requirements
3. Run the application

## Running the Dashboard

```bash
python sporting_cp_analysis_dashboard.py
```

The dashboard will start on `http://localhost:8050`

## Data Format

The application expects a CSV file with at least the following columns:
- `match_id`: Unique match identifier
- `team_name`: Team name
- `event`: Type of event (Pass, Shot, Tackle, etc.)
- `x`, `y`: Starting coordinates of event
- `Pass End X`, `Pass End Y`: Ending coordinates for passes
- `outcome`: Success indicator (1 for successful, 0 for unsuccessful)
- `local_date`: Match date
- `period_length`: Duration of period/match
- Additional event-specific fields

## Dashboard Layout

```
┌─────────────────────────────────────────────────┐
│        Sporting CP Match Analysis               │
├─────────────────────────────────────────────────┤
│  [Match Selector Dropdown]                      │
├─────────────────────────────────────────────────┤
│  [Match Summary Card]                           │
├─────────────────────────────────────────────────┤
│  [PPDA] [Def/90] [Pass Acc] [Shot Eff]         │
├──────────────────┬──────────────────────────────┤
│ Attacking        │ Pass Receive                 │
│ Pattern          │ Heatmap                      │
├──────────────────┼──────────────────────────────┤
│ Chance Creation  │ Defensive Action             │
│ Heatmap          │ Map                          │
└──────────────────┴──────────────────────────────┘
```

## Heatmap Interpretation

### Color Scales

- **Attacking Pattern (Blues)**: Blue = High frequency of pass initiations
- **Pass Receive (Greens)**: Green = High frequency of pass receptions
- **Chance Creation (Reds)**: Red = High frequency of shot attempts
- **Defensive Actions (Purples)**: Purple = High frequency of defensive actions

### Field Dimensions

- Field width: 0-100 units (x-axis)
- Field height: 0-68 units (y-axis)
- Center line: x = 50 (marked with dashed white line)

## Statistics Calculation

### PPDA Formula
```
PPDA = Total Passes / Total Defensive Actions
```
Lower PPDA indicates more aggressive pressing (more defensive actions per pass allowed)

### Defensive Actions
Includes:
- Tackles
- Interceptions
- Clearances
- Challenges
- Blocks

### Pass Accuracy
```
Pass Accuracy (%) = (Successful Passes / Total Passes) × 100
```

### Shot Efficiency
```
Shot Efficiency (%) = (Goals / Total Shots) × 100
```

## Performance Notes

- The dashboard uses efficient 2D histograms for fast rendering
- Data is filtered and preprocessed at load time
- Callbacks use responsive updates for smooth interactions
- Works optimally with datasets containing 5,000-20,000 events per team

## Future Enhancements

- [ ] Add player performance breakdowns
- [ ] Include temporal analysis (shots/minute timeline)
- [ ] Add passing network visualization
- [ ] Compare against opponent stats
- [ ] Export data and visualizations
- [ ] Add possession analysis
- [ ] Include expected goals (xG) when available

## License

[Add appropriate license]

## Contact

For issues or feature requests, please reach out to the development team.
