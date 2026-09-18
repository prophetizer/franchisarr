"""TMDb client, with particular attention to explaining a bad API key.

Every user brings their own key (docs/DESIGN.md decision log), so "my key doesn't work" is the
support question this project will get most. Technical challenge #11 lists the failure modes;
they each get a test.
"""

from __future__ import annotations

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from app.clients.tmdb_client import (
    TMDB_BASE_URL,
    TmdbAuthError,
    TmdbClient,
    TmdbError,
    TmdbNotFound,
    looks_like_v4_token,
)

V3_KEY = "0123456789abcdef0123456789abcdef"
V4_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJmYWtlIn0.not-a-real-signature"


def _client(key: str = V3_KEY, **kwargs) -> TmdbClient:
    # A high rate limit keeps the tests fast; the limiter itself is tested separately.
    return TmdbClient(key, max_requests_per_second=10_000, **kwargs)


# ------------------------------------------------------------------ key validation


def test_a_v4_token_is_recognised_before_any_request_is_made() -> None:
    """The most common configuration mistake there is: TMDb's settings page shows both, and the
    v4 token is the more prominent one."""
    assert looks_like_v4_token(V4_TOKEN) is True
    assert looks_like_v4_token(V3_KEY) is False

    with responses.RequestsMock():  # a request here would fail the test
        with pytest.raises(TmdbAuthError) as exc_info:
            _client(V4_TOKEN).validate_key()

    assert "v4 Read Access Token" in str(exc_info.value)
    assert "v3 API Key" in str(exc_info.value)


def test_an_empty_key_is_reported_without_a_request() -> None:
    with responses.RequestsMock():
        with pytest.raises(TmdbAuthError):
            _client("").validate_key()


@responses.activate
def test_a_valid_key_validates() -> None:
    responses.add(responses.GET, f"{TMDB_BASE_URL}/configuration", json={"images": {}})

    _client().validate_key()  # does not raise


@responses.activate
def test_a_truncated_key_is_explained_as_such() -> None:
    responses.add(responses.GET, f"{TMDB_BASE_URL}/configuration", status=401)

    with pytest.raises(TmdbAuthError) as exc_info:
        _client("too-short").validate_key()

    assert "32 characters" in str(exc_info.value)


@responses.activate
def test_a_correctly_shaped_but_rejected_key_mentions_activation_delay() -> None:
    """A brand-new TMDb key takes a moment to start working, which looks identical to a wrong
    key unless you say so."""
    responses.add(responses.GET, f"{TMDB_BASE_URL}/configuration", status=401)

    with pytest.raises(TmdbAuthError) as exc_info:
        _client().validate_key()

    assert "activate" in str(exc_info.value)


@responses.activate
def test_an_error_never_contains_the_api_key() -> None:
    """The key travels in the query string, so transport errors can carry it."""
    responses.add(
        responses.GET,
        f"{TMDB_BASE_URL}/configuration",
        body=RequestsConnectionError(f"failed connecting with api_key={V3_KEY}"),
    )

    with pytest.raises(TmdbError) as exc_info:
        _client().validate_key()

    assert V3_KEY not in str(exc_info.value)


# ------------------------------------------------------------------ fetching


@responses.activate
def test_get_movie_extracts_the_collection() -> None:
    responses.add(
        responses.GET,
        f"{TMDB_BASE_URL}/movie/90",
        json={
            "id": 90,
            "title": "Beverly Hills Cop",
            "release_date": "1984-12-05",
            "belongs_to_collection": {"id": 85861, "name": "Beverly Hills Cop Collection"},
        },
    )

    movie = _client().get_movie(90)

    assert movie.collection_id == 85861
    assert movie.collection_name == "Beverly Hills Cop Collection"
    assert movie.year == 1984


@responses.activate
def test_a_standalone_film_has_no_collection() -> None:
    responses.add(
        responses.GET,
        f"{TMDB_BASE_URL}/movie/78",
        json={"id": 78, "title": "Blade Runner", "release_date": "1982-06-25",
              "belongs_to_collection": None},
    )

    assert _client().get_movie(78).collection_id is None


@responses.activate
def test_get_collection_returns_its_members_in_order() -> None:
    responses.add(
        responses.GET,
        f"{TMDB_BASE_URL}/collection/85861",
        json={
            "id": 85861,
            "name": "Beverly Hills Cop Collection",
            "parts": [
                {"id": 90, "title": "Beverly Hills Cop", "release_date": "1984-12-05"},
                {"id": 96, "title": "Beverly Hills Cop II", "release_date": "1987-05-18"},
                {"id": 306, "title": "Beverly Hills Cop III", "release_date": "1994-05-24"},
            ],
        },
    )

    collection = _client().get_collection(85861)

    assert [m.tmdb_id for m in collection.movies] == [90, 96, 306]
    assert collection.movies[0].year == 1984


@responses.activate
def test_a_missing_record_raises_not_found_rather_than_a_generic_error() -> None:
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/1", status=404)

    with pytest.raises(TmdbNotFound):
        _client().get_movie(1)


@responses.activate
def test_find_by_external_id() -> None:
    responses.add(
        responses.GET,
        f"{TMDB_BASE_URL}/find/tt0086960",
        json={"movie_results": [{"id": 90, "title": "Beverly Hills Cop", "release_date": "1984-12-05"}]},
    )

    found = _client().find_by_external_id("tt0086960", "imdb_id")

    assert found is not None
    assert found.tmdb_id == 90


@responses.activate
def test_find_returns_none_when_tmdb_knows_nothing() -> None:
    responses.add(responses.GET, f"{TMDB_BASE_URL}/find/tt9999999", json={"movie_results": []})

    assert _client().find_by_external_id("tt9999999", "imdb_id") is None


@responses.activate
def test_search_skips_malformed_results_rather_than_crashing() -> None:
    responses.add(
        responses.GET,
        f"{TMDB_BASE_URL}/search/movie",
        json={"results": [{"title": "No id here"}, {"id": 5, "title": "Fine"}]},
    )

    assert [m.tmdb_id for m in _client().search_movies("x")] == [5]


# ------------------------------------------------------------------ rate limiting


@responses.activate
def test_a_429_is_retried_and_then_succeeds() -> None:
    responses.add(
        responses.GET, f"{TMDB_BASE_URL}/movie/90", status=429, headers={"Retry-After": "0"}
    )
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/90", json={"id": 90, "title": "OK"})

    assert _client().get_movie(90).tmdb_id == 90


@responses.activate
def test_persistent_rate_limiting_eventually_gives_up_with_a_clear_message() -> None:
    for _ in range(5):
        responses.add(
            responses.GET, f"{TMDB_BASE_URL}/movie/90", status=429, headers={"Retry-After": "0"}
        )

    with pytest.raises(TmdbError) as exc_info:
        _client().get_movie(90)

    assert "rate-limiting" in str(exc_info.value)


def test_the_limiter_spaces_requests_out() -> None:
    import time

    from app.clients.tmdb_client import _RateLimiter

    limiter = _RateLimiter(max_per_second=50)
    started = time.monotonic()
    for _ in range(5):
        limiter.wait()

    # 5 requests at 50/s cannot complete in under ~80ms of spacing.
    assert time.monotonic() - started >= 0.06


@responses.activate
def test_get_show_carries_its_poster_and_external_ids() -> None:
    """One request, with external_ids appended: a show scan makes hundreds of these, and a
    second call per show would double TMDb's side of it for no gain."""
    responses.add(
        responses.GET,
        f"{TMDB_BASE_URL}/tv/4614",
        json={
            "id": 4614, "name": "NCIS", "first_air_date": "2003-09-23",
            "poster_path": "/ncis.jpg", "networks": [{"name": "CBS"}],
            "external_ids": {"imdb_id": "tt0364845", "tvdb_id": 72108, "facebook_id": None},
        },
    )

    show = _client().get_show(4614)

    assert show.poster_path == "/ncis.jpg"
    assert show.imdb_id == "tt0364845"
    assert show.tvdb_id == 72108
    assert "append_to_response=external_ids" in responses.calls[0].request.url


@responses.activate
def test_get_show_tolerates_missing_external_ids() -> None:
    """Obscure shows have none, and TMDb sends nulls rather than omitting keys."""
    responses.add(
        responses.GET,
        f"{TMDB_BASE_URL}/tv/9",
        json={"id": 9, "name": "Obscure", "external_ids": {"imdb_id": None, "tvdb_id": None}},
    )

    show = _client().get_show(9)

    assert show.imdb_id is None and show.tvdb_id is None and show.poster_path is None
