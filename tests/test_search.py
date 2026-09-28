"""Search: one box for collections, franchises, directors, films and shows."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.api_keys import generate_api_key
from app.auth.dependencies import API_KEY_HEADER
from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import (
    CollectionExclude, DirectorFilm, DismissedItem, Franchise, FranchiseMember, IncludedLibrary, LibraryItem,
    MatchSource, MediaServer, MovieDirector, RadarrInstance, RadarrMovie, SpinoffMapping, TmdbCollection, TmdbCollectionMovie,
    TmdbMovie, TmdbShow, User,
)
from app.services import media_server_service, search_service
from app.services.settings_service import SettingKey, set_setting
from tests.conftest import seed_server

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"
TODAY = date(2026, 9, 28)
ALIEN = 8091


def _own(session: Session, server_id: int, tmdb_id: int, title: str, *, show: bool = False) -> None:
    session.add(LibraryItem(server_id=server_id, library_key="1", item_key=f"{server_id}-{tmdb_id}",
                            item_type="show" if show else "movie", title=title, tmdb_id=tmdb_id,
                            match_source=MatchSource.GUID.value))


def _library(session: Session) -> int:
    server = seed_server(session, "plex").id
    session.add(TmdbCollection(tmdb_collection_id=ALIEN, name="Alien Collection", poster_path="/alien.jpg"))
    for pos, (tid, title, released) in enumerate([(348, "Alien", "1979-05-25"), (679, "Aliens", "1986-07-18"),
                                                  (8077, "Alien³", "1992-05-22"), (999, "Alien: Next", "2027-01-01"),
                                                  (555, "Alien Toys", "2000-01-01")]):
        session.add(TmdbCollectionMovie(collection_id=ALIEN, tmdb_movie_id=tid, title=title, release_date=released,
                                        release_year=int(released[:4]), position=pos))
    session.add(CollectionExclude(tmdb_collection_id=ALIEN, tmdb_movie_id=555))
    session.add(TmdbMovie(tmdb_id=348, title="Alien", collection_id=ALIEN))
    for tid, title in ((348, "Alien"), (679, "Aliens"), (78, "Blade Runner"), (98, "Gladiator")):
        _own(session, server, tid, title)
    # Ridley Scott: three owned films clears the floor of 3, so he has a page.
    set_setting(session, SettingKey.MIN_DIRECTOR_FILMS, "3")
    for tid in (348, 78, 98):
        session.add(MovieDirector(tmdb_movie_id=tid, person_id=578, name="Ridley Scott"))
    session.add(DirectorFilm(person_id=578, tmdb_movie_id=286217, title="The Martian", release_date="2015-10-02"))
    # James Cameron directed one owned film: below the floor, no page.
    session.add(MovieDirector(tmdb_movie_id=679, person_id=2710, name="James Cameron"))
    session.add(Franchise(wikidata_id="Q16", name="Alien franchise"))
    session.add(FranchiseMember(franchise_id="Q16", item_type="movie", tmdb_id=348, title="Alien", year=1979))
    session.add(FranchiseMember(franchise_id="Q16", item_type="show", tmdb_id=157239, title="Alien: Earth", year=2025))
    # Shows: one owned, one spin-off suggestion.
    _own(session, server, 1396, "Breaking Bad", show=True)
    session.add(TmdbShow(tmdb_id=60059, name="Better Call Saul", first_air_year=2015))
    session.add(SpinoffMapping(source_show_tmdb_id=1396, spinoff_show_tmdb_id=60059, source="wikidata",
                               confidence="confirmed", origin_ref="P155"))
    session.add(IncludedLibrary(server_id=server, library_key="1", library_name="Films", library_type="movie",
                                enabled=True))
    session.commit()
    return server


def _find(results, group: str, title: str):
    return next(r for r in getattr(results, group) if getattr(r, "title", getattr(r, "name", None)) == title)


# ------------------------------------------------------------------ matching


@pytest.mark.parametrize("query,title", [("spiderman", "Spider-Man"), ("spider man", "Spider-Man"),
                                         ("amelie", "Amélie"), ("ALIEN 3", "Alien³")])
def test_matching_ignores_case_accents_and_punctuation(query: str, title: str) -> None:
    assert search_service.normalise(query) in search_service.normalise(title)


def test_one_letter_searches_for_nothing(session: Session) -> None:
    _library(session)
    results = search_service.search(session, "a", None, today=TODAY)
    assert results.too_short and results.empty


# ------------------------------------------------------------------ what's found


def test_every_kind_of_thing_is_found_with_its_status_and_pages(session: Session) -> None:
    _library(session)

    results = search_service.search(session, "alien", None, today=TODAY)

    assert [c.name for c in results.collections] == ["Alien Collection"]
    assert results.collections[0].detail == "2 of 4 owned", "the excluded film isn't counted"
    assert [f.name for f in results.franchises] == ["Alien franchise"]
    assert results.franchises[0].image_path == "/alien.jpg", "the owned film's collection poster, as on Franchises"
    films = {r.title: r for r in results.films}
    assert set(films) == {"Alien", "Aliens", "Alien³", "Alien: Next"}, "an excluded film is not in the collection"
    assert films["Alien"].status == "owned" and films["Alien"].servers == ("Plex",)
    assert [link.path for link in films["Alien"].links] == [f"/collections/{ALIEN}", "/franchises/Q16"]
    assert films["Alien³"].status == "missing"
    assert films["Alien: Next"].status == "upcoming"
    assert [s.title for s in results.shows] == ["Alien: Earth"]


def test_a_director_is_found_only_if_they_have_a_page(session: Session) -> None:
    _library(session)

    assert [d.name for d in search_service.search(session, "ridley", None, today=TODAY).directors] == ["Ridley Scott"]
    assert search_service.search(session, "cameron", None, today=TODAY).directors == []
    martian = _find(search_service.search(session, "martian", None, today=TODAY), "films", "The Martian")
    assert martian.status == "missing" and martian.links[0].path == "/directors/578"


def test_shows_owned_and_spin_offs(session: Session) -> None:
    _library(session)

    assert _find(search_service.search(session, "breaking", None, today=TODAY), "shows", "Breaking Bad").status == "owned"
    saul = _find(search_service.search(session, "saul", None, today=TODAY), "shows", "Better Call Saul")
    assert saul.status == "missing" and saul.links[0].path == "/shows"


def test_radarr_dismissed_and_a_server_that_is_off_change_the_status(session: Session) -> None:
    server = _library(session)
    instance = RadarrInstance(name="Radarr", url="http://radarr:7878", api_key="k" * 32)
    session.add(instance); session.commit(); session.refresh(instance)
    session.add(RadarrMovie(instance_id=instance.id, tmdb_id=8077, title="Alien³"))
    user = User(local_username="u", is_admin=True); session.add(user); session.commit(); session.refresh(user)
    session.add(DismissedItem(user_id=user.id, item_type="movie", tmdb_id=999)); session.commit()

    films = {r.title: r.status for r in search_service.search(session, "alien", user.id, today=TODAY).films}
    assert films["Alien³"] == "in_arr" and films["Alien: Next"] == "dismissed"

    media_server_service.set_enabled(session, session.get(MediaServer, server), False)
    films = {r.title: r.status for r in search_service.search(session, "alien", user.id, today=TODAY).films}
    assert films["Alien"] == "missing", "a server that's off holds nothing (0.32.0)"


# ------------------------------------------------------------------ the page


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            _library(session)
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def test_the_nav_links_to_search_and_the_page_finds_things(client: TestClient) -> None:
    assert f'href="{BASE}/search"' in client.get(f"{BASE}/collections").text

    page = client.get(f"{BASE}/search?q=alien").text

    assert "<h1>Search</h1>" in page and 'value="alien"' in page
    assert f'href="{BASE}/collections/{ALIEN}"' in page and f'href="{BASE}/franchises/Q16"' in page
    assert f'hx-get="{BASE}/add/8077"' in page, "Add for a missing film"
    assert f'hx-get="{BASE}/add/348"' not in page, "not for one already owned"


def test_typing_gets_just_the_results(client: TestClient) -> None:
    body = client.get(f"{BASE}/search?q=saul", headers={"HX-Request": "true", "HX-Target": "search-results"}).text

    assert "<h1>" not in body and "Better Call Saul" in body
    assert f'hx-get="{BASE}/shows/add/60059"' in body


def test_not_interested_hides_it_for_that_person(client: TestClient) -> None:
    response = client.post(f"{BASE}/search/dismiss/movie/8077")

    assert response.status_code == 200 and "Hidden from your lists" in response.text
    with Session(get_engine()) as session:
        assert session.exec(select(DismissedItem).where(DismissedItem.tmdb_id == 8077)).one()
    assert client.post(f"{BASE}/search/dismiss/person/1").status_code == 404


def test_a_member_can_search_but_not_add(client: TestClient) -> None:
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.ALLOW_MEMBER_SIGNIN, "true")
        member = User(external_user_id="m-1", external_username="housemate", is_admin=False)
        session.add(member); session.commit(); session.refresh(member)
        key = generate_api_key(session, member)

    client.cookies.clear()   # the fixture signed the admin in; this request is the member's alone
    page = client.get(f"{BASE}/search?q=alien", headers={API_KEY_HEADER: key}).text

    assert "Alien Collection" in page and "Not interested" in page
    assert f'/add/8077"' not in page
