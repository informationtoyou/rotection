"""
Constants and config
"""

import os
from dotenv import load_dotenv

# -- project root (so file paths work on PythonAnywhere WSGI) --
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

API_KEY_HEADER = os.getenv("API_KEY_HEADER")

# -- endpoints --
ROTECTOR_BASE = "https://roscoe.rotector.com"
ROBLOX_GROUPS_API = "https://groups.roblox.com"
ROBLOX_USERS_API = "https://users.roblox.com"
ROBLOX_THUMBNAILS_API = "https://thumbnails.roblox.com"

# -- files (absolute paths so they work under any WSGI cwd) --
CACHE_FILE = os.path.join(PROJECT_ROOT, "scan_cache.json")
FLAGGED_FILE = os.path.join(PROJECT_ROOT, "flagged.txt")

# -- SEA Military HR/HC ranks --
SEA_MILITARY_GROUP_ID = 2648601
# Bracket prefixes that indicate HR/HC+ ranks (rank 10+)
SEA_HRHC_PREFIXES = {
    "[HR1]", "[HR2]", "[HR3]",
    "[HC1]", "[HC2]", "[HC3]", "[HC3+]",
    "[DR]", "[M]", "[L]",
}

# -- rate limits --
ROTECTOR_RATE_LIMIT = 500
ROTECTOR_RATE_WINDOW = 10
ROBLOX_RATE_LIMIT = 80
ROBLOX_RATE_WINDOW = 10

# -- threading --
WORKER_THREADS = 50
MAX_RETRIES = 5

# -- HTTP timeouts & retry behaviour --
HTTP_TIMEOUT_ROTECTOR = 30      # seconds
HTTP_TIMEOUT_ROBLOX = 20        # seconds
HTTP_RETRY_SLEEP = 1            # seconds to sleep between retry attempts
HTTP_RETRY_AFTER_DEFAULT = 5    # fallback seconds when Retry-After header is missing/invalid

# -- queue worker timings --
QUEUE_WORKER_POLL_TIMEOUT = 30  # seconds to wait for new work before re-checking
QUEUE_INTER_SCAN_SLEEP = 2      # seconds between consecutive scans
QUEUE_ERROR_BACKOFF = 5         # seconds to sleep after an unexpected queue loop error

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
