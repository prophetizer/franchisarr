"""The media-server seam: the factory, a scan through a non-Plex server, and server sign-in."""

from __future__ import annotations

import pytest
import responses
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.clients.emby_client import EmbyLikeClient
from app.clients.media_server import MediaServerKind
from app.clients.plex_client import PlexClient
from app.clients.tmdb_client import TMDB_BASE_URL, TmdbClient
from app.db import get_engine
from app.models import IncludedLibrary, LibraryItem, User
from app.services import media_server_service, scan_service
from app.services.settings_service import SettingKey, set_setting

BASE = "/franchisarr"
JF = "http://jellyfin.test:8096"


def _configure(session: Session, kind: str, url: str = JF, key: str = "k" * 32) -> None:
    set_setting(session, SettingKey.MEDIA_SERVER, kind)
    if kind == "plex":
        set_setting(session, SettingKey.PLEX_URL, url); set_setting(session, SettingKey.PLEX_TOKEN, key)
    elif kind == "jellyfin":
        set_setting(session, SettingKey.JELLYFIN_URL, url); set_setting(session, SettingKey.JELLYFIN_API_KEY, key)
    else:
        set_setting(session, SettingKey.EMBY_URL, url); set_setting(session, SettingKey.EMBY_API_KEY, key)
    session.commit()


# ------------------------------------------------------------------ factory


def test_the_factory_builds_the_configured_server(session: Session) -> None:
    assert media_server_service.client_for(session) is None, "nothing configured yet"
    assert media_server_service.missing_message(session) == "No Plex connection is configured yet."

    _configure(session, "jellyfin")
    client = media_server_service.client_for(session)
    assert isinstance(client, EmbyLikeClient) and client.kind == MediaServerKind.JELLYFIN
    assert media_server_service.label(session) == "Jellyfin"

    _configure(session, "emby")
    assert media_server_service.client_for(session).kind == MediaServerKind.EMBY

    _configure(session, "plex")
    assert isinstance(media_server_service.client_for(session), PlexClient)


def test_a_typo_in_the_kind_falls_back_to_plex(session: Session) -> None:
    set_setting(session, SettingKey.MEDIA_SERVER, "jellyfun"); session.commit()
    assert media_server_service.kind(session) == MediaServerKind.PLEX


def test_the_env_infers_the_kind_from_whichever_url_is_set(monkeypatch) -> None:
    """A Jellyfin-only .env needs no MEDIA_SERVER line."""
    from app.config import _media_server_kind

    monkeypatch.delenv("MEDIA_SERVER", raising=False); monkeypatch.delenv("PLEX_URL", raising=False)
    monkeypatch.setenv("JELLYFIN_URL", JF)
    assert _media_server_kind() == "jellyfin"
    monkeypatch.setenv("PLEX_URL", "http://plex:32400")
    assert _media_server_kind() == "plex", "Plex wins when both are set and nothing says otherwise"
    monkeypatch.setenv("MEDIA_SERVER", "emby")
    assert _media_server_kind() == "emby"


# ------------------------------------------------------------------ a scan through Jellyfin


@responses.activate
def test_a_movie_scan_through_jellyfin_matches_on_provider_ids(session: Session) -> None:
    """No GUID parsing, no per-item refetch: the id is on the item, and the matcher takes it."""
    _configure(session, "jellyfin")
    session.add(IncludedLibrary(library_key="f137a2dd", library_name="Movies", library_type="movie", enabled=True))
    session.commit()
    responses.add(responses.GET, f"{JF}/Items", json={"TotalRecordCount": 2, "Items": [
        {"Id": "a1", "Name": "Beverly Hills Cop", "ProductionYear": 1984, "ProviderIds": {"Tmdb": "90"}},
        {"Id": "a2", "Name": "Beverly Hills Cop II", "ProductionYear": 1987, "ProviderIds": {"Imdb": "tt0092644"}},
    ]})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/90", json={"id": 90, "title": "Beverly Hills Cop", "belongs_to_collection": None})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/find/tt0092644",
                  json={"movie_results": [{"id": 96, "title": "Beverly Hills Cop II", "release_date": "1987-05-20"}]})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/96", json={"id": 96, "title": "Beverly Hills Cop II", "belongs_to_collection": None})

    summary = scan_service.scan_movie_libraries(
        session, media_server_service.client_for(session),
        TmdbClient("k" * 32, max_requests_per_second=10_000), enrich=False)

    assert summary.items_seen == 2 and summary.matched == 2
    rows = {r.item_key: r for r in session.exec(select(LibraryItem))}
    assert rows["a1"].tmdb_id == 90
    assert rows["a2"].tmdb_id == 96, "the IMDb-only item resolved through the existing /find fallback"


# ------------------------------------------------------------------ sign-in


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        yield test_client


def _seed(kind: str) -> None:
    with Session(get_engine()) as session:
        _configure(session, kind)


def test_the_login_page_offers_the_configured_servers_sign_in(client: TestClient) -> None:
    _seed("jellyfin")
    body = client.get(f"{BASE}/login").text
    assert "Sign in with Jellyfin" in body and 'action="/franchisarr/auth/server/login"' in body
    assert "Sign in with Plex" not in body

    _seed("emby")
    assert "Sign in with Emby" in client.get(f"{BASE}/login").text


def test_the_login_page_says_when_the_server_is_not_configured(client: TestClient) -> None:
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.MEDIA_SERVER, "emby"); session.commit()
    body = client.get(f"{BASE}/login").text
    assert "Emby sign-in becomes available once" in body
    assert "configure the Emby connection" in body


@responses.activate
def test_signing_in_with_jellyfin_provisions_the_person(client: TestClient) -> None:
    """The server is the authorisation: an account that signs in there has an account here.
    An administrator there administers here."""
    _seed("jellyfin")
    responses.add(responses.POST, f"{JF}/Users/AuthenticateByName", json={
        "User": {"Id": "u-9", "Name": "alice", "Policy": {"IsAdministrator": False}}, "AccessToken": "t"})

    response = client.post(f"{BASE}/auth/server/login", data={"username": "alice", "password": "pw", "next": "/franchisarr/"})

    assert response.status_code == 303 and response.headers["location"] == "/franchisarr/"
    assert "franchisarr_session" in response.headers.get("set-cookie", "")
    with Session(get_engine()) as session:
        user = session.exec(select(User)).one()
        assert (user.auth_provider, user.external_user_id, user.external_username, user.is_admin) == ("jellyfin", "jellyfin:u-9", "alice", False)

    # and a second sign-in finds the same person rather than making another
    client.post(f"{BASE}/auth/server/login", data={"username": "alice", "password": "pw"})
    with Session(get_engine()) as session:
        assert len(session.exec(select(User)).all()) == 1


@responses.activate
def test_a_wrong_password_gets_one_message_for_both_causes(client: TestClient) -> None:
    _seed("jellyfin")
    responses.add(responses.POST, f"{JF}/Users/AuthenticateByName", status=401)

    response = client.post(f"{BASE}/auth/server/login", data={"username": "alice", "password": "wrong"})

    assert response.status_code == 401 and "Incorrect username or password" in response.text


@responses.activate
def test_an_unreachable_server_is_reported_not_swallowed(client: TestClient) -> None:
    from requests.exceptions import ConnectionError as RequestsConnectionError

    _seed("jellyfin")
    responses.add(responses.POST, f"{JF}/Users/AuthenticateByName", body=RequestsConnectionError("down"))

    response = client.post(f"{BASE}/auth/server/login", data={"username": "alice", "password": "pw"})

    assert response.status_code == 502 and "Could not reach Jellyfin" in response.text


def test_server_sign_in_is_refused_on_a_plex_install(client: TestClient) -> None:
    _seed("plex")
    response = client.post(f"{BASE}/auth/server/login", data={"username": "a", "password": "b"})
    assert response.status_code == 502 and "Plex sign-in isn" in response.text


# ------------------------------------------------------------------ scanning from the UI


def test_the_scan_button_works_on_a_jellyfin_only_install(client: TestClient, monkeypatch) -> None:
    """0.12.0 shipped with the scan route still asking for PLEX_URL, so a Jellyfin install got a
    409 from its own scan button. The check has to be about *the* configured server."""
    from app.services import scan_job

    _seed("jellyfin")
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.TMDB_API_KEY, "t" * 32); session.commit()
        create_local_admin(session, "admin", "correct horse battery")
    client.post(f"{BASE}/login", data={"username": "admin", "password": "correct horse battery"})
    started: list[str] = []
    monkeypatch.setattr(scan_job, "run_in_background",
                        lambda trigger="manual", *, force_refresh=False: started.append(trigger) or True)

    response = client.post(f"{BASE}/scan")

    assert response.status_code == 200, response.text[:200]
    assert started == ["manual"]


def test_the_scan_button_names_the_missing_server(client: TestClient) -> None:
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.MEDIA_SERVER, "emby")
        set_setting(session, SettingKey.TMDB_API_KEY, "t" * 32); session.commit()
        create_local_admin(session, "admin", "correct horse battery")
    client.post(f"{BASE}/login", data={"username": "admin", "password": "correct horse battery"})

    response = client.post(f"{BASE}/scan")

    assert response.status_code == 409
    assert "Emby and TMDb both need configuring" in response.text
