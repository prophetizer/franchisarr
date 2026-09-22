"""Overseerr / Jellyseerr as an add target.

The client against a fake HTTP server, the request cache and what it hides, the request path
through add_service, and the dialogs offering the choice. Seerr's API is mocked from the shapes
in Overseerr's own OpenAPI document.
"""

from __future__ import annotations

import pytest
import responses
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.clients.seerr_client import SeerrAuthError, SeerrClient, SeerrError, SeerrUnreachableError
from app.db import get_engine
from app.models import (
    ActivityLogEntry, ItemType, LibraryItem, MatchSource, SeerrRequest, TmdbCollection,
    TmdbCollectionMovie, TmdbMovie, TmdbShow, User,
)
from app.services import add_service, movie_gap_service, seerr_instance_service, tv_spinoff_service
from tests.conftest import ensure_server

URL = "http://overseerr.test:5055"
API = "seerr-key-zzz111aaa222bbb333"
COLLECTION = 85861
BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"


def _requests_page(*items, more: bool = False) -> dict:
    return {"pageInfo": {"pages": 2 if more else 1, "pageSize": 100, "results": len(items), "page": 1},
            "results": list(items)}


def _req(tmdb_id: int, *, media_type: str = "movie", status: int = 1) -> dict:
    return {"id": tmdb_id, "status": status, "type": media_type,
            "media": {"id": 1, "tmdbId": tmdb_id, "mediaType": media_type, "status": 2}}


# ------------------------------------------------------------------ client


@responses.activate
def test_test_connection_returns_the_version_and_sends_the_key() -> None:
    responses.add(responses.GET, f"{URL}/api/v1/status", json={"version": "1.33.2"})

    assert SeerrClient(URL, API).test_connection() == "1.33.2"
    assert responses.calls[0].request.headers["X-Api-Key"] == API


@responses.activate
def test_a_rejected_key_and_an_unreachable_server_are_told_apart() -> None:
    responses.add(responses.GET, f"{URL}/api/v1/status", status=403, json={"message": "no"})
    with pytest.raises(SeerrAuthError):
        SeerrClient(URL, API).test_connection()

    responses.reset()
    from requests.exceptions import ConnectionError as RequestsConnectionError

    responses.add(responses.GET, f"{URL}/api/v1/status", body=RequestsConnectionError("refused"))
    with pytest.raises(SeerrUnreachableError):
        SeerrClient(URL, API).test_connection()


@responses.activate
def test_requesting_a_film_posts_the_tmdb_id_and_reports_approval_state() -> None:
    responses.add(responses.POST, f"{URL}/api/v1/request", status=201, json={"id": 42, "status": 1})

    result = SeerrClient(URL, API).request_movie(306)

    assert responses.calls[0].request.body == b'{"mediaType": "movie", "mediaId": 306}'
    assert result.request_id == 42 and result.needs_approval


@responses.activate
def test_requesting_a_series_asks_for_every_season() -> None:
    responses.add(responses.POST, f"{URL}/api/v1/request", status=201, json={"id": 43, "status": 2})

    result = SeerrClient(URL, API).request_series(1433)

    assert b'"seasons": "all"' in responses.calls[0].request.body
    assert not result.needs_approval


@responses.activate
def test_a_seerr_refusal_carries_its_message() -> None:
    responses.add(responses.POST, f"{URL}/api/v1/request", status=400,
                  json={"message": "Request for this media already exists."})

    with pytest.raises(SeerrError, match="already exists"):
        SeerrClient(URL, API).request_movie(306)


@responses.activate
def test_listing_requests_pages_through_and_drops_declined_ones() -> None:
    responses.add(responses.GET, f"{URL}/api/v1/request",
                  json=_requests_page(*[_req(i) for i in range(1, 101)], more=True))
    responses.add(responses.GET, f"{URL}/api/v1/request",
                  json=_requests_page(_req(500, status=3), _req(1433, media_type="tv", status=2)))

    found = SeerrClient(URL, API).list_requests()

    assert len(found) == 101
    assert ("tv", 1433) in {(r.media_type, r.tmdb_id) for r in found}
    assert 500 not in {r.tmdb_id for r in found}
    assert responses.calls[1].request.params["skip"] == "100"


# ------------------------------------------------------------------ cache and gaps


def _library_with_gap(session: Session) -> None:
    session.add(TmdbCollection(tmdb_collection_id=COLLECTION, name="Beverly Hills Cop Collection"))
    for position, (tmdb_id, title) in enumerate(
        [(90, "Beverly Hills Cop"), (96, "Beverly Hills Cop II"), (306, "Beverly Hills Cop III")]
    ):
        session.add(TmdbCollectionMovie(collection_id=COLLECTION, tmdb_movie_id=tmdb_id, title=title,
                                        release_year=1984 + position, release_date=f"{1984 + position}-06-01",
                                        position=position))
    session.add(LibraryItem(server_id=ensure_server(session), library_key="1", item_key="1",
                            item_type=ItemType.MOVIE.value, title="Beverly Hills Cop", year=1984,
                            tmdb_id=90, match_source=MatchSource.GUID.value))
    session.add(TmdbMovie(tmdb_id=90, title="Beverly Hills Cop", collection_id=COLLECTION))
    session.commit()


def test_the_first_seerr_instance_becomes_the_default(session: Session) -> None:
    first = seerr_instance_service.create_seerr(session, name="Overseerr", url=URL, api_key=API)
    second = seerr_instance_service.create_seerr(session, name="Jellyseerr", kind="jellyseerr",
                                                 url="http://j.test:5055", api_key="k" * 30)
    assert first.is_default and not second.is_default
    assert seerr_instance_service.label(second) == "Jellyseerr"


@responses.activate
def test_refreshing_caches_open_requests_and_they_stop_being_gaps(session: Session) -> None:
    _library_with_gap(session)
    instance = seerr_instance_service.create_seerr(session, name="Overseerr", url=URL, api_key=API)
    responses.add(responses.GET, f"{URL}/api/v1/request",
                  json=_requests_page(_req(96), _req(96, status=2), _req(2, media_type="tv")))

    refresh = seerr_instance_service.refresh_instance_cache(session, instance)

    assert refresh.ok and refresh.requests == 2
    assert {(r.media_type, r.tmdb_id) for r in session.exec(select(SeerrRequest))} == {("movie", 96), ("show", 2)}
    assert [m.tmdb_id for m in movie_gap_service.collections_with_gaps(session)[0].missing] == [306]
    assert 2 in tv_spinoff_service.sonarr_known_ids(session)


@responses.activate
def test_an_unreachable_seerr_keeps_its_previous_cache(session: Session) -> None:
    instance = seerr_instance_service.create_seerr(session, name="Overseerr", url=URL, api_key=API)
    seerr_instance_service.record_request(session, instance, ItemType.MOVIE.value, 96, 1)
    from requests.exceptions import ConnectionError as RequestsConnectionError

    responses.add(responses.GET, f"{URL}/api/v1/request", body=RequestsConnectionError("refused"))

    refresh = seerr_instance_service.refresh_instance_cache(session, instance)

    assert not refresh.ok
    assert seerr_instance_service.requested_ids(session, ItemType.MOVIE.value) == {96}


@responses.activate
def test_a_request_is_logged_as_a_seerr_request_and_leaves_the_list_at_once(session: Session) -> None:
    _library_with_gap(session)
    instance = seerr_instance_service.create_seerr(session, name="Overseerr", url=URL, api_key=API)
    user = User(local_username="admin", is_admin=True)
    session.add(user); session.commit(); session.refresh(user)
    responses.add(responses.POST, f"{URL}/api/v1/request", status=201, json={"id": 9, "status": 1})

    result = add_service.request_via_seerr(session, instance=instance, item_type=ItemType.MOVIE.value,
                                           tmdb_id=96, title="Beverly Hills Cop II", user=user)

    assert result.needs_approval and result.instance_name == "Overseerr"
    entry = session.exec(select(ActivityLogEntry)).one()
    assert (entry.target, entry.instance_id, entry.triggered_by) == ("seerr", instance.id, user.id)
    assert [m.tmdb_id for m in movie_gap_service.collections_with_gaps(session)[0].missing] == [306]


# ------------------------------------------------------------------ the pages


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            _library_with_gap(session)
            session.add(TmdbShow(tmdb_id=1433, name="NCIS: Los Angeles", first_air_year=2009))
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def test_the_dialogs_offer_a_request_only_when_a_seerr_is_configured(client: TestClient) -> None:
    assert "Request via" not in client.get(f"{BASE}/add/96").text

    client.post(f"{BASE}/instances/seerr", data={"name": "Overseerr", "url": URL, "api_key": API,
                                                "seerr_kind": "overseerr"})

    film = client.get(f"{BASE}/add/96").text
    show = client.get(f"{BASE}/shows/add/1433").text
    assert "Request via Overseerr" in film and "/franchisarr/add/request" in film
    assert "Request via Overseerr" in show and "/franchisarr/shows/add/request" in show
    assert "No Radarr instance is configured" not in film
    page = client.get(f"{BASE}/instances").text
    assert "Overseerr" in page and API not in page and API[-4:] in page


@responses.activate
def test_submitting_a_request_reports_the_approval_state_and_the_activity_page_names_seerr(client: TestClient) -> None:
    client.post(f"{BASE}/instances/seerr", data={"name": "Overseerr", "url": URL, "api_key": API})
    with Session(get_engine()) as session:
        seerr_id = session.exec(select(seerr_instance_service.SeerrInstance)).one().id
    responses.add(responses.POST, f"{URL}/api/v1/request", status=201, json={"id": 9, "status": 1})

    result = client.post(f"{BASE}/add/request", data={"tmdb_id": 96, "seerr_id": seerr_id}).text

    assert "Requested" in result and "waiting for approval" in result
    assert "Beverly Hills Cop II" in result
    activity = client.get(f"{BASE}/activity").text
    assert "Overseerr" in activity


@responses.activate
def test_a_seerr_refusal_is_shown_in_the_dialog(client: TestClient) -> None:
    client.post(f"{BASE}/instances/seerr", data={"name": "Overseerr", "url": URL, "api_key": API})
    with Session(get_engine()) as session:
        seerr_id = session.exec(select(seerr_instance_service.SeerrInstance)).one().id
    responses.add(responses.POST, f"{URL}/api/v1/request", status=400, json={"message": "Quota exceeded"})

    result = client.post(f"{BASE}/shows/add/request", data={"tmdb_id": 1433, "seerr_id": seerr_id}).text

    assert "request it" in result and "Quota exceeded" in result
