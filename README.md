# Rotection

Scans SEA Military (and its affiliates, so everyone!) or its divisions, or ANY other group using [Rotector's](https://rotector.com) convenient [API](https://roscoe.rotector.com), resolves their Discord and Roblox accounts, and gives you a list of Discord IDs to massban!

This comes with a web dashboard and a CLI. Web version has live progress, charts, statistic, and export options.

## What does this do?

1. Takes a Roblox group ID
2. Optionally discovers all allied/enemy groups
3. Pulls tracked/flagged users from each group via Rotector
4. Fills in missing usernames from the Roblox API wherever it can
5. Fetches flag details (type, confidence, reasons)
6. Resolves linked Discord accounts for each flagged user
7. Saves everything to `scan_cache.db` and `flagged.txt`

The web dashboard shows all of this in real time with an ETA, and lets you filter/sort/export the results after. It is highly recommended if you are not a developer to use the web dashboard.

You can find the site hosting this [here](https://rotection.pythonanywhere.com). It is **locked** by an account authentication to avoid clankers (exception: ThatOneClankerr as he also happens to be a clanker but not *that* type). Make an account there!

## Self-hosting for the cool kids

```bash
# Clone the actual repository
git clone https://github.com/informationtoyou/rotection.git
cd Rotection

# Make a virtual environment (venv)
python3 -m venv .venv
source .venv/bin/activate  # On windows: .venv\Scripts\activate

# Install all dependencies (Python 3.14.3 is what this is written in, but usually this should work on Python 3.8+)
pip install -r requirements.txt
```

Optionally, create a `.env` file in the project root:

```
API_KEY_HEADER=your_rotector_api_key_here
ADMIN_SECRET=whatever_admin_password_you_want
```

You get the API key from Rotector. Without it, the scanner can't fetch flag data. Rotector API keys are not available to the public at the moment without contacting the owner of Rotector. The owner of Rotector was kind enough to give me one, which is being used at https://rotection.pythonanywhere.com/.

Admin's username is `admin`.

## Hey, I wanna help!

Fork and make a PR. I will review it personally. Please detail your PR with the feature, or fix, or whatever and try to explain what you're doing. I'm not expecting an essay but something that makes my life easier and so I can quickly review the PR :D!

## Hey, I have a suggestion / Hey, there's a bug!

DM or make an Issue. Your contribution helps.

## Running

**Web dashboard (local dev):**

```bash
python app.py
# open http://localhost:5050 in your web browser
```

**CLI:**

```bash
python bot.py                        # scan default group (2648601) with allies/enemies
python bot.py --group=12345          # scan a different group
python bot.py --no-allies            # skip allied groups
python bot.py --no-enemies           # skip enemy groups
python bot.py --history              # list previous scans
python bot.py --load=20260310_1234   # print a saved scan's results
```

## Project structure

```
Rotection/
├── app.py                  — Thin entry point: creates the Flask app and runs it
├── bot.py                  — CLI interface (no web server needed)
├── requirements.txt        — Python dependencies
├── app/
│   ├── __init__.py         — Flask app factory (create_app), session config, DB + affiliates init
│   ├── affiliates.py       — Fetches & caches SEA Military allies/enemies from the Roblox API
│   ├── database.py         — SQLite database (users, scan queue, user statuses)
│   ├── deploy_state.py     — Thread-safe deploy banner state management
│   ├── queue_worker.py     — Background thread that processes queued scans one at a time
│   └── routes/
│       ├── __init__.py     — Registers all blueprints
│       ├── auth.py         — Login, signup, logout, session, login_required/admin_required
│       ├── admin.py        — Admin panel: confirm users, change roles, delete accounts
│       ├── pages.py        — GET / (dashboard), /login, /signup
│       ├── scan.py         — /api/scan, /api/progress, /api/queue, /api/user-status
│       ├── scans.py        — /api/scans, /api/scans/<id>, /api/scans/<id>/discord-export
│       └── deploy.py       — /api/deploy/notify, /api/deploy/status
├── scanner/
│   ├── __init__.py         — Re-exports public API (run_scan, is_scanning, etc.)
│   ├── constants.py        — Endpoints, config, flag types, verification sources
│   ├── rate_limiter.py     — Thread-safe sliding-window rate limiter
│   ├── http.py             — Persistent sessions + request helpers (retries, 429 handling)
│   ├── roblox.py           — Roblox API (groups, allies/enemies, users, thumbnails)
│   ├── rotector.py         — Rotector API (tracked users, batch lookup, discord IDs)
│   ├── cache.py            — SQLite scan cache (auto-migrates from JSON, load/save/query)
│   ├── progress.py         — ScanProgress class + global instance
│   └── engine.py           — run_scan, is_scanning, background _scan_worker
├── static/
│   ├── styles.css          — Dashboard styles
│   └── js/
│       ├── state.js        — Shared globals, constants, utility helpers
│       ├── auth.js         — Login, logout, loadCurrentUser
│       ├── scan.js         — Scan controls, queue polling, progress stream, deploy banner
│       ├── results.js      — Results table, filters, sorting, pagination, user status
│       ├── stats.js        — Statistics charts (Flag, Group, Confidence)
│       ├── discord.js      — Discord ID export panel
│       ├── admin.js        — Admin panel, user detail modal, history, queue
│       └── main.js         — Tab wiring, modal listeners, init()
├── templates/
│   ├── index.html          — Single-page dashboard (requires login)
│   ├── login.html          — Login page
│   └── signup.html         — Signup page with role/division selection
├── .env                    — API keys (gitignored)
├── rotection.db            — SQLite database (auto-generated, gitignored)
├── scan_cache.db           — Saved scan results, SQLite (auto-generated, gitignored)
└── flagged.txt             — Space-separated Discord IDs from last scan (auto-generated, gitignored)
```

## Features

- **Threaded scanning**: Discord ID lookups run in parallel (20 threads by default) so scans finish way faster. 20 is the limit for those who do not have an API Key, if you do, 50 threads is the maximum as 500 requests / 10 seconds are allowed.
- **Roblox API fallback**: if Rotector doesn't have a username or role, it pulls directly from Roblox when it can.
- **Scan deduplication**: re-scanning the same group+allies combo updates the old scan instead of making duplicates
- **W Error Handling!?**: it can handle erros if I messed up gg
- **Progress Bar**: progress bar shows estimated time remaining per phase, as with any progress bar, this is never 100% accurate, it's just a metric to know something is actually happening
- **Advanced filters**: filter by group, role, flag type, confidence range, actionable status, has-discord
- **Pagination**: browse all users, not just the first 500
- **Statistics tab**: charts for flag distribution, confidence spread, users per group, and much more coming soon!
- **Discord ID export**: copy as space-separated, one-per-line, CSV, or download as JSON with full user details
- **Scan history** : load any previous scan from the History tab
- **Group navigation**: click group buttons to filter by specific affiliated groups
- **Deploy banner**: GitHub Actions notifies the site before deploying; users see a banner and the deploy waits for any running scan to finish

## Rate limits

- Rotector: 500 requests per 10 seconds (with API key; 200 without)
- Roblox: 80 requests per 10 seconds (conservative to avoid 429s)

The scanner backs off and retries on 429 responses.
By default, a maximum of 5 retries.
Again, this is open-source for a reason.
Go wild and change it in `scanner/constants.py`.

## License
Do whatever the hell you want with this as long as you:
- Credit @Infoflexy or @informationtoyou
- **Don't** claim this work as your own. (unless you have contributed, then feel free to brag about how cool you are.)
- Do not use it to evade bans from Rule 1, 11, 14, 19 in SEA.

## help is this a virus
no lmao plz scan on virustotal if this being open-source is not already enough for you, ask someone to review for you, ask AI, anything basically

## Final Notes
ofc to anyone who criticises this, as Poppe once rightfully said:
"anything but banning the p3dos" - Mr_Poppe2 March 2026
Shoutout to all the people who supported along the way! You know who you are, thanks.
Big shoutout to ggpv for indirectly giving me the idea to make this.
Big shoutout to antonio_farah for reminding me that multithreading exists, I lowkey forgot it does (how am I even real).
