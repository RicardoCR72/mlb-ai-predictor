"""Constantes centrales, mapeos de equipos, husos horarios y configuraciones compartidas."""
from __future__ import annotations
from zoneinfo import ZoneInfo

# ==============================================================================
# 1. HUSOS HORARIOS DEL PROYECTO
# ==============================================================================
ZONA_MX = ZoneInfo("America/Mazatlan")        # Zona principal para corte de jornada
ZONA_CDMX = ZoneInfo("America/Mexico_City")   # Hora centro de México
ZONA_UTC = ZoneInfo("UTC")

# ==============================================================================
# 2. MAPEOS DE EQUIPOS MLB (30 FRANQUICIAS)
# ==============================================================================
MLB_TEAMS_ABBR = {
    'Arizona Diamondbacks': 'ARI', 'Athletics': 'OAK', 'Oakland Athletics': 'OAK',
    'Atlanta Braves': 'ATL', 'Baltimore Orioles': 'BAL', 'Boston Red Sox': 'BOS',
    'Chicago Cubs': 'CHC', 'Chicago White Sox': 'CWS', 'Cincinnati Reds': 'CIN',
    'Cleveland Guardians': 'CLE', 'Colorado Rockies': 'COL', 'Detroit Tigers': 'DET',
    'Houston Astros': 'HOU', 'Kansas City Royals': 'KC', 'Los Angeles Angels': 'LAA',
    'Los Angeles Dodgers': 'LAD', 'Miami Marlins': 'MIA', 'Milwaukee Brewers': 'MIL',
    'Minnesota Twins': 'MIN', 'New York Mets': 'NYM', 'New York Yankees': 'NYY',
    'Philadelphia Phillies': 'PHI', 'Pittsburgh Pirates': 'PIT', 'San Diego Padres': 'SD',
    'San Francisco Giants': 'SF', 'Seattle Mariners': 'SEA', 'St. Louis Cardinals': 'STL',
    'Tampa Bay Rays': 'TB', 'Texas Rangers': 'TEX', 'Toronto Blue Jays': 'TOR',
    'Washington Nationals': 'WSH',
}

MLB_TEAMS_IDS = {
    'Arizona Diamondbacks': 109, 'Atlanta Braves': 144, 'Baltimore Orioles': 110,
    'Boston Red Sox': 111, 'Chicago Cubs': 112, 'Chicago White Sox': 145,
    'Cincinnati Reds': 113, 'Cleveland Guardians': 114, 'Colorado Rockies': 115,
    'Detroit Tigers': 116, 'Houston Astros': 117, 'Kansas City Royals': 118,
    'Los Angeles Angels': 108, 'Los Angeles Dodgers': 119, 'Miami Marlins': 146,
    'Milwaukee Brewers': 158, 'Minnesota Twins': 142, 'New York Mets': 121,
    'New York Yankees': 147, 'Athletics': 133, 'Oakland Athletics': 133,
    'Philadelphia Phillies': 143, 'Pittsburgh Pirates': 134, 'San Diego Padres': 135,
    'San Francisco Giants': 137, 'Seattle Mariners': 136, 'St. Louis Cardinals': 138,
    'Tampa Bay Rays': 139, 'Texas Rangers': 140, 'Toronto Blue Jays': 141,
    'Washington Nationals': 120
}

MLB_STADIUM_TIMEZONES = {
    'ARI': -7, 'ATL': -5, 'BAL': -5, 'BOS': -5, 'CHC': -6, 'CWS': -6, 'CIN': -5, 'CLE': -5,
    'COL': -7, 'DET': -5, 'HOU': -6, 'KC': -6, 'LAA': -8, 'LAD': -8, 'MIA': -5, 'MIL': -6,
    'MIN': -6, 'NYM': -5, 'NYY': -5, 'OAK': -8, 'PHI': -5, 'PIT': -5, 'SD': -8, 'SF': -8,
    'SEA': -8, 'STL': -6, 'TB': -5, 'TEX': -6, 'TOR': -5, 'WSH': -5
}

# ==============================================================================
# 3. MAPEOS DE EQUIPOS NFL (32 FRANQUICIAS)
# ==============================================================================
NFL_TEAMS = {
    'ARI': 'Arizona Cardinals', 'ATL': 'Atlanta Falcons', 'BAL': 'Baltimore Ravens',
    'BUF': 'Buffalo Bills', 'CAR': 'Carolina Panthers', 'CHI': 'Chicago Bears',
    'CIN': 'Cincinnati Bengals', 'CLE': 'Cleveland Browns', 'DAL': 'Dallas Cowboys',
    'DEN': 'Denver Broncos', 'DET': 'Detroit Lions', 'GB': 'Green Bay Packers',
    'HOU': 'Houston Texans', 'IND': 'Indianapolis Colts', 'JAX': 'Jacksonville Jaguars',
    'KC': 'Kansas City Chiefs', 'LV': 'Las Vegas Raiders', 'LAC': 'Los Angeles Chargers',
    'LAR': 'Los Angeles Rams', 'MIA': 'Miami Dolphins', 'MIN': 'Minnesota Vikings',
    'NE': 'New England Patriots', 'NO': 'New Orleans Saints', 'NYG': 'New York Giants',
    'NYJ': 'New York Jets', 'PHI': 'Philadelphia Eagles', 'PIT': 'Pittsburgh Steelers',
    'SF': 'San Francisco 49ers', 'SEA': 'Seattle Seahawks', 'TB': 'Tampa Bay Buccaneers',
    'TEN': 'Tennessee Titans', 'WAS': 'Washington Commanders',
}

# ==============================================================================
# 4. MAPEOS DE EQUIPOS LIGA MX (18 CLUBES)
# ==============================================================================
LIGA_MX_TEAMS = [
    'América', 'Atlas', 'Atlético San Luis', 'Cruz Azul', 'Guadalajara',
    'Juárez', 'León', 'Mazatlán', 'Monterrey', 'Necaxa', 'Pachuca',
    'Puebla', 'Pumas UNAM', 'Querétaro', 'Santos Laguna', 'Tijuana',
    'Toluca', 'Tigres UANL'
]
