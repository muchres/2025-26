"""
Shared constants for the Sports Analytics dashboard.

All colours, file paths, formation lookups and pitch geometry live here so
that no module re-declares them.  Paths are resolved relative to this file's
location so the app works regardless of the current working directory.
"""

import os

# ── Path roots ────────────────────────────────────────────────────────────────
# This file lives at  <PROJECT_ROOT>/6_Final/utils/constants.py
_THIS_DIR    = os.path.dirname(os.path.abspath(__file__))      # .../6_Final/utils
APP_DIR      = os.path.dirname(_THIS_DIR)                       # .../6_Final
PROJECT_ROOT = os.path.dirname(APP_DIR)                         # .../FMP
DATA_ROOT    = PROJECT_ROOT                                     # data folders sit under FMP

# ── Data file paths — LaLiga navigation app ───────────────────────────────────
LALIGA_COLOUR_CSV = os.path.join(DATA_ROOT, "3_Working", "laliga_team_colour_1.csv")
LALIGA_MATCH_CSV  = os.path.join(DATA_ROOT, "1_Downloader", "laliga_0524_1.csv")
LOGOS_ROOT        = os.path.join(DATA_ROOT, "4_Logos")
LALIGA_LOGO_DIR   = os.path.join(DATA_ROOT, "4_Logos", "LaLiga", "128x128")

# ── Data file paths — Premier League navigation app ───────────────────────────
EPL_COLOUR_CSV = os.path.join(DATA_ROOT, "3_Working", "epl_team_colour_1.csv")
EPL_MATCH_CSV  = os.path.join(DATA_ROOT, "1_Downloader", "epl_0524.csv")
EPL_LOGO_DIR   = os.path.join(DATA_ROOT, "4_Logos", "EPL", "128x128")

# ── Data file paths — match-analysis dashboard (EPL sample) ───────────────────
MATCH_PLAYERS_CSV = os.path.join(DATA_ROOT, "2_Data", "epl_player_list.csv")
MATCH_TEAMS_CSV   = os.path.join(DATA_ROOT, "3_Working", "epl_team_colour_1.csv")
MATCH_LOGO_DIR    = os.path.join(DATA_ROOT, "4_Logos", "EPL", "64x64")
# Default sample match used when no match_id mapping is supplied.
MATCH_DEFAULT_CSV = os.path.join(
    DATA_ROOT, "2_Data", "EPL",
    "EPL_20251123_ARS_TOT_28m9dl3dg3b2kv50yxgrt2sk4.csv",
)

# ── Data file paths — match-analysis dashboard (LaLiga) ───────────────────────
EPL_DATA_DIR          = os.path.join(DATA_ROOT, "2_Data", "EPL")
EPL_PLAYERS_CSV       = os.path.join(DATA_ROOT, "2_Data", "EPL_player_list.csv")
LALIGA_DATA_DIR       = os.path.join(DATA_ROOT, "2_Data", "LaLiga")
LALIGA_PLAYERS_CSV    = os.path.join(DATA_ROOT, "2_Data", "laliga_player_list.csv")
LALIGA_TEAMS_CSV      = LALIGA_COLOUR_CSV   # 3_Working/laliga_team_colour_1.csv
LALIGA_MATCH_LOGO_DIR = os.path.join(DATA_ROOT, "4_Logos", "LaLiga", "64x64")

# ── Palette — navigation app ──────────────────────────────────────────────────
LALIGA_RED = "#301B06"
SIDEBAR_BG = "#EEECE3"
CARD_BG    = "#FAF9F6"
BORDER     = "#BCB6A3"
TEXT_MAIN  = "#000000"
TEXT_MUTED = "#AEAEAE"

# ── Palette — match-analysis dashboard ────────────────────────────────────────
# HOME_COLOUR / AWAY_COLOUR are resolved per-match from the team colour CSV.
BG_COLOUR     = "#FAF9F6"   # page background
PRIMARY_COL   = "#EEECE3"   # table header / section labels
SECONDARY_COL = "#301B06"   # table cell text
TERTIARY_COL  = "#edf2f7"   # borders / placeholder

# ── Short-name → team_code map — EPL match CSV ───────────────────────────────
EPL_TEAM_MAP = {
    "Arsenal":        "ARS",
    "Aston Villa":    "AVL",
    "Bournemouth":    "BOU",
    "Brentford":      "BRE",
    "Brighton":       "BHA",
    "Burnley":        "BUR",
    "Chelsea":        "CHE",
    "Crystal Palace": "CRY",
    "Everton":        "EVE",
    "Fulham":         "FUL",
    "Leeds":          "LEE",
    "Liverpool":      "LIV",
    "Man City":       "MCI",
    "Man Utd":        "MUN",
    "Newcastle":      "NEW",
    "Nottm Forest":   "NFO",
    "Spurs":          "TOT",
    "Sunderland":     "SUN",
    "West Ham":       "WHU",
    "Wolves":         "WOL",
}

# ── Short-name → team_code map (match CSV uses short names) ────────────────────
TEAM_MAP = {
    "Athletic":      "ATH",
    "Atletico":      "ATM",
    "Atlético":      "ATM",
    "Alaves":        "ALA",
    "Alavés":        "ALA",
    "Barcelona":     "BAR",
    "Betis":         "BET",
    "Celta":         "CEL",
    "Elche":         "ELC",
    "Espanyol":      "ESP",
    "Getafe":        "GET",
    "Girona":        "GIR",
    "Levante":       "LEV",
    "Mallorca":      "MLL",
    "Osasuna":       "OSA",
    "Oviedo":        "OVI",
    "Rayo":          "RAY",
    "Real Madrid":   "RMA",
    "Real Sociedad": "RSO",
    "Sevilla":       "SEV",
    "Valencia":      "VAL",
    "Villarreal":    "VIL",
}

# ── Formation lookups ─────────────────────────────────────────────────────────
formation_mapping = {
    "1": "",     "2": "442",   "3": "41212", "4": "433",  "5": "451",
    "6": "4411", "7": "4141",  "8": "4231",  "9": "4321", "10": "532",
    "11": "541", "12": "352",  "13": "343",  "14": "31312","15": "4222",
    "16": "3511","17": "3421", "18": "3412", "19": "3142", "20": "",
    "21": "4132","22": "",     "23": "4312", "24": "3241", "25": "3232",
}

formation_position_mapping = {
    "442":   {"1":"GK","2":"RB", "3":"LB", "4":"CM", "5":"CB", "6":"CB", "7":"RM", "8":"CM",  "9":"ST", "10":"ST",  "11":"LM"},
    "41212": {"1":"GK","2":"RB", "3":"LB", "4":"CDM","5":"CB", "6":"CB", "7":"CM", "8":"CAM", "9":"ST", "10":"ST",  "11":"CM"},
    "433":   {"1":"GK","2":"RB", "3":"LB", "4":"CM", "5":"CB", "6":"CB", "7":"CM", "8":"CM",  "9":"ST", "10":"RW",  "11":"LW"},
    "451":   {"1":"GK","2":"RB", "3":"LB", "4":"CM", "5":"CB", "6":"CB", "7":"RM", "8":"CM",  "9":"CAM","10":"ST",  "11":"LM"},
    "4411":  {"1":"GK","2":"RB", "3":"LB", "4":"CM", "5":"CB", "6":"CB", "7":"RM", "8":"CM",  "9":"ST", "10":"SS",  "11":"LM"},
    "4141":  {"1":"GK","2":"RB", "3":"LB", "4":"CDM","5":"CB", "6":"CB", "7":"RM", "8":"CM",  "9":"ST", "10":"CM",  "11":"LM"},
    "4231":  {"1":"GK","2":"RB", "3":"LB", "4":"CDM","5":"CB", "6":"CB", "7":"RW", "8":"CDM", "9":"ST", "10":"CAM", "11":"LW"},
    "4321":  {"1":"GK","2":"RB", "3":"LB", "4":"CDM","5":"CB", "6":"CB", "7":"CM", "8":"CM",  "9":"ST", "10":"CAM", "11":"CAM"},
    "532":   {"1":"GK","2":"RWB","3":"LWB","4":"CB", "5":"CB", "6":"CB", "7":"CM", "8":"CDM", "9":"ST", "10":"ST",  "11":"CM"},
    "541":   {"1":"GK","2":"RWB","3":"LWB","4":"CB", "5":"CB", "6":"CB", "7":"RM", "8":"CM",  "9":"ST", "10":"CM",  "11":"LM"},
    "352":   {"1":"GK","2":"RWB","3":"LWB","4":"CB", "5":"CB", "6":"CB", "7":"CM", "8":"CM",  "9":"ST", "10":"ST",  "11":"CAM"},
    "343":   {"1":"GK","2":"RWB","3":"LWB","4":"CB", "5":"CB", "6":"CB", "7":"CM", "8":"CM",  "9":"ST", "10":"RW",  "11":"LW"},
    "31312": {"1":"GK","2":"RWB","3":"LWB","4":"CDM","5":"CB", "6":"CB", "7":"CB", "8":"CM",  "9":"ST", "10":"CAM", "11":"SS"},
    "4222":  {"1":"GK","2":"RB", "3":"LB", "4":"CDM","5":"CB", "6":"CB", "7":"CDM","8":"CAM", "9":"ST", "10":"ST",  "11":"CAM"},
    "3511":  {"1":"GK","2":"RWB","3":"LWB","4":"CB", "5":"CB", "6":"CB", "7":"CM", "8":"CM",  "9":"ST", "10":"SS",  "11":"CAM"},
    "3421":  {"1":"GK","2":"RWB","3":"LWB","4":"CB", "5":"CB", "6":"CB", "7":"CM", "8":"CM",  "9":"CAM","10":"CAM", "11":"ST"},
    "3412":  {"1":"GK","2":"RWB","3":"LWB","4":"CB", "5":"CB", "6":"CB", "7":"CM", "8":"CM",  "9":"CAM","10":"ST",  "11":"ST"},
    "4132":  {"1":"GK","2":"RB", "3":"LB", "4":"CDM","5":"CB", "6":"CB", "7":"RM", "8":"CM",  "9":"ST", "10":"ST",  "11":"LM"},
    "4312":  {"1":"GK","2":"RB", "3":"LB", "4":"CDM","5":"CB", "6":"CB", "7":"CM", "8":"CAM",  "9":"ST", "10":"ST", "11":"CM"},
    "3241":  {"1":"GK","2":"CM", "3":"CM", "4":"CB", "5":"CB", "6":"CB", "7":"SS", "8":"SS",  "9":"ST", "10":"RM", "11":"LM"},
    "3232":  {"1":"GK","2":"CAM", "3":"CDM", "4":"CB", "5":"CB", "6":"CB", "7":"ST", "8":"CDM",  "9":"ST", "10":"RM", "11":"LM"},
}

formation_coords = {
"442":   {"1": (5,34), "2": (15,10), "3": (15,58), "4": (30,24), "5": (15,24), "6": (15,44), "7": (30,10), "8": (30,44), "9": (47,26), "10": (47,42), "11": (30,58)},
"41212": {"1": (5,34), "2": (15,10), "3": (15,58), "4": (23,34), "5": (15,24), "6": (15,44), "7": (30,44), "8": (39,34), "9": (47,26), "10": (47,42), "11": (30,24)},
"433":   {"1": (5,34), "2": (15,10), "3": (15,58), "4": (30,34), "5": (15,24), "6": (15,44), "7": (30,22), "8": (30,46), "9": (45,34), "10": (45,10), "11": (45,58)},
"451":   {"1": (5,34), "2": (15,10), "3": (15,58), "4": (30,22), "5": (15,24), "6": (15,44), "7": (30,10), "8": (30,46), "9": (34,34), "10": (47,34), "11": (30,58)},
"4411":  {"1": (5,34), "2": (15,10), "3": (15,58), "4": (30,24), "5": (15,24), "6": (15,44), "7": (30,10), "8": (30,44), "9": (47,34), "10": (39,34), "11": (30,58)},
"4141":  {"1": (5,34), "2": (15,10), "3": (15,58), "4": (26,34), "5": (15,24), "6": (15,44), "7": (36,10), "8": (36,24), "9": (47,34), "10": (36,44), "11": (36,58)},
"4231":  {"1": (5,34), "2": (15,10), "3": (15,58), "4": (26,44), "5": (15,24), "6": (15,44), "7": (34,10), "8": (26,24), "9": (47,34), "10": (34,34), "11": (34,58)},
"4321":  {"1": (5,34), "2": (15,10), "3": (15,58), "4": (28,34), "5": (15,24), "6": (15,44), "7": (30,48), "8": (30,20), "9": (47,34), "10": (39,44), "11": (39,24)},
"532":   {"1": (5,34), "2": (18,8), "3": (18,60), "4": (15,34), "5": (15,22), "6": (15,46), "7": (32,48), "8": (31,34), "9": (47,26), "10": (47,42), "11": (32,20)},
"541":   {"1": (5,34), "2": (18,8), "3": (18,60), "4": (15,34), "5": (15,22), "6": (15,46), "7": (30,10), "8": (30,24), "9": (47,34), "10": (30,44), "11": (30,58)},
"352":   {"1": (5,34), "2": (28,8), "3": (28,60), "4": (15,34), "5": (15,22), "6": (15,46), "7": (28,44), "8": (28,24), "9": (47,26), "10": (47,42), "11": (39,34)},
"343":   {"1": (5,34), "2": (30,8), "3": (30,60), "4": (15,34), "5": (15,22), "6": (15,46), "7": (30,44), "8": (30,24), "9": (47,34), "10": (45,14), "11": (45,54)},
"31312": {"1": (5,34), "2": (30,8), "3": (30,60), "4": (23,34), "5": (15,22), "6": (15,46), "7": (15,34), "8": (30,34), "9": (47,26), "10": (37,34), "11": (46,42)},
"4222":  {"1": (5,34), "2": (15,10), "3": (15,58), "4": (26,24), "5": (15,24), "6": (15,44), "7": (26,44), "8": (36,50), "9": (47,26), "10": (47,42), "11": (36,18)},
"3511":  {"1": (5,34), "2": (28,8), "3": (28,60), "4": (15,34), "5": (15,22), "6": (15,46), "7": (28,46), "8": (28,22), "9": (47,34), "10": (40,34), "11": (32,34)},
"3421":  {"1": (5,34), "2": (28,8), "3": (28,60), "4": (15,34), "5": (15,22), "6": (15,46), "7": (28,44), "8": (28,24), "9": (38,44), "10": (38,24), "11": (47,34)},
"3412":  {"1": (5,34), "2": (28,8), "3": (28,60), "4": (15,34), "5": (15,22), "6": (15,46), "7": (28,44), "8": (28,24), "9": (39,34), "10": (47,26), "11": (47,42)},
"4132":  {"1": (5,34), "2": (15,10), "3": (15,58), "4": (24,34), "5": (15,24), "6": (15,44), "7": (35,20), "8": (35,34), "9": (47,26), "10": (47,42), "11": (35,48)},
"4312":  {"1": (5,34), "2": (15,10), "3": (15,58), "4": (28,34), "5": (15,24), "6": (15,44), "7": (28,48), "8": (38,34), "9": (47,26), "10": (47,42), "11": (28,20)},
"3241":  {"1": (5,34), "2": (25,24), "3": (25,44), "4": (15,34), "5": (15,20), "6": (15,48), "7": (36,44), "8": (36,24), "9": (47,34), "10": (36,8), "11": (36,60)},
"3232":  {"1": (5,34), "2": (36,34), "3": (25,44), "4": (15,34), "5": (15,20), "6": (15,48), "7": (47,42), "8": (25,24), "9": (47,26), "10": (36,10), "11": (36,58)},
}

# ── Pitch / zone constants ────────────────────────────────────────────────────
ROW_H        = 68 / 3                   # ≈ 22.67
ATT_X0       = 72.0
ATT_MIDX     = 88.5
LW_SPLIT     = (2 * ROW_H + 68) / 2     # ≈ 56.67
RW_SPLIT     = ROW_H / 2                # ≈ 11.33
KEY_ZONES    = ["Z14", "LHS", "RHS"]
ARROW_COLORS = {"Z14": "#27AE60", "LHS": "#B8860B", "RHS": "#B8860B"}
GOAL_X, GOAL_Y = 100, 50
MAX_DIST     = 111.80339887498948

POS_ORDER = ["GK","LWB","LB","CB","RB","RWB","CDM","LM","CM","RM","CAM","LW","RW","SS","ST"]
