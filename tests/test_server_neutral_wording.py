"""Pages that said "Plex" to everyone, Jellyfin and Emby users included."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.api_keys import generate_api_key
from app.auth.dependencies import API_KEY_HEADER
from app.db import get_engine
from app.models import User

BASE = "/franchisarr"


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        yield test_client


def _key_for(provider: str) -> str:
    with Session(get_engine()) as session:
        user = User(auth_provider=provider, external_user_id=f"{provider}-1",
                    external_username="michael", is_admin=True)
        session.add(user)
        session.commit()
        session.refresh(user)
        return generate_api_key(session, user)


@pytest.mark.parametrize("provider,label", [("jellyfin", "Jellyfin"), ("emby", "Emby"), ("plex", "Plex")])
def test_the_password_page_names_the_server_you_sign_in_with(client: TestClient, provider: str, label: str) -> None:
    headers = {API_KEY_HEADER: _key_for(provider)}

    page = " ".join(client.get(f"{BASE}/password", headers=headers).text.split())

    assert f"You sign in with {label}, so your password is kept by {label}" in page
    assert ("plex.tv" in page) == (provider == "plex"), "plex.tv only for Plex accounts"

    refused = client.post(f"{BASE}/password", headers=headers, data={
        "current_password": "x", "new_password": "y" * 10, "confirm_password": "y" * 10}).text
    assert f"signs in with {label}, so there" in refused
