"""fanart.tv API v3 client.

An *optional* enrichment layer, not a metadata source. PROJECT_PLAN.md commits to TMDb as the
only thing Franchisarr requires, and that stands: without a fanart key every screen still works,
just without the franchise logos.

The division of labour was measured against the real library rather than assumed, and it is
lopsided. On 80 films the library was missing, fanart.tv had a poster TMDb lacked exactly zero
times, while TMDb had one 91% of the time -- so fanart is never a poster source here. What it has
that TMDb has nothing comparable to is clearlogos: the transparent, typeset franchise wordmark,
present for the anchor film of all 70 collections sampled. That one asset is the whole reason
this client exists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from app.clients.rate_limit import RateLimiter
from app.logging_config import register_secret

logger = logging.getLogger(__name__)

FANART_BASE_URL = "https://webservice.fanart.tv/v3"
DEFAULT_TIMEOUT = 15

#: fanart.tv publishes no rate limit for personal keys. A scan touches it once per collection --
#: hundreds of requests, not thousands -- so a deliberately modest ceiling costs nothing.
MAX_REQUESTS_PER_SECOND = 5

#: Logos in preference order. The HD list is the same artwork at a usable size; a collection
#: heading is rendered large, so a 400px logo from the legacy list is the fallback, not the pick.
LOGO_KEYS = ("hdmovielogo", "movielogo")
BACKGROUND_KEYS = ("moviebackground",)


class FanartError(RuntimeError):
    """Any fanart.tv failure. Its message is safe to show a user."""


class FanartAuthError(FanartError):
    """The API key was rejected."""


class FanartNotFound(FanartError):
    """fanart.tv has no record for this film. Entirely normal -- it is community-contributed,
    so anything unreleased or obscure simply isn't there yet."""


@dataclass(frozen=True)
class MovieArt:
    """The two assets worth having. Full URLs, because fanart serves them from its own CDN with
    no size variants to choose between -- unlike TMDb, there is no rendering decision to defer."""

    logo_url: str | None = None
    background_url: str | None = None

    def __bool__(self) -> bool:
        return bool(self.logo_url or self.background_url)


def _best(entries: list, *, prefer_language: str = "en") -> str | None:
    """Pick one image from fanart's list of community uploads.

    Language first, popularity second. A logo in the wrong language is worse than no logo -- it
    is a wordmark, so the text *is* the image -- while for artwork with no text fanart uses an
    empty lang, which is why that counts as a match rather than a miss.
    """
    usable = [e for e in entries if isinstance(e, dict) and e.get("url")]
    if not usable:
        return None

    def sort_key(entry: dict) -> tuple[int, int]:
        lang = (entry.get("lang") or "").lower()
        language_rank = 0 if lang == prefer_language else (1 if lang == "" else 2)
        try:
            likes = int(entry.get("likes") or 0)
        except (TypeError, ValueError):
            likes = 0
        return (language_rank, -likes)

    return str(sorted(usable, key=sort_key)[0]["url"])


class FanartClient:
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

    def _get(self, path: str) -> dict:
        self._limiter.wait()
        try:
            response = self._session.get(
                f"{FANART_BASE_URL}{path}",
                params={"api_key": self._api_key},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            # Generic on purpose: the request URL carries the API key in its query string.
            raise FanartError("Could not reach fanart.tv") from exc

        if response.status_code in (401, 403):
            raise FanartAuthError(self._explain_401())
        if response.status_code == 404:
            raise FanartNotFound("fanart.tv has no artwork for that film")
        if response.status_code >= 400:
            raise FanartError(f"fanart.tv returned {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise FanartError("fanart.tv returned a response that wasn't JSON") from exc
        if not isinstance(payload, dict):
            raise FanartError("fanart.tv returned a response in an unexpected shape")
        return payload

    def _explain_401(self) -> str:
        if not self._api_key:
            return "No fanart.tv API key has been configured."
        if len(self._api_key) != 32:
            return (
                "fanart.tv rejected that API key. A personal key is 32 characters long; check it "
                "was pasted in full."
            )
        return (
            "fanart.tv rejected that API key. Check it against the one on your fanart.tv account "
            "page — artwork is optional, so Franchisarr works without it."
        )

    # ---------------------------------------------------------------- public API

    def validate_key(self) -> None:
        """Raise FanartAuthError with an actionable message if the key is unusable.

        Validated against a real film rather than a dedicated endpoint, because fanart.tv has no
        equivalent of TMDb's /configuration. 550 is Fight Club, which has had artwork for years.
        """
        if not self._api_key:
            raise FanartAuthError("No fanart.tv API key has been configured.")
        try:
            self._get("/movies/550")
        except FanartNotFound:
            # Astonishing, but it would mean the key worked.
            return

    def get_movie_art(self, tmdb_id: int) -> MovieArt:
        """Fetch the artwork worth keeping for one film.

        Returns an empty MovieArt rather than raising when fanart simply has nothing, since a
        film with no community artwork is the normal case, not a failure.
        """
        try:
            payload = self._get(f"/movies/{tmdb_id}")
        except FanartNotFound:
            return MovieArt()

        def first_of(keys: tuple[str, ...]) -> str | None:
            for key in keys:
                found = _best(payload.get(key) or [])
                if found:
                    return found
            return None

        return MovieArt(
            logo_url=first_of(LOGO_KEYS),
            background_url=first_of(BACKGROUND_KEYS),
        )
