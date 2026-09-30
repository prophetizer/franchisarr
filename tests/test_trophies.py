"""The Trophy case (0.52.0): what's finished, in what order, and the milestones."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import get_engine
from app.models import (
    CollectionCompletion,
    IncludedLibrary,
    ItemType,
    LibraryItem,
    MatchSource,
    TmdbCollection,
    TmdbCollectionMovie,
    TmdbMovie,
)
from app.services import trophies
from tests.conftest import ensure_server
from tests.test_movie_ui import BASE, client  # noqa: F401 - fixture

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _collection(session: Session, collection_id: int, name: str, films: list[int], owned: list[int]) -> None:
    session.add(TmdbCollection(tmdb_collection_id=collection_id, name=name))
    for position, tmdb_id in enumerate(films):
        session.add(TmdbCollectionMovie(collection_id=collection_id, tmdb_movie_id=tmdb_id, title=f"{name} {position + 1}",
                                        release_year=2000 + position, release_date=f"{2000 + position}-01-01",
                                        position=position))
    for tmdb_id in owned:
        session.add(TmdbMovie(tmdb_id=tmdb_id, title=str(tmdb_id), collection_id=collection_id))
        session.add(LibraryItem(server_id=ensure_server(session), library_key="1", item_key=str(tmdb_id),
                                item_type=ItemType.MOVIE.value, title=str(tmdb_id), tmdb_id=tmdb_id,
                                match_source=MatchSource.GUID.value))
    session.commit()


def _library(session: Session) -> None:
    from sqlmodel import select

    if session.exec(select(IncludedLibrary)).first() is None:
        session.add(IncludedLibrary(server_id=ensure_server(session), library_key="1", library_name="Movies",
                                    library_type="movie", enabled=True))
    _collection(session, 1, "Alien Collection", [10, 11], [10, 11])
    _collection(session, 2, "Back to the Future Collection", [20, 21, 22], [20, 21, 22])
    _collection(session, 3, "Cars Collection", [30, 31], [30, 31])
    _collection(session, 4, "Die Hard Collection", [40, 41], [40])            # not finished
    session.add(CollectionCompletion(collection_id=1, name="Alien Collection", celebrate=False))
    session.add(CollectionCompletion(collection_id=2, name="Back to the Future Collection",
                                     completed_at=NOW - timedelta(days=40)))
    session.add(CollectionCompletion(collection_id=3, name="Cars Collection", completed_at=NOW - timedelta(days=2)))
    session.commit()


def test_finished_collections_newest_first_and_the_old_ones_after_undated(session: Session) -> None:
    _library(session)

    found = trophies.case(session, now=NOW)

    assert [t.name for t in found.collections] == ["Cars Collection", "Back to the Future Collection", "Alien Collection"]
    cars, future, alien = found.collections
    assert cars.new and not future.new, "new for a month"
    assert alien.when is None, "complete before anyone was counting: no date to give"
    assert future.detail == "3 films" and cars.path == "/collections/3"


def test_milestones_earned_and_the_next_one_of_each_kind() -> None:
    case = trophies.Case(collections=[trophies.Trophy(str(n), "/", None, "") for n in range(12)])

    assert [b.label for b in case.earned] == ["10 complete collections", "First complete collection"]
    upcoming = {b.kind: (b.label, b.to_go) for b in case.next_up}
    assert upcoming == {"collections": ("25 complete collections", 13),
                        "franchises": ("First complete franchise", 1),
                        "directors": ("First complete filmography", 1)}


def test_the_page_is_for_everyone_and_in_the_menu(client: TestClient) -> None:  # noqa: F811
    with Session(get_engine()) as session:
        _library(session)

    page = client.get(f"{BASE}/trophies")

    assert page.status_code == 200
    assert "Cars Collection" in page.text and "Die Hard Collection" not in page.text
    assert "First complete collection" in page.text and "25 complete collections" not in page.text
    assert f'href="{BASE}/trophies"' in client.get(f"{BASE}/collections").text


def test_an_empty_case_says_how_to_fill_it(client: TestClient) -> None:  # noqa: F811
    page = client.get(f"{BASE}/trophies")

    assert "Nothing finished yet" in page.text
