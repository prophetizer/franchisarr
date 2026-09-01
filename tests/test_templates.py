"""The rendered UI must respect BASE_URL, and must not reach out to a CDN.

Extends the base-URL guarantee in tests/test_base_url.py from routes to the things a browser
fetches afterwards -- stylesheets, scripts, and in-page links -- which is where a subpath
deployment actually tends to break.
"""

from __future__ import annotations

import re

import pytest

from app.templating import STATIC_DIR, build_templates, get_templates, make_url_builder

VENDORED_ASSETS = ["pico.min.css", "htmx.min.js", "alpine.min.js", "app.css"]


@pytest.mark.parametrize(
    ("base_url", "path", "expected"),
    [
        ("", "/", "/"),
        ("", "/health", "/health"),
        ("", "static/app.css", "/static/app.css"),
        ("/franchisarr", "/", "/franchisarr/"),
        ("/franchisarr", "/health", "/franchisarr/health"),
        ("/franchisarr", "/static/app.css", "/franchisarr/static/app.css"),
    ],
)
def test_url_builder(base_url: str, path: str, expected: str) -> None:
    assert make_url_builder(base_url)(path) == expected


def _render(base_url: str) -> str:
    templates = build_templates(base_url)
    return templates.get_template("index.html").render()


def test_get_templates_follows_the_configured_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: route modules used to capture BASE_URL at import time, so whether asset links
    carried the subpath depended on which module imported first."""
    monkeypatch.setenv("BASE_URL", "/franchisarr")
    assert get_templates().env.globals["url"]("/static/app.css") == "/franchisarr/static/app.css"

    monkeypatch.setenv("BASE_URL", "/")
    assert get_templates().env.globals["url"]("/static/app.css") == "/static/app.css"


def test_theme_is_dark_by_default() -> None:
    html = _render("")
    assert 'data-theme="dark"' in html


def test_theme_can_be_overridden_for_a_future_light_toggle() -> None:
    """Phase 9's toggle should only need to change this attribute."""
    templates = build_templates("")
    html = templates.get_template("index.html").render(color_scheme="light")
    assert 'data-theme="light"' in html


@pytest.mark.parametrize("asset", VENDORED_ASSETS)
def test_assets_are_served_from_base_url(asset: str) -> None:
    html = _render("/franchisarr")
    assert f"/franchisarr/static/{asset}" in html


@pytest.mark.parametrize("asset", VENDORED_ASSETS)
def test_assets_are_served_from_root_when_base_url_is_unset(asset: str) -> None:
    html = _render("")
    assert f'"/static/{asset}"' in html


def test_no_link_escapes_the_base_url() -> None:
    """Any href/src that starts with a single slash must carry the prefix."""
    html = _render("/franchisarr")

    paths = re.findall(r'(?:href|src)="(/[^"]*)"', html)
    assert paths, "expected the page to contain absolute-path links"
    unprefixed = [path for path in paths if not path.startswith("/franchisarr/")]
    assert unprefixed == []


def test_no_external_asset_references() -> None:
    """No CDN links: a self-hosted app must render without outbound internet access."""
    html = _render("")
    assert "//cdn." not in html
    assert "//unpkg." not in html
    assert "http://" not in html
    assert "https://" not in html


@pytest.mark.parametrize("asset", VENDORED_ASSETS)
def test_vendored_assets_exist_on_disk(asset: str) -> None:
    path = STATIC_DIR / asset
    assert path.is_file(), f"{asset} is referenced by the templates but not vendored"
    assert path.stat().st_size > 0
