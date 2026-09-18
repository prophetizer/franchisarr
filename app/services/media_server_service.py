"""The configured media servers, and a client for each.

There is never "the media server" any more than there is "the Radarr" (docs/DEVELOPMENT.md
convention 4). A household might keep Plex for the family and Jellyfin for itself, or be halfway
through moving between them; their libraries are scanned together and a film on any of them is
owned. Everything here takes or returns a `MediaServer` row.

The environment can still describe servers -- PLEX_URL/PLEX_TOKEN, JELLYFIN_URL/JELLYFIN_API_KEY,
EMBY_URL/EMBY_API_KEY -- and on first boot each pair becomes a row. After that the rows are the
truth, so a stale value in docker-compose can't undo a change made in the app.
"""

from __future__ import annotations

import logging

from sqlmodel import Session, col, delete, select

from app.clients.media_server import MediaServerClient, MediaServerKind
from app.config import EnvSettings
from app.logging_config import register_secret
from app.models import IncludedLibrary, LibraryItem, MediaServer

logger = logging.getLogger(__name__)

LABELS = {MediaServerKind.PLEX: "Plex", MediaServerKind.JELLYFIN: "Jellyfin", MediaServerKind.EMBY: "Emby"}


def label(kind: MediaServerKind | str) -> str:
    return LABELS[MediaServerKind(kind)]


def kind_of(server: MediaServer) -> MediaServerKind:
    return MediaServerKind(server.kind)


def list_servers(session: Session) -> list[MediaServer]:
    return list(session.exec(select(MediaServer).order_by(col(MediaServer.name))).all())


def enabled_servers(session: Session) -> list[MediaServer]:
    return [server for server in list_servers(session) if server.enabled]


def get_server(session: Session, server_id: int) -> MediaServer | None:
    return session.get(MediaServer, server_id)


def is_configured(session: Session) -> bool:
    return bool(enabled_servers(session))


def missing_message(session: Session) -> str:
    return "No media server is configured yet."


def plex_servers(session: Session) -> list[MediaServer]:
    return [s for s in enabled_servers(session) if kind_of(s) == MediaServerKind.PLEX]


def password_servers(session: Session) -> list[MediaServer]:
    """Servers a person can sign in to with a username and password: Jellyfin and Emby."""
    return [s for s in enabled_servers(session) if kind_of(s) != MediaServerKind.PLEX]


def client_for(server: MediaServer) -> MediaServerClient:
    if kind_of(server) == MediaServerKind.PLEX:
        from app.clients.plex_client import PlexClient

        return PlexClient(server.url, server.credential)
    from app.clients.emby_client import EmbyLikeClient

    return EmbyLikeClient(server.url, server.credential, kind=kind_of(server),
                          watched_user=server.watched_user)


def create_server(session: Session, **fields) -> MediaServer:
    server = MediaServer(**fields)
    server.kind = MediaServerKind(server.kind).value
    session.add(server)
    session.commit()
    session.refresh(server)
    register_secret(server.credential)
    logger.info("Added %s server %r", label(server.kind), server.name)
    return server


def update_server(session: Session, server: MediaServer, **fields) -> MediaServer:
    """Change what was given. An empty credential means "keep the old one", because the edit form
    shows a masked value and submitting it unchanged must not blank the key."""
    for key, value in fields.items():
        if key == "credential" and not value:
            continue
        if key == "kind":
            value = MediaServerKind(value).value
        setattr(server, key, value)
    session.add(server)
    session.commit()
    session.refresh(server)
    register_secret(server.credential)
    return server


def delete_server(session: Session, server_id: int) -> None:
    """Remove a server and everything scanned from it. The gap views recompute from what is
    left, so a film that was only on this server stops counting as owned."""
    server = get_server(session, server_id)
    if server is None:
        return
    session.exec(delete(LibraryItem).where(col(LibraryItem.server_id) == server_id))
    session.exec(delete(IncludedLibrary).where(col(IncludedLibrary.server_id) == server_id))
    session.delete(server)
    session.commit()
    logger.info("Removed %s server %r and its scanned libraries", label(server.kind), server.name)


def test_connection(server: MediaServer) -> str:
    return client_for(server).test_connection()


def seed_from_env(session: Session, env: EnvSettings) -> list[MediaServer]:
    """Create servers from the environment on first boot, one per configured kind.

    Only ever creates, and only when no server exists at all. MEDIA_SERVER, when set, limits it
    to that kind -- the 0.12 meaning of the variable, kept so an existing .env behaves the same.
    """
    if list_servers(session):
        logger.debug("Media servers already configured; skipping env bootstrap")
        return []
    pairs = (
        (MediaServerKind.PLEX, env.plex_url, env.plex_token),
        (MediaServerKind.JELLYFIN, env.jellyfin_url, env.jellyfin_api_key),
        (MediaServerKind.EMBY, env.emby_url, env.emby_api_key),
    )
    created = []
    for kind, url, credential in pairs:
        if not (url and credential):
            continue
        if env.media_server and env.media_server != kind.value:
            continue
        created.append(create_server(session, name=LABELS[kind], kind=kind.value,
                                     url=url, credential=credential))
    if created:
        logger.info("Seeded %d media server(s) from the environment", len(created))
    return created
