"""Director completion: a director's filmography against the library."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
import responses
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.clients.tmdb_client import TMDB_BASE_URL, TmdbClient
from app.db import get_engine
from app.models import (
    DirectorFilm, IncludedLibrary, ItemType, LibraryItem, MatchSource, MovieDirector, TmdbMovie,
)
from app.services import director_service
from app.services.settings_service import SettingKey, set_setting
from tests.conftest import ensure_server

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"
NOLAN = 525
TODAY = date(2026, 9, 17)


def _own(session: Session, tmdb_id: int, title: str, director: int | None = NOLAN, name: str = "Christopher Nolan") -> None:
    session.add(TmdbMovie(tmdb_id=tmdb_id, title=title, release_year=2005))
    session.add(LibraryItem(server_id=ensure_server(session), library_key="1", item_key=f"f{tmdb_id}", item_type="movie",
                            title=title, year=2005, tmdb_id=tmdb_id, match_source="guid"))
    if director is not None:
        session.add(MovieDirector(tmdb_movie_id=tmdb_id, person_id=director, name=name))
    session.commit()


def _film(session: Session, tmdb_id: int, title: str, released: str | None, *, votes: int = 500,
          average: float = 7.0, documentary: bool = False, person: int = NOLAN) -> None:
    session.add(DirectorFilm(person_id=person, tmdb_movie_id=tmdb_id, title=title,
                             release_date=released, vote_count=votes, vote_average=average,
                             is_documentary=documentary))
    session.commit()


def _floor(session: Session, n: int) -> None:
    set_setting(session, SettingKey.MIN_DIRECTOR_FILMS, str(n)); session.commit()


# ------------------------------------------------------------------ views


def test_a_director_page_splits_the_filmography(session: Session) -> None:
    _floor(session, 2)
    _own(session, 155, "The Dark Knight"); _own(session, 27205, "Inception")
    _film(session, 155, "The Dark Knight", "2008-07-16")
    _film(session, 27205, "Inception", "2010-07-15")
    _film(session, 320, "Insomnia", "2002-05-24")
    _film(session, 11660, "Following", "1998-09-12")
    _film(session, 900, "Untitled Nolan", "2028-01-01")
    _film(session, 901, "Quay", "2015-08-19", documentary=True)

    view = director_service.director_views(session, today=TODAY)[0]

    assert view.name == "Christopher Nolan"
    assert [t.title for t in view.owned] == ["The Dark Knight", "Inception"]
    assert [t.title for t in view.missing] == ["Following", "Insomnia"]
    assert [t.title for t in view.upcoming] == ["Untitled Nolan"]
    assert [t.title for t in view.documentaries] == ["Quay"]
    assert view.total == 5, "an unreleased film is not yet a film they directed"


def test_the_floor_hides_directors_you_own_few_films_by(session: Session) -> None:
    _floor(session, 3)
    _own(session, 155, "The Dark Knight"); _own(session, 27205, "Inception")
    _film(session, 320, "Insomnia", "2002-05-24")

    assert director_service.director_views(session, today=TODAY) == []


def test_the_rating_filter_applies_here_too(session: Session) -> None:
    _floor(session, 2)
    _own(session, 1, "A"); _own(session, 2, "B")
    _film(session, 3, "Good", "2000-01-01", average=7.5)
    _film(session, 4, "Bad", "2000-01-01", average=4.0)
    _film(session, 5, "Obscure", "2000-01-01", average=2.0, votes=3)
    set_setting(session, SettingKey.MIN_GAP_RATING, "6"); session.commit()

    view = director_service.director_views(session, today=TODAY)[0]

    assert [t.title for t in view.missing] == ["Good", "Obscure"], "few votes is unknown, not bad"
    assert [t.title for t in view.hidden] == ["Bad"]


def test_a_director_whose_filmography_is_not_fetched_yet_is_marked_pending(session: Session) -> None:
    _floor(session, 2)
    _own(session, 1, "A"); _own(session, 2, "B")

    view = director_service.director_views(session, today=TODAY)[0]

    assert view.pending and view.missing == []


def test_a_film_already_in_radarr_is_not_missing(session: Session, monkeypatch) -> None:
    _floor(session, 2)
    _own(session, 1, "A"); _own(session, 2, "B")
    _film(session, 3, "Tracked", "2000-01-01")
    monkeypatch.setattr(director_service.movie_gap_service, "radarr_known_ids",
                        lambda session, instance_id=None: {3})

    assert director_service.director_views(session, today=TODAY)[0].missing == []


def test_sort_by_best_missing_film(session: Session) -> None:
    _floor(session, 2)
    _own(session, 1, "A"); _own(session, 2, "B")
    _own(session, 3, "C", director=99, name="Other"); _own(session, 4, "D", director=99, name="Other")
    _film(session, 10, "Meh", "2000-01-01", average=5.0)
    _film(session, 11, "Great", "2000-01-01", average=8.5, person=99)

    by_rating = [v.name for v in director_service.director_views(session, today=TODAY, sort="rating")]
    by_name = [v.name for v in director_service.director_views(session, today=TODAY, sort="name")]

    assert by_rating == ["Other", "Christopher Nolan"]
    assert by_name == ["Christopher Nolan", "Other"]


# ------------------------------------------------------------------ discovery


@responses.activate
def test_discovery_credits_films_once_and_fetches_qualifying_filmographies(session: Session) -> None:
    _floor(session, 2)
    _own(session, 155, "The Dark Knight", director=None); _own(session, 27205, "Inception", director=None)
    for tid in (155, 27205):
        responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/{tid}/credits", json={"crew": [
            {"id": NOLAN, "name": "Christopher Nolan", "job": "Director"},
            {"id": 1, "name": "Someone", "job": "Producer"}]})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/person/{NOLAN}/movie_credits", json={"crew": [
        {"id": 155, "title": "The Dark Knight", "job": "Director", "release_date": "2008-07-16"},
        {"id": 320, "title": "Insomnia", "job": "Director", "release_date": "2002-05-24",
         "vote_average": 6.9, "vote_count": 5528, "genre_ids": [80, 53]},
        {"id": 320, "title": "Insomnia", "job": "Director"},   # listed twice: director and co-director
        {"id": 901, "title": "Quay", "job": "Director", "genre_ids": [99]},
        {"id": 155, "title": "The Dark Knight", "job": "Writer"}]})

    tmdb = TmdbClient("k" * 32, max_requests_per_second=10_000)
    credited, refreshed = director_service.discover(session, tmdb, ttl=timedelta(days=7))
    assert (credited, refreshed) == (2, 1)

    # Second scan: credits are not re-fetched, and the filmography is inside its TTL.
    credited, refreshed = director_service.discover(session, tmdb, ttl=timedelta(days=7))
    assert (credited, refreshed) == (0, 0)
    assert len([c for c in responses.calls if "/credits" in c.request.url]) == 2

    films = session.exec(select(DirectorFilm)).all()
    assert {(f.tmdb_movie_id, f.is_documentary) for f in films} == {(155, False), (320, False), (901, True)}
    assert len(films) == 3, "a film credited twice is one row"


@responses.activate
def test_a_film_with_no_director_credit_is_not_asked_about_again(session: Session) -> None:
    _own(session, 7, "Anonymous", director=None)
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/7/credits", json={"crew": []})
    tmdb = TmdbClient("k" * 32, max_requests_per_second=10_000)

    director_service.discover(session, tmdb, ttl=timedelta(days=7))
    director_service.discover(session, tmdb, ttl=timedelta(days=7))

    assert len(responses.calls) == 1
    assert director_service.director_views(session) == []


# ------------------------------------------------------------------ pages


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            session.add(IncludedLibrary(server_id=ensure_server(session), library_key="1", library_name="Movies",
                                        library_type="movie", enabled=True))
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def test_the_pages_render_and_route_adds_to_radarr(client: TestClient) -> None:
    with Session(get_engine()) as session:
        _floor(session, 2)
        _own(session, 155, "The Dark Knight"); _own(session, 27205, "Inception")
        _film(session, 155, "The Dark Knight", "2008-07-16")
        _film(session, 320, "Insomnia", "2002-05-24", average=6.9, votes=5528)

    index = client.get(f"{BASE}/directors").text
    assert "Christopher Nolan" in index and "2 owned" in index and "1 missing" in index
    assert "★ 6.9" in index

    detail = client.get(f"{BASE}/directors/{NOLAN}").text
    assert "You have 2 of 3" in detail
    assert f'hx-get="{BASE}/add/320"' in detail
    assert client.get(f"{BASE}/directors/1").status_code == 404

    assert client.post(f"{BASE}/directors/floor", data={"floor": "3"}).status_code == 303
    assert "Christopher Nolan" not in client.get(f"{BASE}/directors").text


def test_shorts_fold_away_unless_the_preference_says_otherwise(session: Session) -> None:
    """Doodlebug is three minutes long and rated 6.5. It is Nolan's; it is not what someone
    completing Nolan is after -- until they say it is. An unknown runtime is never a short."""
    _floor(session, 2)
    _own(session, 1, "A"); _own(session, 2, "B")
    session.add(DirectorFilm(person_id=NOLAN, tmdb_movie_id=3, title="Doodlebug", release_date="1997-01-01",
                             vote_count=500, vote_average=6.5, runtime=3))
    session.add(DirectorFilm(person_id=NOLAN, tmdb_movie_id=4, title="Insomnia", release_date="2002-05-24",
                             vote_count=500, vote_average=7.0, runtime=118))
    session.add(DirectorFilm(person_id=NOLAN, tmdb_movie_id=5, title="Unknown length", release_date="2000-01-01",
                             vote_count=500, vote_average=7.0, runtime=None))
    session.commit()

    view = director_service.director_views(session, today=TODAY)[0]
    assert [t.title for t in view.missing] == ["Unknown length", "Insomnia"]
    assert [t.title for t in view.shorts] == ["Doodlebug"]

    set_setting(session, SettingKey.DIRECTOR_INCLUDE_SHORTS, "true"); session.commit()
    view = director_service.director_views(session, today=TODAY)[0]
    assert "Doodlebug" in [t.title for t in view.missing] and view.shorts == []


@responses.activate
def test_discovery_learns_runtimes_for_unowned_films_once(session: Session) -> None:
    _floor(session, 2)
    _own(session, 1, "A", director=None); _own(session, 2, "B", director=None)
    for tid in (1, 2):
        responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/{tid}/credits",
                      json={"crew": [{"id": NOLAN, "name": "Christopher Nolan", "job": "Director"}]})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/person/{NOLAN}/movie_credits", json={"crew": [
        {"id": 1, "title": "A", "job": "Director", "release_date": "2000-01-01"},
        {"id": 3, "title": "Doodlebug", "job": "Director", "release_date": "1997-01-01"}]})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/3", json={"id": 3, "title": "Doodlebug", "runtime": 3})
    tmdb = TmdbClient("k" * 32, max_requests_per_second=10_000)

    director_service.discover(session, tmdb, ttl=timedelta(days=7))
    director_service.discover(session, tmdb, ttl=timedelta(days=7))

    row = session.exec(select(DirectorFilm).where(DirectorFilm.tmdb_movie_id == 3)).one()
    assert row.runtime == 3
    assert len([c for c in responses.calls if c.request.url.endswith("/movie/3?api_key=" + "k" * 32)]) == 1, "once"
    owned_row = session.exec(select(DirectorFilm).where(DirectorFilm.tmdb_movie_id == 1)).one()
    assert owned_row.runtime is None, "owned films are never candidates to hide, so no lookup"
