"""Playlists of a franchise, collection or director, in the order things came out.

The titles are the ones you own on that page. Films and every regular episode of the shows go
into one list sorted by first release -- so for a franchise that spans film and TV, episodes
fall between the films as they were broadcast. Nothing records story order (where *Rogue One*
sits in the timeline), so release order is the order there is.

One playlist per media server, since a playlist can only hold that server's items, named
"<name> (Franchisarr)". Making and keeping them is franchisarr_playlists.py (0.42.0): each is
written by its id and edited in place. This module keeps the pieces -- ordering, posters, and
deleting ours.

Playlists belong to one account on every server. On Plex that's the token's owner (normally the
server owner); on Jellyfin and Emby it's the server's "watched as" user, the first
administrator unless set.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session, col, select

from app.models import LibraryItem, MediaServer

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
    #: The one server this was built on, when it was asked for one; None for every server.
    only: str | None = None
    #: Servers left out because they held fewer than `min_items` of the titles.
    skipped: int = 0

    @property
    def made_any(self) -> bool:
        return any(s.error is None and (s.films or s.episodes) for s in self.servers)


def available(session: Session) -> bool:
    """Whether any server here can take a playlist: Plex, Jellyfin and Emby all can."""
    from app.services import media_server_service

    return bool(media_server_service.enabled_servers(session))


def targets(session: Session) -> list[MediaServer]:
    """The servers a playlist can go on, for the per-server buttons: every enabled one."""
    from app.services import media_server_service

    return media_server_service.enabled_servers(session)


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


# ------------------------------------------------------------------ deleting ours


@dataclass
class ServerPlaylists:
    """Franchisarr's playlists on one server: the ones found, or the ones just deleted."""

    server: str
    titles: list[str] = field(default_factory=list)
    error: str | None = None


def _chosen(session: Session, server_id: int | None) -> list[MediaServer]:
    return [s for s in targets(session) if server_id is None or s.id == server_id]


def ours(session: Session, server_id: int | None = None, *, everything: bool = False) -> list[ServerPlaylists]:
    """What deleting would remove, for the confirmation: every playlist named
    "... (Franchisarr)", on one server or all of them -- or, with `everything`, every playlist in
    the account Franchisarr uses there (the Plex token's owner, the Jellyfin/Emby "watched as"
    user), the ones people made themselves included. Nobody else's are ever listed."""
    from app.services import media_server_service

    found = []
    for server in _chosen(session, server_id):
        entry = ServerPlaylists(server=server.name)
        try:
            client = media_server_service.client_for(server)
            entry.titles = sorted(client.playlist_titles()) if everything else client.playlists_ending(SUFFIX)
        except Exception as exc:  # noqa: BLE001 -- shown in the confirmation, logged in full
            logger.exception("Couldn't list playlists on %s", server.name)
            entry.error = f"Couldn't be reached ({type(exc).__name__})."
        found.append(entry)
    return found


def delete_ours(session: Session, server_id: int | None = None, *, everything: bool = False) -> list[ServerPlaylists]:
    """Delete every Franchisarr playlist on one server or all of them; what went, per server.
    Only names ending " (Franchisarr)" -- a playlist anyone made by hand is never touched --
    unless `everything`, which deletes every playlist in the account Franchisarr uses there and
    only that account's (see `ours`)."""
    from app.services import media_server_service

    done = []
    for server in _chosen(session, server_id):
        entry = ServerPlaylists(server=server.name)
        try:
            client = media_server_service.client_for(server)
            entry.titles = client.delete_all_playlists() if everything else client.delete_playlists(SUFFIX)
            logger.info("Deleted %d %splaylist(s) on %s", len(entry.titles),
                        "" if everything else "Franchisarr ", server.name)
            # Clearing a server isn't someone deleting one playlist: it mustn't spread (0.42.0).
            from app.services import franchisarr_playlists

            franchisarr_playlists.forget_server(session, server.id if server_id is not None else None)
        except Exception as exc:  # noqa: BLE001 -- reported to the admin, logged in full
            logger.exception("Couldn't delete playlists on %s", server.name)
            entry.error = f"The server refused or couldn't be reached ({type(exc).__name__})."
        done.append(entry)
    return done


def repost_all(session: Session) -> list[tuple[str, bool]]:
    """Give every existing Franchisarr playlist on every server a fresh poster, with the counts
    read from the playlist itself and without touching its contents. Returns (title, poster went
    on) per playlist. For when the poster design changes."""
    from app.services import media_server_service

    done: list[tuple[str, bool]] = []
    for server in media_server_service.enabled_servers(session):
        client = media_server_service.client_for(server)
        for title in client.playlist_titles():
            if not title.endswith(SUFFIX):
                continue
            name = title[: -len(SUFFIX)]
            art = _art_for_name(session, name)
            counts = client.playlist_counts(title)
            if art is None or counts is None:
                done.append((title, False))
                continue
            films, shows, episodes = counts
            done.append((title, apply_poster(client, title, name, films, episodes, art, shows=shows)))
    return done
