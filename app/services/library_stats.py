"""The library in numbers (0.72.0, michael's pick): films by decade, how much is watched, how long
it all runs, the most complete sets, the genres and directors the shelves lean to. Read-time and
from the same tables as everything else; no request leaves the app."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlmodel import Session, col, select

from app.models import ItemType, LibraryItem, MovieDirector, TmdbCollectionMovie
from app.services.about_service import GENRES
from app.services.ownership_service import on_enabled_server


@dataclass(frozen=True)
class Bar:
    label: str
    value: int
    #: Of `value`, how many are watched (the darker part of a decade's bar); None when unknown.
    part: int | None = None
    detail: str = ""
    path: str | None = None


@dataclass
class Numbers:
    films: int = 0
    shows: int = 0
    watched: int | None = None
    #: Minutes across films whose runtime is known, and how many those are.
    minutes: int = 0
    timed: int = 0
    decades: list[Bar] = field(default_factory=list)
    complete_sets: int = 0
    sets_with_gaps: int = 0
    closest: list[Bar] = field(default_factory=list)
    genres: list[Bar] = field(default_factory=list)
    directors: list[Bar] = field(default_factory=list)

    @property
    def peak(self) -> int:
        return max((b.value for b in self.decades), default=0)


def numbers(session: Session, gaps: list) -> Numbers:  # noqa: ANN001 - every CollectionGap
    out = Numbers()
    rows = session.exec(
        select(LibraryItem.tmdb_id, LibraryItem.item_key, LibraryItem.item_type, LibraryItem.year,
               LibraryItem.runtime, LibraryItem.watched)
        .where(on_enabled_server(), col(LibraryItem.needs_review) == False)  # noqa: E712 - SQL
    ).all()
    # One per title: the same film on two servers is one film; True watched on any wins.
    films: dict[object, list] = {}
    shows: set[object] = set()
    for tmdb_id, key, item_type, year, runtime, watched in rows:
        ident = tmdb_id or f"k:{key}"
        if item_type == ItemType.SHOW.value:
            shows.add(ident)
            continue
        have = films.setdefault(ident, [tmdb_id, year, runtime, watched])
        have[1] = have[1] or year
        have[2] = max(have[2] or 0, runtime or 0) or None
        have[3] = True if (watched or have[3]) else (False if (watched is False or have[3] is False) else None)
    out.films, out.shows = len(films), len(shows)
    known = [f for f in films.values() if f[3] is not None]
    out.watched = sum(1 for f in known if f[3]) if known else None
    timed = [f[2] for f in films.values() if f[2]]
    out.minutes, out.timed = sum(timed), len(timed)

    by_decade: Counter = Counter()
    seen_decade: Counter = Counter()
    for _, year, _, watched in films.values():
        if year:
            by_decade[year // 10 * 10] += 1
            seen_decade[year // 10 * 10] += 1 if watched else 0
    out.decades = [Bar(f"{d}s", by_decade[d], seen_decade[d] if known else None) for d in sorted(by_decade)]

    out.complete_sets = sum(1 for g in gaps if g.owned and not g.missing)
    out.sets_with_gaps = sum(1 for g in gaps if g.owned and g.missing)
    nearly = sorted((g for g in gaps if len(g.owned) + len(g.missing) >= 3 and g.missing and g.owned),
                    key=lambda g: (-len(g.owned) / (len(g.owned) + len(g.missing)), len(g.missing), g.name.casefold()))
    out.closest = [Bar(g.name, round(100 * len(g.owned) / (len(g.owned) + len(g.missing))),
                       detail=f"{len(g.owned)} of {len(g.owned) + len(g.missing)}", path=f"/collections/{g.collection_id}")
                   for g in nearly[:8]]

    owned_ids = {f[0] for f in films.values() if f[0]}
    genres: Counter = Counter()
    if owned_ids:
        seen: set[int] = set()
        for tmdb_id, ids in session.exec(select(TmdbCollectionMovie.tmdb_movie_id, TmdbCollectionMovie.genre_ids)
                                         .where(col(TmdbCollectionMovie.tmdb_movie_id).in_(owned_ids))):
            if tmdb_id in seen or not ids:
                continue
            seen.add(tmdb_id)
            for g in ids.split(","):
                if g.strip().isdigit() and int(g) in GENRES:
                    genres[GENRES[int(g)]] += 1
        directors: Counter = Counter()
        names: dict[int, str] = {}
        for tmdb_id, person_id, name in session.exec(select(MovieDirector.tmdb_movie_id, MovieDirector.person_id, MovieDirector.name)
                                                     .where(col(MovieDirector.tmdb_movie_id).in_(owned_ids),
                                                            col(MovieDirector.person_id) != 0)):
            directors[person_id] += 1
            names[person_id] = name
        out.directors = [Bar(names[p], n, path=f"/directors/{p}") for p, n in directors.most_common(8)]
    out.genres = [Bar(name, n) for name, n in genres.most_common(10)]
    return out
