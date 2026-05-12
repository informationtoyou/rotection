"""
Roblox authenticated actions using OAuth access tokens.
"""

from __future__ import annotations

import logging
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

ROBLOX_USERS_AUTH = "https://users.roblox.com/v1/users/authenticated"
ROBLOX_GROUP_MEMBER = "https://groups.roblox.com/v1/groups/{group_id}/users/{user_id}"


def build_session(access_token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Rotection/1.0",
        "Authorization": f"Bearer {access_token}",
    })
    return s


def get_authenticated_user(access_token: str) -> dict | None:
    session = build_session(access_token)
    try:
        resp = session.get(ROBLOX_USERS_AUTH, timeout=15)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    return resp.json()


def remove_users_from_group(
    access_token: str,
    group_id: int,
    user_ids: Iterable[int],
) -> dict:
    """
    Remove a list of users from a group. Returns summary dict.
    """
    ids = [int(uid) for uid in user_ids if int(uid) > 0]
    if not ids:
        return {"removed": [], "failed": {}, "skipped": []}

    session = build_session(access_token)

    removed = []
    failed = {}
    for uid in ids:
        url = ROBLOX_GROUP_MEMBER.format(group_id=group_id, user_id=uid)
        try:
            resp = session.delete(url, timeout=20)
        except requests.RequestException:
            failed[uid] = "network_error"
            continue
        if resp.status_code in (200, 204):
            removed.append(uid)
            continue
        if resp.status_code == 403:
            failed[uid] = "forbidden"
            continue
        if resp.status_code == 404:
            failed[uid] = "not_in_group"
            continue
        failed[uid] = f"http_{resp.status_code}"

    return {"removed": removed, "failed": failed, "skipped": []}
