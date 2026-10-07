"""0.72.0, second batch: quality badges, the start-here ribbon, list cards' dot strip, franchise
chips, On this day, Almost on the shelf, the share card and the keyboard shortcut sheet."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import responses
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.clients.media_server import best_resolution, resolution_from_width
from app.db import get_engine
from app.models import Franchise, FranchiseMember, LibraryItem
from app.services import franchise_service, home_service, runtimes
from app.templating import get_templates
from tests.test_movie_ui import BASE, COLLECTION, _seed_collection, client  # noqa: F401 - fixture
from tests.test_plex_client import _register_section, client as plex, mocked_plex, plex_fixtures  # noqa: F401

HERE = Path(__file__).resolve().parents[1]
STATIC = HERE / "app" / "static"


def _render(source: str, **context) -> str:
    return get_templates().env.from_string(source).render(**context)


# ------------------------------------------------------------------ quality


def test_resolution_by_width_and_the_best_of_several() -> None:
    assert [resolution_from_width(w) for w in (3840, 1920, 1280, 720, 0, None, "x")] == \
        ["4K", "1080p", "720p", "SD", None, None, None]
    assert best_resolution("720p", None, "1080p") == "1080p" and best_resolution(None, "junk") is None


def test_plex_reads_the_best_copy_from_the_listing(mocked_plex, plex_fixtures, plex) -> None:  # noqa: F811
    _register_section(mocked_plex, plex_fixtures, 1, "section_1_movies.xml")
    films = plex.list_movies("1")
    assert [m.resolution for m in films] == ["4K", "1080p", None]
    assert not [c for c in mocked_plex.calls if "/library/metadata/" in c.request.url], "no request per film"


def test_an_owned_poster_carries_its_badge_and_a_ribbon() -> None:
    tile = _render('{% from "partials/tile.html" import tile %}{% call tile("/p.jpg", "owned", badge="4K", ribbon="Next") %}x{% endcall %}')
    assert 'class="collection-poster has-marks"' in tile and '<span class="poster-ribbon">Next</span>' in tile
    assert 'class="quality-badge quality-badge--4k" title="Your best copy: 4K">4K</span>' in tile
    assert "has-marks" not in _render('{% from "partials/tile.html" import tile %}{% call tile("/p.jpg", "owned") %}x{% endcall %}')


def test_the_owned_tiles_on_every_detail_page_pass_their_marks() -> None:
    for name in ("collection_detail.html", "franchise_detail.html", "director_detail.html"):
        page = (HERE / "app" / "templates" / name).read_text()
        assert "next_to_watch(" in page and "ribbon=(nxt[1] if nxt and nxt[0] ==" in page and "badge=" in page, name


# ------------------------------------------------------------------ start here


@dataclass
class _Film:
    tmdb_id: int
    title: str
    release_date: str | None = None
    watched: bool | None = None


def test_next_is_the_first_unwatched_in_release_order() -> None:
    films = [_Film(3, "III", "1994-01-01", False), _Film(1, "I", "1984-01-01", True), _Film(2, "II", "1987-01-01", False)]
    assert runtimes.next_to_watch(films) == (2, "Next")
    fresh = [_Film(3, "III", "1994-01-01", False), _Film(1, "I", "1984-01-01", False)]
    assert runtimes.next_to_watch(fresh) == (1, "Start here")
    assert runtimes.next_to_watch([_Film(1, "I", watched=True)]) is None, "all watched"
    assert runtimes.next_to_watch([_Film(1, "I")]) is None, "nobody says"


# ------------------------------------------------------------------ dot strip


def test_a_list_card_shows_its_set_as_dots() -> None:
    @dataclass
    class T:
        title: str
        tmdb_id: int
        year: int
        poster: str | None = None

    src = '{% from "partials/dot_strip.html" import dot_strip %}{{ dot_strip(o, m, u) }}'
    html = _render(src, o=[T("A", 1, 1990)], m=[T("B", 2, 1985)], u=[T("C", 3, 2030)])
    assert html.index('dot--missing" title="B (1985)"') < html.index('dot--owned" title="A (1990)"') < html.index("dot--upcoming")
    assert "dot-more" in _render(src, o=[T(str(n), n, 2000 + n) for n in range(45)], m=[], u=[])
    for name in ("collections.html", "franchises.html"):
        assert "dot_strip(" in (HERE / "app" / "templates" / name).read_text(), name


# ------------------------------------------------------------------ franchise chips


def test_a_collection_page_says_which_franchises_it_is_part_of(client: TestClient) -> None:  # noqa: F811
    _seed_collection()
    with Session(get_engine()) as session:
        session.add(Franchise(wikidata_id="Q1", name="Beverly Hills Cop"))
        session.add(FranchiseMember(franchise_id="Q1", item_type="movie", tmdb_id=90, title="Beverly Hills Cop"))
        session.add(FranchiseMember(franchise_id="Q1", item_type="movie", tmdb_id=96, title="Beverly Hills Cop II"))
        session.commit()
        assert franchise_service.for_collection(session, COLLECTION) == [("Q1", "Beverly Hills Cop")]
    page = client.get(f"{BASE}/collections/{COLLECTION}").text
    assert f'<span>Part of</span><a href="{BASE}/franchises/Q1">Beverly Hills Cop →</a>' in page
    franchise = client.get(f"{BASE}/franchises/Q1").text
    assert f'<span>Collections in it</span><a href="{BASE}/collections/{COLLECTION}">Beverly Hills Cop Collection</a>' in franchise


# ------------------------------------------------------------------ on this day


def test_on_this_day_is_owned_films_released_today_in_past_years(client: TestClient) -> None:  # noqa: F811
    _seed_collection()   # owns Beverly Hills Cop, released 1984-12-05
    with Session(get_engine()) as session:
        cards = home_service.on_this_day(session, date(2026, 12, 5))
        assert [(c.title, c.detail, c.path) for c in cards] == \
            [("Beverly Hills Cop", "1984 · 42 years ago today", f"/collections/{COLLECTION}")]
        assert home_service.on_this_day(session, date(2026, 12, 6)) == []
        assert home_service.on_this_day(session, date(1984, 12, 5)) == [], "not the day it came out"


# ------------------------------------------------------------------ almost on the shelf


def test_the_trophy_case_lists_sets_a_few_titles_short() -> None:
    from app.services import trophies

    a = trophies.Almost("collection", "Cop", "/collections/1", None, 2, 3, ("Cop III",))
    assert a.to_go == 1
    page = (HERE / "app" / "templates" / "trophies.html").read_text()
    assert "Almost on the shelf" in page and "{{ a.left | join(', ') }}" in page
    src = (HERE / "app" / "services" / "trophies.py").read_text()
    assert "franchise_service._same_name(f.name, name) for name in listed" in src, "one set, listed once"


# ------------------------------------------------------------------ share and keys


def test_the_share_card_is_drawn_in_the_browser_from_the_strip() -> None:
    js = (STATIC / "share.js").read_text()
    assert "document.querySelectorAll('.timeline-step')" in js and "img.crossOrigin = 'anonymous';" in js
    assert "'/t/p/w154/'" in js, "a size the page loads only for reading"
    assert "navigator.canShare" in js and "link.download = png.name;" in js and "fetch(" not in js, "nothing uploaded"
    strip = (HERE / "app" / "templates" / "partials" / "timeline.html").read_text()
    assert 'data-share-set data-summary="{{ have }} of {{ released }}" hidden' in strip


def test_shortcuts_jump_inside_the_app_and_skip_typing() -> None:
    js = (STATIC / "keys.js").read_text()
    assert ".replace(/\\/+$/, '')" in js, "no //collections"
    assert "typing(e.target)" in js and "e.ctrlKey || e.metaKey || e.altKey" in js
    assert "['c', '/collections', 'Collections']" in js and "e.key === '?'" in js


def test_both_scripts_load_for_anyone_signed_in(client: TestClient) -> None:  # noqa: F811
    page = client.get(f"{BASE}/collections").text
    assert "/static/keys.js?v=" in page and f'data-base="{BASE}/"' in page and "/static/share.js?v=" in page
