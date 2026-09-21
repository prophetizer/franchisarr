"""What a public announcement invites: brute-forced logins, cross-site posts, oversized
uploads, framing. Each guard has one test that shows it biting and one that shows it staying
out of the way of normal use."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.hardening import LoginLimiter, login_limiter, security_headers

BASE = "/franchisarr"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def client(app_factory):
    login_limiter.reset()
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
        yield test_client
    login_limiter.reset()


# ------------------------------------------------------------------ login rate limit


def test_ten_wrong_passwords_lock_the_address_out_for_a_while(client: TestClient) -> None:
    for _ in range(10):
        assert client.post(f"{BASE}/login", data={"username": "admin", "password": "nope"}).status_code == 401

    blocked = client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})

    assert blocked.status_code == 429 and "Retry-After" in blocked.headers, "even the right password waits"


def test_a_successful_sign_in_clears_the_count(client: TestClient) -> None:
    for _ in range(9):
        client.post(f"{BASE}/login", data={"username": "admin", "password": "nope"})
    assert client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD}).status_code == 303
    client.post(f"{BASE}/logout")
    for _ in range(9):
        client.post(f"{BASE}/login", data={"username": "admin", "password": "nope"})
    assert client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD}).status_code == 303


def test_the_window_slides() -> None:
    limiter = LoginLimiter(attempts=2, window=100)
    import app.hardening as h

    clock = [1000.0]
    original = h.time.monotonic
    h.time.monotonic = lambda: clock[0]
    try:
        limiter.failed("a"); limiter.failed("a")
        with pytest.raises(Exception):
            limiter.check("a")
        clock[0] += 101
        limiter.check("a")  # the old failures have aged out
        limiter.check("b")  # another address was never affected
    finally:
        h.time.monotonic = original


def test_the_media_server_form_counts_failures_too(client: TestClient, monkeypatch) -> None:
    """It relays every attempt to the Jellyfin server; without the limit Franchisarr would be a
    proxy for guessing someone's media-server password."""
    from app.clients.emby_client import EmbyAuthError
    from app.services import auth_service
    from tests.conftest import seed_server

    with Session(get_engine()) as session:
        seed_server(session, "jellyfin")

    def refuse(*a, **k):
        raise EmbyAuthError("no")

    monkeypatch.setattr(auth_service, "sign_in_with_media_server", refuse)
    for _ in range(10):
        assert client.post(f"{BASE}/auth/server/login", data={"username": "a", "password": "b"}).status_code == 401
    assert client.post(f"{BASE}/auth/server/login", data={"username": "a", "password": "b"}).status_code == 429


# ------------------------------------------------------------------ cross-site posts


def test_a_post_from_another_site_is_refused(client: TestClient) -> None:
    response = client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD},
                           headers={"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"})
    assert response.status_code == 403


def test_same_site_posts_and_headerless_clients_are_fine(client: TestClient) -> None:
    assert client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD},
                       headers={"Sec-Fetch-Site": "same-origin"}).status_code == 303
    client.post(f"{BASE}/logout")
    # A browser that sends only Origin (older), matching the host.
    assert client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD},
                       headers={"Origin": "http://testserver"}).status_code == 303
    client.post(f"{BASE}/logout")
    # No fetch metadata at all: curl, the CLI, an *arr. Judged by its own credentials.
    assert client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD}).status_code == 303


# ------------------------------------------------------------------ body size


def test_an_oversized_body_is_refused_before_it_is_read(client: TestClient) -> None:
    response = client.post(f"{BASE}/settings/import", headers={"Content-Length": str(50 * 1024 * 1024)})
    assert response.status_code == 413


# ------------------------------------------------------------------ headers


def test_every_page_carries_the_security_headers(client: TestClient) -> None:
    response = client.get(f"{BASE}/login")
    h = response.headers
    assert h["X-Frame-Options"] == "DENY" and h["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert "https://image.tmdb.org" in h["Content-Security-Policy"]
    assert "form-action 'self' https://app.plex.tv" in h["Content-Security-Policy"]


def test_the_theme_host_is_allowed_by_the_csp() -> None:
    csp = security_headers("https://theme-park.dev")["Content-Security-Policy"]
    assert "style-src" in csp and "https://theme-park.dev" in csp.split("style-src")[1].split(";")[0]
    assert "https://theme-park.dev" in csp.split("img-src")[1].split(";")[0]
