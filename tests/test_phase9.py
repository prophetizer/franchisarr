"""Activity log, instance management UI, config backup, password change and update checks."""

from __future__ import annotations

import json

import pytest
import responses
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import (
    ActivityLogEntry,
    CollectionExclude,
    ItemType,
    RadarrInstance,
    SonarrInstance,
    SpinoffMapping,
    TriggerSource,
    User,
)
from app.services import config_backup, instance_service, sonarr_instance_service, update_checker
from app.services.settings_service import SettingKey, get_setting, set_setting

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"
RADARR = "http://radarr.test:7878"


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


# ------------------------------------------------------------------ instance UI


def test_the_instances_page_masks_api_keys(client: TestClient) -> None:
    """Convention #3: a key must not be in the page source, masked on screen or not."""
    with Session(get_engine()) as session:
        instance_service.create_radarr(session, name="HD", url=RADARR,
                                       api_key="verysecretapikey1234")

    body = client.get(f"{BASE}/instances").text

    assert "verysecretapikey1234" not in body
    assert "1234" in body, "the last few characters identify which key it is"


def test_adding_an_instance_through_the_ui(client: TestClient) -> None:
    response = client.post(f"{BASE}/instances/radarr", data={
        "name": "HD", "url": RADARR, "api_key": "abc123def456",
    })

    assert response.status_code == 303
    with Session(get_engine()) as session:
        assert len(instance_service.list_radarr(session)) == 1


def test_the_add_form_never_prefills_a_key(client: TestClient) -> None:
    """A pre-filled password field is a key sitting in the page source."""
    with Session(get_engine()) as session:
        instance_service.create_radarr(session, name="HD", url=RADARR, api_key="abc123def456")

    body = client.get(f"{BASE}/instances").text

    assert 'value="abc123def456"' not in body


def test_removing_an_instance(client: TestClient) -> None:
    with Session(get_engine()) as session:
        instance = instance_service.create_radarr(session, name="HD", url=RADARR, api_key="k")
        instance_id = instance.id

    client.post(f"{BASE}/instances/radarr/{instance_id}/delete")

    with Session(get_engine()) as session:
        assert instance_service.list_radarr(session) == []


@responses.activate
def test_testing_an_instance_reports_a_proxy_clearly(client: TestClient) -> None:
    with Session(get_engine()) as session:
        instance = instance_service.create_radarr(session, name="HD", url=RADARR, api_key="k")
        instance_id = instance.id
    responses.add(responses.GET, f"{RADARR}/api/v3/system/status", status=401,
                  body="<html>login</html>", content_type="text/html")

    body = client.get(f"{BASE}/instances/radarr/{instance_id}/test").text

    assert "authentication proxy" in body


# ------------------------------------------------------------------ activity log


def _log(session: Session, **kwargs) -> ActivityLogEntry:
    defaults = {"item_type": ItemType.MOVIE.value, "tmdb_id": 90, "title": "Beverly Hills Cop",
                "trigger_source": TriggerSource.MANUAL.value}
    entry = ActivityLogEntry(**{**defaults, **kwargs})
    session.add(entry)
    session.commit()
    return entry


def test_the_activity_page_lists_adds(client: TestClient) -> None:
    with Session(get_engine()) as session:
        user = session.exec(select(User)).first()
        _log(session, triggered_by=user.id)

    body = client.get(f"{BASE}/activity").text

    assert "Beverly Hills Cop" in body
    assert "admin" in body


def test_a_scheduled_add_is_attributed_to_the_scheduler(client: TestClient) -> None:
    with Session(get_engine()) as session:
        _log(session, triggered_by=None, trigger_source=TriggerSource.SCHEDULED.value)

    assert "Scheduled scan" in client.get(f"{BASE}/activity").text


def test_a_deleted_users_add_is_not_mistaken_for_a_scheduled_one(client: TestClient) -> None:
    """Both have triggered_by NULL; trigger_source is what tells them apart, which is the whole
    reason SET NULL is safe on that column."""
    with Session(get_engine()) as session:
        _log(session, triggered_by=None, trigger_source=TriggerSource.MANUAL.value)

    body = client.get(f"{BASE}/activity").text

    assert "deleted account" in body
    assert "Scheduled scan" not in body


def test_the_activity_page_says_it_is_not_tracking_downloads(client: TestClient) -> None:
    with Session(get_engine()) as session:
        _log(session)

    assert "history page" in client.get(f"{BASE}/activity").text


# ------------------------------------------------------------------ config backup


def _seed_config(session: Session) -> None:
    set_setting(session, SettingKey.TMDB_API_KEY, "tmdb-secret-key")
    set_setting(session, SettingKey.PLEX_TOKEN, "plex-secret-token")
    set_setting(session, SettingKey.SCAN_SCHEDULE_CRON, "0 3 * * *")
    session.commit()
    instance_service.create_radarr(session, name="HD", url=RADARR, api_key="radarr-secret")
    sonarr_instance_service.create_sonarr(session, name="TV", url="http://sonarr.test:8989",
                                          api_key="sonarr-secret")
    session.add(SpinoffMapping(source_show_tmdb_id=4614, spinoff_show_tmdb_id=17610,
                               source="local", confidence="confirmed"))
    session.add(CollectionExclude(tmdb_collection_id=85861, tmdb_movie_id=306))
    session.commit()


def test_a_full_export_contains_the_credentials_it_needs_to_restore(session: Session) -> None:
    _seed_config(session)

    document = config_backup.export_config(session)

    assert document["settings"][SettingKey.TMDB_API_KEY] == "tmdb-secret-key"
    assert document["radarr_instances"][0]["api_key"] == "radarr-secret"
    assert document["redacted"] is False


def test_a_redacted_export_contains_no_credentials(session: Session) -> None:
    """The one to paste into a forum thread — which is exactly when people leak their keys."""
    _seed_config(session)

    blob = json.dumps(config_backup.export_config(session, redact=True))

    for secret in ("tmdb-secret-key", "plex-secret-token", "radarr-secret", "sonarr-secret"):
        assert secret not in blob
    assert json.loads(blob)["redacted"] is True


def test_a_redacted_export_keeps_the_non_secret_configuration(session: Session) -> None:
    _seed_config(session)

    document = config_backup.export_config(session, redact=True)

    assert document["settings"][SettingKey.SCAN_SCHEDULE_CRON] == "0 3 * * *"
    assert document["radarr_instances"][0]["url"] == RADARR
    assert len(document["spinoff_mappings"]) == 1


def test_the_activity_log_is_not_exported(session: Session) -> None:
    """Local history, not configuration — and it would bloat the file for no benefit."""
    _seed_config(session)
    _log(session)

    assert "activity" not in json.dumps(config_backup.export_config(session)).lower()


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ("not a dict", "Franchisarr config"),
        ({}, "no version marker"),
        ({"franchisarr_export_version": 99}, "newer Franchisarr"),
        ({"franchisarr_export_version": 1, "radarr_instances": "not a list"}, "wrong shape"),
        ({"franchisarr_export_version": 1, "radarr_instances": [{"url": "x"}]}, "missing its name"),
    ],
)
def test_a_malformed_backup_is_rejected_with_an_explanation(document, expected: str) -> None:
    with pytest.raises(config_backup.InvalidBackup) as exc_info:
        config_backup.validate(document)

    assert expected in str(exc_info.value)


def test_nothing_is_written_when_validation_fails(session: Session) -> None:
    """A half-applied config is worse than a rejected one."""
    with pytest.raises(config_backup.InvalidBackup):
        config_backup.import_config(session, {"franchisarr_export_version": 99})

    assert session.exec(select(RadarrInstance)).all() == []


def test_importing_the_same_backup_twice_is_harmless(session: Session) -> None:
    """Restoring onto a system that already holds the same data is ordinary — re-importing your
    own export, or merging two installs. It must not fail on a unique constraint."""
    _seed_config(session)
    document = config_backup.export_config(session)

    counts = config_backup.import_config(session, document)

    assert counts["already_present"] >= 3, "everything was already there"
    assert len(session.exec(select(RadarrInstance)).all()) == 1
    assert len(session.exec(select(SpinoffMapping)).all()) == 1


def test_replace_clears_before_importing(session: Session) -> None:
    _seed_config(session)
    document = config_backup.export_config(session)

    counts = config_backup.import_config(session, document, replace=True)

    assert counts["radarr"] == 1
    assert len(session.exec(select(RadarrInstance)).all()) == 1


def test_a_round_trip_restores_the_configuration(session: Session, tmp_path) -> None:
    _seed_config(session)
    document = config_backup.export_config(session)

    for model in (RadarrInstance, SonarrInstance, SpinoffMapping, CollectionExclude):
        for row in session.exec(select(model)).all():
            session.delete(row)
    session.commit()

    counts = config_backup.import_config(session, document)

    assert counts["radarr"] == 1 and counts["sonarr"] == 1
    assert session.exec(select(RadarrInstance)).first().api_key == "radarr-secret"
    assert get_setting(session, SettingKey.TMDB_API_KEY) == "tmdb-secret-key"


def test_importing_a_redacted_export_skips_rather_than_breaking_connections(
    session: Session,
) -> None:
    """An instance that exists but can't authenticate is harder to diagnose than one that's
    plainly absent."""
    _seed_config(session)
    document = config_backup.export_config(session, redact=True)
    for model in (RadarrInstance, SonarrInstance):
        for row in session.exec(select(model)).all():
            session.delete(row)
    session.commit()

    counts = config_backup.import_config(session, document)

    assert counts["radarr"] == 0
    assert counts["skipped_redacted"] >= 1
    assert session.exec(select(RadarrInstance)).all() == []


# ------------------------------------------------------------------ update checks


@responses.activate
def test_an_available_update_is_detected_from_a_release_list() -> None:
    """Forgejo and GitHub both return /releases newest-first with the same field names, which is
    why that endpoint is used rather than /releases/latest."""
    responses.add(responses.GET, update_checker.DEFAULT_RELEASES_URL,
                  json=[{"tag_name": "v99.0.0", "html_url": "https://example/releases/99"}])

    status = update_checker.check()

    assert status.update_available is True
    assert status.latest == "99.0.0"
    assert status.url == "https://example/releases/99"


@responses.activate
def test_the_highest_version_wins_regardless_of_list_order() -> None:
    """A forge sorts releases by creation time, and that is not the same thing as newest
    version. Forgejo once stamped v0.6.0 with the epoch -- the tag push and the release request
    landed together -- so it sorted *last*, and this checker would have told every install on
    0.5.0 it was up to date. Version numbers are the fact; list order is someone else's detail."""
    responses.add(responses.GET, update_checker.DEFAULT_RELEASES_URL, json=[
        {"tag_name": "v98.0.0", "html_url": "https://example/98"},
        {"tag_name": "v97.5.0", "html_url": "https://example/97"},
        {"tag_name": "v99.0.0", "html_url": "https://example/99"},   # mis-stamped, sorted last
    ])

    status = update_checker.check()

    assert status.latest == "99.0.0"
    assert status.url == "https://example/99"


@responses.activate
def test_a_draft_that_happens_to_be_first_does_not_hide_the_real_latest() -> None:
    responses.add(responses.GET, update_checker.DEFAULT_RELEASES_URL, json=[
        {"tag_name": "v100.0.0", "draft": True},
        {"tag_name": "v99.0.0"},
    ])

    assert update_checker.check().latest == "99.0.0"


@responses.activate
def test_a_tag_that_is_not_a_version_is_ignored() -> None:
    responses.add(responses.GET, update_checker.DEFAULT_RELEASES_URL, json=[
        {"tag_name": "nightly"},
        {"tag_name": "v99.0.0"},
    ])

    assert update_checker.check().latest == "99.0.0"


@responses.activate
def test_a_single_release_object_also_works() -> None:
    """So pointing this at /releases/latest, or a different forge, needs no code change."""
    responses.add(responses.GET, update_checker.DEFAULT_RELEASES_URL,
                  json={"tag_name": "v99.0.0"})

    assert update_checker.check().update_available is True


@responses.activate
def test_a_repository_with_no_releases_yet_is_not_an_error() -> None:
    """Forgejo answers /releases/latest with 404 when nothing is tagged, which is why the list
    endpoint is used -- it returns an empty list instead."""
    responses.add(responses.GET, update_checker.DEFAULT_RELEASES_URL, json=[])

    status = update_checker.check()

    assert status.latest is None
    assert status.update_available is False


@responses.activate
def test_a_draft_or_prerelease_is_not_announced() -> None:
    """Sending people to something not meant for them yet is worse than staying quiet."""
    responses.add(responses.GET, update_checker.DEFAULT_RELEASES_URL,
                  json=[{"tag_name": "v99.0.0", "prerelease": True}])

    assert update_checker.check().update_available is False


def test_the_default_release_url_points_at_this_project() -> None:
    assert "franchisarr" in update_checker.DEFAULT_RELEASES_URL
    assert update_checker.DEFAULT_RELEASES_URL.startswith("https://")


def test_the_release_url_can_be_overridden_per_install(session: Session) -> None:
    """For a fork, or for anyone who would rather the install asked no one."""
    assert update_checker.releases_url(session) == update_checker.DEFAULT_RELEASES_URL

    set_setting(session, SettingKey.UPDATE_RELEASES_URL, "https://example.invalid/releases")
    session.commit()

    assert update_checker.releases_url(session) == "https://example.invalid/releases"


@responses.activate
def test_the_current_version_is_not_an_update() -> None:
    from app import __version__

    responses.add(responses.GET, update_checker.DEFAULT_RELEASES_URL,
                  json={"tag_name": f"v{__version__}"})

    assert update_checker.check().update_available is False


@responses.activate
def test_an_unreachable_release_api_is_not_an_error() -> None:
    """A private repo or an offline host is an ordinary state, not the user's problem."""
    from requests.exceptions import ConnectionError as RequestsConnectionError

    responses.add(responses.GET, update_checker.DEFAULT_RELEASES_URL,
                  body=RequestsConnectionError("offline"))

    status = update_checker.check()

    assert status.update_available is False
    assert status.latest is None


@responses.activate
def test_the_update_check_sends_nothing_about_the_install() -> None:
    """Technical challenge #18: no telemetry.

    `limit=1` is a query parameter but says nothing about the install; what matters is that
    nothing identifying it is sent. Checked against the whole request rather than just the
    parameters, so a header or body added later would fail this too.
    """
    responses.add(responses.GET, update_checker.DEFAULT_RELEASES_URL, json={"tag_name": "v0.0.1"})

    update_checker.check()

    request = responses.calls[0].request
    assert request.body is None

    everything_sent = (
        f"{request.url} {dict(request.headers)}".lower()
    )
    for leak in ("franchisarr/0", "version=", "library", "plex", "tmdb", "instance", "uuid"):
        assert leak not in everything_sent, f"the update check disclosed {leak!r}"


# ------------------------------------------------------------------ password change


def test_changing_the_password(client: TestClient) -> None:
    response = client.post(f"{BASE}/password", data={
        "current_password": PASSWORD, "new_password": "a-brand-new-passphrase",
        "confirm_password": "a-brand-new-passphrase",
    })

    assert response.status_code == 303
    client.cookies.clear()
    assert client.post(f"{BASE}/login", data={
        "username": "admin", "password": "a-brand-new-passphrase"}).status_code == 303


def test_the_wrong_current_password_is_refused(client: TestClient) -> None:
    response = client.post(f"{BASE}/password", data={
        "current_password": "wrong", "new_password": "a-brand-new-passphrase",
        "confirm_password": "a-brand-new-passphrase",
    })

    assert response.status_code == 400
    assert "current password" in response.text


def test_mismatched_new_passwords_are_refused(client: TestClient) -> None:
    response = client.post(f"{BASE}/password", data={
        "current_password": PASSWORD, "new_password": "a-brand-new-passphrase",
        "confirm_password": "something-else-entirely",
    })

    assert response.status_code == 400
    assert "don't match" in response.text.replace("&#39;", "'")


def test_a_short_password_is_refused(client: TestClient) -> None:
    response = client.post(f"{BASE}/password", data={
        "current_password": PASSWORD, "new_password": "short", "confirm_password": "short",
    })

    assert response.status_code == 400
    assert "8 characters" in response.text


def test_changing_the_password_signs_out_other_browsers(client: TestClient, app_factory) -> None:
    """delete_sessions_for_user has existed unused since Phase 2 for exactly this."""
    from app.auth.sessions import COOKIE_NAME, get_session_user

    other_token = client.cookies[COOKIE_NAME]

    client.post(f"{BASE}/password", data={
        "current_password": PASSWORD, "new_password": "a-brand-new-passphrase",
        "confirm_password": "a-brand-new-passphrase",
    })

    with Session(get_engine()) as session:
        assert get_session_user(session, other_token) is None


def test_the_theme_toggle_is_present_and_defaults_to_dark(client: TestClient) -> None:
    body = client.get(f"{BASE}/settings").text

    assert 'data-theme="dark"' in body
    assert "franchisarrToggleTheme" in body
    assert "franchisarr-theme" in body, "the preference should persist per viewer"


def test_dismissals_are_exported_by_username_and_restored_to_the_same_person(session: Session) -> None:
    """Every 'Not interested' ever clicked, keyed by name: user ids are assigned in sign-in
    order and will not match on a new install. A dismissal whose person does not exist yet is
    counted, not handed to whoever ran the import."""
    from app.models import DismissedItem, User

    alice = User(external_username="alice"); bob = User(local_username="bob")
    session.add(alice); session.add(bob); session.commit()
    session.add(DismissedItem(user_id=alice.id, item_type="movie", tmdb_id=306))
    session.add(DismissedItem(user_id=bob.id, item_type="show", tmdb_id=17610))
    session.commit()

    document = config_backup.export_config(session)
    assert sorted((d["username"], d["item_type"], d["tmdb_id"]) for d in document["dismissed_items"]) == [
        ("alice", "movie", 306), ("bob", "show", 17610)]

    # A new install where only alice has signed in so far.
    for row in session.exec(select(DismissedItem)).all():
        session.delete(row)
    session.delete(bob); session.commit()

    counts = config_backup.import_config(session, document)

    assert counts["dismissals"] == 1 and counts["dismissals_unmatched"] == 1
    restored = session.exec(select(DismissedItem)).one()
    assert (restored.user_id, restored.tmdb_id) == (alice.id, 306)
    assert config_backup.import_config(session, document)["dismissals"] == 0, "idempotent"


def test_an_export_from_before_the_media_server_rename_still_imports(session: Session) -> None:
    """0.12 renamed plex_library_key to library_key. A backup taken on 0.11 has the old names."""
    from app.models import IncludedLibrary

    old = {"franchisarr_export_version": 1, "included_libraries": [
        {"plex_library_key": "1", "plex_library_name": "Movies", "library_type": "movie", "enabled": True}]}

    counts = config_backup.import_config(session, old)

    assert counts["libraries"] == 1
    lib = session.exec(select(IncludedLibrary)).one()
    assert (lib.library_key, lib.library_name, lib.enabled) == ("1", "Movies", True)
