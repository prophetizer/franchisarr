"""Ties Plex sign-in to a Franchisarr user account.

Keeps the two identifiers the sign-in check depends on:

* **client id** -- a stable UUID identifying this install to plex.tv. Generated once and kept,
  because plex.tv ties a PIN to the client identifier that created it; a value that changed per
  request would break the flow mid-sign-in.
* **machine identifier** -- which Plex server each configured `MediaServer` row *is*. Sign-in is
  refused unless the account can reach one of those specific servers, so this is a
  security-relevant value, not a cache.
"""

from __future__ import annotations

import logging
import uuid

from sqlmodel import Session, col, select

from app.auth import plex_oauth
from app.clients.plex_client import PlexClient, PlexClientError
from app.models import MediaServer, User
from app.services.settings_service import SettingKey, get_setting, set_setting

logger = logging.getLogger(__name__)


class PlexAccessDenied(RuntimeError):
    """The Plex account is valid but has no access to this install's Plex server."""


def get_or_create_client_id(session: Session) -> str:
    client_id = get_setting(session, SettingKey.PLEX_CLIENT_ID)
    if client_id:
        return client_id

    client_id = str(uuid.uuid4())
    set_setting(session, SettingKey.PLEX_CLIENT_ID, client_id)
    session.commit()
    logger.info("Generated a Plex client identifier for this install")
    return client_id


def known_plex_servers(session: Session) -> list[MediaServer]:
    """Enabled Plex servers whose identity has been learned -- the ones sign-in can check."""
    from app.services import media_server_service

    return [s for s in media_server_service.plex_servers(session) if s.machine_identifier]


def plex_sign_in_available(session: Session) -> bool:
    return bool(known_plex_servers(session))


def discover_machine_identifier(
    session: Session, server: MediaServer, client: PlexClient
) -> str | None:
    """Learn which Plex server this row points at, and remember it on the row.

    Called when the connection is configured or used. Failure is not fatal here -- it just means
    Plex sign-in through this server stays unavailable until it can be reached, which is the
    correct conservative outcome.
    """
    try:
        machine_identifier = client.server.machineIdentifier
    except PlexClientError as exc:
        logger.warning("Could not determine the identity of Plex server %r: %s", server.name, exc)
        return None

    if machine_identifier and server.machine_identifier != str(machine_identifier):
        server.machine_identifier = str(machine_identifier)
        session.add(server)
        session.commit()
        logger.info("Recorded the machine identifier of Plex server %r", server.name)
    return machine_identifier


def provision_plex_user(session: Session, account: plex_oauth.PlexAccount, *, is_owner: bool) -> User:
    """Find or create the local record for a Plex account.

    The server owner administers the install. Someone the library is shared with gets an ordinary
    account: their own dismiss list, but no settings or instance configuration.
    """
    user = session.exec(select(User).where(col(User.external_user_id) == account.id)).first()

    if user is None:
        user = User(
            auth_provider="plex",
            external_user_id=account.id,
            external_username=account.username,
            is_admin=is_owner,
        )
        session.add(user)
        logger.info("Provisioned Plex user %r (admin=%s)", account.username, is_owner)
    else:
        user.external_username = account.username
        # Ownership can change -- a server can be handed over, or sharing revoked and regranted.
        user.is_admin = user.is_admin or is_owner
        session.add(user)

    session.commit()
    session.refresh(user)
    return user


def sign_in_with_plex_token(session: Session, token: str) -> User:
    """Turn a verified plex.tv token into a signed-in user.

    Raises PlexAccessDenied unless the account can reach one of *this* install's Plex servers.
    That check is the entire reason this function exists rather than callers trusting the token.
    Owning any of them administers the install.
    """
    client_id = get_or_create_client_id(session)
    servers = known_plex_servers(session)
    if not servers:
        raise PlexAccessDenied(
            "Plex sign-in isn't available: no Plex server's identity is known yet."
        )

    reachable = [s for s in servers
                 if plex_oauth.has_server_access(client_id, token, s.machine_identifier)]
    if not reachable:
        raise PlexAccessDenied(
            "That Plex account doesn't have access to this install's Plex libraries."
        )

    account = plex_oauth.get_account(client_id, token)
    is_owner = any(plex_oauth.owns_server(client_id, token, s.machine_identifier) for s in reachable)
    return provision_plex_user(session, account, is_owner=is_owner)



class MediaServerSignInUnavailable(RuntimeError):
    """The named server is Plex (which signs in by PIN), disabled, or doesn't exist."""


def sign_in_with_media_server(
    session: Session, server_id: int | None, username: str, password: str
) -> User:
    """Sign in with a Jellyfin or Emby account on one of the configured servers.

    The server itself is the authorisation: an account that can sign in there is an account on
    *this* install's server, which is what the Plex flow establishes with its server-access
    check. An administrator there administers here; anyone else gets an ordinary account with
    their own dismiss list.

    Raises EmbyAuthError for a wrong username or password, EmbyClientError when the server can't
    be reached, and MediaServerSignInUnavailable when this install isn't set up for it.
    """
    from app.clients.emby_client import EmbyLikeClient
    from app.services import media_server_service

    candidates = media_server_service.password_servers(session)
    if server_id is None and len(candidates) == 1:
        server_id = candidates[0].id
    server = next((s for s in candidates if s.id == server_id), None)
    if server is None:
        raise MediaServerSignInUnavailable("That server isn't available to sign in with.")
    client = media_server_service.client_for(server)
    assert isinstance(client, EmbyLikeClient)
    account = client.authenticate(username, password)
    provider = client.kind.value
    external_id = f"{provider}:{account['user_id']}"

    user = session.exec(select(User).where(col(User.external_user_id) == external_id)).first()
    if user is None:
        user = User(auth_provider=provider, external_user_id=external_id,
                    external_username=account["username"], is_admin=account["is_admin"])
        session.add(user)
        logger.info("Provisioned %s user %r (admin=%s)", provider, account["username"], account["is_admin"])
    else:
        user.external_username = account["username"]
        user.is_admin = user.is_admin or account["is_admin"]
        session.add(user)
    session.commit()
    session.refresh(user)
    return user
