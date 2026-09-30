"""Showcase's celebrations (0.49.0): a collection completed by a scan, celebrated once per person."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import (
    CollectionCompletion, IncludedLibrary, LibraryItem, MatchSource, TmdbCollection, TmdbCollectionMovie, TmdbMovie, User,
)
from app.services import celebrations, look
from tests.conftest import seed_server

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"


def _collection(session: Session, server: int, cid: int, films: list[int], owned: list[int]) -> None:
    session.add(TmdbCollection(tmdb_collection_id=cid, name=f"Collection {cid}"))
    for pos, tid in enumerate(films):
        session.add(TmdbCollectionMovie(collection_id=cid, tmdb_movie_id=tid, title=f"Film {tid}",
                                        release_date="2000-01-01", release_year=2000, position=pos))
        session.add(TmdbMovie(tmdb_id=tid, title=f"Film {tid}", collection_id=cid))
    for tid in owned:
        _own(session, server, tid)
    session.commit()


def _own(session: Session, server: int, tid: int) -> None:
    session.add(LibraryItem(server_id=server, library_key="1", item_key=f"k{tid}", item_type="movie", title=f"Film {tid}",
                            tmdb_id=tid, match_source=MatchSource.GUID.value))
    session.commit()


def _library(session: Session) -> int:
    server = seed_server(session).id
    session.add(IncludedLibrary(server_id=server, library_key="1", library_name="Films", library_type="movie",
                                enabled=True))
    _collection(session, server, 1, [11, 12], [11, 12])         # already complete
    _collection(session, server, 2, [21, 22], [21])             # one to go
    return server


def test_the_first_record_is_quiet_and_a_later_completion_is_news(session: Session) -> None:
    server = _library(session)

    assert celebrations.record(session) == [], "complete before anyone was watching: not news"
    _own(session, server, 22)
    assert celebrations.record(session) == ["Collection 2"]
    assert celebrations.record(session) == [], "once"

    rows = {c.collection_id: c.celebrate for c in session.exec(select(CollectionCompletion)).all()}
    assert rows == {1: False, 2: True}


def test_each_person_sees_it_once_and_only_in_showcase(session: Session) -> None:
    server = _library(session)
    celebrations.record(session)
    _own(session, server, 22)
    celebrations.record(session)
    alice, bob = User(local_username="alice", is_admin=True), User(local_username="bob", is_admin=False)
    session.add(alice); session.add(bob); session.commit()

    assert celebrations.for_page(session, alice) == [], "Classic: nothing, and nothing used up"
    look.set_look(session, alice.id, look.SHOWCASE)
    assert [c.name for c in celebrations.for_page(session, alice)] == ["Collection 2"]
    assert celebrations.for_page(session, alice) == [], "seen"
    look.set_look(session, bob.id, look.SHOWCASE)
    assert celebrations.for_page(session, bob, 1) == [], "not that collection's"
    assert [c.name for c in celebrations.for_page(session, bob, 2)] == ["Collection 2"], "bob's own"


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            server = _library(session)
            celebrations.record(session)
            _own(session, server, 22)
            celebrations.record(session)
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def test_the_collection_page_throws_confetti_once_in_showcase(client: TestClient) -> None:
    assert "data-confetti" not in client.get(f"{BASE}/collections/2").text, "Classic"
    client.post(f"{BASE}/look", data={"look": "showcase"})

    page = client.get(f"{BASE}/collections/2").text
    assert "data-confetti" in page and "Collection complete!" in page and "Collection 2" in page
    assert "data-confetti" not in client.get(f"{BASE}/collections/2").text
    assert "data-confetti" not in client.get(f"{BASE}/").text, "already celebrated, home too"


def test_the_scan_status_has_a_reel_for_showcase(client: TestClient) -> None:
    from app.services import scan_state

    scan_state.begin("test")
    try:
        assert 'class="sc-reel"' in client.get(f"{BASE}/scan/status").text
    finally:
        scan_state.finish("done", [])
