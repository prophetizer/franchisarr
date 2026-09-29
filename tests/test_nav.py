"""The menu (0.40.0): Browse / Manage / your-name dropdowns, search at the far right, a ☰ panel
on a phone, the current page marked, and "/" for search."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.api_keys import generate_api_key
from app.auth.dependencies import API_KEY_HEADER
from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import IncludedLibrary, User
from app.services.settings_service import SettingKey, set_setting
from tests.conftest import seed_server

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            server = seed_server(session, "plex")
            session.add(IncludedLibrary(server_id=server.id, library_key="1", library_name="Movies",
                                        library_type="movie", enabled=True))
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def _menu(page: str, label: str) -> list[str]:
    """The link labels in the dropdown whose summary is `label`."""
    block = page.split(f"<summary>{label}</summary>", 1)[1].split("</details>", 1)[0]
    return re.findall(r">([^<>]+)</a>", block)


def test_an_admin_gets_browse_manage_and_their_own_menu(client: TestClient) -> None:
    page = client.get(f"{BASE}/collections").text

    assert _menu(page, "Browse") == ["Franchises", "Collections", "Spin-offs", "Upcoming", "Directors"]
    assert _menu(page, "Playlists") == ["Sync", "Add playlists", "Delete playlists", "History"]
    assert _menu(page, "Manage") == ["Servers", "Libraries", "Instances", "Users", "Settings", "Activity"]
    assert _menu(page, "admin") == ["Preferences", "Password"]
    assert "Sign out" in page and "theme-toggle" in page
    nav = page.split('<nav class="app-nav">', 1)[1].split("</nav>", 1)[0]
    assert nav.index("<summary>admin</summary>") < nav.index(f'href="{BASE}/search"'), "search at the far right"


def test_the_page_youre_on_is_marked_and_its_menu_highlighted(client: TestClient) -> None:
    page = client.get(f"{BASE}/collections").text

    assert f'<a href="{BASE}/collections" aria-current="page">Collections</a>' in page
    assert 'class="dropdown nav-here"' in page.split("<summary>Browse</summary>", 1)[0].rsplit("<details", 1)[1]
    assert 'class="dropdown nav-here"' not in page.split("<summary>Manage</summary>", 1)[0].rsplit("<details", 1)[1]


def test_a_member_has_no_manage_menu_and_finds_activity_under_their_name(client: TestClient) -> None:
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.ALLOW_MEMBER_SIGNIN, "true")
        member = User(external_user_id="m-1", external_username="housemate", is_admin=False)
        session.add(member); session.commit(); session.refresh(member)
        key = generate_api_key(session, member)
    client.cookies.clear()

    page = client.get(f"{BASE}/collections", headers={API_KEY_HEADER: key}).text

    assert "<summary>Manage</summary>" not in page
    assert _menu(page, "housemate") == ["Password", "Activity"]


def test_the_phone_panel_has_every_section_and_slash_goes_to_search(client: TestClient) -> None:
    page = client.get(f"{BASE}/collections").text

    panel = page.split('id="nav-panel"', 1)[1].split("</div>", 1)[0]
    for label in ("Franchises", "Servers", "Playlists", "Preferences", "Sign out"):
        assert label in panel
    assert 'aria-controls="nav-panel"' in page and "franchisarrToggleMenu" in page
    assert "event.key !== '/'" in page and f'"{BASE}/search"' in page


def test_the_sign_in_page_has_no_menu(client: TestClient) -> None:
    client.post(f"{BASE}/logout")
    client.cookies.clear()

    page = client.get(f"{BASE}/login").text

    assert "<summary>Browse</summary>" not in page and 'id="nav-panel"' not in page


def test_only_the_playlist_page_youre_on_is_marked(client: TestClient) -> None:
    """/playlists is the Sync page and the start of the other playlist pages' paths."""
    page = client.get(f"{BASE}/playlists/history").text
    block = page.split("<summary>Playlists</summary>", 1)[1].split("</details>", 1)[0]
    assert block.count('aria-current="page"') == 1 and f'href="{BASE}/playlists/history" aria-current' in block
