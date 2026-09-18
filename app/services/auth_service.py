"""Ties Plex sign-in to a Franchisarr user account.

Keeps the two identifiers the sign-in check depends on:

* **client id** -- a stable UUID identifying this install to plex.tv. Generated once and kept,
  because plex.tv ties a PIN to the client identifier that created it; a value that changed per
  request would break the flow mid-sign-in.
* **machine identifier** -- which Plex server this install is *for*. Sign-in is refused unless
  the account can reach that specific server, so this is a security-relevant value, not a cache.
"""

from __future__ import annotations

import logging
import uuid

from sqlmodel import Session, col, select

from app.auth import plex_oauth
from app.clients.plex_client import PlexClient, PlexClientError
from app.models import User
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


def get_machine_identifier(session: Session) -> str | None:
    return get_setting(session, SettingKey.PLEX_MACHINE_IDENTIFIER) or None


def remember_machine_identifier(session: Session, machine_identifier: str) -> None:
    if get_machine_identifier(session) != machine_identifier:
        set_setting(session, SettingKey.PLEX_MACHINE_IDENTIFIER, machine_identifier)
        session.commit()
        logger.info("Recorded the configured Plex server's machine identifier")


def discover_machine_identifier(session: Session, client: PlexClient) -> str | None:
    """Learn which server this install points at, and remember it.

    Called when the Plex connection is configured or used. Failure is not fatal here -- it just
    means Plex sign-in stays unavailable until the server can be reached, which is the correct
    conservative outcome.
    """
    try:
        machine_identifier = client.server.machineIdentifier
    except PlexClientError as exc:
        logger.warning("Could not determine the Plex server identity: %s", exc)
        return None

    if machine_identifier:
        remember_machine_identifier(session, str(machine_identifier))
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

    Raises PlexAccessDenied unless the account can reach *this* install's Plex server. That check
    is the entire reason this function exists rather than callers trusting the token.
    """
    client_id = get_or_create_client_id(session)
    machine_identifier = get_machine_identifier(session)

    if not plex_oauth.has_server_access(client_id, token, machine_identifier):
        raise PlexAccessDenied(
            "That Plex account doesn't have access to this server's Plex library."
        )

    account = plex_oauth.get_account(client_id, token)
    is_owner = plex_oauth.owns_server(client_id, token, machine_identifier)
    return provision_plex_user(session, account, is_owner=is_owner)



class MediaServerSignInUnavailable(RuntimeError):
    """The configured server is Plex (which signs in by PIN) or nothing is configured."""


def sign_in_with_media_server(session: Session, username: str, password: str) -> User:
    """Sign in with a Jellyfin or Emby account on the configured server.

    The server itself is the authorisation: an account that can sign in there is an account on
    *this* install's server, which is what the Plex flow establishes with its server-access
    check. An administrator there administers here; anyone else gets an ordinary account with
    their own dismiss list.

    Raises EmbyAuthError for a wrong username or password, EmbyClientError when the server can't
    be reached, and MediaServerSignInUnavailable when this install isn't set up for it.
    """
    from app.clients.emby_client import EmbyLikeClient
    from app.services import media_server_service

    client = media_server_service.client_for(session)
    if not isinstance(client, EmbyLikeClient):
        raise MediaServerSignInUnavailable(
            f"{media_server_service.label(session)} sign-in isn't available on this install."
        )
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
