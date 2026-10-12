"""Encryption at rest for secrets stored in the database (WhatsApp tokens and app secrets).

A copied or leaked database alone does not reveal them: the key lives in the server
environment (ENCRYPTION_KEY, or derived from SECRET_KEY when not set).
"""

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from .config import get_settings

log = logging.getLogger(__name__)
PREFIX = "enc:v1:"


@lru_cache
def _fernet() -> Fernet:
    s = get_settings()
    if s.encryption_key:
        return Fernet(s.encryption_key.encode())
    digest = hashlib.sha256(f"travel-ai-encryption:{s.secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str | None) -> str | None:
    if not value or value.startswith(PREFIX):
        return value
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    if not value or not value.startswith(PREFIX):
        return value  # empty, or written before encryption existed
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        log.error("A stored secret cannot be decrypted (was SECRET_KEY/ENCRYPTION_KEY changed?). Re-enter it.")
        return None


class EncryptedText(TypeDecorator):
    """A text column that is encrypted in the database and plain in Python."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt(value)

    def process_result_value(self, value, dialect):
        return decrypt(value)
