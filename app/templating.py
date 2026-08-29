"""Jinja2 environment.

The `url()` global is the single place a link becomes a path. Templates never write a literal
"/something": Franchisarr is expected to run behind a reverse proxy at a subpath, and one
hardcoded path breaks the UI for those users while looking perfectly fine at the root
(PROJECT_PLAN.md technical challenge #10).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app import __version__

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def make_url_builder(base_url: str) -> Callable[[str], str]:
    """Build the `url()` helper for a given base URL ('' or '/franchisarr')."""

    def url(path: str = "/") -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{base_url}{path}"

    return url


def build_templates(base_url: str) -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.globals["url"] = make_url_builder(base_url)
    templates.env.globals["version"] = __version__
    return templates
