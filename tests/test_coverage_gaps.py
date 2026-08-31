"""Tests for paths the suite reached only incidentally.

Written after measuring coverage in Phase 10 rather than guessing: library syncing, Plex user
provisioning, the TV scan, and the TV routes were the thinnest areas.
"""

from __future__ import annotations

import pytest
import responses
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth import plex_oauth
from app.auth.local_admin import create_local_admin
from app.clients.plex_client import PlexClient, PlexLibrary
from app.clients.tmdb_client import TMDB_BASE_URL, TmdbClient
from app.db import get_engine
from app.models import IncludedLibrary, ItemType, LibraryItem, MatchSource, TmdbShow, User
from app.services import auth_service, library_service, scan_service, tv_spinoff_service
from app.services.settings_service import SettingKey, get_setting, set_setting

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"
OUR_SERVER = "abc123def456abc123def456abc123def456abc1"
PLEX = "http://plex.test:32400"


def _lib(key: str, title: str, kind: str = "movie") -> PlexLibrary:
    return PlexLibrary(key=key, title=title, library_type=kind)


# ------------------------------------------------------------------ library syncing


def test_new_libraries_arrive_disabled(session: Session) -> None:
    """A fresh install must not start scanning home videos on its own."""
    library_service.sync_libraries(session, [_lib("1", "Movies"), _lib("2", "TV", "show")])

    assert all(not lib.enabled for lib in library_service.list_libraries(session))


def test_a_resync_preserves_the_users_choice(session: Session) -> None:
    library_service.sync_libraries(session, [_lib("1", "Movies")])
    library_service.set_enabled_libraries(session, ["1"])

    library_service.sync_libraries(session, [_lib("1", "Movies")])

    assert library_service.list_libraries(session)[0].enabled is True


def test_a_renamed_library_keeps_its_selection(session: Session) -> None:
    """Renaming it in Plex shouldn't silently drop it out of scans."""
    library_service.sync_libraries(session, [_lib("1", "Movies")])
    library_service.set_enabled_libraries(session, ["1"])

    library_service.sync_libraries(session, [_lib("1", "Films")])

    rows = library_service.list_libraries(session)
    assert rows[0].plex_library_name == "Films"
    assert rows[0].enabled is True


def test_a_library_removed_from_plex_disappears(session: Session) -> None:
    """Offering a checkbox for something that no longer exists is just confusing."""
    library_service.sync_libraries(session, [_lib("1", "Movies"), _lib("2", "Old")])

    library_service.sync_libraries(session, [_lib("1", "Movies")])

    assert [lib.plex_library_key for lib in library_service.list_libraries(session)] == ["1"]


def test_setting_the_selection_replaces_it_wholesale(session: Session) -> None:
    """The form posts every ticked box, so anything absent was deliberately unticked."""
    library_service.sync_libraries(session, [_lib("1", "Movies"), _lib("2", "TV", "show")])
    library_service.set_enabled_libraries(session, ["1", "2"])

    library_service.set_enabled_libraries(session, ["2"])

    assert [lib.plex_library_key for lib in library_service.enabled_libraries(session)] == ["2"]


def test_has_selection_reflects_reality(session: Session) -> None:
    library_service.sync_libraries(session, [_lib("1", "Movies")])
    assert library_service.has_selection(session) is False

    library_service.set_enabled_libraries(session, ["1"])
    assert library_service.has_selection(session) is True


# ------------------------------------------------------------------ Plex provisioning


def _account(user_id: str = "5551234", username: str = "michael") -> plex_oauth.PlexAccount:
    return plex_oauth.PlexAccount(id=user_id, username=username)


def test_the_server_owner_is_provisioned_as_an_admin(session: Session) -> None:
    user = auth_service.provision_plex_user(session, _account(), is_owner=True)

    assert user.is_admin is True
    assert user.plex_username == "michael"


def test_a_shared_user_is_provisioned_without_admin(session: Session) -> None:
    user = auth_service.provision_plex_user(session, _account("999", "housemate"), is_owner=False)

    assert user.is_admin is False


def test_signing_in_again_updates_the_username_without_duplicating(session: Session) -> None:
    """Plex usernames change; the account is keyed on the Plex user id."""
    auth_service.provision_plex_user(session, _account(username="old"), is_owner=True)

    auth_service.provision_plex_user(session, _account(username="new"), is_owner=True)

    users = session.exec(select(User)).all()
    assert len(users) == 1
    assert users[0].plex_username == "new"


def test_admin_is_not_revoked_by_a_later_non_owner_sign_in(session: Session) -> None:
    """Losing admin because plex.tv briefly reported ownership differently would be alarming."""
    auth_service.provision_plex_user(session, _account(), is_owner=True)

    user = auth_service.provision_plex_user(session, _account(), is_owner=False)

    assert user.is_admin is True


def test_the_client_id_is_generated_once_and_kept(session: Session) -> None:
    """plex.tv ties a PIN to the client identifier that created it, so a value that changed per
    request would break sign-in halfway through."""
    first = auth_service.get_or_create_client_id(session)

    assert auth_service.get_or_create_client_id(session) == first
    assert get_setting(session, SettingKey.PLEX_CLIENT_ID) == first


@responses.activate
def test_sign_in_is_refused_when_the_account_cannot_reach_this_server(session: Session) -> None:
    auth_service.remember_machine_identifier(session, OUR_SERVER)
    responses.add(responses.GET, plex_oauth.PLEX_RESOURCES_URL,
                  json=[{"clientIdentifier": "someone-elses", "provides": "server", "owned": True}])

    with pytest.raises(auth_service.PlexAccessDenied):
        auth_service.sign_in_with_plex_token(session, "a-valid-looking-token")

    assert session.exec(select(User)).all() == []


@responses.activate
def test_discovering_the_machine_identifier(session: Session, fixtures_dir) -> None:
    plex_dir = fixtures_dir / "plex"
    responses.add(responses.GET, f"{PLEX}/", body=(plex_dir / "root.xml").read_text(),
                  content_type="application/xml")

    found = auth_service.discover_machine_identifier(session, PlexClient(PLEX, "token"))

    assert found
    assert auth_service.get_machine_identifier(session) == found


@responses.activate
def test_an_unreachable_plex_leaves_sign_in_unavailable(session: Session) -> None:
    """Failing to learn the server's identity must not be fatal -- it just means Plex sign-in
    stays off until the server can be reached, which is the conservative outcome."""
    responses.add(responses.GET, f"{PLEX}/", status=500)

    assert auth_service.discover_machine_identifier(session, PlexClient(PLEX, "token")) is None
    assert auth_service.get_machine_identifier(session) is None


# ------------------------------------------------------------------ the TV scan


@responses.activate
def test_a_tv_scan_populates_the_snapshot_and_show_cache(session: Session, fixtures_dir) -> None:
    plex_dir = fixtures_dir / "plex"
    for name, url in [
        ("root.xml", f"{PLEX}/"),
        ("library.xml", f"{PLEX}/library"),
        ("library_sections.xml", f"{PLEX}/library/sections"),
        ("section_2_shows.xml", f"{PLEX}/library/sections/2/all"),
    ]:
        responses.add(responses.GET, url, body=(plex_dir / name).read_text(),
                      content_type="application/xml")
    responses.add(responses.GET, f"{TMDB_BASE_URL}/tv/1621",
                  json={"id": 1621, "name": "NCIS", "first_air_date": "2003-09-23",
                        "networks": [{"name": "CBS"}]})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/tv/44006",
                  json={"id": 44006, "name": "Chicago Fire", "first_air_date": "2012-10-10",
                        "networks": [{"name": "NBC"}]})

    session.add(IncludedLibrary(plex_library_key="2", plex_library_name="TV Shows",
                                library_type="show", enabled=True))
    session.commit()

    summary = scan_service.scan_show_libraries(
        session, PlexClient(PLEX, "token"), TmdbClient("k" * 32, max_requests_per_second=10_000)
    )

    assert summary.items_seen == 2
    assert summary.matched == 2
    shows = session.exec(select(TmdbShow)).all()
    assert {s.name for s in shows} == {"NCIS", "Chicago Fire"}
    assert {s.network for s in shows} == {"CBS", "NBC"}


def test_a_tv_scan_with_no_enabled_libraries_says_so(session: Session) -> None:
    summary = scan_service.scan_show_libraries(
        session, PlexClient(PLEX, "t"), TmdbClient("k" * 32)
    )

    assert "No TV libraries are enabled" in summary.errors[0]


def test_the_movie_scan_ignores_show_libraries_and_vice_versa(session: Session) -> None:
    """They share the snapshot table, so each has to filter by type."""
    session.add(IncludedLibrary(plex_library_key="2", plex_library_name="TV",
                                library_type="show", enabled=True))
    session.commit()

    summary = scan_service.scan_movie_libraries(
        session, PlexClient(PLEX, "t"), TmdbClient("k" * 32)
    )

    assert "No movie libraries are enabled" in summary.errors[0]


# ------------------------------------------------------------------ TV routes


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def _own_show(tmdb_id: int, title: str) -> None:
    with Session(get_engine()) as session:
        session.add(LibraryItem(plex_library_key="2", rating_key=str(tmdb_id),
                                item_type=ItemType.SHOW.value, title=title, year=2003,
                                tmdb_id=tmdb_id, match_source=MatchSource.GUID.value))
        session.commit()


def test_removing_a_mapping_from_the_ui(client: TestClient) -> None:
    from app.models import SpinoffMapping

    _own_show(4614, "NCIS")
    with Session(get_engine()) as session:
        mapping = tv_spinoff_service.add_mapping(
            session, source_show_tmdb_id=4614, spinoff_show_tmdb_id=17610
        )
        mapping_id = mapping.id

    response = client.post(f"{BASE}/shows/mappings/{mapping_id}/delete")

    assert response.status_code == 200
    with Session(get_engine()) as session:
        assert session.exec(select(SpinoffMapping)).all() == []


def test_dismissing_a_spinoff_stops_it_being_suggested(client: TestClient) -> None:
    """Dismissing means "don't suggest this to me", not "forget this is a spin-off". The mapping
    stays in the management list; only the actionable suggestion goes."""
    _own_show(4614, "NCIS")
    with Session(get_engine()) as session:
        session.add(TmdbShow(tmdb_id=17610, name="NCIS: Los Angeles"))
        session.commit()
        tv_spinoff_service.add_mapping(session, source_show_tmdb_id=4614,
                                       spinoff_show_tmdb_id=17610)

    before = client.get(f"{BASE}/shows").text
    assert f"{BASE}/shows/add/17610" in before, "offered as something to add"

    client.post(f"{BASE}/shows/dismiss/17610")

    after = client.get(f"{BASE}/shows").text
    assert f"{BASE}/shows/add/17610" not in after, "no longer offered"
    assert "NCIS: Los Angeles" in after, "but the mapping itself is still listed"


def test_dismissing_the_same_show_twice_is_harmless(client: TestClient) -> None:
    _own_show(4614, "NCIS")

    client.post(f"{BASE}/shows/dismiss/17610")
    assert client.post(f"{BASE}/shows/dismiss/17610").status_code == 200


def test_the_add_show_dialog_reports_no_sonarr_configured(client: TestClient) -> None:
    _own_show(4614, "NCIS")

    assert "No Sonarr instance is configured" in client.get(f"{BASE}/shows/add/17610").text


def test_closing_the_dialogs_returns_nothing(client: TestClient) -> None:
    assert client.get(f"{BASE}/shows/add/close").text == ""
    assert client.get(f"{BASE}/shows/candidates/close").text == ""
    assert client.get(f"{BASE}/add/close").text == ""


def test_a_mapping_of_a_show_to_itself_is_refused(client: TestClient) -> None:
    response = client.post(f"{BASE}/shows/mappings", data={
        "source_show_tmdb_id": 4614, "spinoff_show_tmdb_id": 4614,
    })

    assert response.status_code == 400
