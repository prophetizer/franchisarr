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

from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.clients.media_server import MediaServerClient, MediaServerError
from app.clients.fanart_client import FanartAuthError, FanartClient, FanartError
from app.clients.wikidata_client import WikidataClient, WikidataError
from app.clients.tmdb_client import TmdbAuthError, TmdbClient, TmdbError, TmdbNotFound
from app.models import (
    ItemType,
    LibraryItem,
    MatchSource,
    TmdbCollection,
    TmdbCollectionMovie,
    TmdbMovie,
    TmdbShow,
    utcnow,
)
from app.services import library_service
from app.services.matcher import match_movie, match_show

#: Called as (phase, processed, total) while a scan runs. Reporting through a callback rather
#: than reaching for the live scan state keeps this module usable on its own -- the CLI and the
#: tests both drive it without any background machinery.
ProgressHook = "Callable[[str, int, int], None] | None"
from app.services.settings_service import SettingKey, get_int_setting

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_DAYS = 7

#: Rows written per transaction while walking a library. Large enough to keep the commit overhead
#: negligible, small enough that a scan interrupted halfway leaves useful progress behind.
COMMIT_BATCH = 500

#: How often to report progress. Every item would be thousands of lock acquisitions for a number
#: nobody can read changing that fast.
PROGRESS_EVERY = 25


@dataclass
class ScanSummary:
    libraries_scanned: int = 0
    items_seen: int = 0
    matched: int = 0
    needs_review: int = 0
    unmatched: int = 0
    removed: int = 0
    collections_found: int = 0
    #: Spin-off relations discovered or refreshed from Wikidata.
    spinoffs_found: int = 0
    #: Set once TMDb has rejected the key. Every later step that would call TMDb checks it: a
    #: rejected key is rejected for every remaining request, and the point of stopping is to
    #: stop -- not to stop one step and let the next one make three thousand doomed calls.
    tmdb_auth_failed: bool = False
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
    plex: MediaServerClient,
    tmdb: TmdbClient,
    *,
    fanart: FanartClient | None = None,
    force_refresh: bool = False,
    enrich: bool = True,
    progress=None,
) -> ScanSummary:
    """Refresh the snapshot for every enabled movie library, then cache their collections.

    `enrich=False` stops after the collections -- the part the Collections page needs -- and
    leaves directors to `enrich_movies`. A first scan uses that split so the pages fill in
    minutes rather than after every film's credits have been read.
    """
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
            items = list(plex.iter_movies(library.library_key))
        except MediaServerError as exc:
            logger.warning("Skipping library %r: %s", library.library_name, exc)
            summary.errors.append(f"{library.library_name}: {exc}")
            continue

        summary.libraries_scanned += 1

        # Every existing row for this library is loaded once, up front. Querying per item
        # instead is quadratic: SQLAlchemy autoflushes the pending objects before each query, so
        # by the three-thousandth film every lookup flushes thousands of rows. Worth perhaps 15%
        # of a 3,400-film scan today, but the cost grows faster than linearly, so it matters more
        # on the larger libraries a public tool will meet than it does here.
        existing = {
            row.item_key: row
            for row in session.exec(
                select(LibraryItem).where(
                    col(LibraryItem.library_key) == library.library_key
                )
            ).all()
        }

        for index, item in enumerate(items, start=1):
            summary.items_seen += 1
            _upsert_item(session, library.library_key, item, tmdb, summary, existing)
            if index % COMMIT_BATCH == 0:
                session.commit()
            if progress and index % PROGRESS_EVERY == 0:
                progress(f"Reading {library.library_name}", index, len(items))

        session.commit()
        summary.removed += _prune_missing(session, library.library_key, started)

    summary.collections_found = _cache_collections(
        session, tmdb, ttl, summary, progress, fanart=fanart
    )
    if enrich and not summary.tmdb_auth_failed:
        enrich_movies(session, tmdb, ttl, summary, progress)
    return summary


def enrich_movies(
    session: Session, tmdb: TmdbClient, ttl: timedelta, summary: ScanSummary, progress=None
) -> None:
    """The film-side enrichment: directors. Touches every owned film -- 3,400 credits requests
    on a first run -- so it is the step a first scan defers. A failure costs only the Directors
    page."""
    from app.services import director_service

    try:
        director_service.discover(session, tmdb, ttl=ttl, progress=progress)
    except TmdbAuthError as exc:
        summary.errors.append(str(exc))
        summary.tmdb_auth_failed = True
    except TmdbError as exc:
        summary.errors.append(f"Director lookup failed: {exc}")


def scan_show_libraries(
    session: Session,
    plex: MediaServerClient,
    tmdb: TmdbClient,
    *,
    wikidata: WikidataClient | None = None,
    force_refresh: bool = False,
    enrich: bool = True,
    progress=None,
) -> ScanSummary:
    """Refresh the snapshot for every enabled TV library, and cache each show's TMDb details.

    `enrich=False` stops after the show cache and leaves spin-offs, continuations and franchises
    to `enrich_shows`, for the same reason the movie scan defers directors.

    Deliberately a sibling of the movie scan rather than a generalisation of it: the two share
    the snapshot table but almost nothing else, since shows have no collections to walk and their
    spin-off relationships come from Wikidata and the user rather than from TMDb.
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
            items = list(plex.iter_shows(library.library_key))
        except MediaServerError as exc:
            logger.warning("Skipping library %r: %s", library.library_name, exc)
            summary.errors.append(f"{library.library_name}: {exc}")
            continue

        summary.libraries_scanned += 1
        existing = {
            row.item_key: row
            for row in session.exec(
                select(LibraryItem).where(
                    col(LibraryItem.library_key) == library.library_key
                )
            ).all()
        }

        for index, item in enumerate(items, start=1):
            summary.items_seen += 1
            _upsert_item(
                session, library.library_key, item, tmdb, summary, existing,
                item_type=ItemType.SHOW.value,
            )
            if index % COMMIT_BATCH == 0:
                session.commit()
            if progress and index % PROGRESS_EVERY == 0:
                progress(f"Reading {library.library_name}", index, len(items))

        session.commit()
        summary.removed += _prune_missing(session, library.library_key, started)

    _cache_shows(session, tmdb, ttl, summary, progress)
    if enrich and wikidata is not None:
        enrich_shows(session, wikidata, tmdb, ttl, summary, progress)
    return summary


def enrich_shows(
    session: Session, wikidata: WikidataClient, tmdb: TmdbClient, ttl: timedelta,
    summary: ScanSummary, progress=None,
) -> None:
    """The TV-side enrichment, all from Wikidata: spin-offs, continuations across media, and
    franchises. The franchise step alone is minutes on a first run."""
    _discover_spinoffs(session, wikidata, tmdb, ttl, summary, progress)


def _discover_spinoffs(
    session: Session,
    wikidata: WikidataClient,
    tmdb: TmdbClient,
    ttl: timedelta,
    summary: ScanSummary,
    progress=None,
) -> None:
    """Ask Wikidata which of the library's shows have spin-offs, and record what it says.

    Never fatal. The scan's job is the library snapshot; this is enrichment on top of it, so a
    Wikidata outage costs the suggestions and nothing else.
    """
    from app.services import tv_spinoff_service

    owned = sorted(tv_spinoff_service.owned_show_ids(session))
    if not owned:
        return

    if progress:
        progress("Looking for spin-offs", 0, len(owned))

    try:
        relations = wikidata.spinoffs_for(owned)
    except WikidataError as exc:
        # Worth recording, not worth failing over.
        logger.warning("Spin-off discovery skipped: %s", exc)
        summary.errors.append(f"Spin-off lookup failed: {exc}")
        return

    # A suggestion needs a name and a year to be worth showing, and those come from TMDb.
    for index, relation in enumerate(relations, start=1):
        if progress and index % PROGRESS_EVERY == 0:
            progress("Looking for spin-offs", index, len(relations))
        cached = session.get(TmdbShow, relation.spinoff_tmdb_id)
        if cached is not None and _is_fresh(cached.fetched_at, ttl):
            continue
        try:
            tv_spinoff_service.cache_show(session, tmdb.get_show(relation.spinoff_tmdb_id))
            summary.tmdb_lookups += 1
        except TmdbNotFound:
            continue
        except TmdbAuthError as exc:
            summary.errors.append(str(exc))
            summary.tmdb_auth_failed = True
            logger.error("Stopping TMDb enrichment: %s", exc)
            break
        except TmdbError as exc:
            logger.debug("Could not cache spin-off %s: %s", relation.spinoff_tmdb_id, exc)
            continue

    added, refreshed = tv_spinoff_service.import_wikidata_relations(session, relations)
    summary.spinoffs_found = added + refreshed

    # Across media too: films for owned shows, shows for owned films. Runs over the whole film
    # library, so it is the longest Wikidata step -- about three minutes on 3,400 films at the
    # limiter's pace -- and it is enrichment, so it comes last and a failure costs only itself.
    from app.services import cross_media_service, movie_gap_service

    movie_ids = sorted(movie_gap_service.owned_tmdb_ids(session))
    if progress:
        progress("Looking across films and TV", 0, len(owned) + len(movie_ids))
    try:
        cross = wikidata.cross_media_for(show_ids=owned, movie_ids=movie_ids)
    except WikidataError as exc:
        logger.warning("Cross-media discovery skipped: %s", exc)
        summary.errors.append(f"Cross-media lookup failed: {exc}")
        return
    try:
        cross_media_service.import_relations(session, cross, tmdb)
    except TmdbAuthError as exc:
        summary.errors.append(str(exc))
        summary.tmdb_auth_failed = True
        return

    from app.services import franchise_service

    try:
        franchise_service.discover(session, wikidata, tmdb, ttl=ttl, progress=progress)
    except WikidataError as exc:
        logger.warning("Franchise discovery skipped: %s", exc)
        summary.errors.append(f"Franchise lookup failed: {exc}")
    except TmdbAuthError as exc:
        summary.errors.append(str(exc))
        summary.tmdb_auth_failed = True


def _cache_shows(
    session: Session, tmdb: TmdbClient, ttl: timedelta, summary: ScanSummary, progress=None
) -> None:
    """Fetch and cache details for each owned show, so spin-off views have names to display."""
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

    for index, tmdb_id in enumerate(sorted(owned), start=1):
        if progress and index % PROGRESS_EVERY == 0:
            progress("Looking shows up on TMDb", index, len(owned))
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
            summary.tmdb_auth_failed = True
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
    row = existing.get(item.item_key)

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
        row = LibraryItem(library_key=library_key, item_key=item.item_key)
        existing[item.item_key] = row

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
            col(LibraryItem.library_key) == library_key,
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
    session: Session,
    tmdb: TmdbClient,
    ttl: timedelta,
    summary: ScanSummary,
    progress=None,
    *,
    fanart: FanartClient | None = None,
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
    for index, tmdb_id in enumerate(sorted(owned_ids), start=1):
        if progress and index % PROGRESS_EVERY == 0:
            progress("Looking films up on TMDb", index, len(owned_ids))
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
                summary.tmdb_auth_failed = True
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

    for index, collection_id in enumerate(sorted(collection_ids), start=1):
        if progress:
            progress("Fetching collections", index, len(collection_ids))
        try:
            if not _cache_collection(session, tmdb, collection_id, ttl, summary, fanart=fanart):
                # The fanart key was rejected, and it will be rejected for every remaining
                # collection too. Artwork is optional, so the scan carries on without it rather
                # than failing -- but it stops asking.
                fanart = None
        except TmdbAuthError as exc:
            summary.errors.append(str(exc))
            summary.tmdb_auth_failed = True
            logger.error("Stopping TMDb enrichment: %s", exc)
            break

    return len(collection_ids)


def _cache_collection(
    session: Session,
    tmdb: TmdbClient,
    collection_id: int,
    ttl: timedelta,
    summary: ScanSummary,
    *,
    fanart: FanartClient | None = None,
) -> bool:
    """Cache one collection. Returns False only to say the fanart key is unusable."""
    existing = session.get(TmdbCollection, collection_id)
    if existing is not None and _is_fresh(existing.fetched_at, ttl):
        return True

    try:
        details = tmdb.get_collection(collection_id)
    except TmdbNotFound:
        return True
    except TmdbAuthError:
        raise
    except TmdbError as exc:
        summary.errors.append(str(exc))
        logger.warning("TMDb collection lookup failed for %s: %s", collection_id, exc)
        return True

    summary.tmdb_lookups += 1
    fanart_usable = True
    logo_url = None
    if fanart is not None:
        logo_url, fanart_usable = _collection_logo(fanart, details, summary)

    session.merge(
        TmdbCollection(
            tmdb_collection_id=details.tmdb_collection_id,
            name=details.name,
            poster_path=details.poster_path,
            backdrop_path=details.backdrop_path,
            logo_url=logo_url,
            fetched_at=utcnow(),
        )
    )

    # Members are replaced wholesale: a film removed from a collection upstream must disappear
    # here too. Exclusions key on TMDb ids, so they survive this (technical challenge #13).
    #
    # A bulk delete, for the reason instance_service documents: SQLAlchemy does not guarantee
    # DELETE-before-INSERT ordering between different objects in one flush, so an ORM delete loop
    # followed by adds fails the (collection_id, tmdb_movie_id) unique constraint as soon as the
    # two sets overlap -- which is always, since a collection's members are what barely change.
    # This only ever runs on a refetch, so it stayed invisible until a cache went stale.
    session.exec(
        delete(TmdbCollectionMovie).where(
            col(TmdbCollectionMovie.collection_id) == collection_id
        )
    )
    session.flush()

    for position, movie in enumerate(details.movies):
        session.add(
            TmdbCollectionMovie(
                collection_id=details.tmdb_collection_id,
                tmdb_movie_id=movie.tmdb_id,
                title=movie.title,
                release_year=movie.year,
                release_date=movie.release_date,
                poster_path=movie.poster_path,
                vote_average=movie.vote_average,
                vote_count=movie.vote_count,
                popularity=movie.popularity,
                position=position,
            )
        )
    session.commit()
    return fanart_usable


def _collection_logo(
    fanart: FanartClient, details, summary: ScanSummary
) -> tuple[str | None, bool]:
    """Find a franchise logo for a collection, via its earliest film.

    fanart.tv has no collection endpoint -- it is keyed per film -- so this leans on the fact
    that a franchise's wordmark is established by its first entry and reused by the sequels.
    Measured on 70 of the real library's collections, the anchor film had a logo every time.

    Returns the logo and whether the fanart key is still worth using.
    """
    anchor = min(
        details.movies,
        key=lambda movie: (movie.year is None, movie.year or 0),
        default=None,
    )
    if anchor is None:
        return None, True

    try:
        art = fanart.get_movie_art(anchor.tmdb_id)
    except FanartAuthError as exc:
        summary.errors.append(str(exc))
        logger.error("Disabling fanart.tv artwork for this scan: %s", exc)
        return None, False
    except FanartError as exc:
        # Artwork is decoration. A collection with no logo is a heading in text, which is what
        # every install without a fanart key gets anyway.
        logger.debug("fanart.tv lookup failed for %s: %s", anchor.tmdb_id, exc)
        return None, True

    return art.logo_url, True
