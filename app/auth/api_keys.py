"""Per-user API keys for the CLI and any future non-browser client.

The CLI is a thin HTTP client against this app's own API rather than a direct database caller
(docs/DESIGN.md decision log), so it needs a credential of its own: `docker exec franchisarr
cli.py scan movies` has no browser session to borrow.

Stored as a SHA-256 hash, like session tokens: the server only ever compares a key, so it never
needs the key itself, and a copy of the database (a backup, a stolen disk) hands over nothing
usable. Until 0.26.0 the key was stored as-is; migration 0023 hashed the existing ones, and the
keys people already hold keep working because an incoming key is hashed before the lookup.
A key is shown in full exactly once, when generated.
"""

from __future__ import annotations

import hashlib
import logging
import secrets

from sqlmodel import Session, col, select

from app.logging_config import register_secret
from app.models import User

logger = logging.getLogger(__name__)

#: Long enough that guessing is hopeless, short enough to paste into a compose file.
KEY_BYTES = 32


#: Marks a stored value as a hash, so migration 0023 can tell hashed rows from old plaintext ones.
HASH_PREFIX = "sha256:"


def hash_api_key(key: str) -> str:
    return HASH_PREFIX + hashlib.sha256(key.strip().encode("utf-8")).hexdigest()


def generate_api_key(session: Session, user: User) -> str:
    """Issue a new key for this user, replacing any previous one. Returns the only plaintext copy."""
    key = secrets.token_urlsafe(KEY_BYTES)
    user.api_key = hash_api_key(key)
    session.add(user)
    session.commit()
    register_secret(key)
    logger.info("Issued a new API key for user id=%s", user.id)
    return key


def revoke_api_key(session: Session, user: User) -> None:
    user.api_key = None
    session.add(user)
    session.commit()
    logger.info("Revoked the API key for user id=%s", user.id)


def find_user_by_api_key(session: Session, api_key: str | None) -> User | None:
    if not api_key or not api_key.strip():
        return None
    return session.exec(
        select(User).where(col(User.api_key) == hash_api_key(api_key))
    ).first()
