"""theme.park theming, configured the way a homelab actually configures it.

Themes are set by environment variable, not in the app's own settings. In a homelab running
theme.park across a dozen services the theme is chosen once — in compose, or centrally by a
reverse proxy — and every app picks it up. Making someone open each app and paste a URL is
exactly backwards, and that is what the first version of this did.

The variables match theme.park's own Docker mod, taken from its mod scripts rather than guessed,
so this drops into an existing stack unchanged:

    TP_THEME=nord                  # theme name; unset means no theming
    TP_DOMAIN=theme-park.dev       # or your own self-hosted copy
    TP_SCHEME=https
    TP_COMMUNITY_THEME=false       # true selects community-theme-options

`THEME_CSS_URL` overrides all of that with a literal stylesheet URL, for anything unusual.

The other route needs no configuration here at all: a reverse proxy can inject the stylesheet
link into the page itself (nginx `sub_filter`, a Traefik plugin, the theme.park mod). That works
because `theme-adapter.css` is always loaded, so an injected theme-options file takes effect
without Franchisarr knowing anything about it.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("http", "https")

DEFAULT_DOMAIN = "theme-park.dev"
DEFAULT_SCHEME = "https"


class InvalidThemeUrl(ValueError):
    """The URL isn't something safe to put in a stylesheet link."""


@dataclass(frozen=True)
class ThemeConfig:
    """Where the theme stylesheet lives, and how it was decided."""

    url: str = ""
    source: str = "none"

    @property
    def enabled(self) -> bool:
        return bool(self.url)


def validate_theme_url(raw: str) -> str:
    """Return a cleaned URL, or raise. Empty means "no theme", which is valid."""
    value = (raw or "").strip()
    if not value:
        return ""

    parsed = urlparse(value)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        # A `javascript:` URL in a stylesheet link is a scripting vector.
        raise InvalidThemeUrl("The theme URL must start with http:// or https://")
    if not parsed.netloc:
        raise InvalidThemeUrl("That doesn't look like a complete URL.")
    if parsed.username or parsed.password:
        raise InvalidThemeUrl("Don't put credentials in the theme URL.")

    return value


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def build_theme_park_url(
    theme: str, *, domain: str = "", scheme: str = "", community: bool = False
) -> str:
    """Construct a theme.park theme-options URL, matching their mod's own layout."""
    domain = (domain or DEFAULT_DOMAIN).strip().strip("/")
    scheme = (scheme or DEFAULT_SCHEME).strip()
    folder = "community-theme-options" if community else "theme-options"
    return f"{scheme}://{domain}/css/{folder}/{theme.strip()}.css"


def resolve() -> ThemeConfig:
    """Work out the active theme from the environment.

    Returns an empty config rather than raising when something is malformed: a bad value should
    leave the app unthemed and say so in the log, not stop it serving pages.
    """
    explicit = _env("THEME_CSS_URL")
    if explicit:
        try:
            return ThemeConfig(url=validate_theme_url(explicit), source="THEME_CSS_URL")
        except InvalidThemeUrl as exc:
            logger.error("Ignoring THEME_CSS_URL: %s", exc)
            return ThemeConfig()

    theme = _env("TP_THEME")
    if not theme:
        return ThemeConfig()

    url = build_theme_park_url(
        theme,
        domain=_env("TP_DOMAIN"),
        scheme=_env("TP_SCHEME"),
        community=_env("TP_COMMUNITY_THEME").lower() in ("1", "true", "yes", "on"),
    )
    try:
        return ThemeConfig(url=validate_theme_url(url), source="TP_THEME")
    except InvalidThemeUrl as exc:
        logger.error("Ignoring TP_THEME: %s", exc)
        return ThemeConfig()
