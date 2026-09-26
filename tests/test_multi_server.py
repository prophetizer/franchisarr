"""Several media servers at once: the management page, libraries grouped by server, a film owned
once however many hold it, and watched state on the pages that list owned titles."""

from __future__ import annotations

import pytest
import responses
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import (
    IncludedLibrary, ItemType, LibraryItem, MatchSource, MediaServer, TmdbCollection,
    TmdbCollectionMovie, TmdbMovie,
)
from app.services import library_service, media_server_service
from app.services.ownership_service import owned_details
from tests.conftest import seed_server

BASE = "/franchisarr"
PASSWORD = "correct horse battery staple"
COLLECTION = 86311


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def _two_servers() -> tuple[int, int]:
    with Session(get_engine()) as session:
        plex = seed_server(session, "plex", name="Living room")
        jellyfin = seed_server(session, "jellyfin", name="Attic")
        for server in (plex, jellyfin):
            session.add(IncludedLibrary(server_id=server.id, library_key="1", library_name="Movies",
                                        library_type="movie", enabled=True))
        session.commit()
        return plex.id, jellyfin.id


def _collection(owned: dict[int, list[tuple[int, bool | None]]]) -> None:
    """A three-film collection; `owned` maps server id -> [(tmdb_id, watched)]."""
    with Session(get_engine()) as session:
        session.add(TmdbCollection(tmdb_collection_id=COLLECTION, name="Beverly Hills Cop Collection"))
        for position, (tmdb_id, title, year) in enumerate([
            (90, "Beverly Hills Cop", 1984), (96, "Beverly Hills Cop II", 1987), (306, "Beverly Hills Cop III", 1994),
        ]):
            session.add(TmdbCollectionMovie(collection_id=COLLECTION, tmdb_movie_id=tmdb_id, title=title,
                                            release_year=year, release_date=f"{year}-06-01", position=position))
        for server_id, films in owned.items():
            for tmdb_id, watched in films:
                session.add(LibraryItem(server_id=server_id, library_key="1", item_key=f"{server_id}-{tmdb_id}",
                                        item_type=ItemType.MOVIE.value, title=str(tmdb_id), tmdb_id=tmdb_id,
                                        match_source=MatchSource.GUID.value, watched=watched))
                if not session.get(TmdbMovie, tmdb_id):
                    session.add(TmdbMovie(tmdb_id=tmdb_id, title=str(tmdb_id), collection_id=COLLECTION))
        session.commit()


# ------------------------------------------------------------------ ownership


def test_a_film_on_two_servers_is_owned_once_with_both_named(session: Session) -> None:
    plex = seed_server(session, "plex", name="Living room"); jf = seed_server(session, "jellyfin", name="Attic")
    session.add(LibraryItem(server_id=plex.id, library_key="1", item_key="a", title="x", tmdb_id=90, watched=False))
    session.add(LibraryItem(server_id=jf.id, library_key="1", item_key="b", title="x", tmdb_id=90, watched=True))
    session.add(LibraryItem(server_id=jf.id, library_key="1", item_key="c", title="y", tmdb_id=96, watched=None))
    session.commit()

    details = owned_details(session)

    assert details[90].servers == ("Attic", "Living room") and details[90].watched is True
    assert details[96].servers == ("Attic",) and details[96].watched is None
    assert details[90].where == "Attic, Living room"


def test_the_collection_counts_films_not_copies(client: TestClient) -> None:
    plex, jellyfin = _two_servers()
    _collection({plex: [(90, False)], jellyfin: [(90, True), (96, None)]})

    body = client.get(f"{BASE}/collections/{COLLECTION}").text

    assert "2 of 3 in your library, 1 watched." in body
    assert body.count('film-tile owned') == 2
    assert "on Attic, Living room" in body, "a two-server install says where a film is"
    assert 'class="watched-mark"' in body


def test_a_single_server_install_does_not_name_it(client: TestClient) -> None:
    with Session(get_engine()) as session:
        only = seed_server(session, "plex").id
    _collection({only: [(90, True)]})

    body = client.get(f"{BASE}/collections/{COLLECTION}").text

    assert "1 of 3 in your library, 1 watched." in body
    assert "owned-where" not in body and 'class="watched-mark"' in body


# ------------------------------------------------------------------ started-watching filter


def test_the_started_filter_keeps_collections_someone_has_begun(client: TestClient) -> None:
    with Session(get_engine()) as session:
        only = seed_server(session, "plex").id
        session.add(TmdbCollection(tmdb_collection_id=2, name="Untouched Collection"))
        for position, tmdb_id in enumerate((500, 501)):
            session.add(TmdbCollectionMovie(collection_id=2, tmdb_movie_id=tmdb_id, title=f"U{tmdb_id}",
                                            release_year=2000, release_date="2000-01-01", position=position))
        session.add(TmdbMovie(tmdb_id=500, title="U500", collection_id=2))
        session.add(LibraryItem(server_id=only, library_key="1", item_key="u", item_type=ItemType.MOVIE.value,
                                title="U500", tmdb_id=500, match_source=MatchSource.GUID.value, watched=False))
        session.commit()
    _collection({only: [(90, True)]})

    everything = client.get(f"{BASE}/collections").text
    started = client.get(f"{BASE}/collections?started=1").text

    assert "Beverly Hills Cop Collection" in everything and "Untouched Collection" in everything
    assert "Beverly Hills Cop Collection" in started and "Untouched Collection" not in started
    assert "<strong>started watching</strong>" in started


def test_the_filter_is_not_offered_before_any_server_reports_watched_state(client: TestClient) -> None:
    with Session(get_engine()) as session:
        only = seed_server(session, "plex").id
    _collection({only: [(90, None)]})

    body = client.get(f"{BASE}/collections?started=1").text

    assert "started watching" not in body
    assert "Beverly Hills Cop Collection" in body, "and asking for it hides nothing"


# ------------------------------------------------------------------ libraries page


@responses.activate
def test_the_libraries_page_groups_by_server_and_survives_one_being_down(client: TestClient) -> None:
    plex, jellyfin = _two_servers()
    responses.add(responses.GET, "http://jellyfin.test:8096/Library/VirtualFolders",
                  json=[{"Name": "Films", "CollectionType": "movies", "ItemId": "abc"}])
    # Plex is down: its stored library stays, with a note.

    body = client.get(f"{BASE}/libraries").text

    assert "<h2>Attic</h2>" in body and "<h2>Living room</h2>" in body
    assert "Films" in body and "Movies" in body
    assert "Living room: " in body and "Showing the libraries last seen" in body
    with Session(get_engine()) as session:
        assert [(r.library_key, r.enabled) for r in library_service.list_libraries(session, jellyfin)] == \
               [("abc", False)], "Jellyfin answered, so its stale library went and the new one arrived off"
        assert [(r.library_key, r.enabled) for r in library_service.list_libraries(session, plex)] == \
               [("1", True)], "Plex didn't answer, so what was stored stays"


def test_saving_the_selection_posts_row_ids(client: TestClient) -> None:
    plex, jellyfin = _two_servers()
    with Session(get_engine()) as session:
        ids = {lib.server_id: lib.id for lib in library_service.list_libraries(session)}

    response = client.post(f"{BASE}/libraries", data={"keys": [str(ids[jellyfin])]})

    assert response.status_code == 303
    with Session(get_engine()) as session:
        enabled = library_service.enabled_libraries(session)
        assert [lib.server_id for lib in enabled] == [jellyfin]


def test_the_libraries_page_points_at_media_servers_when_there_are_none(client: TestClient) -> None:
    body = client.get(f"{BASE}/libraries").text
    assert "No media server is configured yet" in body and 'href="/franchisarr/media-servers"' in body


# ------------------------------------------------------------------ media-servers page


def test_the_media_servers_page_lists_masked_credentials(client: TestClient) -> None:
    with Session(get_engine()) as session:
        seed_server(session, "jellyfin", name="Attic", credential="abcdefghijklmnopqrstuvwxyz123456",
                    watched_user="michael")

    body = client.get(f"{BASE}/media-servers").text

    assert "Attic" in body and "3456" in body and "abcdefghijkl" not in body
    assert "watched as michael" in body


def test_adding_editing_and_removing_a_server(client: TestClient) -> None:
    response = client.post(f"{BASE}/media-servers", data={
        "name": "Attic", "kind": "emby", "url": "http://emby.test:8096/", "credential": "k" * 32,
        "watched_user": "",
    })
    assert response.status_code == 303 and response.headers["location"].endswith("/media-servers?saved=1")
    with Session(get_engine()) as session:
        server = session.exec(select(MediaServer)).one()
        assert (server.name, server.kind, server.url, server.watched_user, server.enabled) == \
               ("Attic", "emby", "http://emby.test:8096", None, True)
        server_id = server.id

    client.post(f"{BASE}/media-servers/{server_id}", data={
        "name": "Attic Emby", "url": "http://emby.test:8096", "credential": "", "watched_user": "bob",
    })
    with Session(get_engine()) as session:
        server = session.get(MediaServer, server_id)
        assert (server.name, server.credential, server.watched_user, server.enabled) == \
               ("Attic Emby", "k" * 32, "bob", False), "blank credential kept; unticked box disables"

    client.post(f"{BASE}/media-servers/{server_id}/delete")
    with Session(get_engine()) as session:
        assert session.exec(select(MediaServer)).all() == []


def test_a_duplicate_name_is_refused_with_a_message(client: TestClient) -> None:
    with Session(get_engine()) as session:
        seed_server(session, "plex", name="Attic")

    response = client.post(f"{BASE}/media-servers", data={
        "name": "Attic", "kind": "plex", "url": "http://plex2.test:32400", "credential": "t" * 20})

    assert "already+exists" in response.headers["location"]
    assert "already exists" in client.get(response.headers["location"]).text


def test_changing_a_plex_url_forgets_its_identity(client: TestClient) -> None:
    with Session(get_engine()) as session:
        server_id = seed_server(session, "plex", machine_identifier="abc").id

    client.post(f"{BASE}/media-servers/{server_id}", data={
        "name": "Plex", "url": "http://elsewhere.test:32400", "enabled": "1"})

    with Session(get_engine()) as session:
        assert session.get(MediaServer, server_id).machine_identifier is None


@responses.activate
def test_testing_a_plex_server_learns_its_identity(client: TestClient, fixtures_dir) -> None:
    with Session(get_engine()) as session:
        server_id = seed_server(session, "plex").id
    responses.add(responses.GET, "http://plex.test:32400/",
                  body=(fixtures_dir / "plex" / "root.xml").read_text(), content_type="application/xml")

    body = client.get(f"{BASE}/media-servers/{server_id}/test").text

    assert "Reachable" in body
    with Session(get_engine()) as session:
        assert session.get(MediaServer, server_id).machine_identifier


def test_a_non_admin_can_see_but_not_change_servers(app_factory) -> None:
    from app.models import User

    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as viewer:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            user = session.exec(select(User)).one(); user.is_admin = False
            session.add(user); session.commit()
            seed_server(session, "plex")
        viewer.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})

        assert viewer.get(f"{BASE}/media-servers").status_code == 200
        assert viewer.post(f"{BASE}/media-servers", data={
            "name": "x", "kind": "plex", "url": "http://p", "credential": "t" * 20}).status_code == 403
