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

from datetime import date

import requests

from app import __version__

from app.clients.media_server import (
    PlaylistEntry,
    PlaylistInfo,
    PlaylistItemRef,
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


#: Item ids per request when fetching or adding to a playlist; keeps the URL short.
PLAYLIST_CHUNK = 100


def _premiere(item: dict) -> date | None:
    """An item's release/air date from PremiereDate, else 1 January of its ProductionYear."""
    raw = item.get("PremiereDate")
    if raw:
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            pass
    year = item.get("ProductionYear")
    return date(int(year), 1, 1) if year else None


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
        self._session.headers["Accept"] = "application/json"
        if kind == MediaServerKind.JELLYFIN:
            # Jellyfin 12 refuses the legacy X-Emby-Token header outright (401) and takes the key
            # only in its Authorization scheme -- which every Jellyfin since 10.x also accepts, so
            # this is the one form that works on old and new alike.
            self._session.headers["Authorization"] = (
                'MediaBrowser Client="Franchisarr", Device="Franchisarr", DeviceId="franchisarr", '
                f'Version="{__version__}", Token="{self._api_key}"'
            )
        else:
            # Emby (4.10) still wants X-Emby-Token, with client identifiers its auth middleware
            # requires.
            self._session.headers.update({
                "X-Emby-Token": self._api_key,
                "X-Emby-Client": "Franchisarr",
                "X-Emby-Device-Name": "Franchisarr",
                "X-Emby-Device-Id": "franchisarr",
                "X-Emby-Client-Version": "1",
            })
        register_secret(self._api_key)

    @property
    def label(self) -> str:
        return "Jellyfin" if self.kind == MediaServerKind.JELLYFIN else "Emby"

    def _params(self, params: dict | None) -> dict | None:
        """Jellyfin 12 matches query parameters case-sensitively and documents them camelCase:
        `UserId` is ignored on some endpoints and a 400 on others, where `userId` works. Earlier
        Jellyfin and Emby match case-insensitively, so Jellyfin always gets camelCase and Emby
        keeps the PascalCase its own docs use."""
        if not params or self.kind != MediaServerKind.JELLYFIN:
            return params
        return {key[:1].lower() + key[1:]: value for key, value in params.items()}

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        try:
            response = self._session.get(f"{self._base}{path}", params=self._params(params),
                                         timeout=self._timeout)
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

    def _send(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None,
              data: bytes | None = None, headers: dict | None = None) -> dict | None:
        """A write, with the same error mapping as _get. Returns the JSON body if there is one."""
        try:
            response = self._session.request(method, f"{self._base}{path}", params=self._params(params), json=json,
                                             data=data, headers=headers, timeout=self._timeout)
        except requests.RequestException as exc:
            raise EmbyClientError(f"Could not reach {self.label} at {self._base}") from exc
        if response.status_code in (401, 403):
            raise EmbyAuthError(f"{self.label} refused that ({response.status_code}).")
        if response.status_code >= 400:
            raise EmbyClientError(f"{self.label} returned {response.status_code} for {method} {path}")
        try:
            return response.json() if response.content else None
        except ValueError:
            return None

    # ---------------------------------------------------------------- playlists

    def _playlists(self) -> list[dict]:
        """The watched-as user's playlists (id and name)."""
        found = self._get("/Items", {"IncludeItemTypes": "Playlist", "Recursive": "true",
                                     "UserId": self.watched_user_id(), "Fields": "ChildCount"})
        return list(found.get("Items") or []) if isinstance(found, dict) else []

    def _every_playlist(self) -> list[dict]:
        """Every playlist on the server, whoever owns it: an interrupted earlier run, or a changed
        "watched as" user, can leave one of ours that the user's own view doesn't show."""
        found = self._get("/Items", {"IncludeItemTypes": "Playlist", "Recursive": "true"})
        return list(found.get("Items") or []) if isinstance(found, dict) else []

    def _playlist_id(self, title: str) -> str | None:
        return next((p["Id"] for p in self._playlists() if p.get("Name") == title), None)

    def playlist_entries(self, films: list[str], shows: list[str]) -> list[PlaylistEntry]:
        """Films and every regular episode of the shows, with air dates: films in batches by id,
        then one request per show for its episodes."""
        user = self.watched_user_id()
        entries: list[PlaylistEntry] = []
        for start in range(0, len(films), PLAYLIST_CHUNK):
            batch = self._get("/Items", {"Ids": ",".join(films[start:start + PLAYLIST_CHUNK]),
                                         "Fields": "PremiereDate,ProductionYear", "UserId": user})
            for item in batch.get("Items") or []:
                entries.append(PlaylistEntry(raw=item["Id"], aired=_premiere(item), key=item["Id"]))
        for show_id in shows:
            try:
                episodes = self._get(f"/Shows/{show_id}/Episodes", {"UserId": user, "Fields": "PremiereDate"})
            except MediaLibraryNotFoundError:
                logger.warning("Show %s is no longer on %s; skipped", show_id, self.label)
                continue
            previous: date | None = None
            rows = sorted(episodes.get("Items") or [],
                          key=lambda e: (e.get("ParentIndexNumber") or 0, e.get("IndexNumber") or 0))
            for item in rows:
                season = int(item.get("ParentIndexNumber") or 0)
                if season == 0:
                    continue     # specials: not part of the run
                aired = _premiere(item) or previous
                previous = aired or previous
                entries.append(PlaylistEntry(raw=item["Id"], aired=aired, show_key=str(show_id), key=item["Id"],
                                             season=season, episode=int(item.get("IndexNumber") or 0)))
        return entries

    def create_playlist(self, title: str, items: list) -> str:  # noqa: ANN001 - item ids
        """A new playlist of `items` (ids), in order, in the watched-as user's account; its id.
        Never touches another playlist, same-named ones included."""
        user = self.watched_user_id()
        before = {p.get("Id") for p in self._playlists()}
        first = [str(i) for i in items[:PLAYLIST_CHUNK]]
        if self.kind == MediaServerKind.JELLYFIN:
            created = self._send("POST", "/Playlists", json={
                "Name": title, "Ids": first, "UserId": user, "MediaType": "Video"})
        else:
            created = self._send("POST", "/Playlists", params={
                "Name": title, "Ids": ",".join(first), "UserId": user, "MediaType": "Video"})
        # If the server doesn't answer with the id, the new one is the playlist that wasn't
        # there before -- not whichever happens to share the name.
        playlist_id = (created or {}).get("Id") or next(
            (p["Id"] for p in self._playlists() if p.get("Id") not in before and p.get("Name") == title), None)
        if not playlist_id:
            raise EmbyClientError(f"{self.label} didn't say which playlist it made")
        for start in range(PLAYLIST_CHUNK, len(items), PLAYLIST_CHUNK):
            chunk = ",".join(str(i) for i in items[start:start + PLAYLIST_CHUNK])
            self._send("POST", f"/Playlists/{playlist_id}/Items", params={"Ids": chunk, "UserId": user})
        return str(playlist_id)

    # ---------------------------------------------------------------- playlist sync

    def list_playlists(self) -> list[PlaylistInfo]:
        """The watched-as user's playlists."""
        return [PlaylistInfo(id=str(p["Id"]), title=p.get("Name", ""),
                             video=(p.get("MediaType") or "Video") not in ("Audio", "Photo"),
                             count=int(p.get("ChildCount") or 0))
                for p in self._playlists() if p.get("Id")]

    def playlist_items(self, playlist_id: str) -> list[PlaylistItemRef]:
        found = self._get(f"/Playlists/{playlist_id}/Items", {"UserId": self.watched_user_id()})
        refs = []
        for row in (found.get("Items") or []) if isinstance(found, dict) else []:
            kind, key = row.get("Type"), str(row.get("Id", ""))
            entry = str(row.get("PlaylistItemId") or "")
            if kind == "Movie":
                refs.append(PlaylistItemRef("movie", key, row.get("Name", ""), entry_id=entry))
            elif kind == "Episode":
                season, number = int(row.get("ParentIndexNumber") or 0), int(row.get("IndexNumber") or 0)
                refs.append(PlaylistItemRef("episode", key, f"{row.get('SeriesName', '')} S{season:02d}E{number:02d}",
                                            show_key=str(row.get("SeriesId") or ""), season=season, episode=number,
                                            entry_id=entry))
            else:
                refs.append(PlaylistItemRef("other", key, row.get("Name", ""), entry_id=entry))
        return refs

    # Editing in place (media_server.edit_in_place), by PlaylistItemId: the same endpoints on
    # Jellyfin and Emby -- except that Jellyfin 12.1 answers Move with a 400 ("Error processing
    # request") whichever id it's given, with or without a user (measured 2026-09-29), so on
    # Jellyfin the order is fixed by rewriting the tail.

    @property
    def can_move_playlist_entries(self) -> bool:
        return self.kind != MediaServerKind.JELLYFIN

    def remove_playlist_entries(self, playlist_id: str, entry_ids: list[str]) -> None:
        for start in range(0, len(entry_ids), PLAYLIST_CHUNK):
            self._send("DELETE", f"/Playlists/{playlist_id}/Items",
                       params={"EntryIds": ",".join(entry_ids[start:start + PLAYLIST_CHUNK])})

    def append_to_playlist(self, playlist_id: str, items: list) -> None:  # noqa: ANN001 - item ids
        user = self.watched_user_id()
        for start in range(0, len(items), PLAYLIST_CHUNK):
            chunk = ",".join(str(i) for i in items[start:start + PLAYLIST_CHUNK])
            self._send("POST", f"/Playlists/{playlist_id}/Items", params={"Ids": chunk, "UserId": user})

    def move_playlist_entry(self, playlist_id: str, entry_id: str, index: int, after: str | None) -> None:
        """Jellyfin and Emby place an entry at an index."""
        self._send("POST", f"/Playlists/{playlist_id}/Items/{entry_id}/Move/{int(index)}")

    def delete_playlist_id(self, playlist_id: str) -> None:
        """Delete it if it's still there; one someone already removed is no error. (_send maps a
        404 to a plain client error, so ask first rather than catch it.)"""
        if any(str(p.get("Id")) == str(playlist_id) for p in self._playlists()):
            self._send("DELETE", f"/Items/{playlist_id}")

    def playlist_poster(self, playlist_id: str) -> bytes | None:
        """The playlist's primary image, if it has one."""
        try:
            response = self._session.get(f"{self._base}/Items/{playlist_id}/Images/Primary", timeout=self._timeout)
        except requests.RequestException:
            return None
        return response.content if response.status_code == 200 and response.content else None

    def set_playlist_poster_id(self, playlist_id: str, image: bytes) -> bool:
        import base64

        self._send("POST", f"/Items/{playlist_id}/Images/Primary", data=base64.b64encode(image),
                   headers={"Content-Type": "image/jpeg"})
        return True

    def set_playlist_poster(self, title: str, image: bytes) -> bool:
        """Upload `image` (JPEG) as the playlist's primary image. Both servers take the image
        base64-encoded in the body."""
        import base64

        playlist_id = self._playlist_id(title)
        if playlist_id is None:
            return False
        self._send("POST", f"/Items/{playlist_id}/Images/Primary", data=base64.b64encode(image),
                   headers={"Content-Type": "image/jpeg"})
        return True

    def playlist_titles(self) -> list[str]:
        return [p.get("Name", "") for p in self._playlists()]

    def playlists_ending(self, suffix: str) -> list[str]:
        return sorted(p.get("Name", "") for p in self._every_playlist()
                      if p.get("Name", "").endswith(suffix))

    def delete_playlists(self, suffix: str) -> list[str]:
        """Delete every playlist on the server whose name ends with `suffix`, server-wide: an
        interrupted earlier run, or a changed "watched as" user, can leave one of ours that the
        user's own view doesn't show. Only Franchisarr names playlists "... (Franchisarr)". The
        names deleted, sorted."""
        gone = []
        for playlist in self._every_playlist():
            name = playlist.get("Name", "")
            if name.endswith(suffix):
                self._send("DELETE", f"/Items/{playlist['Id']}")
                gone.append(name)
        return sorted(gone)

    def delete_all_playlists(self) -> list[str]:
        """Every playlist the watched-as user sees (`_playlists` is that user's view, unlike the
        server-wide listing delete_playlists uses). Jellyfin 12 says nothing
        about who owns a playlist -- no owner field, and /Playlists/{id} answers 400 -- so one
        shared with this user can't be told from their own and is included; the confirmation
        says so, and lists every title first (michael's call, 0.37.0)."""
        gone = []
        for playlist in self._playlists():
            self._send("DELETE", f"/Items/{playlist['Id']}")
            gone.append(playlist.get("Name", ""))
        return sorted(gone)

    def playlist_counts(self, title: str) -> tuple[int, int, int] | None:
        playlist_id = self._playlist_id(title)
        if playlist_id is None:
            return None
        items = self._get(f"/Playlists/{playlist_id}/Items", {"UserId": self.watched_user_id()})
        rows = items.get("Items") or [] if isinstance(items, dict) else []
        episodes = [r for r in rows if r.get("Type") == "Episode"]
        return (sum(1 for r in rows if r.get("Type") == "Movie"),
                len({r.get("SeriesId") for r in episodes}), len(episodes))

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
        headers = {k: v for k, v in self._session.headers.items()
                   if k not in ("X-Emby-Token", "Authorization")}
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
