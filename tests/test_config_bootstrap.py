"""Env-var bootstrap of the settings table (docs/DESIGN.md section 6)."""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.config import get_settings
from app.models import Setting
from app.services.settings_service import (
    DEFAULTS,
    SettingKey,
    get_all_settings,
    get_bool_setting,
    get_int_setting,
    is_seeded,
    seed_settings_from_env,
    set_setting,
)


def test_env_seeds_an_empty_database(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASE_URL", "/franchisarr")
    monkeypatch.setenv("PLEX_URL", "http://plex.local:32400")
    monkeypatch.setenv("TMDB_API_KEY", "tmdb-key-from-env")
    monkeypatch.setenv("SCAN_SCHEDULE_CRON", "0 3 * * *")
    monkeypatch.setenv("WEBHOOK_URL", "https://discord.example/hook")
    monkeypatch.setenv("WEBHOOK_FORMAT", "discord")
    monkeypatch.setenv("TMDB_CACHE_TTL_DAYS", "14")
    monkeypatch.setenv("CROSS_INSTANCE_DEDUP", "true")

    assert seed_settings_from_env(session, get_settings()) is True

    stored = get_all_settings(session)
    assert stored[SettingKey.BASE_URL] == "/franchisarr"
    assert stored[SettingKey.PLEX_URL] == "http://plex.local:32400"
    assert stored[SettingKey.TMDB_API_KEY] == "tmdb-key-from-env"
    assert stored[SettingKey.SCAN_SCHEDULE_CRON] == "0 3 * * *"
    assert stored[SettingKey.WEBHOOK_FORMAT] == "discord"
    assert get_int_setting(session, SettingKey.TMDB_CACHE_TTL_DAYS, 7) == 14
    assert get_bool_setting(session, SettingKey.CROSS_INSTANCE_DEDUP) is True


def test_seeding_covers_every_required_key_even_with_no_env(session: Session) -> None:
    assert seed_settings_from_env(session, get_settings()) is True

    keys = {row.key for row in session.exec(select(Setting)).all()}
    assert keys == set(DEFAULTS)
    # The seven keys the settings table is specified to cover, plus the Plex connection.
    assert {
        SettingKey.BASE_URL,
        SettingKey.TMDB_API_KEY,
        SettingKey.WEBHOOK_URL,
        SettingKey.WEBHOOK_FORMAT,
        SettingKey.SCAN_SCHEDULE_CRON,
        SettingKey.TMDB_CACHE_TTL_DAYS,
        SettingKey.CROSS_INSTANCE_DEDUP,
    } <= keys


def test_env_does_not_overwrite_existing_settings(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A value set through the UI must survive a restart, even if a stale env var disagrees."""
    set_setting(session, SettingKey.TMDB_API_KEY, "key-set-in-the-ui")
    session.commit()

    monkeypatch.setenv("TMDB_API_KEY", "stale-key-from-compose")
    monkeypatch.setenv("WEBHOOK_URL", "https://never-applied.example/hook")

    assert seed_settings_from_env(session, get_settings()) is False

    stored = get_all_settings(session)
    assert stored[SettingKey.TMDB_API_KEY] == "key-set-in-the-ui"
    # And no other key was back-filled from the environment either.
    assert session.get(Setting, SettingKey.WEBHOOK_URL) is None


def test_cleared_setting_is_not_resurrected_by_env(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clearing a webhook in the UI must stick, rather than coming back on next boot."""
    monkeypatch.setenv("WEBHOOK_URL", "https://discord.example/hook")
    seed_settings_from_env(session, get_settings())

    set_setting(session, SettingKey.WEBHOOK_URL, "")
    session.commit()

    seed_settings_from_env(session, get_settings())
    assert get_all_settings(session)[SettingKey.WEBHOOK_URL] == ""


def test_is_seeded_reflects_table_state(session: Session) -> None:
    assert is_seeded(session) is False
    seed_settings_from_env(session, get_settings())
    assert is_seeded(session) is True


def test_env_settings_expose_secrets_for_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLEX_TOKEN", "plex-token")
    monkeypatch.setenv("TMDB_API_KEY", "tmdb-key")
    monkeypatch.setenv("RADARR_API_KEY", "radarr-key")
    monkeypatch.setenv("SONARR_API_KEY", "sonarr-key")
    monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")

    secrets = get_settings().secret_values()

    assert set(secrets) == {"plex-token", "tmdb-key", "radarr-key", "sonarr-key", "hunter2"}
