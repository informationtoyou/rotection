"""
SQLite-backed scan cache.

Migrates any existing scan_cache.json on first use, then all reads/writes
go through SQLite.  The public API that the rest of the codebase relies on
is kept identical:
    load_cache, save_cache, get_previous_scans, get_scan_by_id

New helpers:
    save_scan, delete_scan_by_id, tag_scan_field
"""

import json
import os
import sqlite3
import threading

from scanner.constants import CACHE_FILE          # "scan_cache.json"

CACHE_DB = "scan_cache.db"
_local = threading.local()                        # one connection per thread


# ─────────────────────── connection helpers ───────────────────────

def _get_conn() -> sqlite3.Connection:
    """Return a per-thread SQLite connection (created once, reused)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(CACHE_DB, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return conn


def _init_db():
    """Create the scans table if it doesn't exist."""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id                TEXT PRIMARY KEY,
            timestamp         TEXT,
            primary_group_id  INTEGER,
            primary_group_name TEXT,
            include_allies    INTEGER,
            include_enemies   INTEGER,
            total_flagged     INTEGER,
            total_discord_ids INTEGER,
            requested_by      TEXT,
            data              TEXT NOT NULL
        )
    """)
    conn.commit()


# ─────────────────────── JSON migration ───────────────────────

def _maybe_migrate_json():
    """If scan_cache.json exists, import every scan into SQLite then rename it."""
    if not os.path.exists(CACHE_FILE):
        return
    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, IOError):
        return

    scans = cache.get("scans", [])
    if not scans:
        # empty json — just remove it
        os.rename(CACHE_FILE, CACHE_FILE + ".migrated")
        return

    conn = _get_conn()
    for s in scans:
        scan_id = s.get("id", "")
        if not scan_id:
            continue
        # skip if already imported (idempotent)
        row = conn.execute("SELECT 1 FROM scans WHERE id = ?", (scan_id,)).fetchone()
        if row:
            continue
        conn.execute(
            """INSERT INTO scans
               (id, timestamp, primary_group_id, primary_group_name,
                include_allies, include_enemies,
                total_flagged, total_discord_ids, requested_by, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scan_id,
                s.get("timestamp", ""),
                s.get("primary_group_id", 0),
                s.get("primary_group_name", ""),
                int(s.get("include_allies", False)),
                int(s.get("include_enemies", False)),
                s.get("total_flagged", 0),
                s.get("total_discord_ids", 0),
                s.get("requested_by", ""),
                json.dumps(s, separators=(",", ":"), default=str),
            ),
        )
    conn.commit()
    os.rename(CACHE_FILE, CACHE_FILE + ".migrated")


# run once at import time
_init_db()
_maybe_migrate_json()


# ─────────────────────── public API (kept compatible) ───────────────────────

def load_cache() -> dict:
    """Return the full cache as a dict with a 'scans' list.
    Kept for backward compat — prefer the per-scan helpers below."""
    conn = _get_conn()
    rows = conn.execute("SELECT data FROM scans ORDER BY rowid").fetchall()
    scans = [json.loads(r["data"]) for r in rows]
    return {"scans": scans, "groups": {}}


def save_cache(cache: dict):
    """Overwrite the entire DB from a dict with a 'scans' list.
    Kept for backward compat — prefer save_scan / delete_scan_by_id."""
    conn = _get_conn()
    conn.execute("DELETE FROM scans")
    for s in cache.get("scans", []):
        scan_id = s.get("id", "")
        if not scan_id:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO scans
               (id, timestamp, primary_group_id, primary_group_name,
                include_allies, include_enemies,
                total_flagged, total_discord_ids, requested_by, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scan_id,
                s.get("timestamp", ""),
                s.get("primary_group_id", 0),
                s.get("primary_group_name", ""),
                int(s.get("include_allies", False)),
                int(s.get("include_enemies", False)),
                s.get("total_flagged", 0),
                s.get("total_discord_ids", 0),
                s.get("requested_by", ""),
                json.dumps(s, separators=(",", ":"), default=str),
            ),
        )
    conn.commit()


def get_previous_scans() -> list[dict]:
    """Return lightweight summaries for every scan (newest first)."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT id, timestamp, primary_group_id, primary_group_name,
                  include_allies, include_enemies,
                  total_flagged, total_discord_ids, requested_by
           FROM scans ORDER BY rowid DESC"""
    ).fetchall()
    summaries = []
    for r in rows:
        summaries.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "primary_group": r["primary_group_name"] or "Unknown",
            "primary_group_id": r["primary_group_id"],
            "include_allies": bool(r["include_allies"]),
            "include_enemies": bool(r["include_enemies"]),
            "requested_by": r["requested_by"] or "",
            "groups_scanned": 0,  # filled below if needed
            "total_flagged": r["total_flagged"],
            "total_discord_ids": r["total_discord_ids"],
        })
    # fill in groups_scanned from the JSON blob (cheap parse of just that key)
    # only for the summaries — we avoid loading the full blob here
    for summary in summaries:
        conn2 = _get_conn()
        row = conn2.execute("SELECT data FROM scans WHERE id = ?", (summary["id"],)).fetchone()
        if row:
            try:
                full = json.loads(row["data"])
                summary["groups_scanned"] = len(full.get("groups", {}))
            except Exception:
                pass
    return summaries


def get_scan_by_id(scan_id: str) -> dict | None:
    """Return full scan dict, or None."""
    conn = _get_conn()
    row = conn.execute("SELECT data FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if row:
        return json.loads(row["data"])
    return None


# ─────────────────────── new per-scan helpers ───────────────────────

def save_scan(scan: dict, max_scans: int = 20):
    """Insert or replace a single scan.  Trims old scans beyond max_scans."""
    scan_id = scan.get("id", "")
    if not scan_id:
        return
    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO scans
           (id, timestamp, primary_group_id, primary_group_name,
            include_allies, include_enemies,
            total_flagged, total_discord_ids, requested_by, data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            scan_id,
            scan.get("timestamp", ""),
            scan.get("primary_group_id", 0),
            scan.get("primary_group_name", ""),
            int(scan.get("include_allies", False)),
            int(scan.get("include_enemies", False)),
            scan.get("total_flagged", 0),
            scan.get("total_discord_ids", 0),
            scan.get("requested_by", ""),
            json.dumps(scan, separators=(",", ":"), default=str),
        ),
    )
    # trim oldest scans beyond the cap
    count = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    if count > max_scans:
        conn.execute(
            "DELETE FROM scans WHERE id IN "
            "(SELECT id FROM scans ORDER BY rowid LIMIT ?)",
            (count - max_scans,),
        )
    conn.commit()


def delete_scan_by_id(scan_id: str) -> bool:
    """Delete a scan. Returns True if a row was actually removed."""
    conn = _get_conn()
    cur = conn.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
    conn.commit()
    return cur.rowcount > 0


def find_duplicate_scan(primary_group_id: int, include_allies: bool,
                        include_enemies: bool) -> str | None:
    """Return the scan_id of an existing scan with matching params, or None."""
    conn = _get_conn()
    row = conn.execute(
        """SELECT id FROM scans
           WHERE primary_group_id = ?
             AND include_allies = ?
             AND include_enemies = ?
           LIMIT 1""",
        (primary_group_id, int(include_allies), int(include_enemies)),
    ).fetchone()
    return row["id"] if row else None


def tag_scan_field(scan_id: str, field: str, value):
    """Set a single top-level field on a scan's JSON blob (e.g. requested_by)."""
    conn = _get_conn()
    row = conn.execute("SELECT data FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if not row:
        return
    scan = json.loads(row["data"])
    scan[field] = value
    # also update the indexed column if it exists
    col_update = ""
    params: list = [json.dumps(scan, separators=(",", ":"), default=str)]
    if field == "requested_by":
        col_update = ", requested_by = ?"
        params.append(value)
    params.append(scan_id)
    conn.execute(f"UPDATE scans SET data = ?{col_update} WHERE id = ?", params)
    conn.commit()
