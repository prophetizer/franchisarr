"""Seerr as an add target.

The client against a fake HTTP server, the request cache and what it hides, the request path
through add_service, and the dialogs offering the choice. The API is mocked from the shapes in
Seerr's own OpenAPI document, which Overseerr and Jellyseerr share.
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

URL = "http://seerr.test:5055"
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
def test_test_connection_returns_the_version_and_proves_the_key() -> None:
    responses.add(responses.GET, f"{URL}/api/v1/status", json={"version": "3.4.1"})
    responses.add(responses.GET, f"{URL}/api/v1/auth/me", json={"id": 1, "permissions": 2})

    assert SeerrClient(URL, API).test_connection() == "3.4.1"
    assert [c.request.url.split("/api/v1")[1] for c in responses.calls] == ["/status", "/auth/me"]
    assert all(c.request.headers["X-Api-Key"] == API for c in responses.calls)


@responses.activate
def test_a_wrong_key_fails_the_test_even_though_status_answers() -> None:
    """Measured on a live Seerr 3.4.1: /status is public and answered 200 to a made-up key,
    so a test that stopped there reported success for an instance that refuses every request.
    /auth/me is what actually checks the key."""
    responses.add(responses.GET, f"{URL}/api/v1/status", json={"version": "3.4.1"})
    responses.add(responses.GET, f"{URL}/api/v1/auth/me", status=403, json={"message": "Unauthorized"})

    with pytest.raises(SeerrAuthError) as refused:
        SeerrClient(URL, "x" * 68, label="Seerr").test_connection()
    # The message names the app that refused -- it said "Radarr" until the live test.
    assert "Seerr rejected the API key" in str(refused.value)


@responses.activate
def test_a_rejected_key_and_an_unreachable_server_are_told_apart() -> None:
    responses.add(responses.GET, f"{URL}/api/v1/status", json={"version": "3.4.1"})
    responses.add(responses.GET, f"{URL}/api/v1/auth/me", status=403, json={"message": "no"})
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
def test_listing_requests_pages_through_and_keeps_only_the_handled_ones() -> None:
    responses.add(responses.GET, f"{URL}/api/v1/request",
                  json=_requests_page(*[_req(i) for i in range(1, 101)], more=True))
    responses.add(responses.GET, f"{URL}/api/v1/request",
                  json=_requests_page(_req(500, status=3), _req(1433, media_type="tv", status=2)))

    found = SeerrClient(URL, API).list_requests()

    assert len(found) == 101
    assert ("tv", 1433) in {(r.media_type, r.tmdb_id) for r in found}
    assert 500 not in {r.tmdb_id for r in found}
    assert responses.calls[1].request.params["skip"] == "100"


@responses.activate
def test_all_five_request_statuses_are_sorted_the_way_a_user_would() -> None:
    """Seerr's published spec documents three statuses; the live server returned five
    (MediaRequestStatus: pending, approved, declined, failed, completed). Pending, approved and
    completed are handled. Declined and failed are not -- a failed request never reached an
    *arr, so hiding it would make the film vanish with nothing on its way."""
    responses.add(responses.GET, f"{URL}/api/v1/request", json=_requests_page(
        _req(1, status=1), _req(2, status=2), _req(3, status=3), _req(4, status=4), _req(5, status=5)))

    kept = {r.tmdb_id for r in SeerrClient(URL, API).list_requests()}

    assert kept == {1, 2, 5}


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
    first = seerr_instance_service.create_seerr(session, name="Seerr", url=URL, api_key=API)
    second = seerr_instance_service.create_seerr(session, name="Old one", kind="jellyseerr",
                                                 url="http://j.test:5055", api_key="k" * 30)
    assert first.is_default and not second.is_default
    assert seerr_instance_service.label(second) == "Jellyseerr"


def test_all_three_generations_are_labelled_and_a_new_one_defaults_to_seerr(session: Session) -> None:
    """Jellyseerr became Seerr and Overseerr was archived, but installs still run the older
    two and the API is the same for all of them."""
    made = [seerr_instance_service.create_seerr(session, name=n, url=f"http://{n}.test:5055",
                                                api_key="k" * 30, **k)
            for n, k in [("new", {}), ("old", {"kind": "overseerr"}), ("mid", {"kind": "jellyseerr"})]]

    assert [seerr_instance_service.label(i) for i in made] == ["Seerr", "Overseerr", "Jellyseerr"]
    assert made[0].kind == "seerr"


@responses.activate
def test_refreshing_caches_open_requests_and_they_stop_being_gaps(session: Session) -> None:
    _library_with_gap(session)
    instance = seerr_instance_service.create_seerr(session, name="Seerr", url=URL, api_key=API)
    responses.add(responses.GET, f"{URL}/api/v1/request",
                  json=_requests_page(_req(96), _req(96, status=2), _req(2, media_type="tv")))

    refresh = seerr_instance_service.refresh_instance_cache(session, instance)

    assert refresh.ok and refresh.requests == 2
    assert {(r.media_type, r.tmdb_id) for r in session.exec(select(SeerrRequest))} == {("movie", 96), ("show", 2)}
    assert [m.tmdb_id for m in movie_gap_service.collections_with_gaps(session)[0].missing] == [306]
    assert 2 in tv_spinoff_service.sonarr_known_ids(session)


@responses.activate
def test_an_unreachable_seerr_keeps_its_previous_cache(session: Session) -> None:
    instance = seerr_instance_service.create_seerr(session, name="Seerr", url=URL, api_key=API)
    seerr_instance_service.record_request(session, instance, ItemType.MOVIE.value, 96, 1)
    from requests.exceptions import ConnectionError as RequestsConnectionError

    responses.add(responses.GET, f"{URL}/api/v1/request", body=RequestsConnectionError("refused"))

    refresh = seerr_instance_service.refresh_instance_cache(session, instance)

    assert not refresh.ok
    assert seerr_instance_service.requested_ids(session, ItemType.MOVIE.value) == {96}


@responses.activate
def test_a_request_is_logged_as_a_seerr_request_and_leaves_the_list_at_once(session: Session) -> None:
    _library_with_gap(session)
    instance = seerr_instance_service.create_seerr(session, name="Seerr", url=URL, api_key=API)
    user = User(local_username="admin", is_admin=True)
    session.add(user); session.commit(); session.refresh(user)
    responses.add(responses.POST, f"{URL}/api/v1/request", status=201, json={"id": 9, "status": 1})

    result = add_service.request_via_seerr(session, instance=instance, item_type=ItemType.MOVIE.value,
                                           tmdb_id=96, title="Beverly Hills Cop II", user=user)

    assert result.needs_approval and result.instance_name == "Seerr"
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

    client.post(f"{BASE}/instances/seerr", data={"name": "Seerr", "url": URL, "api_key": API,
                                                "seerr_kind": "seerr"})

    film = client.get(f"{BASE}/add/96").text
    show = client.get(f"{BASE}/shows/add/1433").text
    assert "Request via Seerr" in film and "/franchisarr/add/request" in film
    assert "Request via Seerr" in show and "/franchisarr/shows/add/request" in show
    assert "No Radarr instance is configured" not in film
    page = client.get(f"{BASE}/instances").text
    assert "Seerr" in page and API not in page and API[-4:] in page


@responses.activate
def test_submitting_a_request_reports_the_approval_state_and_the_activity_page_names_seerr(client: TestClient) -> None:
    client.post(f"{BASE}/instances/seerr", data={"name": "Seerr", "url": URL, "api_key": API})
    with Session(get_engine()) as session:
        seerr_id = session.exec(select(seerr_instance_service.SeerrInstance)).one().id
    responses.add(responses.POST, f"{URL}/api/v1/request", status=201, json={"id": 9, "status": 1})

    result = client.post(f"{BASE}/add/request", data={"tmdb_id": 96, "seerr_id": seerr_id}).text

    assert "Requested" in result and "waiting for approval" in result
    assert "Beverly Hills Cop II" in result
    activity = client.get(f"{BASE}/activity").text
    assert "Seerr" in activity


@responses.activate
def test_a_seerr_refusal_is_shown_in_the_dialog(client: TestClient) -> None:
    client.post(f"{BASE}/instances/seerr", data={"name": "Seerr", "url": URL, "api_key": API})
    with Session(get_engine()) as session:
        seerr_id = session.exec(select(seerr_instance_service.SeerrInstance)).one().id
    responses.add(responses.POST, f"{URL}/api/v1/request", status=400, json={"message": "Quota exceeded"})

    result = client.post(f"{BASE}/shows/add/request", data={"tmdb_id": 1433, "seerr_id": seerr_id}).text

    assert "request it" in result and "Quota exceeded" in result
