"""fanart.tv client.

Artwork is optional, and that is the property most worth protecting: every failure mode here has
to degrade to "no logo", never to a broken scan. The shapes asserted below were taken from real
responses rather than the documentation.
"""

from __future__ import annotations

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from app.clients.fanart_client import (
    FANART_BASE_URL,
    FanartAuthError,
    FanartClient,
    FanartError,
    MovieArt,
    _best,
)

KEY = "0123456789abcdef0123456789abcdef"


def _client(key: str = KEY, **kwargs) -> FanartClient:
    return FanartClient(key, max_requests_per_second=10_000, **kwargs)


def _art(**lists) -> dict:
    return {"name": "Terminator 2", "tmdb_id": "280", **lists}


@responses.activate
def test_returns_the_logo_and_background() -> None:
    responses.add(
        responses.GET,
        f"{FANART_BASE_URL}/movies/280",
        json=_art(
            hdmovielogo=[{"id": "1", "lang": "en", "likes": "17", "url": "https://f/logo.png"}],
            moviebackground=[{"id": "2", "lang": "", "likes": "10", "url": "https://f/bg.jpg"}],
        ),
    )

    art = _client().get_movie_art(280)

    assert art.logo_url == "https://f/logo.png"
    assert art.background_url == "https://f/bg.jpg"
    assert art


@responses.activate
def test_hd_logos_are_preferred_over_the_legacy_ones() -> None:
    """Both lists hold the same artwork; only the HD one is big enough for a heading."""
    responses.add(
        responses.GET,
        f"{FANART_BASE_URL}/movies/280",
        json=_art(
            movielogo=[{"lang": "en", "likes": "500", "url": "https://f/small.png"}],
            hdmovielogo=[{"lang": "en", "likes": "1", "url": "https://f/hd.png"}],
        ),
    )

    assert _client().get_movie_art(280).logo_url == "https://f/hd.png"


@responses.activate
def test_a_film_with_no_artwork_is_not_an_error() -> None:
    """fanart is community-contributed, so this is the normal case for anything obscure."""
    responses.add(responses.GET, f"{FANART_BASE_URL}/movies/999", json=_art())

    art = _client().get_movie_art(999)

    assert art == MovieArt()
    assert not art


@responses.activate
def test_an_unknown_film_returns_nothing_rather_than_raising() -> None:
    responses.add(responses.GET, f"{FANART_BASE_URL}/movies/999", status=404, json={})

    assert _client().get_movie_art(999) == MovieArt()


@responses.activate
def test_a_rejected_key_is_reported_as_an_auth_failure() -> None:
    responses.add(
        responses.GET,
        f"{FANART_BASE_URL}/movies/280",
        status=401,
        json={"error": "missing api_key or client_key parameter"},
    )

    with pytest.raises(FanartAuthError):
        _client().get_movie_art(280)


@responses.activate
def test_a_short_key_gets_a_message_saying_so() -> None:
    responses.add(responses.GET, f"{FANART_BASE_URL}/movies/280", status=401, json={})

    with pytest.raises(FanartAuthError) as exc:
        _client("too-short").get_movie_art(280)

    assert "32 characters" in str(exc.value)


@responses.activate
def test_the_api_key_never_appears_in_a_connection_error() -> None:
    """The key rides in the query string, so any message quoting the URL would leak it."""
    responses.add(
        responses.GET, f"{FANART_BASE_URL}/movies/280", body=RequestsConnectionError("boom")
    )

    with pytest.raises(FanartError) as exc:
        _client().get_movie_art(280)

    assert KEY not in str(exc.value)


@responses.activate
def test_a_non_json_response_is_an_error_not_a_crash() -> None:
    responses.add(responses.GET, f"{FANART_BASE_URL}/movies/280", body="<html>nope</html>")

    with pytest.raises(FanartError):
        _client().get_movie_art(280)


@responses.activate
def test_a_json_list_instead_of_an_object_is_rejected() -> None:
    responses.add(responses.GET, f"{FANART_BASE_URL}/movies/280", json=[])

    with pytest.raises(FanartError):
        _client().get_movie_art(280)


@responses.activate
def test_validate_key_accepts_a_working_key() -> None:
    responses.add(responses.GET, f"{FANART_BASE_URL}/movies/550", json=_art())

    _client().validate_key()  # does not raise


@responses.activate
def test_validate_key_rejects_a_bad_one() -> None:
    responses.add(responses.GET, f"{FANART_BASE_URL}/movies/550", status=401, json={})

    with pytest.raises(FanartAuthError):
        _client().validate_key()


def test_validate_key_refuses_an_empty_key_without_asking_fanart() -> None:
    with pytest.raises(FanartAuthError):
        _client("").validate_key()


# ------------------------------------------------------------------ picking one image


def test_english_wins_over_a_more_popular_foreign_logo() -> None:
    """A logo is a wordmark: the text is the image, so the wrong language is worse than none."""
    chosen = _best(
        [
            {"lang": "de", "likes": "900", "url": "https://f/de.png"},
            {"lang": "en", "likes": "2", "url": "https://f/en.png"},
        ]
    )

    assert chosen == "https://f/en.png"


def test_textless_art_counts_as_a_match_not_a_miss() -> None:
    """fanart uses an empty lang for artwork with no text in it, which suits any language."""
    chosen = _best(
        [
            {"lang": "fr", "likes": "900", "url": "https://f/fr.jpg"},
            {"lang": "", "likes": "1", "url": "https://f/neutral.jpg"},
        ]
    )

    assert chosen == "https://f/neutral.jpg"


def test_likes_break_the_tie_within_a_language() -> None:
    chosen = _best(
        [
            {"lang": "en", "likes": "3", "url": "https://f/meh.png"},
            {"lang": "en", "likes": "40", "url": "https://f/best.png"},
        ]
    )

    assert chosen == "https://f/best.png"


def test_entries_without_a_url_are_skipped() -> None:
    assert _best([{"lang": "en", "likes": "99"}, {"lang": "en", "url": "https://f/ok.png"}]) == (
        "https://f/ok.png"
    )


def test_unparseable_likes_do_not_crash_the_sort() -> None:
    """The field is a string in fanart's JSON, so it is one bad upload away from being junk."""
    assert _best([{"lang": "en", "likes": None, "url": "https://f/a.png"}]) == "https://f/a.png"


def test_nothing_to_choose_from_is_none() -> None:
    assert _best([]) is None
