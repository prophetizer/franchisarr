"""Multi-instance behaviour, the dedup toggles, and adding.

docs/DEVELOPMENT.md convention 4: there is never "the Radarr". These tests exist to keep that true --
several of them would pass trivially on a single-instance design and fail on a wrong one.
"""

from __future__ import annotations

import pytest
import responses
from sqlmodel import Session, select

from app.clients.radarr_client import RadarrClient
from app.models import (
    ActivityLogEntry,
    ItemType,
    LibraryItem,
    MatchSource,
    RadarrInstance,
    RadarrMovie,
    TmdbCollection,
    TmdbCollectionMovie,
    TmdbMovie,
    User,
)
from app.services import add_service, instance_service, movie_gap_service
from app.services.settings_service import SettingKey, set_setting

COLLECTION = 85861
HD = "http://radarr-hd.test:7878"
UHD = "http://radarr-4k.test:7878"


def _instance(session: Session, name: str, url: str, **kwargs) -> RadarrInstance:
    return instance_service.create_radarr(
        session, name=name, url=url, api_key=f"key-{name}", **kwargs
    )


def _user(session: Session) -> User:
    user = User(local_username="admin", is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _library_with_gap(session: Session) -> None:
    """Owns Beverly Hills Cop; II and III are missing."""
    session.add(TmdbCollection(tmdb_collection_id=COLLECTION, name="Beverly Hills Cop Collection"))
    for position, (tmdb_id, title) in enumerate(
        [(90, "Beverly Hills Cop"), (96, "Beverly Hills Cop II"), (306, "Beverly Hills Cop III")]
    ):
        session.add(
            TmdbCollectionMovie(
                collection_id=COLLECTION, tmdb_movie_id=tmdb_id, title=title,
                release_year=1984 + position, release_date=f"{1984 + position}-06-01",
                position=position,
            )
        )
    session.add(
        LibraryItem(library_key="1", item_key="1", item_type=ItemType.MOVIE.value,
                    title="Beverly Hills Cop", year=1984, tmdb_id=90,
                    match_source=MatchSource.GUID.value)
    )
    session.add(TmdbMovie(tmdb_id=90, title="Beverly Hills Cop", collection_id=COLLECTION))
    session.commit()


def _cache(session: Session, instance: RadarrInstance, tmdb_id: int, *, in_queue: bool = False) -> None:
    session.add(
        RadarrMovie(instance_id=instance.id, tmdb_id=tmdb_id, title="x", in_queue=in_queue)
    )
    session.commit()


# ------------------------------------------------------------------ instance management


def test_the_first_instance_becomes_the_default_automatically(session: Session) -> None:
    """Otherwise a single-instance install opens the add dialog with nothing selected."""
    first = _instance(session, "Radarr", HD)

    assert first.is_default is True


def test_marking_a_default_clears_the_previous_one(session: Session) -> None:
    first = _instance(session, "HD", HD)
    second = _instance(session, "4K", UHD)

    instance_service.set_default(session, second.id)

    session.refresh(first)
    session.refresh(second)
    assert (first.is_default, second.is_default) == (False, True)


def test_deleting_the_default_promotes_another(session: Session) -> None:
    """An install with no default would open the add dialog blank."""
    first = _instance(session, "HD", HD)
    _instance(session, "4K", UHD)

    instance_service.delete_radarr(session, first.id)

    remaining = instance_service.list_radarr(session)
    assert len(remaining) == 1
    assert remaining[0].is_default is True


def test_deleting_an_instance_removes_its_cached_films(session: Session) -> None:
    instance = _instance(session, "HD", HD)
    _cache(session, instance, 90)

    instance_service.delete_radarr(session, instance.id)

    assert session.exec(select(RadarrMovie)).all() == []


# ------------------------------------------------------------------ which instance is offered


def test_the_default_instance_is_offered_when_the_user_has_no_history(session: Session) -> None:
    _instance(session, "HD", HD)
    fourk = _instance(session, "4K", UHD)
    instance_service.set_default(session, fourk.id)

    assert instance_service.preferred_instance(session, _user(session)).id == fourk.id


def test_a_users_last_choice_beats_the_global_default(session: Session) -> None:
    """On a 4K/1080p split, whoever always adds to 1080p shouldn't retype it every time
    (technical challenge #3)."""
    hd = _instance(session, "HD", HD)
    fourk = _instance(session, "4K", UHD)
    instance_service.set_default(session, fourk.id)
    user = _user(session)

    instance_service.remember_choice(session, user, hd.id)

    assert instance_service.preferred_instance(session, user).id == hd.id


def test_a_stale_last_choice_falls_back_instead_of_breaking(session: Session) -> None:
    """The remembered id isn't a foreign key, so a deleted instance must read as no preference."""
    hd = _instance(session, "HD", HD)
    user = _user(session)
    instance_service.remember_choice(session, user, hd.id)
    fourk = _instance(session, "4K", UHD)
    instance_service.delete_radarr(session, hd.id)

    assert instance_service.preferred_instance(session, user).id == fourk.id


def test_no_instances_means_no_preference(session: Session) -> None:
    assert instance_service.preferred_instance(session, _user(session)) is None


# ------------------------------------------------------------------ dedup toggles


def test_a_film_already_in_radarr_is_not_a_gap(session: Session) -> None:
    _library_with_gap(session)
    instance = _instance(session, "HD", HD)
    _cache(session, instance, 96)

    gaps = movie_gap_service.collections_with_gaps(session)

    assert [m.tmdb_id for m in gaps[0].missing] == [306]


def test_instances_are_independent_by_default(session: Session) -> None:
    """A 4K/1080p split legitimately wants the same film in both, so one instance holding it
    must not hide it from the other's list."""
    _library_with_gap(session)
    hd = _instance(session, "HD", HD)
    fourk = _instance(session, "4K", UHD)
    _cache(session, hd, 96)

    from_4k = movie_gap_service.collections_with_gaps(session, radarr_instance_id=fourk.id)

    assert {m.tmdb_id for m in from_4k[0].missing} == {96, 306}


def test_cross_instance_dedup_makes_any_instance_count(session: Session) -> None:
    """Right when instances are split by content type rather than quality tier."""
    _library_with_gap(session)
    hd = _instance(session, "HD", HD)
    fourk = _instance(session, "4K", UHD)
    _cache(session, hd, 96)
    set_setting(session, SettingKey.CROSS_INSTANCE_DEDUP, "true")
    session.commit()

    from_4k = movie_gap_service.collections_with_gaps(session, radarr_instance_id=fourk.id)

    assert [m.tmdb_id for m in from_4k[0].missing] == [306]


def test_a_queued_film_counts_as_owned_when_hide_if_queued_is_on(session: Session) -> None:
    _library_with_gap(session)
    instance = _instance(session, "HD", HD, hide_if_queued=True)
    _cache(session, instance, 96, in_queue=True)

    gaps = movie_gap_service.collections_with_gaps(session)

    assert [m.tmdb_id for m in gaps[0].missing] == [306]


def test_a_queued_film_still_shows_when_hide_if_queued_is_off(session: Session) -> None:
    _library_with_gap(session)
    instance = _instance(session, "HD", HD, hide_if_queued=False)
    _cache(session, instance, 96, in_queue=True)

    gaps = movie_gap_service.collections_with_gaps(session)

    assert {m.tmdb_id for m in gaps[0].missing} == {96, 306}


def test_radarr_alone_does_not_pull_in_an_unrelated_franchise(session: Session) -> None:
    """Collections are driven by what Plex holds. Keying off Radarr too would mean adding one
    film dragged its whole collection into the gap list."""
    session.add(TmdbCollection(tmdb_collection_id=999, name="Unrelated Collection"))
    session.add(TmdbMovie(tmdb_id=555, title="Unrelated", collection_id=999))
    session.add(
        TmdbCollectionMovie(collection_id=999, tmdb_movie_id=556, title="Unrelated II",
                            release_year=2000, release_date="2000-01-01", position=1)
    )
    instance = _instance(session, "HD", HD)
    _cache(session, instance, 555)
    session.commit()

    assert movie_gap_service.collection_gaps(session) == []


# ------------------------------------------------------------------ adding


@responses.activate
def test_adding_records_activity_and_remembers_the_instance(session: Session) -> None:
    instance = _instance(session, "HD", HD, default_quality_profile_id=1,
                         default_root_folder="/movies")
    user = _user(session)
    responses.add(responses.GET, f"{HD}/api/v3/movie/lookup",
                  json=[{"tmdbId": 306, "title": "Beverly Hills Cop III"}])
    responses.add(responses.POST, f"{HD}/api/v3/movie",
                  json={"id": 7, "tmdbId": 306, "title": "Beverly Hills Cop III"})
    responses.add(responses.GET, f"{HD}/api/v3/movie", json=[{"tmdbId": 306, "title": "BHC III"}])
    responses.add(responses.GET, f"{HD}/api/v3/queue", json={"records": []})

    result = add_service.add_movie(session, instance=instance, tmdb_id=306, user=user)

    assert result.title == "Beverly Hills Cop III"
    entry = session.exec(select(ActivityLogEntry)).first()
    assert entry.tmdb_id == 306
    assert entry.triggered_by == user.id
    assert entry.instance_id == instance.id

    session.refresh(user)
    assert user.last_radarr_instance_id == instance.id


@responses.activate
def test_a_successful_add_immediately_stops_being_a_gap(session: Session) -> None:
    """The cache is refreshed on add, so the film doesn't linger in the list until the next
    scheduled refresh."""
    _library_with_gap(session)
    instance = _instance(session, "HD", HD, default_quality_profile_id=1,
                         default_root_folder="/movies")
    responses.add(responses.GET, f"{HD}/api/v3/movie/lookup",
                  json=[{"tmdbId": 96, "title": "Beverly Hills Cop II"}])
    responses.add(responses.POST, f"{HD}/api/v3/movie", json={"id": 7, "tmdbId": 96})
    responses.add(responses.GET, f"{HD}/api/v3/movie", json=[{"tmdbId": 96, "title": "BHC II"}])
    responses.add(responses.GET, f"{HD}/api/v3/queue", json={"records": []})

    add_service.add_movie(session, instance=instance, tmdb_id=96)

    gaps = movie_gap_service.collections_with_gaps(session)
    assert [m.tmdb_id for m in gaps[0].missing] == [306]


def test_adding_without_a_profile_is_refused_rather_than_guessed(session: Session) -> None:
    """Choosing a quality profile for someone means downloading the wrong thing at the wrong
    size (technical challenge #15)."""
    instance = _instance(session, "HD", HD, default_root_folder="/movies")

    with pytest.raises(add_service.AddFailed) as exc_info:
        add_service.add_movie(session, instance=instance, tmdb_id=306)

    assert "quality profile" in str(exc_info.value)


def test_adding_without_a_root_folder_is_refused(session: Session) -> None:
    instance = _instance(session, "HD", HD, default_quality_profile_id=1)

    with pytest.raises(add_service.AddFailed) as exc_info:
        add_service.add_movie(session, instance=instance, tmdb_id=306)

    assert "root folder" in str(exc_info.value)


@responses.activate
def test_a_failed_add_records_no_activity(session: Session) -> None:
    instance = _instance(session, "HD", HD, default_quality_profile_id=1,
                         default_root_folder="/movies")
    responses.add(responses.GET, f"{HD}/api/v3/movie/lookup", json=[])

    with pytest.raises(add_service.AddFailed):
        add_service.add_movie(session, instance=instance, tmdb_id=306)

    assert session.exec(select(ActivityLogEntry)).all() == []


# ------------------------------------------------------------------ cache refresh


@responses.activate
def test_an_unreachable_instance_keeps_its_previous_cache(session: Session) -> None:
    """Treating "couldn't ask" as "has nothing" would flood the gap list with films the user
    already owns -- worse than slightly stale data (technical challenge #15)."""
    instance = _instance(session, "HD", HD)
    _cache(session, instance, 96)
    responses.add(responses.GET, f"{HD}/api/v3/movie", status=500)

    result = instance_service.refresh_instance_cache(session, instance)

    assert result.ok is False
    assert result.error
    assert {row.tmdb_id for row in session.exec(select(RadarrMovie)).all()} == {96}


@responses.activate
def test_a_refresh_replaces_the_cache_wholesale(session: Session) -> None:
    instance = _instance(session, "HD", HD)
    _cache(session, instance, 111)
    responses.add(responses.GET, f"{HD}/api/v3/movie", json=[{"tmdbId": 222, "title": "New"}])
    responses.add(responses.GET, f"{HD}/api/v3/queue", json={"records": []})

    instance_service.refresh_instance_cache(session, instance)

    assert {row.tmdb_id for row in session.exec(select(RadarrMovie)).all()} == {222}


@responses.activate
def test_a_refresh_survives_the_cached_films_being_the_same_ones(session: Session) -> None:
    """The realistic case, and the one that broke on a real instance.

    A library barely changes between refreshes, so almost every id is already cached. Deleting
    the old rows through the ORM and adding the new ones in the same flush let SQLAlchemy order
    the INSERTs before the DELETEs, tripping the (instance_id, tmdb_id) unique constraint. The
    previous test only used non-overlapping ids, so it never saw it -- which is exactly why this
    reached a real Radarr before it was found.
    """
    instance = _instance(session, "HD", HD)
    for tmdb_id in (111, 222, 333):
        _cache(session, instance, tmdb_id)

    responses.add(
        responses.GET,
        f"{HD}/api/v3/movie",
        json=[{"tmdbId": tmdb_id, "title": f"Film {tmdb_id}"} for tmdb_id in (111, 222, 333, 444)],
    )
    responses.add(responses.GET, f"{HD}/api/v3/queue", json={"records": []})

    result = instance_service.refresh_instance_cache(session, instance)

    assert result.ok is True
    assert {row.tmdb_id for row in session.exec(select(RadarrMovie)).all()} == {111, 222, 333, 444}


@responses.activate
def test_two_refreshes_in_a_row_are_safe(session: Session) -> None:
    """Every add triggers a refresh, so the second one must work as well as the first."""
    instance = _instance(session, "HD", HD)
    for _ in range(2):
        responses.add(responses.GET, f"{HD}/api/v3/movie",
                      json=[{"tmdbId": 90, "title": "Beverly Hills Cop"}])
        responses.add(responses.GET, f"{HD}/api/v3/queue", json={"records": []})

    assert instance_service.refresh_instance_cache(session, instance).ok is True
    assert instance_service.refresh_instance_cache(session, instance).ok is True
    assert len(session.exec(select(RadarrMovie)).all()) == 1


@responses.activate
def test_the_queue_is_not_fetched_when_hide_if_queued_is_off(session: Session) -> None:
    """No point paying for a request whose answer is ignored."""
    instance = _instance(session, "HD", HD, hide_if_queued=False)
    responses.add(responses.GET, f"{HD}/api/v3/movie", json=[])

    instance_service.refresh_instance_cache(session, instance)

    assert not [c for c in responses.calls if "/queue" in c.request.url]


# ------------------------------------------------------------------ env bootstrap


def test_env_seeds_a_first_instance(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("RADARR_URL", HD)
    monkeypatch.setenv("RADARR_API_KEY", "from-compose")

    instance = instance_service.seed_radarr_from_env(session, get_settings())

    assert instance is not None
    assert instance.is_default is True


def test_env_does_not_add_a_second_instance(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same rule as the settings and admin bootstraps: create only, and only when empty. A stale
    compose value must not quietly add a duplicate on every restart."""
    from app.config import get_settings

    _instance(session, "Configured in the app", UHD)
    monkeypatch.setenv("RADARR_URL", HD)
    monkeypatch.setenv("RADARR_API_KEY", "from-compose")

    assert instance_service.seed_radarr_from_env(session, get_settings()) is None
    assert len(instance_service.list_radarr(session)) == 1


def test_env_seeding_needs_both_url_and_key(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("RADARR_URL", HD)

    assert instance_service.seed_radarr_from_env(session, get_settings()) is None
