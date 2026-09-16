"""Continuations across media -- films for owned shows, shows for owned films."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
import responses
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.clients.tmdb_client import TMDB_BASE_URL, TmdbClient
from app.clients.wikidata_client import SPARQL_ENDPOINT, CrossMediaRelation, WikidataClient
from app.db import get_engine
from app.models import (
    CrossMediaMapping, IncludedLibrary, ItemType, LibraryItem, MappingConfidence, MatchSource,
    TmdbMovie, TmdbShow,
)
from app.services import cross_media_service

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"


def _client() -> WikidataClient:
    return WikidataClient(max_requests_per_second=10_000)


def _sparql(*rows: dict) -> dict:
    return {"results": {"bindings": list(rows)}}


def _row(mine: int, other: int, name: str, prop: str, mine_label: str = "Mine",
         src_lang: str | None = None, other_lang: str | None = None) -> dict:
    row = {
        "tmdb": {"value": str(mine)}, "mineLabel": {"value": mine_label},
        "other": {"value": f"http://www.wikidata.org/entity/Q{other}"},
        "otherLabel": {"value": name}, "otherTmdb": {"value": str(other)},
        "prop": {"value": f"http://www.wikidata.org/entity/{prop}"},
    }
    if src_lang:
        row["srcLang"] = {"value": f"http://www.wikidata.org/entity/{src_lang}"}
    if other_lang:
        row["otherLang"] = {"value": f"http://www.wikidata.org/entity/{other_lang}"}
    return row


# ------------------------------------------------------------------ client


@responses.activate
def test_a_show_related_to_an_owned_film_is_found() -> None:
    """Own Serenity, find Firefly. The direction the measurement said was worth building."""
    # shows batch: two directions, nothing; films batch: two directions, one hit
    for payload in (_sparql(), _sparql(), _sparql(_row(16320, 1437, "Firefly", "P156", "Serenity")), _sparql()):
        responses.add(responses.GET, SPARQL_ENDPOINT, json=payload)

    found = _client().cross_media_for(show_ids=[1], movie_ids=[16320])

    assert len(found) == 1
    assert (found[0].source_type, found[0].target_type) == ("movie", "show")
    assert found[0].target_name == "Firefly" and found[0].relation == "P156"


@responses.activate
def test_queries_are_flat_not_unioned() -> None:
    """The UNION form of this timed out at 65s on a 40-id batch; each half alone took 0.1s."""
    for _ in range(4):
        responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())

    _client().cross_media_for(show_ids=[1], movie_ids=[2])

    queries = [parse_qs(urlparse(c.request.url).query)["query"][0] for c in responses.calls]
    assert len(queries) == 4
    assert all("UNION" not in q for q in queries)


@responses.activate
def test_pornographic_films_are_excluded_in_the_query() -> None:
    """Three of the fourteen films 'based on' an owned show were XXX parodies."""
    for _ in range(4):
        responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())

    _client().cross_media_for(show_ids=[1], movie_ids=[2])

    query = parse_qs(urlparse(responses.calls[0].request.url).query)["query"][0]
    assert "MINUS { ?other wdt:P136 ?excluded ." in query
    assert "wd:Q185529" in query and "wd:Q16254232" in query, "genre and its parody subgenre"


@responses.activate
def test_a_same_title_adaptation_is_kept() -> None:
    """Fargo the film -> Fargo the series is the norm across media, not a remake signature."""
    responses.add(responses.GET, SPARQL_ENDPOINT,
                  json=_sparql(_row(275, 60622, "Fargo", "P144", "Fargo", "Q1860", "Q1860")))
    for _ in range(3):
        responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())

    found = _client().cross_media_for(show_ids=[275], movie_ids=[])

    assert [r.target_name for r in found] == ["Fargo"]


@responses.activate
def test_a_foreign_language_series_based_on_an_owned_film_is_a_remake() -> None:
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())
    responses.add(responses.GET, SPARQL_ENDPOINT,
                  json=_sparql(_row(1, 2, "18 Again", "P144", "17 Again", "Q1860", "Q9176")))
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())

    assert _client().cross_media_for(show_ids=[], movie_ids=[1]) == []


# ------------------------------------------------------------------ service


def _rel(source_type: str, source: int, target_type: str, target: int, name: str,
         prop: str = "P144") -> CrossMediaRelation:
    return CrossMediaRelation(source_type=source_type, source_tmdb_id=source,
                              target_type=target_type, target_tmdb_id=target,
                              target_name=name, relation=prop)


@responses.activate
def test_import_fetches_display_details_once(session: Session) -> None:
    responses.add(responses.GET, f"{TMDB_BASE_URL}/tv/1437",
                  json={"id": 1437, "name": "Firefly", "first_air_date": "2002-09-20",
                        "poster_path": "/ff.jpg"})

    tmdb = TmdbClient("k" * 32, max_requests_per_second=10_000)
    rel = _rel("movie", 16320, "show", 1437, "Firefly", "P156")
    assert cross_media_service.import_relations(session, [rel], tmdb) == (1, 0)
    assert cross_media_service.import_relations(session, [rel], tmdb) == (0, 0)

    row = session.exec(select(CrossMediaMapping)).one()
    assert (row.target_title, row.target_year, row.target_poster_path) == ("Firefly", 2002, "/ff.jpg")
    assert row.confidence == MappingConfidence.CONFIRMED.value
    assert len(responses.calls) == 1, "details fetched once, not on every scan"


def _own_film(session: Session, tmdb_id: int, title: str) -> None:
    session.add(TmdbMovie(tmdb_id=tmdb_id, title=title))
    session.add(LibraryItem(plex_library_key="1", rating_key=f"f{tmdb_id}",
                            item_type=ItemType.MOVIE.value, title=title, year=2005,
                            tmdb_id=tmdb_id, match_source=MatchSource.GUID.value))
    session.commit()


def test_suggestions_route_to_the_other_medium(session: Session) -> None:
    _own_film(session, 16320, "Serenity")
    session.add(CrossMediaMapping(source_type="movie", source_tmdb_id=16320, target_type="show",
                                  target_tmdb_id=1437, target_title="Firefly", target_year=2002,
                                  relation="P156"))
    session.commit()

    shows = cross_media_service.suggestions(session, ItemType.SHOW.value)
    films = cross_media_service.suggestions(session, ItemType.MOVIE.value)

    assert [s.target_title for s in shows] == ["Firefly"]
    assert shows[0].relationships == "precedes Serenity"
    assert films == []


def test_a_target_already_owned_is_not_suggested(session: Session) -> None:
    _own_film(session, 16320, "Serenity")
    session.add(TmdbShow(tmdb_id=1437, name="Firefly"))
    session.add(LibraryItem(plex_library_key="2", rating_key="s1437", item_type="show",
                            title="Firefly", year=2002, tmdb_id=1437, match_source="guid"))
    session.add(CrossMediaMapping(source_type="movie", source_tmdb_id=16320, target_type="show",
                                  target_tmdb_id=1437, target_title="Firefly", relation="P156"))
    session.commit()

    assert cross_media_service.suggestions(session, ItemType.SHOW.value) == []


def test_a_mapping_whose_source_is_no_longer_owned_is_not_suggested(session: Session) -> None:
    """The film left the library; the relation stays recorded but stops applying."""
    session.add(CrossMediaMapping(source_type="movie", source_tmdb_id=16320, target_type="show",
                                  target_tmdb_id=1437, target_title="Firefly", relation="P156"))
    session.commit()

    assert cross_media_service.suggestions(session, ItemType.SHOW.value) == []


# ------------------------------------------------------------------ scan path, discovery ON


@responses.activate
def test_a_tv_scan_runs_cross_media_discovery(session: Session, fixtures_dir) -> None:
    """Runs the joining function, not just its ends -- the lesson from 0.4.1."""
    from app.clients.plex_client import PlexClient
    from app.services import scan_service

    PLEX = "http://plex.test:32400"
    for name, url in [("root.xml", f"{PLEX}/"), ("library.xml", f"{PLEX}/library"),
                      ("library_sections.xml", f"{PLEX}/library/sections"),
                      ("section_2_shows.xml", f"{PLEX}/library/sections/2/all")]:
        responses.add(responses.GET, url, body=(fixtures_dir / "plex" / name).read_text(),
                      content_type="application/xml")
    for tid, name in ((1621, "NCIS"), (44006, "Chicago Fire")):
        responses.add(responses.GET, f"{TMDB_BASE_URL}/tv/{tid}",
                      json={"id": tid, "name": name, "first_air_date": "2003-09-23"})
    # spin-off discovery: nothing; cross-media: one film for NCIS
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())
    responses.add(responses.GET, SPARQL_ENDPOINT,
                  json=_sparql(_row(1621, 777, "NCIS: The Movie", "P2512", "NCIS")))
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())
    responses.add(responses.GET, f"{TMDB_BASE_URL}/movie/777",
                  json={"id": 777, "title": "NCIS: The Movie", "release_date": "2030-01-01",
                        "poster_path": "/n.jpg"})
    _own_film(session, 1, "unrelated")
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())

    session.add(IncludedLibrary(plex_library_key="2", plex_library_name="TV Shows",
                                library_type="show", enabled=True))
    session.commit()

    summary = scan_service.scan_show_libraries(
        session, PlexClient(PLEX, "token"), TmdbClient("k" * 32, max_requests_per_second=10_000),
        wikidata=_client(),
    )

    assert summary.errors == []
    row = session.exec(select(CrossMediaMapping)).one()
    assert (row.source_tmdb_id, row.target_tmdb_id, row.target_title) == (1621, 777, "NCIS: The Movie")


# ------------------------------------------------------------------ page


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            session.add(IncludedLibrary(plex_library_key="2", plex_library_name="TV",
                                        library_type="show", enabled=True))
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def test_the_spinoff_page_lists_shows_from_films_with_a_sonarr_add(client: TestClient) -> None:
    with Session(get_engine()) as session:
        _own_film(session, 16320, "Serenity")
        session.add(LibraryItem(plex_library_key="2", rating_key="s1", item_type="show",
                                title="Some Show", year=2000, tmdb_id=99, match_source="guid"))
        session.add(TmdbShow(tmdb_id=99, name="Some Show"))
        session.add(CrossMediaMapping(source_type="movie", source_tmdb_id=16320, target_type="show",
                                      target_tmdb_id=1437, target_title="Firefly", target_year=2002,
                                      target_poster_path="/ff.jpg", relation="P156"))
        session.commit()

    body = client.get(f"{BASE}/shows").text

    assert "TV from films you own" in body
    assert "precedes Serenity" in body
    assert 'hx-get="/franchisarr/shows/add/1437"' in body
    assert "https://image.tmdb.org/t/p/w92/ff.jpg" in body


def test_the_spinoff_page_lists_films_from_shows_with_a_radarr_add(client: TestClient) -> None:
    with Session(get_engine()) as session:
        session.add(LibraryItem(plex_library_key="2", rating_key="s275", item_type="show",
                                title="Fargo", year=2014, tmdb_id=60622, match_source="guid"))
        session.add(TmdbShow(tmdb_id=60622, name="Fargo"))
        session.add(CrossMediaMapping(source_type="show", source_tmdb_id=60622, target_type="movie",
                                      target_tmdb_id=275, target_title="Fargo", target_year=1996,
                                      relation="P144", confidence="heuristic"))
        session.commit()

    body = client.get(f"{BASE}/shows").text

    assert "Films from shows you own" in body
    assert "based on Fargo" in body and "· possible" in body
    assert 'hx-get="/franchisarr/add/275"' in body
    # and the add dialog can name it, though it is in no owned collection
    assert "Fargo" in client.get(f"{BASE}/add/275").text
