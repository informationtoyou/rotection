"""
Constants and config
"""

import os
from dotenv import load_dotenv

load_dotenv()

API_KEY_HEADER = os.getenv("API_KEY_HEADER")

# -- endpoints --
ROTECTOR_BASE = "https://roscoe.rotector.com"
ROBLOX_GROUPS_API = "https://groups.roblox.com"
ROBLOX_USERS_API = "https://users.roblox.com"
ROBLOX_THUMBNAILS_API = "https://thumbnails.roblox.com"

# -- files --
CACHE_FILE = "scan_cache.json"
FLAGGED_FILE = "flagged.txt"

# -- SEA Military HR/HC ranks --
SEA_MILITARY_GROUP_ID = 2648601
SEA_HRHC_RANKS = {
    "HR1", "HR2", "HR3",
    "HC1", "HC2", "HC3",
}

# -- rate limits --
ROTECTOR_RATE_LIMIT = 500
ROTECTOR_RATE_WINDOW = 10
ROBLOX_RATE_LIMIT = 80
ROBLOX_RATE_WINDOW = 10

# -- threading --
WORKER_THREADS = 50
MAX_RETRIES = 5

# -- flag types --
FLAG_TYPES = {
    0: {"name": "Unflagged", "actionable": False, "color": "#6b7280"},
    1: {"name": "Flagged", "actionable": True, "color": "#ef4444"},
    2: {"name": "Confirmed", "actionable": True, "color": "#dc2626"},
    3: {"name": "Queued", "actionable": False, "color": "#f59e0b"},
    5: {"name": "Mixed", "actionable": False, "color": "#f97316"},
    6: {"name": "Past Offender", "actionable": False, "color": "#8b5cf6"},
}

VERIFICATION_SOURCES = {0: "Bloxlink", 1: "RoVer", 2: "Discord Profile"}
