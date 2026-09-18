"""End-to-end auth: the login page, session cookies, protected routes, and Plex sign-in.

Runs everything under a subpath BASE_URL, because that is where auth breaks in practice --
cookie paths and redirect targets are exactly the things that get written root-relative.
"""

from __future__ import annotations

import pytest
import responses
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.auth.local_admin import create_local_admin
from app.auth.plex_oauth import PLEX_PINS_URL, PLEX_RESOURCES_URL, PLEX_USER_URL
from app.auth.sessions import COOKIE_NAME
from app.db import get_engine
from app.models import IncludedLibrary, MediaServer, User
from app.services.settings_service import SettingKey, set_setting
from tests.conftest import ensure_server

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"
OUR_SERVER = "abc123def456abc123def456abc123def456abc1"
OTHER_SERVER = "9999999999999999999999999999999999999999"


@pytest.fixture
def client(app_factory):
    """A signed-out client against an app with a local admin account available."""
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
        yield test_client


def _login(client: TestClient) -> None:
    response = client.post(
        f"{BASE}/login", data={"username": "admin", "password": PASSWORD}
    )
    assert response.status_code == 303


def _seed(**settings: str) -> None:
    with Session(get_engine()) as session:
        for key, value in settings.items():
            set_setting(session, key, value)
        session.commit()


def _known_plex_server() -> None:
    """A Plex row whose identity has been learned -- what Plex sign-in needs."""
    with Session(get_engine()) as session:
        server = session.get(MediaServer, ensure_server(session))
        server.machine_identifier = OUR_SERVER
        session.add(server); session.commit()


def _add_library(*, enabled: bool = True, key: str = "1") -> None:
    with Session(get_engine()) as session:
        session.add(
            IncludedLibrary(server_id=ensure_server(session), 
                library_key=key,
                library_name="Movies",
                library_type="movie",
                enabled=enabled,
            )
        )
        session.commit()


# ------------------------------------------------------------------ protecting routes


def test_anonymous_visitors_are_sent_to_the_login_page(client: TestClient) -> None:
    response = client.get(f"{BASE}/")

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"{BASE}/login")


def test_the_login_redirect_remembers_where_you_were_going(client: TestClient) -> None:
    response = client.get(f"{BASE}/libraries")

    assert f"next={BASE}/libraries" in response.headers["location"]


def test_health_stays_unauthenticated(client: TestClient) -> None:
    """Docker's HEALTHCHECK has no session; requiring one would fail every container."""
    assert client.get(f"{BASE}/health").status_code == 200


def test_static_files_stay_unauthenticated(client: TestClient) -> None:
    """The login page needs its own stylesheet before anyone is signed in."""
    assert client.get(f"{BASE}/static/pico.min.css").status_code == 200


# ------------------------------------------------------------------ local login


def test_login_succeeds_and_sets_a_session_cookie(client: TestClient) -> None:
    response = client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})

    assert response.status_code == 303
    assert COOKIE_NAME in response.cookies


def test_the_session_cookie_is_scoped_to_the_base_url(client: TestClient) -> None:
    """A cookie at / would be sent to every other app behind the same hostname."""
    response = client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})

    cookie_header = response.headers["set-cookie"]
    assert f"Path={BASE}/" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header.replace("samesite", "SameSite")


def test_logged_in_users_reach_the_app(client: TestClient) -> None:
    _add_library()
    _login(client)

    response = client.get(f"{BASE}/")

    assert response.status_code == 200
    assert "Franchisarr" in response.text


def test_wrong_password_is_rejected_without_a_session(client: TestClient) -> None:
    response = client.post(f"{BASE}/login", data={"username": "admin", "password": "nope"})

    assert response.status_code == 401
    assert COOKIE_NAME not in response.cookies
    assert "Incorrect username or password" in response.text


def test_the_error_does_not_reveal_whether_the_account_exists(client: TestClient) -> None:
    wrong_password = client.post(f"{BASE}/login", data={"username": "admin", "password": "no"})
    no_such_user = client.post(f"{BASE}/login", data={"username": "ghost", "password": "no"})

    assert "Incorrect username or password" in wrong_password.text
    assert "Incorrect username or password" in no_such_user.text


def test_logout_revokes_the_session(client: TestClient) -> None:
    _add_library()
    _login(client)
    assert client.get(f"{BASE}/").status_code == 200

    response = client.post(f"{BASE}/logout")
    assert response.status_code == 303

    assert client.get(f"{BASE}/").status_code == 303


def test_a_revoked_session_cookie_stops_working_even_if_replayed(client: TestClient) -> None:
    """Server-side revocation: keeping the cookie must not keep the session."""
    _add_library()
    _login(client)
    token = client.cookies[COOKIE_NAME]
    client.post(f"{BASE}/logout")

    client.cookies.set(COOKIE_NAME, token)
    assert client.get(f"{BASE}/").status_code == 303


# ------------------------------------------------------------------ open redirect


@pytest.mark.parametrize(
    "hostile",
    ["//evil.example.com", "https://evil.example.com", "/somewhere-else", "javascript:alert(1)"],
)
def test_login_will_not_redirect_off_site(client: TestClient, hostile: str) -> None:
    """An unchecked `next` turns our own login page into an open redirect."""
    response = client.post(
        f"{BASE}/login",
        data={"username": "admin", "password": PASSWORD, "next": hostile},
    )

    assert response.headers["location"] == f"{BASE}/"


def test_login_honours_an_in_app_next(client: TestClient) -> None:
    response = client.post(
        f"{BASE}/login",
        data={"username": "admin", "password": PASSWORD, "next": f"{BASE}/libraries"},
    )

    assert response.headers["location"] == f"{BASE}/libraries"


# ------------------------------------------------------------------ Plex sign-in


def test_plex_sign_in_is_unavailable_until_the_server_is_known(client: TestClient) -> None:
    """Without knowing which Plex server to check against, sign-in cannot be safe."""
    response = client.post(f"{BASE}/auth/plex/start")

    assert response.status_code == 409
    assert "isn't available" in response.json()["error"]


def test_the_login_page_hides_plex_sign_in_until_it_is_usable(client: TestClient) -> None:
    assert "Sign in with Plex" not in client.get(f"{BASE}/login").text

    _known_plex_server()
    assert "Sign in with Plex" in client.get(f"{BASE}/login").text


def test_the_popup_is_not_kept_in_alpine_reactive_state(client: TestClient) -> None:
    """Alpine makes component data reactive, and its proxy probes properties like __v_isRef on
    whatever it holds. The sign-in popup is same-origin (about:blank) when it is stored and
    cross-origin the moment it goes to plex.tv, so from then on *any* read of it -- including a
    bare `if (popup)` -- raised a SecurityError.

    That killed the poll loop after the sign-in had already succeeded server-side: the session
    existed, but the page never redirected and the button spun until the user reloaded by hand.
    Keeping the window in a closure instead of in the component keeps it un-proxied.
    """
    _known_plex_server()

    page = client.get(f"{BASE}/login").text
    component = page.split("return {", 1)[1].split("\n    };", 1)[0]

    assert "popup:" not in component, "the popup is a component property again"
    assert "this.popup" not in page, "the popup is being read through Alpine's proxy again"
    assert "let popup = null;" in page


def test_a_failure_while_polling_cannot_leave_the_button_spinning(client: TestClient) -> None:
    """poll() is deliberately not awaited, so without a catch any exception inside it becomes an
    unhandled rejection -- the spinner runs forever and the user is never told why."""
    _known_plex_server()

    page = client.get(f"{BASE}/login").text

    assert "this.poll().catch(" in page


def test_closing_the_popup_cannot_block_the_redirect(client: TestClient) -> None:
    """Closing it is a courtesy. If it throws -- and cross-origin windows can -- the sign-in must
    still complete."""
    _known_plex_server()

    page = client.get(f"{BASE}/login").text
    close_body = page.split("const closePopup", 1)[1].split("};", 1)[0]

    assert "try {" in close_body and "catch" in close_body


@responses.activate
def test_plex_start_returns_an_auth_url(client: TestClient) -> None:
    _known_plex_server()
    responses.add(responses.POST, PLEX_PINS_URL, json={"id": 77, "code": "WXYZ"})

    response = client.post(f"{BASE}/auth/plex/start")

    assert response.status_code == 200
    assert response.json()["auth_url"].startswith("https://app.plex.tv/auth#?")
    assert "code=WXYZ" in response.json()["auth_url"]


@responses.activate
def test_polling_reports_pending_until_the_user_signs_in(client: TestClient) -> None:
    _known_plex_server()
    responses.add(responses.POST, PLEX_PINS_URL, json={"id": 77, "code": "WXYZ"})
    responses.add(responses.GET, f"{PLEX_PINS_URL}/77", json={"id": 77, "authToken": None})

    client.post(f"{BASE}/auth/plex/start")
    response = client.post(f"{BASE}/auth/plex/poll")

    assert response.json() == {"status": "pending"}
    assert COOKIE_NAME not in response.cookies


@responses.activate
def test_a_plex_user_with_server_access_is_signed_in(client: TestClient) -> None:
    _add_library()
    _known_plex_server()
    responses.add(responses.POST, PLEX_PINS_URL, json={"id": 77, "code": "WXYZ"})
    responses.add(responses.GET, f"{PLEX_PINS_URL}/77", json={"id": 77, "authToken": "tok"})
    responses.add(
        responses.GET,
        PLEX_RESOURCES_URL,
        json=[{"clientIdentifier": OUR_SERVER, "provides": "server", "owned": True}],
    )
    responses.add(responses.GET, PLEX_USER_URL, json={"id": 5551234, "username": "michael"})

    client.post(f"{BASE}/auth/plex/start")
    response = client.post(f"{BASE}/auth/plex/poll")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert COOKIE_NAME in response.cookies

    with Session(get_engine()) as session:
        user = session.exec(select(User).where(col(User.external_user_id) == "5551234")).first()
    assert user is not None
    assert user.external_username == "michael"
    assert user.is_admin is True, "the server owner administers the install"


@responses.activate
def test_a_stranger_with_a_valid_plex_account_is_refused(client: TestClient) -> None:
    """The security property of technical challenge #2, enforced at the route."""
    _known_plex_server()
    responses.add(responses.POST, PLEX_PINS_URL, json={"id": 77, "code": "WXYZ"})
    responses.add(responses.GET, f"{PLEX_PINS_URL}/77", json={"id": 77, "authToken": "tok"})
    responses.add(
        responses.GET,
        PLEX_RESOURCES_URL,
        json=[{"clientIdentifier": OTHER_SERVER, "provides": "server", "owned": True}],
    )

    client.post(f"{BASE}/auth/plex/start")
    response = client.post(f"{BASE}/auth/plex/poll")

    assert response.status_code == 403
    assert COOKIE_NAME not in response.cookies

    with Session(get_engine()) as session:
        provisioned = session.exec(select(User).where(col(User.external_user_id).is_not(None))).all()
    assert provisioned == [], "a refused sign-in must not leave an account behind"


@responses.activate
def test_a_shared_user_is_signed_in_without_admin(client: TestClient) -> None:
    _add_library()
    _known_plex_server()
    responses.add(responses.POST, PLEX_PINS_URL, json={"id": 77, "code": "WXYZ"})
    responses.add(responses.GET, f"{PLEX_PINS_URL}/77", json={"id": 77, "authToken": "tok"})
    responses.add(
        responses.GET,
        PLEX_RESOURCES_URL,
        json=[{"clientIdentifier": OUR_SERVER, "provides": "server", "owned": False}],
    )
    responses.add(responses.GET, PLEX_USER_URL, json={"id": 999, "username": "housemate"})

    client.post(f"{BASE}/auth/plex/start")
    assert client.post(f"{BASE}/auth/plex/poll").json()["status"] == "ok"

    with Session(get_engine()) as session:
        user = session.exec(select(User).where(col(User.external_username) == "housemate")).first()
    assert user is not None
    assert user.is_admin is False


def test_polling_without_having_started_is_rejected(client: TestClient) -> None:
    _known_plex_server()

    response = client.post(f"{BASE}/auth/plex/poll")

    assert response.status_code == 400


# ------------------------------------------------------------------ library selection


def test_first_run_sends_you_to_pick_libraries(client: TestClient) -> None:
    """With nothing selected there is nothing for the app to show."""
    _login(client)

    response = client.get(f"{BASE}/")

    assert response.status_code == 303
    assert response.headers["location"] == f"{BASE}/libraries"


def test_saving_a_selection_completes_setup(client: TestClient) -> None:
    _add_library(enabled=False)
    _login(client)

    response = client.post(f"{BASE}/libraries", data={"keys": ["1"]})
    assert response.status_code == 303

    assert client.get(f"{BASE}/").status_code == 200


def test_the_library_page_requires_a_login(client: TestClient) -> None:
    assert client.get(f"{BASE}/libraries").status_code == 303
    assert client.post(f"{BASE}/libraries", data={"keys": ["1"]}).status_code == 303


def test_unticking_everything_returns_you_to_setup(client: TestClient) -> None:
    _add_library(enabled=True)
    _login(client)

    client.post(f"{BASE}/libraries", data={})

    assert client.get(f"{BASE}/").headers["location"] == f"{BASE}/libraries"
