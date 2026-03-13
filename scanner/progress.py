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

    def reset(self):
        with self.lock:
            self._cancel.clear()
            self.status = "idle"
            self.phase = ""
            self.phase_description = ""
            self.logs = []
            self.progress = 0.0
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

    def update_eta(self):
        with self.lock:
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
                "current_group": self.current_group,
                "groups_done": self.groups_done,
                "groups_total": self.groups_total,
                "users_checked": self.users_checked,
                "users_total": self.users_total,
                "flagged_found": self.flagged_found,
                "discord_ids_found": self.discord_ids_found,
                "scan_id": self.scan_id,
                "eta_seconds": round(self.eta_seconds, 0) if self.eta_seconds is not None else None,
            }


# single global instance shared by engine, app, and CLI
scan_progress = ScanProgress()
