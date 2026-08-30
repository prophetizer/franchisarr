"""Per-user API keys for the CLI and any future non-browser client.

The CLI is a thin HTTP client against this app's own API rather than a direct database caller
(PROJECT_PLAN.md decision log), so it needs a credential of its own: `docker exec franchisarr
cli.py scan movies` has no browser session to borrow.

Unlike session tokens, the key itself is stored. It has to be: the user keeps it in a config file
or an env var and sends it verbatim, and there is no login step in which to exchange it for
something else. It is therefore treated as a secret everywhere it appears -- masked in the UI,
registered for log redaction, and shown in full exactly once, when generated.
"""

from __future__ import annotations

import logging
import secrets

from sqlmodel import Session, col, select

from app.logging_config import register_secret
from app.models import User

logger = logging.getLogger(__name__)

#: Long enough that guessing is hopeless, short enough to paste into a compose file.
KEY_BYTES = 32


def generate_api_key(session: Session, user: User) -> str:
    """Issue a new key for this user, replacing any previous one."""
    key = secrets.token_urlsafe(KEY_BYTES)
    user.api_key = key
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
        select(User).where(col(User.api_key) == api_key.strip())
    ).first()
