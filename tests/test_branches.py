"""The develop branch (docs/DEVELOPMENT.md, Branches): its image carries its commit as a build id,
which reaches the footer and the asset URLs; releases carry none and are unchanged."""

from __future__ import annotations

from pathlib import Path

from app import __version__
from app.templating import build_id, make_asset_builder

HERE = Path(__file__).resolve().parents[1]


def test_a_release_build_has_plain_versioned_assets(monkeypatch) -> None:
    monkeypatch.delenv("FRANCHISARR_BUILD", raising=False)
    assert build_id() == ""
    assert make_asset_builder("/f")("/static/app.css") == f"/f/static/app.css?v={__version__}"


def test_a_develop_build_busts_caches_with_its_commit(monkeypatch) -> None:
    monkeypatch.setenv("FRANCHISARR_BUILD", "0123456789abcdef")
    assert build_id() == "0123456"
    assert make_asset_builder("")("/static/app.css") == f"/static/app.css?v={__version__}-0123456"


def test_the_footer_says_which_develop_build_is_running() -> None:
    base = (HERE / "app" / "templates" / "base.html").read_text()
    assert "{% if build %} · develop {{ build }}{% endif %}" in base


def test_only_tags_and_develop_publish_images() -> None:
    ci = (HERE / ".github" / "workflows" / "ci.yml").read_text()
    assert "push: ${{ startsWith(github.ref, 'refs/tags/v') || github.ref == 'refs/heads/develop' }}" in ci
    assert "FRANCHISARR_BUILD=${{ github.ref == 'refs/heads/develop' && github.sha || '' }}" in ci
    assert "type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/v') }}" in ci, "latest is releases only"
    docker = (HERE / "Dockerfile").read_text()
    assert 'ARG FRANCHISARR_BUILD=""' in docker and "ENV FRANCHISARR_BUILD=$FRANCHISARR_BUILD" in docker


def test_dependabot_targets_develop_and_screenshots_stay_on_master() -> None:
    bot = (HERE / ".github" / "dependabot.yml").read_text()
    assert bot.count("target-branch: develop") == bot.count("package-ecosystem:") == 3
    shots = (HERE / ".github" / "workflows" / "screenshots.yml").read_text()
    assert "branches: [master]" in shots


def test_no_image_publishes_while_the_dependency_audit_fails() -> None:
    """v0.75.0 reached :latest with pip-audit failing on Pillow: only the tests gated the image."""
    ci = (HERE / ".github" / "workflows" / "ci.yml").read_text()
    image = ci[ci.index("\n  image:"):]
    assert "needs: [test, audit]" in image


def _login_page(app_factory, monkeypatch, build: str) -> str:
    from fastapi.testclient import TestClient

    from app.templating import _cached_templates

    if build:
        monkeypatch.setenv("FRANCHISARR_BUILD", build)
    else:
        monkeypatch.delenv("FRANCHISARR_BUILD", raising=False)
    _cached_templates.cache_clear()               # the build id is read when templates are built
    try:
        module = app_factory("/f")
        with TestClient(module.app) as client:
            return client.get("/f/login").text
    finally:
        _cached_templates.cache_clear()


def test_a_develop_build_says_so_across_the_top_of_every_page(app_factory, monkeypatch) -> None:
    """michael, 2026-10-22: franchisarr-dev runs beside the release, and should be unmistakable."""
    page = _login_page(app_factory, monkeypatch, "0123456789abcdef")
    assert 'class="dev-banner"' in page and "develop 0123456" in page
    assert "<title>DEV · " in page
    assert page.index('class="dev-banner"') < page.index('<header class="container">'), "first thing on the page"


def test_a_release_build_shows_no_banner(app_factory, monkeypatch) -> None:
    page = _login_page(app_factory, monkeypatch, "")
    assert "dev-banner" not in page.split("</head>")[1] and "<title>DEV" not in page
