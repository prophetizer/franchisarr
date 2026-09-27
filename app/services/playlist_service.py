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
    shows: int = 0
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
        outcome.shows = len({e.show_key for e in entries if e.show_key is not None})
        if art is not None:
            outcome.poster = apply_poster(client, title, name, outcome.films, outcome.episodes, art,
                                          shows=outcome.shows)
        logger.info("Playlist %r on %s: %d films, %d episodes", title, server.name,
                    outcome.films, outcome.episodes)
    return result


def apply_poster(client, title: str, name: str, films: int, episodes: int,  # noqa: ANN001
                 art: PosterArt, *, shows: int = 0) -> bool:
    """Render and upload the poster. Never raises: True if it went on, False otherwise."""
    from app.services import playlist_poster

    image = playlist_poster.render(name, films=films, episodes=episodes, shows=shows,
                                   backdrop_url=art.backdrop_url, poster_urls=list(art.poster_urls))
    if image is None:
        return False
    try:
        return bool(client.set_playlist_poster(title, image))
    except Exception:  # noqa: BLE001
        logger.warning("Couldn't upload the poster for %r", title, exc_info=True)
        return False


def art_from(backdrop_path: str | None, titles) -> PosterArt:  # noqa: ANN001
    """A poster's artwork: the page's backdrop, and film posters oldest first as a fallback."""
    from app.services.artwork import backdrop_url, poster_url

    dated = sorted((t for t in titles if getattr(t, "poster_path", None)),
                   key=lambda t: str(getattr(t, "release_date", None) or getattr(t, "year", None)
                                     or getattr(t, "release_year", None) or "9999"))
    return PosterArt(
        backdrop_url=backdrop_url(backdrop_path, "w1280") if backdrop_path else None,
        poster_urls=tuple(poster_url(t.poster_path, "w342") for t in dated[:10]),
    )


def _art_for_name(session: Session, name: str) -> PosterArt | None:
    """Find which page a playlist called "<name> (Franchisarr)" came from -- a franchise, a
    collection or a director of that name, in that order -- and its artwork."""
    from app.models import Franchise, MovieDirector, TmdbCollection
    from app.services import director_service, franchise_service, movie_gap_service

    franchise = session.exec(select(Franchise).where(col(Franchise.name) == name)).first()
    if franchise is not None:
        view = franchise_service.franchise_view(session, franchise.wikidata_id)
        if view is not None:
            return art_from(view.backdrop_path, view.owned_films)
    collection = session.exec(select(TmdbCollection).where(col(TmdbCollection.name) == name)).first()
    if collection is not None:
        gap = next((g for g in movie_gap_service.collection_gaps(
            session, None, only={collection.tmdb_collection_id})), None)
        return art_from(collection.backdrop_path, gap.owned if gap else ())
    person = session.exec(select(MovieDirector.person_id).where(col(MovieDirector.name) == name)).first()
    if person is not None:
        view = director_service.director_view(session, person)
        if view is not None:
            return art_from(None, view.owned)
    return None


def repost_all(session: Session) -> list[tuple[str, bool]]:
    """Give every existing Franchisarr playlist on every Plex server a fresh poster, with the
    counts read from the playlist itself and without touching its contents. Returns
    (title, poster went on) per playlist. For when the poster design changes."""
    from app.services import media_server_service

    done: list[tuple[str, bool]] = []
    for server in media_server_service.enabled_servers(session):
        if media_server_service.kind_of(server) != MediaServerKind.PLEX:
            continue
        client = media_server_service.client_for(server)
        for playlist in client.server.playlists():
            if not playlist.title.endswith(SUFFIX):
                continue
            name = playlist.title[: -len(SUFFIX)]
            art = _art_for_name(session, name)
            if art is None:
                done.append((playlist.title, False))
                continue
            items = playlist.items()
            films = sum(1 for i in items if getattr(i, "TYPE", "") == "movie")
            episodes = [i for i in items if getattr(i, "TYPE", "") == "episode"]
            shows = len({i.__dict__.get("grandparentRatingKey") for i in episodes})
            done.append((playlist.title, apply_poster(client, playlist.title, name, films, len(episodes),
                                                      art, shows=shows)))
    return done
