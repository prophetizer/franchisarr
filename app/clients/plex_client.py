"""Plex Media Server client.

Returns plain frozen dataclasses, never plexapi objects. Services must not grow a dependency on
plexapi's object model -- docs/DESIGN.md commits to an adapter pattern so Emby/Jellyfin can be
added later, and that only works if the seam is real.

Two things here exist because of the scale this runs at (~3,600 movies, a few hundred shows):

* Listing is paged. `iter_movies`/`iter_shows` issue one HTTP request per page and convert as
  they go, so a scan never holds the whole library as plexapi objects.
* The section listing is asked for GUIDs inline (plexapi sets `includeGuids=1` by default), which
  is what makes a full scan a handful of requests instead of one metadata call per item. Older
  Plex servers ignore that parameter; when they do, items come back with no external IDs and
  `fetch_external_ids()` is the per-item fallback -- used selectively by the Phase 3 matcher, not
  fired blindly at 3,600 items.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date, datetime
from dataclasses import dataclass, field

import plexapi
import plexapi.media
from plexapi.exceptions import BadRequest, NotFound, Unauthorized
from plexapi.server import PlexServer
import requests
from requests.exceptions import RequestException

from app.clients.media_server import (
    MediaItem,
    MediaLibrary,
    MediaLibraryNotFoundError,
    MediaMovie,
    MediaServerError,
    MediaServerKind,
    MediaShow,
    PlaylistEntry,
    PlaylistInfo,
    PlaylistItemRef,
)
from app.clients.plex_guid import ExternalIds, extract_external_ids, unknown_schemes
from app.logging_config import register_secret
from app.models import LibraryType

logger = logging.getLogger(__name__)

#: Items per HTTP request when walking a library. Large enough that 3,600 movies is a handful of
#: requests, small enough not to make a Plex server on a NAS build an enormous XML document.
DEFAULT_PAGE_SIZE = 500

DEFAULT_TIMEOUT = 30

#: Plex section types we care about, mapped to our own library type.
_SECTION_TYPES = {"movie": LibraryType.MOVIE, "show": LibraryType.SHOW}


class PlexClientError(MediaServerError):
    """Base for every failure this client reports."""


class PlexUnreachableError(PlexClientError):
    """The server did not answer (down, wrong URL, DNS, TLS)."""


class PlexUnauthorizedError(PlexClientError):
    """The token was rejected."""


class PlexLibraryNotFoundError(PlexClientError, MediaLibraryNotFoundError):
    """No library section with that key."""


# Plex's items are the neutral ones; these names remain for the parser and audit script.
PlexLibrary = MediaLibrary
PlexItem = MediaItem
PlexMovie = MediaMovie
PlexShow = MediaShow


class PlexClient:
    kind = MediaServerKind.PLEX

    """Thin, typed wrapper over plexapi.

    The connection is lazy: constructing a client must not perform I/O, so config can be built
    and stored before the server is known to be reachable.
    """

    def __init__(
        self,
        url: str,
        token: str,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._page_size = max(1, page_size)
        self._server: PlexServer | None = None
        register_secret(token)

    @property
    def server(self) -> PlexServer:
        if self._server is None:
            self._server = self._connect()
        return self._server

    def _connect(self) -> PlexServer:
        _disable_plexapi_autoreload()
        try:
            return PlexServer(self._url, self._token, timeout=self._timeout)
        except Unauthorized as exc:
            raise PlexUnauthorizedError("Plex rejected the configured token") from exc
        except (BadRequest, RequestException) as exc:
            # Deliberately generic: this message is destined for a UI, and transport-layer
            # exceptions carry request detail that has no business being rendered into a page.
            # The original is chained, so the logs (where redaction applies) keep the specifics.
            raise PlexUnreachableError(f"Could not reach the Plex server at {self._url}") from exc

    def playlist_entries(self, films: list[str], shows: list[str]) -> list[PlaylistEntry]:
        """Playable films and regular episodes for the given rating keys, with air dates."""
        return _playlist_entries(self, films, shows)

    def set_playlist_poster(self, title: str, image: bytes) -> bool:
        return _set_playlist_poster(self, title, image)

    def playlist_titles(self) -> list[str]:
        return _playlist_titles(self)

    def playlist_counts(self, title: str) -> tuple[int, int, int] | None:
        return _playlist_counts(self, title)

    def playlists_ending(self, suffix: str) -> list[str]:
        return sorted(p.title for p in self.server.playlists() if p.title.endswith(suffix))

    def delete_playlists(self, suffix: str) -> list[str]:
        return _delete_playlists(self, suffix)

    # ---------------------------------------------------------------- playlist sync

    def list_playlists(self) -> list[PlaylistInfo]:
        """The token owner's playlists."""
        return [PlaylistInfo(id=str(_attr(p, "ratingKey", "")), title=_attr(p, "title", ""),
                             smart=bool(_attr(p, "smart", False)),
                             video=_attr(p, "playlistType", "video") == "video",
                             count=int(_attr(p, "leafCount", 0) or 0))
                for p in self.server.playlists()]

    def playlist_items(self, playlist_id: str) -> list[PlaylistItemRef]:
        """What the playlist holds now, in order -- a smart playlist's current contents too."""
        refs = []
        for item in self.server.fetchItem(int(playlist_id)).items():
            kind = getattr(item, "TYPE", "")
            key = str(_attr(item, "ratingKey", ""))
            entry = str(_attr(item, "playlistItemID", "") or "")
            if kind == "movie":
                refs.append(PlaylistItemRef("movie", key, _attr(item, "title", ""), entry_id=entry))
            elif kind == "episode":
                season, number = int(_attr(item, "parentIndex", 0) or 0), int(_attr(item, "index", 0) or 0)
                refs.append(PlaylistItemRef(
                    "episode", key, f"{_attr(item, 'grandparentTitle', '')} S{season:02d}E{number:02d}",
                    show_key=str(_attr(item, "grandparentRatingKey", "")), season=season, episode=number,
                    entry_id=entry))
            else:
                refs.append(PlaylistItemRef("other", key, _attr(item, "title", ""), entry_id=entry))
        return refs

    # Editing in place (media_server.edit_in_place): by playlistItemID, straight to Plex's
    # endpoints -- plexapi's removeItems/moveItem re-read the whole playlist for every item.

    def remove_playlist_entries(self, playlist_id: str, entry_ids: list[str]) -> None:
        for entry_id in entry_ids:
            self.server.query(f"/playlists/{int(playlist_id)}/items/{int(entry_id)}",
                              method=self.server._session.delete)

    def append_to_playlist(self, playlist_id: str, items: list) -> None:  # noqa: ANN001 - plexapi objects
        playlist = self.server.fetchItem(int(playlist_id))
        for start in range(0, len(items), PLAYLIST_CHUNK):
            playlist.addItems(items[start:start + PLAYLIST_CHUNK])

    def rename_playlist(self, playlist_id: str, title: str) -> None:
        from urllib.parse import quote

        self.server.query(f"/playlists/{int(playlist_id)}?title={quote(title)}", method=self.server._session.put)

    def move_playlist_entry(self, playlist_id: str, entry_id: str, index: int, after: str | None) -> None:
        """Plex places an entry after another one; with none, first."""
        key = f"/playlists/{int(playlist_id)}/items/{int(entry_id)}/move"
        if after:
            key += f"?after={int(after)}"
        self.server.query(key, method=self.server._session.put)

    def create_playlist(self, title: str, items: list) -> str:  # noqa: ANN001 - plexapi objects
        """A new playlist of `items`, in order; its id. Never touches another playlist."""
        playlist = self.server.createPlaylist(title, items=items[:PLAYLIST_CHUNK])
        for start in range(PLAYLIST_CHUNK, len(items), PLAYLIST_CHUNK):
            playlist.addItems(items[start:start + PLAYLIST_CHUNK])
        return str(_attr(playlist, "ratingKey", ""))

    def delete_playlist_id(self, playlist_id: str) -> None:
        from plexapi.exceptions import NotFound

        try:
            self.server.fetchItem(int(playlist_id)).delete()
        except NotFound:
            pass

    def playlist_poster(self, playlist_id: str) -> bytes | None:
        """The playlist's own poster, if someone set one; None for Plex's automatic mosaic.
        plexapi doesn't parse a playlist's `thumb`, so it's read off the raw XML."""
        playlist = self.server.fetchItem(int(playlist_id))
        thumb = getattr(playlist, "_data", None) is not None and playlist._data.attrib.get("thumb")
        if not thumb:
            return None
        response = requests.get(self.server.url(thumb, includeToken=True), timeout=30)
        return response.content if response.ok and response.content else None

    def set_playlist_poster_id(self, playlist_id: str, image: bytes) -> bool:
        return _upload_poster(self.server.fetchItem(int(playlist_id)), image)

    def delete_all_playlists(self) -> list[str]:
        """Every playlist of the token's owner -- theirs alone; Plex keeps each user's apart."""
        return _delete_playlists(self, "")

    def test_connection(self) -> str:
        """Connect and return the server's friendly name. Used by the setup wizard's
        "Test Connection" button in Phase 2."""
        return self.server.friendlyName

    def list_libraries(self) -> list[PlexLibrary]:
        """Movie and show sections. Music and photo sections are skipped -- Franchisarr has
        nothing to say about them, and offering them as checkboxes would only mislead."""
        try:
            sections = self.server.library.sections()
        except (BadRequest, RequestException) as exc:
            raise PlexUnreachableError("Could not list Plex libraries") from exc

        libraries = []
        for section in sections:
            library_type = _SECTION_TYPES.get(getattr(section, "type", None))
            if library_type is None:
                continue
            libraries.append(
                PlexLibrary(
                    key=str(section.key),
                    title=section.title,
                    library_type=library_type.value,
                    agent=getattr(section, "agent", None),
                )
            )
        return libraries

    def _section(self, library_key: str | int):
        key = int(library_key) if str(library_key).isdigit() else library_key
        try:
            return self.server.library.sectionByID(key)
        except NotFound as exc:
            raise PlexLibraryNotFoundError(f"No Plex library with key {library_key}") from exc
        except (BadRequest, RequestException) as exc:
            raise PlexUnreachableError("Could not reach the Plex server") from exc

    def _iter_section(self, library_key: str | int, libtype: str) -> Iterator[PlexItem]:
        section = self._section(library_key)
        offset = 0
        seen_unknown: set[str] = set()

        while True:
            try:
                batch = section.search(
                    libtype=libtype,
                    container_start=offset,
                    container_size=self._page_size,
                    maxresults=self._page_size,
                )
            except (BadRequest, RequestException) as exc:
                raise PlexUnreachableError(
                    f"Plex stopped responding while listing library {library_key}"
                ) from exc

            for raw in batch:
                yield _to_item(raw, seen_unknown)

            if len(batch) < self._page_size:
                return
            offset += self._page_size

    def iter_movies(self, library_key: str | int) -> Iterator[PlexMovie]:
        for item in self._iter_section(library_key, "movie"):
            yield PlexMovie(**vars(item))

    def iter_shows(self, library_key: str | int) -> Iterator[PlexShow]:
        for item in self._iter_section(library_key, "show"):
            yield PlexShow(**vars(item))

    def list_movies(self, library_key: str | int) -> list[PlexMovie]:
        return list(self.iter_movies(library_key))

    def list_shows(self, library_key: str | int) -> list[PlexShow]:
        return list(self.iter_shows(library_key))

    def fetch_external_ids(self, item_key: str | int) -> ExternalIds:
        """Per-item fallback for servers whose section listing omits <Guid> children.

        One HTTP request per call, so callers must use it for the items that need it, not as the
        default path.
        """
        try:
            item = self.server.fetchItem(int(item_key))
        except NotFound:
            return ExternalIds()
        except (BadRequest, RequestException) as exc:
            raise PlexUnreachableError(f"Could not fetch Plex item {item_key}") from exc
        return _external_ids_of(item)


#: plexapi builds one URL listing every rating key; chunks keep it short on a big franchise.
PLAYLIST_CHUNK = 100


def _aired(raw) -> date | None:  # noqa: ANN001 - a plexapi Video
    value = _attr(raw, "originallyAvailableAt")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    year = _attr(raw, "year")
    return date(int(year), 1, 1) if year else None


def _playlist_entries(client: "PlexClient", films: list[str], shows: list[str]) -> list[PlaylistEntry]:
    """Films and every regular episode of the shows, as PlaylistEntry, from as few requests as
    plexapi allows: films in batches by rating key, then one request per show for its episodes."""
    entries: list[PlaylistEntry] = []
    server = client.server
    for start in range(0, len(films), PLAYLIST_CHUNK):
        keys = ",".join(films[start:start + PLAYLIST_CHUNK])
        for raw in server.fetchItems(f"/library/metadata/{keys}"):
            entries.append(PlaylistEntry(raw=raw, aired=_aired(raw), key=str(_attr(raw, "ratingKey", ""))))
    for show_key in shows:
        try:
            show = server.fetchItem(int(show_key))
        except NotFound:
            logger.warning("Show %s is no longer on the Plex server; skipped", show_key)
            continue
        previous: date | None = None
        episodes = sorted(show.episodes(), key=lambda e: (_attr(e, "parentIndex", 0), _attr(e, "index", 0)))
        for raw in episodes:
            season = int(_attr(raw, "parentIndex", 0) or 0)
            if season == 0:
                continue     # specials: not part of the run, and usually not in air order
            aired = _aired(raw) or previous   # an undated episode stays after the one before it
            previous = aired or previous
            entries.append(PlaylistEntry(raw=raw, aired=aired, show_key=str(show_key),
                                         season=season, episode=int(_attr(raw, "index", 0) or 0),
                                         key=str(_attr(raw, "ratingKey", ""))))
    return entries


def _delete_playlists(client: "PlexClient", suffix: str) -> list[str]:
    """Delete every playlist whose title ends with `suffix`; the titles deleted, sorted."""
    gone = []
    for playlist in client.server.playlists():
        if playlist.title.endswith(suffix):
            playlist.delete()
            gone.append(playlist.title)
    return sorted(gone)


def _playlist_titles(client: "PlexClient") -> list[str]:
    return [p.title for p in client.server.playlists()]


def _playlist_counts(client: "PlexClient", title: str) -> tuple[int, int, int] | None:
    """(films, shows, episodes) in the playlist called `title`, or None if there isn't one."""
    playlist = next((p for p in client.server.playlists() if p.title == title), None)
    if playlist is None:
        return None
    items = playlist.items()
    films = sum(1 for i in items if getattr(i, "TYPE", "") == "movie")
    episodes = [i for i in items if getattr(i, "TYPE", "") == "episode"]
    return films, len({i.__dict__.get("grandparentRatingKey") for i in episodes}), len(episodes)


def _set_playlist_poster(client: "PlexClient", title: str, image: bytes) -> bool:
    """Upload `image` (JPEG bytes) as the poster of the playlist called `title`. False if there
    is no such playlist. plexapi uploads from a file path, hence the temporary file."""
    import tempfile

    for playlist in client.server.playlists():
        if playlist.title == title:
            return _upload_poster(playlist, image)
    return False


def _upload_poster(playlist, image: bytes) -> bool:  # noqa: ANN001 - a plexapi Playlist
    """plexapi uploads from a file path, hence the temporary file."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".jpg") as handle:
        handle.write(image)
        handle.flush()
        playlist.uploadPoster(filepath=handle.name)
    return True


def _disable_plexapi_autoreload() -> None:
    """Turn off plexapi's implicit per-item metadata refetch.

    plexapi's PlexPartialObject.__getattribute__ reloads the entire object from the server
    whenever an attribute reads back as None or [] and the object came from a listing rather than
    a full metadata call. That is a sensible default for a script poking at one movie, and a
    catastrophe here: every item without a year, and every show whose listing omits childCount,
    silently becomes its own HTTP request -- turning a handful of requests for a 3,600-movie
    library into 3,600 requests against someone's NAS, with nothing in our code to show for it.

    It cannot be avoided by being careful about which attributes we touch, because plexapi
    triggers it from inside its own _loadData while constructing the object (Show._loadData
    reads self.childCount to default seasonCount). The library's own config flag is the only
    lever, and it is read per-object at construction time -- so setting it before the server
    object exists covers every object built from that server afterwards.

    Where an item really does need its full metadata, `fetch_external_ids()` asks for it
    explicitly, which is the point: the request becomes a decision rather than a side effect.
    """
    plexapi.CONFIG.data.setdefault("plexapi", {})["autoreload"] = False


def _attr(raw, name: str, default=None):  # noqa: ANN001 - a plexapi Video
    """Read an attribute off a plexapi object, defaulting None away.

    Goes through __dict__ rather than getattr: underscore-prefixed names skip the auto-reload
    branch entirely, so this stays correct even if the config flag above is ever reverted.
    """
    value = raw.__dict__.get(name, default)
    return default if value is None else value


def _guid_strings(raw) -> tuple[str, ...]:  # noqa: ANN001 - a plexapi Video
    guids = raw.__dict__.get("guids")
    if guids is None and raw.__dict__.get("_data") is not None:
        # plexapi 4.18 builds `guids` lazily, on first read, so it isn't in __dict__ yet. Build
        # it from the item's own XML, as plexapi would: no request, and no trip through the
        # auto-reload in __getattribute__ (findItems is a method, never None or []).
        guids = raw.findItems(raw.__dict__["_data"], plexapi.media.Guid)
    return tuple(guid.id for guid in guids or () if guid.__dict__.get("id"))


def _external_ids_of(raw) -> ExternalIds:  # noqa: ANN001 - a plexapi Video
    return extract_external_ids(item_guid=_attr(raw, "guid"), guids=_guid_strings(raw))


def _to_item(raw, seen_unknown: set[str]) -> PlexItem:  # noqa: ANN001 - a plexapi Video
    item_guid = _attr(raw, "guid")
    child_guids = _guid_strings(raw)
    external_ids = extract_external_ids(item_guid=item_guid, guids=child_guids)

    all_guids = tuple(child_guids) + ((item_guid,) if item_guid else ())

    # Log a given unrecognised agent once per scan, not once per item -- a library matched
    # entirely by an agent we don't know would otherwise produce thousands of identical lines.
    for guid in unknown_schemes(item_guid=item_guid, guids=child_guids):
        scheme = guid.split("://", 1)[0]
        if scheme not in seen_unknown:
            seen_unknown.add(scheme)
            logger.warning(
                "Unrecognised Plex agent %r (e.g. %r on %r) — its items cannot be matched to "
                "TMDb until support is added",
                scheme,
                guid,
                _attr(raw, "title", "?"),
            )

    return PlexItem(
        item_key=str(_attr(raw, "ratingKey", "")),
        title=_attr(raw, "title", "") or "",
        year=_attr(raw, "year"),
        external_ids=external_ids,
        guids=all_guids,
        watched=_watched(raw),
        runtime=_runtime(_attr(raw, "duration")),
    )


def _runtime(milliseconds) -> int | None:  # noqa: ANN001 - whatever the listing held
    """Plex's duration (ms) in whole minutes; None when absent or nonsense."""
    try:
        minutes = round(int(milliseconds) / 60000)
    except (TypeError, ValueError):
        return None
    return minutes if minutes > 0 else None


def _watched(raw) -> bool | None:  # noqa: ANN001 - a plexapi Video
    """The token owner's play state: a film's viewCount, a show's viewedLeafCount (any episode).
    Both come with the listing, so this costs no extra request."""
    # plexapi gives every Video a viewCount (0 when absent) but only shows a viewedLeafCount,
    # which is the meaningful one there -- a show's own viewCount stays 0 however much was played.
    leaf = _attr(raw, "viewedLeafCount")
    if isinstance(leaf, int):
        return leaf > 0
    if _attr(raw, "type") == "show":
        return None  # a listing without the count is silent, not "unwatched"
    count = _attr(raw, "viewCount")
    return count > 0 if isinstance(count, int) else None


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "PlexClient",
    "PlexClientError",
    "PlexLibrary",
    "PlexLibraryNotFoundError",
    "PlexItem",
    "PlexMovie",
    "PlexShow",
    "PlexUnauthorizedError",
    "PlexUnreachableError",
]
