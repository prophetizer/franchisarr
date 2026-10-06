"""Jinja2 environment.

The `url()` global is the single place a link becomes a path. Templates never write a literal
"/something": Franchisarr is expected to run behind a reverse proxy at a subpath, and one
hardcoded path breaks the UI for those users while looking perfectly fine at the root
(docs/DESIGN.md technical challenge #10).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import logging
import os
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
    stamp = f"{__version__}-{build_id()}" if build_id() else __version__

    def asset(path: str) -> str:
        return f"{url(path)}?v={stamp}"

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


def _solo_context(request) -> dict:  # noqa: ANN001 - a Starlette Request
    """"Showing only Jellyfin" on every page while "Use only this server" is on.

    Every page, because that's where it matters: with the other servers off, films they hold
    show as missing, and a banner on the servers page alone would be long out of sight by then.
    Two small reads per render. A database that can't answer (a test rendering a template on
    its own) just means no banner -- this must never be what breaks a page.
    """
    from sqlalchemy.exc import SQLAlchemyError
    from sqlmodel import Session

    from app.db import get_engine
    from app.services import media_server_service

    try:
        with Session(get_engine()) as session:
            return {"solo": media_server_service.solo_state(session)}
    except SQLAlchemyError:
        return {"solo": None}


def title_hue(title: str) -> int:
    """A hue (0-359) from a title, the same every time: a placeholder poster's tint (0.72.0)."""
    import zlib

    return zlib.crc32(title.casefold().encode("utf-8")) % 360


def build_id() -> str:
    """The commit a develop image was built from, short; empty in a release (docs/DEVELOPMENT.md,
    Branches). A develop build keeps the last release's version number, so without this its
    CSS and scripts would sit in browsers' caches from one develop push to the next."""
    return os.environ.get("FRANCHISARR_BUILD", "").strip()[:7]


def build_templates(base_url: str) -> Jinja2Templates:
    templates = Jinja2Templates(
        directory=str(TEMPLATES_DIR),
        context_processors=[_theme_context, _scan_context, _solo_context],
    )
    templates.env.globals["url"] = make_url_builder(base_url)
    templates.env.globals["version"] = __version__
    templates.env.globals["build"] = build_id()
    templates.env.globals["asset"] = make_asset_builder(base_url)
    from app.services.sorting import sort_titles

    templates.env.globals["sort_titles"] = sort_titles
    from app.services.sorting import decades
    templates.env.globals["decades"] = decades
    from app.services.runtimes import hours, summary as runtime_summary, watched_of
    templates.env.globals["watched_of"] = watched_of
    templates.env.globals["runtime_summary"] = runtime_summary
    templates.env.filters["hours"] = hours
    templates.env.filters["title_hue"] = title_hue
    from app.services.timeline import decade_marks
    templates.env.globals["decade_marks"] = decade_marks
    from app.services import look as look_service

    templates.env.globals["look_of"] = look_service.of
    templates.env.globals["intros_of"] = look_service.intros_of
    templates.env.globals["effects_of"] = look_service.effects_of
    templates.env.globals["density_of"] = look_service.density_of
    templates.env.globals["next_effects"] = look_service.next_effects
    import json

    templates.env.filters["fromjson"] = json.loads
    templates.env.filters["ago"] = ago
    return templates


def ago(when, now=None) -> str:  # noqa: ANN001
    """"just now", "5 min ago", "3 h ago", "2 days ago". A naive time is UTC, as stored."""
    from datetime import datetime, timezone

    if when is None:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    seconds = max(0, int(((now or datetime.now(timezone.utc)) - when).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 2 * 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} days ago"


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
