"""Switching a media server off and on, "use only this server", and scanning one server.

Off means off: before this, a disabled server was skipped by scans and playlists but everything
it had already scanned still counted as owned, so turning Jellyfin off showed exactly what it
showed before. The rows stay (turning it back on needs no rescan); only the counting changes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import (
    ItemType, LibraryItem, MatchSource, MediaServer, SeenGap, TmdbCollection, TmdbCollectionMovie,
    TmdbMovie,
)
from app.services import media_server_service, movie_gap_service, scan_job, tv_spinoff_service
from app.services.ownership_service import owned_details
from app.services.settings_service import SettingKey, get_setting, set_setting
from tests.conftest import seed_server

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"
COLLECTION = 85861


def _item(session: Session, server: MediaServer, tmdb_id: int, *, show: bool = False) -> None:
    session.add(LibraryItem(server_id=server.id, library_key="1", item_key=f"{server.id}-{tmdb_id}",
                            item_type=(ItemType.SHOW if show else ItemType.MOVIE).value,
                            title=f"Title {tmdb_id}", tmdb_id=tmdb_id, match_source=MatchSource.GUID.value))
    session.commit()


def _three(session: Session) -> tuple[MediaServer, MediaServer, MediaServer]:
    return seed_server(session, "plex"), seed_server(session, "jellyfin"), seed_server(session, "emby")


# ------------------------------------------------------------------ what counts as owned


def test_a_server_that_is_off_owns_nothing_until_it_is_back_on(session: Session) -> None:
    plex, jellyfin, _ = _three(session)
    _item(session, plex, 1)
    _item(session, jellyfin, 2)
    _item(session, jellyfin, 20, show=True)

    media_server_service.set_enabled(session, jellyfin, False)

    assert movie_gap_service.owned_tmdb_ids(session) == {1}
    assert tv_spinoff_service.owned_show_ids(session) == set()
    assert tv_spinoff_service.owned_shows(session) == []
    assert 2 not in owned_details(session), "nor is it listed as 'on Jellyfin'"
    # The rows are untouched, and scan-time steps still see them.
    assert movie_gap_service.owned_tmdb_ids(session, all_servers=True) == {1, 2}
    assert tv_spinoff_service.owned_show_ids(session, all_servers=True) == {20}

    media_server_service.set_enabled(session, jellyfin, True)

    assert movie_gap_service.owned_tmdb_ids(session) == {1, 2}, "back on, no rescan"
    assert owned_details(session)[2].servers == ("Jellyfin",)


def test_a_title_on_two_servers_stays_owned_when_one_is_off(session: Session) -> None:
    plex, jellyfin, _ = _three(session)
    _item(session, plex, 1)
    _item(session, jellyfin, 1)

    media_server_service.set_enabled(session, plex, False)

    assert movie_gap_service.owned_tmdb_ids(session) == {1}
    assert owned_details(session)[1].servers == ("Jellyfin",)


# ------------------------------------------------------------------ use only this server


def _enabled(session: Session) -> list[str]:
    session.expire_all()
    return [s.name for s in media_server_service.enabled_servers(session)]


def test_use_only_turns_the_others_off_and_restore_brings_back_exactly_those(session: Session) -> None:
    plex, jellyfin, emby = _three(session)
    media_server_service.set_enabled(session, emby, False)  # off before, and stays off after

    media_server_service.use_only(session, jellyfin)
    assert _enabled(session) == ["Jellyfin"]
    assert media_server_service.solo_state(session) == {"on": ["Jellyfin"], "off": ["Plex"]}

    assert media_server_service.restore_others(session) == 1
    assert _enabled(session) == ["Jellyfin", "Plex"]
    assert media_server_service.solo_state(session) is None
    assert get_setting(session, SettingKey.SOLO_RESTORE) is None


def test_moving_from_one_server_to_another_still_restores_the_starting_point(session: Session) -> None:
    plex, jellyfin, emby = _three(session)

    media_server_service.use_only(session, jellyfin)
    media_server_service.use_only(session, emby)
    assert _enabled(session) == ["Emby"]
    assert sorted(media_server_service.solo_state(session)["off"]) == ["Jellyfin", "Plex"]

    media_server_service.restore_others(session)
    assert _enabled(session) == ["Emby", "Jellyfin", "Plex"]


def test_the_banner_goes_once_everything_is_back_on_by_hand(session: Session) -> None:
    plex, jellyfin, _ = _three(session)
    media_server_service.use_only(session, plex)

    for server in (jellyfin, session.exec(select(MediaServer).where(MediaServer.name == "Emby")).one()):
        media_server_service.set_enabled(session, server, True)

    assert media_server_service.solo_state(session) is None


def test_sign_in_still_goes_through_a_server_use_only_paused(session: Session) -> None:
    """Otherwise a session lapsing mid-test locks out anyone who signs in through Plex. A server
    turned off by hand (or restored from a backup, which arrives off) stays refused."""
    plex, jellyfin, emby = _three(session)
    media_server_service.set_enabled(session, emby, False)

    media_server_service.use_only(session, jellyfin)

    assert [s.name for s in media_server_service.plex_servers(session)] == ["Plex"]
    assert [s.name for s in media_server_service.password_servers(session)] == ["Jellyfin"]

    media_server_service.restore_others(session)
    media_server_service.set_enabled(session, plex, False)
    assert media_server_service.plex_servers(session) == []


# ------------------------------------------------------------------ scanning


def test_a_scan_can_be_narrowed_to_one_server(session: Session) -> None:
    plex, jellyfin, _ = _three(session)
    set_setting(session, SettingKey.TMDB_API_KEY, "k" * 32)
    session.commit()

    sources, _, _, errors = scan_job._clients(session, jellyfin.id)

    assert errors == []
    assert [source.server.name for source in sources] == ["Jellyfin"]
    assert len(scan_job._clients(session)[0]) == 3


def test_a_film_on_a_server_that_is_off_is_not_announced_as_a_new_gap(session: Session, monkeypatch) -> None:
    """Announcing it would mark it reported, and when it really did go missing later it would
    never be announced at all."""
    plex, jellyfin, emby = _three(session)
    session.add(TmdbCollection(tmdb_collection_id=COLLECTION, name="Beverly Hills Cop Collection"))
    for position, tmdb_id in enumerate((90, 96)):
        session.add(TmdbCollectionMovie(collection_id=COLLECTION, tmdb_movie_id=tmdb_id, title=f"BHC {tmdb_id}",
                                        release_year=1984 + position, release_date=f"{1984 + position}-06-01",
                                        position=position))
        session.add(TmdbMovie(tmdb_id=tmdb_id, title=f"BHC {tmdb_id}", collection_id=COLLECTION))
    set_setting(session, SettingKey.TMDB_API_KEY, "k" * 32)
    session.commit()
    _item(session, plex, 90)
    _item(session, jellyfin, 96)
    media_server_service.set_enabled(session, emby, False)
    for name in ("scan_movie_libraries", "scan_show_libraries"):
        monkeypatch.setattr(scan_job.scan_service, name, lambda *a, **k: scan_job.scan_service.ScanSummary())
    monkeypatch.setattr(scan_job.instance_service, "refresh_all", lambda s: [])
    monkeypatch.setattr(scan_job.sonarr_instance_service, "refresh_all", lambda s: [])

    media_server_service.use_only(session, plex)
    result = scan_job.run(session, notify=False)

    missing = [m.tmdb_id for gap in movie_gap_service.collections_with_gaps(session) for m in gap.missing]
    assert missing == [96], "the page shows what Plex alone lacks"
    assert result.report.new_movies == []
    assert session.exec(select(SeenGap)).all() == []


# ------------------------------------------------------------------ the page


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            _three(session)
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def _server(name: str) -> MediaServer:
    with Session(get_engine()) as session:
        return session.exec(select(MediaServer).where(MediaServer.name == name)).one()


def test_the_page_turns_a_server_off_and_on_in_one_click(client: TestClient) -> None:
    jellyfin = _server("Jellyfin")
    page = client.get(f"{BASE}/media-servers").text
    assert f'action="{BASE}/media-servers/{jellyfin.id}/toggle"' in page
    assert f'action="{BASE}/media-servers/{jellyfin.id}/only"' in page

    assert client.post(f"{BASE}/media-servers/{jellyfin.id}/toggle").status_code == 303
    assert _server("Jellyfin").enabled is False
    assert "Turn on" in client.get(f"{BASE}/media-servers").text

    client.post(f"{BASE}/media-servers/{jellyfin.id}/toggle")
    assert _server("Jellyfin").enabled is True


def test_use_only_shows_a_banner_on_every_page_until_restored(client: TestClient) -> None:
    client.post(f"{BASE}/media-servers/{_server('Emby').id}/only")

    page = client.get(f"{BASE}/collections").text
    assert "Showing only <strong>Emby</strong>" in page
    assert "Jellyfin and Plex" in " ".join(page.split()), "names the ones it turned off"
    assert f'action="{BASE}/media-servers/restore"' in page

    response = client.post(f"{BASE}/media-servers/restore",
                           headers={"referer": f"http://testserver{BASE}/collections?sort=name"})
    assert response.headers["location"] == f"{BASE}/collections?sort=name", "back where it was pressed"
    assert "Showing only" not in client.get(f"{BASE}/collections").text
    assert all(_server(n).enabled for n in ("Plex", "Jellyfin", "Emby"))


def test_restore_never_redirects_off_site(client: TestClient) -> None:
    client.post(f"{BASE}/media-servers/{_server('Emby').id}/only")

    response = client.post(f"{BASE}/media-servers/restore", headers={"referer": "https://evil.example//x"})

    assert response.headers["location"] == f"{BASE}/"


def test_the_scan_button_scans_that_server_only(client: TestClient, monkeypatch) -> None:
    started = []
    monkeypatch.setattr(scan_job, "run_in_background", lambda trigger, **k: started.append(k) or True)
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.TMDB_API_KEY, "k" * 32)
        session.commit()
    jellyfin = _server("Jellyfin")

    assert client.post(f"{BASE}/media-servers/{jellyfin.id}/scan").status_code == 200
    assert started == [{"server_id": jellyfin.id}]

    client.post(f"{BASE}/media-servers/{jellyfin.id}/toggle")
    started.clear()
    refused = client.post(f"{BASE}/media-servers/{jellyfin.id}/scan")
    assert refused.status_code == 200 and "Jellyfin is turned off" in refused.text
    assert started == [], "off: nothing to scan"


def test_the_home_page_counts_libraries_per_server_that_is_on(client: TestClient) -> None:
    """It said "Scanning 6 Plex libraries" when two were on Jellyfin and two on Emby, and
    counted servers that were turned off, which a scan skips."""
    from app.models import IncludedLibrary

    with Session(get_engine()) as session:
        for name, count in (("Plex", 2), ("Jellyfin", 2), ("Emby", 1)):
            server = session.exec(select(MediaServer).where(MediaServer.name == name)).one()
            for key in range(count):
                session.add(IncludedLibrary(server_id=server.id, library_key=str(key), library_name=f"L{key}",
                                            library_type="movie", enabled=True))
        session.commit()
    flat = lambda html: " ".join(html.split())  # noqa: E731

    assert "Scanning 5 libraries: 1 on Emby, 2 on Jellyfin, 2 on Plex." in flat(client.get(f"{BASE}/").text)

    client.post(f"{BASE}/media-servers/{_server('Plex').id}/only")
    home = flat(client.get(f"{BASE}/").text)
    assert "Scanning 2 libraries on Plex." in home and "Plex libraries" not in home
