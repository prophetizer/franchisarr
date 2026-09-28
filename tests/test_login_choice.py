"""The sign-in page's "Sign in with" dropdown: one entry per way in, only that form shown."""

from __future__ import annotations

import re

import pytest
import responses
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.local_admin import create_local_admin
from app.db import get_engine
from tests.conftest import seed_server

BASE = "/franchisarr"
JF = "http://jellyfin.test:8096"


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        yield test_client


def _servers(*kinds: str, local: bool = True) -> dict[str, int]:
    ids = {}
    with Session(get_engine()) as session:
        for kind in kinds:
            extra = {"machine_identifier": "known"} if kind == "plex" else {}
            ids[kind] = seed_server(session, kind, url=JF if kind == "jellyfin" else None, **extra).id
        if local:
            create_local_admin(session, "admin", "a-long-passphrase")
    return ids


def _options(page: str) -> list[str]:
    select = page.split('<select name="method"', 1)[1].split("</select>", 1)[0]
    return [label.strip() for label in re.findall(r"<option[^>]*>([^<]+)</option>", select)]


def test_every_way_in_is_one_entry_by_name_with_the_local_account_last(client: TestClient) -> None:
    _servers("plex", "jellyfin", "emby")

    page = client.get(f"{BASE}/login").text

    assert _options(page) == ["Emby", "Jellyfin", "Plex", "Local account"]
    assert page.count('x-show="method ===') == 4, "one form per entry, only the chosen one shown"
    # The component's arguments are JSON, full of double quotes: inside a double-quoted attribute
    # they ended it early, Alpine never started, and every form showed at once.
    component = re.search(r"x-data=(.)signInChoice\((.*?)\)\1", page)
    assert component and component.group(1) == "'", "x-data must be single-quoted"
    assert '"' not in page.split('x-show="method ===', 1)[1].split('"', 1)[0].replace("'", "")


def test_a_server_named_other_than_its_kind_says_both(client: TestClient) -> None:
    with Session(get_engine()) as session:
        seed_server(session, "jellyfin", name="Attic")
    _servers(local=True)

    assert _options(client.get(f"{BASE}/login").text) == ["Jellyfin (Attic)", "Local account"]


def test_one_way_in_needs_no_dropdown(client: TestClient) -> None:
    _servers(local=True)

    page = client.get(f"{BASE}/login").text

    assert '<select name="method"' not in page and 'action="/franchisarr/login"' in page


@responses.activate
def test_a_failed_sign_in_comes_back_on_the_method_that_failed(client: TestClient) -> None:
    """Not the one this browser last chose: the error belongs to the form that was used."""
    ids = _servers("jellyfin", "emby")
    responses.add(responses.POST, f"{JF}/Users/AuthenticateByName", status=401)

    page = client.post(f"{BASE}/auth/server/login",
                       data={"username": "alice", "password": "wrong", "server_id": ids["jellyfin"]}).text

    assert "Incorrect username or password" in page
    assert f'signInChoice(["server-{ids["emby"]}", "server-{ids["jellyfin"]}", "local"], "server-{ids["jellyfin"]}", true)' in page

    page = client.post(f"{BASE}/login", data={"username": "admin", "password": "wrong"}).text
    assert '"local", true)' in page
