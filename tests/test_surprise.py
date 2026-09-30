"""Surprise me (0.53.0): which films it can land on, that it moves on a spin again, and the page."""

from __future__ import annotations

import random

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import get_engine
from app.models import IncludedLibrary, ItemType, LibraryItem, MatchSource, TmdbCollection, TmdbCollectionMovie, TmdbMovie
from app.services import surprise
from tests.conftest import ensure_server
from tests.test_movie_ui import BASE, client  # noqa: F401 - fixture

#: (tmdb_id, title, vote_average, vote_count); 100 is owned, the rest are missing.
FILMS = [
    (100, "Owned One", 8.0, 900),
    (101, "Great Sequel", 7.9, 4000),
    (102, "Fine Sequel", 6.5, 50),
    (103, "Poor Sequel", 5.1, 3000),
    (104, "Barely Rated Gem", 9.0, 12),
    (105, "Unrated", None, None),
]


def _seed(session: Session) -> None:
    if session.exec(select(IncludedLibrary)).first() is None:
        session.add(IncludedLibrary(server_id=ensure_server(session), library_key="1", library_name="Movies",
                                    library_type="movie", enabled=True))
    session.add(TmdbCollection(tmdb_collection_id=9, name="Test Collection"))
    for position, (tmdb_id, title, average, votes) in enumerate(FILMS):
        session.add(TmdbCollectionMovie(collection_id=9, tmdb_movie_id=tmdb_id, title=title, release_year=2000 + position,
                                        release_date=f"{2000 + position}-01-01", poster_path=f"/p{tmdb_id}.jpg",
                                        vote_average=average, vote_count=votes, position=position))
    session.add(TmdbMovie(tmdb_id=100, title="Owned One", collection_id=9))
    session.add(LibraryItem(server_id=ensure_server(session), library_key="1", item_key="100",
                            item_type=ItemType.MOVIE.value, title="Owned One", tmdb_id=100,
                            match_source=MatchSource.GUID.value))
    session.commit()


def test_only_well_rated_missing_films_by_enough_people(session: Session) -> None:
    _seed(session)

    found = {p.title: p for p in surprise.build_pool(session, None)}

    assert set(found) == {"Great Sequel", "Fine Sequel"}, "owned, poorly rated, barely rated and unrated are out"
    assert found["Great Sequel"].path == "/collections/9" and found["Great Sequel"].source == "Test Collection"


def test_spin_again_always_moves_when_there_is_a_choice(session: Session) -> None:
    _seed(session)
    surprise.forget()
    rng = random.Random(1)

    first, reel = surprise.spin(session, 1, rng=rng)
    again = [surprise.spin(session, 1, avoid=first.tmdb_id, rng=rng)[0].tmdb_id for _ in range(10)]

    assert first.tmdb_id not in again
    assert reel and all(src.endswith(".jpg") for src in reel)
    assert first.small_poster not in reel, "the reel rolls past the others and lands on the pick"


def test_the_pool_is_kept_a_while_and_dropped_on_an_add(session: Session) -> None:
    _seed(session)
    surprise.forget()
    assert len(surprise.pool(session, 1, now=0.0)) == 2
    session.add(LibraryItem(server_id=ensure_server(session), library_key="1", item_key="101",
                            item_type=ItemType.MOVIE.value, title="Great Sequel", tmdb_id=101,
                            match_source=MatchSource.GUID.value))
    session.commit()

    assert len(surprise.pool(session, 1, now=10.0)) == 2, "kept"
    assert len(surprise.pool(session, 1, now=surprise.POOL_FOR + 1)) == 1, "worked out again once it's old"
    surprise.forget(1)
    assert 1 not in surprise._pools


def test_the_home_page_offers_it_and_the_card_comes_back(client: TestClient) -> None:  # noqa: F811
    with Session(get_engine()) as session:
        _seed(session)
    surprise.forget()

    home = client.get(f"{BASE}/").text
    assert "🎲 Surprise me" in home and 'hx-trigger="click, load"' not in home
    assert 'hx-trigger="click, load"' in client.get(f"{BASE}/?surprise=1").text, "Ctrl+K's link spins on arrival"

    card = client.get(f"{BASE}/surprise").text
    assert ("Great Sequel" in card) != ("Fine Sequel" in card), "one pick"
    assert "data-reel='[" in card and f'hx-get="{BASE}/add/' in card


def test_nothing_to_pick_says_so(client: TestClient) -> None:  # noqa: F811
    surprise.forget()

    card = client.get(f"{BASE}/surprise").text

    assert "Nothing to pick from yet" in card and "6.5" in card
