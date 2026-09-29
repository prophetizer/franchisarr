"""Read/write access to the install-wide `settings` key/value table, plus first-boot seeding.

Seeding rule (docs/DESIGN.md section 6): env vars populate the table **only when it is
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
    #: Which media server this install reads: plex, jellyfin or emby. One per install for now.
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
    #: Taste settings, each defaulting to the cleaner list. Off means "folded away", never
    #: "deleted": the hidden things stay reachable on each page.
    FRANCHISE_INCLUDE_TV_FILMS = "franchise_include_tv_films"
    DIRECTOR_INCLUDE_SHORTS = "director_include_shorts"
    #: Set once the first-run preferences page has been seen (saved or skipped).
    PREFERENCES_REVIEWED = "preferences_reviewed"

    # Generated or discovered at runtime rather than configured, so deliberately absent from
    # DEFAULTS: a default value for either would be actively wrong.
    PLEX_CLIENT_ID = "plex_client_id"

    #: Where to look for new releases. Empty uses the built-in default; set it to point at a fork,
    #: or at nothing, if you'd rather the install asked no one.
    UPDATE_RELEASES_URL = "update_releases_url"
    #: Whether Franchisarr asks GitHub's public releases API for newer versions. The only
    #: request the app makes that the user didn't configure, so it can be turned off.
    UPDATE_CHECK = "update_check"
    #: Whether anyone besides an administrator may sign in: people the Plex server is shared
    #: with, and Jellyfin/Emby accounts that aren't administrators there. Off unless an admin
    #: turns it on, because "can reach my Plex" is a much wider group than "runs this house".
    ALLOW_MEMBER_SIGNIN = "allow_member_signin"
    #: Set by "Use only this server": the ids of the servers it switched off, so "Turn the
    #: others back on" restores exactly those. Absent when not in use. Never restored from a
    #: backup -- the ids are this install's own.
    SOLO_RESTORE = "solo_restore"
    #: Playlist sync: every video playlist syncs, new ones too, except those switched off.
    PLAYLIST_SYNC_ALL = "playlist_sync_all"
    #: Playlist sync: a "... (Franchisarr)" playlist on one server is built on the others from
    #: their own libraries, and deleting it on one deletes it everywhere.
    PLAYLIST_SYNC_FRANCHISARR = "playlist_sync_franchisarr"
    #: Playlist sync's own schedule (cron, like the scan's); empty for none. Syncs also follow
    #: every scan.
    PLAYLIST_SYNC_CRON = "playlist_sync_cron"


#: Values used when neither the environment nor the user has said otherwise.
DEFAULTS: dict[str, str] = {
    SettingKey.BASE_URL: "",
    SettingKey.TMDB_API_KEY: "",
    SettingKey.FANART_API_KEY: "",
    SettingKey.TMDB_CACHE_TTL_DAYS: "7",
    SettingKey.SCAN_SCHEDULE_CRON: "",
    SettingKey.WEBHOOK_URL: "",
    SettingKey.WEBHOOK_FORMAT: WebhookFormat.GENERIC.value,
    SettingKey.CROSS_INSTANCE_DEDUP: "false",
    SettingKey.MIN_GAP_RATING: "0",
    SettingKey.MIN_DIRECTOR_FILMS: "5",
    SettingKey.FRANCHISE_INCLUDE_TV_FILMS: "false",
    SettingKey.DIRECTOR_INCLUDE_SHORTS: "false",
    SettingKey.PREFERENCES_REVIEWED: "false",
    SettingKey.UPDATE_RELEASES_URL: "",
    SettingKey.UPDATE_CHECK: "true",
    SettingKey.ALLOW_MEMBER_SIGNIN: "false",
    SettingKey.PLAYLIST_SYNC_ALL: "false",
    SettingKey.PLAYLIST_SYNC_FRANCHISARR: "false",
    SettingKey.PLAYLIST_SYNC_CRON: "",
}

#: Theming moved to environment variables in 0.2.0 (TP_THEME and friends), so a homelab can set
#: it once centrally instead of per app. Any `theme_url` row left in an upgraded database is
#: simply ignored.

#: Settings whose values must never be logged or rendered unmasked.
SECRET_KEYS = frozenset({
    SettingKey.TMDB_API_KEY, SettingKey.FANART_API_KEY,
    # A Discord webhook URL lets anyone post to the channel, and an Apprise URL carries the
    # service's token in the URL itself.
    SettingKey.WEBHOOK_URL,
})


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


#: Filled from the environment on every start while still empty. The TMDb key only: nothing
#: works without it, so an empty one is never a choice -- first boot used to save it empty and
#: then ignore a TMDB_API_KEY added to .env afterwards, for good (a Reddit report, 0.33.1). A
#: schedule or webhook someone cleared in the app is a choice, and must not come back from the
#: environment at every restart, so nothing else is refilled.
REFILL_FROM_ENV = frozenset({SettingKey.TMDB_API_KEY})


def seed_settings_from_env(session: Session, env: EnvSettings) -> bool:
    """Populate an empty settings table from the environment. Returns True if it seeded.

    A populated table is left alone except for REFILL_FROM_ENV keys that are still empty. Other
    environment values that differ from what's saved are named in the log (never their values),
    so "I changed it in .env and nothing happened" has an answer.
    """
    from_env = _env_values(env)
    if is_seeded(session):
        filled = [key for key in sorted(REFILL_FROM_ENV & from_env.keys())
                  if not (get_setting(session, key) or "").strip()]
        for key in filled:
            set_setting(session, key, from_env[key])
        if filled:
            session.commit()
            logger.info("Filled %s from the environment (it was empty)", ", ".join(filled))
        # BASE_URL is read from the environment on every start anyway.
        ignored = [key for key in sorted(from_env) if key not in filled and key != SettingKey.BASE_URL
                   and (get_setting(session, key) or "") not in ("", from_env[key])]
        if ignored:
            logger.info("%s in the environment differ from the saved value%s; the saved one is used. "
                        "Change it in Settings.", ", ".join(ignored), "" if len(ignored) == 1 else "s")
        return False

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
