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
    assert ".spotlight, .timeline-ring, .sc-reel, .poster-wall, .end-credits { display: none; }" in classic
    assert "@view-transition { navigation: auto; }" in showcase
    reduce = showcase[showcase.index("@media (prefers-reduced-motion: reduce)"):]
    assert "@view-transition { navigation: none; }" in reduce, "no morphing for reduce motion"


def test_the_spotlight_shrinks_without_losing_what_made_it_work() -> None:
    """0.50.0's shrinking spotlight: each rule here was a bug in the browser before it was a rule."""
    import re
    from pathlib import Path

    showcase = (Path(__file__).resolve().parents[1] / "app" / "static" / "showcase.css").read_text()
    section = re.search(r'\[data-look="showcase"\] \.spotlight \{(.*?)\n\}', showcase, re.S).group(1)
    assert "display: block;" in section, "app.css hides it for Classic; Showcase has to show it again"
    assert "overflow: clip;" in section and "overflow: hidden" not in section, "hidden would stop the band sticking"
    band = re.search(r'\[data-look="showcase"\] \.spotlight-band \{(.*?)\n\}', showcase, re.S).group(1)
    assert "position: sticky;" in band
    backdrop = re.search(r'\[data-look="showcase"\] \.spotlight-backdrop \{(.*?)\n\}', showcase, re.S).group(1)
    assert "max-width: none;" in backdrop, "Pico caps an image at the band's width, short of the window's edges"
    # Phones and "reduce motion" get a shorter band that stays put.
    phones = showcase[showcase.index("@media (pointer: coarse), (max-width: 767px)"):]
    assert "--sc-full: 20rem" in phones
    assert "--sc-full: min(45vh, 26rem)" in showcase[showcase.index("@media (prefers-reduced-motion: reduce)"):]


def test_empty_slots_only_where_owned_films_sit_beside_them() -> None:
    """A search result or a list of nothing but missing films isn't a shelf with gaps in it."""
    from pathlib import Path

    showcase = (Path(__file__).resolve().parents[1] / "app" / "static" / "showcase.css").read_text()
    slots = [line for line in showcase.splitlines() if ".film-tile.missing" in line]
    assert slots and all("main:has(.collection-grid--owned)" in line for line in slots)
    # The poster box stretches to the card's height; a frame on it ran on below the picture (0.50.1).
    box = next(line for line in slots if line.rstrip().endswith(".collection-poster { align-self: start; position: relative; }"))
    assert box


def test_the_home_page_wraps_the_spotlight_in_its_band() -> None:
    from pathlib import Path

    template = (Path(__file__).resolve().parents[1] / "app" / "templates" / "index.html").read_text()
    start = template.index('<section class="spotlight"')
    assert template.index('<div class="spotlight-band">', start) < template.index('class="spotlight-slide', start)


def test_franchise_intros_are_showcase_only_and_each_persons_to_switch_off(client: TestClient) -> None:
    classic = client.get(f"{BASE}/collections").text
    assert "showcase-intros.js" not in classic and "Franchise intros" not in classic

    client.post(f"{BASE}/look", data={"look": "showcase", "back": f"{BASE}/collections"})
    page = client.get(f"{BASE}/collections").text
    assert "showcase-intros.js" in page and "Franchise intros: on" in page and 'data-intros="off"' not in page

    response = client.post(f"{BASE}/preferences/intros", data={"on": "false", "back": f"{BASE}/collections"})
    assert response.status_code == 303 and response.headers["location"] == f"{BASE}/collections"
    page = client.get(f"{BASE}/collections").text
    assert 'data-intros="off"' in page and "Franchise intros: off" in page
    assert client.post(f"{BASE}/preferences/intros", data={"on": "true", "back": "https://evil.example/"}).headers[
        "location"] == f"{BASE}/", "only ever back inside the app"


def test_every_franchise_pattern_has_an_intro_to_play() -> None:
    import re
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "app" / "static" / "showcase-intros.js").read_text()
    defined = set(re.findall(r"^    (\w+): function \(\) \{", js, re.M))
    wanted = set(re.findall(r"^    \[/.*/i, '(\w+)'\],$", js, re.M))
    assert len(wanted) == 128 and wanted <= defined, wanted - defined


def test_the_readme_lists_every_franchise_intro() -> None:
    """michael, 2026-10-01: the README keeps a list of the intros, updated whenever one is added.
    One table row per franchise the intros recognise, and every page name in the row recognised."""
    import re
    from pathlib import Path

    here = Path(__file__).resolve().parents[1]
    js = (here / "app" / "static" / "showcase-intros.js").read_text()
    patterns = [re.compile(p, re.I) for p in re.findall(r"^    \[/(.*)/i, '\w+'\],$", js, re.M)]
    readme = (here / "README.md").read_text()
    section = readme[readme.index("### Franchise intros"):]
    section = section[:section.index("\n## ")]
    rows = [line for line in section.splitlines() if line.startswith("| ") and not line.startswith("| Franchise")]
    assert len(rows) == len(patterns), f"{len(patterns)} intros, {len(rows)} README rows"
    for row in rows:
        names = re.findall(r"\*([^*]+)\*", row.split("|")[2])
        assert names, row
        for name in names:
            plain = name.rstrip("…")
            assert any(p.search(plain) for p in patterns), f"README names {plain!r}, which no intro recognises"


def test_cards_are_marked_on_every_page_not_only_pages_with_an_intro() -> None:
    """0.61.0: the 🎬 marks are placed from the same patterns the intros play by, and on list pages
    -- which have no banner -- so they must run before the script stops for want of one; and not
    at all for someone who switched intros off."""
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "app" / "static" / "showcase-intros.js").read_text()
    marks = js.index("markCards(document);")
    assert js.index("var WHICH = [") < marks < js.index("if (!heading) { return; }")
    assert "if (root.dataset.intros !== 'off') {" in js[marks - 200:marks]


def test_every_other_set_gets_a_genre_intro() -> None:
    """michael, 2026-10-03: "make intros for everything". A collection or franchise without its
    own intro plays its genre's -- one for every mood the server can set, and a plain one."""
    import re
    from pathlib import Path

    from app.services.about_service import MOODS

    js = (Path(__file__).resolve().parents[1] / "app" / "static" / "showcase-intros.js").read_text()
    block = js[js.index("var GENRE = {"):js.index("// A collection's or franchise's own intro if it has one")]
    genres = set(re.findall(r"^    (\w+): function \(\) \{", block, re.M))
    assert genres == {name for _, name in MOODS} | {"cinema"}
    assert "SET_PAGE.test(window.location.pathname) ? GENRE[GENRE[mood] ? mood : 'cinema']" in js, "sets only, not directors"
