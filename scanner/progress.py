"""
Shows ETA on scan's progress.
"""

import threading
import time
from datetime import datetime


class ScanProgress:
    def __init__(self):
        self.lock = threading.Lock()
        self._cancel = threading.Event()
        self.status = "idle"
        self.phase = ""
        self.phase_description = ""
        self.logs: list[str] = []
        self.progress = 0.0
        self.work_done = 0.0
        self.work_total = 0.0
        self.current_group = ""
        self.groups_done = 0
        self.groups_total = 0
        self.users_checked = 0
        self.users_total = 0
        self.flagged_found = 0
        self.discord_ids_found = 0
        self.scan_id: str | None = None
        self.eta_seconds: float | None = None
        self.start_time: float | None = None
        self.requested_by: str | None = None

    def reset(self):
        with self.lock:
            self._cancel.clear()
            self.status = "idle"
            self.phase = ""
            self.phase_description = ""
            self.logs = []
            self.progress = 0.0
            self.work_done = 0.0
            self.work_total = 0.0
            self.current_group = ""
            self.groups_done = 0
            self.groups_total = 0
            self.users_checked = 0
            self.users_total = 0
            self.flagged_found = 0
            self.discord_ids_found = 0
            self.scan_id = None
            self.eta_seconds = None
            self.start_time = None
            self.requested_by = None

    def cancel(self):
        self._cancel.set()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def log(self, msg: str):
        with self.lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self.logs.append(f"[{ts}] {msg}")

    def set_phase(self, phase: str, description: str = ""):
        with self.lock:
            self.phase = phase
            self.phase_description = description

    def set_work(self, done: float = 0.0, total: float = 0.0):
        with self.lock:
            self.work_done = max(0.0, float(done))
            self.work_total = max(0.0, float(total))
            self._update_progress_locked()

    def add_work_total(self, units: float):
        if units <= 0:
            return
        with self.lock:
            self.work_total += float(units)
            self._update_progress_locked()

    def advance_work(self, units: float = 1.0):
        if units <= 0:
            return
        with self.lock:
            self.work_done += float(units)
            if self.work_done > self.work_total:
                self.work_total = self.work_done
            self._update_progress_locked()

    def _update_progress_locked(self):
        if self.work_total <= 0:
            self.progress = 0.0
        else:
            calculated = min(99.0, (self.work_done / self.work_total) * 100)
            # Work can be discovered during a scan. Never move the visible bar backwards.
            self.progress = max(self.progress, calculated)
        self._update_eta_locked()

    def update_eta(self):
        with self.lock:
            self._update_eta_locked()

    def _update_eta_locked(self):
        if not self.start_time or self.progress <= 0:
            self.eta_seconds = None
            return
        elapsed = time.time() - self.start_time
        if self.progress >= 100:
            self.eta_seconds = 0
            return
        rate = elapsed / self.progress
        remaining = (100 - self.progress) * rate
        self.eta_seconds = remaining

    def to_dict(self, log_cursor: int = 0) -> dict:
        with self.lock:
            all_logs = self.logs
            new_logs = all_logs[log_cursor:] if log_cursor < len(all_logs) else []
            return {
                "status": self.status,
                "phase": self.phase,
                "phase_description": self.phase_description,
                "log_count": len(all_logs),
                "logs": new_logs,
                "progress": round(self.progress, 1),
                "work_done": round(self.work_done, 1),
                "work_total": round(self.work_total, 1),
                "current_group": self.current_group,
                "groups_done": self.groups_done,
                "groups_total": self.groups_total,
                "users_checked": self.users_checked,
                "users_total": self.users_total,
                "flagged_found": self.flagged_found,
                "discord_ids_found": self.discord_ids_found,
                "scan_id": self.scan_id,
                "eta_seconds": round(self.eta_seconds, 0) if self.eta_seconds is not None else None,
                "requested_by": self.requested_by,
            }


# single global instance shared by engine, app, and CLI
scan_progress = ScanProgress()
