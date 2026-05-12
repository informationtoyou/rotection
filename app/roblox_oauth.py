"""
Roblox OAuth helpers (Open Cloud OAuth 2.0 / OIDC).
"""

from __future__ import annotations

import os
import time
import urllib.parse
from typing import Optional

import requests


def get_oauth_config() -> dict | None:
    client_id = os.getenv("ROBLOX_OAUTH_CLIENT_ID")
    client_secret = os.getenv("ROBLOX_OAUTH_CLIENT_SECRET")
    redirect_uri = os.getenv("ROBLOX_OAUTH_REDIRECT_URI")
    authorize_url = os.getenv("ROBLOX_OAUTH_AUTHORIZE_URL", "https://apis.roblox.com/oauth/v1/authorize")
    token_url = os.getenv("ROBLOX_OAUTH_TOKEN_URL", "https://apis.roblox.com/oauth/v1/token")
    userinfo_url = os.getenv("ROBLOX_OAUTH_USERINFO_URL", "https://apis.roblox.com/oauth/v1/userinfo")
    scope = os.getenv("ROBLOX_OAUTH_SCOPE", "openid profile")
    if not client_id or not client_secret or not redirect_uri:
        return None
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "authorize_url": authorize_url,
        "token_url": token_url,
        "userinfo_url": userinfo_url,
        "scope": scope,
    }


def build_authorize_url(state: str) -> str:
    cfg = get_oauth_config()
    if not cfg:
        raise ValueError("OAuth config missing")
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": cfg["scope"],
        "state": state,
    }
    return cfg["authorize_url"] + "?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict | None:
    cfg = get_oauth_config()
    if not cfg:
        return None
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg["redirect_uri"],
        "client_id": cfg["client_id"],
    }
    try:
        resp = requests.post(
            cfg["token_url"],
            data=data,
            auth=(cfg["client_id"], cfg["client_secret"]),
            headers={"Accept": "application/json"},
            timeout=20,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    token = resp.json()
    if "expires_in" in token:
        try:
            token["expires_at"] = int(time.time()) + int(token["expires_in"])
        except (TypeError, ValueError):
            token["expires_at"] = None
    return token


def refresh_access_token(refresh_token: str) -> dict | None:
    cfg = get_oauth_config()
    if not cfg:
        return None
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": cfg["client_id"],
    }
    try:
        resp = requests.post(
            cfg["token_url"],
            data=data,
            auth=(cfg["client_id"], cfg["client_secret"]),
            headers={"Accept": "application/json"},
            timeout=20,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    token = resp.json()
    if "expires_in" in token:
        try:
            token["expires_at"] = int(time.time()) + int(token["expires_in"])
        except (TypeError, ValueError):
            token["expires_at"] = None
    return token


def fetch_userinfo(access_token: str) -> Optional[dict]:
    cfg = get_oauth_config()
    if not cfg:
        return None
    try:
        resp = requests.get(
            cfg["userinfo_url"],
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    return resp.json()
