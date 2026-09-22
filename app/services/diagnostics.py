"""A redacted bundle for bug reports.

The first thing anyone asks about a matching report is "which version, which media server, how
big is the library, what didn't match" -- and the reporter rarely knows where to find any of it.
This is one download from Settings that answers all of it, safe to attach to a public issue:
the redacted config export (every credential blanked), library and cache counts, the titles that
failed to match or need review, the last scan's outcome, and the recent activity.

No secret goes in by construction (the config export is asked for its redacted form) and, as a
second lock, the finished JSON is passed through the logging redactor, which knows every credential
the app has been given. If a key were ever stored somewhere new and forgotten here, it still
comes out as the placeholder.
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone

from sqlmodel import Session, func, select

from app import __version__
from app.config import get_settings
from app.logging_config import redact
from app.models import (
    ActivityLogEntry, CrossMediaMapping, DirectorFilm, DismissedItem, Franchise, IncludedLibrary,
    LibraryItem, MediaServer, MovieDirector, RadarrInstance, SonarrInstance, SpinoffMapping,
    TmdbCollection, TmdbMovie, TmdbShow,
)
from app.services import config_backup, scan_state

#: How many unmatched / needs-review titles to include. Enough to see a pattern, not a dump of
#: someone's whole library.
SAMPLE = 200


def _count(session: Session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for clause in where:
        stmt = stmt.where(clause)
    return session.exec(stmt).one()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _library_items(session: Session, *where) -> list[dict]:
    rows = session.exec(
        select(LibraryItem).where(*where).order_by(LibraryItem.item_type, LibraryItem.title).limit(SAMPLE)
    ).all()
    return [
        {
            "type": r.item_type, "title": r.title, "year": r.year, "library": r.library_key,
            "tmdb_id": r.tmdb_id, "imdb_id": r.imdb_id, "tvdb_id": r.tvdb_id,
            "match_source": r.match_source, "confidence": r.match_confidence,
        }
        for r in rows
    ]


def build(session: Session) -> dict:
    """Everything a maintainer needs, nothing a reporter would regret posting."""
    env = get_settings()
    scan = scan_state.current()

    by_type = {
        item_type: n for item_type, n in session.exec(
            select(LibraryItem.item_type, func.count()).group_by(LibraryItem.item_type)
        ).all()
    }
    by_source = {
        source: n for source, n in session.exec(
            select(LibraryItem.match_source, func.count()).group_by(LibraryItem.match_source)
        ).all()
    }
    mappings_by_source = {
        source: n for source, n in session.exec(
            select(SpinoffMapping.source, func.count()).group_by(SpinoffMapping.source)
        ).all()
    }

    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "franchisarr": __version__,
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.machine()}",
        "base_url": env.base_url,
        "config": config_backup.export_config(session, redact=True),
        "media_servers": [
            {"name": s.name, "kind": s.kind, "libraries": [
                {"key": lib.library_key, "name": lib.library_name, "type": lib.library_type}
                for lib in session.exec(select(IncludedLibrary).where(IncludedLibrary.server_id == s.id)).all()
            ]}
            for s in session.exec(select(MediaServer)).all()
        ],
        "instances": {
            "radarr": _count(session, RadarrInstance),
            "sonarr": _count(session, SonarrInstance),
        },
        "library": {
            "items_by_type": by_type,
            "items_by_match_source": by_source,
            "needs_review": _count(session, LibraryItem, LibraryItem.needs_review == True),  # noqa: E712
            "unmatched": _count(session, LibraryItem, LibraryItem.tmdb_id == None),  # noqa: E711
        },
        "cache": {
            "movies": _count(session, TmdbMovie),
            "shows": _count(session, TmdbShow),
            "collections": _count(session, TmdbCollection),
            "spinoff_mappings_by_source": mappings_by_source,
            "cross_media_mappings": _count(session, CrossMediaMapping),
            "franchises": _count(session, Franchise),
            "directors": session.exec(select(func.count(MovieDirector.person_id.distinct()))).one(),
            "director_films": _count(session, DirectorFilm),
            "dismissed": _count(session, DismissedItem),
        },
        "last_scan": {
            "running": scan.running,
            "trigger": scan.trigger,
            "started_at": _iso(scan.started_at),
            "finished_at": _iso(scan.finished_at),
            "summary": scan.summary,
            "errors": list(scan.errors),
        },
        # The titles that matter for a matching report, and what the matcher made of them.
        "unmatched_sample": _library_items(session, LibraryItem.tmdb_id == None),  # noqa: E711
        "needs_review_sample": _library_items(session, LibraryItem.needs_review == True),  # noqa: E712
        "recent_activity": [
            {
                "at": _iso(e.timestamp), "type": e.item_type, "tmdb_id": e.tmdb_id, "title": e.title,
                "instance_id": e.instance_id, "trigger": e.trigger_source,
            }
            for e in session.exec(
                select(ActivityLogEntry).order_by(ActivityLogEntry.timestamp.desc()).limit(25)
            ).all()
        ],
    }
    return document


def render(session: Session) -> str:
    """The bundle as JSON text, with every registered secret replaced -- the second lock."""
    return redact(json.dumps(build(session), indent=2, default=str))
