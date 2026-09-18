"""Several media servers behind one boundary: the factory, a scan through Jellyfin, sign-in."""

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
from app.config import get_settings
from app.db import get_engine
from app.models import IncludedLibrary, LibraryItem, MediaServer, User
from app.services import media_server_service, scan_service
from app.services.settings_service import SettingKey, set_setting
from tests.conftest import seed_server

JF = "http://jellyfin.test:8096"
BASE = "/franchisarr"


# ------------------------------------------------------------------ factory


def test_the_factory_builds_a_client_per_server(session: Session) -> None:
    assert media_server_service.is_configured(session) is False, "nothing configured yet"
    assert media_server_service.missing_message(session) == "No media server is configured yet."

    jellyfin = seed_server(session, "jellyfin")
    client = media_server_service.client_for(jellyfin)
    assert isinstance(client, EmbyLikeClient) and client.kind == MediaServerKind.JELLYFIN
    assert media_server_service.label(jellyfin.kind) == "Jellyfin"

    assert media_server_service.client_for(seed_server(session, "emby")).kind == MediaServerKind.EMBY
    assert isinstance(media_server_service.client_for(seed_server(session, "plex")), PlexClient)
    assert [s.name for s in media_server_service.enabled_servers(session)] == ["Emby", "Jellyfin", "Plex"]


def test_a_disabled_server_is_configured_but_not_scanned(session: Session) -> None:
    seed_server(session, "plex", enabled=False)
    assert media_server_service.list_servers(session) and not media_server_service.enabled_servers(session)
    assert media_server_service.is_configured(session) is False


def test_the_env_seeds_one_server_per_configured_kind(session: Session, monkeypatch) -> None:
    """A .env with Plex and Jellyfin in it means both, scanned together -- unless MEDIA_SERVER
    still says which one, which is what it meant in 0.12."""
    monkeypatch.setenv("PLEX_URL", "http://plex:32400"); monkeypatch.setenv("PLEX_TOKEN", "t" * 20)
    monkeypatch.setenv("JELLYFIN_URL", JF); monkeypatch.setenv("JELLYFIN_API_KEY", "k" * 32)
    monkeypatch.setenv("EMBY_URL", "http://emby:8096")  # no key: not a server

    created = media_server_service.seed_from_env(session, get_settings())

    assert [(s.name, s.kind) for s in created] == [("Plex", "plex"), ("Jellyfin", "jellyfin")]
    assert media_server_service.seed_from_env(session, get_settings()) == [], "only ever on an empty table"


def test_media_server_limits_the_seed_to_one_kind(session: Session, monkeypatch) -> None:
    monkeypatch.setenv("PLEX_URL", "http://plex:32400"); monkeypatch.setenv("PLEX_TOKEN", "t" * 20)
    monkeypatch.setenv("JELLYFIN_URL", JF); monkeypatch.setenv("JELLYFIN_API_KEY", "k" * 32)
    monkeypatch.setenv("MEDIA_SERVER", "jellyfin")

    created = media_server_service.seed_from_env(session, get_settings())

    assert [s.kind for s in created] == ["jellyfin"]


def test_removing_a_server_takes_its_scanned_rows_with_it(session: Session) -> None:
    plex = seed_server(session, "plex"); jellyfin = seed_server(session, "jellyfin")
    for server in (plex, jellyfin):
        session.add(IncludedLibrary(server_id=server.id, library_key="1", library_name="Movies", library_type="movie"))
        session.add(LibraryItem(server_id=server.id, library_key="1", item_key="x", title="Film", tmdb_id=90))
    session.commit()

    media_server_service.delete_server(session, jellyfin.id)

    assert [r.server_id for r in session.exec(select(LibraryItem))] == [plex.id]
    assert [r.server_id for r in session.exec(select(IncludedLibrary))] == [plex.id]
    assert session.get(MediaServer, jellyfin.id) is None


def test_an_edit_with_a_blank_credential_keeps_the_old_one(session: Session) -> None:
    server = seed_server(session, "emby", credential="old-key-old-key-old-key")
    media_server_service.update_server(session, server, name="Emby (attic)", credential="")
    assert (server.name, server.credential) == ("Emby (attic)", "old-key-old-key-old-key")


# ------------------------------------------------------------------ a scan through Jellyfin


@responses.activate
def test_a_movie_scan_through_jellyfin_matches_on_provider_ids(session: Session) -> None:
    """No GUID parsing, no per-item refetch: the id is on the item, and the matcher takes it."""
    jellyfin = seed_server(session, "jellyfin", url=JF)
    session.add(IncludedLibrary(server_id=jellyfin.id, library_key="f137a2dd", library_name="Movies", library_type="movie", enabled=True))
    session.commit()
    responses.add(responses.GET, f"{JF}/Users", json=[{"Id": "u1", "Name": "admin", "Policy": {"IsAdministrator": True}}])
    responses.add(responses.GET, f"{JF}/Items", json={"TotalRecordCount": 2, "Items": [
        {"Id": "a1", "Name": "Beverly Hills Cop", "ProductionYear": 1984, "ProviderIds": {"Tmdb": "90"}},
        {"Id": "a2", "Name": "Beverly Hills Cop II", "ProductionYear": 1987, "ProviderIds": {"Imdb": "tt0092644"}},
    ]})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/90", json={"id": 90, "title": "Beverly Hills Cop", "belongs_to_collection": None})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/find/tt0092644",
                  json={"movie_results": [{"id": 96, "title": "Beverly Hills Cop II", "release_date": "1987-05-20"}]})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/96", json={"id": 96, "title": "Beverly Hills Cop II", "belongs_to_collection": None})

    summary = scan_service.scan_movie_libraries(
        session, [scan_service.ScanSource(jellyfin, media_server_service.client_for(jellyfin))],
        TmdbClient("k" * 32, max_requests_per_second=10_000), enrich=False)

    assert summary.items_seen == 2 and summary.matched == 2
    rows = {r.item_key: r for r in session.exec(select(LibraryItem))}
    assert rows["a1"].tmdb_id == 90
    assert rows["a2"].tmdb_id == 96, "the IMDb-only item resolved through the existing /find fallback"
    assert {r.server_id for r in rows.values()} == {jellyfin.id}


@responses.activate
def test_a_scan_reads_every_enabled_server_and_owns_the_union(session: Session) -> None:
    """Two servers, one film on each, one film on both: three rows, two distinct films, and the
    server that is down costs its own libraries and nothing else."""
    jellyfin = seed_server(session, "jellyfin", url=JF)
    emby = seed_server(session, "emby", url="http://emby.test:8096")
    off = seed_server(session, "plex", enabled=False)
    for server, key in ((jellyfin, "j1"), (emby, "e1"), (off, "1")):
        session.add(IncludedLibrary(server_id=server.id, library_key=key, library_name="Movies", library_type="movie", enabled=True))
    session.commit()
    users = [{"Id": "u1", "Name": "admin", "Policy": {"IsAdministrator": True}}]
    responses.add(responses.GET, f"{JF}/Users", json=users)
    responses.add(responses.GET, f"{JF}/Items", json={"TotalRecordCount": 2, "Items": [
        {"Id": "a", "Name": "Beverly Hills Cop", "ProviderIds": {"Tmdb": "90"}, "UserData": {"Played": True}},
        {"Id": "b", "Name": "Beverly Hills Cop II", "ProviderIds": {"Tmdb": "96"}, "UserData": {"Played": False}},
    ]})
    responses.add(responses.GET, "http://emby.test:8096/Users", json=users)
    responses.add(responses.GET, "http://emby.test:8096/Items", json={"TotalRecordCount": 2, "Items": [
        {"Id": "c", "Name": "Beverly Hills Cop", "ProviderIds": {"Tmdb": "90"}, "UserData": {"Played": False}},
        {"Id": "d", "Name": "Beverly Hills Cop III", "ProviderIds": {"Tmdb": "306"}},
    ]})
    for tmdb_id in (90, 96, 306):
        responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/{tmdb_id}", json={"id": tmdb_id, "title": "x", "belongs_to_collection": None})
    sources = [scan_service.ScanSource(s, media_server_service.client_for(s)) for s in media_server_service.enabled_servers(session)]

    summary = scan_service.scan_movie_libraries(session, sources, TmdbClient("k" * 32, max_requests_per_second=10_000), enrich=False)

    assert summary.libraries_scanned == 2 and summary.items_seen == 4
    rows = list(session.exec(select(LibraryItem)))
    assert len(rows) == 4 and len({r.tmdb_id for r in rows}) == 3
    watched = {(r.server_id, r.tmdb_id): r.watched for r in rows}
    assert watched[(jellyfin.id, 90)] is True and watched[(emby.id, 90)] is False
    assert watched[(emby.id, 306)] is None, "no UserData: unknown, not unwatched"
    assert not any(call.request.url.startswith("http://plex.test") for call in responses.calls)


# ------------------------------------------------------------------ sign-in


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        yield test_client


def _seed(kind: str, **fields) -> int:
    with Session(get_engine()) as session:
        return seed_server(session, kind, url=JF if kind == "jellyfin" else None, **fields).id


def test_the_login_page_offers_the_configured_servers_sign_in(client: TestClient) -> None:
    _seed("jellyfin")
    body = client.get(f"{BASE}/login").text
    assert "Sign in with Jellyfin" in body and 'action="/franchisarr/auth/server/login"' in body
    assert "Sign in with Plex" not in body

    _seed("emby")
    assert "Sign in with Jellyfin or Emby" in client.get(f"{BASE}/login").text, "now a choice"


def test_the_login_page_says_when_no_server_is_configured(client: TestClient) -> None:
    body = client.get(f"{BASE}/login").text
    assert "sign-in becomes available once a Plex, Jellyfin or Emby server is configured" in body


def test_two_password_servers_give_the_person_a_choice(client: TestClient) -> None:
    _seed("jellyfin"); _seed("emby")
    body = client.get(f"{BASE}/login").text
    assert '<select name="server_id"' in body and "Jellyfin (Jellyfin)" in body and "Emby (Emby)" in body
    assert "Sign in with Jellyfin or Emby" in body


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


def test_server_sign_in_is_refused_on_a_plex_only_install(client: TestClient) -> None:
    _seed("plex")
    response = client.post(f"{BASE}/auth/server/login", data={"username": "a", "password": "b"})
    assert response.status_code == 502 and "isn&#39;t available to sign in with" in response.text


@responses.activate
def test_the_chosen_server_is_the_one_asked(client: TestClient) -> None:
    _seed("jellyfin"); emby_id = _seed("emby")
    responses.add(responses.POST, "http://emby.test:8096/Users/AuthenticateByName", json={
        "User": {"Id": "e-1", "Name": "bob", "Policy": {"IsAdministrator": True}}})

    response = client.post(f"{BASE}/auth/server/login",
                           data={"username": "bob", "password": "pw", "server_id": str(emby_id)})

    assert response.status_code == 303
    with Session(get_engine()) as session:
        user = session.exec(select(User)).one()
        assert (user.auth_provider, user.external_user_id, user.is_admin) == ("emby", "emby:e-1", True)


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


def test_the_scan_button_says_when_no_server_is_configured(client: TestClient) -> None:
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.TMDB_API_KEY, "t" * 32); session.commit()
        create_local_admin(session, "admin", "correct horse battery")
    client.post(f"{BASE}/login", data={"username": "admin", "password": "correct horse battery"})

    response = client.post(f"{BASE}/scan")

    assert response.status_code == 409
    assert "A media server and TMDb both need configuring" in response.text
