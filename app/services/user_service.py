"""Who has an account here, and taking access away.

Accounts are created by signing in (Plex, Jellyfin, Emby) or from ADMIN_USERNAME, never by hand,
so there is nothing to add -- only to end: an account's sessions, its API key, or the account.
Removing someone who can still reach the server doesn't stop them signing in again; the sign-in
rules (admins only unless members are allowed) are what decide that.
"""

from __future__ import annotations

import logging

from sqlmodel import Session, col, select, update

from app.auth.api_keys import revoke_api_key
from app.auth.sessions import delete_sessions_for_user
from app.models import ActivityLogEntry, DismissedItem, User, UserPreference, UserSession

logger = logging.getLogger(__name__)


class CannotRemove(ValueError):
    pass


def list_users(session: Session) -> list[dict]:
    sessions: dict[int, int] = {}
    for user_id in session.exec(select(UserSession.user_id)).all():
        sessions[user_id] = sessions.get(user_id, 0) + 1
    return [
        {
            "id": user.id,
            "name": user.external_username or user.local_username or f"user {user.id}",
            "provider": user.auth_provider or "local",
            "is_admin": user.is_admin,
            "sessions": sessions.get(user.id, 0),
            "has_api_key": bool(user.api_key),
            "created_at": user.created_at,
        }
        for user in session.exec(select(User).order_by(col(User.id))).all()
    ]


def end_sessions(session: Session, user_id: int) -> None:
    delete_sessions_for_user(session, user_id)
    logger.info("Ended every session of user id=%s", user_id)


def revoke_key(session: Session, user_id: int) -> None:
    user = session.get(User, user_id)
    if user is not None:
        revoke_api_key(session, user)


def remove(session: Session, user_id: int, *, acting_user_id: int) -> None:
    """Delete an account, its sessions and its own dismissals. Shared data it created (spin-off
    mappings, collection excludes) stays, and the activity log keeps the entries, unattributed."""
    if user_id == acting_user_id:
        raise CannotRemove("You can't remove your own account while signed in with it.")
    user = session.get(User, user_id)
    if user is None:
        return
    admins = session.exec(select(User).where(col(User.is_admin) == True)).all()  # noqa: E712
    if user.is_admin and len(admins) <= 1:
        raise CannotRemove("That's the only administrator left.")
    delete_sessions_for_user(session, user_id)
    for model in (DismissedItem, UserPreference):
        for row in session.exec(select(model).where(col(model.user_id) == user_id)).all():
            session.delete(row)
    session.exec(update(ActivityLogEntry).where(col(ActivityLogEntry.triggered_by) == user_id)
                 .values(triggered_by=None))
    session.delete(user)
    session.commit()
    logger.info("Removed user id=%s", user_id)
