"""
HTTP sessions and low-level request helpers with rate limiting, retries, and 429 handling.
"""

import requests
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from scanner.constants import (
    ROTECTOR_BASE, API_KEY_HEADER, WORKER_THREADS, MAX_RETRIES,
    ROTECTOR_RATE_LIMIT, ROTECTOR_RATE_WINDOW,
    ROBLOX_RATE_LIMIT, ROBLOX_RATE_WINDOW,
    HTTP_TIMEOUT_ROTECTOR, HTTP_TIMEOUT_ROBLOX,
    HTTP_RETRY_SLEEP, HTTP_RETRY_AFTER_DEFAULT,
    DISCORD_WORKERS, GROUP_SCAN_WORKERS, ROBLOX_MEMBERSHIP_WORKERS,
)
from scanner.rate_limiter import RateLimiter

# -- rate limiters --
rotector_limiter = RateLimiter(ROTECTOR_RATE_LIMIT, ROTECTOR_RATE_WINDOW)
roblox_limiter = RateLimiter(ROBLOX_RATE_LIMIT, ROBLOX_RATE_WINDOW)
_pool_size = max(WORKER_THREADS, DISCORD_WORKERS, GROUP_SCAN_WORKERS, ROBLOX_MEMBERSHIP_WORKERS)

# -- persistent sessions for connection reuse (HTTP keep-alive) --
_rotector_session = requests.Session()
_rotector_session.headers.update({"X-Auth-Token": API_KEY_HEADER or ""})
_rotector_session.mount("https://", requests.adapters.HTTPAdapter(
    pool_connections=_pool_size, pool_maxsize=_pool_size, max_retries=0, pool_block=True,
))

_roblox_session = requests.Session()
_roblox_session.mount("https://", requests.adapters.HTTPAdapter(
    pool_connections=_pool_size, pool_maxsize=_pool_size, max_retries=0, pool_block=True,
))


def _parse_retry_after(headers: dict) -> int:
    """Parse seconds or HTTP-date Retry-After values, falling back to the default."""
    raw = headers.get("Retry-After")
    if raw is not None:
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            try:
                retry_at = parsedate_to_datetime(raw)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(0, int((retry_at - datetime.now(timezone.utc)).total_seconds()))
            except (TypeError, ValueError, IndexError, OverflowError):
                pass
    return HTTP_RETRY_AFTER_DEFAULT


def _json_or_none(resp: requests.Response) -> dict | None:
    try:
        return resp.json()
    except ValueError:
        return None


def _request_with_retry(
    session: requests.Session,
    limiter: RateLimiter,
    method: str,
    url: str,
    timeout: int,
    raise_for_status: bool = True,
    **kwargs,
) -> dict | None:
    """
    Shared retry loop used by all four API helpers.

    Waits on the rate limiter before each attempt, handles 429 with Retry-After,
    and retries on network errors up to MAX_RETRIES times.
    Returns the parsed JSON dict on success, or None after all retries are exhausted.
    """
    for attempt in range(MAX_RETRIES):
        limiter.wait()
        try:
            resp = session.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code == 429:
                time.sleep(_parse_retry_after(resp.headers))
                continue
            if raise_for_status:
                resp.raise_for_status()
                return _json_or_none(resp)
            if resp.status_code == 200:
                return _json_or_none(resp)
            return None
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(HTTP_RETRY_SLEEP)
                continue
            return None
    return None


# -- Rotector helpers --

def rotector_get(path: str, params: dict | None = None) -> dict | None:
    return _request_with_retry(
        _rotector_session, rotector_limiter, "GET",
        f"{ROTECTOR_BASE}{path}", HTTP_TIMEOUT_ROTECTOR,
        raise_for_status=True, params=params,
    )


def rotector_post(path: str, json_body: dict) -> dict | None:
    return _request_with_retry(
        _rotector_session, rotector_limiter, "POST",
        f"{ROTECTOR_BASE}{path}", HTTP_TIMEOUT_ROTECTOR,
        raise_for_status=True, json=json_body,
    )


# -- Roblox helpers --

def roblox_get(url: str, params: dict | None = None) -> dict | None:
    return _request_with_retry(
        _roblox_session, roblox_limiter, "GET",
        url, HTTP_TIMEOUT_ROBLOX,
        raise_for_status=False, params=params,
    )


def roblox_post(url: str, json_body: dict) -> dict | None:
    return _request_with_retry(
        _roblox_session, roblox_limiter, "POST",
        url, HTTP_TIMEOUT_ROBLOX,
        raise_for_status=False, json=json_body,
    )
