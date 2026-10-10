"""Encryption at rest for credentials companies enter in Settings (SMTP and
mailbox passwords, WhatsApp/SMS API tokens).

Values are Fernet tokens (AES-128-CBC + HMAC). The key comes from
CREDENTIALS_KEY; when that isn't set (local development) it is derived
from JWT_SECRET so things still work, but production should set its own
key and keep it as safe as the database backup.
"""
import base64
import hashlib
import json
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_PREFIX = "gAAAA"  # every Fernet token starts like this


@lru_cache
def _fernet() -> Fernet:
    key = settings.CREDENTIALS_KEY
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256(f"credentials:{settings.JWT_SECRET}".encode()).digest()).decode()
    return Fernet(key)


def encrypt(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    """Decrypts a stored secret. Values saved before encryption existed are
    plain text and are returned as they are."""
    if not value or not value.startswith(_PREFIX):
        return value
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        # Wrong key (e.g. CREDENTIALS_KEY changed): treat as not set rather
        # than crash; the company re-enters it in Settings.
        return None


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        return json.loads(_fernet().decrypt(value.encode()))
    except (InvalidToken, ValueError):
        return {}
