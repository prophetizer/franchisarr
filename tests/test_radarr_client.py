"""Radarr v3 client, with attention to the unreachable-instance state (challenge #15)."""

from __future__ import annotations

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from app.clients.radarr_client import (
    MovieAlreadyAddedError,
    RadarrAuthError,
    RadarrClient,
    RadarrError,
    RadarrUnreachableError,
)

URL = "http://radarr.test:7878"
API = "abc123def456"


def _client() -> RadarrClient:
    return RadarrClient(URL, API)


# ------------------------------------------------------------------ connection


@responses.activate
def test_test_connection_returns_the_version() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/system/status", json={"version": "5.14.0.9383"})

    assert _client().test_connection() == "5.14.0.9383"
    assert responses.calls[0].request.headers["X-Api-Key"] == API


@responses.activate
def test_a_bad_api_key_is_named_as_such() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/system/status", status=401)

    with pytest.raises(RadarrAuthError):
        _client().test_connection()


@responses.activate
def test_an_unreachable_instance_is_distinguishable_from_a_broken_one() -> None:
    """The add dialog needs to say "can't reach this right now" rather than showing nothing."""
    responses.add(
        responses.GET, f"{URL}/api/v3/system/status", body=RequestsConnectionError("refused")
    )

    with pytest.raises(RadarrUnreachableError):
        _client().test_connection()


@responses.activate
def test_pointing_at_something_that_is_not_radarr_says_so() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/system/status", body="<html>hello</html>")

    with pytest.raises(RadarrError) as exc_info:
        _client().test_connection()

    assert "really Radarr" in str(exc_info.value)


@responses.activate
def test_an_error_never_contains_the_api_key() -> None:
    responses.add(
        responses.GET,
        f"{URL}/api/v3/system/status",
        body=RequestsConnectionError(f"failed with X-Api-Key: {API}"),
    )

    with pytest.raises(RadarrError) as exc_info:
        _client().test_connection()

    assert API not in str(exc_info.value)


# ------------------------------------------------------------------ options


@responses.activate
def test_quality_profiles_and_root_folders() -> None:
    responses.add(
        responses.GET,
        f"{URL}/api/v3/qualityprofile",
        json=[{"id": 1, "name": "HD-1080p"}, {"id": 2, "name": "Ultra-HD"}],
    )
    responses.add(
        responses.GET,
        f"{URL}/api/v3/rootfolder",
        json=[{"path": "/movies", "freeSpace": 2_000_000_000_000, "accessible": True}],
    )

    client = _client()

    assert [p.name for p in client.quality_profiles()] == ["HD-1080p", "Ultra-HD"]
    folder = client.root_folders()[0]
    assert folder.path == "/movies"
    assert "TB free" in folder.free_space_label


@responses.activate
def test_a_root_folder_with_unknown_free_space_has_no_label() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/rootfolder", json=[{"path": "/movies"}])

    assert _client().root_folders()[0].free_space_label == ""


# ------------------------------------------------------------------ library state


@responses.activate
def test_movies_reports_what_the_instance_tracks() -> None:
    responses.add(
        responses.GET,
        f"{URL}/api/v3/movie",
        json=[
            {"tmdbId": 90, "title": "Beverly Hills Cop", "hasFile": True, "monitored": True},
            {"tmdbId": 96, "title": "Beverly Hills Cop II", "hasFile": False, "monitored": True},
            {"title": "No tmdb id here"},
        ],
    )

    movies = _client().movies()

    assert {m.tmdb_id for m in movies} == {90, 96}
    assert movies[0].has_file is True


@responses.activate
def test_the_queue_is_read_from_the_records_wrapper() -> None:
    responses.add(
        responses.GET,
        f"{URL}/api/v3/queue",
        json={"records": [{"movie": {"tmdbId": 306}}, {"tmdbId": 12345}]},
    )

    assert _client().queued_tmdb_ids() == {306, 12345}


@responses.activate
def test_an_empty_queue_is_not_an_error() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/queue", json={"records": []})

    assert _client().queued_tmdb_ids() == set()


# ------------------------------------------------------------------ adding


@responses.activate
def test_add_movie_posts_what_radarr_itself_described() -> None:
    """Radarr's add endpoint wants fields only its metadata layer knows, so the film is looked up
    first and our four decisions are added to what comes back."""
    responses.add(
        responses.GET,
        f"{URL}/api/v3/movie/lookup",
        json=[{"tmdbId": 306, "title": "Beverly Hills Cop III", "titleSlug": "bhc-iii",
               "year": 1994, "images": []}],
    )
    responses.add(responses.POST, f"{URL}/api/v3/movie",
                  json={"id": 7, "tmdbId": 306, "title": "Beverly Hills Cop III"})

    added = _client().add_movie(306, quality_profile_id=1, root_folder_path="/movies")

    assert added.tmdb_id == 306
    posted = responses.calls[-1].request.body
    import json as _json

    body = _json.loads(posted)
    assert body["qualityProfileId"] == 1
    assert body["rootFolderPath"] == "/movies"
    assert body["monitored"] is True
    assert body["addOptions"]["searchForMovie"] is True
    assert body["titleSlug"] == "bhc-iii", "Radarr's own description must be preserved"


@responses.activate
def test_search_on_add_can_be_turned_off() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/movie/lookup",
                  json=[{"tmdbId": 306, "title": "X"}])
    responses.add(responses.POST, f"{URL}/api/v3/movie", json={"id": 7, "tmdbId": 306})

    _client().add_movie(306, quality_profile_id=1, root_folder_path="/m", search_on_add=False)

    import json as _json

    assert _json.loads(responses.calls[-1].request.body)["addOptions"]["searchForMovie"] is False


@responses.activate
def test_adding_something_radarr_already_has_is_its_own_error() -> None:
    """Usually means the gap list was stale, not that anything is broken."""
    responses.add(
        responses.GET,
        f"{URL}/api/v3/movie/lookup",
        json=[{"id": 42, "tmdbId": 306, "title": "Beverly Hills Cop III"}],
    )

    with pytest.raises(MovieAlreadyAddedError):
        _client().add_movie(306, quality_profile_id=1, root_folder_path="/movies")


@responses.activate
def test_a_film_radarr_cannot_find_is_reported_clearly() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/movie/lookup", json=[])

    with pytest.raises(RadarrError) as exc_info:
        _client().add_movie(1, quality_profile_id=1, root_folder_path="/movies")

    assert "couldn't find" in str(exc_info.value)


@responses.activate
def test_a_radarr_validation_failure_surfaces_its_message() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/movie/lookup", json=[{"tmdbId": 1, "title": "X"}])
    responses.add(
        responses.POST,
        f"{URL}/api/v3/movie",
        status=400,
        json=[{"errorMessage": "Root folder /nope does not exist"}],
    )

    with pytest.raises(RadarrError) as exc_info:
        _client().add_movie(1, quality_profile_id=1, root_folder_path="/nope")

    assert "Root folder /nope does not exist" in str(exc_info.value)


# ------------------------------------------------------------------ auth proxies


@responses.activate
def test_an_sso_proxy_is_not_reported_as_a_bad_api_key() -> None:
    """Plenty of this audience puts Authelia or similar in front of their *arr apps. The proxy
    answers 401 with an HTML login page, and calling that "your API key was rejected" sends
    someone to check a credential that was never the problem."""
    responses.add(
        responses.GET,
        f"{URL}/api/v3/system/status",
        status=401,
        body='<a href="https://auth.example.com/?rd=https%3A%2F%2Fradarr">Found</a>',
        content_type="text/html",
    )

    with pytest.raises(RadarrAuthError) as exc_info:
        _client().test_connection()

    message = str(exc_info.value)
    assert "authentication proxy" in message
    assert "bypass rule" in message
    assert "rejected the API key" not in message


@responses.activate
def test_a_genuine_key_rejection_still_says_so() -> None:
    responses.add(
        responses.GET, f"{URL}/api/v3/system/status", status=401,
        json={"error": "Unauthorized"},
    )

    with pytest.raises(RadarrAuthError) as exc_info:
        _client().test_connection()

    assert "rejected the API key" in str(exc_info.value)
