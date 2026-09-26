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
from collections import defaultdict
from dataclasses import dataclass, replace
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


#: Below this many votes a TMDb average is noise. Ten is TMDb's own floor for showing one.
MIN_VOTES_FOR_A_RATING = 10


@dataclass(frozen=True)
class MissingMovie:
    tmdb_id: int
    title: str
    release_year: int | None
    release_date: str | None = None
    poster_path: str | None = None
    vote_average: float | None = None
    vote_count: int | None = None
    popularity: float | None = None
    #: For owned films: which servers hold it, and whether it has been watched on any of them.
    servers: tuple[str, ...] = ()
    watched: bool | None = None

    @property
    def where(self) -> str:
        return ", ".join(self.servers)

    @property
    def rating(self) -> float | None:
        """The score worth showing: None until enough people have voted for it to mean anything.
        A film with three votes averaging 9.0 is not a 9.0 film."""
        if self.vote_average is None or (self.vote_count or 0) < MIN_VOTES_FOR_A_RATING:
            return None
        return round(self.vote_average, 1)

    def falls_below(self, threshold: float) -> bool:
        """Whether a rating filter should tuck this away. Unrated films never are: unknown is not
        the same as bad, and hiding them would hide every obscure film in every collection."""
        return self.rating is not None and self.rating < threshold

    @property
    def poster(self) -> str | None:
        from app.services.artwork import SMALL_CARD_SIZE, poster_url

        return poster_url(self.poster_path, SMALL_CARD_SIZE)

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
    #: Missing, released, and rated below the user's threshold. Kept rather than dropped so the
    #: filter is a fold, not a deletion -- the detail page shows what it hid.
    hidden: tuple[MissingMovie, ...] = ()
    poster_path: str | None = None
    backdrop_path: str | None = None
    #: A full fanart.tv URL, or None when no fanart key is configured.
    logo: str | None = None

    @property
    def poster(self) -> str | None:
        from app.services.artwork import CARD_SIZE, poster_url

        return poster_url(self.poster_path, CARD_SIZE)

    @property
    def small_poster(self) -> str | None:
        """For the list card, where the poster is a thumbnail beside the text."""
        from app.services.artwork import SMALL_CARD_SIZE, poster_url

        return poster_url(self.poster_path, SMALL_CARD_SIZE)

    @property
    def backdrop(self) -> str | None:
        from app.services.artwork import backdrop_url

        return backdrop_url(self.backdrop_path)

    @property
    def logo_image(self) -> str | None:
        from app.services.artwork import logo_url

        return logo_url(self.logo)

    @property
    def total(self) -> int:
        return len(self.owned) + len(self.missing) + len(self.upcoming)

    @property
    def has_gaps(self) -> bool:
        """Deliberately ignores `upcoming` and `hidden`: a collection whose only absence is a
        film nobody can watch yet, or one the user has said isn't worth having, is complete as
        far as they are concerned."""
        return bool(self.missing)

    @property
    def started(self) -> bool:
        """Whether any owned film has been watched -- the difference between a franchise the
        person is following and one that merely landed in the library."""
        return any(movie.watched for movie in self.owned)

    @property
    def watched_count(self) -> int:
        return sum(1 for movie in self.owned if movie.watched)

    @property
    def best_rating(self) -> float:
        """The strongest reason to look at this collection: its best-rated missing film.
        Unrated films sort last, not first -- a list led by films nobody has scored would bury
        the ones people actually want."""
        rated = [movie.rating for movie in self.missing if movie.rating is not None]
        return max(rated) if rated else -1.0


def owned_tmdb_ids(session: Session) -> set[int]:
    """TMDb ids of films actually in the library.

    Items flagged for review are excluded: an unconfirmed guess must not be able to mark a film
    as owned, because that would silently hide a real gap.
    """
    # The column, not the row: 20,000 LibraryItem objects in the session's identity map make
    # every later commit pay to expire them all (scripts/loadtest.py found the scan going O(n²)).
    ids = session.exec(
        select(LibraryItem.tmdb_id).where(
            col(LibraryItem.item_type) == ItemType.MOVIE.value,
            col(LibraryItem.tmdb_id).is_not(None),
            col(LibraryItem.needs_review) == False,  # noqa: E712 - SQL, not Python
        )
    ).all()
    return {tmdb_id for tmdb_id in ids if tmdb_id}


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
    # An open Seerr request is handled too: pending someone's approval or
    # already passed on to a Radarr, there is nothing for the user to do about it.
    from app.services import seerr_instance_service

    return known | seerr_instance_service.requested_ids(session, ItemType.MOVIE.value)


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


def min_gap_rating(session: Session) -> float:
    """The household's rating floor. 0 means the filter is off."""
    from app.services.settings_service import SettingKey, get_setting

    raw = get_setting(session, SettingKey.MIN_GAP_RATING) or "0"
    try:
        return max(0.0, min(10.0, float(raw)))
    except ValueError:
        return 0.0


def collection_gaps(
    session: Session,
    user_id: int | None = None,
    *,
    today: date | None = None,
    radarr_instance_id: int | None = None,
    sort: str = "rating",
    only: set[int] | None = None,
) -> list[CollectionGap]:
    """Every cached collection the library touches, with its owned and missing films.

    Collections where nothing is owned are left out: those are collections the user has no
    demonstrated interest in, and including them would turn this into "every franchise on TMDb".
    `only` narrows to those collection ids -- the detail page wants one, not all 3,000.
    """
    # "Owned" means in Plex or already handled by Radarr. Both hide a film for the same reason:
    # there is nothing for the user to do about it.
    owned = owned_tmdb_ids(session) | radarr_known_ids(session, radarr_instance_id)
    dismissed = dismissed_ids(session, user_id)
    from app.services.ownership_service import owned_details

    details = owned_details(session, ItemType.MOVIE.value)

    # Only collections the *Plex library* touches are considered. Keying this off `owned` would
    # let a single Radarr add pull an entire unrelated franchise into the gap list.
    in_library = owned_tmdb_ids(session)
    relevant = {
        collection_id
        for tmdb_id, collection_id in session.exec(
            select(TmdbMovie.tmdb_id, TmdbMovie.collection_id)
            .where(col(TmdbMovie.collection_id).is_not(None))
        ).all()
        if collection_id and tmdb_id in in_library
    }
    if only is not None:
        relevant &= only

    threshold = min_gap_rating(session)

    # Three queries for everything, not three per collection. At 3,300 collections the
    # per-collection form was 10,000 queries and eleven seconds a page (scripts/loadtest.py);
    # every page calls this. The tables are filtered in Python rather than with IN (...), which
    # SQLite caps at 999 parameters on older builds.
    collections = {
        c.tmdb_collection_id: c for c in session.exec(select(TmdbCollection)).all()
        if c.tmdb_collection_id in relevant
    }
    # Column tuples rather than ORM rows: at 25,000 members the objects alone were half the
    # page, and nothing here needs them to be objects.
    members_by_collection: dict[int, list[tuple]] = defaultdict(list)
    for row in session.exec(
        select(TmdbCollectionMovie.collection_id, TmdbCollectionMovie.tmdb_movie_id,
               TmdbCollectionMovie.title, TmdbCollectionMovie.release_year,
               TmdbCollectionMovie.release_date, TmdbCollectionMovie.poster_path,
               TmdbCollectionMovie.vote_average, TmdbCollectionMovie.vote_count,
               TmdbCollectionMovie.popularity)
        .order_by(col(TmdbCollectionMovie.collection_id), col(TmdbCollectionMovie.position))
    ).all():
        if row[0] in relevant:
            members_by_collection[row[0]].append(row)
    excluded_by_collection: dict[int, set[int]] = defaultdict(set)
    for exclude in session.exec(select(CollectionExclude)).all():
        excluded_by_collection[exclude.tmdb_collection_id].add(exclude.tmdb_movie_id)

    gaps: list[CollectionGap] = []
    for collection_id in relevant:
        collection = collections.get(collection_id)
        if collection is None:
            continue

        members = members_by_collection.get(collection_id)
        if not members:
            continue

        excluded = excluded_by_collection.get(collection_id, ())
        owned_here: list[MissingMovie] = []
        missing_here: list[MissingMovie] = []
        upcoming_here: list[MissingMovie] = []
        hidden_here: list[MissingMovie] = []

        for (_, tmdb_id, title, release_year, release_date, poster_path,
             vote_average, vote_count, popularity) in members:
            info = details.get(tmdb_id) if tmdb_id in owned else None
            entry = MissingMovie(
                tmdb_id=tmdb_id,
                title=title,
                release_year=release_year,
                release_date=release_date,
                poster_path=poster_path,
                vote_average=vote_average,
                vote_count=vote_count,
                popularity=popularity,
                servers=info.servers if info else (),
                watched=info.watched if info else None,
            )
            if tmdb_id in owned:
                owned_here.append(entry)
            elif tmdb_id in excluded or tmdb_id in dismissed:
                continue
            elif not entry.is_released(today):
                upcoming_here.append(entry)
            elif entry.falls_below(threshold):
                hidden_here.append(entry)
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
                upcoming=tuple(upcoming_here),
                hidden=tuple(hidden_here),
                poster_path=collection.poster_path,
                backdrop_path=collection.backdrop_path,
                logo=collection.logo_url,
            )
        )

    # Complete collections always trail. Within the incomplete ones, "rating" leads with the
    # collection whose best missing film is best -- the order that answers "what's worth
    # getting?" -- and "name" is the old alphabetical order for finding a known one.
    if sort == "name":
        gaps.sort(key=lambda gap: (not gap.has_gaps, gap.name.casefold()))
    else:
        gaps.sort(key=lambda gap: (not gap.has_gaps, -gap.best_rating, gap.name.casefold()))
    return gaps


def collections_with_gaps(
    session: Session,
    user_id: int | None = None,
    *,
    today: date | None = None,
    radarr_instance_id: int | None = None,
    sort: str = "rating",
) -> list[CollectionGap]:
    return [
        gap
        for gap in collection_gaps(
            session, user_id, today=today, radarr_instance_id=radarr_instance_id, sort=sort
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
