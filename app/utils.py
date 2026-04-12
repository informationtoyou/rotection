"""
Shared utilities for Flask route handlers.
"""

import logging
from flask import request

logger = logging.getLogger(__name__)


def get_json_body() -> dict:
    """Parse the JSON request body, returning an empty dict on missing or invalid JSON."""
    return request.get_json(force=True, silent=True) or {}


def safe_audit(actor_id, event: str, obj: str | None = None, details: str | None = None) -> None:
    """
    Write an audit log entry, emitting a warning instead of silently swallowing failures.
    This ensures audit failures are visible in logs rather than disappearing without a trace.
    """
    from app.database import log_audit
    try:
        log_audit(actor_id, event, obj=obj, details=details)
    except Exception as exc:
        logger.warning("Audit log failed [%s obj=%s]: %s", event, obj, exc)
