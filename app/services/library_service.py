"""Which Plex libraries Franchisarr looks at.

New libraries arrive disabled. A fresh install scanning everything it finds would go looking for
franchise gaps in home videos, concert rips and calibration clips -- and the plan is explicit that
the user chooses (docs/DESIGN.md: "not an automatic 'every movie/TV library' scan"). Re-syncing
never overrides a choice already made.
"""

from __future__ import annotations

import logging

from sqlmodel import Session, col, select

from app.clients.plex_client import PlexClient, PlexLibrary
from app.models import IncludedLibrary

logger = logging.getLogger(__name__)


def list_libraries(session: Session) -> list[IncludedLibrary]:
    return list(
        session.exec(select(IncludedLibrary).order_by(col(IncludedLibrary.library_name))).all()
    )


def enabled_libraries(session: Session) -> list[IncludedLibrary]:
    return [library for library in list_libraries(session) if library.enabled]


def sync_libraries(session: Session, libraries: list[PlexLibrary]) -> list[IncludedLibrary]:
    """Reconcile the stored library list with what Plex reports.

    Existing rows keep their `enabled` choice and refresh their name, so renaming a library in
    Plex doesn't silently drop it from scans. Libraries that have disappeared from Plex are
    removed -- keeping them would offer the user checkboxes for things that no longer exist.
    """
    existing = {library.library_key: library for library in list_libraries(session)}
    seen: set[str] = set()

    for library in libraries:
        seen.add(library.key)
        row = existing.get(library.key)
        if row is None:
            session.add(
                IncludedLibrary(
                    library_key=library.key,
                    library_name=library.title,
                    library_type=library.library_type,
                    enabled=False,
                )
            )
            logger.info("Discovered Plex library %r (disabled until selected)", library.title)
        else:
            row.library_name = library.title
            row.library_type = library.library_type
            session.add(row)

    for key, row in existing.items():
        if key not in seen:
            logger.info("Library %r no longer exists on the media server; removing", row.library_name)
            session.delete(row)

    session.commit()
    return list_libraries(session)


def sync_from_plex(session: Session, client: PlexClient) -> list[IncludedLibrary]:
    return sync_libraries(session, client.list_libraries())


def set_enabled_libraries(session: Session, keys: list[str]) -> list[IncludedLibrary]:
    """Replace the selection wholesale -- the form posts every ticked box, so anything absent
    was deliberately unticked."""
    wanted = set(keys)
    for row in list_libraries(session):
        row.enabled = row.library_key in wanted
        session.add(row)
    session.commit()

    chosen = enabled_libraries(session)
    logger.info("Library selection updated: %d enabled", len(chosen))
    return chosen


def has_selection(session: Session) -> bool:
    """Whether the user has chosen at least one library -- drives the post-login setup step."""
    return bool(enabled_libraries(session))
