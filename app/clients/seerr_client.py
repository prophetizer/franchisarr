"""Overseerr and Jellyseerr, which share one API.

The subset used: `/status` to test a connection, `POST /request` to ask for a film or a series,
and `GET /request` to learn what has already been asked for. A request is identified by TMDb id
for both media types (Seerr looks the TVDB id up itself), and Seerr chooses the *arr, profile and
folder from its own settings -- there is nothing to offer the user beyond "request it".

Field names are from Overseerr's own OpenAPI document; Jellyseerr is a fork and keeps them.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from app.clients.radarr_client import _auth_failure_message
from app.logging_config import register_secret

DEFAULT_TIMEOUT = 15
#: Seerr's own vocabulary for a request's state.
STATUS_PENDING = 1
STATUS_APPROVED = 2
STATUS_DECLINED = 3


class SeerrError(RuntimeError):
    pass


class SeerrUnreachableError(SeerrError):
    pass


class SeerrAuthError(SeerrError):
    pass


@dataclass(frozen=True)
class SeerrRequestInfo:
    media_type: str      # "movie" or "tv"
    tmdb_id: int
    status: int


@dataclass(frozen=True)
class SeerrRequestResult:
    request_id: int
    status: int

    @property
    def needs_approval(self) -> bool:
        return self.status == STATUS_PENDING


class SeerrClient:
    def __init__(self, url: str, api_key: str, *, label: str = "Overseerr",
                 timeout: int = DEFAULT_TIMEOUT, session: requests.Session | None = None) -> None:
        self._base = url.rstrip("/")
        self._api_key = api_key.strip()
        self._label = label
        self._timeout = timeout
        self._session = session or requests.Session()
        register_secret(self._api_key)

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self._base}/api/v1{path}"
        try:
            response = self._session.request(
                method, url, headers={"X-Api-Key": self._api_key, "Accept": "application/json"},
                timeout=self._timeout, **kwargs,
            )
        except requests.RequestException as exc:
            raise SeerrUnreachableError(f"Couldn't reach {self._label} at {self._base}") from exc

        if response.status_code in (401, 403):
            raise SeerrAuthError(_auth_failure_message(response, self._base, self._label))
        if response.status_code == 404 and path != "/status":
            raise SeerrError(f"{self._label} has no endpoint at {path} — is this really {self._label}?")
        if response.status_code >= 400:
            raise SeerrError(_describe_failure(response, self._label))
        return response

    def _get_json(self, path: str, **kwargs):
        response = self._request("GET", path, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise SeerrError(f"{self._base} answered, but not with JSON — is that URL really {self._label}?") from exc

    # ---------------------------------------------------------------- reads

    def test_connection(self) -> str:
        """The instance's version, for "Test connection"."""
        payload = self._get_json("/status")
        version = payload.get("version") if isinstance(payload, dict) else None
        if not version:
            raise SeerrError(f"{self._base} answered, but doesn't look like {self._label}.")
        return str(version)

    def list_requests(self) -> list[SeerrRequestInfo]:
        """Every request that is pending or approved. Declined ones are left out: those are
        the ones the user may want to ask about again."""
        out: list[SeerrRequestInfo] = []
        skip, page = 0, 100
        while True:
            payload = self._get_json("/request", params={"take": page, "skip": skip, "filter": "all"})
            results = payload.get("results", []) if isinstance(payload, dict) else []
            for item in results:
                media = item.get("media") or {}
                tmdb_id, status = media.get("tmdbId"), item.get("status")
                if tmdb_id is None or status == STATUS_DECLINED:
                    continue
                media_type = "tv" if item.get("type") == "tv" or media.get("mediaType") == "tv" else "movie"
                out.append(SeerrRequestInfo(media_type=media_type, tmdb_id=int(tmdb_id), status=int(status or 0)))
            if len(results) < page:
                return out
            skip += page

    # ---------------------------------------------------------------- writes

    def request_movie(self, tmdb_id: int) -> SeerrRequestResult:
        return self._post_request({"mediaType": "movie", "mediaId": tmdb_id})

    def request_series(self, tmdb_id: int, *, seasons: list[int] | str = "all") -> SeerrRequestResult:
        return self._post_request({"mediaType": "tv", "mediaId": tmdb_id, "seasons": seasons})

    def _post_request(self, body: dict) -> SeerrRequestResult:
        response = self._request("POST", "/request", json=body)
        try:
            payload = response.json()
        except ValueError as exc:
            raise SeerrError(f"{self._label} accepted the request but answered with no detail.") from exc
        return SeerrRequestResult(request_id=int(payload.get("id", 0)), status=int(payload.get("status", 0)))


def _describe_failure(response: requests.Response, label: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"{label} returned {response.status_code}."
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if message:
            return f"{label} rejected the request: {message}"
    return f"{label} returned {response.status_code}."
