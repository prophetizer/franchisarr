"""Showcase 0.60.0: genre moods, end credits, the ticket stub, the shelf and the empty-page
scenes -- the server's side of each. The motion itself lives in showcase-cinema.js and was
checked in a browser."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import get_engine
from app.models import DirectorFilm, MovieDirector, TmdbCollection, TmdbCollectionMovie
from app.services import about_service, end_credits
from app.services.timeline import Step
from tests.test_movie_ui import BASE, COLLECTION, _seed_collection, client  # noqa: F401 - fixture

HERE = Path(__file__).resolve().parents[1]


def _film(session: Session, tmdb_id: int, collection_id: int, genres: str | None) -> None:
    if session.get(TmdbCollection, collection_id) is None:
        session.add(TmdbCollection(tmdb_collection_id=collection_id, name=f"Set {collection_id}"))
    session.add(TmdbCollectionMovie(collection_id=collection_id, tmdb_movie_id=tmdb_id, title=str(tmdb_id),
                                    genre_ids=genres))


# ------------------------------------------------------------------ genre moods


def test_a_set_takes_the_mood_most_of_its_films_share(session: Session) -> None:
    _film(session, 1, 40, "878,28")
    _film(session, 2, 40, "878")
    _film(session, 3, 40, "35")
    _film(session, 4, 41, "37")
    _film(session, 5, 41, "35")
    _film(session, 6, 42, None)
    session.commit()

    assert about_service.mood(session, collection_id=40) == "scifi"
    assert about_service.mood(session, collection_id=41) is None, "half isn't most"
    assert about_service.mood(session, collection_id=42) is None, "unknown genres set no mood"
    assert about_service.mood(session, film_ids=[1, 2, 5]) == "scifi"
    assert about_service.mood(session) is None


def test_horror_wins_a_tie_and_crime_loses_one(session: Session) -> None:
    """An animated horror is horror (and gets October's touch); a crime thriller that's mostly
    action is filed under crime by TMDb far too often to let crime win anything."""
    _film(session, 1, 50, "16,27")
    _film(session, 2, 50, "16,27")
    _film(session, 3, 51, "80,10752")
    _film(session, 4, 51, "80,10752")
    session.commit()

    assert about_service.mood(session, collection_id=50) == "horror"
    assert about_service.is_horror(session, collection_id=50)
    assert about_service.mood(session, collection_id=51) == "war"


def test_nothing_drifts_or_chases_over_a_banner() -> None:
    """michael, 2026-10-03: "get rid of the snow type specs, get rid of the flashing lights on
    completed" -- the motes, the film grain, the genre weather, the beam's dust and the marquee
    bulbs all went in 0.70.1. The genre grades and the vignette stay."""
    js = (HERE / "app" / "static" / "showcase-cinema.js").read_text()
    css = (HERE / "app" / "static" / "showcase.css").read_text()
    main = (HERE / "app" / "static" / "showcase.js").read_text()
    for gone in ("sc-marquee", "sc-chase", "sc-mood--", "sc-shooting", "sc-beam-dust", "sc-grain", "@keyframes sc-mote",
                 "feTurbulence"):
        assert gone not in js + css + main, gone
    assert "mote.style" not in main
    assert "root.dataset.mood = moody.dataset.mood;" in js
    assert '[data-look="showcase"][data-mood="western"] .collection-backdrop' in css
    assert "radial-gradient(ellipse at center, transparent 55%" in css, "the vignette stays"


def test_the_detail_page_carries_its_mood(client: TestClient) -> None:  # noqa: F811
    _seed_collection()
    assert "data-mood=" not in client.get(f"{BASE}/collections/{COLLECTION}").text
    with Session(get_engine()) as session:
        for row in session.exec(select(TmdbCollectionMovie)).all():
            row.genre_ids = "37"
            session.add(row)
        session.commit()
    assert 'data-mood="western"' in client.get(f"{BASE}/collections/{COLLECTION}").text


# ------------------------------------------------------------------ end credits


def _step(tmdb_id: int, title: str, status: str = "owned", item_type: str = "movie") -> Step:
    return Step(title, 2000, None, status, tmdb_id, item_type)


def test_credits_name_who_directed_each_film(session: Session) -> None:
    session.add(MovieDirector(tmdb_movie_id=1, person_id=7, name="Martin Brest"))
    session.add(MovieDirector(tmdb_movie_id=1, person_id=8, name="Second Unit"))
    # A missing film: known only from the filmography of a director of an owned one.
    session.add(DirectorFilm(person_id=7, tmdb_movie_id=2, title="Two"))
    session.commit()

    credits = end_credits.roll(session, [_step(1, "One"), _step(2, "Two", "missing"), _step(3, "Three", "missing"),
                                         _step(1, "A show", item_type="show")])

    assert [c.directors for c in credits] == [("Martin Brest", "Second Unit"), ("Martin Brest",), (), ()], \
        "a show's id is not a film's, even when the numbers match"
    assert [c.status for c in credits] == ["owned", "missing", "missing", "owned"]


def test_only_showcase_rolls_the_credits(client: TestClient) -> None:  # noqa: F811
    _seed_collection()
    classic = client.get(f"{BASE}/collections/{COLLECTION}").text
    assert 'class="end-credits"' not in classic

    client.post(f"{BASE}/look", data={"look": "showcase"})
    page = client.get(f"{BASE}/collections/{COLLECTION}").text

    credits = page[page.index('class="end-credits"'):]
    assert credits.index("Beverly Hills Cop II") < credits.index("Beverly Hills Cop III"), "release order"
    assert "To be continued" in credits and "The End" not in credits, "two of three are missing"
    assert "showcase-cinema.js" in page


def test_a_set_of_one_has_nothing_to_roll(session: Session) -> None:
    from app.models import User
    from app.services import look

    user = User(username="viewer", is_admin=False)
    session.add(user)
    session.commit()
    look.set_look(session, user.id, look.SHOWCASE)
    session.commit()

    assert end_credits.for_page(session, user, [_step(1, "One")]) == []
    assert len(end_credits.for_page(session, user, [_step(1, "One"), _step(2, "Two")])) == 2


# ------------------------------------------------------------------ ticket stub


def _add_result(**context) -> str:
    from app.templating import get_templates

    return get_templates().env.get_template("partials/add_result.html").render(**context)


def test_an_add_that_worked_carries_its_ticket_and_one_that_failed_does_not() -> None:
    added = _add_result(added=True, title="Beverly Hills Cop III", instance="Radarr 4K", searched=True)
    assert 'data-ticket="Beverly Hills Cop III" data-ticket-to="Radarr 4K">' in added

    requested = _add_result(added=True, requested=True, title="Axel F", instance="Seerr")
    assert "data-ticket-requested" in requested

    failed = _add_result(added=False, title="Beverly Hills Cop III", instance="Radarr", error="No.")
    assert "data-ticket" not in failed


def test_the_ticket_title_is_escaped() -> None:
    added = _add_result(added=True, title='A "quoted" <title>', instance="Radarr")
    assert 'data-ticket="A &#34;quoted&#34; &lt;title&gt;"' in added


# ------------------------------------------------------------------ shelf and scenes


def test_the_collections_and_franchises_grids_can_be_shelved() -> None:
    for name in ("collections.html", "franchises.html"):
        page = (HERE / "app" / "templates" / name).read_text()
        assert '<div class="collection-grid collection-grid--compact" data-shelf>' in page, name


def test_every_scene_the_pages_name_is_one_the_script_draws() -> None:
    js = (HERE / "app" / "static" / "showcase-cinema.js").read_text()
    drawn = set(re.findall(r"^    (\w+): '<svg", js, re.M))
    named: set[str] = set()
    for page in (HERE / "app" / "templates").rglob("*.html"):
        text = page.read_text()
        named |= set(re.findall(r'data-scene="(\w+)"', text))
        for expression in re.findall(r'data-scene="\{\{(.*?)\}\}"', text):   # chosen in the template
            named |= set(re.findall(r"'(\w+)'", expression))
    assert named == drawn == {"usher", "ghostlight", "reel"}


def test_an_empty_collections_page_sets_its_scene(client: TestClient) -> None:  # noqa: F811
    assert 'data-scene="reel"' in client.get(f"{BASE}/collections").text, "nothing scanned yet"


def test_shading_never_reads_the_background_colour_inside_a_link() -> None:
    """Pico redefines --pico-background-color on every link (as transparent) and button, so a fade
    or shadow built from it inside one draws nothing: the spotlight's legibility shading was
    invisible from 0.48.0 to 0.60.1. Showcase takes the page's colour once, at the root."""
    css = (HERE / "app" / "static" / "showcase.css").read_text()
    assert css.count("var(--pico-background-color)") == 1
    assert "--sc-page: var(--pico-background-color);" in css
    app = (HERE / "app" / "static" / "app.css").read_text()
    assert ".fm-node :is(circle, rect) { fill: var(--franchisarr-page);" in app, "the map's nodes are links"
    assert ".fm-star circle { cursor: grab; fill: var(--franchisarr-page);" in app


def test_nothing_falls_in_october_or_december() -> None:
    """michael, 2026-10-02: "remove those falling leaves things" -- and December's snow with them.
    October's pumpkin glow and December's frost stay."""
    js = (HERE / "app" / "static" / "showcase.js").read_text()
    assert not any(mark in js for mark in ("🍂", "🍁", "❄", "❅", "❆", "sc-sky"))
    assert "root.classList.add('sc-october');" in js and "root.classList.add('sc-december');" in js


# ------------------------------------------------------------------ 0.62.0


def _render(source: str) -> str:
    from app.templating import get_templates

    return get_templates().env.from_string(source).render()


def test_a_show_tile_is_marked_for_its_tv_screen_and_a_film_tile_is_not() -> None:
    show = _render('{% from "partials/tile.html" import tile %}{% call tile("/p.jpg", "owned", show=True) %}x{% endcall %}')
    film = _render('{% from "partials/tile.html" import tile %}{% call tile("/p.jpg", "owned") %}x{% endcall %}')
    assert 'film-tile owned is-show"' in show and "is-show" not in film


def test_films_on_the_spin_offs_page_stay_out_of_the_tv_frame() -> None:
    page = (HERE / "app" / "templates" / "shows.html").read_text()
    films = page[page.index("films_from_shows %}"):]
    assert "'#add-dialog', none, show=False) }}" in films


def test_release_dates_are_machine_readable_for_the_countdown(client: TestClient) -> None:  # noqa: F811
    _seed_collection(with_upcoming=True)
    page = client.get(f"{BASE}/collections/{COLLECTION}").text
    assert 'expected <time datetime="2099-01-01">2099-01-01</time>' in page
    for name in ("franchise_detail.html", "director_detail.html", "upcoming.html"):
        assert '<time datetime="{{' in (HERE / "app" / "templates" / name).read_text(), name


def test_the_banner_says_how_much_is_owned_for_the_colour_fill(client: TestClient) -> None:  # noqa: F811
    _seed_collection()
    assert 'data-have="1" data-of="3"' in client.get(f"{BASE}/collections/{COLLECTION}").text
    assert 'data-have="{{ f.owned }}" data-of="{{ f.total }}"' in (HERE / "app" / "templates" / "franchise_detail.html").read_text()


def test_activity_marks_its_table_for_the_stubs() -> None:
    assert "<table data-stubs>" in (HERE / "app" / "templates" / "activity.html").read_text()
    js = (HERE / "app" / "static" / "showcase-cinema.js").read_text()
    assert "document.querySelector('table[data-stubs]')" in js and "ledger.hidden = true;" in js
