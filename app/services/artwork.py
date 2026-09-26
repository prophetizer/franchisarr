"""Where poster images come from.

TMDb serves artwork from its own CDN, so a poster on the page is a request from the viewer's
browser to image.tmdb.org. That is worth being deliberate about in a self-hosted app: it is the
one thing on these pages that isn't served by the user's own server. It is also what makes a
media UI usable, and every app in this space does it, so it is on by default with an off switch
rather than the other way round.

Only the path fragment is stored. The size is a rendering decision -- a card wants a different
one from a list thumbnail -- and baking a full URL into the database would fix that at scan time.
"""

from __future__ import annotations

import os

#: TMDb's image CDN. Their /configuration endpoint is the canonical source and this value has not
#: changed in over a decade, so it is not worth a request per render to re-learn it.
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/"

#: Sizes TMDb publishes for posters. Anything else 404s.
POSTER_SIZES = ("w92", "w154", "w185", "w342", "w500", "w780", "original")

CARD_SIZE = "w342"
#: Backdrops are rendered full-width behind a heading, so they need the wide sizes.
BACKDROP_SIZES = ("w300", "w780", "w1280", "original")
HERO_SIZE = "w1280"
#: A small card poster: 88 CSS px wide, so w185 stays sharp on a 2x screen. Every film and show
#: in a list is a tile of this size since 0.24.0, so the old w92 thumbnail size is gone.
SMALL_CARD_SIZE = "w185"


def images_enabled() -> bool:
    """Off only if the operator says so. `SHOW_ARTWORK=false` keeps every request on their own
    server, at the cost of a text-only interface."""
    return os.environ.get("SHOW_ARTWORK", "true").strip().lower() not in ("0", "false", "no", "off")


def poster_url(path: str | None, size: str = CARD_SIZE) -> str | None:
    """Build a TMDb poster URL from a stored path. None when there is no artwork."""
    if not path or not images_enabled():
        return None
    if size not in POSTER_SIZES:
        size = CARD_SIZE
    return f"{TMDB_IMAGE_BASE}{size}{path if path.startswith('/') else '/' + path}"


#: Sizes TMDb publishes for people. h632 is the tall one for a heading.
PROFILE_SIZES = ("w45", "w185", "h632", "original")
PROFILE_SIZE = "w185"
PROFILE_LARGE_SIZE = "h632"


def profile_url(path: str | None, size: str = PROFILE_SIZE) -> str | None:
    """A TMDb person photo, same off switch as the posters."""
    if not path or not images_enabled():
        return None
    if size not in PROFILE_SIZES:
        size = PROFILE_SIZE
    return f"{TMDB_IMAGE_BASE}{size}{path if path.startswith('/') else '/' + path}"


def backdrop_url(path: str | None, size: str = HERO_SIZE) -> str | None:
    """A TMDb backdrop, for the band behind a collection heading."""
    if not path or not images_enabled():
        return None
    if size not in BACKDROP_SIZES:
        size = HERO_SIZE
    return f"{TMDB_IMAGE_BASE}{size}{path if path.startswith('/') else '/' + path}"


def logo_url(url: str | None) -> str | None:
    """A fanart.tv logo, passed through the same off switch as everything else.

    Stored complete rather than as a path, so there is nothing to build here -- but it still has
    to answer to SHOW_ARTWORK, or turning artwork off would leave one image behind.
    """
    if not url or not images_enabled():
        return None
    return url
