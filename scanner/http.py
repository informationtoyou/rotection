"""
HTTP sessions and low-level request helpers with rate limiting, retries, and 429 handling.
"""

import requests
import time

from scanner.constants import (
    ROTECTOR_BASE, API_KEY_HEADER, WORKER_THREADS, MAX_RETRIES,
    ROTECTOR_RATE_LIMIT, ROTECTOR_RATE_WINDOW,
    ROBLOX_RATE_LIMIT, ROBLOX_RATE_WINDOW,
    HTTP_TIMEOUT_ROTECTOR, HTTP_TIMEOUT_ROBLOX,
    HTTP_RETRY_SLEEP, HTTP_RETRY_AFTER_DEFAULT,
)
from scanner.rate_limiter import RateLimiter

# -- rate limiters --
rotector_limiter = RateLimiter(ROTECTOR_RATE_LIMIT, ROTECTOR_RATE_WINDOW)
roblox_limiter = RateLimiter(ROBLOX_RATE_LIMIT, ROBLOX_RATE_WINDOW)

# -- persistent sessions for connection reuse (HTTP keep-alive) --
_rotector_session = requests.Session()
_rotector_session.headers.update({"X-Auth-Token": API_KEY_HEADER or ""})
_rotector_session.mount("https://", requests.adapters.HTTPAdapter(
    pool_connections=WORKER_THREADS, pool_maxsize=WORKER_THREADS, max_retries=0,
))

_roblox_session = requests.Session()
_roblox_session.mount("https://", requests.adapters.HTTPAdapter(
    pool_connections=WORKER_THREADS, pool_maxsize=WORKER_THREADS, max_retries=0,
))


def _parse_retry_after(headers: dict) -> int:
    """Parse the Retry-After header, falling back to the default if missing or non-integer."""
    raw = headers.get("Retry-After")
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            pass
    return HTTP_RETRY_AFTER_DEFAULT


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
                return resp.json()
            if resp.status_code == 200:
                return resp.json()
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
