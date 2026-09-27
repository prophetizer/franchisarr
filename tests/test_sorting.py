"""Sort options on every list page, and each person's last choice remembered on their account."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import Franchise, FranchiseMember, User
from app.services import sorting

BASE = "/franchisarr"
PASSWORD = "correct horse battery staple"


# ------------------------------------------------------------------ remembering


def _user(session: Session, name: str) -> int:
    user = User(external_user_id=name, external_username=name, is_admin=True)
    session.add(user); session.commit(); session.refresh(user)
    return user.id


def test_a_choice_is_remembered_per_person_and_per_page(session: Session) -> None:
    alice, bob = _user(session, "alice"), _user(session, "bob")

    assert sorting.resolve(session, alice, "franchises", None) == "owned", "the default"
    assert sorting.resolve(session, alice, "franchises", "name") == "name"
    assert sorting.resolve(session, alice, "franchises", None) == "name", "remembered"
    assert sorting.resolve(session, alice, "collections", None) == "rating", "another page is its own"
    assert sorting.resolve(session, bob, "franchises", None) == "owned", "another person is their own"


def test_a_link_always_wins_and_nonsense_is_ignored(session: Session) -> None:
    alice = _user(session, "alice")
    sorting.resolve(session, alice, "directors", "missing")

    assert sorting.resolve(session, alice, "directors", "name") == "name"
    assert sorting.resolve(session, alice, "directors", "'; drop table") == "name", "not saved"


# ------------------------------------------------------------------ orderings


@dataclass
class T:
    title: str
    release_date: str | None = None
    rating: float | None = None


@dataclass
class G:
    name: str
    owned: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    best_rating: float = -1.0


def _names(groups) -> list[str]:  # noqa: ANN001
    return [g.name for g in groups]


def test_collection_orders() -> None:
    a = G("Alpha", owned=[T("a1")] * 9, missing=[T("a2", "2001-01-01")])                 # 90%, 1 missing
    b = G("Bravo", owned=[T("b1")], missing=[T("b2", "2024-05-01"), T("b3", "1990-01-01")])  # 33%, 2 missing
    c = G("Charlie", owned=[T("c1")] * 3, missing=[])                                    # complete
    d = G("Delta", owned=[T("d1")] * 2, missing=[T("d2", "2010-01-01")] * 3)              # 40%, 3 missing
    groups = [c, d, b, a]

    assert _names(sorting.sort_groups(groups, "collections", "missing")) == ["Delta", "Bravo", "Alpha", "Charlie"]
    assert _names(sorting.sort_groups(groups, "collections", "almost")) == ["Alpha", "Bravo", "Delta", "Charlie"]
    assert _names(sorting.sort_groups(groups, "collections", "complete")) == ["Alpha", "Delta", "Bravo", "Charlie"]
    assert _names(sorting.sort_groups(groups, "collections", "newest")) == ["Bravo", "Delta", "Alpha", "Charlie"]
    assert _names(sorting.sort_groups(groups, "collections", "name"))[-1] == "Charlie", "complete ones trail"


@dataclass
class F:
    name: str
    owned_films: list = field(default_factory=list)
    owned_shows: list = field(default_factory=list)
    missing_films: list = field(default_factory=list)
    missing_shows: list = field(default_factory=list)

    @property
    def owned(self) -> int:
        return len(self.owned_films) + len(self.owned_shows)

    @property
    def missing(self) -> int:
        return len(self.missing_films) + len(self.missing_shows)


def test_franchise_orders() -> None:
    star = F("Star Wars", owned_films=[T("x", "1977-05-25")] * 8, missing_shows=[T("y", "2026-05-04")] * 7)
    bond = F("James Bond", owned_films=[T("x", "1962-10-05")] * 5, missing_films=[T("z", "2021-09-30")] * 20)
    alien = F("Alien", owned_films=[T("x", "1979-05-25")] * 4)
    groups = [bond, alien, star]

    assert _names(sorting.sort_groups(groups, "franchises", "owned")) == ["Star Wars", "James Bond", "Alien"]
    assert _names(sorting.sort_groups(groups, "franchises", "missing")) == ["James Bond", "Star Wars", "Alien"]
    assert _names(sorting.sort_groups(groups, "franchises", "complete")) == ["Alien", "Star Wars", "James Bond"]
    assert _names(sorting.sort_groups(groups, "franchises", "newest")) == ["Star Wars", "James Bond", "Alien"]
    assert _names(sorting.sort_groups(groups, "franchises", "name")) == ["Alien", "James Bond", "Star Wars"]


def test_detail_tiles_sort_by_release_rating_or_name() -> None:
    films = [T("Beta", "2005-01-01", 7.0), T("alpha", "1999-01-01", None), T("Gamma", None, 8.0)]

    assert [t.title for t in sorting.sort_titles(films, "release")] == ["alpha", "Beta", "Gamma"], "undated last"
    assert [t.title for t in sorting.sort_titles(films, "rating")] == ["Gamma", "Beta", "alpha"], "unrated last"
    assert [t.title for t in sorting.sort_titles(films, "name")] == ["alpha", "Beta", "Gamma"]


@dataclass
class S:
    spinoff_name: str
    first_air_year: int | None


def test_spinoff_orders_put_undated_last_either_way() -> None:
    shows = [S("Joey", 2004), S("Mystery", None), S("1923", 2022)]
    assert [s.spinoff_name for s in sorting.sort_spinoffs(shows, "newest")] == ["1923", "Joey", "Mystery"]
    assert [s.spinoff_name for s in sorting.sort_spinoffs(shows, "oldest")] == ["Joey", "1923", "Mystery"]


@dataclass
class U:
    title: str
    collection_name: str
    release_date: str | None


def test_upcoming_by_collection_and_name() -> None:
    films = [U("Secret Wars", "Avengers", "2027-12-17"), U("Doomsday", "Avengers", "2026-12-18"),
             U("Bond 26", "James Bond", None)]
    assert [f.title for f in sorting.sort_upcoming(films, "collection")] == ["Doomsday", "Secret Wars", "Bond 26"]
    assert [f.title for f in sorting.sort_upcoming(films, "name")] == ["Bond 26", "Doomsday", "Secret Wars"]


# ------------------------------------------------------------------ on the pages


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            session.add(Franchise(wikidata_id="Q1", name="Alien", kind="film series"))
            session.add(FranchiseMember(franchise_id="Q1", item_type="movie", tmdb_id=348, title="Alien", year=1979))
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


@pytest.mark.parametrize("path,page", [("/franchises", "franchises"), ("/collections", "collections"),
                                       ("/directors", "directors"), ("/upcoming", "upcoming")])
def test_each_page_offers_its_options_and_remembers_the_choice(client: TestClient, path: str, page: str) -> None:
    last_key, last_label = sorting.OPTIONS[page][-1]
    client.get(f"{BASE}{path}?sort={last_key}")

    body = client.get(f"{BASE}{path}").text
    assert f"<strong>{last_label}</strong>" in body or "Sort by" not in body, "remembered across visits"
    with Session(get_engine()) as session:
        from app.models import UserPreference

        saved = session.exec(select(UserPreference).where(UserPreference.key == f"sort:{page}")).one()
        assert saved.value == last_key


def test_a_franchise_page_offers_no_rating_sort_and_reads_a_remembered_one_as_release(client: TestClient) -> None:
    client.get(f"{BASE}/collections?sort=rating")          # harmless: collections use their own key
    with Session(get_engine()) as session:
        admin = session.exec(select(User)).one()
        sorting.resolve(session, admin.id, "detail", "rating")

    body = client.get(f"{BASE}/franchises/Q1").text
    if "Sort by" in body:
        assert ">rating<" not in body and "<strong>release date</strong>" in body
