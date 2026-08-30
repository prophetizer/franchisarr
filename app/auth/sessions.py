"""Server-side browser sessions.

The cookie carries a random opaque token; the database stores only its SHA-256. A copied /config
volume or a database backup therefore cannot be replayed as a live login, and logging out deletes
the row, which revokes the session everywhere rather than merely asking one browser to forget it.

A plain hash is right here where a password hash would not be: the token is 256 bits of CSPRNG
output, so there is no guessable input for an attacker to grind against.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, col, delete, select

from app.models import User, UserSession, utcnow

logger = logging.getLogger(__name__)

COOKIE_NAME = "franchisarr_session"
SESSION_LIFETIME = timedelta(days=30)

#: Re-extending on every request would mean a write per page load. Only extend once a session is
#: past this fraction of its life, which keeps active logins alive without the write traffic.
RENEW_AFTER = 0.5


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; compare them as UTC rather than crashing."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def create_session(session: Session, user: User, *, lifetime: timedelta = SESSION_LIFETIME) -> str:
    """Start a session and return the token to put in the cookie. The token is never stored."""
    token = secrets.token_urlsafe(32)
    row = UserSession(
        token_hash=_hash_token(token),
        user_id=user.id,
        expires_at=utcnow() + lifetime,
    )
    session.add(row)
    session.commit()
    logger.info("Session created for user id=%s", user.id)
    return token


def get_session_user(session: Session, token: str | None) -> User | None:
    """Resolve a cookie token to a user, or None. Expired sessions are deleted as they're met."""
    if not token:
        return None

    row = session.exec(
        select(UserSession).where(UserSession.token_hash == _hash_token(token))
    ).first()
    if row is None:
        return None

    now = utcnow()
    if _as_utc(row.expires_at) <= now:
        session.delete(row)
        session.commit()
        logger.info("Expired session rejected for user id=%s", row.user_id)
        return None

    user = session.get(User, row.user_id)
    if user is None:
        # The account was deleted while the session was live.
        session.delete(row)
        session.commit()
        return None

    row.last_seen_at = now
    remaining = _as_utc(row.expires_at) - now
    if remaining < SESSION_LIFETIME * RENEW_AFTER:
        row.expires_at = now + SESSION_LIFETIME
    session.add(row)
    session.commit()

    return user


def delete_session(session: Session, token: str | None) -> None:
    if not token:
        return
    row = session.exec(
        select(UserSession).where(UserSession.token_hash == _hash_token(token))
    ).first()
    if row is not None:
        session.delete(row)
        session.commit()
        logger.info("Session ended for user id=%s", row.user_id)


def delete_sessions_for_user(session: Session, user_id: int) -> None:
    """Log a user out everywhere -- used when their password changes."""
    session.exec(delete(UserSession).where(col(UserSession.user_id) == user_id))
    session.commit()


def purge_expired(session: Session) -> int:
    """Housekeeping, so the table doesn't grow without bound on a long-lived install."""
    expired = session.exec(
        select(UserSession).where(col(UserSession.expires_at) <= utcnow())
    ).all()
    for row in expired:
        session.delete(row)
    session.commit()
    return len(expired)
