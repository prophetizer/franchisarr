"""Playlists of a franchise, collection or director, in the order things came out.

The titles are the ones you own on that page. Films and every regular episode of the shows go
into one list sorted by first release -- so for a franchise that spans film and TV, episodes
fall between the films as they were broadcast. Nothing records story order (where *Rogue One*
sits in the timeline), so release order is the order there is.

One playlist per media server, since a playlist can only hold that server's items, named
"<name> (Franchisarr)". Pressing the button again rebuilds that playlist with whatever is owned
now; playlists with any other name are never touched. Plex first: Jellyfin and Emby items are
counted and reported as not yet supported.

Created in the account whose token the server was configured with -- the server owner's --
because Plex playlists belong to one account and can't be shared.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session, col, select

from app.clients.media_server import MediaServerKind
from app.models import ItemType, LibraryItem, MediaServer

logger = logging.getLogger(__name__)

SUFFIX = " (Franchisarr)"


@dataclass
class ServerResult:
    server: str
    films: int = 0
    episodes: int = 0
    error: str | None = None
    #: Whether our own poster went on; a failure there never fails the playlist.
    poster: bool = False


@dataclass(frozen=True)
class PosterArt:
    """What a playlist poster is made from: a backdrop if the page has one, else film posters
    (in release order) for a mosaic. See playlist_poster."""

    backdrop_url: str | None = None
    poster_urls: tuple[str, ...] = ()


@dataclass
class PlaylistResult:
    title: str
    servers: list[ServerResult] = field(default_factory=list)
    #: Owned titles on servers that can't take a playlist yet (Jellyfin, Emby).
    unsupported: int = 0

    @property
    def made_any(self) -> bool:
        return any(s.error is None and (s.films or s.episodes) for s in self.servers)


def available(session: Session) -> bool:
    """Whether any server here can take a playlist yet (an enabled Plex server)."""
    from app.services import media_server_service

    return any(media_server_service.kind_of(s) == MediaServerKind.PLEX
               for s in media_server_service.enabled_servers(session))


def playlist_title(name: str) -> str:
    return f"{name}{SUFFIX}"


def _owned_items(session: Session, refs: list[tuple[str, int]]) -> dict[int, list[LibraryItem]]:
    """The library rows behind (item_type, tmdb_id) pairs, grouped by server, one query."""
    by_type: dict[str, set[int]] = {}
    for item_type, tmdb_id in refs:
        by_type.setdefault(item_type, set()).add(tmdb_id)
    grouped: dict[int, list[LibraryItem]] = {}
    seen: set[tuple[int, str, int]] = set()
    for item_type, ids in by_type.items():
        rows = session.exec(select(LibraryItem).where(
            col(LibraryItem.item_type) == item_type, col(LibraryItem.tmdb_id).in_(ids),
        )).all()
        for row in rows:
            key = (row.server_id, row.item_type, row.tmdb_id)
            if key in seen:           # two copies of one film on a server: play it once
                continue
            seen.add(key)
            grouped.setdefault(row.server_id, []).append(row)
    return grouped


def order_entries(entries: list) -> list:  # noqa: ANN001 - PlaylistEntry
    """Release order. Undated items go last; a show's episodes keep season/episode order when
    they share a date, and a film sorts before an episode that aired the same day."""
    far_future = date.max
    return sorted(entries, key=lambda e: (
        e.aired or far_future,
        0 if e.show_key is None else 1,
        e.show_key or "",
        e.season,
        e.episode,
    ))


def build(session: Session, name: str, refs: list[tuple[str, int]],
          art: PosterArt | None = None) -> PlaylistResult:
    """Build (or rebuild) the playlist for `name` from the owned (item_type, tmdb_id) pairs,
    and give it a poster made from `art`."""
    from app.services import media_server_service

    title = playlist_title(name)
    result = PlaylistResult(title=title)
    for server_id, items in _owned_items(session, refs).items():
        server = session.get(MediaServer, server_id)
        if server is None or not server.enabled:
            continue
        if media_server_service.kind_of(server) != MediaServerKind.PLEX:
            result.unsupported += len(items)
            continue
        outcome = ServerResult(server=server.name)
        result.servers.append(outcome)
        films = [i.item_key for i in items if i.item_type == ItemType.MOVIE.value]
        shows = [i.item_key for i in items if i.item_type == ItemType.SHOW.value]
        try:
            client = media_server_service.client_for(server)
            entries = order_entries(client.playlist_entries(films, shows))
            if not entries:
                outcome.error = "None of these titles could be found on the server any more."
                continue
            client.replace_playlist(title, [e.raw for e in entries])
        except Exception as exc:  # noqa: BLE001 -- reported to the admin, logged with detail
            logger.exception("Couldn't build playlist %r on %s", title, server.name)
            outcome.error = f"Plex refused or couldn't be reached ({type(exc).__name__})."
            continue
        outcome.films = sum(1 for e in entries if e.show_key is None)
        outcome.episodes = len(entries) - outcome.films
        if art is not None:
            outcome.poster = apply_poster(client, title, name, outcome.films, outcome.episodes, art)
        logger.info("Playlist %r on %s: %d films, %d episodes", title, server.name,
                    outcome.films, outcome.episodes)
    return result


def apply_poster(client, title: str, name: str, films: int, episodes: int,  # noqa: ANN001
                 art: PosterArt) -> bool:
    """Render and upload the poster. Never raises: True if it went on, False otherwise."""
    from app.services import playlist_poster

    image = playlist_poster.render(name, films=films, episodes=episodes,
                                   backdrop_url=art.backdrop_url, poster_urls=list(art.poster_urls))
    if image is None:
        return False
    try:
        return bool(client.set_playlist_poster(title, image))
    except Exception:  # noqa: BLE001
        logger.warning("Couldn't upload the poster for %r", title, exc_info=True)
        return False
