"""Which libraries, on which servers, Franchisarr looks at.

New libraries arrive disabled. A fresh install scanning everything it finds would go looking for
franchise gaps in home videos, concert rips and calibration clips -- and the plan is explicit that
the user chooses (docs/DESIGN.md: "not an automatic 'every movie/TV library' scan"). Re-syncing
never overrides a choice already made.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlmodel import Session, col, select

from app.clients.media_server import MediaLibrary, MediaServerClient, MediaServerError
from app.models import IncludedLibrary, MediaServer

logger = logging.getLogger(__name__)


def list_libraries(session: Session, server_id: int | None = None) -> list[IncludedLibrary]:
    query = select(IncludedLibrary).order_by(col(IncludedLibrary.library_name))
    if server_id is not None:
        query = query.where(col(IncludedLibrary.server_id) == server_id)
    return list(session.exec(query).all())


def enabled_libraries(session: Session, server_id: int | None = None) -> list[IncludedLibrary]:
    return [library for library in list_libraries(session, server_id) if library.enabled]


def sync_libraries(
    session: Session, server: MediaServer, libraries: list[MediaLibrary]
) -> list[IncludedLibrary]:
    """Reconcile one server's stored library list with what it reports.

    Existing rows keep their `enabled` choice and refresh their name, so renaming a library on
    the server doesn't silently drop it from scans. Libraries that have disappeared are removed --
    keeping them would offer the user checkboxes for things that no longer exist.
    """
    existing = {library.library_key: library for library in list_libraries(session, server.id)}
    seen: set[str] = set()

    for library in libraries:
        seen.add(library.key)
        row = existing.get(library.key)
        if row is None:
            session.add(
                IncludedLibrary(
                    server_id=server.id,
                    library_key=library.key,
                    library_name=library.title,
                    library_type=library.library_type,
                    enabled=False,
                )
            )
            logger.info("Discovered library %r on %s (disabled until selected)",
                        library.title, server.name)
        else:
            row.library_name = library.title
            row.library_type = library.library_type
            session.add(row)

    for key, row in existing.items():
        if key not in seen:
            logger.info("Library %r no longer exists on %s; removing", row.library_name, server.name)
            session.delete(row)

    session.commit()
    return list_libraries(session, server.id)


def sync_from_server(
    session: Session, server: MediaServer, client: MediaServerClient
) -> list[IncludedLibrary]:
    return sync_libraries(session, server, client.list_libraries())


@dataclass
class ServerLibraries:
    """One server's libraries for the selection page, with the error if it couldn't be asked."""

    server: MediaServer
    libraries: list[IncludedLibrary] = field(default_factory=list)
    error: str | None = None


def sync_all(session: Session) -> list[ServerLibraries]:
    """Refresh every enabled server's list, keeping what was stored for any that can't be
    reached -- an unreachable server must not make the page unusable, or a user could be stuck
    unable to change their selection until it comes back."""
    from app.services import media_server_service

    groups = []
    for server in media_server_service.enabled_servers(session):
        group = ServerLibraries(server=server)
        try:
            client = media_server_service.client_for(server)
            group.libraries = sync_from_server(session, server, client)
            if server.kind == "plex":
                # Learning the server's identity here is what makes Plex sign-in possible at all.
                from app.services.auth_service import discover_machine_identifier

                discover_machine_identifier(session, server, client)
        except MediaServerError as exc:
            group.error = f"{exc}. Showing the libraries last seen."
            group.libraries = list_libraries(session, server.id)
        groups.append(group)
    return groups


def set_enabled_libraries(session: Session, ids: list[int]) -> list[IncludedLibrary]:
    """Replace the selection wholesale -- the form posts every ticked box, so anything absent
    was deliberately unticked."""
    wanted = set(ids)
    for row in list_libraries(session):
        row.enabled = row.id in wanted
        session.add(row)
    session.commit()

    chosen = enabled_libraries(session)
    logger.info("Library selection updated: %d enabled", len(chosen))
    return chosen


def has_selection(session: Session) -> bool:
    """Whether the user has chosen at least one library -- drives the post-login setup step."""
    return bool(enabled_libraries(session))
