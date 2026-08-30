"""The JSON API, and the API-key credential the CLI authenticates with.

The CLI is a thin HTTP client against these same endpoints, so what's covered here covers both
(PROJECT_PLAN.md decision log).
"""

from __future__ import annotations

import pytest
import responses
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.api_keys import generate_api_key, revoke_api_key
from app.auth.dependencies import API_KEY_HEADER
from app.auth.local_admin import create_local_admin
from app.clients.tmdb_client import TMDB_BASE_URL
from app.db import get_engine
from app.services.settings_service import SettingKey, set_setting

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"
V3_KEY = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
        yield test_client


@pytest.fixture
def api_key() -> str:
    with Session(get_engine()) as session:
        from sqlmodel import select

        from app.models import User

        user = session.exec(select(User)).first()
        return generate_api_key(session, user)


def _login(client: TestClient) -> None:
    assert client.post(
        f"{BASE}/login", data={"username": "admin", "password": PASSWORD}
    ).status_code == 303


# ------------------------------------------------------------------ API key auth


def test_the_api_rejects_anonymous_callers(client: TestClient) -> None:
    assert client.get(f"{BASE}/api/me").status_code in (303, 401)


def test_an_api_key_authenticates_without_a_browser_session(
    client: TestClient, api_key: str
) -> None:
    """`docker exec franchisarr cli.py scan movies` has no cookie to borrow."""
    response = client.get(f"{BASE}/api/me", headers={API_KEY_HEADER: api_key})

    assert response.status_code == 200
    assert response.json()["username"] == "admin"


def test_a_wrong_api_key_is_refused(client: TestClient) -> None:
    response = client.get(f"{BASE}/api/me", headers={API_KEY_HEADER: "not-a-real-key"})

    assert response.status_code in (303, 401)


def test_a_revoked_api_key_stops_working(client: TestClient, api_key: str) -> None:
    with Session(get_engine()) as session:
        from sqlmodel import select

        from app.models import User

        revoke_api_key(session, session.exec(select(User)).first())

    assert client.get(f"{BASE}/api/me", headers={API_KEY_HEADER: api_key}).status_code in (303, 401)


def test_issuing_a_key_replaces_the_previous_one(client: TestClient, api_key: str) -> None:
    _login(client)
    new_key = client.post(f"{BASE}/api/me/api-key").json()["api_key"]

    # The session cookie is checked before the API key, so it has to go before the old key can
    # be shown to be dead.
    client.cookies.clear()

    assert new_key != api_key
    assert client.get(f"{BASE}/api/me", headers={API_KEY_HEADER: new_key}).status_code == 200
    assert client.get(f"{BASE}/api/me", headers={API_KEY_HEADER: api_key}).status_code in (303, 401)


def test_a_session_still_works_alongside_api_keys(client: TestClient) -> None:
    _login(client)
    assert client.get(f"{BASE}/api/me").status_code == 200


# ------------------------------------------------------------------ TMDb key check


@responses.activate
def test_tmdb_test_reports_a_working_key(client: TestClient, api_key: str) -> None:
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.TMDB_API_KEY, V3_KEY)
        session.commit()
    responses.add(responses.GET, f"{TMDB_BASE_URL}/configuration", json={"images": {}})

    response = client.get(f"{BASE}/api/tmdb/test", headers={API_KEY_HEADER: api_key})

    assert response.json() == {"ok": True}


def test_tmdb_test_explains_a_v4_token(client: TestClient, api_key: str) -> None:
    """The most likely misconfiguration gets a specific message, not a generic failure."""
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.TMDB_API_KEY, "eyJhbGciOiJIUzI1NiJ9.abc.def")
        session.commit()

    response = client.get(f"{BASE}/api/tmdb/test", headers={API_KEY_HEADER: api_key})

    assert response.json()["ok"] is False
    assert "v3 API Key" in response.json()["error"]


def test_a_missing_tmdb_key_is_a_clear_conflict(client: TestClient, api_key: str) -> None:
    response = client.get(f"{BASE}/api/tmdb/test", headers={API_KEY_HEADER: api_key})

    assert response.status_code == 409
    assert "TMDb API key" in response.json()["detail"]


# ------------------------------------------------------------------ scanning and gaps


def test_scanning_without_plex_configured_is_a_clear_conflict(
    client: TestClient, api_key: str
) -> None:
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.TMDB_API_KEY, V3_KEY)
        session.commit()

    response = client.post(f"{BASE}/api/scan/movies", headers={API_KEY_HEADER: api_key})

    assert response.status_code == 409
    assert "Plex" in response.json()["detail"]


def test_gaps_is_empty_before_anything_is_scanned(client: TestClient, api_key: str) -> None:
    response = client.get(f"{BASE}/api/collections/gaps", headers={API_KEY_HEADER: api_key})

    assert response.status_code == 200
    assert response.json() == {"collections": []}


def test_review_endpoint_reports_both_buckets(client: TestClient, api_key: str) -> None:
    response = client.get(f"{BASE}/api/matches/review", headers={API_KEY_HEADER: api_key})

    assert response.json() == {"needs_review": [], "unmatched": []}


def test_the_api_is_mounted_under_the_base_url(client: TestClient, api_key: str) -> None:
    assert client.get("/api/me", headers={API_KEY_HEADER: api_key}).status_code == 404
    assert client.get(f"{BASE}/api/me", headers={API_KEY_HEADER: api_key}).status_code == 200
