"""Which media server this install reads, and a client for it.

One server per install. The setting says which; the matching URL and credential say where. A
missing credential is reported in the server's own terms ("No Jellyfin connection is configured
yet"), because that is the sentence the person has to act on.
"""

from __future__ import annotations

from sqlmodel import Session

from app.clients.media_server import MediaServerClient, MediaServerKind
from app.services.settings_service import SettingKey, get_setting

LABELS = {MediaServerKind.PLEX: "Plex", MediaServerKind.JELLYFIN: "Jellyfin", MediaServerKind.EMBY: "Emby"}


def kind(session: Session) -> MediaServerKind:
    raw = (get_setting(session, SettingKey.MEDIA_SERVER) or "plex").strip().lower()
    try:
        return MediaServerKind(raw)
    except ValueError:
        return MediaServerKind.PLEX


def label(session: Session) -> str:
    return LABELS[kind(session)]


def credentials(session: Session) -> tuple[str | None, str | None]:
    """(url, credential) for the configured server, or Nones."""
    which = kind(session)
    if which == MediaServerKind.PLEX:
        return get_setting(session, SettingKey.PLEX_URL), get_setting(session, SettingKey.PLEX_TOKEN)
    if which == MediaServerKind.JELLYFIN:
        return get_setting(session, SettingKey.JELLYFIN_URL), get_setting(session, SettingKey.JELLYFIN_API_KEY)
    return get_setting(session, SettingKey.EMBY_URL), get_setting(session, SettingKey.EMBY_API_KEY)


def is_configured(session: Session) -> bool:
    url, credential = credentials(session)
    return bool(url and credential)


def missing_message(session: Session) -> str:
    return f"No {label(session)} connection is configured yet."


def client_for(session: Session) -> MediaServerClient | None:
    """A client for the configured server, or None when it isn't configured."""
    url, credential = credentials(session)
    if not (url and credential):
        return None
    which = kind(session)
    if which == MediaServerKind.PLEX:
        from app.clients.plex_client import PlexClient

        return PlexClient(url, credential)
    from app.clients.emby_client import EmbyLikeClient

    return EmbyLikeClient(url, credential, kind=which)
