"""Jellyfin and Emby, through one client.

Jellyfin forked Emby in 2018 and the read API they share has not diverged in any way a scan
cares about. Measured on the developer's own instances (Jellyfin 10.11, Emby 4.9): the same
four requests, with the same header and the same response shapes, answered identically on both.
The differences that exist are cosmetic -- Emby leaves `ProductName` empty in `/System/Info`
and lists `boxsets` and `playlists` as libraries, which are skipped -- so the `kind` is
configuration, not detection.

Items carry their external ids directly in `ProviderIds` (99.7-100% had a TMDb id on both
servers), which is simpler and more complete than Plex's GUID parsing. Reads are paged, one
request per 500 items, with no per-item refetch to guard against.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import requests

from app.clients.media_server import (
    MediaLibrary,
    MediaLibraryNotFoundError,
    MediaMovie,
    MediaServerError,
    MediaServerKind,
    MediaShow,
)
from app.clients.plex_guid import ExternalIds
from app.logging_config import register_secret
from app.models import LibraryType

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
PAGE_SIZE = 500

#: Jellyfin's `CollectionType` / Emby's, for the two kinds of library a scan reads.
COLLECTION_TYPES = {"movies": LibraryType.MOVIE.value, "tvshows": LibraryType.SHOW.value}


class EmbyClientError(MediaServerError):
    """Any Jellyfin/Emby failure. The message is safe to show a user."""


class EmbyAuthError(EmbyClientError):
    """The API key was rejected."""


def _watched(item: dict) -> bool | None:
    """Played state from the UserData a user-scoped listing carries. A film is watched when
    played; a series when any of it has been (`Played` there means every episode)."""
    data = item.get("UserData")
    if not isinstance(data, dict):
        return None
    if data.get("Played"):
        return True
    percent = data.get("PlayedPercentage")
    if isinstance(percent, (int, float)) and percent > 0:
        return True
    unplayed = data.get("UnplayedItemCount")
    child_count = item.get("RecursiveItemCount") or item.get("ChildCount")
    if isinstance(unplayed, int) and isinstance(child_count, int) and child_count > 0:
        return unplayed < child_count
    return False


def _external_ids(provider_ids: dict | None) -> ExternalIds:
    """`ProviderIds` keys are capitalised inconsistently across plugins ("Tmdb", "tmdb",
    "TMDB"); compare case-insensitively."""
    ids = {str(k).lower(): str(v).strip() for k, v in (provider_ids or {}).items() if v}
    tmdb = ids.get("tmdb")
    tvdb = ids.get("tvdb")
    anidb = ids.get("anidb")
    return ExternalIds(
        tmdb_id=int(tmdb) if tmdb and tmdb.isdigit() else None,
        imdb_id=ids.get("imdb") or None,
        tvdb_id=int(tvdb) if tvdb and tvdb.isdigit() else None,
        anidb_id=int(anidb) if anidb and anidb.isdigit() else None,
    )


class EmbyLikeClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        kind: MediaServerKind = MediaServerKind.JELLYFIN,
        timeout: int = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
        watched_user: str | None = None,
    ) -> None:
        self.kind = kind
        #: Whose watched state to read. An API key belongs to no one, so the server has to be
        #: asked on behalf of a user; None means the first administrator.
        self._watched_user = (watched_user or "").strip() or None
        self._watched_user_id: str | None | bool = False  # False: not looked up yet
        self._base = base_url.rstrip("/")
        self._api_key = api_key.strip()
        self._timeout = timeout
        self._session = session or requests.Session()
        # Both servers accept the token in this header. The client identifiers are required by
        # Emby's auth middleware and harmless on Jellyfin.
        self._session.headers.update({
            "X-Emby-Token": self._api_key,
            "X-Emby-Client": "Franchisarr",
            "X-Emby-Device-Name": "Franchisarr",
            "X-Emby-Device-Id": "franchisarr",
            "X-Emby-Client-Version": "1",
            "Accept": "application/json",
        })
        register_secret(self._api_key)

    @property
    def label(self) -> str:
        return "Jellyfin" if self.kind == MediaServerKind.JELLYFIN else "Emby"

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        try:
            response = self._session.get(f"{self._base}{path}", params=params, timeout=self._timeout)
        except requests.RequestException as exc:
            # Generic on purpose: the key rides in a header, but the URL is worth not quoting.
            raise EmbyClientError(f"Could not reach {self.label} at {self._base}") from exc
        if response.status_code in (401, 403):
            raise EmbyAuthError(f"{self.label} rejected the API key.")
        if response.status_code == 404:
            raise MediaLibraryNotFoundError(f"{self.label} has nothing at {path}")
        if response.status_code >= 400:
            raise EmbyClientError(f"{self.label} returned {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise EmbyClientError(f"{self.label} returned a response that wasn't JSON") from exc

    # ---------------------------------------------------------------- MediaServerClient

    def test_connection(self) -> str:
        info = self._get("/System/Info")
        if not isinstance(info, dict):
            raise EmbyClientError(f"{self.label} answered /System/Info in an unexpected shape")
        name = info.get("ServerName") or info.get("ProductName") or self.label
        version = info.get("Version") or "?"
        return f"{name} ({self.label} {version})"

    def list_libraries(self) -> list[MediaLibrary]:
        folders = self._get("/Library/VirtualFolders")
        libraries: list[MediaLibrary] = []
        for folder in folders if isinstance(folders, list) else []:
            if not isinstance(folder, dict):
                continue
            library_type = COLLECTION_TYPES.get(str(folder.get("CollectionType") or "").lower())
            if library_type is None:
                continue  # boxsets, playlists, music, photos: nothing here to scan
            key = folder.get("ItemId")
            if not key:
                continue
            libraries.append(MediaLibrary(key=str(key), title=str(folder.get("Name") or key),
                                          library_type=library_type))
        return libraries

    def list_users(self) -> list[dict]:
        """Accounts on the server: {"id", "name", "is_admin"}."""
        payload = self._get("/Users")
        users = []
        for user in payload if isinstance(payload, list) else []:
            if isinstance(user, dict) and user.get("Id"):
                users.append({
                    "id": str(user["Id"]),
                    "name": str(user.get("Name") or ""),
                    "is_admin": bool((user.get("Policy") or {}).get("IsAdministrator")),
                })
        return users

    def watched_user_id(self) -> str | None:
        """The account whose play state the listings carry, looked up once per client."""
        if self._watched_user_id is False:
            self._watched_user_id = None
            try:
                users = self.list_users()
            except EmbyClientError as exc:
                logger.warning("%s: could not list users, so watched state is unknown: %s",
                               self.label, exc)
                return None
            if self._watched_user:
                match = next((u for u in users if u["name"].lower() == self._watched_user.lower()), None)
                if match is None:
                    logger.warning("%s has no user named %r; watched state is unknown",
                                   self.label, self._watched_user)
            else:
                match = next((u for u in users if u["is_admin"]), None) or (users[0] if users else None)
            self._watched_user_id = match["id"] if match else None
        return self._watched_user_id

    def _iter_items(self, library_key: str | int, item_type: str) -> Iterator[dict]:
        start = 0
        user_id = self.watched_user_id()
        while True:
            params = {
                "ParentId": str(library_key),
                "Recursive": "true",
                "IncludeItemTypes": item_type,
                "Fields": "ProviderIds,ProductionYear",
                "StartIndex": start,
                "Limit": PAGE_SIZE,
            }
            if user_id:
                params["UserId"] = user_id  # makes each item carry that account's UserData
            page = self._get("/Items", params)
            items = page.get("Items") if isinstance(page, dict) else None
            if not items:
                return
            yield from (i for i in items if isinstance(i, dict) and i.get("Id"))
            start += len(items)
            if start >= int(page.get("TotalRecordCount") or 0):
                return

    def iter_movies(self, library_key: str | int) -> Iterator[MediaMovie]:
        for item in self._iter_items(library_key, "Movie"):
            yield MediaMovie(
                item_key=str(item["Id"]),
                title=str(item.get("Name") or ""),
                year=item.get("ProductionYear") if isinstance(item.get("ProductionYear"), int) else None,
                external_ids=_external_ids(item.get("ProviderIds")),
                watched=_watched(item),
            )

    def iter_shows(self, library_key: str | int) -> Iterator[MediaShow]:
        for item in self._iter_items(library_key, "Series"):
            yield MediaShow(
                item_key=str(item["Id"]),
                title=str(item.get("Name") or ""),
                year=item.get("ProductionYear") if isinstance(item.get("ProductionYear"), int) else None,
                external_ids=_external_ids(item.get("ProviderIds")),
                watched=_watched(item),
            )

    # ---------------------------------------------------------------- sign-in

    def authenticate(self, username: str, password: str) -> dict:
        """Sign a person in with their own credentials on this server.

        Returns {"user_id", "username", "is_admin"}. This is the whole authorisation check: an
        account that can sign in here is an account on *this* server, which is what "sign in
        with Jellyfin" has to mean -- the equivalent of the Plex server-access check.
        """
        headers = {k: v for k, v in self._session.headers.items() if k != "X-Emby-Token"}
        headers["Authorization"] = ('MediaBrowser Client="Franchisarr", Device="Franchisarr", '
                                    'DeviceId="franchisarr", Version="1"')
        try:
            response = requests.post(
                f"{self._base}/Users/AuthenticateByName",
                json={"Username": username, "Pw": password},
                headers=headers, timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise EmbyClientError(f"Could not reach {self.label} at {self._base}") from exc
        if response.status_code in (401, 403):
            raise EmbyAuthError(f"{self.label} did not accept that username and password.")
        if response.status_code >= 400:
            raise EmbyClientError(f"{self.label} returned {response.status_code} on sign-in")
        payload = response.json()
        user = payload.get("User") or {}
        if not user.get("Id"):
            raise EmbyClientError(f"{self.label} signed in but returned no user")
        return {
            "user_id": str(user["Id"]),
            "username": str(user.get("Name") or username),
            "is_admin": bool((user.get("Policy") or {}).get("IsAdministrator")),
        }
