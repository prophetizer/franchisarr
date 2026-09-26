"""Who besides an administrator may use the install, and what they may do.

"Can reach my Plex server" is a far wider group than "runs this house", so non-administrators
(people a Plex server is shared with, non-admin Jellyfin/Emby accounts) are refused unless an
admin turns on Settings → Who can sign in. Let in, they browse and hide titles for themselves;
everything that adds, scans or changes the household is admin-only, and hidden from them.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.api_keys import generate_api_key
from app.auth.dependencies import API_KEY_HEADER
from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import User
from app.services.settings_service import SettingKey, set_setting

BASE = "/franchisarr"


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        yield test_client


def _key_for(*, admin: bool) -> str:
    with Session(get_engine()) as session:
        user = User(external_user_id="admin-1" if admin else "member-1",
                    external_username="owner" if admin else "housemate", is_admin=admin)
        session.add(user)
        session.commit()
        session.refresh(user)
        return generate_api_key(session, user)


def _allow_members(on: bool) -> None:
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.ALLOW_MEMBER_SIGNIN, "true" if on else "false")
        session.commit()


# Everything that adds to an *arr, starts work, or changes what the whole household sees.
ADMIN_ONLY = [
    ("post", "/scan"), ("post", "/api/scan"),
    ("get", "/add/1"), ("post", "/add"), ("post", "/add/request"),
    ("post", "/api/radarr/add"), ("post", "/api/sonarr/add"),
    ("get", "/shows/add/1"), ("post", "/shows/add"), ("post", "/shows/add/request"),
    ("post", "/collections/1/exclude/2"), ("post", "/collections/rating-filter"),
    ("post", "/directors/floor"), ("get", "/preferences"), ("post", "/preferences"),
    ("post", "/shows/mappings"), ("post", "/shows/mappings/1/delete"), ("get", "/shows/1/candidates"),
    ("post", "/api/spinoffs/mappings"),
    ("get", "/settings"), ("post", "/settings/schedule"), ("post", "/settings/webhook"),
    ("post", "/settings/api-key"), ("post", "/settings/members"),
    ("get", "/libraries"), ("post", "/libraries"),
    ("get", "/instances"), ("get", "/media-servers"),
    ("get", "/api/instances/radarr"), ("get", "/api/instances/sonarr"),
    ("post", "/api/instances/radarr/refresh"),
]

MEMBER_PAGES = ["/", "/collections", "/franchises", "/directors", "/upcoming", "/shows", "/activity"]


def test_a_member_is_locked_out_while_members_are_off(client: TestClient) -> None:
    """The default. A member's existing key (or session) stops working, not only new sign-ins,
    so turning the switch off really does end their access -- import-list URLs included."""
    key = _key_for(admin=False)

    assert client.get(f"{BASE}/collections", headers={API_KEY_HEADER: key}).status_code == 303
    assert client.get(f"{BASE}/api/lists/collections.json?api_key={key}").status_code == 401

    _allow_members(True)
    assert client.get(f"{BASE}/collections", headers={API_KEY_HEADER: key}).status_code == 200

    _allow_members(False)
    assert client.get(f"{BASE}/collections", headers={API_KEY_HEADER: key}).status_code == 303


def test_an_admin_is_never_affected_by_the_switch(client: TestClient) -> None:
    key = _key_for(admin=True)
    for on in (False, True):
        _allow_members(on)
        assert client.get(f"{BASE}/settings", headers={API_KEY_HEADER: key}).status_code == 200


@pytest.mark.parametrize("method,path", ADMIN_ONLY)
def test_a_member_cannot_add_scan_or_change_the_household(client: TestClient, method: str, path: str) -> None:
    _allow_members(True)
    key = _key_for(admin=False)

    response = getattr(client, method)(f"{BASE}{path}", headers={API_KEY_HEADER: key})

    assert response.status_code == 403, f"{method.upper()} {path} answered {response.status_code}"


def test_a_member_can_browse_and_hide_for_themselves(client: TestClient) -> None:
    _allow_members(True)
    key = _key_for(admin=False)
    headers = {API_KEY_HEADER: key}

    for path in MEMBER_PAGES:
        assert client.get(f"{BASE}{path}", headers=headers).status_code == 200, path
    assert client.post(f"{BASE}/shows/dismiss/5", headers=headers).status_code == 200


def test_a_member_is_not_shown_controls_they_cannot_use(client: TestClient) -> None:
    """A button that answers 403 is a broken button. Members don't see the admin pages in the
    nav, or scan, search and mapping controls."""
    _allow_members(True)
    member = {API_KEY_HEADER: _key_for(admin=False)}

    home = client.get(f"{BASE}/", headers=member).text
    assert f'href="{BASE}/settings"' not in home and f'href="{BASE}/instances"' not in home
    assert f'href="{BASE}/libraries"' not in home and f'href="{BASE}/media-servers"' not in home
    assert f'hx-post="{BASE}/scan"' not in home

    shows = client.get(f"{BASE}/shows", headers=member).text
    assert "Search a single show" not in shows


def test_the_switch_is_on_the_settings_page_and_off_by_default(client: TestClient) -> None:
    with Session(get_engine()) as session:
        create_local_admin(session, "admin", "a-long-enough-password")
    client.post(f"{BASE}/login", data={"username": "admin", "password": "a-long-enough-password"})

    body = client.get(f"{BASE}/settings").text
    assert "Who can sign in" in body
    assert 'name="enabled" value="1" checked' not in body.split("Who can sign in")[1].split("</form>")[0]

    assert client.post(f"{BASE}/settings/members", data={"enabled": "1"}).status_code == 303
    with Session(get_engine()) as session:
        from app.services.auth_service import members_allowed

        assert members_allowed(session) is True
