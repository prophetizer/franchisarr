"""The media-server boundary: what a scan needs from Plex, Jellyfin or Emby, and nothing else.

Every server answers the same four questions -- is it reachable, which libraries exist, which
films are in one, which shows -- and everything downstream of the scan consumes `ExternalIds`,
never a server's own object model. So this is the whole interface. A new server is a new module
that implements it; nothing in the scan, the matcher or the pages knows which one it is talking to.

Measured before it was drawn: on the developer's own Jellyfin and Emby, 99.7-100% of films and
shows carry a TMDb id directly in `ProviderIds`, which is better than Plex manages after parsing
two generations of GUID formats. The `guids` field exists for Plex's benefit and is empty
elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Iterator, Protocol

from app.clients.plex_guid import ExternalIds
from app.models import LibraryType


class MediaServerKind(str, Enum):
    PLEX = "plex"
    JELLYFIN = "jellyfin"
    EMBY = "emby"


class MediaServerError(RuntimeError):
    """Any media-server failure. The message is safe to show a user."""


class MediaLibraryNotFoundError(MediaServerError):
    """No library with that key."""


@dataclass(frozen=True)
class MediaLibrary:
    key: str
    title: str
    library_type: str
    #: Plex's metadata agent, when known. Other servers leave it None.
    agent: str | None = None

    @property
    def is_movie_library(self) -> bool:
        return self.library_type == LibraryType.MOVIE.value

    @property
    def is_show_library(self) -> bool:
        return self.library_type == LibraryType.SHOW.value


@dataclass(frozen=True)
class MediaItem:
    """One film or show, with whatever external ids the server could give us.

    `guids` keeps Plex's raw GUID strings: when a library turns up an agent format the parser
    doesn't know, that field is the evidence needed to add it.
    """

    item_key: str
    title: str
    year: int | None
    external_ids: ExternalIds
    guids: tuple[str, ...] = field(default_factory=tuple)
    #: Played by the account the server was asked as; for a show, any episode played. None when
    #: the server gave no answer.
    watched: bool | None = None

    @property
    def has_external_ids(self) -> bool:
        return not self.external_ids.is_empty


@dataclass(frozen=True)
class MediaMovie(MediaItem):
    pass


@dataclass(frozen=True)
class MediaShow(MediaItem):
    pass


class MediaServerClient(Protocol):
    kind: MediaServerKind

    def test_connection(self) -> str:
        """The server's name, or raise MediaServerError with something a user can act on."""
        ...

    def list_libraries(self) -> list[MediaLibrary]: ...

    def iter_movies(self, library_key: str | int) -> Iterator[MediaMovie]: ...

    def iter_shows(self, library_key: str | int) -> Iterator[MediaShow]: ...


@dataclass(frozen=True)
class PlaylistEntry:
    """One playable item for a playlist, with what it takes to put it in release order.

    `raw` is whatever the server's client needs to put the item in a playlist: the plexapi
    object for Plex (holding on to it saves fetching every item twice), the item id for
    Jellyfin and Emby.
    """

    raw: object
    aired: date | None
    #: For episodes: position within the show, and the show's own key so a show's episodes
    #: keep their order when several share an air date.
    show_key: str | None = None
    season: int = 0
    episode: int = 0
    #: The item's own key on its server (a Plex ratingKey, a Jellyfin/Emby id), for matching
    #: a playlist's titles across servers (playlist_sync).
    key: str | None = None


@dataclass(frozen=True)
class PlaylistInfo:
    """A playlist as a server lists it, for playlist sync."""

    id: str
    title: str
    #: A Plex smart playlist: its contents follow rules, and a copy holds what it held at sync.
    smart: bool = False
    #: Films and episodes. Music and photo playlists aren't synced.
    video: bool = True
    count: int = 0


@dataclass(frozen=True)
class PlaylistItemRef:
    """One entry of a playlist being synced, in the terms the other servers can be asked for:
    a film by its own key, an episode by its show's key and its season and number."""

    item_type: str            # "movie", "episode" or "other"
    key: str
    title: str = ""
    show_key: str | None = None
    season: int = 0
    episode: int = 0
    #: Which entry of the playlist this is -- Plex's playlistItemID, Jellyfin/Emby's
    #: PlaylistItemId -- the handle for removing or moving it. A title can appear twice.
    entry_id: str = ""


#: How long edit_in_place waits for a server to list what was just added: tries, and seconds
#: apart; and how many passes it makes before giving up on the order.
SETTLE_TRIES, SETTLE_PAUSE, EDIT_TRIES = 10, 0.5, 3


def _pause(seconds: float) -> None:
    import time

    time.sleep(seconds)


def edit_in_place(client, playlist_id: str, wanted: list[tuple[str, object]]) -> bool:  # noqa: ANN001
    """Make a playlist hold exactly `wanted` -- see _edit_once -- and check it did. Emby 4.10 can
    list a playlist as it was a moment before the last edit (measured 2026-09-29: a removal by
    entry id then hit the wrong title, one run in eight), and every pass moves the playlist
    towards `wanted`, so a pass whose result doesn't read back right is simply run again."""
    import logging

    changed = False
    want = [key for key, _ in wanted]
    for attempt in range(EDIT_TRIES):
        if not _edit_once(client, playlist_id, wanted):
            return changed
        changed = True
        now = [ref.key for ref in client.playlist_items(playlist_id)]
        present = set(now)
        if now == [key for key in want if key in present]:     # right, less anything refused
            return True
        _pause(SETTLE_PAUSE * (attempt + 1))
    logging.getLogger(__name__).warning("Playlist %s still isn't in the wanted order after %d tries",
                                        playlist_id, EDIT_TRIES)
    return changed


def _edit_once(client, playlist_id: str, wanted: list[tuple[str, object]]) -> bool:  # noqa: ANN001
    """Make a playlist hold exactly `wanted` -- (item key, what the client adds) -- in that order,
    by removing, adding and moving entries rather than deleting and recreating it. The playlist
    keeps its id, its poster and its place in people's apps, and whoever tracks it by id (sync,
    the Franchisarr set) still finds it. Returns whether anything changed.

    Needs from the client: playlist_items (with entry ids), remove_playlist_entries,
    append_to_playlist and move_playlist_entry. Only titles not already there are added, so a
    server that quietly drops duplicates can't lose anything. A client whose server won't move
    entries (`can_move_playlist_entries` False: Jellyfin) gets the tail rewritten instead."""
    current = [(ref.entry_id, ref.key) for ref in client.playlist_items(playlist_id)]
    want_keys = [key for key, _ in wanted]
    if [key for _, key in current] == want_keys:
        return False
    if not getattr(client, "can_move_playlist_entries", True):
        # Keep what's already in order at the front; remove everything after it, then add the
        # rest in order. Adding a new film at the end -- the usual case -- removes nothing.
        same = 0
        while same < min(len(current), len(want_keys)) and current[same][1] == want_keys[same]:
            same += 1
        if current[same:]:
            client.remove_playlist_entries(playlist_id, [entry_id for entry_id, _ in current[same:]])
        if wanted[same:]:
            client.append_to_playlist(playlist_id, [raw for _, raw in wanted[same:]])
        return True
    needed: dict[str, int] = {}
    for key in want_keys:
        needed[key] = needed.get(key, 0) + 1
    keep: list[tuple[str, str]] = []
    remove: list[str] = []
    for entry_id, key in current:
        if needed.get(key, 0) > 0:
            needed[key] -= 1
            keep.append((entry_id, key))
        else:
            remove.append(entry_id)
    if remove:
        client.remove_playlist_entries(playlist_id, remove)
    have: dict[str, int] = {}
    for _, key in keep:
        have[key] = have.get(key, 0) + 1
    add = []
    for key, raw in wanted:
        if have.get(key, 0) > 0:
            have[key] -= 1
        else:
            add.append(raw)
    if add:
        client.append_to_playlist(playlist_id, add)
    # Now put it in order: read back the entries (the new ones' ids are the server's to give),
    # then walk the wanted order, moving whatever is out of place to where it belongs. Emby 4.10
    # sometimes lists an addition a moment late (measured 2026-09-29: two runs in five), and
    # ordering a list that's missing it leaves it at the end -- so wait until it's there.
    entries = [(ref.entry_id, ref.key) for ref in client.playlist_items(playlist_id)]
    for _ in range(SETTLE_TRIES):
        if len(entries) >= len(keep) + len(add):
            break
        _pause(SETTLE_PAUSE)
        entries = [(ref.entry_id, ref.key) for ref in client.playlist_items(playlist_id)]
    there: dict[str, int] = {}
    for _, key in entries:
        there[key] = there.get(key, 0) + 1
    order = []                 # the wanted order, less anything the server wouldn't take
    for key in want_keys:
        if there.get(key, 0) > 0:
            there[key] -= 1
            order.append(key)
    for index, key in enumerate(order):
        if entries[index][1] == key:
            continue
        at = next(i for i in range(index + 1, len(entries)) if entries[i][1] == key)
        entry = entries.pop(at)
        after = entries[index - 1][0] if index > 0 else None
        client.move_playlist_entry(playlist_id, entry[0], index, after)
        entries.insert(index, entry)
    return True
