"""Trailers (0.54.0): which video TMDb's list gives, that nothing odd reaches the page, and where
the button is."""

from __future__ import annotations

import responses
from fastapi.testclient import TestClient

from app.clients.tmdb_client import TMDB_BASE_URL, TmdbClient, TmdbError
from app.services import about_service
from tests.test_movie_ui import BASE, COLLECTION, _seed_collection, client  # noqa: F401 - fixture


def _client() -> TmdbClient:
    return TmdbClient("0123456789abcdef0123456789abcdef", max_requests_per_second=10_000)


def _video(key: str, kind: str = "Trailer", official: bool = True, lang: str | None = "en", site: str = "YouTube") -> dict:
    return {"key": key, "type": kind, "official": official, "iso_639_1": lang, "site": site}


@responses.activate
def test_an_official_trailer_beats_teasers_clips_and_fan_uploads() -> None:
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/603/videos", json={"results": [
        _video("clipclipcli", "Clip"),
        _video("teaserteas1", "Teaser"),
        _video("fanfanfanfa", official=False),
        _video("vimeovimeo1", site="Vimeo"),
        _video("officialtr1"),
    ]})

    assert _client().get_trailer(603) == "officialtr1"


@responses.activate
def test_a_teaser_will_do_and_a_clip_will_not() -> None:
    responses.add(responses.GET, f"{TMDB_BASE_URL}/tv/1399/videos", json={"results": [_video("teaserteas1", "Teaser")]})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/2/videos", json={"results": [_video("clipclipcli", "Clip")]})

    assert _client().get_trailer(1399, "tv") == "teaserteas1"
    assert _client().get_trailer(2) is None


@responses.activate
def test_a_key_that_isnt_a_youtube_id_never_leaves_the_client() -> None:
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/3/videos",
                  json={"results": [_video('abc"><script')]})

    assert _client().get_trailer(3) is None


def test_the_answer_is_remembered_even_when_it_is_none() -> None:
    calls = []

    class Tmdb:
        def get_trailer(self, tmdb_id: int, kind: str) -> str | None:
            calls.append((tmdb_id, kind))
            return None

    about_service._trailers.clear()
    assert about_service.trailer("show", 7, Tmdb()) is None
    assert about_service.trailer("show", 7, Tmdb()) is None
    assert calls == [(7, "tv")]


def test_a_failing_tmdb_is_asked_again_later() -> None:
    class Broken:
        def get_trailer(self, tmdb_id: int, kind: str) -> str | None:
            raise TmdbError("down")

    about_service._trailers.clear()
    assert about_service.trailer("movie", 8, Broken()) is None
    assert ("movie", 8) not in about_service._trailers


def test_the_player_is_youtubes_privacy_mode_with_a_referrer(client: TestClient) -> None:  # noqa: F811
    about_service._trailers.clear()
    about_service._trailers[("movie", 96)] = "officialtr1"

    page = client.get(f"{BASE}/trailer/movie/96", params={"title": "Cop <II>"}).text

    assert 'src="https://www.youtube-nocookie.com/embed/officialtr1?autoplay=1' in page
    assert 'referrerpolicy="strict-origin-when-cross-origin"' in page
    assert "Cop &lt;II&gt;" in page and "Cop <II>" not in page
    assert client.get(f"{BASE}/trailer/person/96").status_code == 404


def test_no_trailer_says_so(client: TestClient) -> None:  # noqa: F811
    about_service._trailers.clear()
    about_service._trailers[("movie", 5)] = None

    page = client.get(f"{BASE}/trailer/movie/5").text

    assert "doesn't list a trailer" in page.replace("&#39;", "'") and "<iframe" not in page


def test_missing_films_have_a_play_button_and_every_page_a_place_to_play(client: TestClient) -> None:  # noqa: F811
    _seed_collection()

    page = client.get(f"{BASE}/collections/{COLLECTION}").text

    assert f'hx-get="{BASE}/trailer/movie/96?title=Beverly%20Hills%20Cop%20II"' in page
    assert f'hx-get="{BASE}/trailer/movie/90' not in page, "owned films don't get one"
    assert '<div id="trailer"></div>' in page


def test_the_spotlight_plays_the_film_that_would_finish_the_set() -> None:
    from types import SimpleNamespace as Film

    from app.services import home_service

    gap = Film(name="Cop Collection", collection_id=1, backdrop="/b.jpg", logo_image=None, poster=None,
               owned=[Film(vote_count=10)], missing=[Film(tmdb_id=306, title="III", release_date="1994-05-24"),
                                                     Film(tmdb_id=96, title="II", release_date="1987-05-18")])

    slide = home_service.spotlight([gap])[0]

    assert (slide.next_id, slide.next_title) == (96, "II")
