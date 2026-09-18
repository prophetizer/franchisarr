"""Resolve a Plex item to a TMDb id (docs/DESIGN.md technical challenges #1 and #14).

Four tiers, most trustworthy first:

1. **GUID** -- Plex already knows the TMDb id. On a real 3,427-film library this covered 99.9%
   of items, so everything below is a genuine fallback, not the hot path.
2. **IMDb id** -- resolved through TMDb's /find. Measured on that same library, this covers more
   of the remaining gap than title matching does, which is why it sits above it.
3. **TVDb id** -- same mechanism. Mostly relevant to items matched by legacy or anime agents.
4. **Title + year search** -- the only guessing step, and the only one with a confidence bar.

Challenge #14 asks for an actual bar rather than a vague notion of "strong match":

* accepted when normalised title similarity >= 0.87 **and** both sides have a release year
  within +/-1 of each other
* flagged for review when similarity >= 0.60, when a near-perfect title has the wrong year, or
  when there is no year to corroborate the title at all
* rejected below that

Requiring a year on both sides for auto-accept, rather than merely not-disagreeing, matters more
than it looks: short titles with a plural or sequel suffix score very high on similarity alone
("Predator"/"Predators" is 0.94), so the year is the only independent evidence a title search
has.

The middle tier is the important one. A near miss is neither silently trusted (which would add
the wrong film to somebody's Radarr) nor silently dropped (which would make a missing film
invisible with no way to find out why). It surfaces for a human to confirm.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.clients.plex_client import PlexItem
from app.clients.tmdb_client import (
    TmdbClient,
    TmdbError,
    TmdbMovieSummary,
    TmdbShowSummary,
)
from app.models import MatchSource

logger = logging.getLogger(__name__)

#: Title similarity at or above this, with a matching year, is taken as correct.
ACCEPT_SIMILARITY = 0.87

#: Below this a candidate isn't worth a human's attention either.
REVIEW_SIMILARITY = 0.60

#: Release years disagree between Plex and TMDb often enough (festival vs. general release,
#: regional dates) that demanding an exact match would reject correct answers.
YEAR_TOLERANCE = 1

_ARTICLES = ("the ", "a ", "an ")
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")
_TRAILING_YEAR = re.compile(r"\s*\(\d{4}\)\s*$")

#: Plex titles routinely carry edition markers that TMDb's titles do not.
_EDITION_MARKERS = re.compile(
    r"\b(director\'?s cut|extended( edition| cut)?|unrated|remastered|theatrical( cut)?|"
    r"special edition|final cut|redux|imax|3d|uncut)\b",
    re.IGNORECASE,
)


def normalise_title(title: str) -> str:
    """Reduce a title to something comparable across sources.

    Strips accents, punctuation, a trailing "(1984)", edition markers, and a leading article, so
    "The Lord of the Rings: The Two Towers" and "Lord of the Rings - The Two Towers (Extended
    Edition)" compare as near-identical rather than as a weak partial match.
    """
    text = unicodedata.normalize("NFKD", title or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    text = _TRAILING_YEAR.sub("", text)
    text = _EDITION_MARKERS.sub(" ", text)
    text = _PUNCTUATION.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()

    for article in _ARTICLES:
        if text.startswith(article):
            text = text[len(article):]
            break

    return text


def title_similarity(left: str, right: str) -> float:
    a, b = normalise_title(left), normalise_title(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def years_agree(left: int | None, right: int | None) -> bool:
    """Unknown years don't disagree -- absence of evidence isn't evidence of a mismatch."""
    if left is None or right is None:
        return True
    return abs(left - right) <= YEAR_TOLERANCE


@dataclass(frozen=True)
class MatchResult:
    tmdb_id: int | None
    source: str
    confidence: float | None = None
    needs_review: bool = False
    candidate_title: str | None = None
    reason: str | None = None

    @property
    def matched(self) -> bool:
        return self.tmdb_id is not None

    @property
    def usable(self) -> bool:
        """Safe to act on without asking a human."""
        return self.matched and not self.needs_review


NO_MATCH = MatchResult(tmdb_id=None, source=MatchSource.NONE.value, reason="no candidate found")


def score_candidate(
    item_title: str, item_year: int | None, candidate: TmdbMovieSummary
) -> tuple[float, bool]:
    """Score one search result. Returns (similarity, year_ok)."""
    return title_similarity(item_title, candidate.title), years_agree(item_year, candidate.year)


def choose_candidate(
    item_title: str, item_year: int | None, candidates: list[TmdbMovieSummary]
) -> MatchResult:
    """Apply the confidence bar to a list of search results."""
    if not candidates:
        return NO_MATCH

    scored = [
        (similarity, year_ok, candidate)
        for candidate in candidates
        for similarity, year_ok in [score_candidate(item_title, item_year, candidate)]
    ]
    # Prefer agreeing years, then similarity: a perfect title in the wrong year is more often a
    # remake than a match.
    scored.sort(key=lambda row: (row[1], row[0]), reverse=True)
    similarity, year_ok, best = scored[0]

    # A year on *both* sides is required to auto-accept, not merely a non-disagreement. Short
    # titles with a plural or sequel suffix score dangerously high on similarity alone --
    # "Predator"/"Predators" is 0.94 and "Alien"/"Aliens" is 0.91, and those are different films.
    # The year is the only independent corroboration a title search has; without it, the most
    # confident-looking matches are exactly the ones most likely to be wrong.
    corroborated = item_year is not None and best.year is not None and year_ok

    if similarity >= ACCEPT_SIMILARITY and corroborated:
        return MatchResult(
            tmdb_id=best.tmdb_id,
            source=MatchSource.TITLE.value,
            confidence=round(similarity, 3),
            candidate_title=best.title,
        )

    if similarity >= REVIEW_SIMILARITY:
        if not year_ok:
            reason = f"title matched {similarity:.0%} but the year differs ({item_year} vs {best.year})"
        elif not corroborated:
            reason = f"title matched {similarity:.0%} but there is no release year to confirm it"
        else:
            reason = f"title only matched {similarity:.0%}"
        return MatchResult(
            tmdb_id=best.tmdb_id,
            source=MatchSource.TITLE.value,
            confidence=round(similarity, 3),
            needs_review=True,
            candidate_title=best.title,
            reason=reason,
        )

    return MatchResult(
        tmdb_id=None,
        source=MatchSource.NONE.value,
        confidence=round(similarity, 3),
        candidate_title=best.title,
        reason=f"best candidate only matched {similarity:.0%}",
    )


def match_movie(item: PlexItem, client: TmdbClient) -> MatchResult:
    """Resolve one Plex movie to a TMDb id, cheapest and most trustworthy tier first."""
    ids = item.external_ids

    if ids.tmdb_id:
        return MatchResult(tmdb_id=ids.tmdb_id, source=MatchSource.GUID.value)

    for external_id, source, label in (
        (ids.imdb_id, "imdb_id", MatchSource.IMDB.value),
        (str(ids.tvdb_id) if ids.tvdb_id else None, "tvdb_id", MatchSource.TVDB.value),
    ):
        if not external_id:
            continue
        try:
            found = client.find_by_external_id(external_id, source)
        except TmdbError as exc:
            logger.warning("TMDb lookup failed for %s %s: %s", source, external_id, exc)
            continue
        if found:
            return MatchResult(tmdb_id=found.tmdb_id, source=label)

    if not item.title:
        return NO_MATCH

    try:
        candidates = client.search_movies(item.title, item.year)
    except TmdbError as exc:
        logger.warning("TMDb search failed for %r: %s", item.title, exc)
        return MatchResult(tmdb_id=None, source=MatchSource.NONE.value, reason=str(exc))

    return choose_candidate(item.title, item.year, candidates)


def choose_show_candidate(
    item_name: str, item_year: int | None, candidates: list[TmdbShowSummary]
) -> MatchResult:
    """Apply the same confidence bar to shows.

    Shows are, if anything, more dangerous than films here: a franchise deliberately names its
    spin-offs after the original ("NCIS" / "NCIS: Los Angeles"), so title similarity alone is
    exactly the wrong tool. The year requirement does the real work.
    """
    return choose_candidate(
        item_name,
        item_year,
        [
            TmdbMovieSummary(
                tmdb_id=candidate.tmdb_id,
                title=candidate.name,
                release_date=candidate.first_air_date,
            )
            for candidate in candidates
        ],
    )


def match_show(item: PlexItem, client: TmdbClient) -> MatchResult:
    """Resolve one Plex show to a TMDb id, cheapest and most trustworthy tier first."""
    ids = item.external_ids

    if ids.tmdb_id:
        return MatchResult(tmdb_id=ids.tmdb_id, source=MatchSource.GUID.value)

    for external_id, source, label in (
        (ids.imdb_id, "imdb_id", MatchSource.IMDB.value),
        (str(ids.tvdb_id) if ids.tvdb_id else None, "tvdb_id", MatchSource.TVDB.value),
    ):
        if not external_id:
            continue
        try:
            found = client.find_show_by_external_id(external_id, source)
        except TmdbError as exc:
            logger.warning("TMDb show lookup failed for %s %s: %s", source, external_id, exc)
            continue
        if found:
            return MatchResult(tmdb_id=found.tmdb_id, source=label)

    if not item.title:
        return NO_MATCH

    try:
        candidates = client.search_shows(item.title, item.year)
    except TmdbError as exc:
        logger.warning("TMDb show search failed for %r: %s", item.title, exc)
        return MatchResult(tmdb_id=None, source=MatchSource.NONE.value, reason=str(exc))

    return choose_show_candidate(item.title, item.year, candidates)
