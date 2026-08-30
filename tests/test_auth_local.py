"""Password hashing, session store, and the local admin fallback."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.auth.local_admin import (
    authenticate_local,
    create_local_admin,
    get_local_admin,
    has_local_admin,
    seed_local_admin_from_env,
)
from app.auth.passwords import hash_password, verify_password
from app.auth.sessions import (
    create_session,
    delete_session,
    delete_sessions_for_user,
    get_session_user,
    purge_expired,
)
from app.config import get_settings
from app.models import User, UserSession, utcnow

# ------------------------------------------------------------------ password hashing


def test_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_hash_is_salted() -> None:
    assert hash_password("same") != hash_password("same")


def test_password_is_never_stored_in_the_clear() -> None:
    assert "hunter2" not in hash_password("hunter2")


def test_long_passphrases_are_not_silently_truncated() -> None:
    """bcrypt only reads the first 72 bytes and this version truncates silently, so without
    pre-hashing these two passphrases would both verify against either hash."""
    base = "x" * 72
    hashed = hash_password(base + "AAAA")

    assert verify_password(base + "AAAA", hashed) is True
    assert verify_password(base + "BBBB", hashed) is False


@pytest.mark.parametrize("bad_hash", [None, "", "not-a-hash", "bcrypt-sha256$garbage", "$2b$xx"])
def test_malformed_hashes_deny_access_rather_than_raising(bad_hash: str | None) -> None:
    assert verify_password("anything", bad_hash) is False


def test_empty_password_never_verifies() -> None:
    assert verify_password("", hash_password("real")) is False
    with pytest.raises(ValueError):
        hash_password("")


# ------------------------------------------------------------------ local admin


def test_create_and_authenticate(session: Session) -> None:
    create_local_admin(session, "Admin", "s3cret-passphrase")

    user = authenticate_local(session, "admin", "s3cret-passphrase")

    assert user is not None
    assert user.is_admin is True
    assert user.local_username == "admin"


def test_username_is_case_insensitive(session: Session) -> None:
    create_local_admin(session, "michael", "s3cret-passphrase")
    assert authenticate_local(session, "MICHAEL", "s3cret-passphrase") is not None


def test_wrong_password_is_rejected(session: Session) -> None:
    create_local_admin(session, "admin", "s3cret-passphrase")
    assert authenticate_local(session, "admin", "wrong") is None


def test_unknown_user_is_rejected(session: Session) -> None:
    create_local_admin(session, "admin", "s3cret-passphrase")
    assert authenticate_local(session, "nobody", "s3cret-passphrase") is None


def test_authenticating_against_an_empty_database_is_safe(session: Session) -> None:
    assert authenticate_local(session, "admin", "anything") is None


# ------------------------------------------------------------------ env seeding


def test_env_seeds_the_admin_on_first_boot(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "michael")
    monkeypatch.setenv("ADMIN_PASSWORD", "from-the-environment")

    user = seed_local_admin_from_env(session, get_settings())

    assert user is not None
    assert authenticate_local(session, "michael", "from-the-environment") is not None


def test_env_seeding_does_nothing_without_both_values(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_USERNAME", "michael")

    assert seed_local_admin_from_env(session, get_settings()) is None
    assert has_local_admin(session) is False


def test_env_never_resets_an_existing_password(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale ADMIN_PASSWORD in docker-compose must not undo a password change."""
    create_local_admin(session, "michael", "changed-in-the-app")

    monkeypatch.setenv("ADMIN_USERNAME", "michael")
    monkeypatch.setenv("ADMIN_PASSWORD", "stale-from-compose")
    assert seed_local_admin_from_env(session, get_settings()) is None

    assert authenticate_local(session, "michael", "changed-in-the-app") is not None
    assert authenticate_local(session, "michael", "stale-from-compose") is None


def test_env_does_not_resurrect_a_differently_named_admin(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard is "any local admin exists", not "this username exists" -- otherwise renaming
    the admin would let the env var quietly create a second one."""
    create_local_admin(session, "michael", "chosen-in-the-app")

    monkeypatch.setenv("ADMIN_USERNAME", "someone-else")
    monkeypatch.setenv("ADMIN_PASSWORD", "from-compose")
    seed_local_admin_from_env(session, get_settings())

    assert get_local_admin(session, "someone-else") is None
    assert len(session.exec(select(User)).all()) == 1


# ------------------------------------------------------------------ sessions


def test_session_roundtrip(session: Session) -> None:
    user = create_local_admin(session, "admin", "s3cret-passphrase")

    token = create_session(session, user)
    resolved = get_session_user(session, token)

    assert resolved is not None
    assert resolved.id == user.id


def test_the_raw_token_is_never_stored(session: Session) -> None:
    """A copied /config volume must not yield replayable logins."""
    user = create_local_admin(session, "admin", "s3cret-passphrase")
    token = create_session(session, user)

    stored = session.exec(select(UserSession)).all()
    assert len(stored) == 1
    assert stored[0].token_hash != token
    assert token not in stored[0].token_hash


@pytest.mark.parametrize("token", [None, "", "not-a-real-token"])
def test_bad_tokens_resolve_to_nobody(session: Session, token: str | None) -> None:
    create_local_admin(session, "admin", "s3cret-passphrase")
    assert get_session_user(session, token) is None


def test_expired_sessions_are_rejected_and_cleaned_up(session: Session) -> None:
    user = create_local_admin(session, "admin", "s3cret-passphrase")
    token = create_session(session, user, lifetime=timedelta(seconds=-1))

    assert get_session_user(session, token) is None
    assert session.exec(select(UserSession)).all() == []


def test_logout_revokes_the_session(session: Session) -> None:
    user = create_local_admin(session, "admin", "s3cret-passphrase")
    token = create_session(session, user)

    delete_session(session, token)

    assert get_session_user(session, token) is None


def test_deleting_a_user_invalidates_their_session(session: Session) -> None:
    """The session row cascades away with the account, so a deleted user's cookie cannot remain
    a live credential."""
    user = create_local_admin(session, "admin", "s3cret-passphrase")
    token = create_session(session, user)

    session.delete(session.get(User, user.id))
    session.commit()

    assert get_session_user(session, token) is None
    assert session.exec(select(UserSession)).all() == []


def test_sessions_can_be_revoked_for_a_whole_user(session: Session) -> None:
    user = create_local_admin(session, "admin", "s3cret-passphrase")
    tokens = [create_session(session, user) for _ in range(3)]

    delete_sessions_for_user(session, user.id)

    assert all(get_session_user(session, token) is None for token in tokens)


def test_a_near_expiry_session_is_extended_on_use(session: Session) -> None:
    user = create_local_admin(session, "admin", "s3cret-passphrase")
    token = create_session(session, user, lifetime=timedelta(days=1))
    before = session.exec(select(UserSession)).first().expires_at

    assert get_session_user(session, token) is not None

    session.expire_all()
    after = session.exec(select(UserSession)).first().expires_at
    assert after > before


def test_purge_expired_removes_only_dead_sessions(session: Session) -> None:
    user = create_local_admin(session, "admin", "s3cret-passphrase")
    live = create_session(session, user)
    create_session(session, user, lifetime=timedelta(seconds=-1))

    assert purge_expired(session) == 1
    assert get_session_user(session, live) is not None
