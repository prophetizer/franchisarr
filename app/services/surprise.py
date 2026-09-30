"""Surprise me (0.53.0): one missing film picked at random, from the sets being collected.

Only films worth being surprised by (michael's call): rated at least MIN_RATING on TMDb by at
least MIN_VOTES people, from a collection or a director's films, not dismissed by this person.
A franchise's films are here when they're in a collection or by a director; a franchise-only
film carries no score to judge it by.

The pool takes most of a second to work out (a collection and a director pass), so it's kept per
person for POOL_FOR -- "spin again" is a click away, and a spin shouldn't wait on the database."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from threading import Lock

from sqlmodel import Session

MIN_RATING = 6.5
#: MIN_VOTES_FOR_A_RATING (10) decides whether a score is shown at all; a pick is a
#: recommendation, so it wants a score more people stand behind.
MIN_VOTES = 50
POOL_FOR = 600.0
#: Posters that roll past in Showcase's spin before the pick lands.
REEL = 14


@dataclass(frozen=True)
class Pick:
    tmdb_id: int
    title: str
    year: int | None
    poster_path: str | None
    rating: float
    path: str
    source: str               # "The Dark Knight Collection", "Christopher Nolan"
    by_director: bool = False

    @property
    def poster(self) -> str | None:
        from app.services.artwork import CARD_SIZE, poster_url

        return poster_url(self.poster_path, CARD_SIZE)

    @property
    def small_poster(self) -> str | None:
        from app.services.artwork import SMALL_CARD_SIZE, poster_url

        return poster_url(self.poster_path, SMALL_CARD_SIZE)


_pools: dict[int, tuple[float, list[Pick]]] = {}
_lock = Lock()


def _worthy(vote_average: float | None, vote_count: int | None) -> bool:
    return vote_average is not None and vote_average >= MIN_RATING and (vote_count or 0) >= MIN_VOTES


def build_pool(session: Session, user_id: int | None) -> list[Pick]:
    from app.services import director_service, movie_gap_service

    picks: dict[int, Pick] = {}
    for gap in movie_gap_service.collections_with_gaps(session, user_id):
        for m in gap.missing:
            if _worthy(m.vote_average, m.vote_count) and m.tmdb_id not in picks:
                picks[m.tmdb_id] = Pick(m.tmdb_id, m.title, m.release_year, m.poster_path, round(m.vote_average, 1),
                                        f"/collections/{gap.collection_id}", gap.name)
    for d in director_service.director_views(session, user_id):
        for m in d.missing:
            if _worthy(m.vote_average, m.vote_count) and m.tmdb_id not in picks:
                year = int(m.release_date[:4]) if m.release_date and m.release_date[:4].isdigit() else None
                picks[m.tmdb_id] = Pick(m.tmdb_id, m.title, year, m.poster_path, round(m.vote_average, 1),
                                        f"/directors/{d.person_id}", d.name, by_director=True)
    return list(picks.values())


def pool(session: Session, user_id: int, *, now: float | None = None) -> list[Pick]:
    now = time.monotonic() if now is None else now
    with _lock:
        kept = _pools.get(user_id)
        if kept and now - kept[0] < POOL_FOR:
            return kept[1]
    found = build_pool(session, user_id)
    with _lock:
        _pools[user_id] = (now, found)
    return found


def forget(user_id: int | None = None) -> None:
    """Drop the kept pools -- one person's, or everyone's."""
    with _lock:
        if user_id is None:
            _pools.clear()
        else:
            _pools.pop(user_id, None)


def spin(session: Session, user_id: int, *, avoid: int | None = None,
         rng: random.Random | None = None) -> tuple[Pick | None, list[str]]:
    """A pick, not `avoid` (the last one) when there's any choice; and the posters to roll past
    it in Showcase's spin."""
    rng = rng or random.Random()
    choices = pool(session, user_id)
    if not choices:
        return None, []
    fresh = [p for p in choices if p.tmdb_id != avoid] or choices
    chosen = rng.choice(fresh)
    others = [p for p in choices if p.tmdb_id != chosen.tmdb_id and p.small_poster]
    reel = [p.small_poster for p in rng.sample(others, min(REEL, len(others)))]
    return chosen, reel
