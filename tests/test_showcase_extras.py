"""Showcase 0.51.0: flipped posters, previews, the October check and quick search -- the server's
side of each. The motion itself lives in showcase.js and is checked in a browser."""

from __future__ import annotations

from datetime import timedelta

import responses
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.clients.tmdb_client import (
    TMDB_BASE_URL,
    TmdbClient,
    TmdbCollectionDetails,
    TmdbError,
    TmdbMovieSummary,
)
from app.db import get_engine
from app.models import TmdbCollectionMovie
from app.services import about_service
from app.services.scan_service import ScanSummary, _cache_collection
from tests.test_movie_ui import BASE, COLLECTION, _seed_collection, client  # noqa: F401 - fixture


def _client() -> TmdbClient:
    return TmdbClient("0123456789abcdef0123456789abcdef", max_requests_per_second=10_000)


# ------------------------------------------------------------------ what TMDb sends


@responses.activate
def test_a_collections_films_keep_their_plot_and_genres() -> None:
    responses.add(responses.GET, f"{TMDB_BASE_URL}/collection/1", json={"id": 1, "name": "Scream", "parts": [
        {"id": 4232, "title": "Scream", "release_date": "1996-12-20", "overview": " A killer calls. ",
         "genre_ids": [27, 9648, "junk"]},
        {"id": 4233, "title": "Scream 2", "overview": "", "genre_ids": None},
    ]})

    first, second = _client().get_collection(1).movies

    assert first.overview == "A killer calls." and first.genre_ids == (27, 9648)
    assert second.overview is None and second.genre_ids == ()


@responses.activate
def test_a_film_looked_up_brings_its_plot_genres_and_score() -> None:
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/603", json={
        "id": 603, "title": "The Matrix", "overview": "Wake up.", "runtime": 136, "vote_average": 8.2,
        "genres": [{"id": 28, "name": "Action"}, {"id": 878, "name": "Science Fiction"}]})

    film = _client().get_movie(603)

    assert (film.overview, film.genres, film.vote_average) == ("Wake up.", ("Action", "Science Fiction"), 8.2)


def test_the_scan_stores_them(session: Session) -> None:
    class Tmdb:
        def get_collection(self, collection_id: int) -> TmdbCollectionDetails:
            return TmdbCollectionDetails(collection_id, "Scream Collection", movies=(
                TmdbMovieSummary(4232, "Scream", "1996-12-20", overview="A killer calls.", genre_ids=(27, 9648)),))

    _cache_collection(session, Tmdb(), 2602, timedelta(days=7), ScanSummary())

    row = session.get(TmdbCollectionMovie, 1)
    assert (row.overview, row.genre_ids) == ("A killer calls.", "27,9648")


# ------------------------------------------------------------------ the back of a poster


def _film(session: Session, tmdb_id: int, collection_id: int = 7, *, overview: str | None = None,
          genres: str | None = None, rating: float | None = None) -> None:
    from app.models import TmdbCollection

    if session.get(TmdbCollection, collection_id) is None:
        session.add(TmdbCollection(tmdb_collection_id=collection_id, name=f"Set {collection_id}"))
    session.add(TmdbCollectionMovie(collection_id=collection_id, tmdb_movie_id=tmdb_id, title=str(tmdb_id),
                                    overview=overview, genre_ids=genres, vote_average=rating))
    session.commit()


def test_a_collection_film_is_answered_from_the_scan_without_asking_tmdb(session: Session) -> None:
    _film(session, 11, overview="Long ago.", genres="12,28,99999", rating=8.2)

    found = about_service.about(session, "movie", 11, tmdb=None)

    assert found == about_service.About("Long ago.", ("Adventure", "Action"), 8.2)


def test_anything_else_is_asked_of_tmdb_once(session: Session) -> None:
    calls = []

    class Tmdb:
        def get_show(self, tmdb_id: int):
            calls.append(tmdb_id)
            from app.clients.tmdb_client import TmdbShowSummary
            return TmdbShowSummary(tmdb_id, "Angel", overview="Vampire detective.", genres=("Drama",))

    about_service._remembered.clear()
    first = about_service.about(session, "show", 2426, Tmdb())
    again = about_service.about(session, "show", 2426, Tmdb())

    assert first == again and first.overview == "Vampire detective." and calls == [2426]


def test_no_key_or_a_failing_tmdb_is_nothing_to_say(session: Session) -> None:
    class Broken:
        def get_movie(self, tmdb_id: int):
            raise TmdbError("down")

    about_service._remembered.clear()
    assert about_service.about(session, "movie", 5, tmdb=None) is None
    assert about_service.about(session, "movie", 5, Broken()) is None


def test_the_about_route_shows_the_plot_escaped(client: TestClient) -> None:  # noqa: F811
    _seed_collection()
    with Session(get_engine()) as session:
        row = session.exec(select(TmdbCollectionMovie)
                           .where(TmdbCollectionMovie.tmdb_movie_id == 96)).one()
        row.overview, row.genre_ids = "Axel <b>returns</b>.", "28,35"
        session.add(row)
        session.commit()

    page = client.get(f"{BASE}/about/movie/96")

    assert page.status_code == 200
    assert "Axel &lt;b&gt;returns&lt;/b&gt;." in page.text and "Action, Comedy" in page.text
    assert client.get(f"{BASE}/about/person/96").status_code == 404


def test_missing_films_say_what_they_are_and_owned_ones_do_not(client: TestClient) -> None:  # noqa: F811
    _seed_collection()

    page = client.get(f"{BASE}/collections/{COLLECTION}").text

    assert 'data-about="movie/96"' in page and 'data-about="movie/306"' in page
    assert 'data-about="movie/90"' not in page, "only missing films turn over"


# ------------------------------------------------------------------ previews and October


def test_a_collection_card_carries_its_preview_inert(client: TestClient) -> None:  # noqa: F811
    _seed_collection()

    page = client.get(f"{BASE}/collections").text

    start = page.index('<template class="sc-peek">')
    preview = page[start:page.index("</template>", start)]
    assert "Missing 2" in preview


def test_a_horror_page_is_marked_only_when_most_of_it_is_horror(session: Session) -> None:
    _film(session, 1, 30, genres="27,53")
    _film(session, 2, 30, genres="27")
    _film(session, 3, 30, genres="35")
    _film(session, 4, 31, genres="27")
    _film(session, 5, 31, genres="35")
    _film(session, 6, 32)

    assert about_service.is_horror(session, collection_id=30)
    assert not about_service.is_horror(session, collection_id=31), "half isn't most"
    assert not about_service.is_horror(session, collection_id=32), "unknown genres aren't horror"
    assert about_service.is_horror(session, film_ids=[1, 2, 5])
    assert not about_service.is_horror(session)


def test_the_collection_page_carries_the_mark(client: TestClient) -> None:  # noqa: F811
    _seed_collection()
    marker = "<span data-sc-horror hidden></span>"
    assert marker not in client.get(f"{BASE}/collections/{COLLECTION}").text
    with Session(get_engine()) as session:
        for row in session.exec(select(TmdbCollectionMovie)).all():
            row.genre_ids = "27"
            session.add(row)
        session.commit()
    assert marker in client.get(f"{BASE}/collections/{COLLECTION}").text


# ------------------------------------------------------------------ quick search


def test_quick_search_answers_with_one_line_per_match(client: TestClient) -> None:  # noqa: F811
    _seed_collection()

    page = client.get(f"{BASE}/search", params={"q": "beverly"},
                      headers={"HX-Request": "true", "HX-Target": "quick-results"})

    assert page.status_code == 200
    assert '<ul class="sc-quick-list"' in page.text and "<html" not in page.text
    assert f'href="{BASE}/collections/{COLLECTION}"' in page.text
    assert "Beverly Hills Cop III" in page.text and "Film · 1994 · missing" in page.text
    short = client.get(f"{BASE}/search", params={"q": "b"}, headers={"HX-Request": "true", "HX-Target": "quick-results"})
    assert "Keep typing" in short.text


# ------------------------------------------------------------------ 0.56.0


def test_the_poster_wall_draws_owned_posters_and_keeps_them_all_day(session: Session) -> None:
    from datetime import date

    from app.models import IncludedLibrary, ItemType, LibraryItem, MatchSource, TmdbMovie
    from app.services import home_service
    from tests.conftest import ensure_server

    session.add(IncludedLibrary(server_id=ensure_server(session), library_key="1", library_name="Movies",
                                library_type="movie", enabled=True))
    for n in range(1, 41):
        _film(session, n, overview=None)
        row = session.exec(select(TmdbCollectionMovie).where(TmdbCollectionMovie.tmdb_movie_id == n)).one()
        row.poster_path = f"/p{n}.jpg"
        session.add(row)
        if n <= 30:   # ten of them not owned
            session.add(TmdbMovie(tmdb_id=n, title=str(n), collection_id=7))
            session.add(LibraryItem(server_id=ensure_server(session), library_key="1", item_key=str(n),
                                    item_type=ItemType.MOVIE.value, title=str(n), tmdb_id=n,
                                    match_source=MatchSource.GUID.value))
    session.commit()

    home_service._walls.clear()
    today = home_service.poster_wall(session, date(2026, 10, 1), limit=12)
    again = home_service.poster_wall(session, date(2026, 10, 1), limit=12)
    tomorrow = home_service.poster_wall(session, date(2026, 10, 2), limit=12)

    assert len(today) == 12 and today == again and today != tomorrow
    assert all("/w92/p" in url and int(url.rsplit("/p", 1)[1].split(".")[0]) <= 30 for url in today), "owned only"


def test_a_complete_collection_page_says_so(client: TestClient) -> None:  # noqa: F811
    _seed_collection()
    assert "data-complete" not in client.get(f"{BASE}/collections/{COLLECTION}").text
    from app.models import ItemType, LibraryItem, MatchSource
    from tests.conftest import ensure_server
    with Session(get_engine()) as session:
        for tmdb_id in (96, 306):
            session.add(LibraryItem(server_id=ensure_server(session), library_key="1", item_key=str(tmdb_id),
                                    item_type=ItemType.MOVIE.value, title=str(tmdb_id), tmdb_id=tmdb_id,
                                    match_source=MatchSource.GUID.value))
        session.commit()
    assert "data-complete" in client.get(f"{BASE}/collections/{COLLECTION}").text


def test_still_layers_are_parked_off_screen_for_reduce_motion() -> None:
    """With "reduce motion" no animation runs, so the sweep and glint layers sit at their base
    position -- which must be off to the side, not a stripe across the title or a poster."""
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "showcase.css").read_text()
    sweep = re.search(r"\.collection-heading hgroup::after \{(.*?)\n\}", css, re.S).group(1)
    glint = re.search(r":is\(\.collection-poster, \.poster-row-card\)::before \{(.*?)\n\}", css, re.S).group(1)
    assert "translate: -120% 0;" in sweep and "translate: -130% 0;" in glint


def test_only_showcase_pays_for_the_poster_wall(client: TestClient) -> None:  # noqa: F811
    from app.services import home_service

    _seed_collection()
    home_service._walls.clear()
    assert 'class="poster-wall"' not in client.get(f"{BASE}/").text and not home_service._walls, "Classic: not drawn"
    client.post(f"{BASE}/look", data={"look": "showcase"})
    client.get(f"{BASE}/")
    assert home_service._walls, "Showcase: drawn (and kept)"


def test_a_collection_card_carries_its_fan_of_films(client: TestClient) -> None:  # noqa: F811
    _seed_collection()
    from app.models import TmdbCollection

    with Session(get_engine()) as session:
        session.get(TmdbCollection, COLLECTION).poster_path = "/c.jpg"
        for row in session.exec(select(TmdbCollectionMovie)).all():
            row.poster_path = f"/p{row.tmdb_movie_id}.jpg"
            session.add(row)
        session.commit()

    page = client.get(f"{BASE}/collections").text

    fan = page[page.index('<template class="sc-fan">'):]
    fan = fan[:fan.index("</template>")]
    assert fan.count("<img") == 3 and "/p90.jpg" in fan, "owned first"


def test_transform_is_only_used_where_it_must_be() -> None:
    """Animations use translate/rotate/scale so nothing holds a transform over the tilt
    (CLAUDE.md). The crawl is the exception: its text must move along its own tilted plane,
    and its overlay is removed when it ends."""
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "showcase.css").read_text()
    frames = re.findall(r"@keyframes ([\w-]+) \{(.*?)\n\}", css, re.S) + re.findall(r"@keyframes ([\w-]+) \{([^\n]*)\}", css)
    holding = {name for name, body in frames if "transform:" in body}
    assert holding == {"sc-crawl"}
