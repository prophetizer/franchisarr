"""The Showcase look (0.47.0): per person, off by default, and nothing but extra CSS and JS."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.api_keys import generate_api_key
from app.auth.dependencies import API_KEY_HEADER
from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import IncludedLibrary, User
from app.services import look
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
            server = seed_server(session)
            session.add(IncludedLibrary(server_id=server.id, library_key="1", library_name="Films",
                                        library_type="movie", enabled=True))
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def test_classic_is_the_default_and_loads_nothing_extra(client: TestClient) -> None:
    page = client.get(f"{BASE}/collections").text

    assert "data-look" not in page and "showcase.css" not in page and "showcase.js" not in page
    assert "✦ Showcase look" in page, "offered under your name, and in the phone menu"
    assert page.count('action="' + BASE + '/look"') == 2


def test_choosing_showcase_follows_the_person_and_comes_back_to_the_page(client: TestClient) -> None:
    response = client.post(f"{BASE}/look", data={"look": "showcase", "back": f"{BASE}/collections"})

    assert response.status_code == 303 and response.headers["location"] == f"{BASE}/collections"
    page = client.get(f"{BASE}/collections").text
    assert 'data-look="showcase"' in page and "/static/showcase.css" in page and "/static/showcase.js" in page
    assert "◻ Classic look" in page

    client.post(f"{BASE}/look", data={"look": "classic", "back": f"{BASE}/"})
    assert "data-look" not in client.get(f"{BASE}/collections").text


@pytest.mark.parametrize("back", ["https://evil.example/", "//evil.example/x", "/elsewhere", ""])
def test_it_only_ever_goes_back_inside_the_app(client: TestClient, back: str) -> None:
    response = client.post(f"{BASE}/look", data={"look": "showcase", "back": back})

    assert response.headers["location"] == f"{BASE}/"


def test_a_member_can_choose_their_own_look_and_it_is_theirs_alone(client: TestClient) -> None:
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.ALLOW_MEMBER_SIGNIN, "true")
        member = User(external_user_id="m-1", external_username="housemate", is_admin=False)
        session.add(member); session.commit(); session.refresh(member)
        key = generate_api_key(session, member)
        member_id = member.id
    client.cookies.clear()

    assert client.post(f"{BASE}/look", data={"look": "showcase"}, headers={API_KEY_HEADER: key}).status_code == 303

    with Session(get_engine()) as session:
        assert look.get(session, member_id) == "showcase"
        admin = session.exec(select(User).where(User.local_username == "admin")).one()
        assert look.get(session, admin.id) == "classic"


def test_unknown_values_are_classic(session: Session) -> None:
    user = User(local_username="u", is_admin=True)
    session.add(user); session.commit(); session.refresh(user)

    assert look.set_look(session, user.id, "disco") == "classic" and look.get(session, user.id) == "classic"


def test_showcase_hides_its_pieces_from_classic_and_opts_into_page_transitions() -> None:
    from pathlib import Path

    static = Path(__file__).resolve().parents[1] / "app" / "static"
    classic, showcase = (static / "app.css").read_text(), (static / "showcase.css").read_text()
    assert ".spotlight, .timeline-ring { display: none; }" in classic
    assert "@view-transition { navigation: auto; }" in showcase
    reduce = showcase[showcase.index("@media (prefers-reduced-motion: reduce)"):]
    assert "@view-transition { navigation: none; }" in reduce, "no morphing for reduce motion"
