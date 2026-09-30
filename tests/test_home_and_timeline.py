"""The release-order strip and the home page's poster rows (0.45.0)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import (
    Franchise, FranchiseMember, IncludedLibrary, LibraryItem, MatchSource, TmdbCollection, TmdbCollectionMovie,
    TmdbMovie,
)
from app.services import home_service, timeline
from tests.conftest import seed_server

BASE = "/franchisarr"
PASSWORD = "correct horse battery staple"


@dataclass
class Item:
    title: str
    tmdb_id: int
    year: int | None = None
    release_date: str | None = None
    poster: str | None = None
    item_type: str = "movie"


# ------------------------------------------------------------------ the strip


def test_the_strip_is_every_title_in_release_order_whatever_list_it_came_from() -> None:
    steps = timeline.build(owned=[Item("Empire", 2, 1980, "1980-05-21"), Item("The Mandalorian", 9, 2019, item_type="show")],
                           missing=[Item("Rogue One", 5, 2016, "2016-12-14"), Item("Undated", 7)],
                           upcoming=[Item("Mandalorian & Grogu", 8, 2026, "2026-05-22")])

    assert [(s.title, s.status) for s in steps] == [
        ("Empire", "owned"), ("Rogue One", "missing"), ("The Mandalorian", "owned"),
        ("Mandalorian & Grogu", "upcoming"), ("Undated", "missing")]
    assert steps[2].item_type == "show", "a missing show would open Sonarr's dialog"


# ------------------------------------------------------------------ home rows


@dataclass
class Gap:
    name: str
    collection_id: int
    owned: tuple
    missing: tuple
    small_poster: str | None = None


def test_closest_to_complete_puts_the_smallest_share_missing_first() -> None:
    gaps = [Gap("Half", 1, (1, 2), (3, 4)), Gap("Nearly", 2, (1, 2, 3, 4), (5,)), Gap("Done", 3, (1,), ())]

    cards = home_service.closest_to_complete(gaps)

    assert [c.title for c in cards] == ["Nearly", "Half"], "a complete one isn't a gap"
    assert cards[0].detail == "1 missing · 4 of 5" and cards[0].path == "/collections/2"


@dataclass
class Spot(Gap):
    backdrop: str | None = None
    logo_image: str | None = None
    poster: str | None = None


def test_the_spotlight_is_the_nearly_done_ones_that_have_a_backdrop() -> None:
    gaps = [Spot("Half", 1, (1, 2), (3, 4), backdrop="/h.jpg"), Spot("Nearly", 2, (1, 2, 3, 4), (5,), backdrop="/n.jpg"),
            Spot("No picture", 3, (1, 2, 3, 4, 5), (6,)), Spot("Done", 4, (1,), (), backdrop="/d.jpg")]

    slides = home_service.spotlight(gaps)

    assert [s.title for s in slides] == ["Nearly", "Half"], "a backdrop to fill the screen, and a gap"

    assert slides[0].detail == "You have 4 of 5 — one film away" and slides[1].detail == "You have 2 of 4 — 2 to go"


def test_the_spotlight_leads_with_the_best_known_sets_a_film_or_two_from_done() -> None:
    @dataclass
    class Film:
        vote_count: int

    gaps = [Spot("Frosty", 1, (Film(40), Film(30)), (Film(20),), backdrop="/f.jpg"),
            Spot("Star Trek", 2, (Film(9000),), (Film(8000), Film(7000)), backdrop="/s.jpg"),
            Spot("Far off but famous", 3, (Film(99999),), (Film(1), Film(1), Film(1)), backdrop="/x.jpg")]

    assert [s.title for s in home_service.spotlight(gaps)] == ["Star Trek", "Frosty", "Far off but famous"], \
        "two to go still counts; three waits behind"


@dataclass
class Upcoming:
    title: str
    release_date: str
    collection_id: int = 1
    poster: str | None = None

    def days_until(self, today: date) -> int:
        return (date.fromisoformat(self.release_date) - today).days


def test_coming_soon_is_the_next_ninety_days_soonest_first() -> None:
    today = date(2026, 9, 29)
    films = [Upcoming("Later", "2027-06-01"), Upcoming("Soon", "2026-10-09"), Upcoming("Tomorrow", "2026-09-30"),
             Upcoming("Gone", "2026-09-01")]

    cards = home_service.coming_soon(films, today)

    assert [(c.title, c.detail) for c in cards] == [("Tomorrow", "2026-09-30 · tomorrow"),
                                                   ("Soon", "2026-10-09 · in 10 days")]


def _film(session: Session, server: int, tmdb_id: int, title: str, first_seen: datetime | None) -> None:
    row = LibraryItem(server_id=server, library_key="1", item_key=f"k{tmdb_id}", item_type="movie", title=title,
                      tmdb_id=tmdb_id, match_source=MatchSource.GUID.value)
    row.first_seen_at = first_seen
    session.add(row)
    if first_seen is None:
        # A row from before 0.45 is undated; an INSERT would date it (the column's default), so
        # take the date away with an UPDATE, as the migration left the old ones.
        session.flush()
        row.first_seen_at = None
        session.add(row)


def test_just_added_is_new_titles_from_sets_being_collected(session: Session) -> None:
    server = seed_server(session).id
    now = datetime.now(timezone.utc)
    _film(session, server, 1, "From before 0.45", None)                    # no date: never "new"
    _film(session, server, 2, "Aliens", now - timedelta(days=2))
    _film(session, server, 3, "Some one-off", now - timedelta(hours=1))    # belongs to no set
    _film(session, server, 4, "Alien³", now - timedelta(hours=3))
    session.add(TmdbCollection(tmdb_collection_id=8091, name="Alien Collection"))
    for tmdb_id, title in ((1, "Alien"), (2, "Aliens"), (4, "Alien³")):
        session.add(TmdbCollectionMovie(collection_id=8091, tmdb_movie_id=tmdb_id, title=title, poster_path=f"/{tmdb_id}.jpg"))
    session.commit()

    cards = home_service.just_added(session)

    assert [(c.title, c.detail, c.path) for c in cards] == [("Alien³", "today", "/collections/8091"),
                                                           ("Aliens", "2 days ago", "/collections/8091")]
    assert cards[0].poster.endswith("/4.jpg")


def test_a_fresh_installs_first_scan_is_not_just_added(session: Session) -> None:
    server = seed_server(session).id
    start = datetime.now(timezone.utc) - timedelta(days=5)
    session.add(TmdbCollection(tmdb_collection_id=8091, name="Alien Collection"))
    for tmdb_id, when in ((1, start), (2, start + timedelta(minutes=10)), (4, start + timedelta(days=3))):
        _film(session, server, tmdb_id, f"film {tmdb_id}", when)
        session.add(TmdbCollectionMovie(collection_id=8091, tmdb_movie_id=tmdb_id, title=f"film {tmdb_id}"))
    session.commit()

    assert [c.title for c in home_service.just_added(session)] == ["film 4"]


# ------------------------------------------------------------------ the pages


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            server = seed_server(session).id
            session.add(IncludedLibrary(server_id=server, library_key="1", library_name="Films", library_type="movie",
                                        enabled=True))
            session.add(TmdbCollection(tmdb_collection_id=8091, name="Alien Collection", poster_path="/c.jpg"))
            for pos, (tmdb_id, title, released) in enumerate(((348, "Alien", "1979-05-25"), (679, "Aliens", "1986-07-18"),
                                                              (8077, "Alien³", "1992-05-22"))):
                session.add(TmdbCollectionMovie(collection_id=8091, tmdb_movie_id=tmdb_id, title=title,
                                                release_date=released, release_year=int(released[:4]), position=pos,
                                                poster_path=f"/{tmdb_id}.jpg"))
                session.add(TmdbMovie(tmdb_id=tmdb_id, title=title, collection_id=8091))
            for tmdb_id, title in ((348, "Alien"), (679, "Aliens")):
                _film(session, server, tmdb_id, title, None)
            session.add(Franchise(wikidata_id="Q16", name="Alien franchise"))
            session.add(FranchiseMember(franchise_id="Q16", item_type="movie", tmdb_id=348, title="Alien", year=1979))
            session.add(FranchiseMember(franchise_id="Q16", item_type="movie", tmdb_id=8077, title="Alien³", year=1992))
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def test_the_collection_page_has_the_strip_with_add_on_the_missing_one(client: TestClient) -> None:
    page = client.get(f"{BASE}/collections/8091").text

    strip = page.split('<ol class="timeline-strip">', 1)[1].split("</ol>", 1)[0]
    assert strip.index("Alien (1979)") < strip.index("Aliens (1986)") < strip.index("Alien³ (1992)")
    assert "timeline-step--missing" in strip and f'hx-get="{BASE}/add/8077"' in strip
    assert "2 of 3" in page.split('class="timeline-heading"', 1)[1][:1200]
    assert page.index('class="timeline"') < page.index("<h2>Missing"), "above the grids"


def test_the_strips_count_matches_the_banner_with_whats_coming_apart(client: TestClient) -> None:
    with Session(get_engine()) as session:
        session.add(TmdbCollectionMovie(collection_id=8091, tmdb_movie_id=999, title="Alien: Next",
                                        release_date="2099-01-01", release_year=2099, position=9))
        session.commit()

    page = client.get(f"{BASE}/collections/8091").text

    assert "2 of 3, 1 coming" in page.split('class="timeline-heading"', 1)[1][:1200]


def test_the_strip_carries_its_ring_and_play_order_for_showcase(client: TestClient) -> None:
    page = client.get(f"{BASE}/collections/8091").text

    assert 'class="timeline-ring"' in page and "--sc-pct: 66.7" in page, "2 of 3"
    assert 'style="--i: 0"' in page and 'style="--i: 2"' in page


def test_the_home_page_carries_the_spotlight_hidden_unless_showcase(client: TestClient) -> None:
    with Session(get_engine()) as session:
        collection = session.get(TmdbCollection, 8091)
        collection.backdrop_path = "/back.jpg"
        session.add(collection); session.commit()

    page = client.get(f"{BASE}/").text

    assert 'class="spotlight"' in page and "You have 2 of 3 — one film away" in page
    assert 'loading="lazy"' in page.split('class="spotlight"', 1)[1][:600], "Classic never fetches it"


def test_the_franchise_page_has_the_strip_too(client: TestClient) -> None:
    page = client.get(f"{BASE}/franchises/Q16").text

    assert '<ol class="timeline-strip">' in page and f'hx-get="{BASE}/add/8077"' in page


def test_the_home_page_leads_with_the_rows_it_has(client: TestClient) -> None:
    page = client.get(f"{BASE}/").text

    assert "Closest to complete" in page and "1 missing · 2 of 3" in page
    assert page.index("Closest to complete") < page.index("home-grid"), "rows first, counts below"
    assert "Just added" not in page, "an empty row isn't shown"
