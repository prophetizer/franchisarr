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
from tests.conftest import ensure_server

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
            session.add(IncludedLibrary(server_id=ensure_server(session), library_key="1", library_name="Movies",
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
        session.add(LibraryItem(server_id=ensure_server(session), library_key="1", item_key="1",
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
    assert client.get(f"{BASE}/collections/157950").status_code == 404


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
def _own_show(tmdb_id: int, title: str) -> None:
    from app.models import ItemType as _IT

    with Session(get_engine()) as session:
        session.add(LibraryItem(server_id=ensure_server(session), library_key="2", item_key=str(tmdb_id),
                                item_type=_IT.SHOW.value, title=title, year=2003,
                                tmdb_id=tmdb_id, match_source=MatchSource.GUID.value))
        session.commit()


def test_the_spinoff_page_explains_why_it_starts_empty(client: TestClient) -> None:
    """An empty list looks broken unless you say why it is empty. It used to say there was no
    spin-off data to import, which stopped being true when Wikidata discovery landed -- so it
    now points at the thing that fills it, which is running a scan."""
    _own_show(4614, "NCIS")

    body = client.get(f"{BASE}/shows").text

    assert "Wikidata" in body
    assert "run one" in body


def test_the_spinoff_page_does_not_demand_a_click_per_show(client: TestClient) -> None:
    """The per-show search was the only way to see anything, on a library of 656 shows. It is a
    fallback now, not the main route, so it must not be the first thing presented."""
    _own_show(4614, "NCIS")

    body = client.get(f"{BASE}/shows").text

    assert "Search a single show" in body
    assert body.index("Suggested") < body.index("Search a single show")


def test_the_spinoff_page_lists_your_shows(client: TestClient) -> None:
    _own_show(4614, "NCIS")

    body = client.get(f"{BASE}/shows").text

    assert "NCIS" in body
    assert "Look for spin-offs" in body


def test_a_confirmed_mapping_becomes_a_suggestion(client: TestClient) -> None:
    from app.services import tv_spinoff_service

    _own_show(4614, "NCIS")
    with Session(get_engine()) as session:
        session.add(TmdbShow(tmdb_id=17610, name="NCIS: Los Angeles", first_air_year=2009))
        session.commit()
        tv_spinoff_service.add_mapping(
            session, source_show_tmdb_id=4614, spinoff_show_tmdb_id=17610
        )

    body = client.get(f"{BASE}/shows").text

    assert "NCIS: Los Angeles" in body
    assert "spin-off of NCIS" in body


def test_confirming_a_candidate_creates_a_mapping(client: TestClient) -> None:
    from app.models import SpinoffMapping

    _own_show(4614, "NCIS")

    response = client.post(f"{BASE}/shows/mappings", data={
        "source_show_tmdb_id": 4614, "spinoff_show_tmdb_id": 17610,
    })

    assert response.status_code == 200
    with Session(get_engine()) as session:
        assert len(session.exec(select(SpinoffMapping)).all()) == 1


def test_the_candidates_panel_says_what_it_cannot_find(client: TestClient) -> None:
    """Being honest about the heuristic's blind spot is what stops someone assuming Chicago P.D.
    just isn't a spin-off."""
    _own_show(4614, "NCIS")
    with Session(get_engine()) as session:
        from app.services.settings_service import SettingKey as _SK
        from app.services.settings_service import set_setting as _set

        _set(session, _SK.TMDB_API_KEY, "k" * 32)
        session.commit()

    with responses.RequestsMock() as mock:
        mock.add(responses.GET, "https://api.themoviedb.org/3/search/tv", json={"results": []})
        body = client.get(f"{BASE}/shows/4614/candidates").text

    assert "Chicago" in body, "the panel should name a case it can't detect"


def test_looking_for_candidates_without_a_tmdb_key_says_so(client: TestClient) -> None:
    _own_show(4614, "NCIS")

    body = client.get(f"{BASE}/shows/4614/candidates").text

    assert "TMDb API key" in body


def test_candidates_for_an_unknown_show_is_a_404(client: TestClient) -> None:
    assert client.get(f"{BASE}/shows/999999/candidates").status_code == 404

def test_saving_a_valid_schedule(client: TestClient) -> None:
    response = client.post(f"{BASE}/settings/schedule", data={"scan_schedule_cron": "0 3 * * *"})

    assert response.status_code == 303
    body = client.get(f"{BASE}/settings").text
    assert "0 3 * * *" in body
    assert "Next scheduled scan" in body


def test_saving_a_bad_schedule_is_rejected_with_an_explanation(client: TestClient) -> None:
    response = client.post(f"{BASE}/settings/schedule", data={"scan_schedule_cron": "nonsense"})

    assert response.status_code == 400
    assert "valid cron expression" in response.text


def test_clearing_the_schedule_is_allowed(client: TestClient) -> None:
    client.post(f"{BASE}/settings/schedule", data={"scan_schedule_cron": "0 3 * * *"})

    response = client.post(f"{BASE}/settings/schedule", data={"scan_schedule_cron": ""})

    assert response.status_code == 303
    assert "only scan when you ask" in client.get(f"{BASE}/settings").text


def test_turning_scheduling_on_primes_the_backlog(client: TestClient) -> None:
    """Otherwise the first scheduled run announces every gap that was already there."""
    from app.models import SeenGap

    _seed_collection()

    client.post(f"{BASE}/settings/schedule", data={"scan_schedule_cron": "0 3 * * *"})

    with Session(get_engine()) as session:
        assert session.exec(select(SeenGap)).all(), "existing gaps should be marked as seen"


def test_saving_a_webhook(client: TestClient) -> None:
    response = client.post(f"{BASE}/settings/webhook", data={
        "webhook_url": "https://hooks.example.com/abc", "webhook_format": "discord",
    })

    assert response.status_code == 303
    body = client.get(f"{BASE}/settings").text
    assert "hooks.example.com" in body


def test_a_saved_notification_url_is_redacted_from_logs_from_then_on(app_factory) -> None:
    """A Discord webhook URL lets anyone post to the channel and an Apprise URL carries the
    service token, so saving one registers it with the log redactor -- and so does boot."""
    from app.logging_config import clear_secrets, redact

    url = "tgram://123456:secret-bot-token-zzz/9876"
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD); session.commit()
        client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        client.post(f"{BASE}/settings/webhook", data={"webhook_url": url, "webhook_format": "apprise"})
        assert "secret-bot-token" not in redact(f"sending to {url}")

    # And a restart re-registers what is stored.
    clear_secrets()
    assert "secret-bot-token" in redact(url)
    with TestClient(app_factory(BASE).app):
        assert "secret-bot-token" not in redact(url)


@responses.activate
def test_the_test_button_sends_one_and_reports_the_result(client: TestClient) -> None:
    responses.add(responses.POST, "https://hooks.example.com/abc", status=204)

    response = client.post(f"{BASE}/settings/webhook", data={
        "webhook_url": "https://hooks.example.com/abc",
        "webhook_format": "discord", "test": "1",
    })

    assert response.status_code == 200
    assert "Saved" in response.text


@responses.activate
def test_a_failing_test_webhook_says_so(client: TestClient) -> None:
    responses.add(responses.POST, "https://hooks.example.com/abc", status=404)

    response = client.post(f"{BASE}/settings/webhook", data={
        "webhook_url": "https://hooks.example.com/abc",
        "webhook_format": "discord", "test": "1",
    })

    # Jinja escapes the apostrophe, so match a portion without one.
    assert "deliver the test" in response.text


# ------------------------------------------------------------------ artwork


def test_a_collection_card_shows_its_poster(client: TestClient) -> None:
    _seed_collection()
    with Session(get_engine()) as session:
        collection = session.get(TmdbCollection, COLLECTION)
        collection.poster_path = "/collection-poster.jpg"
        session.add(collection)
        session.commit()

    body = client.get(f"{BASE}/collections").text

    assert "https://image.tmdb.org/t/p/w185/collection-poster.jpg" in body, "the compact card uses the small size"


def test_missing_films_show_a_thumbnail(client: TestClient) -> None:
    _seed_collection()
    with Session(get_engine()) as session:
        from sqlmodel import col

        member = session.exec(
            select(TmdbCollectionMovie).where(col(TmdbCollectionMovie.tmdb_movie_id) == 96)
        ).first()
        member.poster_path = "/film-poster.jpg"
        session.add(member)
        session.commit()

    body = client.get(f"{BASE}/collections/{COLLECTION}").text

    assert "https://image.tmdb.org/t/p/w92/film-poster.jpg" in body


def test_a_collection_with_no_artwork_renders_without_a_broken_image(
    client: TestClient,
) -> None:
    """TMDb doesn't have a poster for everything, and an <img> with an empty src shows a broken
    icon rather than nothing."""
    _seed_collection()

    body = client.get(f"{BASE}/collections").text

    assert "<img" not in body.split('class="collection-grid')[1].split("</article>")[0], "no <img> for a card without art"
    assert 'collection-poster--empty' in body, "a placeholder keeps the card's text column aligned"
    assert "image.tmdb.org" not in body


def test_posters_carry_dimensions_so_the_layout_does_not_jump(client: TestClient) -> None:
    """A grid of a hundred cards would otherwise reflow repeatedly as images arrive."""
    _seed_collection()
    with Session(get_engine()) as session:
        collection = session.get(TmdbCollection, COLLECTION)
        collection.poster_path = "/p.jpg"
        session.add(collection)
        session.commit()

    body = client.get(f"{BASE}/collections").text

    assert 'width="92"' in body and 'height="138"' in body
    assert 'loading="lazy"' in body


def test_artwork_can_be_turned_off_entirely(client: TestClient, monkeypatch) -> None:
    """The only thing on these pages not served by the user's own server, so there is a switch."""
    monkeypatch.setenv("SHOW_ARTWORK", "false")
    _seed_collection()
    with Session(get_engine()) as session:
        collection = session.get(TmdbCollection, COLLECTION)
        collection.poster_path = "/p.jpg"
        session.add(collection)
        session.commit()

    body = client.get(f"{BASE}/collections").text

    assert "image.tmdb.org" not in body


def test_a_collection_with_a_logo_shows_the_wordmark_instead_of_the_title(
    client: TestClient,
) -> None:
    _seed_collection()
    with Session(get_engine()) as session:
        collection = session.get(TmdbCollection, COLLECTION)
        collection.logo_url = "https://assets.fanart.tv/fanart/bhc-logo.png"
        collection.backdrop_path = "/backdrop.jpg"
        session.add(collection)
        session.commit()

    body = client.get(f"{BASE}/collections/{COLLECTION}").text

    assert "https://assets.fanart.tv/fanart/bhc-logo.png" in body
    assert "https://image.tmdb.org/t/p/w1280/backdrop.jpg" in body
    assert "has-backdrop" in body


def test_the_logo_keeps_the_collection_name_as_its_alt_text(client: TestClient) -> None:
    """The wordmark replaces the heading visually, so without this a screen reader gets no
    heading at all."""
    _seed_collection()
    with Session(get_engine()) as session:
        collection = session.get(TmdbCollection, COLLECTION)
        collection.logo_url = "https://assets.fanart.tv/fanart/bhc-logo.png"
        session.add(collection)
        session.commit()

    body = client.get(f"{BASE}/collections/{COLLECTION}").text

    assert 'alt="Beverly Hills Cop Collection"' in body


def test_without_a_logo_the_heading_is_the_name_in_text(client: TestClient) -> None:
    """No fanart key is the default state, so this is the path most installs take."""
    _seed_collection()

    body = client.get(f"{BASE}/collections/{COLLECTION}").text

    assert "<h1>Beverly Hills Cop Collection</h1>" in body
    assert "collection-logo" not in body


def test_turning_artwork_off_removes_the_fanart_logo_too(
    client: TestClient, monkeypatch
) -> None:
    """SHOW_ARTWORK is a promise that nothing is fetched from elsewhere; one stray image from a
    second CDN would quietly break it."""
    monkeypatch.setenv("SHOW_ARTWORK", "false")
    _seed_collection()
    with Session(get_engine()) as session:
        collection = session.get(TmdbCollection, COLLECTION)
        collection.logo_url = "https://assets.fanart.tv/fanart/bhc-logo.png"
        collection.backdrop_path = "/backdrop.jpg"
        session.add(collection)
        session.commit()

    body = client.get(f"{BASE}/collections/{COLLECTION}").text

    assert "fanart.tv" not in body
    assert "image.tmdb.org" not in body
    assert "<h1>Beverly Hills Cop Collection</h1>" in body


def test_the_home_page_offers_a_scan(client: TestClient) -> None:
    """Scanning is what every other page depends on, and it used to be reachable only from the
    collections page — so on a fresh install the primary action was somewhere else entirely."""
    body = client.get(f"{BASE}/").text

    assert 'hx-post="/franchisarr/scan"' in body
    assert "Scan my library" in body


def test_the_spinoff_page_offers_a_scan_when_it_has_nothing(client: TestClient) -> None:
    """It is the page that tells you spin-offs come from a scan, so it has to let you run one."""
    _own_show(4614, "NCIS")

    body = client.get(f"{BASE}/shows").text

    assert 'hx-post="/franchisarr/scan"' in body


def test_every_page_with_a_scan_button_shows_its_progress(client: TestClient) -> None:
    """Without the status region the button posts into nothing and the page looks inert — which
    is exactly what 'I clicked it and nothing happened' looks like."""
    _own_show(4614, "NCIS")

    for path in ("/", "/shows", "/collections"):
        body = client.get(f"{BASE}{path}").text
        assert 'id="scan-status"' in body, f"{path} has no scan status region"


def _seed_spinoff(
    *, poster: str | None = None, imdb: str | None = None, tvdb: int | None = None
) -> None:
    from app.models import SpinoffMapping, TmdbShow

    _own_show(4614, "NCIS")
    with Session(get_engine()) as session:
        session.add(TmdbShow(tmdb_id=17610, name="NCIS: Los Angeles", first_air_year=2009,
                             poster_path=poster, imdb_id=imdb, tvdb_id=tvdb))
        session.add(SpinoffMapping(source_show_tmdb_id=4614, spinoff_show_tmdb_id=17610))
        session.commit()


def test_a_spinoff_suggestion_shows_its_poster(client: TestClient) -> None:
    _seed_spinoff(poster="/la.jpg")

    body = client.get(f"{BASE}/shows").text

    assert "https://image.tmdb.org/t/p/w92/la.jpg" in body


def test_a_spinoff_suggestion_links_to_where_you_can_see_what_it_is(client: TestClient) -> None:
    """A title and a year cannot tell "Ghosts" from "Ghosts"; a link to IMDb or TVDB can."""
    _seed_spinoff(imdb="tt1355642", tvdb=95441)

    body = client.get(f"{BASE}/shows").text

    assert 'href="https://www.imdb.com/title/tt1355642/"' in body
    assert 'href="https://www.thetvdb.com/dereferrer/series/95441"' in body
    assert 'href="https://www.themoviedb.org/tv/17610"' in body


def test_links_are_only_offered_for_ids_tmdb_actually_had(client: TestClient) -> None:
    """A link to imdb.com/title/None/ is worse than no link."""
    _seed_spinoff()

    body = client.get(f"{BASE}/shows").text

    assert "imdb.com" not in body
    assert "thetvdb.com" not in body
    assert 'href="https://www.themoviedb.org/tv/17610"' in body, "TMDb is always known"


def test_outbound_show_links_open_safely(client: TestClient) -> None:
    _seed_spinoff(imdb="tt1")

    body = client.get(f"{BASE}/shows").text
    link = body[body.index("imdb.com"):body.index("imdb.com") + 120]

    assert 'rel="noopener noreferrer"' in link


# ------------------------------------------------------------------ ratings


def _rate_member(tmdb_id: int, average: float, count: int = 500) -> None:
    from sqlmodel import col

    with Session(get_engine()) as session:
        row = session.exec(
            select(TmdbCollectionMovie).where(col(TmdbCollectionMovie.tmdb_movie_id) == tmdb_id)
        ).one()
        row.vote_average, row.vote_count = average, count
        session.add(row)
        session.commit()


def test_missing_films_show_their_rating(client: TestClient) -> None:
    _seed_collection()
    _rate_member(96, 6.6, count=1234)

    body = client.get(f"{BASE}/collections/{COLLECTION}").text

    assert "★ 6.6" in body
    assert "1,234 votes" in body


def test_setting_the_rating_filter_hides_and_explains(client: TestClient) -> None:
    _seed_collection()
    _rate_member(96, 7.0)
    _rate_member(306, 5.0)

    response = client.post(f"{BASE}/collections/rating-filter", data={"min_rating": "6"})
    assert response.status_code == 303

    page = client.get(f"{BASE}/collections").text
    assert "1 film hidden" in page
    assert 'value="6"' in page

    detail = client.get(f"{BASE}/collections/{COLLECTION}").text
    assert "1 film hidden by your" in detail
    assert "Add anyway" in detail


def test_the_sort_toggle_is_shown_and_honoured(client: TestClient) -> None:
    _seed_collection()

    page = client.get(f"{BASE}/collections").text
    assert "<strong>rating</strong>" in page
    assert 'href="/franchisarr/collections?sort=name"' in page

    page = client.get(f"{BASE}/collections?sort=name").text
    assert "<strong>name</strong>" in page



def test_suggestions_say_how_the_show_relates(client: TestClient) -> None:
    """"Follows" and "precedes" are different facts from "spin-off of", and Wikidata states
    which. A flat "spin-off of" made 1923 -> Yellowstone read backwards."""
    from app.models import SpinoffMapping, TmdbShow

    _own_show(157744, "1923")
    with Session(get_engine()) as session:
        session.add(TmdbShow(tmdb_id=73586, name="Yellowstone", first_air_year=2018))
        session.add(TmdbShow(tmdb_id=118357, name="1883", first_air_year=2021))
        session.add(SpinoffMapping(source_show_tmdb_id=157744, spinoff_show_tmdb_id=73586,
                                   source="wikidata", origin_ref="P155"))
        session.add(SpinoffMapping(source_show_tmdb_id=157744, spinoff_show_tmdb_id=118357,
                                   source="wikidata", origin_ref="P156"))
        session.commit()

    body = client.get(f"{BASE}/shows").text

    assert "follows 1923" in body
    assert "precedes 1923" in body
    assert "· possible" not in body, "succession is a precise statement, not a guess"


def test_a_show_related_to_several_owned_ones_is_listed_once(client: TestClient) -> None:
    """Dexter comes before three shows in the library. That is one thing to add."""
    from app.models import SpinoffMapping, TmdbShow

    for tid, name in ((1, "Dexter: New Blood"), (2, "Dexter: Original Sin"), (3, "Dexter: Resurrection")):
        _own_show(tid, name)
    with Session(get_engine()) as session:
        session.add(TmdbShow(tmdb_id=1405, name="Dexter", first_air_year=2006))
        for tid in (1, 2, 3):
            session.add(SpinoffMapping(source_show_tmdb_id=tid, spinoff_show_tmdb_id=1405,
                                       source="wikidata", origin_ref="P156"))
        session.commit()

    body = client.get(f"{BASE}/shows").text

    assert body.count(f'/shows/add/1405"') == 1, "one row, one Add button"
    assert ("precedes Dexter: New Blood, Dexter: Original Sin and Dexter: Resurrection"
            in body)
