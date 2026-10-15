"""Add all missing (0.73.0, michael's pick): every missing film of a collection, franchise or
director, added to Radarr (or requested through Seerr) in one go -- after a confirm that lists
them. Still never automatic: an admin opens the dialog and presses the button. The films are
worked out again on the server when it's pressed, never taken from the page, and released
missing films only: what's coming isn't out to grab, and what a taste filter folded away stays
folded."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session

#: Most films one press adds. A franchise can be missing dozens; past this, add in batches.
MAX = 50
KINDS = ("collection", "franchise", "director")


@dataclass(frozen=True)
class Film:
    tmdb_id: int
    title: str
    year: int | None


@dataclass
class Batch:
    kind: str
    ref: str
    name: str
    films: list[Film] = field(default_factory=list)
    #: Missing beyond MAX, left for a second press.
    more: int = 0


def missing(session: Session, user_id: int | None, kind: str, ref: str) -> Batch | None:
    """The set's missing films, as the page shows them to this person; None when no such set."""
    films: list[Film]
    if kind == "collection":
        from app.services import movie_gap_service

        try:
            cid = int(ref)
        except ValueError:
            return None
        gap = next(iter(movie_gap_service.collection_gaps(session, user_id, only={cid})), None)
        if gap is None:
            return None
        name, films = gap.name, [Film(m.tmdb_id, m.title, m.release_year) for m in gap.missing]
    elif kind == "franchise":
        from app.services import franchise_service

        view = franchise_service.franchise_view(session, ref, user_id)
        if view is None:
            return None
        name, films = view.name, [Film(t.tmdb_id, t.title, t.year) for t in view.missing_films]
    elif kind == "director":
        from app.services import director_service

        try:
            pid = int(ref)
        except ValueError:
            return None
        view = director_service.director_view(session, pid, user_id)
        if view is None:
            return None
        name, films = view.name, [Film(t.tmdb_id, t.title, t.year) for t in view.missing]
    else:
        return None
    films.sort(key=lambda f: (f.year or 9999, f.title.casefold()))
    return Batch(kind, ref, name, films[:MAX], max(0, len(films) - MAX))
