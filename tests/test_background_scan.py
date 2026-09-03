"""Scanning runs in the background.

Reported from a real deployment: pressing "Scan my library" hung the page with no sign of life
and eventually timed out, because the scan ran inside the request. On a 3,400-film library that
is minutes of waiting on Plex and TMDb.
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.dependencies import API_KEY_HEADER
from app.auth.api_keys import generate_api_key
from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import User
from app.services import scan_job, scan_state
from app.services.settings_service import SettingKey, set_setting

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"


@pytest.fixture(autouse=True)
def _clean_state():
    scan_state.reset()
    yield
    scan_state.reset()


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            set_setting(session, SettingKey.PLEX_URL, "http://plex.test:32400")
            set_setting(session, SettingKey.PLEX_TOKEN, "token")
            set_setting(session, SettingKey.TMDB_API_KEY, "k" * 32)
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


# ------------------------------------------------------------------ the state machine


def test_only_one_scan_can_run_at_a_time() -> None:
    """Two clicks half a second apart must not start two scans over the same library."""
    assert scan_state.begin("manual") is True
    assert scan_state.begin("manual") is False


def test_a_finished_scan_frees_the_slot() -> None:
    scan_state.begin("manual")
    scan_state.finish("done")

    assert scan_state.begin("manual") is True


def test_a_failed_scan_frees_the_slot() -> None:
    """Otherwise a crash leaves it stuck on 'running' and the button never comes back."""
    scan_state.begin("manual")
    scan_state.fail("Plex went away")

    assert scan_state.current().running is False
    assert scan_state.begin("manual") is True


def test_progress_is_reported_as_a_percentage() -> None:
    scan_state.begin("manual")
    scan_state.update(phase="Reading Movies", processed=857, total=3428)

    progress = scan_state.current()
    assert progress.percent == 25
    assert progress.phase == "Reading Movies"


def test_percent_does_not_divide_by_zero_before_a_total_is_known() -> None:
    scan_state.begin("manual")
    scan_state.update(phase="Starting")

    assert scan_state.current().percent == 0


def test_updates_after_a_scan_ends_are_ignored() -> None:
    """A straggling progress callback from a finishing thread must not revive the panel."""
    scan_state.begin("manual")
    scan_state.finish("done")

    scan_state.update(phase="Reading Movies", processed=10, total=100)

    assert scan_state.current().running is False


def test_state_survives_concurrent_writers() -> None:
    """The scan thread writes progress while request threads read it."""
    scan_state.begin("manual")
    errors: list[Exception] = []

    def hammer() -> None:
        try:
            for i in range(200):
                scan_state.update(processed=i, total=200)
                scan_state.current()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []


# ------------------------------------------------------------------ the endpoints


def test_the_scan_request_returns_immediately(client: TestClient, monkeypatch) -> None:
    """The point of the change. A slow scan must not hold the request open."""
    started = threading.Event()
    release = threading.Event()

    def slow_run(session, **kwargs):
        started.set()
        release.wait(timeout=5)
        return scan_job.ScanJobResult()

    monkeypatch.setattr(scan_job, "run", slow_run)

    begun = time.monotonic()
    response = client.post(f"{BASE}/scan")
    elapsed = time.monotonic() - begun

    assert response.status_code == 200
    assert elapsed < 2, "the request waited for the scan"
    assert started.wait(timeout=5), "the scan did not actually start"
    release.set()


def test_the_response_shows_progress_and_polls(client: TestClient, monkeypatch) -> None:
    release = threading.Event()
    monkeypatch.setattr(scan_job, "run",
                        lambda session, **kw: release.wait(timeout=5) or scan_job.ScanJobResult())

    body = client.post(f"{BASE}/scan").text

    assert "Scanning" in body
    assert "hx-trigger" in body, "the panel should poll while running"
    assert "every 2s" in body
    release.set()


def test_the_finished_panel_stops_polling(client: TestClient) -> None:
    """The poll ends by the attribute being absent, so its absence is the stop signal."""
    scan_state.begin("manual")
    scan_state.finish("3,428 items scanned.")

    body = client.get(f"{BASE}/scan/status").text

    assert "Scan finished" in body
    assert "hx-trigger" not in body


def test_a_second_trigger_while_running_does_not_start_another(
    client: TestClient, monkeypatch
) -> None:
    calls: list[int] = []
    release = threading.Event()

    def slow_run(session, **kwargs):
        calls.append(1)
        release.wait(timeout=5)
        return scan_job.ScanJobResult()

    monkeypatch.setattr(scan_job, "run", slow_run)

    client.post(f"{BASE}/scan")
    client.post(f"{BASE}/scan")
    time.sleep(0.2)
    release.set()
    time.sleep(0.3)

    assert len(calls) == 1


def test_scanning_without_plex_configured_is_refused_before_starting(
    app_factory,
) -> None:
    """Told to the caller, rather than buried in a status endpoint nobody is polling yet."""
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as anon:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
        anon.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})

        response = anon.post(f"{BASE}/scan")

    assert response.status_code == 409
    assert scan_state.current().running is False


def test_the_scan_panel_appears_on_the_collections_page_while_running(
    client: TestClient,
) -> None:
    """A scan started elsewhere -- by the scheduler, or another browser -- should be visible."""
    scan_state.begin("scheduled")
    scan_state.update(phase="Reading Movies", processed=100, total=3428)

    body = client.get(f"{BASE}/collections").text

    assert "Scanning" in body
    assert "Reading Movies" in body


def test_a_crashing_scan_reports_instead_of_hanging(client: TestClient, monkeypatch) -> None:
    def explode(session, **kwargs):
        raise RuntimeError("Plex went away mid-scan")

    monkeypatch.setattr(scan_job, "run", explode)

    client.post(f"{BASE}/scan")
    for _ in range(50):
        if not scan_state.current().running:
            break
        time.sleep(0.1)

    progress = scan_state.current()
    assert progress.running is False
    assert "Plex went away mid-scan" in progress.errors[0]
    assert "stopped early" in client.get(f"{BASE}/scan/status").text


def test_the_scheduler_skips_when_a_scan_is_already_running(monkeypatch) -> None:
    """A scheduled run firing while someone watches a manual one would do the same work twice."""
    from app.services import scheduler as scheduler_service

    scan_state.begin("manual")
    started: list[str] = []
    monkeypatch.setattr(scan_job, "run_in_background", lambda t="manual": started.append(t) or False)

    scheduler_service._run_scan()

    assert started == ["scheduled"], "it should try, and be told no"
    assert scan_state.current().trigger == "manual", "the running scan is untouched"


def test_a_normal_scan_respects_the_cache(client, monkeypatch) -> None:
    """The default has to stay cheap: a nightly scan must not refetch 555 collections."""
    seen = {}

    def fake(trigger="manual", *, force_refresh=False):
        seen["force_refresh"] = force_refresh
        return True

    monkeypatch.setattr(scan_job, "run_in_background", fake)
    client.post(f"{BASE}/scan")

    assert seen["force_refresh"] is False


def test_refresh_everything_ignores_the_cache(client, monkeypatch) -> None:
    """Without this there is no way to act on a configuration change: adding a fanart.tv key buys
    nothing until the collections are fetched again, which is otherwise a week away."""
    seen = {}

    def fake(trigger="manual", *, force_refresh=False):
        seen["force_refresh"] = force_refresh
        return True

    monkeypatch.setattr(scan_job, "run_in_background", fake)
    client.post(f"{BASE}/scan", data={"refresh": "1"})

    assert seen["force_refresh"] is True
