"""Films that are coming to franchises the user already owns part of.

The gap service already separates announced-but-unreleased films out of the missing list, because
they were 41% of it and nobody can go and get a film that doesn't exist. This is the other side
of that decision: those films are not noise, they are the one thing no *arr tool can tell the
user about. Radarr's calendar knows only what has been added to Radarr. This knows what the user
would *want* added, because it knows what they already have.

Two views of the same data. The page lists everything upcoming, soonest first. The scan compares
each film's date with the last one it saw, so a scheduled run can say "Shrek 5 got a release
date" rather than re-listing the same forty announcements every night.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlmodel import Session, col, select

from app.models import UpcomingWatch, utcnow
from app.services import movie_gap_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpcomingFilm:
    tmdb_id: int
    title: str
    collection_id: int
    collection_name: str
    release_date: str | None
    poster_path: str | None = None
    #: How much of the franchise the user has: "3 of 4" reads as a reason to care.
    owned_count: int = 0
    total_count: int = 0

    @property
    def poster(self) -> str | None:
        from app.services.artwork import SMALL_CARD_SIZE, poster_url

        return poster_url(self.poster_path, SMALL_CARD_SIZE)

    @property
    def release(self) -> date | None:
        try:
            return date.fromisoformat(self.release_date) if self.release_date else None
        except ValueError:
            return None

    def days_until(self, today: date | None = None) -> int | None:
        if self.release is None:
            return None
        return (self.release - (today or date.today())).days

    @property
    def month_label(self) -> str:
        """The group heading on the page. Undated films group under one heading at the end."""
        return self.release.strftime("%B %Y") if self.release else "No date yet"


@dataclass(frozen=True)
class DateEvent:
    """Something worth telling the user about a film's release date."""

    film: UpcomingFilm
    #: "dated" -- it has a date and didn't before; "moved" -- the date changed.
    kind: str
    previous: str | None = None

    @property
    def detail(self) -> str:
        if self.kind == "dated":
            return f"{self.film.collection_name} · {self.film.release_date}"
        return f"{self.film.collection_name} · {self.previous} → {self.film.release_date}"


def upcoming_films(
    session: Session, user_id: int | None = None, *, today: date | None = None
) -> list[UpcomingFilm]:
    """Every announced-but-unreleased film in a collection the user owns part of.

    Dated films first, soonest first; undated ones last, since "some day" is not a date to plan
    around. Dismissed and excluded films are already gone by the time the gap service hands
    these over, so a "not interested" on the collection page applies here too.
    """
    films: list[UpcomingFilm] = []
    for gap in movie_gap_service.collection_gaps(session, user_id, today=today):
        for movie in gap.upcoming:
            films.append(
                UpcomingFilm(
                    tmdb_id=movie.tmdb_id,
                    title=movie.title,
                    collection_id=gap.collection_id,
                    collection_name=gap.name,
                    release_date=movie.release_date,
                    poster_path=movie.poster_path,
                    owned_count=len(gap.owned),
                    total_count=gap.total,
                )
            )

    films.sort(key=lambda f: (f.release is None, f.release or date.max, f.title.casefold()))
    return films


def record_and_diff(session: Session, films: list[UpcomingFilm]) -> list[DateEvent]:
    """Bring the watch table up to date and say what changed.

    Returns events for films that gained a date or whose date moved. A film seen for the first
    time is recorded but not reported: on a first scan that is every announced sequel in the
    library at once, and on later scans a brand-new announcement will usually be undated -- the
    interesting moment is when it *gets* a date, and that is caught the next time round.
    """
    existing = {row.tmdb_id: row for row in session.exec(select(UpcomingWatch)).all()}
    now = utcnow()
    events: list[DateEvent] = []
    seen: set[int] = set()

    for film in films:
        seen.add(film.tmdb_id)
        row = existing.get(film.tmdb_id)
        if row is None:
            session.add(
                UpcomingWatch(
                    tmdb_id=film.tmdb_id,
                    title=film.title,
                    collection_id=film.collection_id,
                    collection_name=film.collection_name,
                    release_date=film.release_date,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
            continue

        if film.release_date and not row.release_date:
            events.append(DateEvent(film=film, kind="dated"))
        elif film.release_date and row.release_date and film.release_date != row.release_date:
            events.append(DateEvent(film=film, kind="moved", previous=row.release_date))

        row.title = film.title
        row.collection_name = film.collection_name
        row.release_date = film.release_date
        row.last_seen_at = now
        session.add(row)

    # Released, removed from the collection, or dismissed: no longer upcoming, so no longer
    # watched. A released film is an ordinary gap now and seen_gaps handles it from here.
    for tmdb_id, row in existing.items():
        if tmdb_id not in seen:
            session.delete(row)

    session.commit()
    if events:
        logger.info("Release-date news: %d film(s)", len(events))
    return events
