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


def test_a_choice_and_its_direction_are_remembered_per_person_and_per_page(session: Session) -> None:
    alice, bob = _user(session, "alice"), _user(session, "bob")

    assert sorting.resolve(session, alice, "franchises", None) == ("owned", "desc"), "the default"
    assert sorting.resolve(session, alice, "franchises", "name") == ("name", "asc"), "its natural direction"
    assert sorting.resolve(session, alice, "franchises", "name", "desc") == ("name", "desc"), "reversed"
    assert sorting.resolve(session, alice, "franchises", None) == ("name", "desc"), "remembered, direction too"
    assert sorting.resolve(session, alice, "collections", None) == ("rating", "desc"), "another page is its own"
    assert sorting.resolve(session, bob, "franchises", None) == ("owned", "desc"), "another person is their own"


def test_a_link_always_wins_and_nonsense_is_ignored(session: Session) -> None:
    alice = _user(session, "alice")
    sorting.resolve(session, alice, "directors", "missing")

    assert sorting.resolve(session, alice, "directors", "name", "sideways") == ("name", "asc")
    assert sorting.resolve(session, alice, "directors", "'; drop table") == ("name", "asc"), "not saved"


def test_choices_saved_before_the_direction_button_still_work(session: Session) -> None:
    """0.29.0 saved bare keys; "almost complete" is now Missing, fewest first."""
    from app.models import UserPreference

    alice = _user(session, "alice")
    for page, old in (("collections", "almost"), ("spinoffs", "oldest"), ("upcoming", "soonest")):
        session.add(UserPreference(user_id=alice, key=f"sort:{page}", value=old))
    session.commit()

    assert sorting.resolve(session, alice, "collections", None) == ("missing", "asc")
    assert sorting.resolve(session, alice, "spinoffs", None) == ("release", "asc")
    assert sorting.resolve(session, alice, "upcoming", None) == ("release", "asc")
    assert sorting.resolve(session, alice, "collections", "almost") == ("missing", "asc"), "old links too"


def test_the_control_says_which_way_and_offers_the_flip() -> None:
    ctl = sorting.control("collections", ("missing", "desc"), "/collections", hidden={"started": 1, "x": None})
    assert ctl["dir_label"] == "↓ Most first" and ctl["flip"] == "asc" and ctl["flip_label"] == "↑ Fewest first"
    assert [o["key"] for o in ctl["options"] if o["selected"]] == ["missing"]
    assert ctl["hidden"] == {"started": 1}
    assert "rating" not in [o["key"] for o in sorting.control("detail", ("release", "asc"), "/x",
                                                                   exclude=("rating",))["options"]]


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


def test_collection_orders_both_ways_with_finished_sets_trailing() -> None:
    a = G("Alpha", owned=[T("a1")] * 9, missing=[T("a2", "2001-01-01")])                 # 90%, 1 missing
    b = G("Bravo", owned=[T("b1")], missing=[T("b2", "2024-05-01"), T("b3", "1990-01-01")])  # 33%, 2 missing
    c = G("Charlie", owned=[T("c1")] * 3, missing=[])                                    # complete
    d = G("Delta", owned=[T("d1")] * 2, missing=[T("d2", "2010-01-01")] * 3)              # 40%, 3 missing
    groups = [c, d, b, a]
    order = lambda key, d: _names(sorting.sort_groups(groups, "collections", (key, d)))  # noqa: E731

    assert order("missing", "desc") == ["Delta", "Bravo", "Alpha", "Charlie"]
    assert order("missing", "asc") == ["Alpha", "Bravo", "Delta", "Charlie"], "the old 'almost complete'"
    assert order("complete", "desc") == ["Alpha", "Delta", "Bravo", "Charlie"]
    assert order("complete", "asc") == ["Bravo", "Delta", "Alpha", "Charlie"]
    assert order("release", "desc") == ["Bravo", "Delta", "Alpha", "Charlie"]
    assert order("name", "desc") == ["Delta", "Bravo", "Alpha", "Charlie"], "finished trails either way"


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
    order = lambda key, d: _names(sorting.sort_groups(groups, "franchises", (key, d)))  # noqa: E731

    assert order("owned", "desc") == ["Star Wars", "James Bond", "Alien"]
    assert order("owned", "asc") == ["Alien", "James Bond", "Star Wars"]
    assert order("missing", "desc") == ["James Bond", "Star Wars", "Alien"]
    assert order("complete", "desc") == ["Alien", "Star Wars", "James Bond"]
    assert order("release", "desc") == ["Star Wars", "James Bond", "Alien"]
    assert order("name", "asc") == ["Alien", "James Bond", "Star Wars"]


def test_detail_tiles_keep_undated_and_unrated_last_either_way() -> None:
    films = [T("Beta", "2005-01-01", 7.0), T("alpha", "1999-01-01", None), T("Gamma", None, 8.0)]
    titles = lambda key, d: [t.title for t in sorting.sort_titles(films, (key, d))]  # noqa: E731

    assert titles("release", "asc") == ["alpha", "Beta", "Gamma"]
    assert titles("release", "desc") == ["Beta", "alpha", "Gamma"], "undated still last"
    assert titles("rating", "desc") == ["Gamma", "Beta", "alpha"]
    assert titles("rating", "asc") == ["Beta", "Gamma", "alpha"], "unrated still last"
    assert titles("name", "desc") == ["Gamma", "Beta", "alpha"]


@dataclass
class S:
    spinoff_name: str
    first_air_year: int | None
    source_show_name: str = "NCIS"


def test_spinoff_orders_put_undated_last_either_way() -> None:
    shows = [S("Joey", 2004, "Friends"), S("Mystery", None), S("1923", 2022, "Yellowstone")]
    names = lambda key, d: [s.spinoff_name for s in sorting.sort_spinoffs(shows, (key, d))]  # noqa: E731
    assert names("release", "desc") == ["1923", "Joey", "Mystery"]
    assert names("release", "asc") == ["Joey", "1923", "Mystery"]
    assert names("show", "asc") == ["Joey", "Mystery", "1923"]


@dataclass
class U:
    title: str
    collection_name: str
    release_date: str | None


def test_upcoming_orders() -> None:
    films = [U("Secret Wars", "Avengers", "2027-12-17"), U("Doomsday", "Avengers", "2026-12-18"),
             U("Bond 26", "James Bond", None)]
    titles = lambda key, d: [f.title for f in sorting.sort_upcoming(films, (key, d))]  # noqa: E731
    assert titles("release", "asc") == ["Doomsday", "Secret Wars", "Bond 26"]
    assert titles("release", "desc") == ["Secret Wars", "Doomsday", "Bond 26"], "undated still last"
    assert titles("collection", "asc") == ["Doomsday", "Secret Wars", "Bond 26"]
    assert titles("name", "asc") == ["Bond 26", "Doomsday", "Secret Wars"]


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
def test_each_page_saves_the_field_and_direction(client: TestClient, path: str, page: str) -> None:
    last = sorting.OPTIONS[page][-1]
    flipped = "desc" if last.default_dir == "asc" else "asc"
    client.get(f"{BASE}{path}?sort={last.key}&dir={flipped}")

    with Session(get_engine()) as session:
        from app.models import UserPreference

        saved = session.exec(select(UserPreference).where(UserPreference.key == f"sort:{page}")).one()
        assert saved.value == f"{last.key}:{flipped}"


def test_a_franchise_page_offers_no_rating_sort_and_reads_a_remembered_one_as_release(client: TestClient) -> None:
    with Session(get_engine()) as session:
        admin = session.exec(select(User)).one()
        sorting.resolve(session, admin.id, "detail", "rating")

    body = client.get(f"{BASE}/franchises/Q1").text
    if 'class="sort-control"' in body:
        assert 'value="rating"' not in body and '<option value="release" selected>' in body
