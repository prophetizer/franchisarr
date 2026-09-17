"""Read/write access to the install-wide `settings` key/value table, plus first-boot seeding.

Seeding rule (PROJECT_PLAN.md section 6): env vars populate the table **only when it is
completely empty**. Once a single row exists, this module never writes from the environment
again. The alternative -- filling in individually missing keys on every boot -- resurrects
settings the user deliberately cleared in the UI, because a stale value in docker-compose
outlives the UI edit. First boot is the only moment the two can't disagree.
"""

from __future__ import annotations

import logging

from sqlmodel import Session, select

from app.config import EnvSettings, parse_bool
from app.models import Setting, WebhookFormat, utcnow

logger = logging.getLogger(__name__)


class SettingKey:
    """Canonical setting names. Constants rather than bare strings so a typo is an
    AttributeError at import time instead of a silently missing setting at runtime."""

    BASE_URL = "base_url"
    PLEX_URL = "plex_url"
    PLEX_TOKEN = "plex_token"
    TMDB_API_KEY = "tmdb_api_key"
    FANART_API_KEY = "fanart_api_key"
    TMDB_CACHE_TTL_DAYS = "tmdb_cache_ttl_days"
    SCAN_SCHEDULE_CRON = "scan_schedule_cron"
    WEBHOOK_URL = "webhook_url"
    WEBHOOK_FORMAT = "webhook_format"
    CROSS_INSTANCE_DEDUP = "cross_instance_dedup"
    #: Missing films rated below this are tucked away rather than listed. "0" is off.
    MIN_GAP_RATING = "min_gap_rating"
    #: A director appears on the Directors page once this many of their films are owned.
    MIN_DIRECTOR_FILMS = "min_director_films"

    # Generated or discovered at runtime rather than configured, so deliberately absent from
    # DEFAULTS: a default value for either would be actively wrong.
    PLEX_CLIENT_ID = "plex_client_id"
    PLEX_MACHINE_IDENTIFIER = "plex_machine_identifier"

    #: Where to look for new releases. Empty uses the built-in default; set it to point at a fork,
    #: or at nothing, if you'd rather the install asked no one.
    UPDATE_RELEASES_URL = "update_releases_url"


#: Values used when neither the environment nor the user has said otherwise.
DEFAULTS: dict[str, str] = {
    SettingKey.BASE_URL: "",
    SettingKey.PLEX_URL: "",
    SettingKey.PLEX_TOKEN: "",
    SettingKey.TMDB_API_KEY: "",
    SettingKey.FANART_API_KEY: "",
    SettingKey.TMDB_CACHE_TTL_DAYS: "7",
    SettingKey.SCAN_SCHEDULE_CRON: "",
    SettingKey.WEBHOOK_URL: "",
    SettingKey.WEBHOOK_FORMAT: WebhookFormat.GENERIC.value,
    SettingKey.CROSS_INSTANCE_DEDUP: "false",
    SettingKey.MIN_GAP_RATING: "0",
    SettingKey.MIN_DIRECTOR_FILMS: "5",
    SettingKey.UPDATE_RELEASES_URL: "",
}

#: Theming moved to environment variables in 0.2.0 (TP_THEME and friends), so a homelab can set
#: it once centrally instead of per app. Any `theme_url` row left in an upgraded database is
#: simply ignored.

#: Settings whose values must never be logged or rendered unmasked.
SECRET_KEYS = frozenset(
    {SettingKey.PLEX_TOKEN, SettingKey.TMDB_API_KEY, SettingKey.FANART_API_KEY}
)


def get_setting(session: Session, key: str, default: str | None = None) -> str | None:
    row = session.get(Setting, key)
    if row is None:
        return default if default is not None else DEFAULTS.get(key)
    return row.value


def get_bool_setting(session: Session, key: str, default: bool = False) -> bool:
    return parse_bool(get_setting(session, key), default)


def get_int_setting(session: Session, key: str, default: int) -> int:
    raw = get_setting(session, key)
    if raw is None or not raw.strip().lstrip("-").isdigit():
        return default
    return int(raw)


def set_setting(session: Session, key: str, value: str | None) -> Setting:
    row = session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
    else:
        row.value = value
        row.updated_at = utcnow()
    session.add(row)
    return row


def get_all_settings(session: Session) -> dict[str, str | None]:
    """Every stored setting, with defaults filled in for keys not yet written.

    Returns raw values including secrets -- callers rendering these to a page or a log must mask
    them first (see `app.logging_config.mask_secret` and `SECRET_KEYS`).
    """
    stored = {row.key: row.value for row in session.exec(select(Setting)).all()}
    return {**DEFAULTS, **stored}


def is_seeded(session: Session) -> bool:
    return session.exec(select(Setting).limit(1)).first() is not None


def _env_values(env: EnvSettings) -> dict[str, str]:
    """Env-provided values, keyed by setting name. Absent env vars are simply omitted so the
    defaults apply."""
    values: dict[str, str] = {}
    if env.base_url:
        values[SettingKey.BASE_URL] = env.base_url
    if env.plex_url:
        values[SettingKey.PLEX_URL] = env.plex_url
    if env.plex_token:
        values[SettingKey.PLEX_TOKEN] = env.plex_token
    if env.tmdb_api_key:
        values[SettingKey.TMDB_API_KEY] = env.tmdb_api_key
    if env.fanart_api_key:
        values[SettingKey.FANART_API_KEY] = env.fanart_api_key
    if env.tmdb_cache_ttl_days is not None:
        values[SettingKey.TMDB_CACHE_TTL_DAYS] = str(env.tmdb_cache_ttl_days)
    if env.scan_schedule_cron:
        values[SettingKey.SCAN_SCHEDULE_CRON] = env.scan_schedule_cron
    if env.webhook_url:
        values[SettingKey.WEBHOOK_URL] = env.webhook_url
    if env.webhook_format:
        values[SettingKey.WEBHOOK_FORMAT] = env.webhook_format.lower()
    if env.cross_instance_dedup is not None:
        values[SettingKey.CROSS_INSTANCE_DEDUP] = str(env.cross_instance_dedup).lower()
    return values


def seed_settings_from_env(session: Session, env: EnvSettings) -> bool:
    """Populate an empty settings table from the environment. Returns True if it seeded.

    A populated table is left completely untouched -- no merging, no filling gaps.
    """
    if is_seeded(session):
        logger.debug("settings table already populated; skipping env bootstrap")
        return False

    from_env = _env_values(env)
    for key, value in {**DEFAULTS, **from_env}.items():
        set_setting(session, key, value)
    session.commit()

    seeded_from_env = sorted(from_env)
    logger.info(
        "seeded settings table on first boot (%d keys, %d from the environment: %s)",
        len(DEFAULTS),
        len(seeded_from_env),
        ", ".join(seeded_from_env) or "none",
    )
    return True
