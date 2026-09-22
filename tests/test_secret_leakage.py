"""Systematic check that no configured secret escapes through any output path.

docs/DEVELOPMENT.md convention 3 says secrets are never rendered or logged. That is easy to honour when
writing a page and easy to break when adding one, so this walks every route the app serves with
recognisable secrets configured and asserts none of them comes back — rather than relying on
whoever adds the next page having remembered.

Covers: HTML pages, JSON API responses, error paths, log output, and the config export.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.api_keys import generate_api_key
from app.auth.dependencies import API_KEY_HEADER
from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import User
from app.services import instance_service, seerr_instance_service, sonarr_instance_service
from tests.conftest import seed_server
from app.services.settings_service import SettingKey, set_setting

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"

#: Distinctive enough that a match cannot be coincidence.
SECRETS = {
    "plex_token": "PLEXTOKEN-zzz111aaa222bbb333",
    "tmdb_key": "TMDBKEY-zzz111aaa222bbb333ccc4",
    "fanart_key": "FANARTKEY-zzz111aaa222bbb33",
    "radarr_key": "RADARRKEY-zzz111aaa222bbb333",
    "sonarr_key": "SONARRKEY-zzz111aaa222bbb333",
    "seerr_key": "SEERRKEY-zzz111aaa222bbb3333",
}


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            seed_server(session, "plex", credential=SECRETS["plex_token"])
            set_setting(session, SettingKey.TMDB_API_KEY, SECRETS["tmdb_key"])
            set_setting(session, SettingKey.FANART_API_KEY, SECRETS["fanart_key"])
            set_setting(session, SettingKey.WEBHOOK_URL, "https://hooks.example.com/abc")
            session.commit()
            instance_service.create_radarr(
                session, name="HD", url="http://radarr.test:7878",
                api_key=SECRETS["radarr_key"],
            )
            sonarr_instance_service.create_sonarr(
                session, name="TV", url="http://sonarr.test:8989",
                api_key=SECRETS["sonarr_key"],
            )
            seerr_instance_service.create_seerr(
                session, name="Overseerr", url="http://overseerr.test:5055",
                api_key=SECRETS["seerr_key"],
            )
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def _assert_clean(text: str, where: str) -> None:
    for name, secret in SECRETS.items():
        assert secret not in text, f"{where} leaked the {name}"


#: Every GET route a signed-in user can reach. Kept as a list so adding a page and forgetting to
#: add it here is visible in review rather than silently untested.
BROWSER_PAGES = [
    "/", "/collections", "/shows", "/libraries", "/settings", "/instances", "/activity",
    "/password", "/login",
]

API_ENDPOINTS = [
    "/api/me", "/api/collections/gaps", "/api/matches/review", "/api/spinoffs",
    "/api/instances/radarr", "/api/instances/sonarr", "/api/activity", "/api/tmdb/test",
]


@pytest.mark.parametrize("path", BROWSER_PAGES)
def test_no_page_renders_a_secret(client: TestClient, path: str) -> None:
    response = client.get(f"{BASE}{path}")

    assert response.status_code in (200, 303, 307), f"{path} returned {response.status_code}"
    _assert_clean(response.text, path)


@pytest.mark.parametrize("path", API_ENDPOINTS)
def test_no_api_response_contains_a_secret(client: TestClient, path: str) -> None:
    response = client.get(f"{BASE}{path}")

    _assert_clean(response.text, path)


def test_the_instances_api_omits_keys_entirely(client: TestClient) -> None:
    """Not merely masked -- the field isn't there. A mask that round-trips is a key in transit."""
    for kind in ("radarr", "sonarr"):
        payload = client.get(f"{BASE}/api/instances/{kind}").json()
        for instance in payload["instances"]:
            assert "api_key" not in instance


def test_the_cli_api_key_is_shown_once_and_not_listed_afterwards(client: TestClient) -> None:
    issued = client.post(f"{BASE}/api/me/api-key").json()["api_key"]

    # It must be usable...
    client.cookies.clear()
    assert client.get(f"{BASE}/api/me", headers={API_KEY_HEADER: issued}).status_code == 200
    # ...but not returned by the endpoint that describes the account.
    assert issued not in client.get(f"{BASE}/api/me", headers={API_KEY_HEADER: issued}).text


def test_a_failing_tmdb_check_does_not_echo_the_key(client: TestClient) -> None:
    """Error paths are where secrets escape, because nobody reviews the unhappy path's wording."""
    import responses as responses_lib

    with responses_lib.RequestsMock() as mock:
        mock.add(responses_lib.GET, "https://api.themoviedb.org/3/configuration", status=401)
        body = client.get(f"{BASE}/api/tmdb/test").text

    _assert_clean(body, "the TMDb error path")


def test_an_unreachable_instance_error_does_not_echo_the_key(client: TestClient) -> None:
    import responses as responses_lib

    with responses_lib.RequestsMock() as mock:
        mock.add(responses_lib.GET, "http://radarr.test:7878/api/v3/system/status", status=500,
                 body=f"failed with {SECRETS['radarr_key']}")
        body = client.get(f"{BASE}/instances/radarr/1/test").text

    _assert_clean(body, "the instance test error path")


def test_nothing_is_logged_in_the_clear(client: TestClient, caplog) -> None:
    """The redaction filter covers our own logs and third-party ones alike."""
    from app.logging_config import configure_logging, register_secret

    configure_logging("DEBUG")
    for secret in SECRETS.values():
        register_secret(secret)

    with caplog.at_level(logging.DEBUG):
        for path in BROWSER_PAGES + API_ENDPOINTS:
            client.get(f"{BASE}{path}")

    _assert_clean(caplog.text, "the logs")


def test_the_redacted_export_carries_no_secret(client: TestClient) -> None:
    body = client.get(f"{BASE}/settings/export?redact=1").text

    _assert_clean(body, "the redacted export")
    # A Discord webhook URL lets anyone post to the channel; an Apprise URL holds the token.
    assert "hooks.example.com" not in body


def test_the_diagnostics_bundle_carries_no_secret_and_names_what_did_not_match(client: TestClient) -> None:
    """The bundle is meant for a public issue. Every credential is blanked; the unmatched titles
    -- the thing a matching report is about -- are in it by name."""
    from app.models import LibraryItem, MediaServer

    with Session(get_engine()) as session:
        server = session.exec(select(MediaServer)).first()
        session.add(LibraryItem(server_id=server.id, library_key="1", item_key="m1", item_type="movie",
                                title="Some Obscure Film", year=1987, tmdb_id=None))
        session.add(LibraryItem(server_id=server.id, library_key="1", item_key="m2", item_type="movie",
                                title="Matched Film", year=2001, tmdb_id=42, match_source="guid"))
        session.commit()

    response = client.get(f"{BASE}/settings/diagnostics")
    body = response.text

    assert response.status_code == 200
    assert "franchisarr-diagnostics.json" in response.headers["content-disposition"]
    _assert_clean(body, "the diagnostics bundle")
    document = json.loads(body)
    assert document["config"]["redacted"] is True
    assert document["library"]["unmatched"] == 1
    assert [t["title"] for t in document["unmatched_sample"]] == ["Some Obscure Film"]
    assert document["media_servers"][0]["kind"] == "plex"
    assert document["instances"] == {"radarr": 1, "sonarr": 1, "seerr": 1}


def test_the_full_export_does_carry_them_and_is_marked_as_such(client: TestClient) -> None:
    """The one place a secret is meant to appear. It must be unambiguous about it, or someone
    shares the wrong file."""
    document = json.loads(client.get(f"{BASE}/settings/export").text)

    assert document["redacted"] is False
    assert SECRETS["radarr_key"] in json.dumps(document)


def test_the_export_download_is_named_distinguishably(client: TestClient) -> None:
    """Two files in a downloads folder, one safe to share and one not -- the names must differ."""
    full = client.get(f"{BASE}/settings/export").headers["content-disposition"]
    redacted = client.get(f"{BASE}/settings/export?redact=1").headers["content-disposition"]

    assert full != redacted
    assert "redacted" in redacted


def test_an_anonymous_visitor_cannot_reach_the_export(app_factory) -> None:
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as anon:
        assert anon.get(f"{BASE}/settings/export").status_code in (303, 401, 403)


def test_a_non_admin_cannot_reach_the_export(client: TestClient) -> None:
    """It contains every credential in the install; an ordinary household account must not have
    it."""
    with Session(get_engine()) as session:
        ordinary = User(external_user_id="99", external_username="housemate", is_admin=False)
        session.add(ordinary)
        session.commit()
        session.refresh(ordinary)
        key = generate_api_key(session, ordinary)

    client.cookies.clear()
    response = client.get(f"{BASE}/settings/export", headers={API_KEY_HEADER: key})

    assert response.status_code == 403


def test_stored_media_server_credentials_are_redacted_from_startup(app_factory, caplog) -> None:
    """A Jellyfin key that was in the database before this boot must never appear in a log
    line -- create/update register with the redactor, but a pre-existing row only got
    registered when something first built a client for it."""
    import logging

    from app.logging_config import redact
    from tests.conftest import seed_server

    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False):
        with Session(get_engine()) as session:
            seed_server(session, "jellyfin", credential="JELLYKEY-zzz111aaa222bbb333ccc")
    # Second boot: the row already exists.
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False):
        assert "JELLYKEY-zzz111aaa222bbb333ccc" not in redact("key is JELLYKEY-zzz111aaa222bbb333ccc")
