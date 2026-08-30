"""TMDb API v3 client.

Kept behind a clean boundary on purpose: PROJECT_PLAN.md commits to TMDb as the only metadata
source for v1, with an optional TVDb enrichment layer possible later. Services depend on the
typed results here, not on TMDb's JSON shapes.

Every user brings their own key, so this client has to be good at explaining what's wrong with
one (technical challenge #11) -- a wrong-but-plausible key is the single most likely support
question this project will ever get.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

import requests

from app.logging_config import register_secret

logger = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_TIMEOUT = 15

#: TMDb tolerates roughly 40-50 requests/second. Staying well under that costs nothing on a
#: cache-backed scan and keeps a large first run from looking like abuse (technical challenge #4).
MAX_REQUESTS_PER_SECOND = 20

#: A 429 should be rare given the limiter, but TMDb's own accounting is what counts.
MAX_RETRIES = 3


class TmdbError(RuntimeError):
    """Any TMDb failure. Its message is safe to show a user."""


class TmdbAuthError(TmdbError):
    """The API key was rejected, or isn't the kind of key we need."""


class TmdbNotFound(TmdbError):
    """No such movie/collection. Usually normal, not an error worth surfacing."""


@dataclass(frozen=True)
class TmdbMovieSummary:
    tmdb_id: int
    title: str
    release_date: str | None = None

    @property
    def year(self) -> int | None:
        if self.release_date and len(self.release_date) >= 4 and self.release_date[:4].isdigit():
            return int(self.release_date[:4])
        return None


@dataclass(frozen=True)
class TmdbMovieDetails:
    tmdb_id: int
    title: str
    release_date: str | None
    collection_id: int | None
    collection_name: str | None

    @property
    def year(self) -> int | None:
        return TmdbMovieSummary(self.tmdb_id, self.title, self.release_date).year


@dataclass(frozen=True)
class TmdbCollectionDetails:
    tmdb_collection_id: int
    name: str
    movies: tuple[TmdbMovieSummary, ...] = field(default_factory=tuple)


class _RateLimiter:
    """Smooths outgoing requests to a fixed ceiling. Thread-safe, since a scheduled scan and a
    web request can both be talking to TMDb at once."""

    def __init__(self, max_per_second: int) -> None:
        self._min_interval = 1.0 / max(1, max_per_second)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = self._next_allowed - now
            self._next_allowed = max(now, self._next_allowed) + self._min_interval
        if sleep_for > 0:
            time.sleep(sleep_for)


def looks_like_v4_token(api_key: str) -> bool:
    """TMDb's settings page shows a v3 key *and* a v4 read access token, and the v4 one is more
    prominent. Pasting it here is the most common configuration mistake there is."""
    return api_key.strip().startswith("eyJ")


class TmdbClient:
    def __init__(
        self,
        api_key: str,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        max_requests_per_second: int = MAX_REQUESTS_PER_SECOND,
        session: requests.Session | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._timeout = timeout
        self._limiter = _RateLimiter(max_requests_per_second)
        self._session = session or requests.Session()
        register_secret(self._api_key)

    def _get(self, path: str, params: dict | None = None) -> dict:
        query = {"api_key": self._api_key, **(params or {})}

        for attempt in range(MAX_RETRIES):
            self._limiter.wait()
            try:
                response = self._session.get(
                    f"{TMDB_BASE_URL}{path}", params=query, timeout=self._timeout
                )
            except requests.RequestException as exc:
                # Generic on purpose: the request URL carries the API key in its query string.
                raise TmdbError("Could not reach TMDb") from exc

            if response.status_code == 429:
                delay = _retry_after(response, attempt)
                logger.warning("TMDb rate-limited us; retrying in %.1fs", delay)
                time.sleep(delay)
                continue

            if response.status_code == 401:
                raise TmdbAuthError(self._explain_401())
            if response.status_code == 404:
                raise TmdbNotFound(f"TMDb has no record at {path}")
            if response.status_code >= 400:
                raise TmdbError(f"TMDb returned {response.status_code}")

            try:
                return response.json()
            except ValueError as exc:
                raise TmdbError("TMDb returned a response that wasn't JSON") from exc

        raise TmdbError("TMDb kept rate-limiting the request; try again shortly")

    def _explain_401(self) -> str:
        """Turn TMDb's generic 401 into something the user can act on."""
        if looks_like_v4_token(self._api_key):
            return (
                "That looks like a TMDb v4 Read Access Token. Franchisarr needs the v3 API Key "
                "instead — it's the shorter value on the same TMDb settings page."
            )
        if len(self._api_key) != 32:
            return (
                "TMDb rejected that API key. A v3 key is 32 characters long; check it was pasted "
                "in full."
            )
        return (
            "TMDb rejected that API key. If it was created in the last few minutes, wait a "
            "moment and try again — new keys take a short while to activate."
        )

    # ---------------------------------------------------------------- public API

    def validate_key(self) -> None:
        """Raise TmdbAuthError with an actionable message if the key is unusable."""
        if not self._api_key:
            raise TmdbAuthError("No TMDb API key has been configured yet.")
        if looks_like_v4_token(self._api_key):
            raise TmdbAuthError(self._explain_401())
        self._get("/configuration")

    def get_movie(self, tmdb_id: int) -> TmdbMovieDetails:
        payload = self._get(f"/movie/{tmdb_id}")
        collection = payload.get("belongs_to_collection") or {}
        return TmdbMovieDetails(
            tmdb_id=int(payload.get("id", tmdb_id)),
            title=str(payload.get("title") or payload.get("original_title") or ""),
            release_date=payload.get("release_date") or None,
            collection_id=int(collection["id"]) if collection.get("id") else None,
            collection_name=collection.get("name"),
        )

    def get_collection(self, collection_id: int) -> TmdbCollectionDetails:
        payload = self._get(f"/collection/{collection_id}")
        parts = payload.get("parts") or []
        return TmdbCollectionDetails(
            tmdb_collection_id=int(payload.get("id", collection_id)),
            name=str(payload.get("name") or ""),
            movies=tuple(
                TmdbMovieSummary(
                    tmdb_id=int(part["id"]),
                    title=str(part.get("title") or part.get("original_title") or ""),
                    release_date=part.get("release_date") or None,
                )
                for part in parts
                if isinstance(part, dict) and part.get("id")
            ),
        )

    def find_by_external_id(self, external_id: str, source: str) -> TmdbMovieSummary | None:
        """Resolve an IMDb or TVDb id to a TMDb movie.

        This is the matcher's first fallback, and on a real library it covers more of the gap
        than title matching does.
        """
        payload = self._get(
            f"/find/{external_id}", {"external_source": source}
        )
        results = payload.get("movie_results") or []
        if not results:
            return None
        first = results[0]
        return TmdbMovieSummary(
            tmdb_id=int(first["id"]),
            title=str(first.get("title") or first.get("original_title") or ""),
            release_date=first.get("release_date") or None,
        )

    def search_movies(self, title: str, year: int | None = None) -> list[TmdbMovieSummary]:
        params: dict[str, str | int] = {"query": title}
        if year:
            params["year"] = year

        payload = self._get("/search/movie", params)
        return [
            TmdbMovieSummary(
                tmdb_id=int(item["id"]),
                title=str(item.get("title") or item.get("original_title") or ""),
                release_date=item.get("release_date") or None,
            )
            for item in payload.get("results") or []
            if isinstance(item, dict) and item.get("id")
        ]


def _retry_after(response: requests.Response, attempt: int) -> float:
    raw = response.headers.get("Retry-After")
    if raw and raw.strip().isdigit():
        return float(raw.strip())
    return float(2**attempt)
