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
from dataclasses import dataclass, field

import plexapi
from plexapi.exceptions import BadRequest, NotFound, Unauthorized
from plexapi.server import PlexServer
from requests.exceptions import RequestException

from app.clients.media_server import (
    MediaItem,
    MediaLibrary,
    MediaLibraryNotFoundError,
    MediaMovie,
    MediaServerError,
    MediaServerKind,
    MediaShow,
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
    return tuple(
        guid.id for guid in _attr(raw, "guids", ()) or () if guid.__dict__.get("id")
    )


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
    )


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
