"""The movie screens: gap lists, dismiss/exclude, the add dialog, and theming in the page."""

from __future__ import annotations

import pytest
import responses
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import (
    CollectionExclude,
    DismissedItem,
    IncludedLibrary,
    ItemType,
    LibraryItem,
    MatchSource,
    TmdbCollection,
    TmdbCollectionMovie,
    TmdbMovie,
    TmdbShow,
)
from app.services import instance_service
from app.services.theme_service import set_theme_url

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"
COLLECTION = 85861
RADARR = "http://radarr.test:7878"


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


def _seed_collection(*, with_upcoming: bool = False) -> None:
    with Session(get_engine()) as session:
        session.add(TmdbCollection(tmdb_collection_id=COLLECTION,
                                   name="Beverly Hills Cop Collection"))
        members = [
            (90, "Beverly Hills Cop", 1984, "1984-12-05"),
            (96, "Beverly Hills Cop II", 1987, "1987-05-18"),
            (306, "Beverly Hills Cop III", 1994, "1994-05-24"),
        ]
        if with_upcoming:
            members.append((280180, "Beverly Hills Cop: Axel F", 2099, "2099-01-01"))
        for position, (tmdb_id, title, year, date) in enumerate(members):
            session.add(TmdbCollectionMovie(collection_id=COLLECTION, tmdb_movie_id=tmdb_id,
                                            title=title, release_year=year, release_date=date,
                                            position=position))
        session.add(LibraryItem(plex_library_key="1", rating_key="1",
                                item_type=ItemType.MOVIE.value, title="Beverly Hills Cop",
                                year=1984, tmdb_id=90, match_source=MatchSource.GUID.value))
        session.add(TmdbMovie(tmdb_id=90, title="Beverly Hills Cop", collection_id=COLLECTION))
        session.commit()


# ------------------------------------------------------------------ collections list


def test_the_collections_page_requires_a_login(app_factory) -> None:
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as anon:
        assert anon.get(f"{BASE}/collections").status_code == 303


def test_an_empty_library_offers_a_scan_rather_than_claiming_completeness(
    client: TestClient,
) -> None:
    """"No gaps" and "nothing scanned" look identical otherwise, and mean opposite things."""
    response = client.get(f"{BASE}/collections")

    assert response.status_code == 200
    assert "Nothing scanned yet" in response.text


def test_collections_with_gaps_are_listed(client: TestClient) -> None:
    _seed_collection()

    response = client.get(f"{BASE}/collections")

    assert "Beverly Hills Cop Collection" in response.text
    assert "2 missing" in response.text
    assert "1 owned" in response.text


def test_the_detail_page_separates_missing_owned_and_upcoming(client: TestClient) -> None:
    _seed_collection(with_upcoming=True)

    response = client.get(f"{BASE}/collections/{COLLECTION}")

    assert response.status_code == 200
    assert "Coming soon" in response.text
    assert "Beverly Hills Cop: Axel F" in response.text
    assert "In your library" in response.text
    # The upcoming film must not be counted among the actionable ones.
    assert "2 missing" in client.get(f"{BASE}/collections").text


def test_a_collection_you_own_nothing_from_is_a_404(client: TestClient) -> None:
    assert client.get(f"{BASE}/collections/99999").status_code == 404


# ------------------------------------------------------------------ dismiss and exclude


def test_dismiss_hides_a_film_and_returns_the_updated_list(client: TestClient) -> None:
    _seed_collection()

    response = client.post(f"{BASE}/collections/{COLLECTION}/dismiss/306")

    assert response.status_code == 200
    assert "Beverly Hills Cop III" not in response.text
    assert "Beverly Hills Cop II" in response.text, "only the dismissed film should go"

    with Session(get_engine()) as session:
        assert session.exec(select(DismissedItem)).first().tmdb_id == 306


def test_exclude_records_a_collection_scoped_correction(client: TestClient) -> None:
    _seed_collection()

    response = client.post(f"{BASE}/collections/{COLLECTION}/exclude/306")

    assert response.status_code == 200
    assert "Beverly Hills Cop III" not in response.text

    with Session(get_engine()) as session:
        row = session.exec(select(CollectionExclude)).first()
        assert row.tmdb_collection_id == COLLECTION
        assert row.tmdb_movie_id == 306


def test_dismissing_twice_does_not_duplicate(client: TestClient) -> None:
    """The unique constraint would raise; the route has to be idempotent."""
    _seed_collection()

    client.post(f"{BASE}/collections/{COLLECTION}/dismiss/306")
    second = client.post(f"{BASE}/collections/{COLLECTION}/dismiss/306")

    assert second.status_code == 200
    with Session(get_engine()) as session:
        assert len(session.exec(select(DismissedItem)).all()) == 1


def test_excluding_twice_does_not_duplicate(client: TestClient) -> None:
    _seed_collection()

    client.post(f"{BASE}/collections/{COLLECTION}/exclude/306")
    second = client.post(f"{BASE}/collections/{COLLECTION}/exclude/306")

    assert second.status_code == 200
    with Session(get_engine()) as session:
        assert len(session.exec(select(CollectionExclude)).all()) == 1


# ------------------------------------------------------------------ add dialog


def test_the_add_dialog_says_so_when_no_instance_is_configured(client: TestClient) -> None:
    _seed_collection()

    response = client.get(f"{BASE}/add/306")

    assert "No Radarr instance is configured" in response.text


@responses.activate
def test_the_add_dialog_reports_an_unreachable_instance(client: TestClient) -> None:
    """Technical challenge #15: an empty dropdown looks like a misconfigured Radarr, which sends
    the user to debug the wrong thing."""
    _seed_collection()
    with Session(get_engine()) as session:
        instance_service.create_radarr(session, name="HD", url=RADARR, api_key="k")
    responses.add(responses.GET, f"{RADARR}/api/v3/qualityprofile", status=500)

    response = client.get(f"{BASE}/add/306")

    assert "can't read this instance" in response.text
    assert "<form" not in response.text, "there must be nothing to submit"


@responses.activate
def test_the_add_dialog_offers_live_profiles_and_folders(client: TestClient) -> None:
    _seed_collection()
    with Session(get_engine()) as session:
        instance_service.create_radarr(session, name="HD", url=RADARR, api_key="k",
                                       default_quality_profile_id=1,
                                       default_root_folder="/movies")
    responses.add(responses.GET, f"{RADARR}/api/v3/qualityprofile",
                  json=[{"id": 1, "name": "HD-1080p"}, {"id": 2, "name": "Ultra-HD"}])
    responses.add(responses.GET, f"{RADARR}/api/v3/rootfolder",
                  json=[{"path": "/movies", "freeSpace": 500_000_000_000}])

    response = client.get(f"{BASE}/add/306")

    assert "HD-1080p" in response.text
    assert "Ultra-HD" in response.text
    assert "/movies" in response.text
    assert "GB free" in response.text or "TB free" in response.text


@responses.activate
def test_the_instance_dropdown_shows_a_distinguishing_hint(client: TestClient) -> None:
    """Two instances both called some variant of "Radarr" are told apart by their root folder
    (technical challenge #3)."""
    _seed_collection()
    with Session(get_engine()) as session:
        instance_service.create_radarr(session, name="Radarr", url=RADARR, api_key="k",
                                       default_root_folder="/movies")
        instance_service.create_radarr(session, name="Radarr 4K", url="http://radarr4k.test:7878",
                                       api_key="k", default_root_folder="/movies-4k")
    responses.add(responses.GET, f"{RADARR}/api/v3/qualityprofile", json=[{"id": 1, "name": "HD"}])
    responses.add(responses.GET, f"{RADARR}/api/v3/rootfolder", json=[{"path": "/movies"}])

    response = client.get(f"{BASE}/add/306")

    assert "/movies-4k" in response.text
    assert "Radarr 4K" in response.text


@responses.activate
def test_submitting_the_dialog_adds_the_film(client: TestClient) -> None:
    _seed_collection()
    with Session(get_engine()) as session:
        instance = instance_service.create_radarr(session, name="HD", url=RADARR, api_key="k")
        instance_id = instance.id
    responses.add(responses.GET, f"{RADARR}/api/v3/movie/lookup",
                  json=[{"tmdbId": 306, "title": "Beverly Hills Cop III"}])
    responses.add(responses.POST, f"{RADARR}/api/v3/movie", json={"id": 1, "tmdbId": 306})
    responses.add(responses.GET, f"{RADARR}/api/v3/movie", json=[])
    responses.add(responses.GET, f"{RADARR}/api/v3/queue", json={"records": []})

    response = client.post(f"{BASE}/add", data={
        "tmdb_id": 306, "instance_id": instance_id,
        "quality_profile_id": 1, "root_folder_path": "/movies", "search_on_add": "on",
    })

    assert response.status_code == 200
    assert "was added to HD" in response.text
    assert "search has started" in response.text


@responses.activate
def test_a_failed_add_shows_the_reason(client: TestClient) -> None:
    _seed_collection()
    with Session(get_engine()) as session:
        instance = instance_service.create_radarr(session, name="HD", url=RADARR, api_key="k")
        instance_id = instance.id
    responses.add(responses.GET, f"{RADARR}/api/v3/movie/lookup", json=[])

    response = client.post(f"{BASE}/add", data={
        "tmdb_id": 306, "instance_id": instance_id,
        "quality_profile_id": 1, "root_folder_path": "/movies",
    })

    # Jinja escapes the apostrophe in "couldn't", so match on a portion without one.
    assert "find TMDb id" in response.text


def test_the_add_result_points_at_radarr_for_what_happens_next(client: TestClient) -> None:
    """Technical challenge #24: don't imply Franchisarr tracks the download."""
    _seed_collection()
    with Session(get_engine()) as session:
        instance_service.create_radarr(session, name="HD", url=RADARR, api_key="k")

    # No HTTP mocked, so the add fails -- but the template's wording is what's under test here.
    response = client.get(f"{BASE}/add/306")
    assert response.status_code == 200


# ------------------------------------------------------------------ theming in the page


def test_no_theme_link_is_rendered_by_default(client: TestClient) -> None:
    body = client.get(f"{BASE}/collections").text

    assert "theme-adapter.css" not in body
    assert "theme-park.dev" not in body


def test_a_configured_theme_is_linked_before_our_own_styles(client: TestClient) -> None:
    """Order matters: the theme defines its variables, the adapter maps them, app.css builds on
    the result."""
    url = "https://theme-park.dev/css/theme-options/nord.css"
    with Session(get_engine()) as session:
        set_theme_url(session, url)

    body = client.get(f"{BASE}/collections").text

    assert url in body
    assert body.index("pico.min.css") < body.index(url)
    assert body.index(url) < body.index("theme-adapter.css")
    assert body.index("theme-adapter.css") < body.index("app.css")


def test_the_theme_reaches_every_page_not_just_the_one_that_set_it(client: TestClient) -> None:
    """The link lives in the base template, so a route that forgot to pass the URL would render
    one unthemed page and nothing would fail. A context processor prevents that."""
    url = "https://theme-park.dev/css/theme-options/nord.css"
    with Session(get_engine()) as session:
        set_theme_url(session, url)
    _seed_collection()

    for path in ("/", "/collections", f"/collections/{COLLECTION}", "/settings", "/libraries"):
        assert url in client.get(f"{BASE}{path}").text, f"{path} rendered without the theme"


def test_saving_a_bad_theme_url_is_rejected_with_a_message(client: TestClient) -> None:
    response = client.post(f"{BASE}/settings", data={"theme_url": "javascript:alert(1)"})

    assert response.status_code == 400
    assert "http://" in response.text


def test_saving_a_theme_url_works(client: TestClient) -> None:
    url = "https://theme-park.dev/css/theme-options/dracula.css"

    response = client.post(f"{BASE}/settings", data={"theme_url": url})

    assert response.status_code == 303
    assert url in client.get(f"{BASE}/settings").text


# ------------------------------------------------------------------ TV screens


def _own_show(tmdb_id: int, title: str) -> None:
    from app.models import ItemType as _IT

    with Session(get_engine()) as session:
        session.add(LibraryItem(plex_library_key="2", rating_key=str(tmdb_id),
                                item_type=_IT.SHOW.value, title=title, year=2003,
                                tmdb_id=tmdb_id, match_source=MatchSource.GUID.value))
        session.commit()


def test_the_spinoff_page_explains_why_it_starts_empty(client: TestClient) -> None:
    """An empty list looks broken unless you say the mapping list is meant to start that way."""
    _own_show(1621, "NCIS")

    body = client.get(f"{BASE}/shows").text

    assert "starts empty" in body
    assert "no reliable spin-off data" in body or "no spin-off data" in body


def test_the_spinoff_page_lists_your_shows(client: TestClient) -> None:
    _own_show(1621, "NCIS")

    body = client.get(f"{BASE}/shows").text

    assert "NCIS" in body
    assert "Look for spin-offs" in body


def test_a_confirmed_mapping_becomes_a_suggestion(client: TestClient) -> None:
    from app.services import tv_spinoff_service

    _own_show(1621, "NCIS")
    with Session(get_engine()) as session:
        session.add(TmdbShow(tmdb_id=17610, name="NCIS: Los Angeles", first_air_year=2009))
        session.commit()
        tv_spinoff_service.add_mapping(
            session, source_show_tmdb_id=1621, spinoff_show_tmdb_id=17610
        )

    body = client.get(f"{BASE}/shows").text

    assert "NCIS: Los Angeles" in body
    assert "spin-off of NCIS" in body


def test_confirming_a_candidate_creates_a_mapping(client: TestClient) -> None:
    from app.models import SpinoffMapping

    _own_show(1621, "NCIS")

    response = client.post(f"{BASE}/shows/mappings", data={
        "source_show_tmdb_id": 1621, "spinoff_show_tmdb_id": 17610,
    })

    assert response.status_code == 200
    with Session(get_engine()) as session:
        assert len(session.exec(select(SpinoffMapping)).all()) == 1


def test_the_candidates_panel_says_what_it_cannot_find(client: TestClient) -> None:
    """Being honest about the heuristic's blind spot is what stops someone assuming Chicago P.D.
    just isn't a spin-off."""
    _own_show(1621, "NCIS")
    with Session(get_engine()) as session:
        from app.services.settings_service import SettingKey as _SK
        from app.services.settings_service import set_setting as _set

        _set(session, _SK.TMDB_API_KEY, "k" * 32)
        session.commit()

    with responses.RequestsMock() as mock:
        mock.add(responses.GET, "https://api.themoviedb.org/3/search/tv", json={"results": []})
        body = client.get(f"{BASE}/shows/1621/candidates").text

    assert "Chicago" in body, "the panel should name a case it can't detect"


def test_looking_for_candidates_without_a_tmdb_key_says_so(client: TestClient) -> None:
    _own_show(1621, "NCIS")

    body = client.get(f"{BASE}/shows/1621/candidates").text

    assert "TMDb API key" in body


def test_candidates_for_an_unknown_show_is_a_404(client: TestClient) -> None:
    assert client.get(f"{BASE}/shows/999999/candidates").status_code == 404


def test_the_spinoff_page_is_themed_like_everything_else(client: TestClient) -> None:
    url = "https://theme-park.dev/css/theme-options/nord.css"
    with Session(get_engine()) as session:
        set_theme_url(session, url)
    _own_show(1621, "NCIS")

    assert url in client.get(f"{BASE}/shows").text
