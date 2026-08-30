"""Radarr v3 API client, instance-aware.

There is never "the Radarr" (docs/DEVELOPMENT.md convention 4) -- a client is constructed per instance,
and callers pass the instance they mean.

Adding is done by looking the film up through Radarr's own `/movie/lookup` and posting what it
gives back, rather than by assembling a payload ourselves. Radarr's add endpoint wants fields
that only its metadata layer knows (title slug, images, the year it recognises), and hand-built
payloads are exactly what breaks when Radarr changes a required field. Letting Radarr describe
the film and then adding our four decisions to it keeps this working across versions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from app.logging_config import register_secret

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20

#: Radarr's own default. "released" avoids grabbing a cam rip the day a film hits cinemas.
DEFAULT_MINIMUM_AVAILABILITY = "released"


class RadarrError(RuntimeError):
    """Any Radarr failure. The message is safe to show a user."""


class RadarrUnreachableError(RadarrError):
    """The instance did not answer -- down, wrong URL, wrong port, DNS, TLS."""


class RadarrAuthError(RadarrError):
    """The API key was rejected."""


class MovieAlreadyAddedError(RadarrError):
    """Radarr already has this film. Not really a failure -- usually a stale gap list."""


@dataclass(frozen=True)
class QualityProfile:
    id: int
    name: str


@dataclass(frozen=True)
class RootFolder:
    path: str
    free_space: int | None = None
    accessible: bool = True

    @property
    def free_space_label(self) -> str:
        if self.free_space is None:
            return ""
        gigabytes = self.free_space / (1024**3)
        if gigabytes >= 1024:
            return f"{gigabytes / 1024:.1f} TB free"
        return f"{gigabytes:.0f} GB free"


@dataclass(frozen=True)
class RadarrMovieInfo:
    tmdb_id: int
    title: str
    monitored: bool = True
    has_file: bool = False


class RadarrClient:
    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        self._base = url.rstrip("/")
        self._api_key = api_key.strip()
        self._timeout = timeout
        self._session = session or requests.Session()
        register_secret(self._api_key)

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self._base}/api/v3{path}"
        try:
            response = self._session.request(
                method,
                url,
                headers={"X-Api-Key": self._api_key, "Accept": "application/json"},
                timeout=self._timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            # Generic on purpose: this reaches a UI, and transport errors carry request detail.
            raise RadarrUnreachableError(f"Couldn't reach Radarr at {self._base}") from exc

        if response.status_code in (401, 403):
            raise RadarrAuthError("Radarr rejected the API key for this instance.")
        if response.status_code == 404 and path != "/system/status":
            raise RadarrError(f"Radarr has no endpoint at {path} — is this really Radarr v3+?")
        if response.status_code >= 400:
            raise RadarrError(_describe_failure(response))

        return response

    def _get_json(self, path: str, **kwargs):
        response = self._request("GET", path, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise RadarrError(
                f"{self._base} answered, but not with JSON — is that URL really Radarr?"
            ) from exc

    # ---------------------------------------------------------------- reads

    def test_connection(self) -> str:
        """Return the instance's version string. Used by "Test Connection" before saving."""
        payload = self._get_json("/system/status")
        version = payload.get("version") if isinstance(payload, dict) else None
        if not version:
            raise RadarrError(f"{self._base} answered, but doesn't look like Radarr.")
        return str(version)

    def quality_profiles(self) -> list[QualityProfile]:
        return [
            QualityProfile(id=int(item["id"]), name=str(item.get("name") or item["id"]))
            for item in self._get_json("/qualityprofile")
            if isinstance(item, dict) and item.get("id") is not None
        ]

    def root_folders(self) -> list[RootFolder]:
        return [
            RootFolder(
                path=str(item["path"]),
                free_space=item.get("freeSpace"),
                accessible=bool(item.get("accessible", True)),
            )
            for item in self._get_json("/rootfolder")
            if isinstance(item, dict) and item.get("path")
        ]

    def movies(self) -> list[RadarrMovieInfo]:
        """Everything this instance is tracking."""
        return [
            RadarrMovieInfo(
                tmdb_id=int(item["tmdbId"]),
                title=str(item.get("title") or ""),
                monitored=bool(item.get("monitored", True)),
                has_file=bool(item.get("hasFile", False)),
            )
            for item in self._get_json("/movie")
            if isinstance(item, dict) and item.get("tmdbId")
        ]

    def queued_tmdb_ids(self) -> set[int]:
        """Films already downloading. `hide_if_queued` decides whether these count as owned."""
        payload = self._get_json("/queue", params={"pageSize": 1000, "includeMovie": "true"})
        records = payload.get("records", payload) if isinstance(payload, dict) else payload
        found: set[int] = set()
        for record in records or []:
            if not isinstance(record, dict):
                continue
            movie = record.get("movie") or {}
            tmdb_id = movie.get("tmdbId") or record.get("tmdbId")
            if tmdb_id:
                found.add(int(tmdb_id))
        return found

    def lookup(self, tmdb_id: int) -> dict:
        """Ask Radarr to describe a film, in its own terms."""
        payload = self._get_json("/movie/lookup", params={"term": f"tmdb:{tmdb_id}"})
        if not payload:
            raise RadarrError(f"Radarr couldn't find TMDb id {tmdb_id}.")
        first = payload[0] if isinstance(payload, list) else payload
        if not isinstance(first, dict):
            raise RadarrError(f"Radarr returned an unexpected lookup result for {tmdb_id}.")
        return first

    # ---------------------------------------------------------------- writes

    def add_movie(
        self,
        tmdb_id: int,
        *,
        quality_profile_id: int,
        root_folder_path: str,
        monitored: bool = True,
        search_on_add: bool = True,
        minimum_availability: str = DEFAULT_MINIMUM_AVAILABILITY,
    ) -> RadarrMovieInfo:
        """Add a film, monitored and searched immediately by default.

        That default matches adding through Radarr's own UI with "search on add" ticked, which is
        what someone clicking "Add" here means (PROJECT_PLAN.md decision log).
        """
        payload = self.lookup(tmdb_id)

        if payload.get("id"):
            # Radarr gives an existing library id, meaning it already tracks this film.
            raise MovieAlreadyAddedError(
                f"{payload.get('title') or tmdb_id} is already in this Radarr instance."
            )

        payload.update(
            {
                "qualityProfileId": quality_profile_id,
                "rootFolderPath": root_folder_path,
                "monitored": monitored,
                "minimumAvailability": minimum_availability,
                "addOptions": {
                    "searchForMovie": search_on_add,
                    "monitor": "movieOnly",
                },
            }
        )

        response = self._request("POST", "/movie", json=payload)
        try:
            created = response.json()
        except ValueError:
            created = {}

        logger.info(
            "Added tmdb:%s to Radarr at %s (search=%s)", tmdb_id, self._base, search_on_add
        )
        return RadarrMovieInfo(
            tmdb_id=int(created.get("tmdbId", tmdb_id)),
            title=str(created.get("title") or payload.get("title") or ""),
            monitored=bool(created.get("monitored", monitored)),
            has_file=bool(created.get("hasFile", False)),
        )


def _describe_failure(response: requests.Response) -> str:
    """Radarr reports validation problems in a list of objects; surface the useful part."""
    try:
        payload = response.json()
    except ValueError:
        return f"Radarr returned {response.status_code}."

    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            message = first.get("errorMessage") or first.get("message")
            if message:
                return f"Radarr rejected the request: {message}"
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if message:
            return f"Radarr rejected the request: {message}"
    return f"Radarr returned {response.status_code}."
