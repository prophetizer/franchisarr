"""Getting a TMDb key into an install that started without one (a Reddit report, 0.33.1).

The first boot saved an empty key and never read the environment again, Settings had no field
for it, and the Scan button's refusal was a 409 that htmx dropped: "nothing happens", with
nothing in the logs. Each of those is covered here.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.local_admin import create_local_admin
from app.clients import tmdb_client
from app.config import get_settings
from app.db import get_engine
from app.models import IncludedLibrary
from app.services.settings_service import SettingKey, get_setting, seed_settings_from_env, set_setting
from tests.conftest import seed_server

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"
KEY = "a" * 28 + "9f3e"


# ------------------------------------------------------------------ the environment


def test_a_key_added_to_the_environment_after_first_boot_is_picked_up(
    session: Session, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    seed_settings_from_env(session, get_settings())          # first boot, no key yet
    assert get_setting(session, SettingKey.TMDB_API_KEY) == ""

    monkeypatch.setenv("TMDB_API_KEY", KEY)
    with caplog.at_level(logging.INFO, logger="app.services.settings_service"):
        seed_settings_from_env(session, get_settings())      # the restart after adding it

    assert get_setting(session, SettingKey.TMDB_API_KEY) == KEY
    assert "Filled tmdb_api_key from the environment" in caplog.text
    assert KEY not in caplog.text


def test_an_environment_value_the_app_ignores_is_named_but_not_shown(
    session: Session, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    set_setting(session, SettingKey.TMDB_API_KEY, "key-set-in-the-app")
    session.commit()
    monkeypatch.setenv("TMDB_API_KEY", "different-key-in-compose")

    with caplog.at_level(logging.INFO, logger="app.services.settings_service"):
        seed_settings_from_env(session, get_settings())

    assert get_setting(session, SettingKey.TMDB_API_KEY) == "key-set-in-the-app", "the app still wins"
    assert "tmdb_api_key in the environment differ" in caplog.text
    assert "different-key-in-compose" not in caplog.text


# ------------------------------------------------------------------ the pages


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


@pytest.fixture
def tmdb_accepts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    checked: list[str] = []
    monkeypatch.setattr(tmdb_client.TmdbClient, "validate_key", lambda self: checked.append(self._api_key))
    return checked


def _saved(key: str) -> str | None:
    with Session(get_engine()) as session:
        return get_setting(session, key)


def test_the_scan_button_says_what_is_missing_instead_of_doing_nothing(client: TestClient) -> None:
    """The reporter's setup: Plex added and reachable, libraries chosen, no TMDb key."""
    with Session(get_engine()) as session:
        server = seed_server(session, "plex")
        session.add(IncludedLibrary(server_id=server.id, library_key="1", library_name="Movies",
                                    library_type="movie", enabled=True))
        session.commit()
    home = client.get(f"{BASE}/").text
    assert "No TMDb API key yet" in home and f'href="{BASE}/settings#keys"' in home, "said before pressing"

    response = client.post(f"{BASE}/scan")

    assert response.status_code == 200
    assert "scan yet</strong>" in response.text and "No TMDb API key yet" in response.text


def test_a_tmdb_key_can_be_added_in_settings_and_is_checked_first(client: TestClient, tmdb_accepts) -> None:
    page = client.get(f"{BASE}/settings").text
    assert 'name="tmdb_api_key"' in page and "not set" in page

    response = client.post(f"{BASE}/settings/keys", data={"tmdb_api_key": f"  {KEY}  "})

    assert response.status_code == 303 and response.headers["location"].endswith("#keys")
    assert tmdb_accepts == [KEY] and _saved(SettingKey.TMDB_API_KEY) == KEY
    page = client.get(f"{BASE}/settings").text
    assert "9f3e" in page and KEY not in page, "masked to the last four"
    assert "No TMDb API key yet" not in client.get(f"{BASE}/").text


def test_a_key_tmdb_rejects_is_not_saved(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(self):  # noqa: ANN001, ANN202
        raise tmdb_client.TmdbAuthError("TMDb rejected that API key.")

    monkeypatch.setattr(tmdb_client.TmdbClient, "validate_key", reject)

    page = client.post(f"{BASE}/settings/keys", data={"tmdb_api_key": "wrong" * 6}).text

    assert "Not saved: TMDb rejected that API key." in page
    assert "wrong" * 6 not in page and not _saved(SettingKey.TMDB_API_KEY)


def test_blank_keeps_the_saved_keys_and_fanart_can_be_removed(client: TestClient, tmdb_accepts) -> None:
    client.post(f"{BASE}/settings/keys", data={"tmdb_api_key": KEY, "fanart_api_key": "f" * 32})

    client.post(f"{BASE}/settings/keys", data={"tmdb_api_key": "", "fanart_api_key": ""})
    assert _saved(SettingKey.TMDB_API_KEY) == KEY and _saved(SettingKey.FANART_API_KEY) == "f" * 32

    client.post(f"{BASE}/settings/keys", data={"fanart_clear": "1"})
    assert _saved(SettingKey.FANART_API_KEY) == "" and _saved(SettingKey.TMDB_API_KEY) == KEY
