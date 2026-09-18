"""The JSON API, and the API-key credential the CLI authenticates with.

The CLI is a thin HTTP client against these same endpoints, so what's covered here covers both
(docs/DESIGN.md decision log).
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


def test_starting_a_scan_without_plex_configured_is_a_clear_conflict(
    client: TestClient, api_key: str
) -> None:
    """Checked before the background task starts, so the caller hears about it rather than a
    status endpoint nobody is polling yet."""
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.TMDB_API_KEY, V3_KEY)
        session.commit()

    response = client.post(f"{BASE}/api/scan", headers={API_KEY_HEADER: api_key})

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


# ------------------------------------------------------------------ Radarr endpoints


RADARR = "http://radarr.test:7878"


def _add_instance(client: TestClient, api_key: str, name: str = "HD") -> int:
    response = client.post(
        f"{BASE}/api/instances/radarr",
        headers={API_KEY_HEADER: api_key},
        json={"name": name, "url": RADARR, "api_key": "radarr-key"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_instance_responses_never_include_the_api_key(client: TestClient, api_key: str) -> None:
    """Convention #3: secrets are write-only from the API's point of view."""
    _add_instance(client, api_key)

    body = client.get(f"{BASE}/api/instances/radarr", headers={API_KEY_HEADER: api_key}).text

    assert "radarr-key" not in body
    assert "api_key" not in body


def test_creating_an_instance_requires_an_admin(client: TestClient) -> None:
    from sqlmodel import select

    from app.auth.api_keys import generate_api_key
    from app.models import User

    with Session(get_engine()) as session:
        ordinary = User(external_user_id="99", external_username="housemate", is_admin=False)
        session.add(ordinary)
        session.commit()
        session.refresh(ordinary)
        key = generate_api_key(session, ordinary)

    response = client.post(
        f"{BASE}/api/instances/radarr",
        headers={API_KEY_HEADER: key},
        json={"name": "HD", "url": RADARR, "api_key": "k"},
    )

    assert response.status_code == 403


@responses.activate
def test_options_reports_an_unreachable_instance_rather_than_empty_lists(
    client: TestClient, api_key: str
) -> None:
    """The add dialog must be able to say "can't reach this" instead of offering nothing
    (technical challenge #15)."""
    instance_id = _add_instance(client, api_key)
    responses.add(responses.GET, f"{RADARR}/api/v3/qualityprofile", status=500)

    body = client.get(
        f"{BASE}/api/instances/radarr/{instance_id}/options", headers={API_KEY_HEADER: api_key}
    ).json()

    assert body["ok"] is False
    assert body["error"]
    assert body["quality_profiles"] == []


@responses.activate
def test_options_are_fetched_live_and_not_stored(client: TestClient, api_key: str) -> None:
    instance_id = _add_instance(client, api_key)
    responses.add(responses.GET, f"{RADARR}/api/v3/qualityprofile",
                  json=[{"id": 1, "name": "HD-1080p"}])
    responses.add(responses.GET, f"{RADARR}/api/v3/rootfolder",
                  json=[{"path": "/movies", "freeSpace": 100_000_000_000}])

    body = client.get(
        f"{BASE}/api/instances/radarr/{instance_id}/options", headers={API_KEY_HEADER: api_key}
    ).json()

    assert body["ok"] is True
    assert body["quality_profiles"] == [{"id": 1, "name": "HD-1080p"}]
    assert body["root_folders"][0]["path"] == "/movies"


def test_adding_without_any_instance_configured_is_a_clear_conflict(
    client: TestClient, api_key: str
) -> None:
    response = client.post(
        f"{BASE}/api/radarr/add", headers={API_KEY_HEADER: api_key}, json={"tmdb_id": 306}
    )

    assert response.status_code == 409
    assert "Radarr instance" in response.json()["detail"]


@responses.activate
def test_adding_falls_back_to_the_preferred_instance(client: TestClient, api_key: str) -> None:
    instance_id = _add_instance(client, api_key)
    with Session(get_engine()) as session:
        from app.services import instance_service

        instance = instance_service.get_radarr(session, instance_id)
        instance.default_quality_profile_id = 1
        instance.default_root_folder = "/movies"
        session.add(instance)
        session.commit()

    responses.add(responses.GET, f"{RADARR}/api/v3/movie/lookup",
                  json=[{"tmdbId": 306, "title": "Beverly Hills Cop III"}])
    responses.add(responses.POST, f"{RADARR}/api/v3/movie", json={"id": 1, "tmdbId": 306})
    responses.add(responses.GET, f"{RADARR}/api/v3/movie", json=[])
    responses.add(responses.GET, f"{RADARR}/api/v3/queue", json={"records": []})

    response = client.post(
        f"{BASE}/api/radarr/add", headers={API_KEY_HEADER: api_key}, json={"tmdb_id": 306}
    )

    assert response.status_code == 200
    assert response.json()["added"] is True


def test_the_activity_log_says_it_does_not_track_downloads(
    client: TestClient, api_key: str
) -> None:
    """Technical challenge #24: don't imply we follow what Radarr does next."""
    body = client.get(f"{BASE}/api/activity", headers={API_KEY_HEADER: api_key}).json()

    assert body["entries"] == []
    assert "history" in body["note"]


# ------------------------------------------------------------------ Sonarr endpoints


SONARR = "http://sonarr.test:8989"


def _add_sonarr(client: TestClient, api_key: str, name: str = "TV") -> int:
    response = client.post(
        f"{BASE}/api/instances/sonarr",
        headers={API_KEY_HEADER: api_key},
        json={"name": name, "url": SONARR, "api_key": "sonarr-key"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_sonarr_instances_are_listed_with_their_monitor_modes(
    client: TestClient, api_key: str
) -> None:
    _add_sonarr(client, api_key)

    body = client.get(f"{BASE}/api/instances/sonarr", headers={API_KEY_HEADER: api_key}).json()

    assert body["instances"][0]["default_monitor_mode"] == "all"
    assert {m["value"] for m in body["monitor_modes"]} == {"all", "future_only", "first_season"}
    assert "api_key" not in body["instances"][0]


def test_making_a_sonarr_instance_default(client: TestClient, api_key: str) -> None:
    first = _add_sonarr(client, api_key, "TV")
    second = _add_sonarr(client, api_key, "Anime")

    response = client.post(f"{BASE}/api/instances/sonarr/{second}/default",
                           headers={API_KEY_HEADER: api_key})
    assert response.status_code == 200

    body = client.get(f"{BASE}/api/instances/sonarr", headers={API_KEY_HEADER: api_key}).json()
    defaults = {i["id"]: i["is_default"] for i in body["instances"]}
    assert defaults == {first: False, second: True}


def test_deleting_a_sonarr_instance(client: TestClient, api_key: str) -> None:
    instance_id = _add_sonarr(client, api_key)

    assert client.delete(f"{BASE}/api/instances/sonarr/{instance_id}",
                         headers={API_KEY_HEADER: api_key}).status_code == 200
    assert client.get(f"{BASE}/api/instances/sonarr",
                      headers={API_KEY_HEADER: api_key}).json()["instances"] == []


def test_an_unknown_sonarr_instance_is_a_404(client: TestClient, api_key: str) -> None:
    assert client.get(f"{BASE}/api/instances/sonarr/999/test",
                      headers={API_KEY_HEADER: api_key}).status_code == 404


@responses.activate
def test_sonarr_options_report_an_unreachable_instance(client: TestClient, api_key: str) -> None:
    instance_id = _add_sonarr(client, api_key)
    responses.add(responses.GET, f"{SONARR}/api/v3/qualityprofile", status=500)

    body = client.get(f"{BASE}/api/instances/sonarr/{instance_id}/options",
                      headers={API_KEY_HEADER: api_key}).json()

    assert body["ok"] is False
    assert body["quality_profiles"] == []


@responses.activate
def test_sonarr_options_include_the_monitor_modes(client: TestClient, api_key: str) -> None:
    instance_id = _add_sonarr(client, api_key)
    responses.add(responses.GET, f"{SONARR}/api/v3/qualityprofile",
                  json=[{"id": 1, "name": "Any"}])
    responses.add(responses.GET, f"{SONARR}/api/v3/rootfolder", json=[{"path": "/tv"}])

    body = client.get(f"{BASE}/api/instances/sonarr/{instance_id}/options",
                      headers={API_KEY_HEADER: api_key}).json()

    assert body["ok"] is True
    assert body["default_monitor_mode"] == "all"
    assert len(body["monitor_modes"]) == 3


def test_adding_a_show_without_an_instance_is_a_clear_conflict(
    client: TestClient, api_key: str
) -> None:
    response = client.post(f"{BASE}/api/sonarr/add", headers={API_KEY_HEADER: api_key},
                           json={"tmdb_id": 17610})

    assert response.status_code == 409
    assert "Sonarr instance" in response.json()["detail"]


def test_the_spinoffs_endpoint_reports_an_empty_mapping_list(
    client: TestClient, api_key: str
) -> None:
    body = client.get(f"{BASE}/api/spinoffs", headers={API_KEY_HEADER: api_key}).json()

    assert body == {"suggestions": [], "mappings": 0}


def test_creating_a_spinoff_mapping_through_the_api(client: TestClient, api_key: str) -> None:
    response = client.post(f"{BASE}/api/spinoffs/mappings", headers={API_KEY_HEADER: api_key},
                           json={"source_show_tmdb_id": 4614, "spinoff_show_tmdb_id": 17610})

    assert response.status_code == 201
    assert response.json()["created"] is True


def test_creating_the_same_mapping_twice_reports_it_rather_than_failing(
    client: TestClient, api_key: str
) -> None:
    payload = {"source_show_tmdb_id": 4614, "spinoff_show_tmdb_id": 17610}
    client.post(f"{BASE}/api/spinoffs/mappings", headers={API_KEY_HEADER: api_key}, json=payload)

    body = client.post(f"{BASE}/api/spinoffs/mappings", headers={API_KEY_HEADER: api_key},
                       json=payload).json()

    assert body["created"] is False
    assert "already exists" in body["reason"]


def test_a_self_referential_mapping_is_refused(client: TestClient, api_key: str) -> None:
    response = client.post(f"{BASE}/api/spinoffs/mappings", headers={API_KEY_HEADER: api_key},
                           json={"source_show_tmdb_id": 4614, "spinoff_show_tmdb_id": 4614})

    assert response.status_code == 400


def test_the_scan_status_endpoint_reports_idle_when_nothing_is_running(
    client: TestClient, api_key: str
) -> None:
    from app.services import scan_state

    scan_state.reset()

    body = client.get(f"{BASE}/api/scan/status", headers={API_KEY_HEADER: api_key}).json()

    assert body["running"] is False
    assert body["percent"] == 0


@responses.activate
def test_refreshing_instances_reports_per_instance_results(
    client: TestClient, api_key: str
) -> None:
    _add_instance(client, api_key)
    responses.add(responses.GET, f"{RADARR}/api/v3/movie", status=500)

    body = client.post(f"{BASE}/api/instances/radarr/refresh",
                       headers={API_KEY_HEADER: api_key}).json()

    assert body["instances"][0]["ok"] is False
    assert body["instances"][0]["error"]
