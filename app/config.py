"""Bootstrap settings loaded from environment variables.

Env vars are a *convenience path*, not the only path: they seed the DB `settings` table on first
boot so a docker-compose/Unraid deployment comes up configured, after which the setup wizard and
Settings UI own the values (docs/DESIGN.md section 6). Nothing here is read at request time
except BASE_URL and LOG_LEVEL, which have to be known before the database is even open.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}


def _normalize_base_url(raw: str) -> str:
    """Normalize BASE_URL to a form like '' or '/franchisarr' (no trailing slash)."""
    value = raw.strip()
    if value in ("", "/"):
        return ""
    if not value.startswith("/"):
        value = "/" + value
    return value.rstrip("/")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_or_none(name: str) -> str | None:
    value = _env(name)
    return value or None


def parse_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in TRUTHY:
        return True
    if value in FALSY:
        return False
    return default


@dataclass(frozen=True)
class EnvSettings:
    """Everything Franchisarr can be bootstrapped with from the environment."""

    base_url: str
    log_level: str

    #: Sets the Secure flag on cookies. Off by default because most installs sit on a LAN over
    #: plain HTTP, where a Secure cookie would simply never be sent and nobody could log in.
    session_cookie_secure: bool = False

    plex_url: str | None = None
    plex_token: str | None = None

    tmdb_api_key: str | None = None
    tmdb_cache_ttl_days: int | None = None

    #: Optional. Buys franchise logos on the collection screens and nothing else; every feature
    #: works without it.
    fanart_api_key: str | None = None

    scan_schedule_cron: str | None = None
    webhook_url: str | None = None
    webhook_format: str | None = None
    cross_instance_dedup: bool | None = None

    # Consumed in Phase 4, when there is a Radarr/Sonarr client to validate them against before
    # they are written to the instance tables.
    radarr_url: str | None = None
    radarr_api_key: str | None = None
    sonarr_url: str | None = None
    sonarr_api_key: str | None = None

    # Consumed in Phase 2, when the local-admin login exists to hash a password for.
    admin_username: str | None = None
    admin_password: str | None = None

    def secret_values(self) -> list[str]:
        """Values that must never reach a log line or a rendered page.

        Registered with the logging secret filter at startup so a token that leaks into, say, a
        third-party library's exception message is still redacted (docs/DEVELOPMENT.md convention 3).
        """
        candidates = [
            self.plex_token,
            self.tmdb_api_key,
            self.radarr_api_key,
            self.sonarr_api_key,
            self.admin_password,
        ]
        return [value for value in candidates if value]


def get_settings() -> EnvSettings:
    ttl_raw = _env("TMDB_CACHE_TTL_DAYS")
    dedup_raw = _env("CROSS_INSTANCE_DEDUP")

    return EnvSettings(
        base_url=_normalize_base_url(os.environ.get("BASE_URL", "/")),
        log_level=(_env("LOG_LEVEL") or "INFO").upper(),
        session_cookie_secure=parse_bool(_env("SESSION_COOKIE_SECURE"), False),
        plex_url=_env_or_none("PLEX_URL"),
        plex_token=_env_or_none("PLEX_TOKEN"),
        tmdb_api_key=_env_or_none("TMDB_API_KEY"),
        fanart_api_key=_env_or_none("FANART_API_KEY"),
        tmdb_cache_ttl_days=int(ttl_raw) if ttl_raw.isdigit() else None,
        scan_schedule_cron=_env_or_none("SCAN_SCHEDULE_CRON"),
        webhook_url=_env_or_none("WEBHOOK_URL"),
        webhook_format=_env_or_none("WEBHOOK_FORMAT"),
        cross_instance_dedup=parse_bool(dedup_raw) if dedup_raw else None,
        radarr_url=_env_or_none("RADARR_URL"),
        radarr_api_key=_env_or_none("RADARR_API_KEY"),
        sonarr_url=_env_or_none("SONARR_URL"),
        sonarr_api_key=_env_or_none("SONARR_API_KEY"),
        admin_username=_env_or_none("ADMIN_USERNAME"),
        admin_password=_env_or_none("ADMIN_PASSWORD"),
    )
