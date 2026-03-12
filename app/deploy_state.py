"""
Deployment banner management
"""

import threading
import time

_deploy_lock = threading.Lock()
_deploy_state = {
    "pending": False,
    "message": "",
    "notified_at": None,
}


def get_deploy_state() -> dict:
    with _deploy_lock:
        return dict(_deploy_state)


def set_deploy_pending(message: str = ""):
    with _deploy_lock:
        _deploy_state["pending"] = True
        _deploy_state["message"] = message or "A new update is being deployed. The site will refresh shortly."
        _deploy_state["notified_at"] = time.time()


def clear_deploy_pending():
    with _deploy_lock:
        _deploy_state["pending"] = False
        _deploy_state["message"] = ""
        _deploy_state["notified_at"] = None
