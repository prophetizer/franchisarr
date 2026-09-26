"""The two sign-in holes found in the 2026-09-26 review, each reproduced as an attack.

1. The rate limiter read the *first* X-Forwarded-For entry, which the client writes, so a
   fresh fake address per request meant unlimited password guesses.
2. The Plex PIN id sat in a cookie as a plain integer, so a guessed PIN id could be polled from
   someone else's browser and collect the owner's session.
"""

from __future__ import annotations

import itertools

import pytest
import responses
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.auth.local_admin import create_local_admin
from app.auth.plex_oauth import PLEX_PINS_URL, PLEX_RESOURCES_URL, PLEX_USER_URL
from app.auth.sessions import COOKIE_NAME
from app.db import get_engine
from app.hardening import LoginLimiter, client_key
from sqlmodel import Session

from tests.test_auth_routes import OUR_SERVER, _add_library, _known_plex_server

BASE = "/franchisarr"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
        yield test_client


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "method": "POST", "path": "/login", "headers": headers,
                    "client": (peer, 5555), "query_string": b""})


# ------------------------------------------------------------------ whose address counts


def test_a_forwarded_header_from_the_internet_is_ignored() -> None:
    """Only a proxy on the local network gets to say who the client is."""
    assert client_key(_request("8.8.8.8", "10.1.1.1")) == "8.8.8.8"


def test_behind_one_proxy_the_client_is_the_entry_the_proxy_appended(monkeypatch) -> None:
    # The client wrote "1.1.1.1"; Traefik appended the address it actually saw.
    assert client_key(_request("172.18.0.2", "1.1.1.1, 198.51.100.7")) == "198.51.100.7"
    assert client_key(_request("172.18.0.2")) == "172.18.0.2"

    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")    # e.g. Cloudflare in front of Traefik
    assert client_key(_request("172.18.0.2", "1.1.1.1, 198.51.100.7, 104.16.0.1")) == "198.51.100.7"


def test_rotating_forwarded_addresses_no_longer_buys_more_guesses(client: TestClient) -> None:
    """The attack as the review ran it: a new X-Forwarded-For on every attempt."""
    for n in range(10):
        response = client.post(f"{BASE}/login", data={"username": "admin", "password": f"guess{n}"},
                               headers={"X-Forwarded-For": f"198.51.100.{n}"})
        assert response.status_code == 401

    blocked = client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD},
                          headers={"X-Forwarded-For": "198.51.100.200"})
    assert blocked.status_code == 429


def test_guesses_spread_over_many_real_addresses_still_hit_a_per_username_limit(
    client: TestClient, monkeypatch
) -> None:
    import app.hardening as hardening

    addresses = (f"198.51.100.{n}" for n in itertools.count())
    monkeypatch.setattr(hardening, "client_key", lambda request: next(addresses))

    for n in range(hardening.USERNAME_ATTEMPTS):
        assert client.post(f"{BASE}/login", data={"username": "Admin", "password": f"g{n}"}).status_code == 401
    assert client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD}).status_code == 429
    # A different account is unaffected.
    assert client.post(f"{BASE}/login", data={"username": "someone", "password": "x"}).status_code == 401


def test_the_limiter_cannot_be_grown_without_bound() -> None:
    limiter = LoginLimiter(max_keys=100)
    for n in range(1_000):
        limiter.failed(f"k{n}")
    assert len(limiter._failures) == 100


# ------------------------------------------------------------------ Plex PIN


def _plex_signin_mocks() -> None:
    responses.add(responses.POST, PLEX_PINS_URL, json={"id": 77, "code": "WXYZ"})
    responses.add(responses.GET, f"{PLEX_PINS_URL}/77", json={"id": 77, "authToken": "tok"})
    responses.add(responses.GET, PLEX_RESOURCES_URL,
                  json=[{"clientIdentifier": OUR_SERVER, "provides": "server", "owned": True}])
    responses.add(responses.GET, PLEX_USER_URL, json={"id": 5551234, "username": "owner"})


@responses.activate
def test_a_guessed_pin_number_gets_nothing(client: TestClient) -> None:
    """The attack: skip /auth/plex/start and poll with a PIN id someone else created."""
    _add_library()
    _known_plex_server()
    _plex_signin_mocks()

    client.cookies.set("franchisarr_plex_pin", "77")
    response = client.post(f"{BASE}/auth/plex/poll")

    assert response.status_code == 400
    assert COOKIE_NAME not in response.cookies
    assert not any(call.request.url.endswith("/77") for call in responses.calls), \
        "a guessed number must not even reach plex.tv"


@responses.activate
def test_the_pin_id_never_reaches_the_browser_and_a_handle_works_once(client: TestClient) -> None:
    _add_library()
    _known_plex_server()
    _plex_signin_mocks()

    started = client.post(f"{BASE}/auth/plex/start")
    handle = started.cookies.get("franchisarr_plex_pin")
    assert handle and handle != "77" and len(handle) >= 40

    assert client.post(f"{BASE}/auth/plex/poll").json()["status"] == "ok"

    client.cookies.set("franchisarr_plex_pin", handle)      # replay the spent handle
    replay = client.post(f"{BASE}/auth/plex/poll")
    assert replay.status_code == 400 and COOKIE_NAME not in replay.cookies


@responses.activate
def test_starting_plex_sign_ins_is_rate_limited(client: TestClient) -> None:
    _add_library()
    _known_plex_server()
    responses.add(responses.POST, PLEX_PINS_URL, json={"id": 77, "code": "WXYZ"})

    statuses = [client.post(f"{BASE}/auth/plex/start").status_code for _ in range(31)]

    assert statuses[:30] == [200] * 30 and statuses[30] == 429
