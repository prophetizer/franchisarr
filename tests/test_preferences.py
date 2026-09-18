"""The Preferences page and the first-run step that leads to it."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.services.settings_service import SettingKey, get_setting, set_setting

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def _setting(key: str) -> str | None:
    with Session(get_engine()) as session:
        return get_setting(session, key)


def test_choosing_libraries_for_the_first_time_leads_to_preferences(client: TestClient, monkeypatch) -> None:
    """Once. Saved or skipped, it never comes back uninvited."""
    from app.services import library_service

    monkeypatch.setattr(library_service, "set_enabled_libraries", lambda session, keys: None)

    first = client.post(f"{BASE}/libraries", data={"keys": ["1"]})
    assert first.status_code == 303
    assert first.headers["location"] == f"{BASE}/preferences?first=1"

    skipped = client.post(f"{BASE}/preferences", data={"skip": "1", "first": "1"})
    assert skipped.headers["location"] == f"{BASE}/"
    assert _setting(SettingKey.PREFERENCES_REVIEWED) == "true"

    again = client.post(f"{BASE}/libraries", data={"keys": ["1"]})
    assert again.headers["location"] == f"{BASE}/"


def test_skipping_keeps_the_defaults(client: TestClient) -> None:
    client.post(f"{BASE}/preferences", data={"skip": "1", "first": "1",
                                              "min_rating": "9", "include_shorts": "1"})

    assert _setting(SettingKey.MIN_GAP_RATING) == "0"
    assert _setting(SettingKey.DIRECTOR_INCLUDE_SHORTS) == "false"


def test_saving_writes_all_four(client: TestClient) -> None:
    response = client.post(f"{BASE}/preferences", data={
        "min_rating": "6", "director_floor": "3", "include_tv_films": "1"})

    assert response.headers["location"] == f"{BASE}/preferences?saved=1"
    assert _setting(SettingKey.MIN_GAP_RATING) == "6"
    assert _setting(SettingKey.MIN_DIRECTOR_FILMS) == "3"
    assert _setting(SettingKey.FRANCHISE_INCLUDE_TV_FILMS) == "true"
    assert _setting(SettingKey.DIRECTOR_INCLUDE_SHORTS) == "false", "an unchecked box is off"


def test_the_page_shows_current_values_and_examples(client: TestClient) -> None:
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.MIN_GAP_RATING, "6.5")
        set_setting(session, SettingKey.DIRECTOR_INCLUDE_SHORTS, "true")
        session.commit()

    body = client.get(f"{BASE}/preferences").text

    assert 'value="6.5"' in body
    assert 'name="include_shorts" value="1" checked' in body
    assert "Holiday Special" in body and "Doodlebug" in body, "every option has an example"
    assert "Skip" not in body, "the skip button is only for the first run"

    first = client.get(f"{BASE}/preferences?first=1").text
    assert "Skip" in first and "Save and continue" in first


def test_settings_links_to_preferences(client: TestClient) -> None:
    assert f'href="{BASE}/preferences"' in client.get(f"{BASE}/settings").text
