"""The medium- and low-severity findings of the 2026-09-26 security review, one test each,
written as the attack the review ran (0.26.0). The two high ones are in test_signin_abuse.py.
"""

from __future__ import annotations

import json
import logging
import time

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.api_keys import generate_api_key, hash_api_key
from app.auth.dependencies import API_KEY_HEADER
from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import MediaServer, User
from app.services import config_backup
from app.services.settings_service import SettingKey, get_setting

BASE = "/franchisarr"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


# ------------------------------------------------------------------ backup import


def test_a_crafted_backup_cannot_add_a_server_that_decides_who_is_admin(session: Session) -> None:
    """The review's attack: a backup adding the attacker's Plex server, identity included, so its
    owner signs in as admin. Imported servers now arrive switched off and identity-less."""
    document = {"franchisarr_export_version": 1, "media_servers": [
        {"name": "Plex2", "kind": "plex", "url": "https://attacker.example:32400",
         "credential": "t" * 20, "enabled": True, "machine_identifier": "ATTACKER-MID", "id": 99}]}

    config_backup.import_config(session, document)

    server = session.exec(select(MediaServer)).one()
    assert (server.enabled, server.machine_identifier) == (False, None)
    assert server.id != 99, "a file doesn't choose primary keys"
    from app.services.auth_service import known_plex_servers
    assert known_plex_servers(session) == []


def test_a_backup_cannot_set_unknown_settings_or_bad_values(session: Session) -> None:
    document = {"franchisarr_export_version": 1, "settings": {
        "made_up_key": "x", SettingKey.WEBHOOK_FORMAT: "x'});alert(1);({a:'",
        SettingKey.SCAN_SCHEDULE_CRON: "not a cron", SettingKey.UPDATE_RELEASES_URL: "http://169.254.169.254/",
        SettingKey.PLEX_CLIENT_ID: "attacker-chosen", SettingKey.MIN_GAP_RATING: {"nested": 1},
        SettingKey.TMDB_CACHE_TTL_DAYS: "14"}}

    counts = config_backup.import_config(session, document)

    assert counts["settings"] == 1 and counts["skipped_invalid"] == 6
    assert get_setting(session, SettingKey.TMDB_CACHE_TTL_DAYS) == "14"
    assert get_setting(session, "made_up_key") is None
    assert get_setting(session, SettingKey.PLEX_CLIENT_ID) != "attacker-chosen"


@pytest.mark.parametrize("document", [
    {"franchisarr_export_version": True},
    {"franchisarr_export_version": -5},
    {"franchisarr_export_version": 1, "radarr_instances": ["not a dict"]},
    {"franchisarr_export_version": 1, "radarr_instances": [{"name": ["x"], "url": "http://r"}]},
    {"franchisarr_export_version": 1, "radarr_instances": [{"name": "x", "url": "javascript:1"}]},
])
def test_malformed_backups_are_refused_with_a_message(session: Session, document) -> None:
    with pytest.raises(config_backup.InvalidBackup):
        config_backup.import_config(session, document)


def test_a_deeply_nested_backup_is_a_message_not_a_crash(client: TestClient) -> None:
    nested = "[" * 100_000 + "]" * 100_000
    response = client.post(f"{BASE}/settings/import", files={"backup": ("b.json", nested, "application/json")})
    assert response.status_code == 400 and "valid JSON" in response.text


# ------------------------------------------------------------------ redirects, CSRF, logout, docs


def test_a_backslash_next_is_not_an_open_redirect(app_factory) -> None:
    from app.routes_auth import _safe_next

    app_factory("")        # the root-path install, where the review's payload worked
    for payload in ("/\\evil.com", "/\\\\evil.com", "/\t/evil.com", "/\n/evil.com"):
        assert _safe_next(payload) == "/", repr(payload)
    assert _safe_next("/collections?sort=name") == "/collections?sort=name"


def test_a_sibling_subdomain_cannot_post_here(client: TestClient) -> None:
    response = client.post(f"{BASE}/settings/members", data={"enabled": "1"},
                           headers={"Sec-Fetch-Site": "same-site", "Origin": "https://evil.home.example"})
    assert response.status_code == 403


def test_logout_is_post_only_and_the_api_docs_are_gone(client: TestClient) -> None:
    assert client.get(f"{BASE}/logout").status_code == 405
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path


def test_credential_pages_and_downloads_are_never_stored_by_the_browser(client: TestClient) -> None:
    for path in ("/settings", "/settings/export", "/settings/diagnostics"):
        assert client.get(f"{BASE}{path}").headers.get("cache-control") == "no-store", path
    assert client.post(f"{BASE}/settings/api-key").headers.get("cache-control") == "no-store"


# ------------------------------------------------------------------ API keys


def test_api_keys_are_stored_hashed_and_revocable(client: TestClient) -> None:
    with Session(get_engine()) as session:
        user = session.exec(select(User)).one()
        key = generate_api_key(session, user)
        assert user.api_key == hash_api_key(key) and key not in user.api_key

    with TestClient(client.app, follow_redirects=False) as keyed:
        assert keyed.get(f"{BASE}/api/me", headers={API_KEY_HEADER: key}).status_code == 200

    client.post(f"{BASE}/settings/api-key/revoke")
    client.cookies.clear()                  # the key alone, not the signed-in session
    assert client.get(f"{BASE}/api/me", headers={API_KEY_HEADER: key}).status_code == 303


def test_a_key_in_a_url_never_reaches_the_log(caplog) -> None:
    """After a restart nothing had registered the key, so uvicorn's access line printed it."""
    from app.logging_config import RedactingFormatter

    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
                               '127.0.0.1 - "GET /api/lists/films.json?api_key=%s&min_rating=7 HTTP/1.1" 200',
                               ("FAKEUSERKEY-qqq999www888eee777rrr",), None)
    line = RedactingFormatter("%(message)s").format(record)
    assert "FAKEUSERKEY" not in line and "min_rating=7" in line


def test_migration_0023_hashes_existing_plaintext_keys(tmp_path) -> None:
    import sqlite3

    from alembic import command
    from alembic.config import Config

    db = tmp_path / "old.db"
    cfg = Config()
    cfg.set_main_option("script_location", "app/migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "0022")
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO users (id, is_admin, api_key, created_at) VALUES (1, 1, 'plain-old-key', '2026-01-01')")
    command.upgrade(cfg, "0023")
    with sqlite3.connect(db) as conn:
        stored = conn.execute("SELECT api_key FROM users").fetchone()[0]
    assert stored == hash_api_key("plain-old-key")


# ------------------------------------------------------------------ users and admin rights


def test_admin_rights_follow_the_server_on_every_sign_in(session: Session) -> None:
    """A Plex server handed to someone else, or a Jellyfin admin demoted, stopped being admin
    there but stayed admin here, because sign-in only ever added the flag."""
    from app.auth.plex_oauth import PlexAccount
    from app.services.auth_service import provision_plex_user

    account = PlexAccount(id="42", username="former-owner")
    assert provision_plex_user(session, account, is_owner=True).is_admin is True
    assert provision_plex_user(session, account, is_owner=False).is_admin is False


def test_the_users_page_ends_sessions_and_removes_accounts_but_never_the_last_admin(client: TestClient) -> None:
    with Session(get_engine()) as session:
        other = User(external_user_id="7", external_username="housemate", is_admin=False)
        session.add(other); session.commit(); session.refresh(other)
        other_id = other.id
        admin_id = session.exec(select(User).where(User.local_username == "admin")).one().id

    body = client.get(f"{BASE}/users").text
    assert "housemate" in body and "(you)" in body

    assert "Account removed" in client.post(f"{BASE}/users/{other_id}/remove").text
    assert "only administrator" in client.post(f"{BASE}/users/{admin_id}/remove").text or \
        "your own account" in client.post(f"{BASE}/users/{admin_id}/remove").text
    with Session(get_engine()) as session:
        assert session.get(User, other_id) is None and session.get(User, admin_id) is not None


def test_a_short_admin_password_from_the_environment_creates_no_account(session: Session, caplog) -> None:
    from app.auth.local_admin import has_local_admin, seed_local_admin_from_env
    
    import dataclasses

    from app.config import get_settings

    env = dataclasses.replace(get_settings(), admin_username="admin", admin_password="short")
    assert seed_local_admin_from_env(session, env) is None
    assert not has_local_admin(session)


def test_login_timing_does_not_reveal_which_usernames_exist(session: Session) -> None:
    from app.auth.local_admin import authenticate_local

    create_local_admin(session, "admin", PASSWORD)
    authenticate_local(session, "nobody", "x")         # build the dummy hash once, outside timing

    def cost(name: str) -> float:
        start = time.perf_counter()
        for _ in range(3):
            authenticate_local(session, name, "wrong password")
        return time.perf_counter() - start

    real, missing = cost("admin"), cost("nobody")
    assert 0.6 < missing / real < 1.6, (real, missing)


# ------------------------------------------------------------------ outputs and inputs


@__import__("responses").activate
def test_the_update_link_must_be_https() -> None:
    import responses

    from app.services import update_checker

    responses.add(responses.GET, update_checker.DEFAULT_RELEASES_URL, json=[
        {"tag_name": "v99.0.0", "html_url": "javascript:alert(1)", "draft": False, "prerelease": False}])
    status = update_checker.check()
    assert status.latest and status.url is None


def test_the_releases_url_override_must_be_https(session: Session) -> None:
    from app.services import update_checker
    from app.services.settings_service import set_setting

    set_setting(session, SettingKey.UPDATE_RELEASES_URL, "http://169.254.169.254/latest/meta-data")
    session.commit()
    assert update_checker.releases_url(session) == update_checker.DEFAULT_RELEASES_URL


def test_a_title_cannot_inject_calendar_lines() -> None:
    from app.services.ical import _escape

    assert "\r" not in _escape("Upcoming\rATTENDEE:mailto:x@y") and "\x07" not in _escape("a\x07b")


def test_a_padded_title_cannot_stall_the_matcher() -> None:
    from app.services.matcher import normalise_title

    start = time.perf_counter()
    normalise_title("a" + " " * 40_000 + "b")
    assert time.perf_counter() - start < 0.5
    assert normalise_title("Alien (1979) ") == "alien"


def test_huge_page_numbers_are_clamped_not_a_500(client: TestClient) -> None:
    assert client.get(f"{BASE}/activity?page={10**20}").status_code == 200
    response = client.get(f"{BASE}/api/activity?offset={10**20}&limit={10**20}")
    assert response.status_code == 200
