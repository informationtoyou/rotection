"""
Queueing system for all the scans
"""

import json
import logging
import threading
import time
import traceback

from scanner.constants import QUEUE_WORKER_POLL_TIMEOUT, QUEUE_INTER_SCAN_SLEEP, QUEUE_ERROR_BACKOFF
from scanner.progress import scan_progress
from scanner.engine import _scan_worker
from app.database import (
    get_next_queued, mark_queue_running, mark_queue_done, mark_queue_failed,
    get_user,
)
from app.utils import safe_audit

logger = logging.getLogger(__name__)

_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()
_wake_event = threading.Event()


def maybe_start_worker():
    """Start the queue worker thread if not already running."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            _wake_event.set()  # wake it up to check for new work
            return
        _worker_thread = threading.Thread(target=_queue_loop, daemon=True)
        _worker_thread.start()


def _resolve_actor_id(username: str | None) -> int | None:
    """Look up the numeric user ID for a username, returning None on failure."""
    if not username:
        return None
    try:
        actor = get_user(username)
        return actor["id"] if actor else None
    except Exception:
        return None


def _queue_loop():
    """Main loop: pick next queued scan, run it, repeat. Sleep when idle."""
    while True:
        try:
            entry = get_next_queued()
            if not entry:
                # nothing to do — sleep until woken or timeout
                _wake_event.clear()
                _wake_event.wait(timeout=QUEUE_WORKER_POLL_TIMEOUT)
                continue

            queue_id = entry["id"]
            group_id = entry["group_id"]
            include_allies = entry["include_allies"]
            include_enemies = entry["include_enemies"]
            requester = entry.get("requested_by")

            mark_queue_running(queue_id)
            scan_progress.reset()
            scan_progress.status = "scanning"
            scan_progress.requested_by = requester

            actor_id = _resolve_actor_id(requester)
            safe_audit(actor_id, "scan_started", obj=str(queue_id),
                       details=json.dumps({"group_id": group_id, "include_allies": include_allies,
                                           "include_enemies": include_enemies}))

            try:
                _scan_worker(group_id, include_allies, include_enemies)

                if scan_progress.status == "done" and scan_progress.scan_id:
                    _tag_scan_requester(scan_progress.scan_id, requester)
                    mark_queue_done(queue_id, scan_progress.scan_id)
                    safe_audit(actor_id, "scan_completed", obj=scan_progress.scan_id,
                               details=json.dumps({"queue_id": queue_id, "group_id": group_id}))
                else:
                    mark_queue_failed(queue_id)
                    safe_audit(actor_id, "scan_failed", obj=str(queue_id),
                               details=json.dumps({"queue_id": queue_id, "group_id": group_id}))

            except Exception as e:
                scan_progress.status = "error"
                scan_progress.log(f"QUEUE ERROR: {e}")
                scan_progress.log(traceback.format_exc())
                mark_queue_failed(queue_id)
                logger.exception("Scan worker raised an unexpected error (queue_id=%s)", queue_id)
                safe_audit(actor_id, "scan_error", obj=str(queue_id), details=str(e)[:512])

            # brief pause between scans to avoid CPU spike on PythonAnywhere
            time.sleep(QUEUE_INTER_SCAN_SLEEP)

        except Exception:
            logger.exception("Unexpected error in queue loop")
            time.sleep(QUEUE_ERROR_BACKOFF)


def _tag_scan_requester(scan_id: str, username: str):
    """Add requested_by field to the cached scan result."""
    try:
        from scanner.cache import tag_scan_field
        tag_scan_field(scan_id, "requested_by", username)
    except Exception:
        pass
