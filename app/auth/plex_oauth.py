"""Plex sign-in via plex.tv's PIN flow (PROJECT_PLAN.md technical challenge #2).

The flow, which is what Overseerr and Tautulli use:

1. Ask plex.tv for a PIN. It returns an id and a short code.
2. Send the user to app.plex.tv with that code; they log in to Plex, not to us. We never see
   their Plex password.
3. Poll the PIN until plex.tv attaches an auth token to it.
4. **Verify that token can actually reach *this* Plex server**, then provision the user.

Step 4 is the one that matters. A valid Plex token only proves the person has *a* Plex account --
there are millions. Without checking that their account owns or is shared on the specific server
this install is configured against, "Sign in with Plex" would let any stranger into someone's
media library. If that check cannot be performed, sign-in is refused rather than assumed.

No app registration with Plex is required: X-Plex-Client-Identifier is simply a stable UUID we
generate once per install and keep in settings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from app import __version__
from app.logging_config import register_secret

logger = logging.getLogger(__name__)

PLEX_PINS_URL = "https://plex.tv/api/v2/pins"
PLEX_USER_URL = "https://plex.tv/api/v2/user"
PLEX_RESOURCES_URL = "https://plex.tv/api/v2/resources"
PLEX_AUTH_APP_URL = "https://app.plex.tv/auth"

PRODUCT_NAME = "Franchisarr"
DEFAULT_TIMEOUT = 15


class PlexOAuthError(RuntimeError):
    """plex.tv could not be reached, or answered with something unusable."""


@dataclass(frozen=True)
class PlexPin:
    id: int
    code: str


@dataclass(frozen=True)
class PlexAccount:
    id: str
    username: str
    email: str | None = None


def _headers(client_id: str, token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "X-Plex-Product": PRODUCT_NAME,
        "X-Plex-Version": __version__,
        "X-Plex-Client-Identifier": client_id,
        "X-Plex-Device": PRODUCT_NAME,
        "X-Plex-Platform": "Web",
    }
    if token:
        headers["X-Plex-Token"] = token
    return headers


def _request(method: str, url: str, **kwargs) -> requests.Response:
    try:
        response = requests.request(method, url, timeout=DEFAULT_TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        # Deliberately generic: this reaches a UI, and transport errors carry request detail.
        raise PlexOAuthError("Could not reach plex.tv") from exc

    if response.status_code >= 400:
        raise PlexOAuthError(f"plex.tv returned {response.status_code}")
    return response


def create_pin(client_id: str) -> PlexPin:
    """Ask plex.tv for a new sign-in PIN."""
    response = _request(
        "POST", PLEX_PINS_URL, headers=_headers(client_id), data={"strong": "true"}
    )
    payload = response.json()
    try:
        return PlexPin(id=int(payload["id"]), code=str(payload["code"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PlexOAuthError("plex.tv returned an unexpected PIN response") from exc


def build_auth_url(client_id: str, code: str, *, forward_url: str | None = None) -> str:
    """The app.plex.tv URL to send the user to."""
    params = {
        "clientID": client_id,
        "code": code,
        "context[device][product]": PRODUCT_NAME,
        "context[device][version]": __version__,
    }
    if forward_url:
        params["forwardUrl"] = forward_url
    return f"{PLEX_AUTH_APP_URL}#?{urlencode(params)}"


def check_pin(client_id: str, pin_id: int) -> str | None:
    """Return the auth token once the user has signed in, or None while still waiting."""
    response = _request(
        "GET", f"{PLEX_PINS_URL}/{pin_id}", headers=_headers(client_id)
    )
    token = response.json().get("authToken")
    if not token:
        return None

    register_secret(token)
    return str(token)


def get_account(client_id: str, token: str) -> PlexAccount:
    """Who the token belongs to."""
    payload = _request("GET", PLEX_USER_URL, headers=_headers(client_id, token)).json()
    try:
        return PlexAccount(
            id=str(payload["id"]),
            username=str(payload.get("username") or payload.get("title") or payload["id"]),
            email=payload.get("email"),
        )
    except (KeyError, TypeError) as exc:
        raise PlexOAuthError("plex.tv returned an unexpected account response") from exc


def accessible_servers(client_id: str, token: str) -> dict[str, bool]:
    """Every Plex server this account may use, mapped to whether the account *owns* it.

    Ownership decides who gets admin: the person whose server this is administers the install,
    and someone the library is merely shared with does not.
    """
    payload = _request(
        "GET", PLEX_RESOURCES_URL, headers=_headers(client_id, token),
        params={"includeHttps": "1", "includeRelay": "1"},
    ).json()

    if not isinstance(payload, list):
        raise PlexOAuthError("plex.tv returned an unexpected resources response")

    return {
        str(item["clientIdentifier"]): bool(item.get("owned"))
        for item in payload
        if isinstance(item, dict)
        and item.get("clientIdentifier")
        and "server" in str(item.get("provides", "")).split(",")
    }


def accessible_server_ids(client_id: str, token: str) -> set[str]:
    return set(accessible_servers(client_id, token))


def owns_server(client_id: str, token: str, machine_identifier: str | None) -> bool:
    """Whether this account owns the configured server, i.e. should administer this install."""
    if not machine_identifier:
        return False
    return accessible_servers(client_id, token).get(machine_identifier, False)


def has_server_access(client_id: str, token: str, machine_identifier: str | None) -> bool:
    """Whether this account can reach the Plex server this install is configured against.

    A missing machine identifier returns False. Not knowing which server to check is not a reason
    to let someone in -- it is the reason not to.
    """
    if not machine_identifier:
        logger.warning(
            "Refusing Plex sign-in: this install has no known Plex server to check access "
            "against. Configure the Plex connection first."
        )
        return False

    allowed = accessible_server_ids(client_id, token)
    if machine_identifier in allowed:
        return True

    logger.warning(
        "Refusing Plex sign-in: the account has access to %d Plex server(s), none of which is "
        "this one.",
        len(allowed),
    )
    return False
