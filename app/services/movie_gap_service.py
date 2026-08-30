"""Work out which films are missing from collections the user partly owns.

Reads only cached data, so this is cheap enough to run on a page load. `scan_service` is what
talks to Plex and TMDb.

Three separate things can hide a film, and they are deliberately not the same thing:

* **owned** -- it's in the Plex library already.
* **collection exclude** -- a data-quality correction, shared by everyone: TMDb lists a
  re-release or a director's cut as a separate film and it shouldn't count as a gap.
* **dismissed** -- one person's "don't show me this", private to that user.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.models import (
    CollectionExclude,
    DismissedItem,
    ItemType,
    LibraryItem,
    TmdbCollection,
    TmdbCollectionMovie,
    TmdbMovie,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MissingMovie:
    tmdb_id: int
    title: str
    release_year: int | None


@dataclass(frozen=True)
class CollectionGap:
    collection_id: int
    name: str
    owned: tuple[MissingMovie, ...]
    missing: tuple[MissingMovie, ...]

    @property
    def total(self) -> int:
        return len(self.owned) + len(self.missing)

    @property
    def has_gaps(self) -> bool:
        return bool(self.missing)


def owned_tmdb_ids(session: Session) -> set[int]:
    """TMDb ids of films actually in the library.

    Items flagged for review are excluded: an unconfirmed guess must not be able to mark a film
    as owned, because that would silently hide a real gap.
    """
    rows = session.exec(
        select(LibraryItem).where(
            col(LibraryItem.item_type) == ItemType.MOVIE.value,
            col(LibraryItem.tmdb_id).is_not(None),
            col(LibraryItem.needs_review) == False,  # noqa: E712 - SQL, not Python
        )
    ).all()
    return {row.tmdb_id for row in rows if row.tmdb_id}


def excluded_ids(session: Session, collection_id: int) -> set[int]:
    rows = session.exec(
        select(CollectionExclude).where(
            col(CollectionExclude.tmdb_collection_id) == collection_id
        )
    ).all()
    return {row.tmdb_movie_id for row in rows}


def dismissed_ids(session: Session, user_id: int | None) -> set[int]:
    if user_id is None:
        return set()
    rows = session.exec(
        select(DismissedItem).where(
            col(DismissedItem.user_id) == user_id,
            col(DismissedItem.item_type) == ItemType.MOVIE.value,
        )
    ).all()
    return {row.tmdb_id for row in rows}


def collection_gaps(session: Session, user_id: int | None = None) -> list[CollectionGap]:
    """Every cached collection the library touches, with its owned and missing films.

    Collections where nothing is owned are left out: those are collections the user has no
    demonstrated interest in, and including them would turn this into "every franchise on TMDb".
    """
    owned = owned_tmdb_ids(session)
    dismissed = dismissed_ids(session, user_id)

    relevant = {
        row.collection_id
        for row in session.exec(
            select(TmdbMovie).where(col(TmdbMovie.collection_id).is_not(None))
        ).all()
        if row.collection_id and row.tmdb_id in owned
    }

    gaps: list[CollectionGap] = []
    for collection_id in relevant:
        collection = session.get(TmdbCollection, collection_id)
        if collection is None:
            continue

        members = session.exec(
            select(TmdbCollectionMovie)
            .where(col(TmdbCollectionMovie.collection_id) == collection_id)
            .order_by(col(TmdbCollectionMovie.position))
        ).all()
        if not members:
            continue

        excluded = excluded_ids(session, collection_id)
        owned_here: list[MissingMovie] = []
        missing_here: list[MissingMovie] = []

        for member in members:
            entry = MissingMovie(
                tmdb_id=member.tmdb_movie_id,
                title=member.title,
                release_year=member.release_year,
            )
            if member.tmdb_movie_id in owned:
                owned_here.append(entry)
            elif member.tmdb_movie_id in excluded or member.tmdb_movie_id in dismissed:
                continue
            else:
                missing_here.append(entry)

        if not owned_here:
            continue

        gaps.append(
            CollectionGap(
                collection_id=collection_id,
                name=collection.name,
                owned=tuple(owned_here),
                missing=tuple(missing_here),
            )
        )

    gaps.sort(key=lambda gap: (not gap.has_gaps, gap.name.casefold()))
    return gaps


def collections_with_gaps(session: Session, user_id: int | None = None) -> list[CollectionGap]:
    return [gap for gap in collection_gaps(session, user_id) if gap.has_gaps]


def items_needing_review(session: Session) -> list[LibraryItem]:
    """Plausible-but-unconfirmed matches (technical challenge #14).

    Surfaced rather than silently skipped: a film that didn't match is otherwise invisible, and
    the user has no way to discover why a gap they expected isn't showing.
    """
    return list(
        session.exec(
            select(LibraryItem)
            .where(col(LibraryItem.needs_review) == True)  # noqa: E712 - SQL, not Python
            .order_by(col(LibraryItem.title))
        ).all()
    )


def unmatched_items(session: Session) -> list[LibraryItem]:
    return list(
        session.exec(
            select(LibraryItem)
            .where(col(LibraryItem.tmdb_id).is_(None))
            .order_by(col(LibraryItem.title))
        ).all()
    )
