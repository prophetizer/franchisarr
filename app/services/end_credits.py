"""The end credits at the foot of a collection's or franchise's page in Showcase (0.60.0): each
title in release order with its year and, for a film, who directed it -- then "The End" when
the set is complete, "To be continued" when it isn't.

Directors come from what the scan already holds: `movie_directors` for owned films, and the
filmographies in `director_films` (of directors of owned films) for missing ones. A film no
known director made just has no name under it; nothing is asked of TMDb for a page view."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.models import DirectorFilm, MovieDirector
from app.services.timeline import Step


@dataclass(frozen=True)
class Credit:
    title: str
    year: int | None
    #: "owned", "missing" or "upcoming", as the release strip has it.
    status: str
    #: "movie" or "show".
    item_type: str
    directors: tuple[str, ...]


def roll(session: Session, steps: list[Step]) -> list[Credit]:
    """The release strip's steps as credits. Three queries however long the set is."""
    film_ids = [s.tmdb_id for s in steps if s.item_type == "movie"]
    named: dict[int, list[str]] = {}
    if film_ids:
        for tmdb_id, name in session.exec(
                select(MovieDirector.tmdb_movie_id, MovieDirector.name)
                .where(col(MovieDirector.tmdb_movie_id).in_(film_ids))
                .order_by(col(MovieDirector.id))).all():
            if name not in named.setdefault(tmdb_id, []):
                named[tmdb_id].append(name)
        unknown = [i for i in film_ids if i not in named]
        if unknown:
            made = session.exec(select(DirectorFilm.tmdb_movie_id, DirectorFilm.person_id)
                                .where(col(DirectorFilm.tmdb_movie_id).in_(unknown))).all()
            people = {person for _, person in made}
            names: dict[int, str] = {}
            if people:
                names = {person: name for person, name in session.exec(
                    select(MovieDirector.person_id, MovieDirector.name)
                    .where(col(MovieDirector.person_id).in_(list(people)))).all()}
            for tmdb_id, person in made:
                name = names.get(person)
                if name and name not in named.setdefault(tmdb_id, []):
                    named[tmdb_id].append(name)
    return [Credit(s.title, s.year, s.status, s.item_type,
                   tuple(named.get(s.tmdb_id, ())) if s.item_type == "movie" else ())
            for s in steps]


def for_page(session: Session, user, steps: list[Step]) -> list[Credit]:  # noqa: ANN001 - a User
    """The credits for a detail page: only Showcase shows them, so only Showcase pays for them,
    and a set of one has nothing to roll."""
    from app.services import look

    if len(steps) < 2 or look.get(session, user.id) != look.SHOWCASE:
        return []
    return roll(session, steps)
