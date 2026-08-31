"""Optional external theming, aimed at theme.park (https://theme-park.dev).

theme.park is the theming convention in the *arr community, so an app sitting next to Radarr and
Sonarr looks out of place without it. Its per-theme files are app-agnostic -- a `:root` block of
custom properties -- so Franchisarr can consume them directly by mapping those properties onto
Pico's, with no involvement from theme.park at all.

This is the one deliberate exception to the "vendor everything, never CDN-link" decision made in
Phase 1, so it is opt-in, off by default, and a URL rather than a fixed host: theme.park is
self-hostable and a good part of this audience will run their own copy.

The URL is user-supplied and ends up in a `<link href>`, so it is validated here rather than at
the template: only http and https, and no credentials in the URL.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from sqlmodel import Session

from app.services.settings_service import SettingKey, get_setting, set_setting

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("http", "https")

#: A few well-known theme.park themes, offered as a starting point. The field accepts any URL --
#: these exist so the first-time user doesn't have to go and read theme.park's docs to try it.
SUGGESTED_THEMES: tuple[tuple[str, str], ...] = (
    ("Organizr Dark", "https://theme-park.dev/css/theme-options/organizr-dark.css"),
    ("Nord", "https://theme-park.dev/css/theme-options/nord.css"),
    ("Dracula", "https://theme-park.dev/css/theme-options/dracula.css"),
    ("Aquamarine", "https://theme-park.dev/css/theme-options/aquamarine.css"),
    ("Space Gray", "https://theme-park.dev/css/theme-options/space-gray.css"),
    ("Hotline", "https://theme-park.dev/css/theme-options/hotline.css"),
    ("Plex", "https://theme-park.dev/css/theme-options/plex.css"),
)


class InvalidThemeUrl(ValueError):
    """The URL isn't something safe to put in a stylesheet link."""


def validate_theme_url(raw: str) -> str:
    """Return a cleaned URL, or raise. An empty string means "no theme", which is valid."""
    value = (raw or "").strip()
    if not value:
        return ""

    parsed = urlparse(value)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        # The important one: a `javascript:` URL in a stylesheet link is a scripting vector.
        raise InvalidThemeUrl("The theme URL must start with http:// or https://")
    if not parsed.netloc:
        raise InvalidThemeUrl("That doesn't look like a complete URL.")
    if parsed.username or parsed.password:
        raise InvalidThemeUrl("Don't put credentials in the theme URL.")

    return value


def get_theme_url(session: Session) -> str:
    """The configured URL, re-validated on read.

    Re-validating means a value written directly into the database -- by an older version, a
    hand-edited config, or a restored backup -- still can't put something dangerous in the page.
    """
    try:
        return validate_theme_url(get_setting(session, SettingKey.THEME_URL) or "")
    except InvalidThemeUrl:
        logger.warning("Ignoring a stored theme URL that isn't a valid http(s) address")
        return ""


def set_theme_url(session: Session, raw: str) -> str:
    url = validate_theme_url(raw)
    set_setting(session, SettingKey.THEME_URL, url)
    session.commit()
    logger.info("Theme URL %s", "cleared" if not url else "updated")
    return url
