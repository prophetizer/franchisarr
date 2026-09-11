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
import time
from dataclasses import dataclass, field

import requests

from app.clients.rate_limit import RateLimiter
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
    poster_path: str | None = None
    vote_average: float | None = None
    vote_count: int | None = None
    popularity: float | None = None

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
class TmdbShowSummary:
    tmdb_id: int
    name: str
    first_air_date: str | None = None
    network: str | None = None
    poster_path: str | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None

    @property
    def year(self) -> int | None:
        if (
            self.first_air_date
            and len(self.first_air_date) >= 4
            and self.first_air_date[:4].isdigit()
        ):
            return int(self.first_air_date[:4])
        return None


@dataclass(frozen=True)
class TmdbCollectionDetails:
    tmdb_collection_id: int
    name: str
    poster_path: str | None = None
    backdrop_path: str | None = None
    movies: tuple[TmdbMovieSummary, ...] = field(default_factory=tuple)


#: Kept as a module-level name because this is where the limiter used to live; fanart.tv needs
#: the same behaviour, so the implementation moved to `rate_limit`.
_RateLimiter = RateLimiter


def _as_float(value) -> float | None:  # noqa: ANN001 - raw JSON
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_int(value) -> int | None:  # noqa: ANN001 - raw JSON
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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
        self._limiter = RateLimiter(max_requests_per_second)
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
            poster_path=payload.get("poster_path") or None,
            backdrop_path=payload.get("backdrop_path") or None,
            movies=tuple(
                TmdbMovieSummary(
                    tmdb_id=int(part["id"]),
                    title=str(part.get("title") or part.get("original_title") or ""),
                    release_date=part.get("release_date") or None,
                    poster_path=part.get("poster_path") or None,
                    vote_average=_as_float(part.get("vote_average")),
                    vote_count=_as_int(part.get("vote_count")),
                    popularity=_as_float(part.get("popularity")),
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

    def get_show(self, tmdb_id: int) -> TmdbShowSummary:
        # external_ids appended rather than fetched separately: it is one request either way
        # for us, but appending is one request for TMDb, and a show scan makes hundreds.
        payload = self._get(f"/tv/{tmdb_id}", {"append_to_response": "external_ids"})
        networks = payload.get("networks") or []
        external = payload.get("external_ids") or {}
        tvdb_raw = external.get("tvdb_id")
        return TmdbShowSummary(
            tmdb_id=int(payload.get("id", tmdb_id)),
            name=str(payload.get("name") or payload.get("original_name") or ""),
            first_air_date=payload.get("first_air_date") or None,
            network=str(networks[0]["name"]) if networks and networks[0].get("name") else None,
            poster_path=payload.get("poster_path") or None,
            imdb_id=str(external["imdb_id"]) if external.get("imdb_id") else None,
            tvdb_id=int(tvdb_raw) if isinstance(tvdb_raw, int) or str(tvdb_raw).isdigit() else None,
        )

    def find_show_by_external_id(self, external_id: str, source: str) -> TmdbShowSummary | None:
        payload = self._get(f"/find/{external_id}", {"external_source": source})
        results = payload.get("tv_results") or []
        if not results:
            return None
        first = results[0]
        return TmdbShowSummary(
            tmdb_id=int(first["id"]),
            name=str(first.get("name") or first.get("original_name") or ""),
            first_air_date=first.get("first_air_date") or None,
        )

    def search_shows(self, name: str, year: int | None = None) -> list[TmdbShowSummary]:
        params: dict[str, str | int] = {"query": name}
        if year:
            params["first_air_date_year"] = year

        payload = self._get("/search/tv", params)
        return [
            TmdbShowSummary(
                tmdb_id=int(item["id"]),
                name=str(item.get("name") or item.get("original_name") or ""),
                first_air_date=item.get("first_air_date") or None,
                poster_path=item.get("poster_path") or None,
            )
            for item in payload.get("results") or []
            if isinstance(item, dict) and item.get("id")
        ]

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
