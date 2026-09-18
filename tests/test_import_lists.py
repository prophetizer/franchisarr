"""Import lists: what Franchisarr finds, as JSON Radarr and Sonarr can poll."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.api_keys import generate_api_key
from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import (
    DismissedItem, IncludedLibrary, ItemType, LibraryItem, MatchSource, SpinoffMapping,
    TmdbCollection, TmdbCollectionMovie, TmdbMovie, TmdbShow, User,
)
from app.services.settings_service import SettingKey, set_setting

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"
COLLECTION = 85861


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            session.add(IncludedLibrary(plex_library_key="1", plex_library_name="Movies",
                                        library_type="movie", enabled=True))
            session.commit()
        yield test_client


def _key() -> str:
    with Session(get_engine()) as session:
        user = session.exec(__import__("sqlmodel").select(User)).first()
        key = generate_api_key(session, user); session.commit()
        return key


def _seed_films() -> None:
    with Session(get_engine()) as session:
        session.add(TmdbCollection(tmdb_collection_id=COLLECTION, name="Beverly Hills Cop Collection"))
        for pos, (tid, title, year, avg) in enumerate(((90, "Beverly Hills Cop", 1984, 7.2),
                                                       (96, "Beverly Hills Cop II", 1987, 6.6),
                                                       (306, "Beverly Hills Cop III", 1994, 5.4),
                                                       (99, "Axel F 2", 2030, None))):
            session.add(TmdbCollectionMovie(collection_id=COLLECTION, tmdb_movie_id=tid, title=title,
                                            release_year=year, release_date=f"{year}-06-01", position=pos,
                                            vote_average=avg, vote_count=500 if avg else None))
        session.add(TmdbMovie(tmdb_id=90, title="Beverly Hills Cop", collection_id=COLLECTION))
        session.add(LibraryItem(plex_library_key="1", rating_key="90", item_type="movie", title="Beverly Hills Cop",
                                year=1984, tmdb_id=90, match_source="guid"))
        session.commit()


def test_a_list_needs_a_key_and_takes_it_from_the_query_string(client: TestClient) -> None:
    """Neither *arr can send a header to a list URL."""
    _seed_films()
    assert client.get(f"{BASE}/api/lists/collections.json").status_code == 401
    assert client.get(f"{BASE}/api/lists/collections.json?api_key=nope").status_code == 401

    key = _key()
    response = client.get(f"{BASE}/api/lists/collections.json?api_key={key}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert [f["tmdbId"] for f in response.json()] == [96, 306]
    assert response.json()[0]["title"] == "Beverly Hills Cop II"


def test_a_browser_session_is_not_enough(client: TestClient) -> None:
    """A list URL is for a machine; a cookie in a browser must not turn it into an open door."""
    client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
    assert client.get(f"{BASE}/api/lists/collections.json").status_code == 401


def test_the_household_rating_floor_applies_unless_the_url_overrides_it(client: TestClient) -> None:
    _seed_films(); key = _key()
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.MIN_GAP_RATING, "6"); session.commit()

    assert [f["tmdbId"] for f in client.get(f"{BASE}/api/lists/collections.json?api_key={key}").json()] == [96]
    assert [f["tmdbId"] for f in client.get(f"{BASE}/api/lists/collections.json?api_key={key}&min_rating=0").json()] == [96, 306]
    assert client.get(f"{BASE}/api/lists/collections.json?api_key={key}&min_rating=7").json() == []


def test_upcoming_is_its_own_list_and_optional_in_collections(client: TestClient) -> None:
    _seed_films(); key = _key()

    assert [f["tmdbId"] for f in client.get(f"{BASE}/api/lists/upcoming.json?api_key={key}").json()] == [99]
    assert 99 not in [f["tmdbId"] for f in client.get(f"{BASE}/api/lists/collections.json?api_key={key}").json()]
    assert 99 in [f["tmdbId"] for f in client.get(f"{BASE}/api/lists/collections.json?api_key={key}&include_upcoming=1").json()]


def test_dismissals_apply_to_the_lists(client: TestClient) -> None:
    """A "Not interested" on the page is a "not interested" for Radarr too."""
    _seed_films(); key = _key()
    with Session(get_engine()) as session:
        user = session.exec(__import__("sqlmodel").select(User)).first()
        session.add(DismissedItem(user_id=user.id, item_type=ItemType.MOVIE.value, tmdb_id=306)); session.commit()

    assert [f["tmdbId"] for f in client.get(f"{BASE}/api/lists/collections.json?api_key={key}").json()] == [96]


def test_the_shows_list_carries_tvdb_ids_and_counts_what_it_could_not(client: TestClient) -> None:
    key = _key()
    with Session(get_engine()) as session:
        session.add(IncludedLibrary(plex_library_key="2", plex_library_name="TV", library_type="show", enabled=True))
        session.add(LibraryItem(plex_library_key="2", rating_key="s4614", item_type="show", title="NCIS",
                                year=2003, tmdb_id=4614, match_source="guid"))
        session.add(TmdbShow(tmdb_id=4614, name="NCIS"))
        session.add(TmdbShow(tmdb_id=17610, name="NCIS: Los Angeles", first_air_year=2009, tvdb_id=95441))
        session.add(TmdbShow(tmdb_id=1, name="No TVDB id here", first_air_year=2010))
        session.add(SpinoffMapping(source_show_tmdb_id=4614, spinoff_show_tmdb_id=17610,
                                   source="wikidata", origin_ref="P2512"))
        session.add(SpinoffMapping(source_show_tmdb_id=4614, spinoff_show_tmdb_id=1,
                                   source="wikidata", origin_ref="P2512"))
        session.commit()

    response = client.get(f"{BASE}/api/lists/shows.json?api_key={key}")

    assert response.json() == [{"tvdbId": 95441, "tmdbId": 17610, "title": "NCIS: Los Angeles", "year": 2009,
                                "source": "spin-off", "detail": "spin-off of NCIS"}]
    assert response.headers["x-franchisarr-omitted-without-tvdb-id"] == "1"


def test_an_unknown_list_is_a_404(client: TestClient) -> None:
    assert client.get(f"{BASE}/api/lists/nope.json?api_key={_key()}").status_code == 404


def test_settings_shows_the_urls_and_mints_a_key_once(client: TestClient) -> None:
    client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})

    before = client.get(f"{BASE}/settings").text
    assert "Generate your key" in before and "/api/lists/" not in before, "no URLs until there is a key"

    minted = client.post(f"{BASE}/settings/api-key").text
    assert "shown once" in minted
    assert f"{BASE}/api/lists/films.json?api_key=" in minted

    with Session(get_engine()) as session:
        key = session.exec(__import__("sqlmodel").select(User)).first().api_key
    assert key in minted
    assert key not in client.get(f"{BASE}/settings").text, "never rendered again"
    assert "revokes the old one" in client.get(f"{BASE}/settings").text


def test_the_shows_list_learns_a_missing_show_on_demand_and_caches_it(client: TestClient) -> None:
    """A franchise roster show that never passed through the show cache has no TVDB id yet. The
    list fetches it, once, so Sonarr gets it next poll -- and this poll, if it is quick."""
    import responses as r
    from app.clients.tmdb_client import TMDB_BASE_URL
    from app.models import Franchise, FranchiseMember

    key = _key()
    with Session(get_engine()) as session:
        set_setting(session, SettingKey.TMDB_API_KEY, "k" * 32)
        session.add(IncludedLibrary(plex_library_key="2", plex_library_name="TV", library_type="show", enabled=True))
        session.add(LibraryItem(plex_library_key="2", rating_key="s1855", item_type="show", title="Voyager",
                                year=1995, tmdb_id=1855, match_source="guid"))
        session.add(TmdbShow(tmdb_id=1855, name="Voyager"))
        session.add(Franchise(wikidata_id="Q1092", name="Star Trek", kind="media franchise"))
        session.add(FranchiseMember(franchise_id="Q1092", item_type="show", tmdb_id=1855, title="Voyager", kind="television series"))
        session.add(FranchiseMember(franchise_id="Q1092", item_type="show", tmdb_id=580, title="Deep Space Nine", kind="television series"))
        session.commit()

    with r.RequestsMock() as mock:
        mock.add(r.GET, f"{TMDB_BASE_URL}/tv/580", json={"id": 580, "name": "Star Trek: Deep Space Nine",
                                                          "first_air_date": "1993-01-03",
                                                          "external_ids": {"tvdb_id": 72073, "imdb_id": "tt0106145"}})
        first = client.get(f"{BASE}/api/lists/shows.json?api_key={key}")
        assert [s["tvdbId"] for s in first.json()] == [72073]
        assert len(mock.calls) == 1

        second = client.get(f"{BASE}/api/lists/shows.json?api_key={key}")
        assert [s["tvdbId"] for s in second.json()] == [72073]
        assert len(mock.calls) == 1, "cached; not fetched again"
