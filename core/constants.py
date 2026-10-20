"""Constantes centrales, mapeos de equipos, husos horarios y configuraciones compartidas."""
from __future__ import annotations
from zoneinfo import ZoneInfo

# ==============================================================================
# 1. HUSOS HORARIOS DEL PROYECTO
# ==============================================================================
ZONA_MX = ZoneInfo("America/Mexico_City")        # Zona principal para corte de jornada
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

# ==============================================================================
# 5. MAPEOS DE EQUIPOS NBA (30 FRANQUICIAS)
# ==============================================================================
NBA_TEAMS = {
    'ATL': 'Atlanta Hawks', 'BKN': 'Brooklyn Nets', 'BOS': 'Boston Celtics',
    'CHA': 'Charlotte Hornets', 'CHI': 'Chicago Bulls', 'CLE': 'Cleveland Cavaliers',
    'DAL': 'Dallas Mavericks', 'DEN': 'Denver Nuggets', 'DET': 'Detroit Pistons',
    'GSW': 'Golden State Warriors', 'HOU': 'Houston Rockets', 'IND': 'Indiana Pacers',
    'LAC': 'Los Angeles Clippers', 'LAL': 'Los Angeles Lakers', 'MEM': 'Memphis Grizzlies',
    'MIA': 'Miami Heat', 'MIL': 'Milwaukee Bucks', 'MIN': 'Minnesota Timberwolves',
    'NOP': 'New Orleans Pelicans', 'NYK': 'New York Knicks', 'OKC': 'Oklahoma City Thunder',
    'ORL': 'Orlando Magic', 'PHI': 'Philadelphia 76ers', 'PHX': 'Phoenix Suns',
    'POR': 'Portland Trail Blazers', 'SAC': 'Sacramento Kings', 'SAS': 'San Antonio Spurs',
    'TOR': 'Toronto Raptors', 'UTA': 'Utah Jazz', 'WAS': 'Washington Wizards'
}

NBA_TEAMS_IDS = {
    'Atlanta Hawks': 1610612737, 'Brooklyn Nets': 1610612751, 'Boston Celtics': 1610612738,
    'Charlotte Hornets': 1610612766, 'Chicago Bulls': 1610612741, 'Cleveland Cavaliers': 1610612739,
    'Dallas Mavericks': 1610612742, 'Denver Nuggets': 1610612743, 'Detroit Pistons': 1610612765,
    'Golden State Warriors': 1610612744, 'Houston Rockets': 1610612745, 'Indiana Pacers': 1610612754,
    'Los Angeles Clippers': 1610612746, 'Los Angeles Lakers': 1610612747, 'Memphis Grizzlies': 1610612763,
    'Miami Heat': 1610612748, 'Milwaukee Bucks': 1610612749, 'Minnesota Timberwolves': 1610612750,
    'New Orleans Pelicans': 1610612740, 'New York Knicks': 1610612752, 'Oklahoma City Thunder': 1610612760,
    'Orlando Magic': 1610612753, 'Philadelphia 76ers': 1610612755, 'Phoenix Suns': 1610612756,
    'Portland Trail Blazers': 1610612757, 'Sacramento Kings': 1610612758, 'San Antonio Spurs': 1610612759,
    'Toronto Raptors': 1610612761, 'Utah Jazz': 1610612762, 'Washington Wizards': 1610612764
}

# Normalizador de alias y variantes (ESPN, casas de apuestas, etc.)
NBA_ALIAS_TO_ABBR = {
    'GS': 'GSW', 'GSW': 'GSW', 'GOLDEN STATE': 'GSW', 'GOLDEN STATE WARRIORS': 'GSW',
    'NY': 'NYK', 'NYK': 'NYK', 'NEW YORK': 'NYK', 'NEW YORK KNICKS': 'NYK',
    'SA': 'SAS', 'SAS': 'SAS', 'SAN ANTONIO': 'SAS', 'SAN ANTONIO SPURS': 'SAS',
    'NO': 'NOP', 'NOP': 'NOP', 'NEW ORLEANS': 'NOP', 'NEW ORLEANS PELICANS': 'NOP',
    'UTAH': 'UTA', 'UTA': 'UTA', 'UTAH JAZZ': 'UTA',
    'WSH': 'WAS', 'WAS': 'WAS', 'WASHINGTON': 'WAS', 'WASHINGTON WIZARDS': 'WAS',
    'PHO': 'PHX', 'PHX': 'PHX', 'PHOENIX': 'PHX', 'PHOENIX SUNS': 'PHX',
    'BK': 'BKN', 'BKN': 'BKN', 'BROOKLYN': 'BKN', 'BROOKLYN NETS': 'BKN',
    'CHARLOTTE': 'CHA', 'CHA': 'CHA', 'CHARLOTTE HORNETS': 'CHA',
}
for abbr, name in NBA_TEAMS.items():
    NBA_ALIAS_TO_ABBR[abbr] = abbr
    NBA_ALIAS_TO_ABBR[name.upper()] = abbr

