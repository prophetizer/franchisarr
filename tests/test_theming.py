"""External theming (theme.park support).

The URL is user-supplied and lands in a `<link href>`, so most of this is about it not being
able to do anything it shouldn't.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session

from app.services.theme_service import (
    SUGGESTED_THEMES,
    InvalidThemeUrl,
    get_theme_url,
    set_theme_url,
    validate_theme_url,
)
from app.services.settings_service import SettingKey, set_setting
from app.templating import STATIC_DIR


@pytest.mark.parametrize(
    "url",
    [
        "https://theme-park.dev/css/theme-options/nord.css",
        "http://192.168.1.5:8080/css/theme-options/dracula.css",  # self-hosted
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
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "data:text/css,body{}",
        "file:///etc/passwd",
        "vbscript:msgbox(1)",
    ],
)
def test_dangerous_schemes_are_refused(url: str) -> None:
    """A `javascript:` URL in a stylesheet link is a scripting vector."""
    with pytest.raises(InvalidThemeUrl):
        validate_theme_url(url)


def test_a_bare_word_is_refused() -> None:
    with pytest.raises(InvalidThemeUrl):
        validate_theme_url("nord")


def test_credentials_in_the_url_are_refused() -> None:
    """They'd be rendered into the page source for every visitor to read."""
    with pytest.raises(InvalidThemeUrl):
        validate_theme_url("https://user:secret@example.com/theme.css")


def test_setting_and_reading_a_theme(session: Session) -> None:
    url = "https://theme-park.dev/css/theme-options/nord.css"
    set_theme_url(session, url)
    assert get_theme_url(session) == url


def test_a_theme_can_be_cleared(session: Session) -> None:
    set_theme_url(session, "https://theme-park.dev/css/theme-options/nord.css")
    set_theme_url(session, "")
    assert get_theme_url(session) == ""


def test_a_dangerous_value_already_in_the_database_is_ignored(session: Session) -> None:
    """Defence for a value that arrived some other way -- an older version, a hand-edited
    config, a restored backup. Reading must not be the weak link."""
    set_setting(session, SettingKey.THEME_URL, "javascript:alert(1)")
    session.commit()

    assert get_theme_url(session) == ""


def test_the_adapter_stylesheet_exists_and_only_maps_variables() -> None:
    """The adapter's whole job is assigning theme.park properties to Pico ones. If it started
    setting literal colours it would fight the theme rather than carry it."""
    css = (STATIC_DIR / "theme-adapter.css").read_text()

    assert "--pico-background-color" in css
    assert "--main-bg-color" in css
    # No hex literals: every value should come from a theme.park variable.
    import re

    assert re.search(r":\s*#[0-9a-fA-F]{3,8}\s*;", css) is None


def test_app_css_never_hardcodes_a_colour() -> None:
    """The reason theming was built before the screens. A literal here is a hole in every theme."""
    import re

    css = (STATIC_DIR / "app.css").read_text()
    literals = re.findall(r":\s*(#[0-9a-fA-F]{3,8}|rgb\([^)]*\)|hsl\([^)]*\))\s*;", css)

    assert literals == [], f"hardcoded colours in app.css: {literals}"


def test_suggested_themes_all_point_at_theme_park() -> None:
    for name, url in SUGGESTED_THEMES:
        assert name
        assert validate_theme_url(url) == url
