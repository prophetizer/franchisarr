"""Work out which films are missing from collections the user partly owns.

Reads only cached data, so this is cheap enough to run on a page load. `scan_service` is what
talks to Plex and TMDb.

Three separate things can hide a film, and they are deliberately not the same thing:

* **owned** -- it's in the Plex library already.
* **collection exclude** -- a data-quality correction, shared by everyone: TMDb lists a
  re-release or a director's cut as a separate film and it shouldn't count as a gap.
* **dismissed** -- one person's "don't show me this", private to that user.

A fourth thing merely *defers* a film rather than hiding it. TMDb collections include announced
sequels that do not exist yet, and there are far more of them than you would guess: on a real
3,428-film library, 155 of 382 reported gaps had a future release date or no release date at
all, and 126 of 239 collections had no released film missing whatsoever. Reporting "Untitled
Beetlejuice 3" as a gap you should go and get is not useful, so upcoming films are counted
separately rather than mixed in. They are not discarded -- adding one to Radarr is perfectly
sensible, since Radarr will monitor and grab it on release -- they just do not drive the "this
collection has gaps" signal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlmodel import Session, col, select

from app.models import (
    CollectionExclude,
    DismissedItem,
    ItemType,
    LibraryItem,
    RadarrInstance,
    RadarrMovie,
    TmdbCollection,
    TmdbCollectionMovie,
    TmdbMovie,
)
from app.services.settings_service import SettingKey, get_bool_setting

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MissingMovie:
    tmdb_id: int
    title: str
    release_year: int | None
    release_date: str | None = None

    def is_released(self, today: date | None = None) -> bool:
        """Whether this film exists yet.

        No release date means "announced, not scheduled" -- treated as not released, since a film
        TMDb cannot date is certainly not one you can obtain.
        """
        if not self.release_date:
            return False
        return self.release_date <= (today or date.today()).isoformat()


@dataclass(frozen=True)
class CollectionGap:
    collection_id: int
    name: str
    owned: tuple[MissingMovie, ...]
    #: Films that exist and aren't in the library. This is the actionable list.
    missing: tuple[MissingMovie, ...]
    #: Announced or scheduled but not yet released. Addable, but not a gap to act on today.
    upcoming: tuple[MissingMovie, ...] = ()

    @property
    def total(self) -> int:
        return len(self.owned) + len(self.missing) + len(self.upcoming)

    @property
    def has_gaps(self) -> bool:
        """Deliberately ignores `upcoming`: a collection whose only absence is a film nobody can
        watch yet is complete as far as the user is concerned."""
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


def radarr_known_ids(session: Session, instance_id: int | None = None) -> set[int]:
    """Films Radarr already tracks, and so aren't gaps.

    Two settings shape this (technical challenge #5):

    * per-instance `hide_if_queued` -- whether a film that is downloading but not yet imported
      counts as "have it". A film in the queue is on its way, so for most people it does; someone
      who wants to see it listed until it lands can turn it off.
    * global `cross_instance_dedup` -- when off (the default), each instance is judged
      independently, which is right for a 4K/1080p split where you may legitimately want both.
      When on, a film in *any* instance counts everywhere, which is right when instances are
      split by content type rather than quality tier.
    """
    cross_instance = get_bool_setting(session, SettingKey.CROSS_INSTANCE_DEDUP, False)

    statement = select(RadarrMovie, RadarrInstance).join(
        RadarrInstance, col(RadarrMovie.instance_id) == col(RadarrInstance.id)
    )
    if instance_id is not None and not cross_instance:
        statement = statement.where(col(RadarrMovie.instance_id) == instance_id)

    known: set[int] = set()
    for movie, instance in session.exec(statement).all():
        if movie.in_queue and not instance.hide_if_queued:
            continue
        known.add(movie.tmdb_id)
    return known


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


def collection_gaps(
    session: Session,
    user_id: int | None = None,
    *,
    today: date | None = None,
    radarr_instance_id: int | None = None,
) -> list[CollectionGap]:
    """Every cached collection the library touches, with its owned and missing films.

    Collections where nothing is owned are left out: those are collections the user has no
    demonstrated interest in, and including them would turn this into "every franchise on TMDb".
    """
    # "Owned" means in Plex or already handled by Radarr. Both hide a film for the same reason:
    # there is nothing for the user to do about it.
    owned = owned_tmdb_ids(session) | radarr_known_ids(session, radarr_instance_id)
    dismissed = dismissed_ids(session, user_id)

    # Only collections the *Plex library* touches are considered. Keying this off `owned` would
    # let a single Radarr add pull an entire unrelated franchise into the gap list.
    in_library = owned_tmdb_ids(session)
    relevant = {
        row.collection_id
        for row in session.exec(
            select(TmdbMovie).where(col(TmdbMovie.collection_id).is_not(None))
        ).all()
        if row.collection_id and row.tmdb_id in in_library
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
        upcoming_here: list[MissingMovie] = []

        for member in members:
            entry = MissingMovie(
                tmdb_id=member.tmdb_movie_id,
                title=member.title,
                release_year=member.release_year,
                release_date=member.release_date,
            )
            if member.tmdb_movie_id in owned:
                owned_here.append(entry)
            elif member.tmdb_movie_id in excluded or member.tmdb_movie_id in dismissed:
                continue
            elif entry.is_released(today):
                missing_here.append(entry)
            else:
                upcoming_here.append(entry)

        if not owned_here:
            continue

        gaps.append(
            CollectionGap(
                collection_id=collection_id,
                name=collection.name,
                owned=tuple(owned_here),
                missing=tuple(missing_here),
                upcoming=tuple(upcoming_here),
            )
        )

    gaps.sort(key=lambda gap: (not gap.has_gaps, gap.name.casefold()))
    return gaps


def collections_with_gaps(
    session: Session,
    user_id: int | None = None,
    *,
    today: date | None = None,
    radarr_instance_id: int | None = None,
) -> list[CollectionGap]:
    return [
        gap
        for gap in collection_gaps(
            session, user_id, today=today, radarr_instance_id=radarr_instance_id
        )
        if gap.has_gaps
    ]


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
