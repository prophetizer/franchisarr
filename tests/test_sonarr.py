"""Sonarr client, instances, and adding shows.

The monitor-mode translation gets the most attention here. Technical challenge #22 warned that
the friendly labels wouldn't map 1:1 to Sonarr's enum, and against a real Sonarr 4.0.19 that
turned out to be true for two of the three -- so sending our stored values verbatim would have
failed silently on most adds.
"""

from __future__ import annotations

import json

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError
from sqlmodel import Session, select

from app.clients.sonarr_client import (
    MONITOR_MODE_TO_SONARR,
    SeriesAlreadyAddedError,
    SonarrAuthError,
    SonarrClient,
    SonarrError,
    SonarrUnreachableError,
    to_sonarr_monitor,
)
from app.models import (
    ActivityLogEntry,
    ItemType,
    LibraryItem,
    MatchSource,
    MonitorMode,
    SonarrInstance,
    SonarrSeries,
    SpinoffMapping,
    TmdbShow,
    User,
)
from app.services import add_service, sonarr_instance_service as svc, tv_spinoff_service
from app.services.settings_service import SettingKey, set_setting

URL = "http://sonarr.test:8989"
ANIME = "http://sonarr-anime.test:8989"
NCIS = 4614
NCIS_LA = 17610


def _client() -> SonarrClient:
    return SonarrClient(URL, "sonarr-key")


def _instance(session: Session, name: str = "TV", url: str = URL, **kwargs) -> SonarrInstance:
    return svc.create_sonarr(session, name=name, url=url, api_key=f"key-{name}", **kwargs)


def _user(session: Session) -> User:
    user = User(local_username="admin", is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# ------------------------------------------------------------------ monitor modes


def test_the_friendly_modes_map_to_sonarrs_actual_enum() -> None:
    """Confirmed against a real Sonarr 4.0.19 and its MonitorTypes source."""
    assert MONITOR_MODE_TO_SONARR == {
        "all": "all",
        "future_only": "future",
        "first_season": "firstSeason",
    }


def test_two_of_the_three_modes_would_be_rejected_if_sent_verbatim() -> None:
    """The whole reason challenge #22 exists: the names differ, so a passthrough breaks."""
    assert to_sonarr_monitor(MonitorMode.FUTURE_ONLY.value) != MonitorMode.FUTURE_ONLY.value
    assert to_sonarr_monitor(MonitorMode.FIRST_SEASON.value) != MonitorMode.FIRST_SEASON.value
    assert to_sonarr_monitor(MonitorMode.ALL.value) == MonitorMode.ALL.value


def test_an_unknown_mode_falls_back_to_all_rather_than_being_sent() -> None:
    """Sonarr rejects anything outside its enum, so a bad value must not reach it."""
    assert to_sonarr_monitor("nonsense") == "all"


@responses.activate
@pytest.mark.parametrize(
    ("stored", "expected"),
    [("all", "all"), ("future_only", "future"), ("first_season", "firstSeason")],
)
def test_the_add_sends_the_translated_value(stored: str, expected: str) -> None:
    responses.add(responses.GET, f"{URL}/api/v3/series/lookup",
                  json=[{"tmdbId": NCIS_LA, "title": "NCIS: Los Angeles", "tvdbId": 1}])
    responses.add(responses.POST, f"{URL}/api/v3/series", json={"id": 1, "tmdbId": NCIS_LA})

    _client().add_series(NCIS_LA, quality_profile_id=1, root_folder_path="/tv",
                         monitor_mode=stored)

    body = json.loads(responses.calls[-1].request.body)
    assert body["addOptions"]["monitor"] == expected


# ------------------------------------------------------------------ client basics


@responses.activate
def test_test_connection_returns_the_version() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/system/status", json={"version": "4.0.19.2979"})

    assert _client().test_connection() == "4.0.19.2979"


@responses.activate
def test_a_bad_api_key_is_named_as_such() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/system/status", status=401)

    with pytest.raises(SonarrAuthError):
        _client().test_connection()


@responses.activate
def test_an_unreachable_instance_is_distinguishable() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/system/status",
                  body=RequestsConnectionError("refused"))

    with pytest.raises(SonarrUnreachableError):
        _client().test_connection()


@responses.activate
def test_an_error_never_contains_the_api_key() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/system/status",
                  body=RequestsConnectionError("failed with key sonarr-key"))

    with pytest.raises(SonarrError) as exc_info:
        _client().test_connection()

    assert "sonarr-key" not in str(exc_info.value)


@responses.activate
def test_series_without_a_tmdb_id_are_still_read() -> None:
    """Sonarr tracks some series it has no TMDb id for; the client shouldn't choke on them."""
    responses.add(responses.GET, f"{URL}/api/v3/series", json=[
        {"tmdbId": NCIS, "tvdbId": 72108, "title": "NCIS"},
        {"tvdbId": 999, "title": "Something Obscure"},
    ])

    series = _client().series()

    assert len(series) == 2
    assert series[1].tmdb_id is None


@responses.activate
def test_adding_something_sonarr_already_has_is_its_own_error() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/series/lookup",
                  json=[{"id": 5, "tmdbId": NCIS_LA, "title": "NCIS: Los Angeles"}])

    with pytest.raises(SeriesAlreadyAddedError):
        _client().add_series(NCIS_LA, quality_profile_id=1, root_folder_path="/tv")


@responses.activate
def test_sonarrs_own_description_is_preserved_in_the_add() -> None:
    responses.add(responses.GET, f"{URL}/api/v3/series/lookup", json=[
        {"tmdbId": NCIS_LA, "tvdbId": 83123, "title": "NCIS: Los Angeles",
         "titleSlug": "ncis-los-angeles", "images": [], "seasons": [{"seasonNumber": 1}]},
    ])
    responses.add(responses.POST, f"{URL}/api/v3/series", json={"id": 1, "tmdbId": NCIS_LA})

    _client().add_series(NCIS_LA, quality_profile_id=1, root_folder_path="/tv")

    body = json.loads(responses.calls[-1].request.body)
    assert body["titleSlug"] == "ncis-los-angeles"
    assert body["seasons"] == [{"seasonNumber": 1}]
    assert body["seasonFolder"] is True


# ------------------------------------------------------------------ instances


def test_the_first_instance_becomes_the_default(session: Session) -> None:
    assert _instance(session).is_default is True


def test_a_users_last_choice_beats_the_default(session: Session) -> None:
    tv = _instance(session, "TV")
    anime = _instance(session, "Anime", ANIME)
    svc.set_default(session, anime.id)
    user = _user(session)

    svc.remember_choice(session, user, tv.id)

    assert svc.preferred_instance(session, user).id == tv.id


def test_deleting_an_instance_removes_its_cached_series(session: Session) -> None:
    instance = _instance(session)
    session.add(SonarrSeries(instance_id=instance.id, tmdb_id=NCIS, title="NCIS"))
    session.commit()

    svc.delete_sonarr(session, instance.id)

    assert session.exec(select(SonarrSeries)).all() == []


@responses.activate
def test_a_refresh_survives_the_same_series_coming_back(session: Session) -> None:
    """The delete-then-insert ordering bug the Radarr side hit; the same shape exists here."""
    instance = _instance(session)
    for tmdb_id in (1, 2, 3):
        session.add(SonarrSeries(instance_id=instance.id, tmdb_id=tmdb_id, title="x"))
    session.commit()

    responses.add(responses.GET, f"{URL}/api/v3/series",
                  json=[{"tmdbId": i, "title": f"Show {i}"} for i in (1, 2, 3, 4)])
    responses.add(responses.GET, f"{URL}/api/v3/queue", json={"records": []})

    result = svc.refresh_instance_cache(session, instance)

    assert result.ok is True
    assert {row.tmdb_id for row in session.exec(select(SonarrSeries)).all()} == {1, 2, 3, 4}


@responses.activate
def test_an_unreachable_instance_keeps_its_cache(session: Session) -> None:
    instance = _instance(session)
    session.add(SonarrSeries(instance_id=instance.id, tmdb_id=NCIS, title="NCIS"))
    session.commit()
    responses.add(responses.GET, f"{URL}/api/v3/series", status=500)

    result = svc.refresh_instance_cache(session, instance)

    assert result.ok is False
    assert len(session.exec(select(SonarrSeries)).all()) == 1


@responses.activate
def test_series_with_no_tmdb_id_are_not_cached(session: Session) -> None:
    """They can't be matched against TMDb-keyed suggestions, so caching them achieves nothing."""
    instance = _instance(session)
    responses.add(responses.GET, f"{URL}/api/v3/series", json=[
        {"tmdbId": NCIS, "title": "NCIS"}, {"tvdbId": 1, "title": "No TMDb id"},
    ])
    responses.add(responses.GET, f"{URL}/api/v3/queue", json={"records": []})

    result = svc.refresh_instance_cache(session, instance)

    assert result.series == 1


# ------------------------------------------------------------------ the diff


def _own_show(session: Session, tmdb_id: int, title: str) -> None:
    session.add(LibraryItem(plex_library_key="2", rating_key=str(tmdb_id),
                            item_type=ItemType.SHOW.value, title=title, year=2003,
                            tmdb_id=tmdb_id, match_source=MatchSource.GUID.value))
    session.commit()


def test_a_show_already_in_sonarr_is_not_suggested(session: Session) -> None:
    _own_show(session, NCIS, "NCIS")
    tv_spinoff_service.add_mapping(session, source_show_tmdb_id=NCIS,
                                   spinoff_show_tmdb_id=NCIS_LA)
    instance = _instance(session)
    session.add(SonarrSeries(instance_id=instance.id, tmdb_id=NCIS_LA, title="NCIS: LA"))
    session.commit()

    assert tv_spinoff_service.missing_spinoffs(session) == []


def test_sonarr_instances_are_independent_by_default(session: Session) -> None:
    _own_show(session, NCIS, "NCIS")
    tv_spinoff_service.add_mapping(session, source_show_tmdb_id=NCIS,
                                   spinoff_show_tmdb_id=NCIS_LA)
    tv = _instance(session, "TV")
    anime = _instance(session, "Anime", ANIME)
    session.add(SonarrSeries(instance_id=tv.id, tmdb_id=NCIS_LA, title="NCIS: LA"))
    session.commit()

    from_anime = tv_spinoff_service.missing_spinoffs(session, sonarr_instance_id=anime.id)

    assert len(from_anime) == 1


def test_cross_instance_dedup_applies_to_shows_too(session: Session) -> None:
    _own_show(session, NCIS, "NCIS")
    tv_spinoff_service.add_mapping(session, source_show_tmdb_id=NCIS,
                                   spinoff_show_tmdb_id=NCIS_LA)
    tv = _instance(session, "TV")
    anime = _instance(session, "Anime", ANIME)
    session.add(SonarrSeries(instance_id=tv.id, tmdb_id=NCIS_LA, title="NCIS: LA"))
    set_setting(session, SettingKey.CROSS_INSTANCE_DEDUP, "true")
    session.commit()

    assert tv_spinoff_service.missing_spinoffs(session, sonarr_instance_id=anime.id) == []


def test_sonarr_alone_does_not_create_a_suggestion_source(session: Session) -> None:
    """Sources come from Plex. Otherwise adding one show would make its franchise a source."""
    tv_spinoff_service.add_mapping(session, source_show_tmdb_id=NCIS,
                                   spinoff_show_tmdb_id=NCIS_LA)
    instance = _instance(session)
    session.add(SonarrSeries(instance_id=instance.id, tmdb_id=NCIS, title="NCIS"))
    session.commit()

    assert tv_spinoff_service.missing_spinoffs(session) == []


# ------------------------------------------------------------------ adding


@responses.activate
def test_adding_a_show_logs_it_and_remembers_the_monitor_mode(session: Session) -> None:
    instance = _instance(session, "TV", default_quality_profile_id=1, default_root_folder="/tv")
    user = _user(session)
    responses.add(responses.GET, f"{URL}/api/v3/series/lookup",
                  json=[{"tmdbId": NCIS_LA, "title": "NCIS: Los Angeles"}])
    responses.add(responses.POST, f"{URL}/api/v3/series",
                  json={"id": 1, "tmdbId": NCIS_LA, "title": "NCIS: Los Angeles"})
    responses.add(responses.GET, f"{URL}/api/v3/series", json=[])
    responses.add(responses.GET, f"{URL}/api/v3/queue", json={"records": []})

    result = add_service.add_series(
        session, instance=instance, tmdb_id=NCIS_LA, user=user, monitor_mode="first_season"
    )

    assert result.title == "NCIS: Los Angeles"
    entry = session.exec(select(ActivityLogEntry)).first()
    assert entry.item_type == ItemType.SHOW.value
    assert entry.tmdb_id == NCIS_LA

    session.refresh(instance)
    assert instance.default_monitor_mode == "first_season", "the choice becomes the next default"
    session.refresh(user)
    assert user.last_sonarr_instance_id == instance.id


def test_adding_without_a_profile_is_refused(session: Session) -> None:
    instance = _instance(session, "TV", default_root_folder="/tv")

    with pytest.raises(add_service.AddFailed) as exc_info:
        add_service.add_series(session, instance=instance, tmdb_id=NCIS_LA)

    assert "quality profile" in str(exc_info.value)


@responses.activate
def test_a_failed_add_records_no_activity(session: Session) -> None:
    instance = _instance(session, "TV", default_quality_profile_id=1, default_root_folder="/tv")
    responses.add(responses.GET, f"{URL}/api/v3/series/lookup", json=[])

    with pytest.raises(add_service.AddFailed):
        add_service.add_series(session, instance=instance, tmdb_id=NCIS_LA)

    assert session.exec(select(ActivityLogEntry)).all() == []


# ------------------------------------------------------------------ env bootstrap


def test_env_seeds_a_first_sonarr_instance(session: Session, monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("SONARR_URL", URL)
    monkeypatch.setenv("SONARR_API_KEY", "from-compose")

    instance = svc.seed_sonarr_from_env(session, get_settings())

    assert instance is not None
    assert instance.is_default is True


def test_env_does_not_add_a_second_sonarr_instance(session: Session, monkeypatch) -> None:
    from app.config import get_settings

    _instance(session, "Configured in the app")
    monkeypatch.setenv("SONARR_URL", ANIME)
    monkeypatch.setenv("SONARR_API_KEY", "from-compose")

    assert svc.seed_sonarr_from_env(session, get_settings()) is None
    assert len(svc.list_sonarr(session)) == 1
