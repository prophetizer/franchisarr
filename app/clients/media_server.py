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
