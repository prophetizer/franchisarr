"""The Plex -> TMDb matcher, and the confidence bar from technical challenge #14.

The bar exists so a near miss is neither silently trusted (wrong film added to Radarr) nor
silently dropped (a real gap invisible with no explanation). Most of these tests pin that
middle ground.
"""

from __future__ import annotations

import pytest
import responses

from app.clients.plex_client import PlexMovie
from app.clients.plex_guid import ExternalIds
from app.clients.tmdb_client import TMDB_BASE_URL, TmdbClient, TmdbMovieSummary
from app.models import MatchSource
from app.services.matcher import (
    ACCEPT_SIMILARITY,
    REVIEW_SIMILARITY,
    choose_candidate,
    match_movie,
    normalise_title,
    title_similarity,
    years_agree,
)


def _movie(title: str, year: int | None = 2001, ids: ExternalIds | None = None) -> PlexMovie:
    return PlexMovie(
        item_key="1", title=title, year=year, external_ids=ids or ExternalIds(), guids=()
    )


def _candidate(tmdb_id: int, title: str, date: str | None = "2001-01-01") -> TmdbMovieSummary:
    return TmdbMovieSummary(tmdb_id=tmdb_id, title=title, release_date=date)


# ------------------------------------------------------------------ normalisation


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("The Godfather", "godfather"),
        ("A Beautiful Mind", "beautiful mind"),
        ("An Education", "education"),
        ("Amélie", "amelie"),
        ("WALL·E", "wall e"),
        ("Blade Runner (1982)", "blade runner"),
        ("Blade Runner - Director's Cut", "blade runner"),
        ("Aliens [Extended Edition]", "aliens"),
        ("Se7en", "se7en"),
        ("  Spaced   Out  ", "spaced out"),
    ],
)
def test_normalise_title(raw: str, expected: str) -> None:
    assert normalise_title(raw) == expected


def test_edition_markers_do_not_break_a_match() -> None:
    """Plex titles routinely carry edition markers that TMDb's titles don't."""
    assert title_similarity(
        "The Lord of the Rings: The Two Towers",
        "Lord of the Rings - The Two Towers (Extended Edition)",
    ) == 1.0


def test_a_sequel_is_not_confused_with_its_original() -> None:
    """The failure that would matter most: adding the wrong film to someone's Radarr."""
    assert title_similarity("Blade Runner", "Blade Runner 2049") < ACCEPT_SIMILARITY


# ------------------------------------------------------------------ year tolerance


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (1984, 1984, True),
        (1984, 1985, True),   # festival vs general release
        (1984, 1983, True),
        (1984, 1987, False),
        (None, 1984, True),   # unknown is not a disagreement
        (1984, None, True),
    ],
)
def test_years_agree(left: int | None, right: int | None, expected: bool) -> None:
    assert years_agree(left, right) is expected


# ------------------------------------------------------------------ the confidence bar


def test_a_strong_title_and_year_is_accepted() -> None:
    result = choose_candidate("Beverly Hills Cop", 1984, [_candidate(90, "Beverly Hills Cop", "1984-12-05")])

    assert result.usable is True
    assert result.tmdb_id == 90
    assert result.source == MatchSource.TITLE.value


def test_a_weak_title_is_flagged_for_review_not_used() -> None:
    result = choose_candidate(
        "Ocean's Eleven", 2001, [_candidate(5, "Ocean's Twelve", "2001-01-01")]
    )

    assert result.matched is True
    assert result.needs_review is True
    assert result.usable is False, "a guess must not be acted on without confirmation"


def test_a_hopelessly_different_title_is_not_even_offered_for_review() -> None:
    result = choose_candidate("Mad Max", 1979, [_candidate(9, "Mad Max: Fury Road", "1979-01-01")])

    assert result.matched is False


@pytest.mark.parametrize(
    ("owned", "found"),
    [("Predator", "Predators"), ("Alien", "Aliens")],
)
def test_a_near_identical_sequel_title_is_not_accepted_without_a_year(
    owned: str, found: str
) -> None:
    """These score 0.91-0.94 on title alone and are entirely different films.

    With no year on the library item there is nothing to corroborate the title, so the most
    confident-looking match is exactly the one most likely to be wrong. It must go to review.
    """
    result = choose_candidate(owned, None, [_candidate(11, found, "2010-07-07")])

    assert result.needs_review is True
    assert result.usable is False
    assert "no release year" in result.reason


def test_a_near_identical_sequel_title_is_caught_by_the_year_when_one_exists() -> None:
    result = choose_candidate("Predator", 1987, [_candidate(11, "Predators", "2010-07-07")])

    assert result.needs_review is True
    assert "year differs" in result.reason


def test_a_candidate_with_no_release_date_cannot_be_auto_accepted() -> None:
    result = choose_candidate("Beverly Hills Cop", 1984, [_candidate(90, "Beverly Hills Cop", None)])

    assert result.needs_review is True


def test_a_perfect_title_in_the_wrong_year_is_flagged_not_accepted() -> None:
    """More often a remake than a match -- so it goes to a human."""
    result = choose_candidate("The Thing", 1982, [_candidate(1234, "The Thing", "2011-10-14")])

    assert result.needs_review is True
    assert "year differs" in result.reason


def test_a_hopeless_candidate_is_rejected_outright() -> None:
    result = choose_candidate("Beverly Hills Cop", 1984, [_candidate(7, "Gone with the Wind")])

    assert result.matched is False
    assert result.tmdb_id is None


def test_no_candidates_is_not_a_match() -> None:
    assert choose_candidate("Anything", 2000, []).matched is False


def test_a_matching_year_is_preferred_over_a_better_title() -> None:
    """Given two plausible options, the one whose year agrees wins."""
    result = choose_candidate(
        "The Thing",
        1982,
        [_candidate(1, "The Thing", "2011-10-14"), _candidate(2, "The Thing", "1982-06-25")],
    )

    assert result.tmdb_id == 2
    assert result.usable is True


def test_the_thresholds_are_ordered_sensibly() -> None:
    assert 0 < REVIEW_SIMILARITY < ACCEPT_SIMILARITY <= 1.0


# ------------------------------------------------------------------ tier ordering


def test_a_tmdb_guid_is_used_without_asking_tmdb() -> None:
    """99.9% of a real library takes this path, so it must cost no HTTP at all."""
    with responses.RequestsMock():  # any request would fail the test
        result = match_movie(_movie("Beverly Hills Cop", 1984, ExternalIds(tmdb_id=90)),
                             TmdbClient("key"))

    assert result.tmdb_id == 90
    assert result.source == MatchSource.GUID.value
    assert result.usable is True


@responses.activate
def test_an_imdb_id_is_resolved_before_falling_back_to_the_title() -> None:
    """Measured on a real library, IMDb covers more of the gap than title matching."""
    responses.add(
        responses.GET,
        f"{TMDB_BASE_URL}/find/tt0086960",
        json={"movie_results": [{"id": 90, "title": "Beverly Hills Cop", "release_date": "1984-12-05"}]},
    )

    result = match_movie(
        _movie("Beverly Hills Cop", 1984, ExternalIds(imdb_id="tt0086960")), TmdbClient("key")
    )

    assert result.source == MatchSource.IMDB.value
    assert result.tmdb_id == 90
    assert len(responses.calls) == 1, "the title search should not have been reached"


@responses.activate
def test_a_tvdb_id_is_tried_when_there_is_no_imdb_id() -> None:
    responses.add(
        responses.GET,
        f"{TMDB_BASE_URL}/find/12345",
        json={"movie_results": [{"id": 55, "title": "Something", "release_date": "2001-01-01"}]},
    )

    result = match_movie(_movie("Something", 2001, ExternalIds(tvdb_id=12345)), TmdbClient("key"))

    assert result.source == MatchSource.TVDB.value


@responses.activate
def test_the_title_search_is_the_last_resort() -> None:
    responses.add(
        responses.GET,
        f"{TMDB_BASE_URL}/search/movie",
        json={"results": [{"id": 90, "title": "Beverly Hills Cop", "release_date": "1984-12-05"}]},
    )

    result = match_movie(_movie("Beverly Hills Cop", 1984), TmdbClient("key"))

    assert result.source == MatchSource.TITLE.value
    assert result.usable is True


@responses.activate
def test_a_failing_external_lookup_falls_through_rather_than_aborting() -> None:
    """One bad TMDb response must not abandon an item that the title search could still match."""
    responses.add(responses.GET, f"{TMDB_BASE_URL}/find/tt0086960", status=500)
    responses.add(
        responses.GET,
        f"{TMDB_BASE_URL}/search/movie",
        json={"results": [{"id": 90, "title": "Beverly Hills Cop", "release_date": "1984-12-05"}]},
    )

    result = match_movie(
        _movie("Beverly Hills Cop", 1984, ExternalIds(imdb_id="tt0086960")), TmdbClient("key")
    )

    assert result.tmdb_id == 90
    assert result.source == MatchSource.TITLE.value


@responses.activate
def test_an_item_with_nothing_to_go_on_is_simply_unmatched() -> None:
    responses.add(responses.GET, f"{TMDB_BASE_URL}/search/movie", json={"results": []})

    result = match_movie(_movie("Christmas 2019", None), TmdbClient("key"))

    assert result.matched is False
    assert result.source == MatchSource.NONE.value


def test_an_untitled_item_does_not_reach_tmdb() -> None:
    with responses.RequestsMock():
        assert match_movie(_movie("", None), TmdbClient("key")).matched is False
