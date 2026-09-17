"""theme.park theming, configured by environment variable.

The first version put a URL field in the app's settings page. That was wrong for the audience: a
homelab running theme.park across a dozen services sets the theme once, centrally, and expects
every app to pick it up — not to be opened one at a time and pasted into. These tests pin the
replacement, including the property that makes external injection work at all.
"""

from __future__ import annotations

import pytest

from app.services.theme_service import (
    InvalidThemeUrl,
    ThemeConfig,
    build_theme_park_url,
    resolve,
    validate_theme_url,
)
from app.templating import STATIC_DIR


# ------------------------------------------------------------------ URL validation


@pytest.mark.parametrize(
    "url",
    [
        "https://theme-park.dev/css/theme-options/nord.css",
        "http://192.168.1.5:8080/css/theme-options/dracula.css",
        "https://example.com/my-own-theme.css",
    ],
)
def test_valid_urls_are_accepted(url: str) -> None:
    assert validate_theme_url(url) == url


def test_an_empty_value_means_no_theme() -> None:
    assert validate_theme_url("") == ""
    assert validate_theme_url("   ") == ""


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "JavaScript:alert(1)", "data:text/css,body{}",
     "file:///etc/passwd", "vbscript:msgbox(1)"],
)
def test_dangerous_schemes_are_refused(url: str) -> None:
    with pytest.raises(InvalidThemeUrl):
        validate_theme_url(url)


def test_a_bare_word_is_refused() -> None:
    with pytest.raises(InvalidThemeUrl):
        validate_theme_url("nord")


def test_credentials_in_the_url_are_refused() -> None:
    with pytest.raises(InvalidThemeUrl):
        validate_theme_url("https://user:secret@example.com/theme.css")


# ------------------------------------------------------------------ theme.park convention


def test_the_url_matches_theme_parks_own_layout() -> None:
    """Taken from theme.park's Docker mod scripts rather than guessed, so a stack already using
    TP_THEME needs no new variables."""
    assert build_theme_park_url("nord") == (
        "https://theme-park.dev/css/theme-options/nord.css"
    )


def test_a_self_hosted_theme_park_is_supported() -> None:
    assert build_theme_park_url("nord", domain="themes.lan:8080", scheme="http") == (
        "http://themes.lan:8080/css/theme-options/nord.css"
    )


def test_community_themes_use_their_own_folder() -> None:
    assert "community-theme-options" in build_theme_park_url("hotline", community=True)


# ------------------------------------------------------------------ resolution


def test_no_environment_means_no_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("TP_THEME", "TP_DOMAIN", "TP_SCHEME", "TP_COMMUNITY_THEME", "THEME_CSS_URL"):
        monkeypatch.delenv(name, raising=False)

    assert resolve() == ThemeConfig(url="", source="none")


def test_tp_theme_is_enough_on_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TP_THEME", "nord")

    config = resolve()

    assert config.enabled is True
    assert config.url.endswith("/theme-options/nord.css")
    assert config.source == "TP_THEME"


def test_an_explicit_url_overrides_the_theme_park_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TP_THEME", "nord")
    monkeypatch.setenv("THEME_CSS_URL", "https://example.com/mine.css")

    config = resolve()

    assert config.url == "https://example.com/mine.css"
    assert config.source == "THEME_CSS_URL"


def test_a_malformed_value_leaves_the_app_unthemed_rather_than_broken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bad variable should cost you the theme, not the app."""
    monkeypatch.setenv("THEME_CSS_URL", "javascript:alert(1)")

    assert resolve().enabled is False


# ------------------------------------------------------------------ the adapter


def test_the_adapter_maps_theme_park_properties_onto_pico() -> None:
    css = (STATIC_DIR / "theme-adapter.css").read_text()

    assert "--pico-background-color" in css
    assert "--main-bg-color" in css


def test_every_adapter_mapping_has_a_fallback() -> None:
    """The adapter is always loaded, including when no theme is present. A mapping without a
    fallback would resolve to nothing and leave that property unset — so an unthemed page would
    be visibly broken rather than plain."""
    import re

    css = (STATIC_DIR / "theme-adapter.css").read_text()
    body = css[css.index(":root"):]
    mappings = re.findall(r"--pico-[a-z0-9-]+:\s*([^;]+);", body)

    assert mappings, "expected the adapter to map something"
    for value in mappings:
        assert "," in value, f"mapping without a fallback: {value.strip()}"


def test_app_css_never_hardcodes_a_colour() -> None:
    """The adapter is the one place a literal colour is allowed, because those are Pico's own
    values restated so the mapping can be unconditional. Everywhere else a literal is a hole in
    every theme."""
    import re

    css = (STATIC_DIR / "app.css").read_text()
    literals = re.findall(r":\s*(#[0-9a-fA-F]{3,8}|rgb\([^)]*\)|hsl\([^)]*\))\s*;", css)

    assert literals == [], f"hardcoded colours in app.css: {literals}"


def test_the_light_dark_attribute_is_not_shadowed_by_the_theme_config() -> None:
    """Regression: the settings context used the key `theme`, which the base template already
    used for the light/dark attribute — so a ThemeConfig object was rendered into data-theme."""
    from app.templating import build_templates

    html = build_templates("").get_template("settings.html").render(
        user=None, theme_config=ThemeConfig(), suggested=(), current_cron="",
        schedule_description="", current_webhook_url="", current_webhook_format="generic",
        webhook_formats=[], saved=False, error=None, import_note=None, update=None,
    )

    assert 'data-theme="dark"' in html
    assert "ThemeConfig" not in html


def test_the_layout_cannot_widen_the_page_on_a_phone() -> None:
    """Two rules, each found from a phone screenshot. Pico lays the nav out as one flex row and
    eleven items are wider than a phone, which pushed the whole document wide and every card
    with it; and Pico's aria-busy spinner comes with white-space: nowrap, meant for a button,
    which stopped the scan card's text wrapping. Neither is visible to any other test."""
    css = (STATIC_DIR / "app.css").read_text()

    nav_rule = css[css.index(".app-nav ul {"):]
    nav_rule = nav_rule[:nav_rule.index("}")]
    assert "flex-wrap: wrap" in nav_rule

    busy_rule = css[css.index('article[aria-busy="true"] {'):]
    busy_rule = busy_rule[:busy_rule.index("}")]
    assert "white-space: normal" in busy_rule
