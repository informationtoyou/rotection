"""
Small encryption helper for storing sensitive tokens.
"""

import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


def _derive_key(raw: str) -> bytes:
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Optional[Fernet]:
    """
    Return a Fernet instance from the configured encryption key or SECRET_KEY.

    If an encryption key is provided, it can be either a valid Fernet key
    or any string (which will be SHA256-derived into a Fernet key).
    """
    raw_key = os.getenv("ROTECTION_ENCRYPTION_KEY")
    if raw_key:
        key_bytes = raw_key.encode("utf-8")
        if len(key_bytes) != 44:
            key_bytes = _derive_key(raw_key)
        return Fernet(key_bytes)

    secret = os.getenv("SECRET_KEY")
    if secret:
        return Fernet(_derive_key(secret))

    return None


def encrypt_secret(value: str) -> str:
    fernet = _get_fernet()
    if not fernet:
        raise ValueError("Encryption key not configured")
    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    fernet = _get_fernet()
    if not fernet:
        raise ValueError("Encryption key not configured")
    try:
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid encryption token") from exc
