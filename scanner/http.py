"""
HTTP sessions and low-level request helpers with rate limiting, retries, and 429 handling.
"""

import requests
import time

from scanner.constants import (
    ROTECTOR_BASE, API_KEY_HEADER, WORKER_THREADS, MAX_RETRIES,
)
from scanner.rate_limiter import RateLimiter
from scanner.constants import (
    ROTECTOR_RATE_LIMIT, ROTECTOR_RATE_WINDOW,
    ROBLOX_RATE_LIMIT, ROBLOX_RATE_WINDOW,
)

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


# -- Rotector helpers --

def rotector_get(path: str, params: dict | None = None) -> dict | None:
    url = f"{ROTECTOR_BASE}{path}"
    for attempt in range(MAX_RETRIES):
        rotector_limiter.wait()
        try:
            resp = _rotector_session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 5))
                time.sleep(retry)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            return None
    return None


def rotector_post(path: str, json_body: dict) -> dict | None:
    url = f"{ROTECTOR_BASE}{path}"
    for attempt in range(MAX_RETRIES):
        rotector_limiter.wait()
        try:
            resp = _rotector_session.post(url, json=json_body, timeout=30)
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 5))
                time.sleep(retry)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            return None
    return None


# -- Roblox helpers --

def roblox_get(url: str, params: dict | None = None) -> dict | None:
    for attempt in range(MAX_RETRIES):
        roblox_limiter.wait()
        try:
            resp = _roblox_session.get(url, params=params, timeout=20)
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 5))
                time.sleep(retry)
                continue
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            return None
    return None


def roblox_post(url: str, json_body: dict) -> dict | None:
    for attempt in range(MAX_RETRIES):
        roblox_limiter.wait()
        try:
            resp = _roblox_session.post(url, json=json_body, timeout=20)
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 5))
                time.sleep(retry)
                continue
            if resp.status_code == 200:
                return resp.json()
            return None
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            return None
    return None
