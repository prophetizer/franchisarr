"""Jinja2 environment.

The `url()` global is the single place a link becomes a path. Templates never write a literal
"/something": Franchisarr is expected to run behind a reverse proxy at a subpath, and one
hardcoded path breaks the UI for those users while looking perfectly fine at the root
(PROJECT_PLAN.md technical challenge #10).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import logging
from functools import lru_cache

from fastapi.templating import Jinja2Templates

from app import __version__
from app.config import get_settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def make_url_builder(base_url: str) -> Callable[[str], str]:
    """Build the `url()` helper for a given base URL ('' or '/franchisarr')."""

    def url(path: str = "/") -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{base_url}{path}"

    return url


def make_asset_builder(base_url: str):
    """Static asset URLs carry the app version, so a release invalidates every browser's copy.

    Without this a phone kept the previous app.css across a deploy that fixed its layout: the
    files are served with an ETag but no Cache-Control, and Safari's heuristic freshness is
    enough to skip the revalidation. A changed query string is a different URL, and there is
    nothing heuristic about that.
    """
    url = make_url_builder(base_url)

    def asset(path: str) -> str:
        return f"{url(path)}?v={__version__}"

    return asset


def _theme_context(request) -> dict:  # noqa: ANN001 - a Starlette Request
    """Make the configured theme URL available to every template.

    A context processor rather than a per-route argument: the theme link lives in the base
    template, so a route that forgot to pass it would render one unthemed page and nothing would
    fail loudly. Reading it from the environment costs nothing.
    """
    from app.services.theme_service import resolve

    return {"theme_url": resolve().url}


def _scan_context(request) -> dict:  # noqa: ANN001 - a Starlette Request
    """Make scan progress available to every template.

    Same reasoning as the theme: the scan status region is included by several pages now, and a
    route that forgot to pass `progress` would raise at render time on that page alone. The state
    is a process-local object, so reading it costs nothing.
    """
    from app.services import scan_state

    return {"progress": scan_state.current()}


def build_templates(base_url: str) -> Jinja2Templates:
    templates = Jinja2Templates(
        directory=str(TEMPLATES_DIR), context_processors=[_theme_context, _scan_context]
    )
    templates.env.globals["url"] = make_url_builder(base_url)
    templates.env.globals["version"] = __version__
    templates.env.globals["asset"] = make_asset_builder(base_url)
    return templates


@lru_cache(maxsize=4)
def _cached_templates(base_url: str) -> Jinja2Templates:
    return build_templates(base_url)


def get_templates() -> Jinja2Templates:
    """Templates for the currently configured base URL.

    Resolved per call rather than captured at import. Route modules that bound BASE_URL at import
    time worked only if they happened to be imported after it was set -- which made correctness
    depend on import order, and silently produced root-relative asset links under a subpath. The
    cache is keyed on the base URL, so this stays a dictionary lookup in practice.
    """
    return _cached_templates(get_settings().base_url)
