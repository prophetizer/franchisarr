"""The whole scan, as one callable: libraries, instances, then notify.

Shared by the scheduler and by anything that wants to trigger a full run, so a scheduled scan and
a manual one cannot drift apart -- which is the point of building it as one function rather than
letting the scheduler assemble its own sequence.

Order matters. Plex and TMDb first, so the snapshot is current; then the Radarr/Sonarr caches, so
"already have it" reflects reality; only then the diff, so the notification doesn't announce
films the user acquired an hour ago. Getting that backwards would produce a nightly message full
of things already dealt with, which is how people learn to ignore notifications.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from dataclasses import dataclass, field

from sqlmodel import Session, col, select

from app.clients.fanart_client import FanartClient
from app.clients.wikidata_client import WikidataClient
from app.clients.tmdb_client import TmdbClient
from app.models import ItemType, SeenGap, utcnow
from app.services import (
    media_server_service,
    instance_service,
    movie_gap_service,
    notifier,
    scan_service,
    sonarr_instance_service,
    tv_spinoff_service,
    upcoming_service,
)
from app.services import scan_state
from app.services.settings_service import SettingKey, get_setting

logger = logging.getLogger(__name__)


@dataclass
class ScanJobResult:
    movies: scan_service.ScanSummary | None = None
    shows: scan_service.ScanSummary | None = None
    instances_refreshed: int = 0
    report: notifier.ScanReport = field(default_factory=notifier.ScanReport)
    #: True when this was a first scan and the enrichment steps were left for a follow-up job.
    enrichment_deferred: bool = False
    notified: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _clients(
    session: Session,
) -> tuple[list[scan_service.ScanSource], TmdbClient | None, FanartClient | None, list[str]]:
    errors: list[str] = []
    tmdb_key = get_setting(session, SettingKey.TMDB_API_KEY)
    fanart_key = get_setting(session, SettingKey.FANART_API_KEY)
    sources = [
        scan_service.ScanSource(server, media_server_service.client_for(server))
        for server in media_server_service.enabled_servers(session)
    ]

    if not sources:
        errors.append(media_server_service.missing_message(session))
    if not tmdb_key:
        errors.append("No TMDb API key is configured.")
    if errors:
        return [], None, None, errors

    # Optional, and silently so: a missing fanart key is not a misconfiguration, it is the
    # default. It costs the franchise logos and nothing else.
    fanart = FanartClient(fanart_key) if fanart_key else None
    return sources, TmdbClient(tmdb_key), fanart, []


def _record_new(session: Session, item_type: str, found: dict[int, tuple[str, str]]) -> list[notifier.NewItem]:
    """Which of these gaps we haven't reported before, marking them reported as we go."""
    already = {
        row.tmdb_id
        for row in session.exec(
            select(SeenGap).where(col(SeenGap.item_type) == item_type)
        ).all()
    }

    fresh: list[notifier.NewItem] = []
    for tmdb_id, (title, detail) in sorted(found.items()):
        if tmdb_id in already:
            continue
        fresh.append(notifier.NewItem(item_type=item_type, tmdb_id=tmdb_id, title=title,
                                      detail=detail))
        session.add(
            SeenGap(item_type=item_type, tmdb_id=tmdb_id, title=title, first_seen_at=utcnow())
        )

    session.commit()
    return fresh


def has_ever_scanned(session: Session) -> bool:
    return session.exec(select(SeenGap).limit(1)).first() is not None


def run(
    session: Session, *, notify: bool = True, progress=None, force_refresh: bool = False
) -> ScanJobResult:
    """Do a complete scan and, if anything new turned up, send the webhook.

    The very first run never notifies. Everything missing on a fresh install is the state of the
    world rather than news, and a first message listing 227 films -- the real number on this
    developer's library -- is precisely how someone learns to mute the channel. The settings page
    primes explicitly when a schedule is switched on, but a schedule supplied through
    SCAN_SCHEDULE_CRON never passes through that page, so the guard belongs here too.
    """
    result = ScanJobResult()
    first_run = not has_ever_scanned(session)
    # A first scan does the core work only -- Plex, TMDb, collections -- so the pages fill in
    # minutes. Directors, spin-offs, continuations and franchises are minutes more on a real
    # library and follow in a second job, which run_in_background starts when this one ends.
    result.enrichment_deferred = first_run

    sources, tmdb, fanart, errors = _clients(session)
    if errors:
        result.errors.extend(errors)
        return result

    result.movies = scan_service.scan_movie_libraries(
        session, sources, tmdb, fanart=fanart, force_refresh=force_refresh,
        enrich=not first_run, progress=progress,
    )
    # Wikidata needs no key and no account, so spin-off discovery is simply always on.
    result.shows = scan_service.scan_show_libraries(
        session, sources, tmdb, wikidata=WikidataClient(),
        force_refresh=force_refresh, enrich=not first_run, progress=progress,
    )
    for summary in (result.movies, result.shows):
        # "No movie libraries are enabled" is a normal state for a TV-only install, not a fault.
        result.errors.extend(
            error for error in summary.errors if "libraries are enabled" not in error
        )

    if progress:
        progress("Checking Radarr and Sonarr", 0, 0)
    # Before the diff, so a film acquired since the last run isn't announced as missing.
    refreshed = instance_service.refresh_all(session) + sonarr_instance_service.refresh_all(session)
    result.instances_refreshed = sum(1 for r in refreshed if r.ok)
    result.errors.extend(r.error for r in refreshed if r.error)

    if progress:
        progress("Working out what's missing", 0, 0)

    movie_gaps: dict[int, tuple[str, str]] = {}
    for gap in movie_gap_service.collections_with_gaps(session):
        for movie in gap.missing:
            movie_gaps[movie.tmdb_id] = (movie.title, gap.name)

    show_gaps: dict[int, tuple[str, str]] = {
        suggestion.spinoff_tmdb_id: (suggestion.spinoff_name, suggestion.relationships)
        for suggestion in tv_spinoff_service.missing_spinoffs(session)
    }

    # Release-date news is diffed against the last scan rather than against "ever seen": a film
    # that gets a date is news once, and a film that gets a *new* date is news again.
    date_events = upcoming_service.record_and_diff(
        session, upcoming_service.upcoming_films(session)
    )

    result.report = notifier.ScanReport(
        new_movies=_record_new(session, ItemType.MOVIE.value, movie_gaps),
        new_shows=_record_new(session, ItemType.SHOW.value, show_gaps),
        release_dates=[
            notifier.NewItem(item_type=ItemType.MOVIE.value, tmdb_id=event.film.tmdb_id,
                             title=event.film.title, detail=event.detail)
            for event in date_events
        ],
    )

    if first_run and result.report.has_news:
        logger.info(
            "First scan: recorded %d existing gap(s) without notifying", result.report.total
        )
        notify = False

    if notify and result.report.has_news:
        url = get_setting(session, SettingKey.WEBHOOK_URL)
        if url:
            result.notified = notifier.send(
                url, result.report, get_setting(session, SettingKey.WEBHOOK_FORMAT) or "generic"
            )

    logger.info(
        "Scan finished: %s new (%d movies, %d shows), %d instance(s) refreshed",
        result.report.total, len(result.report.new_movies), len(result.report.new_shows),
        result.instances_refreshed,
    )
    return result


def prime_seen_gaps(session: Session) -> int:
    """Mark everything currently missing as already-reported, without notifying.

    Run once when a schedule is first configured. Otherwise the very first scheduled scan
    announces the entire backlog -- 227 films on a real library -- which is not news, it is the
    state of the world, and it teaches the recipient to mute the channel immediately.
    """
    movie_gaps = {
        movie.tmdb_id: (movie.title, gap.name)
        for gap in movie_gap_service.collections_with_gaps(session)
        for movie in gap.missing
    }
    show_gaps = {
        s.spinoff_tmdb_id: (s.spinoff_name, "") for s in tv_spinoff_service.missing_spinoffs(session)
    }

    primed = len(_record_new(session, ItemType.MOVIE.value, movie_gaps))
    primed += len(_record_new(session, ItemType.SHOW.value, show_gaps))
    logger.info("Marked %d existing gap(s) as already reported", primed)
    return primed


def run_enrichment(session: Session, *, progress=None, force_refresh: bool = False) -> list[str]:
    """The deferred half of a first scan: directors, spin-offs, continuations, franchises.

    Its own job with its own progress, so the page says what is happening and a scheduled scan
    cannot collide with it. Returns the errors, if any.
    """
    plex, tmdb, fanart, errors = _clients(session)
    if errors:
        return errors
    ttl = timedelta(0) if force_refresh else scan_service.cache_ttl(session)
    movies = scan_service.ScanSummary()
    scan_service.enrich_movies(session, tmdb, ttl, movies, progress)
    shows = scan_service.ScanSummary()
    if not movies.tmdb_auth_failed:
        scan_service.enrich_shows(session, WikidataClient(), tmdb, ttl, shows, progress)
    return [*movies.errors, *shows.errors]


def run_in_background(trigger: str = "manual", *, force_refresh: bool = False) -> bool:
    """Start a scan on a background thread. False means one is already running.

    `force_refresh` ignores the cache TTL and refetches every collection and show. It exists
    because the cache hides configuration changes: adding a fanart.tv key buys nothing until the
    collections are fetched again, which without this is a week away.

    A thread rather than a request: a scan of a real library is minutes of waiting on Plex and
    TMDb, and doing that inside a request leaves the page hanging until the proxy gives up.

    The thread opens its own session. Sessions are not safe to share across threads, and the
    request that started this one is long finished by the time the scan ends.
    """
    import threading

    from sqlmodel import Session as DbSession

    from app.db import get_engine

    if not scan_state.begin(trigger):
        return False

    def _work() -> None:
        deferred = False
        try:
            with DbSession(get_engine()) as session:
                result = run(session, notify=True, progress=scan_state.update,
                             force_refresh=force_refresh)
                deferred = result.enrichment_deferred
                summary = _describe(result)
                if deferred:
                    summary += (" Directors, spin-offs and franchises are being worked out now"
                                " -- a few minutes more, in the background.")
                scan_state.finish(summary, result.errors)
        except Exception as exc:  # noqa: BLE001
            # Anything escaping here would leave the state stuck on "running" forever, and the
            # button would never come back.
            logger.exception("Background scan failed")
            scan_state.fail(str(exc) or exc.__class__.__name__)
            return
        if deferred:
            _start_enrichment(force_refresh=force_refresh)

    threading.Thread(target=_work, name="franchisarr-scan", daemon=True).start()
    return True


def _start_enrichment(*, force_refresh: bool = False) -> bool:
    import threading

    from sqlmodel import Session as DbSession

    from app.db import get_engine

    if not scan_state.begin("enrichment"):
        return False

    def _work() -> None:
        try:
            with DbSession(get_engine()) as session:
                errors = run_enrichment(session, progress=scan_state.update,
                                        force_refresh=force_refresh)
                scan_state.finish("Directors, spin-offs and franchises are ready.", errors)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Background enrichment failed")
            scan_state.fail(str(exc) or exc.__class__.__name__)

    threading.Thread(target=_work, name="franchisarr-enrich", daemon=True).start()
    return True


def _describe(result: ScanJobResult) -> str:
    """A sentence for the page to show when the scan ends."""
    seen = (result.movies.items_seen if result.movies else 0) + (
        result.shows.items_seen if result.shows else 0
    )
    if not seen:
        return "Nothing to scan — no libraries are enabled."

    parts = [f"{seen:,} item{'' if seen == 1 else 's'} scanned"]
    if result.report.total:
        parts.append(f"{result.report.total} new since the last scan")
    return ", ".join(parts) + "."
