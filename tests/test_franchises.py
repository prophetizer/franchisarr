"""Franchise pages: one view per franchise, assembled from every list the app already keeps."""

from __future__ import annotations

import pytest
import responses
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.clients.tmdb_client import TMDB_BASE_URL, TmdbClient
from app.clients.wikidata_client import SPARQL_ENDPOINT, WikidataClient
from app.db import get_engine
from app.models import (
    CrossMediaMapping, Franchise, FranchiseMember, IncludedLibrary, ItemType, LibraryItem,
    MatchSource, SpinoffMapping, TmdbCollection, TmdbCollectionMovie, TmdbMovie, TmdbShow,
)
from app.services import franchise_service

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"
TREK = "Q1092"


def _sparql(*rows): return {"results": {"bindings": list(rows)}}


def _own_film(session, tmdb_id, title, collection_id=None):
    session.add(TmdbMovie(tmdb_id=tmdb_id, title=title, collection_id=collection_id))
    session.add(LibraryItem(plex_library_key="1", rating_key=f"f{tmdb_id}", item_type="movie",
                            title=title, year=1990, tmdb_id=tmdb_id, match_source="guid"))


def _own_show(session, tmdb_id, name):
    session.add(TmdbShow(tmdb_id=tmdb_id, name=name))
    session.add(LibraryItem(plex_library_key="2", rating_key=f"s{tmdb_id}", item_type="show",
                            title=name, year=1990, tmdb_id=tmdb_id, match_source="guid"))


def _franchise(session, *members: tuple[str, int, str]):
    session.add(Franchise(wikidata_id=TREK, name="Star Trek", kind="media franchise"))
    for item_type, tmdb_id, title in members:
        session.add(FranchiseMember(franchise_id=TREK, item_type=item_type, tmdb_id=tmdb_id,
                                    title=title, year=1990))
    session.commit()


# ------------------------------------------------------------------ assembly


def test_owned_titles_split_by_medium_and_roster_gaps_are_listed(session: Session) -> None:
    _own_film(session, 154, "Wrath of Khan")
    _own_show(session, 1855, "Voyager")
    _franchise(session, ("movie", 154, "Wrath of Khan"), ("show", 1855, "Voyager"),
               ("show", 580, "Deep Space Nine"), ("movie", 152, "The Motion Picture"))

    view = franchise_service.franchise_views(session)[0]

    assert [t.title for t in view.owned_films] == ["Wrath of Khan"]
    assert [t.title for t in view.owned_shows] == ["Voyager"]
    assert [t.title for t in view.missing_shows] == ["Deep Space Nine"]
    assert [t.title for t in view.missing_films] == ["The Motion Picture"]
    assert view.missing_shows[0].via == "franchise"
    assert view.spans_both and view.total == 4


def test_collection_gaps_of_owned_films_are_folded_in_and_outrank_the_roster(session: Session) -> None:
    """A film reached through a collection is a fact; the same film on Wikidata's roster is a
    weaker claim. When both say it, the collection's account wins."""
    session.add(TmdbCollection(tmdb_collection_id=1, name="Trek Films"))
    session.add(TmdbCollectionMovie(collection_id=1, tmdb_movie_id=154, title="Wrath of Khan",
                                    release_year=1982, release_date="1982-06-04", position=0))
    session.add(TmdbCollectionMovie(collection_id=1, tmdb_movie_id=157, title="Search for Spock",
                                    release_year=1984, release_date="1984-06-01", position=1))
    session.add(TmdbCollectionMovie(collection_id=1, tmdb_movie_id=999, title="Trek 2030",
                                    release_year=2030, release_date="2030-01-01", position=2))
    _own_film(session, 154, "Wrath of Khan", collection_id=1)
    _franchise(session, ("movie", 154, "Wrath of Khan"), ("movie", 157, "Search for Spock"))

    view = franchise_service.franchise_views(session)[0]

    assert [(t.title, t.via) for t in view.missing_films] == [("Search for Spock", "collection")]
    assert [t.title for t in view.upcoming_films] == ["Trek 2030"]


def test_spinoffs_and_continuations_of_franchise_titles_are_included(session: Session) -> None:
    _own_show(session, 1855, "Voyager")
    _own_film(session, 154, "Wrath of Khan")
    session.add(TmdbShow(tmdb_id=580, name="Deep Space Nine", first_air_year=1993))
    session.add(SpinoffMapping(source_show_tmdb_id=1855, spinoff_show_tmdb_id=580,
                               source="wikidata", origin_ref="P155"))
    session.add(CrossMediaMapping(source_type="movie", source_tmdb_id=154, target_type="show",
                                  target_tmdb_id=253, target_title="The Original Series",
                                  target_year=1966, relation="P144", confidence="heuristic"))
    _franchise(session, ("movie", 154, "Wrath of Khan"), ("show", 1855, "Voyager"))

    view = franchise_service.franchise_views(session)[0]

    assert {(t.title, t.via) for t in view.missing_shows} == {
        ("Deep Space Nine", "spin-off"), ("The Original Series", "continuation")}


def test_a_title_already_in_the_arr_is_not_a_gap(session: Session, monkeypatch) -> None:
    _own_show(session, 1855, "Voyager")
    _franchise(session, ("show", 1855, "Voyager"), ("show", 580, "Deep Space Nine"))
    monkeypatch.setattr(franchise_service.tv_spinoff_service, "sonarr_known_ids",
                        lambda session, instance_id=None: {580})

    assert franchise_service.franchise_views(session)[0].missing_shows == []


def test_franchises_sort_by_how_much_you_own(session: Session) -> None:
    _own_film(session, 1, "A"); _own_film(session, 2, "B"); _own_film(session, 3, "C")
    session.add(Franchise(wikidata_id="Q1", name="Small", kind=None))
    session.add(FranchiseMember(franchise_id="Q1", item_type="movie", tmdb_id=1, title="A"))
    session.add(Franchise(wikidata_id="Q2", name="Big", kind=None))
    for i in (2, 3):
        session.add(FranchiseMember(franchise_id="Q2", item_type="movie", tmdb_id=i, title="x"))
    session.commit()

    assert [v.name for v in franchise_service.franchise_views(session)] == ["Big", "Small"]


# ------------------------------------------------------------------ discovery


def _membership_row(tmdb: int, prop: str, qid: str, label: str, cls: str) -> dict:
    return {"tmdb": {"value": str(tmdb)}, "p": {"value": f"http://www.wikidata.org/prop/direct/{prop}"},
            "fr": {"value": f"http://www.wikidata.org/entity/{qid}"}, "frLabel": {"value": label},
            "frClassLabel": {"value": cls}}


def _member_row(qid: str, name: str, cls: str, film: int | None = None, tv: int | None = None) -> dict:
    row = {"m": {"value": f"http://www.wikidata.org/entity/{qid}"}, "mLabel": {"value": name},
           "classLabel": {"value": cls}}
    if film: row["tmdbF"] = {"value": str(film)}
    if tv: row["tmdbT"] = {"value": str(tv)}
    return row


@responses.activate
def test_discovery_folds_subgroups_and_filters_the_roster(session: Session) -> None:
    """Infinity Saga folds into the MCU; episodes and cancelled projects are dropped, and a
    short is kept but tagged so a preference can decide."""
    _own_film(session, 1, "Iron Man"); _own_film(session, 2, "Thor")
    session.commit()
    # membership: shows batch (none), films batch
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        _membership_row(1, "P179", "Q642", "Marvel Cinematic Universe", "media franchise"),
        _membership_row(2, "P179", "Q999", "The Infinity Saga", "film series"),
        _membership_row(2, "P179", "Q777", "list of Marvel films", "Wikimedia list article"),
    ))
    # parents
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        {"child": {"value": "http://www.wikidata.org/entity/Q999"},
         "parent": {"value": "http://www.wikidata.org/entity/Q642"}}))
    # roster of the one kept franchise
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        _member_row("Q10", "Iron Man", "film", film=1),
        _member_row("Q11", "Thor", "film", film=2),
        _member_row("Q12", "Team Thor", "short film", film=3),
        _member_row("Q13", "Some Episode", "television series episode", film=4),
        _member_row("Q14", "Loki", "television series", tv=84958),
    ))
    responses.add(responses.GET, f"{TMDB_BASE_URL}/tv/84958",
                  json={"id": 84958, "name": "Loki", "first_air_date": "2021-06-09", "poster_path": "/l.jpg"})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/1", json={"id": 1, "title": "Iron Man", "poster_path": "/im.jpg"})
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/2", json={"id": 2, "title": "Thor", "poster_path": "/t.jpg"})

    kept = franchise_service.discover(
        session, WikidataClient(max_requests_per_second=10_000),
        TmdbClient("k" * 32, max_requests_per_second=10_000))

    assert kept == 1
    franchise = session.exec(select(Franchise)).one()
    assert franchise.name == "Marvel Cinematic Universe"
    members = {(m.item_type, m.title, m.kind) for m in session.exec(select(FranchiseMember))}
    assert members == {("movie", "Iron Man", "film"), ("movie", "Thor", "film"),
                       ("show", "Loki", "television series"),
                       ("movie", "Team Thor", "short film")}, "the short is kept and tagged, not dropped"


@responses.activate
def test_a_franchise_with_one_owned_title_is_not_kept(session: Session) -> None:
    _own_film(session, 1, "Lonely"); session.commit()
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        _membership_row(1, "P8345", "Q5", "Lonely Franchise", "media franchise")))
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())

    assert franchise_service.discover(session, WikidataClient(max_requests_per_second=10_000), None) == 0
    assert session.exec(select(Franchise)).all() == []


# ------------------------------------------------------------------ pages


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            session.add(IncludedLibrary(plex_library_key="1", plex_library_name="Movies",
                                        library_type="movie", enabled=True))
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def test_the_index_and_detail_pages_render(client: TestClient) -> None:
    with Session(get_engine()) as session:
        _own_film(session, 154, "Wrath of Khan"); _own_show(session, 1855, "Voyager")
        _franchise(session, ("movie", 154, "Wrath of Khan"), ("show", 1855, "Voyager"),
                   ("show", 580, "Deep Space Nine"))

    index = client.get(f"{BASE}/franchises").text
    assert "Star Trek" in index and "2 owned" in index and "1 missing" in index
    assert f'href="{BASE}/franchises/{TREK}"' in index

    detail = client.get(f"{BASE}/franchises/{TREK}").text
    assert "You have 2 of 3" in detail
    assert "Deep Space Nine" in detail
    assert f'hx-get="{BASE}/shows/add/580"' in detail, "a show routes to the Sonarr dialog"
    assert "Wikidata files it under Star Trek" in detail

    assert client.get(f"{BASE}/franchises/Q0").status_code == 404


@responses.activate
def test_two_wikidata_items_with_one_tmdb_id_are_one_member(session: Session) -> None:
    """Spider-Man: No Way Home and its extended edition are two Wikidata items and one film.
    Found on the real library as a unique-constraint crash."""
    _own_film(session, 1, "A"); _own_film(session, 2, "B"); session.commit()
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        _membership_row(1, "P8345", "Q9", "Spidey", "media franchise"),
        _membership_row(2, "P8345", "Q9", "Spidey", "media franchise")))
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        _member_row("Q100", "No Way Home", "film", film=634649),
        _member_row("Q101", "No Way Home: The More Fun Stuff Version", "film", film=634649),
        _member_row("Q102", "A", "film", film=1), _member_row("Q103", "B", "film", film=2)))

    franchise_service.discover(session, WikidataClient(max_requests_per_second=10_000), None)

    ids = [m.tmdb_id for m in session.exec(select(FranchiseMember))]
    assert sorted(ids) == [1, 2, 634649]


@responses.activate
def test_same_named_franchise_and_film_series_items_are_one_franchise(session: Session) -> None:
    """Wikidata has "Jurassic Park" twice -- a media-franchise item and a film-series item with no
    link between them. Twenty such pairs on the real library; to the user each is one thing."""
    _own_film(session, 1, "JP"); _own_film(session, 2, "JP2"); _own_film(session, 3, "JP3")
    session.commit()
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        _membership_row(1, "P8345", "Q2336369", "Jurassic Park", "media franchise"),
        _membership_row(2, "P8345", "Q2336369", "Jurassic Park", "media franchise"),
        _membership_row(2, "P179", "Q17862144", "Jurassic Park", "film series"),
        _membership_row(3, "P179", "Q17862144", "Jurassic Park", "film series")))
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())   # parents: none
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        _member_row("Qa", "JP", "film", film=1), _member_row("Qb", "JP2", "film", film=2)))

    kept = franchise_service.discover(session, WikidataClient(max_requests_per_second=10_000), None)

    assert kept == 1
    franchise = session.exec(select(Franchise)).one()
    assert franchise.wikidata_id == "Q2336369", "the media-franchise item is canonical"
    assert sorted(m.tmdb_id for m in session.exec(select(FranchiseMember))) == [1, 2, 3]



@responses.activate
def test_a_subgroup_folded_to_a_merged_top_ends_at_the_canonical_one(session: Session) -> None:
    """James Bond on the real library: films sit on the film-series item directly, and on the
    franchise item only via 'Eon James Bond series' -> part of -> franchise. Merging the two
    same-named tops has to carry the sub-group with it, or both tops keep all the films."""
    _own_film(session, 1, "Dr. No"); _own_film(session, 2, "Goldfinger"); session.commit()
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        _membership_row(1, "P179", "Q2484680", "James Bond", "film series"),
        _membership_row(2, "P179", "Q2484680", "James Bond", "film series"),
        _membership_row(1, "P179", "Qeon", "Eon James Bond series", "film series"),
        _membership_row(2, "P179", "Qeon", "Eon James Bond series", "film series"),
        _membership_row(1, "P8345", "Q59130", "James Bond", "media franchise")))
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        {"child": {"value": "http://www.wikidata.org/entity/Qeon"},
         "parent": {"value": "http://www.wikidata.org/entity/Q59130"}}))
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        _member_row("Qa", "Dr. No", "film", film=1), _member_row("Qb", "Goldfinger", "film", film=2)))
    # rosters of the two folded-in items: the film-series twin knows a film the franchise doesn't
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        _member_row("Qc", "Thunderball", "film", film=3)))
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/3", json={"id": 3, "title": "Thunderball"})

    kept = franchise_service.discover(session, WikidataClient(max_requests_per_second=10_000),
                                      TmdbClient("k" * 32, max_requests_per_second=10_000))

    assert kept == 1
    assert session.exec(select(Franchise)).one().wikidata_id == "Q59130"
    assert sorted(m.title for m in session.exec(select(FranchiseMember))) == ["Dr. No", "Goldfinger", "Thunderball"]


@responses.activate
def test_discovery_is_skipped_inside_the_ttl(session: Session) -> None:
    """The roster is a query per franchise -- two hundred on the real library, ten minutes the
    first time round. Membership changes on the scale of months, so inside the TTL a scan
    leaves the tables alone and asks Wikidata nothing."""
    from datetime import timedelta

    from app.models import utcnow

    session.add(Franchise(wikidata_id="Q1", name="Fresh", kind=None, fetched_at=utcnow()))
    session.commit()

    kept = franchise_service.discover(
        session, WikidataClient(max_requests_per_second=10_000), None, ttl=timedelta(days=7))

    assert kept == 1
    assert len(responses.calls) == 0


@responses.activate
def test_a_zero_ttl_forces_a_rebuild(session: Session) -> None:
    from datetime import timedelta

    from app.models import utcnow

    session.add(Franchise(wikidata_id="Q1", name="Stale", kind=None, fetched_at=utcnow()))
    session.commit()
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())

    kept = franchise_service.discover(
        session, WikidataClient(max_requests_per_second=10_000), None, ttl=timedelta(0))

    assert kept == 0 and session.exec(select(Franchise)).all() == []


@responses.activate
def test_owned_titles_do_not_cost_a_tmdb_request(session: Session) -> None:
    _own_film(session, 1, "Dr. No"); _own_film(session, 2, "Goldfinger"); session.commit()
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        _membership_row(1, "P8345", "Q59130", "James Bond", "media franchise"),
        _membership_row(2, "P8345", "Q59130", "James Bond", "media franchise")))
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql(
        _member_row("Qa", "Dr. No", "film", film=1), _member_row("Qb", "Goldfinger", "film", film=2),
        _member_row("Qc", "Thunderball", "film", film=3)))
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/3",
                  json={"id": 3, "title": "Thunderball", "release_date": "1965-12-09"})

    franchise_service.discover(session, WikidataClient(max_requests_per_second=10_000),
                               TmdbClient("k" * 32, max_requests_per_second=10_000))

    tmdb_calls = [c for c in responses.calls if "themoviedb" in c.request.url]
    assert len(tmdb_calls) == 1, "only the unowned title needed TMDb"



def test_tv_films_and_shorts_fold_away_unless_the_preference_says_otherwise(session: Session) -> None:
    """The Star Wars Holiday Special is filed under Star Wars on Wikidata, as a television film.
    It is on the page -- folded, never counted as missing -- until someone says they want it."""
    from app.services.settings_service import SettingKey, set_setting

    _own_film(session, 11, "A New Hope"); _own_film(session, 1891, "Empire")
    session.add(Franchise(wikidata_id="Q462", name="Star Wars", kind="media franchise"))
    for tid, title, kind in ((11, "A New Hope", "film"), (1891, "Empire", "film"),
                             (74849, "The Star Wars Holiday Special", "television film"),
                             (1893, "Return of the Jedi", "film")):
        session.add(FranchiseMember(franchise_id="Q462", item_type="movie", tmdb_id=tid, title=title, kind=kind))
    session.commit()

    view = franchise_service.franchise_views(session)[0]
    assert [t.title for t in view.missing_films] == ["Return of the Jedi"]
    assert [t.title for t in view.specials] == ["The Star Wars Holiday Special"]
    assert view.missing == 1

    set_setting(session, SettingKey.FRANCHISE_INCLUDE_TV_FILMS, "true"); session.commit()
    view = franchise_service.franchise_views(session)[0]
    assert {t.title for t in view.missing_films} == {"Return of the Jedi", "The Star Wars Holiday Special"}
    assert view.specials == []
