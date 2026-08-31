"""Walk the enabled Plex libraries, resolve items to TMDb, and cache the result.

Scanning is deliberately separate from viewing gaps (technical challenge #7). A page load reads
the cached snapshot; only an explicit scan or the scheduler talks to Plex and TMDb. On a library
of a few thousand films a full scan is minutes of TMDb calls, which is fine once a week and
absurd once a page load.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, col, select

from app.clients.plex_client import PlexClient, PlexClientError
from app.clients.tmdb_client import TmdbAuthError, TmdbClient, TmdbError, TmdbNotFound
from app.models import (
    ItemType,
    LibraryItem,
    MatchSource,
    TmdbCollection,
    TmdbCollectionMovie,
    TmdbMovie,
    utcnow,
)
from app.services import library_service
from app.services.matcher import match_movie, match_show
from app.services.settings_service import SettingKey, get_int_setting

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_DAYS = 7

#: Rows written per transaction while walking a library. Large enough to keep the commit overhead
#: negligible, small enough that a scan interrupted halfway leaves useful progress behind.
COMMIT_BATCH = 500


@dataclass
class ScanSummary:
    libraries_scanned: int = 0
    items_seen: int = 0
    matched: int = 0
    needs_review: int = 0
    unmatched: int = 0
    removed: int = 0
    collections_found: int = 0
    tmdb_lookups: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def cache_ttl(session: Session) -> timedelta:
    return timedelta(
        days=get_int_setting(session, SettingKey.TMDB_CACHE_TTL_DAYS, DEFAULT_CACHE_TTL_DAYS)
    )


def _is_fresh(fetched_at: datetime, ttl: timedelta) -> bool:
    return utcnow() - _as_utc(fetched_at) < ttl


def scan_movie_libraries(
    session: Session,
    plex: PlexClient,
    tmdb: TmdbClient,
    *,
    force_refresh: bool = False,
) -> ScanSummary:
    """Refresh the snapshot for every enabled movie library, then cache their collections."""
    summary = ScanSummary()
    ttl = timedelta(0) if force_refresh else cache_ttl(session)
    started = utcnow()

    libraries = [lib for lib in library_service.enabled_libraries(session)
                 if lib.library_type == ItemType.MOVIE.value]
    if not libraries:
        summary.errors.append("No movie libraries are enabled.")
        return summary

    for library in libraries:
        try:
            items = list(plex.iter_movies(library.plex_library_key))
        except PlexClientError as exc:
            logger.warning("Skipping library %r: %s", library.plex_library_name, exc)
            summary.errors.append(f"{library.plex_library_name}: {exc}")
            continue

        summary.libraries_scanned += 1

        # Every existing row for this library is loaded once, up front. Querying per item
        # instead is quadratic: SQLAlchemy autoflushes the pending objects before each query, so
        # by the three-thousandth film every lookup flushes thousands of rows. Worth perhaps 15%
        # of a 3,400-film scan today, but the cost grows faster than linearly, so it matters more
        # on the larger libraries a public tool will meet than it does here.
        existing = {
            row.rating_key: row
            for row in session.exec(
                select(LibraryItem).where(
                    col(LibraryItem.plex_library_key) == library.plex_library_key
                )
            ).all()
        }

        for index, item in enumerate(items, start=1):
            summary.items_seen += 1
            _upsert_item(session, library.plex_library_key, item, tmdb, summary, existing)
            if index % COMMIT_BATCH == 0:
                session.commit()

        session.commit()
        summary.removed += _prune_missing(session, library.plex_library_key, started)

    summary.collections_found = _cache_collections(session, tmdb, ttl, summary)
    return summary


def scan_show_libraries(
    session: Session,
    plex: PlexClient,
    tmdb: TmdbClient,
    *,
    force_refresh: bool = False,
) -> ScanSummary:
    """Refresh the snapshot for every enabled TV library, and cache each show's TMDb details.

    Deliberately a sibling of the movie scan rather than a generalisation of it: the two share
    the snapshot table but almost nothing else, since shows have no collections to walk and their
    spin-off relationships come from a curated mapping instead of TMDb.
    """
    summary = ScanSummary()
    ttl = timedelta(0) if force_refresh else cache_ttl(session)
    started = utcnow()

    libraries = [
        lib for lib in library_service.enabled_libraries(session)
        if lib.library_type == ItemType.SHOW.value
    ]
    if not libraries:
        summary.errors.append("No TV libraries are enabled.")
        return summary

    for library in libraries:
        try:
            items = list(plex.iter_shows(library.plex_library_key))
        except PlexClientError as exc:
            logger.warning("Skipping library %r: %s", library.plex_library_name, exc)
            summary.errors.append(f"{library.plex_library_name}: {exc}")
            continue

        summary.libraries_scanned += 1
        existing = {
            row.rating_key: row
            for row in session.exec(
                select(LibraryItem).where(
                    col(LibraryItem.plex_library_key) == library.plex_library_key
                )
            ).all()
        }

        for index, item in enumerate(items, start=1):
            summary.items_seen += 1
            _upsert_item(
                session, library.plex_library_key, item, tmdb, summary, existing,
                item_type=ItemType.SHOW.value,
            )
            if index % COMMIT_BATCH == 0:
                session.commit()

        session.commit()
        summary.removed += _prune_missing(session, library.plex_library_key, started)

    _cache_shows(session, tmdb, ttl, summary)
    return summary


def _cache_shows(
    session: Session, tmdb: TmdbClient, ttl: timedelta, summary: ScanSummary
) -> None:
    """Fetch and cache details for each owned show, so spin-off views have names to display."""
    from app.models import TmdbShow
    from app.services.tv_spinoff_service import cache_show

    owned = {
        row.tmdb_id
        for row in session.exec(
            select(LibraryItem).where(
                col(LibraryItem.item_type) == ItemType.SHOW.value,
                col(LibraryItem.tmdb_id).is_not(None),
                col(LibraryItem.needs_review) == False,  # noqa: E712 - SQL, not Python
            )
        ).all()
        if row.tmdb_id
    }

    for tmdb_id in sorted(owned):
        cached = session.get(TmdbShow, tmdb_id)
        if cached is not None and _is_fresh(cached.fetched_at, ttl):
            continue
        try:
            cache_show(session, tmdb.get_show(tmdb_id))
        except TmdbNotFound:
            continue
        except TmdbAuthError as exc:
            # Same reasoning as the movie scan: a rejected key stays rejected.
            summary.errors.append(str(exc))
            logger.error("Stopping TMDb enrichment: %s", exc)
            return
        except TmdbError as exc:
            summary.errors.append(str(exc))
            continue
        summary.tmdb_lookups += 1


def _upsert_item(
    session: Session,
    library_key: str,
    item,
    tmdb: TmdbClient,
    summary: ScanSummary,
    existing: dict[str, LibraryItem],
    item_type: str = ItemType.MOVIE.value,
) -> LibraryItem:
    row = existing.get(item.rating_key)

    # Only spend a TMDb call when we don't already have an answer for this item. A re-scan of an
    # unchanged library should cost Plex requests and nothing else.
    already_resolved = row is not None and row.tmdb_id is not None and not row.needs_review
    if already_resolved:
        result = None
    else:
        matcher = match_show if item_type == ItemType.SHOW.value else match_movie
        result = matcher(item, tmdb)
        if result.source not in (MatchSource.GUID.value, MatchSource.NONE.value):
            summary.tmdb_lookups += 1

    if row is None:
        row = LibraryItem(plex_library_key=library_key, rating_key=item.rating_key)
        existing[item.rating_key] = row

    row.title = item.title
    row.year = item.year
    row.item_type = item_type
    row.imdb_id = item.external_ids.imdb_id
    row.tvdb_id = item.external_ids.tvdb_id
    row.last_seen_at = utcnow()

    if result is not None:
        row.tmdb_id = result.tmdb_id
        row.match_source = result.source
        row.match_confidence = result.confidence
        row.needs_review = result.needs_review
        row.updated_at = utcnow()
        if result.reason and not result.matched:
            logger.debug("Unmatched %r (%s): %s", item.title, item.year, result.reason)

    if row.tmdb_id is None:
        summary.unmatched += 1
    elif row.needs_review:
        summary.needs_review += 1
    else:
        summary.matched += 1

    session.add(row)
    return row


def _prune_missing(session: Session, library_key: str, started: datetime) -> int:
    """Drop rows for items that were not seen in this pass -- they left the Plex library."""
    stale = session.exec(
        select(LibraryItem).where(
            col(LibraryItem.plex_library_key) == library_key,
            col(LibraryItem.last_seen_at) < started,
        )
    ).all()
    for row in stale:
        session.delete(row)
    if stale:
        session.commit()
        logger.info("Removed %d item(s) no longer in library %s", len(stale), library_key)
    return len(stale)


def _cache_collections(
    session: Session, tmdb: TmdbClient, ttl: timedelta, summary: ScanSummary
) -> int:
    """Look up which collection each owned film belongs to, then cache those collections."""
    owned_ids = {
        row.tmdb_id
        for row in session.exec(
            select(LibraryItem).where(
                col(LibraryItem.tmdb_id).is_not(None),
                col(LibraryItem.item_type) == ItemType.MOVIE.value,
                col(LibraryItem.needs_review) == False,  # noqa: E712 - SQL, not Python
            )
        ).all()
        if row.tmdb_id
    }

    collection_ids: set[int] = set()
    for tmdb_id in sorted(owned_ids):
        cached = session.get(TmdbMovie, tmdb_id)
        if cached is None or not _is_fresh(cached.fetched_at, ttl):
            try:
                details = tmdb.get_movie(tmdb_id)
            except TmdbNotFound:
                continue
            except TmdbAuthError as exc:
                # A rejected key will be rejected for every remaining film. Carrying on would
                # mean thousands of pointless requests, thousands of identical errors, and
                # minutes of waiting to be told one thing that was knowable at the first call.
                summary.errors.append(str(exc))
                logger.error("Stopping TMDb enrichment: %s", exc)
                return 0
            except TmdbError as exc:
                summary.errors.append(str(exc))
                logger.warning("TMDb movie lookup failed for %s: %s", tmdb_id, exc)
                continue

            summary.tmdb_lookups += 1
            cached = TmdbMovie(
                tmdb_id=details.tmdb_id,
                title=details.title,
                release_year=details.year,
                collection_id=details.collection_id,
                fetched_at=utcnow(),
            )
            session.merge(cached)
            session.commit()

        if cached.collection_id:
            collection_ids.add(cached.collection_id)

    for collection_id in sorted(collection_ids):
        try:
            _cache_collection(session, tmdb, collection_id, ttl, summary)
        except TmdbAuthError as exc:
            summary.errors.append(str(exc))
            logger.error("Stopping TMDb enrichment: %s", exc)
            break

    return len(collection_ids)


def _cache_collection(
    session: Session,
    tmdb: TmdbClient,
    collection_id: int,
    ttl: timedelta,
    summary: ScanSummary,
) -> None:
    existing = session.get(TmdbCollection, collection_id)
    if existing is not None and _is_fresh(existing.fetched_at, ttl):
        return

    try:
        details = tmdb.get_collection(collection_id)
    except TmdbNotFound:
        return
    except TmdbAuthError:
        raise
    except TmdbError as exc:
        summary.errors.append(str(exc))
        logger.warning("TMDb collection lookup failed for %s: %s", collection_id, exc)
        return

    summary.tmdb_lookups += 1
    session.merge(
        TmdbCollection(
            tmdb_collection_id=details.tmdb_collection_id,
            name=details.name,
            fetched_at=utcnow(),
        )
    )

    # Members are replaced wholesale: a film removed from a collection upstream must disappear
    # here too. Exclusions key on TMDb ids, so they survive this (technical challenge #13).
    for row in session.exec(
        select(TmdbCollectionMovie).where(col(TmdbCollectionMovie.collection_id) == collection_id)
    ).all():
        session.delete(row)

    for position, movie in enumerate(details.movies):
        session.add(
            TmdbCollectionMovie(
                collection_id=details.tmdb_collection_id,
                tmdb_movie_id=movie.tmdb_id,
                title=movie.title,
                release_year=movie.year,
                release_date=movie.release_date,
                position=position,
            )
        )
    session.commit()
