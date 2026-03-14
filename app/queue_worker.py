"""
Queueing system for all the scans
"""

import threading
import time
import traceback
from datetime import datetime, timezone

from scanner.progress import scan_progress
from scanner.engine import _scan_worker
from app.database import (
    get_next_queued, mark_queue_running, mark_queue_done, mark_queue_failed,
    is_queue_running,
)

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


def _queue_loop():
    """Main loop: pick next queued scan, run it, repeat. Sleep when idle."""
    while True:
        try:
            entry = get_next_queued()
            if not entry:
                # nothing to do — sleep until woken or 30s timeout
                _wake_event.clear()
                _wake_event.wait(timeout=30)
                continue

            queue_id = entry["id"]
            group_id = entry["group_id"]
            include_allies = entry["include_allies"]
            include_enemies = entry["include_enemies"]

            # mark as running
            mark_queue_running(queue_id)
            scan_progress.reset()
            scan_progress.status = "scanning"
            scan_progress.requested_by = entry["requested_by"]

            # run the scan directly (blocks this thread)
            try:
                _scan_worker(group_id, include_allies, include_enemies)

                if scan_progress.status == "done" and scan_progress.scan_id:
                    # store who requested it in the scan cache
                    _tag_scan_requester(scan_progress.scan_id, entry["requested_by"])
                    mark_queue_done(queue_id, scan_progress.scan_id)
                else:
                    mark_queue_failed(queue_id)
            except Exception as e:
                scan_progress.status = "error"
                scan_progress.log(f"QUEUE ERROR: {e}")
                scan_progress.log(traceback.format_exc())
                mark_queue_failed(queue_id)

            # brief pause between scans to avoid CPU spike on PythonAnywhere
            time.sleep(2)

        except Exception:
            time.sleep(5)


def _tag_scan_requester(scan_id: str, username: str):
    """Add requested_by field to the cached scan result."""
    try:
        from scanner.cache import tag_scan_field
        tag_scan_field(scan_id, "requested_by", username)
    except Exception:
        pass
