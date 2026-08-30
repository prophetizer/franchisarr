"""Local admin account -- the fallback login and recovery path.

Plex sign-in is the primary route, but it depends on plex.tv being reachable and on the Plex
server being configured. This account is what gets you in when neither is true: a fresh install
before Plex is set up, an offline network, or a plex.tv outage. It is the reason a misconfigured
Plex connection cannot lock an owner out of their own install.
"""

from __future__ import annotations

import logging

from sqlmodel import Session, col, select

from app.auth.passwords import hash_password, verify_password
from app.config import EnvSettings
from app.models import User

logger = logging.getLogger(__name__)


def get_local_admin(session: Session, username: str) -> User | None:
    return session.exec(
        select(User).where(col(User.local_username) == username.strip().lower())
    ).first()


def has_local_admin(session: Session) -> bool:
    return session.exec(select(User).where(col(User.local_username).is_not(None))).first() is not None


def create_local_admin(session: Session, username: str, password: str) -> User:
    user = User(
        local_username=username.strip().lower(),
        password_hash=hash_password(password),
        is_admin=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    logger.info("Local admin account %r created", user.local_username)
    return user


def authenticate_local(session: Session, username: str, password: str) -> User | None:
    """Verify a username/password pair.

    A missing account still runs a hash comparison, so "no such user" and "wrong password" take
    the same time and the login form can't be used to enumerate account names.
    """
    user = get_local_admin(session, username) if username else None
    stored = user.password_hash if user else None

    if not verify_password(password, stored):
        if stored is None:
            # Burn equivalent work so the timing matches a real failed password.
            verify_password(password, hash_password("timing-equalising-placeholder"))
        logger.warning("Failed local login for username=%r", username)
        return None

    logger.info("Local login succeeded for %r", user.local_username)
    return user


def seed_local_admin_from_env(session: Session, env: EnvSettings) -> User | None:
    """Create the admin from ADMIN_USERNAME/ADMIN_PASSWORD on first boot.

    Only ever creates; it never updates an existing account. An env var that outlives a password
    change in the UI must not silently reset the password back, and it must not be able to
    resurrect an account that was deliberately deleted -- so the guard is "no local admin exists
    at all", not "this username doesn't exist".
    """
    if not env.admin_username or not env.admin_password:
        return None

    if has_local_admin(session):
        logger.debug("Local admin already exists; skipping env bootstrap")
        return None

    user = create_local_admin(session, env.admin_username, env.admin_password)
    logger.info("Seeded local admin %r from the environment", user.local_username)
    return user
