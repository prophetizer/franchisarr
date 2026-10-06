"""0.72.0: designed placeholders, the A-Z rail, watched bars, set runtimes, the lightbox gallery,
Up next, the library in numbers and the density toggle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.clients import emby_client, plex_client
from app.db import get_engine
from app.models import LibraryItem
from app.services import az, home_service, runtimes
from app.templating import get_templates, title_hue
from tests.test_movie_ui import BASE, COLLECTION, _seed_collection, client  # noqa: F401 - fixture

HERE = Path(__file__).resolve().parents[1]


def _render(source: str, **context) -> str:
    return get_templates().env.from_string(source).render(**context)


# ------------------------------------------------------------------ runtimes


@dataclass
class _Film:
    title: str
    runtime: int | None = None
    watched: bool | None = None
    item_type: str = "movie"
    release_date: str | None = None
    release_year: int | None = None
    poster: str | None = None


def test_the_servers_runtimes_are_read_in_minutes() -> None:
    assert plex_client._runtime(6_540_000) == 109 and plex_client._runtime(None) is None
    assert plex_client._runtime("junk") is None and plex_client._runtime(0) is None
    assert emby_client._runtime(65_400_000_000) == 109 and emby_client._runtime(None) is None


def test_a_set_runs_as_long_as_its_owned_films() -> None:
    films = [_Film("A", 120, True), _Film("B", 95, False), _Film("C", None, False), _Film("S", 45, False, "show")]
    rt = runtimes.summary(films)
    assert (rt.films, rt.total, rt.left, rt.partial) == (3, 215, 95, True), "shows don't count; unknowns flag it"
    assert runtimes.summary([_Film("A"), _Film("B")]) is None, "nothing known, nothing said"
    assert runtimes.summary([_Film("A", 100), _Film("B", 50)]).left is None, "no watched state, no 'left'"
    assert [runtimes.hours(m) for m in (142, 50, 120, 0)] == ["2h 22m", "50m", "2h", "0m"]


def test_the_runtime_line_reads_naturally() -> None:
    src = '{% from "partials/set_runtime.html" import set_runtime %}{{ set_runtime(films) }}'
    line = " ".join(_render(src, films=[_Film("A", 120, True), _Film("B", 100, False)]).split())
    assert "3h 40m across the 2 films you own · 1h 40m still to watch" in line
    done = " ".join(_render(src, films=[_Film("A", 120, True)]).split())
    assert "2h across the 1 film you own · all watched" in done


def test_owned_details_carry_the_longest_runtime_a_server_reports(client: TestClient) -> None:  # noqa: F811
    from app.services.ownership_service import owned_details

    _seed_collection()
    with Session(get_engine()) as session:
        row = session.exec(select(LibraryItem).where(LibraryItem.tmdb_id == 90)).one()
        row.runtime = 105
        session.add(row)
        session.commit()
        assert owned_details(session)[90].runtime == 105
    page = client.get(f"{BASE}/collections/{COLLECTION}").text
    assert "1h 45m across the 1 film you own" in " ".join(page.split())


# ------------------------------------------------------------------ watched bars


def test_the_watched_bar_shows_only_when_a_server_says() -> None:
    assert runtimes.watched_of([_Film("A", watched=True), _Film("B", watched=False)]) == 1
    assert runtimes.watched_of([_Film("A"), _Film("B")]) is None
    src = '{% from "partials/completeness.html" import completeness %}{{ completeness(3, 1, watched) }}'
    assert 'class="watched-progress" value="2" max="3"' in _render(src, watched=2)
    assert "watched-progress" not in _render(src, watched=None)


# ------------------------------------------------------------------ placeholders


def test_a_film_without_a_poster_gets_a_designed_card() -> None:
    assert title_hue("Shrek 5") == title_hue("shrek 5"), "the same film, the same colour"
    tile = _render('{% from "partials/tile.html" import tile %}{% call tile(None, "missing", title="Shrek 5", year=2027) %}x{% endcall %}')
    assert f'class="collection-poster poster-card" style="--ph-hue: {title_hue("Shrek 5")}"' in tile
    assert '<span class="poster-card-title">Shrek 5</span>' in tile and '<span class="poster-card-year">2027</span>' in tile
    assert "collection-poster--empty" in _render('{% from "partials/tile.html" import tile %}{% call tile(None) %}x{% endcall %}'), \
        "no title to set, the plain block"


def test_no_list_of_titles_keeps_a_bare_grey_block_where_it_knows_the_title() -> None:
    for name in ("collections.html", "franchises.html", "directors.html", "upcoming.html", "partials/timeline.html",
                 "index.html", "partials/surprise.html"):
        page = (HERE / "app" / "templates" / name).read_text()
        assert "poster_card(" in page and "collection-poster--empty" not in page and "cal-film-name" not in page, name


# ------------------------------------------------------------------ A-Z rail


@dataclass
class _Named:
    name: str


def test_the_rail_jumps_to_the_page_each_letter_starts_on() -> None:
    names = [_Named(n) for n in ["2 Fast"] + [f"Alien {i}" for i in range(20)] + ["Batman", "the Matrix"] + [f"Zorro {i}" for i in range(10)]]
    letters = {l.letter: l.href for l in az.rail(names, path="/f/collections", size=25, params={"started": 1, "sort": "x"})}
    assert letters["#"] == "/f/collections?sort=name&dir=asc&page=1&started=1#az-num"
    assert letters["B"].endswith("page=1&started=1#az-B") and letters["T"].endswith("page=1&started=1#az-T")
    assert letters["Z"].endswith("page=1&started=1#az-Z") and "page=2" in az.rail(names, path="/c", size=20)[26].href
    assert letters["C"] is None
    assert az.rail(names[:10], path="/c", size=25) == [], "a short list has no rail"


def test_cards_carry_anchors_only_in_a_to_z_order() -> None:
    names = [_Named("Alien"), _Named("Aliens"), _Named("Batman")]
    assert az.anchors(names, ("name", "asc")) == {0: "az-A", 2: "az-B"}
    assert az.anchors(names, ("missing", "desc")) == {}
    for name in ("collections.html", "franchises.html", "directors.html"):
        page = (HERE / "app" / "templates" / name).read_text()
        assert '{% if loop.index0 in az_ids %} id="{{ az_ids[loop.index0] }}"{% endif %}' in page
        assert '{% include "partials/az_rail.html" %}' in page, name


# ------------------------------------------------------------------ up next


@dataclass
class _Gap:
    name: str
    collection_id: int
    owned: list


def test_up_next_is_the_first_unwatched_film_of_each_started_set() -> None:
    started = _Gap("Cop", 1, [_Film("Cop III", watched=False, release_date="1994-05-24"),
                              _Film("Cop", watched=True, release_date="1984-12-05"),
                              _Film("Cop II", watched=False, release_date="1987-05-18")])
    untouched = _Gap("Alien", 2, [_Film("Alien", watched=False), _Film("Aliens", watched=False)])
    finished = _Gap("Mad Max", 3, [_Film("Mad Max", watched=True)])
    unknown = _Gap("Heat", 4, [_Film("Heat")])
    cards = home_service.up_next([started, untouched, finished, unknown])
    assert [(c.title, c.detail, c.path) for c in cards] == [("Cop II", "Cop · 1 of 3 watched", "/collections/1")]


# ------------------------------------------------------------------ in numbers


def test_the_numbers_page_counts_the_library(client: TestClient) -> None:  # noqa: F811
    assert "Nothing scanned yet" in client.get(f"{BASE}/stats").text
    _seed_collection()
    page = client.get(f"{BASE}/stats").text
    assert "Your library in numbers" in page and "Films by decade" in page and "1980s" in page
    assert 'href="/franchisarr/stats"' in client.get(f"{BASE}/collections").text, "in the Browse menu"


# ------------------------------------------------------------------ density


def test_density_is_each_persons_and_marks_the_page(client: TestClient) -> None:  # noqa: F811
    page = client.get(f"{BASE}/collections").text
    assert "data-density" not in page and "▤ Density: comfortable" in page
    client.post(f"{BASE}/preferences/density", data={"value": "compact", "back": f"{BASE}/collections"})
    page = client.get(f"{BASE}/collections").text
    assert 'data-density="compact"' in page and "▤ Density: compact" in page
    css = (HERE / "app" / "static" / "app.css").read_text()
    assert '[data-density="compact"] .collection-card--compact > .missing-preview { display: none; }' in css


# ------------------------------------------------------------------ lightbox gallery


def test_the_lightbox_steps_through_the_sets_strip() -> None:
    js = (HERE / "app" / "static" / "showcase-cinema.js").read_text()
    assert "document.querySelectorAll('.timeline-step')" in js and "box.classList.toggle('is-gallery', gallery.length > 1);" in js
    assert "e.key === 'ArrowLeft'" in js and "e.key === 'ArrowRight'" in js
    css = (HERE / "app" / "static" / "showcase.css").read_text()
    assert '[data-look="showcase"] .sc-lightbox.is-gallery .sc-lightbox-step { display: block; }' in css
