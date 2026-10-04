"""0.71.0: the effects dial, blur-up posters, the Upcoming calendar, director banners and career
strips, the seat map, poster-colour accents and decade headings -- the server's side of each, and
the hooks the scripts depend on. The motion itself was checked in a browser."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import get_engine
from app.services import look, timeline, upcoming_calendar
from app.services.sorting import decades
from tests.test_directors import NOLAN, _film, _floor, _own
from tests.test_directors import client as directors_client  # noqa: F401 - fixture
from tests.test_upcoming import _seed_page
from tests.test_upcoming import client  # noqa: F401 - fixture

HERE = Path(__file__).resolve().parents[1]
BASE = "/franchisarr"
STATIC = HERE / "app" / "static"


# ------------------------------------------------------------------ effects dial


def test_the_dial_goes_round_and_refuses_what_it_doesnt_know() -> None:
    assert [look.next_effects(v) for v in ("full", "calm", "off", "nonsense")] == ["calm", "off", "full", "calm"]


def test_calm_and_off_reach_the_page_and_only_in_showcase(client: TestClient) -> None:  # noqa: F811
    page = client.get(f"{BASE}/upcoming").text
    assert "data-effects" not in page, "Classic has no dial"

    client.post(f"{BASE}/look", data={"look": "showcase"})
    page = client.get(f"{BASE}/upcoming").text
    assert "data-effects" not in page and "✨ Effects: full" in page, "full is the default and needs no mark"
    assert 'name="value" value="calm"' in page

    assert client.post(f"{BASE}/preferences/effects", data={"value": "calm", "back": f"{BASE}/upcoming"}).headers[
        "location"] == f"{BASE}/upcoming"
    page = client.get(f"{BASE}/upcoming").text
    assert 'data-effects="calm"' in page and "✨ Effects: calm" in page and 'name="value" value="off"' in page

    client.post(f"{BASE}/preferences/effects", data={"value": "sideways", "back": "https://example.com/"})
    assert "data-effects" not in client.get(f"{BASE}/upcoming").text, "an unknown value is full"


def test_off_is_reduce_motion_to_every_script_and_calm_stops_the_loops() -> None:
    for name in ("showcase.js", "showcase-cinema.js", "showcase-intros.js"):
        assert "document.documentElement.dataset.effects === 'off'" in (STATIC / name).read_text(), name
    css = (STATIC / "showcase.css").read_text()
    assert '[data-look="showcase"][data-effects="off"] *,' in css
    assert '[data-look="showcase"][data-effects="calm"] :is(.poster-wall-row' in css
    assert "progress.completeness::-webkit-progress-value { animation: none !important; }" in css
    assert "#scan-status" not in css[css.index("effects dial (0.71.0)"):css.index("@media (prefers-reduced-motion")], \
        "a scan's progress keeps moving in calm"


# ------------------------------------------------------------------ blur-up, seats, accents


def test_the_scripts_carry_the_blur_up_the_seats_and_the_accents() -> None:
    js = (STATIC / "showcase.js").read_text()
    cinema = (STATIC / "showcase-cinema.js").read_text()
    css = (STATIC / "showcase.css").read_text()
    assert "img.dataset.scLqip = src.replace(TMDB_SIZE" in js and "img.sc-pending.sc-lqip" in css
    assert "'/t/p/' + (wide ? 'w300' : small)" in js, "the glow never samples the placeholder's w92"
    assert "root.classList.add('sc-accented');" in js and "--pico-primary: var(--sc-accent-d);" in css
    assert 'html[data-look="showcase"][data-theme="light"].sc-accented' in css
    assert "make('div', 'sc-seats')" in cinema and ".sc-seat--owned {" in css


def test_a_person_photo_blurs_up_from_a_person_size() -> None:
    assert '<img class="person-photo" src="{{ d.photo }}"' in (HERE / "app" / "templates" / "directors.html").read_text()
    assert "img.classList.contains('person-photo') ? '$1w45/' : '$1w92/'" in (STATIC / "showcase.js").read_text()


# ------------------------------------------------------------------ decades


@dataclass
class _T:
    title: str
    year: int | None


def test_decade_headings_need_a_long_list_by_release_across_decades() -> None:
    films = [_T(f"F{n}", y) for n, y in enumerate([1985, 1989, 1991, 1994, 1999, 2003, 2008, None])]
    labels = [label for label, _ in decades(films, ("release", "asc"))]
    assert labels == ["1980s", None, "1990s", None, None, "2000s", None, "No date yet"]
    assert all(label is None for label, _ in decades(films, ("rating", "desc"))), "only by release"
    assert all(label is None for label, _ in decades(films[:5], None)), "short lists need no help"
    same = [_T(str(n), 2010 + n) for n in range(9)]
    assert all(label is None for label, _ in decades(same, "release")), "one decade has nothing to divide"


def test_the_strip_marks_where_decades_start() -> None:
    steps = [timeline.Step(str(y), y, None, "owned", y, "movie") for y in (1998, 1999, 2002, 2004)]
    assert timeline.decade_marks(steps) == {0: "1990s", 2: "2000s"}
    assert timeline.decade_marks(steps[:2]) == {}


def test_every_sorted_detail_grid_can_take_decade_headings() -> None:
    for name in ("collection_detail.html", "franchise_detail.html", "director_detail.html", "partials/missing_list.html"):
        page = (HERE / "app" / "templates" / name).read_text()
        assert "in sort_titles(" not in page and 'class="decade-divider"' in page, name


# ------------------------------------------------------------------ directors


def test_a_director_page_has_their_photo_behind_it_and_their_career_as_a_strip(directors_client: TestClient) -> None:  # noqa: F811
    with Session(get_engine()) as session:
        _floor(session, 2)
        _own(session, 155, "The Dark Knight"); _own(session, 27205, "Inception")
        _film(session, 155, "The Dark Knight", "2008-07-16")
        _film(session, 27205, "Inception", "2010-07-15")
        _film(session, 320, "Insomnia", "2002-05-24")
        from app.models import MovieDirector
        for row in session.exec(select(MovieDirector)):
            row.profile_path = "/nolan.jpg"; session.add(row)
        session.commit()

    page = directors_client.get(f"{BASE}/directors/{NOLAN}").text
    assert 'class="collection-heading collection-heading--person has-backdrop"' in page
    assert '<img class="collection-backdrop" src="https://image.tmdb.org/t/p/h632/nolan.jpg"' in page
    strip = page[page.index('class="timeline"'):]
    assert strip.index("Insomnia") < strip.index("The Dark Knight") < strip.index("Inception")
    assert 'data-decade="2000s"' in strip and 'data-decade="2010s"' in strip


# ------------------------------------------------------------------ upcoming calendar


@dataclass
class _F:
    title: str
    release: date | None


def test_a_month_is_monday_first_weeks_with_the_films_on_their_days() -> None:
    films = [_F("A", date(2026, 10, 3)), _F("B", date(2026, 10, 3)), _F("C", date(2027, 1, 31)), _F("D", None)]
    months = upcoming_calendar.months(films, today=date(2026, 10, 3))

    assert [m.label for m in months] == ["October 2026", "January 2027"], "only months with a release"
    october = months[0]
    assert october.weeks[0][:3] == [None, None, None], "1 October 2026 is a Thursday"
    saturday = october.weeks[0][5]
    assert saturday.day == date(2026, 10, 3) and [f.title for f in saturday.films] == ["A", "B"] and saturday.is_today
    assert all(len(week) == 7 for m in months for week in m.weeks)


def test_the_calendar_is_remembered_and_the_list_stays_the_default(client: TestClient) -> None:  # noqa: F811
    with Session(get_engine()) as session:
        _seed_page(session)

    listed = client.get(f"{BASE}/upcoming").text
    assert 'class="cal-grid"' not in listed and 'aria-current="page">☰ List' in listed

    calendar = client.get(f"{BASE}/upcoming?view=calendar").text
    assert 'class="cal-grid"' in calendar and "June 2027" in calendar
    assert '<time class="cal-date" datetime="2027-06-30">30</time>' in calendar
    assert f'hx-get="{BASE}/add/5"' in calendar
    assert "1 film with no date yet" in calendar
    assert 'class="cal-grid"' in client.get(f"{BASE}/upcoming").text, "remembered"
    assert 'class="cal-grid"' not in client.get(f"{BASE}/upcoming?view=list").text
