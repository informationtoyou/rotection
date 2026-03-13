"""
SQLite database for auth and scan queue
"""

import os
import json
import sqlite3
import threading
import time
import bcrypt
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rotection.db")

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """One connection per thread (SQLite is not thread-safe by default)."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")  # better concurrency
        _local.conn.execute("PRAGMA busy_timeout=5000")
    return _local.conn


@contextmanager
def get_db():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    """Create tables if they don't exist. Called once on app startup."""
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password    TEXT NOT NULL,
                roles       TEXT NOT NULL DEFAULT '[]',
                division_group_id   INTEGER,
                division_name       TEXT,
                divisions_moderating TEXT DEFAULT '[]',
                admin_confirmed     INTEGER DEFAULT 0,
                division_confirmed  INTEGER DEFAULT 0,
                divisions_mod_confirmed TEXT DEFAULT '[]',
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                is_admin    INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS scan_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id    INTEGER NOT NULL,
                include_allies INTEGER DEFAULT 1,
                include_enemies INTEGER DEFAULT 0,
                requested_by TEXT NOT NULL,
                status      TEXT DEFAULT 'queued',
                position    INTEGER DEFAULT 0,
                scan_id     TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                started_at  TEXT,
                finished_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_scan_queue_status ON scan_queue(status);
        """)

        # ── migrate user_statuses to global (roblox_id-only primary key) ──
        # check if the old scan_id-based table exists
        old = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='user_statuses'"
        ).fetchone()

        if old and "scan_id" in (old["sql"] or ""):
            # old schema — migrate data (keep latest status per roblox_id)
            db.executescript("""
                CREATE TABLE IF NOT EXISTS user_statuses_new (
                    roblox_id   TEXT PRIMARY KEY NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'Pending Review',
                    discord_ids TEXT DEFAULT '[]',
                    set_by      TEXT,
                    set_at      TEXT DEFAULT (datetime('now'))
                );

                INSERT OR IGNORE INTO user_statuses_new (roblox_id, status, set_by, set_at)
                SELECT roblox_id, status, set_by, set_at
                FROM user_statuses
                ORDER BY set_at DESC;

                DROP TABLE user_statuses;
                ALTER TABLE user_statuses_new RENAME TO user_statuses;
            """)
        else:
            # fresh install or already migrated
            db.executescript("""
                CREATE TABLE IF NOT EXISTS user_statuses (
                    roblox_id   TEXT PRIMARY KEY NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'Pending Review',
                    discord_ids TEXT DEFAULT '[]',
                    set_by      TEXT,
                    set_at      TEXT DEFAULT (datetime('now'))
                );
            """)


def ensure_admin():
    """Create or update admin account from ADMIN_SECRET env var."""
    secret = os.getenv("ADMIN_SECRET")
    if not secret:
        return
    hashed = bcrypt.hashpw(secret.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    with get_db() as db:
        row = db.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
        if row:
            db.execute("UPDATE users SET password = ?, is_admin = 1, admin_confirmed = 1 WHERE username = 'admin'", (hashed,))
        else:
            db.execute(
                "INSERT INTO users (username, password, roles, is_admin, admin_confirmed) VALUES (?, ?, ?, 1, 1)",
                ("admin", hashed, '["Admin"]'),
            )


# ──────────────────────── User CRUD ────────────────────────

def create_user(username: str, password: str, roles: list[str],
                division_group_id: int | None = None, division_name: str | None = None,
                divisions_moderating: list[dict] | None = None) -> dict | None:
    """Create a new user. Returns user dict or None if username taken."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        with get_db() as db:
            db.execute(
                """INSERT INTO users (username, password, roles, division_group_id, division_name, divisions_moderating)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (username, hashed, json.dumps(roles), division_group_id, division_name,
                 json.dumps(divisions_moderating or [])),
            )
        return get_user(username)
    except sqlite3.IntegrityError:
        return None


def verify_user(username: str, password: str) -> dict | None:
    """Check credentials. Returns user dict or None."""
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        return None
    if bcrypt.checkpw(password.encode("utf-8"), row["password"].encode("utf-8")):
        return _row_to_user(row)
    return None


def get_user(username: str) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def get_all_users() -> list[dict]:
    with get_db() as db:
        rows = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    return [_row_to_user(r) for r in rows]


def update_user_roles(user_id: int, roles: list[str]):
    with get_db() as db:
        db.execute("UPDATE users SET roles = ? WHERE id = ?", (json.dumps(roles), user_id))


def update_user_admin_confirmed(user_id: int, confirmed: bool):
    with get_db() as db:
        db.execute("UPDATE users SET admin_confirmed = ? WHERE id = ?", (1 if confirmed else 0, user_id))


def update_user_division_confirmed(user_id: int, confirmed: bool):
    with get_db() as db:
        db.execute("UPDATE users SET division_confirmed = ? WHERE id = ?", (1 if confirmed else 0, user_id))


def update_user_divisions_mod_confirmed(user_id: int, confirmed_divisions: list[dict]):
    with get_db() as db:
        db.execute("UPDATE users SET divisions_mod_confirmed = ? WHERE id = ?",
                   (json.dumps(confirmed_divisions), user_id))


def update_user_division(user_id: int, group_id: int | None, name: str | None):
    with get_db() as db:
        db.execute("UPDATE users SET division_group_id = ?, division_name = ?, division_confirmed = 0 WHERE id = ?",
                   (group_id, name, user_id))


def update_user_divisions_moderating(user_id: int, divisions: list[dict]):
    with get_db() as db:
        db.execute("UPDATE users SET divisions_moderating = ?, divisions_mod_confirmed = '[]' WHERE id = ?",
                   (json.dumps(divisions), user_id))


def delete_user(user_id: int):
    with get_db() as db:
        db.execute("DELETE FROM users WHERE id = ? AND is_admin = 0", (user_id,))


def _row_to_user(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "roles": json.loads(row["roles"]),
        "division_group_id": row["division_group_id"],
        "division_name": row["division_name"],
        "divisions_moderating": json.loads(row["divisions_moderating"] or "[]"),
        "admin_confirmed": bool(row["admin_confirmed"]),
        "division_confirmed": bool(row["division_confirmed"]),
        "divisions_mod_confirmed": json.loads(row["divisions_mod_confirmed"] or "[]"),
        "is_admin": bool(row["is_admin"]),
        "created_at": row["created_at"],
    }


# ──────────────────────── Scan Queue ────────────────────────

def enqueue_scan(group_id: int, include_allies: bool, include_enemies: bool, requested_by: str) -> int:
    """Add a scan to the queue. Returns queue entry ID."""
    with get_db() as db:
        # check for duplicate queued scan
        existing = db.execute(
            "SELECT id FROM scan_queue WHERE group_id = ? AND include_allies = ? AND include_enemies = ? AND status = 'queued'",
            (group_id, int(include_allies), int(include_enemies)),
        ).fetchone()
        if existing:
            return existing["id"]

        cur = db.execute(
            """INSERT INTO scan_queue (group_id, include_allies, include_enemies, requested_by)
               VALUES (?, ?, ?, ?)""",
            (group_id, int(include_allies), int(include_enemies), requested_by),
        )
        queue_id = cur.lastrowid
        _recalc_positions(db)
        return queue_id


def get_queue() -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM scan_queue WHERE status IN ('queued', 'running') ORDER BY id ASC"
        ).fetchall()
    return [_row_to_queue(r) for r in rows]


def get_queue_position(queue_id: int) -> int | None:
    with get_db() as db:
        rows = db.execute(
            "SELECT id FROM scan_queue WHERE status IN ('queued', 'running') ORDER BY id ASC"
        ).fetchall()
    for i, r in enumerate(rows):
        if r["id"] == queue_id:
            return i + 1
    return None


def get_next_queued() -> dict | None:
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM scan_queue WHERE status = 'queued' ORDER BY id ASC LIMIT 1"
        ).fetchone()
    return _row_to_queue(row) if row else None


def mark_queue_running(queue_id: int):
    with get_db() as db:
        db.execute(
            "UPDATE scan_queue SET status = 'running', started_at = datetime('now') WHERE id = ?",
            (queue_id,),
        )
        _recalc_positions(db)


def mark_queue_done(queue_id: int, scan_id: str):
    with get_db() as db:
        db.execute(
            "UPDATE scan_queue SET status = 'done', scan_id = ?, finished_at = datetime('now') WHERE id = ?",
            (scan_id, queue_id),
        )
        _recalc_positions(db)


def mark_queue_failed(queue_id: int):
    with get_db() as db:
        db.execute(
            "UPDATE scan_queue SET status = 'failed', finished_at = datetime('now') WHERE id = ?",
            (queue_id,),
        )
        _recalc_positions(db)


def get_queue_entry(queue_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM scan_queue WHERE id = ?", (queue_id,)).fetchone()
    return _row_to_queue(row) if row else None


def is_queue_running() -> bool:
    with get_db() as db:
        row = db.execute("SELECT id FROM scan_queue WHERE status = 'running' LIMIT 1").fetchone()
    return row is not None


def _recalc_positions(db):
    rows = db.execute(
        "SELECT id FROM scan_queue WHERE status IN ('queued', 'running') ORDER BY id ASC"
    ).fetchall()
    for i, r in enumerate(rows):
        db.execute("UPDATE scan_queue SET position = ? WHERE id = ?", (i + 1, r["id"]))


def _row_to_queue(row) -> dict:
    return {
        "id": row["id"],
        "group_id": row["group_id"],
        "include_allies": bool(row["include_allies"]),
        "include_enemies": bool(row["include_enemies"]),
        "requested_by": row["requested_by"],
        "status": row["status"],
        "position": row["position"],
        "scan_id": row["scan_id"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


# ──────────────────────── User Statuses ────────────────────────

VALID_STATUSES = ["Pending Review", "SEA Banned", "False Positive", "Suspicious", "Under Investigation"]
PUBLIC_STATUSES = ["SEA Banned", "False Positive"]


def set_user_status(roblox_id: str, status: str, set_by: str,
                    discord_ids: list[str] | None = None):
    """Set a global status for a roblox user. Persists across all scans."""
    if status not in VALID_STATUSES:
        return False
    discord_json = json.dumps(discord_ids or [])
    with get_db() as db:
        # if we already have discord_ids stored and none were provided, keep old ones
        if discord_ids is None:
            existing = db.execute(
                "SELECT discord_ids FROM user_statuses WHERE roblox_id = ?", (roblox_id,)
            ).fetchone()
            if existing:
                discord_json = existing["discord_ids"] or "[]"
        db.execute(
            """INSERT OR REPLACE INTO user_statuses (roblox_id, status, discord_ids, set_by, set_at)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (roblox_id, status, discord_json, set_by),
        )
    return True


def get_user_statuses_for_scan(roblox_ids: list[str]) -> dict:
    """Get global statuses for a list of roblox IDs (for displaying in a scan)."""
    if not roblox_ids:
        return {}
    with get_db() as db:
        placeholders = ",".join("?" for _ in roblox_ids)
        rows = db.execute(
            f"SELECT roblox_id, status, discord_ids, set_by, set_at FROM user_statuses WHERE roblox_id IN ({placeholders})",
            roblox_ids,
        ).fetchall()
    return {
        r["roblox_id"]: {
            "status": r["status"],
            "discord_ids": json.loads(r["discord_ids"] or "[]"),
            "set_by": r["set_by"],
            "set_at": r["set_at"],
        }
        for r in rows
    }


def get_all_user_statuses() -> dict:
    """Get all statuses, keyed by roblox_id."""
    with get_db() as db:
        rows = db.execute(
            "SELECT roblox_id, status, discord_ids, set_by, set_at FROM user_statuses"
        ).fetchall()
    return {
        r["roblox_id"]: {
            "status": r["status"],
            "discord_ids": json.loads(r["discord_ids"] or "[]"),
            "set_by": r["set_by"],
            "set_at": r["set_at"],
        }
        for r in rows
    }
