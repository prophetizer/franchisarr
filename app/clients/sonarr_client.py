"""Sonarr v3 API client, instance-aware.

Mirrors the Radarr client, with one thing that is genuinely different and was worth checking
rather than assuming (technical challenge #22): the season monitoring mode.

Sonarr's `addOptions.monitor` takes a value from its own `MonitorTypes` enum, serialised
camelCase. Confirmed against a real Sonarr 4.0.19 and its source:

    Unknown, All, Future, Missing, Existing, FirstSeason, LastSeason,
    LatestSeason (obsolete), Pilot, Recent, MonitorSpecials, UnmonitorSpecials, None, Skip

The three friendly options the UI offers do map onto that, but *not by name* -- Franchisarr
stores `future_only` and `first_season` where Sonarr wants `future` and `firstSeason`. Sending
our own values verbatim would fail on two of the three, which is exactly what the plan warned
about, so the translation is explicit and tested.

Series are looked up by TMDb id: verified that Sonarr's `tmdb:` term uses TMDb's real id space,
so a spin-off suggestion can go straight to Sonarr with no TMDb-to-TVDB conversion in between.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from app.logging_config import register_secret
from app.models import MonitorMode

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20

#: Franchisarr's stored monitor modes -> Sonarr's MonitorTypes values.
MONITOR_MODE_TO_SONARR: dict[str, str] = {
    MonitorMode.ALL.value: "all",
    MonitorMode.FUTURE_ONLY.value: "future",
    MonitorMode.FIRST_SEASON.value: "firstSeason",
}

#: What each option means, for the UI to explain rather than making the user guess.
MONITOR_MODE_LABELS: dict[str, str] = {
    MonitorMode.ALL.value: "All seasons",
    MonitorMode.FUTURE_ONLY.value: "Future episodes only",
    MonitorMode.FIRST_SEASON.value: "First season only",
}


class SonarrError(RuntimeError):
    """Any Sonarr failure. The message is safe to show a user."""


class SonarrUnreachableError(SonarrError):
    """The instance did not answer."""


class SonarrAuthError(SonarrError):
    """The API key was rejected."""


class SeriesAlreadyAddedError(SonarrError):
    """Sonarr already tracks this show."""


def to_sonarr_monitor(mode: str) -> str:
    """Translate a stored monitor mode. Unknown values fall back to `all` rather than being sent
    through, since Sonarr rejects anything outside its enum and 'monitor everything' is the least
    surprising default."""
    resolved = MONITOR_MODE_TO_SONARR.get(mode)
    if resolved is None:
        logger.warning("Unknown monitor mode %r; falling back to 'all'", mode)
        return "all"
    return resolved


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
class SonarrSeriesInfo:
    tmdb_id: int | None
    tvdb_id: int | None
    title: str
    monitored: bool = True


class SonarrClient:
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
            raise SonarrUnreachableError(f"Couldn't reach Sonarr at {self._base}") from exc

        if response.status_code in (401, 403):
            raise SonarrAuthError(_auth_failure_message(response, self._base, "Sonarr"))
        if response.status_code >= 400:
            raise SonarrError(_describe_failure(response))
        return response

    def _get_json(self, path: str, **kwargs):
        response = self._request("GET", path, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise SonarrError(
                f"{self._base} answered, but not with JSON — is that URL really Sonarr?"
            ) from exc

    # ---------------------------------------------------------------- reads

    def test_connection(self) -> str:
        payload = self._get_json("/system/status")
        version = payload.get("version") if isinstance(payload, dict) else None
        if not version:
            raise SonarrError(f"{self._base} answered, but doesn't look like Sonarr.")
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

    def series(self) -> list[SonarrSeriesInfo]:
        return [
            SonarrSeriesInfo(
                tmdb_id=int(item["tmdbId"]) if item.get("tmdbId") else None,
                tvdb_id=int(item["tvdbId"]) if item.get("tvdbId") else None,
                title=str(item.get("title") or ""),
                monitored=bool(item.get("monitored", True)),
            )
            for item in self._get_json("/series")
            if isinstance(item, dict)
        ]

    def queued_tmdb_ids(self) -> set[int]:
        payload = self._get_json("/queue", params={"pageSize": 1000, "includeSeries": "true"})
        records = payload.get("records", payload) if isinstance(payload, dict) else payload
        found: set[int] = set()
        for record in records or []:
            if not isinstance(record, dict):
                continue
            series = record.get("series") or {}
            tmdb_id = series.get("tmdbId")
            if tmdb_id:
                found.add(int(tmdb_id))
        return found

    def lookup(self, tmdb_id: int) -> dict:
        payload = self._get_json("/series/lookup", params={"term": f"tmdb:{tmdb_id}"})
        if not payload:
            raise SonarrError(f"Sonarr couldn't find TMDb id {tmdb_id}.")
        first = payload[0] if isinstance(payload, list) else payload
        if not isinstance(first, dict):
            raise SonarrError(f"Sonarr returned an unexpected lookup result for {tmdb_id}.")
        return first

    # ---------------------------------------------------------------- writes

    def ensure_tag(self, label: str = "franchisarr") -> int | None:
        """The id of a tag, creating it if needed. None if tags are unavailable -- tagging is a
        courtesy to the person looking at their library later, never a reason an add fails."""
        try:
            for tag in self._get_json("/tag") or []:
                if isinstance(tag, dict) and str(tag.get("label", "")).lower() == label:
                    return int(tag["id"])
            created = self._request("POST", "/tag", json={"label": label}).json()
            return int(created["id"])
        except Exception as exc:  # noqa: BLE001 - deliberately broad: see docstring
            logger.debug("Could not ensure tag %r: %s", label, exc)
            return None

    def add_series(
        self,
        tmdb_id: int,
        *,
        quality_profile_id: int,
        root_folder_path: str,
        monitor_mode: str = MonitorMode.ALL.value,
        season_folder: bool = True,
        search_on_add: bool = True,
    ) -> SonarrSeriesInfo:
        """Add a series, monitored and searched immediately by default."""
        payload = self.lookup(tmdb_id)

        if payload.get("id"):
            raise SeriesAlreadyAddedError(
                f"{payload.get('title') or tmdb_id} is already in this Sonarr instance."
            )

        tag_id = self.ensure_tag()
        payload.update(
            {
                "tags": [tag_id] if tag_id is not None else payload.get("tags") or [],
                "qualityProfileId": quality_profile_id,
                "rootFolderPath": root_folder_path,
                "monitored": True,
                "seasonFolder": season_folder,
                "addOptions": {
                    # The translation that challenge #22 exists for.
                    "monitor": to_sonarr_monitor(monitor_mode),
                    "searchForMissingEpisodes": search_on_add,
                    "searchForCutoffUnmetEpisodes": False,
                },
            }
        )

        response = self._request("POST", "/series", json=payload)
        try:
            created = response.json()
        except ValueError:
            created = {}

        logger.info(
            "Added tmdb:%s to Sonarr at %s (monitor=%s, search=%s)",
            tmdb_id, self._base, to_sonarr_monitor(monitor_mode), search_on_add,
        )
        return SonarrSeriesInfo(
            tmdb_id=int(created.get("tmdbId", tmdb_id)),
            tvdb_id=int(created["tvdbId"]) if created.get("tvdbId") else None,
            title=str(created.get("title") or payload.get("title") or ""),
            monitored=bool(created.get("monitored", True)),
        )


def _auth_failure_message(response: requests.Response, base: str, app: str) -> str:
    """Explain a 401/403, distinguishing the app from something standing in front of it.

    Sonarr answers with JSON. A forward-auth proxy -- Authelia, Authentik, Cloudflare Access,
    oauth2-proxy -- answers with an HTML login page or a redirect to one, and plenty of this
    audience puts exactly that in front of their *arr apps. Reporting "your API key was rejected"
    in that situation sends someone to check a credential that was never the problem.
    """
    content_type = response.headers.get("content-type", "")
    body = (response.text or "")[:400].lstrip()
    looks_like_a_login_page = (
        "text/html" in content_type.lower() or body.startswith(("<", "<!DOCTYPE", "<!doctype"))
    )

    if looks_like_a_login_page:
        return (
            f"{base} is behind an authentication proxy, not answering as Sonarr. "
            f"Franchisarr sends an API key, which a login-page proxy doesn't understand. "
            f"Either point Franchisarr at Sonarr directly on your internal network, or add a "
            f"bypass rule in the proxy for /api so API-key requests are let through."
        )
    return f"Sonarr rejected the API key for this instance."


def _describe_failure(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"Sonarr returned {response.status_code}."

    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            message = first.get("errorMessage") or first.get("message")
            if message:
                return f"Sonarr rejected the request: {message}"
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if message:
            return f"Sonarr rejected the request: {message}"
    return f"Sonarr returned {response.status_code}."
