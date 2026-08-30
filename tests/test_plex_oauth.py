"""Plex PIN sign-in flow, and above all the server-access check.

Technical challenge #2: a valid Plex token only proves someone has *a* Plex account. Without
verifying their account can reach *this* server, "Sign in with Plex" would admit any stranger to
someone's media library. Several tests here exist purely to hold that line.
"""

from __future__ import annotations

import json

import pytest
import responses

from app.auth.plex_oauth import (
    PLEX_PINS_URL,
    PLEX_RESOURCES_URL,
    PLEX_USER_URL,
    PlexAccount,
    PlexOAuthError,
    accessible_server_ids,
    accessible_servers,
    build_auth_url,
    check_pin,
    create_pin,
    get_account,
    has_server_access,
    owns_server,
)

CLIENT_ID = "franchisarr-test-client-id"
OUR_SERVER = "abc123def456abc123def456abc123def456abc1"
SOMEONE_ELSES_SERVER = "9999999999999999999999999999999999999999"


def _resource(
    machine_id: str, *, provides: str = "server", name: str = "A Server", owned: bool = True
) -> dict:
    return {
        "name": name,
        "clientIdentifier": machine_id,
        "provides": provides,
        "owned": owned,
    }


# --------------------------------------------------------------------- pin creation


@responses.activate
def test_create_pin() -> None:
    responses.add(responses.POST, PLEX_PINS_URL, json={"id": 12345, "code": "ABCD"})

    pin = create_pin(CLIENT_ID)

    assert pin.id == 12345
    assert pin.code == "ABCD"
    assert responses.calls[0].request.headers["X-Plex-Client-Identifier"] == CLIENT_ID
    assert responses.calls[0].request.headers["X-Plex-Product"] == "Franchisarr"


@responses.activate
def test_create_pin_rejects_a_malformed_response() -> None:
    responses.add(responses.POST, PLEX_PINS_URL, json={"unexpected": True})

    with pytest.raises(PlexOAuthError):
        create_pin(CLIENT_ID)


@responses.activate
def test_plex_tv_being_unreachable_is_reported_clearly() -> None:
    responses.add(responses.POST, PLEX_PINS_URL, status=503)

    with pytest.raises(PlexOAuthError):
        create_pin(CLIENT_ID)


def test_build_auth_url_carries_the_code_and_client_id() -> None:
    url = build_auth_url(CLIENT_ID, "ABCD")

    assert url.startswith("https://app.plex.tv/auth#?")
    assert "code=ABCD" in url
    assert f"clientID={CLIENT_ID}" in url


def test_build_auth_url_never_contains_a_token() -> None:
    """The user authenticates against Plex, not against us; no credential belongs in this URL."""
    assert "Token" not in build_auth_url(CLIENT_ID, "ABCD")


# --------------------------------------------------------------------- polling


@responses.activate
def test_check_pin_returns_none_while_the_user_has_not_signed_in_yet() -> None:
    responses.add(responses.GET, f"{PLEX_PINS_URL}/1", json={"id": 1, "authToken": None})

    assert check_pin(CLIENT_ID, 1) is None


@responses.activate
def test_check_pin_returns_the_token_once_signed_in() -> None:
    responses.add(responses.GET, f"{PLEX_PINS_URL}/1", json={"id": 1, "authToken": "tok-abc123"})

    assert check_pin(CLIENT_ID, 1) == "tok-abc123"


@responses.activate
def test_a_returned_token_is_registered_for_log_redaction() -> None:
    from app.logging_config import clear_secrets, redact

    clear_secrets()
    responses.add(responses.GET, f"{PLEX_PINS_URL}/1", json={"id": 1, "authToken": "tok-abc123"})
    try:
        check_pin(CLIENT_ID, 1)
        assert "tok-abc123" not in redact("token is tok-abc123")
    finally:
        clear_secrets()


# --------------------------------------------------------------------- account


@responses.activate
def test_get_account() -> None:
    responses.add(
        responses.GET,
        PLEX_USER_URL,
        json={"id": 5551234, "username": "michael", "email": "michael@example.com"},
    )

    assert get_account(CLIENT_ID, "tok") == PlexAccount(
        id="5551234", username="michael", email="michael@example.com"
    )


@responses.activate
def test_get_account_falls_back_to_title_when_username_is_absent() -> None:
    """Managed/Home Plex accounts have a title but no username."""
    responses.add(responses.GET, PLEX_USER_URL, json={"id": 42, "title": "Kid Account"})

    assert get_account(CLIENT_ID, "tok").username == "Kid Account"


# --------------------------------------------------------------------- server access


@responses.activate
def test_owner_of_this_server_is_granted_access() -> None:
    responses.add(responses.GET, PLEX_RESOURCES_URL, json=[_resource(OUR_SERVER)])

    assert has_server_access(CLIENT_ID, "tok", OUR_SERVER) is True


@responses.activate
def test_a_user_the_server_is_shared_with_is_granted_access() -> None:
    responses.add(
        responses.GET,
        PLEX_RESOURCES_URL,
        json=[
            _resource(SOMEONE_ELSES_SERVER),
            _resource(OUR_SERVER, name="Shared With Me", owned=False),
        ],
    )

    assert has_server_access(CLIENT_ID, "tok", OUR_SERVER) is True


@responses.activate
def test_the_server_owner_is_distinguishable_from_a_shared_user() -> None:
    """Ownership decides who administers the install."""
    responses.add(responses.GET, PLEX_RESOURCES_URL, json=[_resource(OUR_SERVER, owned=True)])
    assert owns_server(CLIENT_ID, "tok", OUR_SERVER) is True


@responses.activate
def test_a_shared_user_does_not_own_the_server() -> None:
    responses.add(responses.GET, PLEX_RESOURCES_URL, json=[_resource(OUR_SERVER, owned=False)])
    assert owns_server(CLIENT_ID, "tok", OUR_SERVER) is False


@responses.activate
def test_a_stranger_with_a_valid_plex_account_is_refused() -> None:
    """The whole point of challenge #2: a valid token is not an authorisation."""
    responses.add(responses.GET, PLEX_RESOURCES_URL, json=[_resource(SOMEONE_ELSES_SERVER)])

    assert has_server_access(CLIENT_ID, "tok", OUR_SERVER) is False


@responses.activate
def test_an_account_with_no_servers_at_all_is_refused() -> None:
    responses.add(responses.GET, PLEX_RESOURCES_URL, json=[])

    assert has_server_access(CLIENT_ID, "tok", OUR_SERVER) is False


def test_access_is_refused_when_we_do_not_know_our_own_server() -> None:
    """Fails closed. Not knowing which server to check is a reason to refuse, not to admit --
    and it must not even ask plex.tv, which is why no HTTP mock is registered here."""
    assert has_server_access(CLIENT_ID, "tok", None) is False
    assert has_server_access(CLIENT_ID, "tok", "") is False


@responses.activate
def test_non_server_resources_are_ignored() -> None:
    """A player or a controller shares the resources list with servers; only servers count."""
    responses.add(
        responses.GET,
        PLEX_RESOURCES_URL,
        json=[_resource(OUR_SERVER, provides="player,controller")],
    )

    assert has_server_access(CLIENT_ID, "tok", OUR_SERVER) is False


@responses.activate
def test_multi_capability_servers_still_count() -> None:
    responses.add(
        responses.GET,
        PLEX_RESOURCES_URL,
        json=[_resource(OUR_SERVER, provides="server,player")],
    )

    assert accessible_server_ids(CLIENT_ID, "tok") == {OUR_SERVER}


@responses.activate
def test_a_malformed_resources_response_raises_rather_than_granting_access() -> None:
    responses.add(responses.GET, PLEX_RESOURCES_URL, body=json.dumps({"not": "a list"}))

    with pytest.raises(PlexOAuthError):
        accessible_server_ids(CLIENT_ID, "tok")


@responses.activate
def test_plex_tv_failure_during_the_access_check_raises_rather_than_granting_access() -> None:
    responses.add(responses.GET, PLEX_RESOURCES_URL, status=500)

    with pytest.raises(PlexOAuthError):
        has_server_access(CLIENT_ID, "tok", OUR_SERVER)
