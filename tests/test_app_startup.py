"""End-to-end boot: the app must come up, migrate, seed, and serve under a subpath.

This is the Phase 1 acceptance test. Everything else here tests a piece; this one checks the
pieces are actually wired to each other.
"""

from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BASE = "/franchisarr"


@pytest.fixture
def app_under_subpath(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Import app.main afresh with a subpath BASE_URL and a throwaway database."""
    monkeypatch.setenv("BASE_URL", BASE)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "franchisarr.db"))
    monkeypatch.setenv("TMDB_API_KEY", "tmdb-key-from-env")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    import app.main

    module = importlib.reload(app.main)
    try:
        yield module
    finally:
        # Leave the module as other tests expect to find it.
        monkeypatch.undo()
        importlib.reload(app.main)


def test_health_is_served_under_the_base_url(app_under_subpath) -> None:
    with TestClient(app_under_subpath.app) as client:
        assert client.get(f"{BASE}/health").json() == {"status": "ok"}
        assert client.get("/health").status_code == 404


def test_index_redirects_anonymous_visitors_to_the_login_page(app_under_subpath) -> None:
    with TestClient(app_under_subpath.app, follow_redirects=False) as client:
        response = client.get(f"{BASE}/")

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"{BASE}/login")


def test_login_page_renders_dark_and_links_under_the_base_url(app_under_subpath) -> None:
    with TestClient(app_under_subpath.app) as client:
        response = client.get(f"{BASE}/login")

    assert response.status_code == 200
    assert 'data-theme="dark"' in response.text
    assert f"{BASE}/static/pico.min.css" in response.text
    assert '"/static/pico.min.css"' not in response.text


@pytest.mark.parametrize(
    "asset", ["pico.min.css", "htmx.min.js", "alpine.min.js", "app.css"]
)
def test_static_assets_are_served_under_the_base_url(app_under_subpath, asset: str) -> None:
    with TestClient(app_under_subpath.app) as client:
        response = client.get(f"{BASE}/static/{asset}")

    assert response.status_code == 200
    assert response.content


def test_startup_migrates_and_seeds_the_database(app_under_subpath, tmp_path: Path) -> None:
    db_path = tmp_path / "franchisarr.db"

    with TestClient(app_under_subpath.app):
        pass

    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        settings = dict(conn.execute("SELECT key, value FROM settings"))

    assert {"users", "settings", "radarr_instances", "activity_log"} <= tables
    assert settings["tmdb_api_key"] == "tmdb-key-from-env"
    assert settings["base_url"] == BASE


def test_startup_registers_env_secrets_for_redaction(app_under_subpath) -> None:
    """A token in the environment must be redacted from logs before anything can log it."""
    from app.logging_config import redact

    with TestClient(app_under_subpath.app):
        assert "tmdb-key-from-env" not in redact("key is tmdb-key-from-env")


def test_plex_sign_in_becomes_available_at_startup(tmp_path, monkeypatch) -> None:
    """Regression: the machine identifier was only learned by opening the library page, which
    requires being signed in. Plex sign-in could therefore never appear on a fresh install, and
    an install with Plex configured but no local admin had no way in at all."""
    import importlib

    import responses as responses_lib
    from sqlmodel import Session

    from app.db import get_engine
    from app.services.auth_service import known_plex_servers

    monkeypatch.setenv("BASE_URL", "/")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "startup.db"))
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("PLEX_URL", "http://plex.test:32400")
    monkeypatch.setenv("PLEX_TOKEN", "a-token")

    fixture = (
        Path(__file__).parent / "fixtures" / "plex" / "root.xml"
    ).read_text()

    import app.main

    module = importlib.reload(app.main)
    try:
        with responses_lib.RequestsMock(assert_all_requests_are_fired=False) as mock:
            mock.add(responses_lib.GET, "http://plex.test:32400/", body=fixture,
                     content_type="application/xml")
            with TestClient(module.app) as client:
                body = client.get("/login").text

        assert "Sign in with Plex" in body, "the button must be offered before anyone signs in"
        with Session(get_engine()) as session:
            assert known_plex_servers(session), "the seeded Plex row learned its identity"
    finally:
        monkeypatch.undo()
        importlib.reload(app.main)


def test_an_unreachable_plex_at_startup_is_not_fatal(tmp_path, monkeypatch) -> None:
    """The app must still boot and still offer the local admin login."""
    import importlib

    import responses as responses_lib

    monkeypatch.setenv("BASE_URL", "/")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "startup2.db"))
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("PLEX_URL", "http://plex.test:32400")
    monkeypatch.setenv("PLEX_TOKEN", "a-token")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-passphrase-here")

    import app.main

    module = importlib.reload(app.main)
    try:
        with responses_lib.RequestsMock(assert_all_requests_are_fired=False) as mock:
            mock.add(responses_lib.GET, "http://plex.test:32400/", status=500)
            with TestClient(module.app) as client:
                assert client.get("/health").status_code == 200
                assert 'name="username"' in client.get("/login").text
    finally:
        monkeypatch.undo()
        importlib.reload(app.main)
