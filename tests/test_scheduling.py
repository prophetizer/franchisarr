"""Scheduled scans and webhook notifications.

Two behaviours get the most attention because getting them wrong makes the feature actively
harmful rather than merely broken: announcing the entire existing backlog on the first run, and
producing a payload the receiving service rejects.
"""

from __future__ import annotations

import json

import pytest
import responses
from sqlmodel import Session, select

from app.models import (
    MediaServer,
    ItemType,
    LibraryItem,
    MatchSource,
    SeenGap,
    TmdbCollection,
    TmdbCollectionMovie,
    TmdbMovie,
    WebhookFormat,
)
from app.services import notifier, scan_job
from app.services import scheduler as scheduler_service
from app.services.settings_service import SettingKey, set_setting
from tests.conftest import ensure_server

HOOK = "https://hooks.example.com/abc"
COLLECTION = 85861


def _report(movies: int = 0, shows: int = 0) -> notifier.ScanReport:
    return notifier.ScanReport(
        new_movies=[notifier.NewItem("movie", i, f"Film {i}", "A Collection") for i in range(movies)],
        new_shows=[notifier.NewItem("show", 1000 + i, f"Show {i}", "spin-off of X") for i in range(shows)],
    )


def _library_with_gap(session: Session) -> None:
    session.add(TmdbCollection(tmdb_collection_id=COLLECTION, name="Beverly Hills Cop Collection"))
    for position, (tmdb_id, title) in enumerate([(90, "Beverly Hills Cop"), (96, "BHC II")]):
        session.add(TmdbCollectionMovie(collection_id=COLLECTION, tmdb_movie_id=tmdb_id,
                                        title=title, release_year=1984 + position,
                                        release_date=f"{1984 + position}-06-01", position=position))
    session.add(LibraryItem(server_id=ensure_server(session), library_key="1", item_key="1", item_type=ItemType.MOVIE.value,
                            title="Beverly Hills Cop", year=1984, tmdb_id=90,
                            match_source=MatchSource.GUID.value))
    session.add(TmdbMovie(tmdb_id=90, title="Beverly Hills Cop", collection_id=COLLECTION))
    session.commit()


# ------------------------------------------------------------------ cron handling


@pytest.mark.parametrize("expression", ["0 3 * * *", "*/15 * * * *", "0 0 * * 0", "30 4 1 * *"])
def test_valid_cron_expressions(expression: str) -> None:
    assert scheduler_service.validate_cron(expression) is not None


def test_an_empty_schedule_is_valid_and_means_no_schedule() -> None:
    assert scheduler_service.validate_cron("") is None
    assert scheduler_service.validate_cron("   ") is None


@pytest.mark.parametrize("expression", ["nonsense", "99 99 * * *", "0 3 * *", "* * * * * *"])
def test_invalid_cron_expressions_are_rejected_with_an_explanation(expression: str) -> None:
    with pytest.raises(scheduler_service.InvalidSchedule) as exc_info:
        scheduler_service.validate_cron(expression)

    assert "cron expression" in str(exc_info.value)


def test_a_bad_schedule_disables_scanning_rather_than_crashing() -> None:
    """A bad value in the database must not stop the app booting -- the operator should get a
    message, not a crash-looping container."""
    assert scheduler_service.apply_schedule("total nonsense") is None
    scheduler_service.shutdown()


def test_describe_explains_no_schedule_rather_than_saying_nothing() -> None:
    assert "only scan when you ask" in scheduler_service.describe("")


def test_describe_reports_the_next_run_in_local_time() -> None:
    """The answer should be in the same frame as the question: someone typing 3am means their
    3am, not UTC."""
    assert "this server's time" in scheduler_service.describe("0 3 * * *")


# ------------------------------------------------------------------ payloads


def test_the_generic_payload_is_not_truncated() -> None:
    """A machine consumer wants the whole list, and there's no third-party cap to respect."""
    payload = notifier.build_generic(_report(movies=50))

    assert len(payload["movies"]) == 50
    assert payload["total_new"] == 50


def test_the_discord_payload_stays_inside_its_limits() -> None:
    """227 missing films is a real first-scan number; Discord rejects an oversized payload
    outright, so a notifier that only works on small scans is worse than none."""
    payload = notifier.build_discord(_report(movies=227, shows=40))

    assert len(payload["content"]) <= notifier.DISCORD_CONTENT_LIMIT
    assert len(payload["embeds"]) <= 10
    for embed in payload["embeds"]:
        assert len(embed["fields"]) <= 25
        for field in embed["fields"]:
            assert len(field["value"]) <= 1024


def test_a_truncated_list_says_how_many_it_left_out() -> None:
    payload = notifier.build_discord(_report(movies=50))

    assert "and 35 more" in payload["embeds"][0]["fields"][0]["value"]


def test_the_slack_payload_sets_text_as_well_as_blocks() -> None:
    """`text` is what shows in the notification popup; without it people get a blank alert."""
    payload = notifier.build_slack(_report(movies=3))

    assert payload["text"]
    assert payload["blocks"]


def test_an_unknown_format_falls_back_to_generic_rather_than_failing() -> None:
    payload = notifier.build_payload(_report(movies=1), "not-a-format")

    assert payload["event"] == "franchisarr.scan_complete"


def test_the_summary_reads_naturally_for_one_and_many() -> None:
    assert notifier.ScanReport(new_movies=[notifier.NewItem("movie", 1, "X")]).summary() == \
        "1 missing film"
    assert "2 missing films" in _report(movies=2).summary()
    assert "and" in _report(movies=1, shows=1).summary()


# ------------------------------------------------------------------ delivery


@responses.activate
def test_a_webhook_is_delivered() -> None:
    responses.add(responses.POST, HOOK, status=204)

    assert notifier.send(HOOK, _report(movies=2), WebhookFormat.DISCORD.value) is True
    assert json.loads(responses.calls[0].request.body)["embeds"]


@responses.activate
def test_a_failing_webhook_does_not_raise() -> None:
    """A Discord outage must not fail the scan that produced the notification -- that work is
    already committed."""
    responses.add(responses.POST, HOOK, status=500)

    assert notifier.send(HOOK, _report(movies=1), "generic") is False


@responses.activate
def test_an_unreachable_webhook_does_not_raise() -> None:
    from requests.exceptions import ConnectionError as RequestsConnectionError

    responses.add(responses.POST, HOOK, body=RequestsConnectionError("no route"))

    assert notifier.send(HOOK, _report(movies=1), "generic") is False


def test_nothing_is_sent_when_there_is_no_news() -> None:
    with responses.RequestsMock():  # any request would fail this
        assert notifier.send(HOOK, notifier.ScanReport(), "generic") is False


def test_nothing_is_sent_without_a_url() -> None:
    with responses.RequestsMock():
        assert notifier.send("", _report(movies=1), "generic") is False


# ------------------------------------------------------------------ apprise


def test_the_text_form_is_titled_and_truncated_like_the_others() -> None:
    title, body = notifier.build_text(_report(movies=20, shows=1))

    assert title.startswith("Franchisarr: 20 missing films")
    assert body.startswith("**Missing films**\n- ")
    assert "…and 5 more" in body and "**Spin-offs**" in body


def test_apprise_urls_split_on_lines_and_commas() -> None:
    assert notifier.apprise_urls("tgram://a/b\n pover://c@d ,ntfy://e\n\n") == [
        "tgram://a/b", "pover://c@d", "ntfy://e"]


@responses.activate
def test_apprise_delivers_through_the_library() -> None:
    """Apprise's json:// service posts to an HTTP endpoint through requests, so the whole path
    -- URL parsing, formatting, delivery -- is exercised without a real Telegram."""
    responses.add(responses.POST, "https://hooks.example.com/abc", status=200)

    assert notifier.send("jsons://hooks.example.com/abc", _report(movies=2), WebhookFormat.APPRISE.value) is True
    sent = json.loads(responses.calls[0].request.body)
    assert sent["title"].startswith("Franchisarr: 2 missing films") and "**Missing films**" in sent["message"]


def test_an_apprise_url_nobody_understands_is_refused_not_raised() -> None:
    with responses.RequestsMock():
        assert notifier.send("nonsense", _report(movies=1), WebhookFormat.APPRISE.value) is False


@responses.activate
def test_apprise_api_gets_title_body_and_markdown() -> None:
    responses.add(responses.POST, "http://apprise:8000/notify/franchisarr", status=200)

    assert notifier.send("http://apprise:8000/notify/franchisarr", _report(movies=1),
                         WebhookFormat.APPRISE_API.value) is True
    sent = json.loads(responses.calls[0].request.body)
    assert sent["format"] == "markdown" and sent["title"].startswith("Franchisarr:") and "- " in sent["body"]


@responses.activate
def test_a_rejecting_apprise_api_does_not_raise() -> None:
    responses.add(responses.POST, "http://apprise:8000/notify", status=424)

    assert notifier.send("http://apprise:8000/notify", _report(movies=1), WebhookFormat.APPRISE_API.value) is False


# ------------------------------------------------------------------ new-since-last-run


def test_priming_marks_the_existing_backlog_as_already_reported(session: Session) -> None:
    """The first scheduled scan must not announce 227 films that were missing all along. That is
    the state of the world, not news, and it teaches people to mute the channel."""
    _library_with_gap(session)

    primed = scan_job.prime_seen_gaps(session)

    assert primed == 1
    assert {row.tmdb_id for row in session.exec(select(SeenGap)).all()} == {96}


def test_an_already_seen_gap_is_not_reported_again(session: Session) -> None:
    _library_with_gap(session)
    scan_job.prime_seen_gaps(session)

    fresh = scan_job._record_new(session, ItemType.MOVIE.value, {96: ("BHC II", "Collection")})

    assert fresh == []


def test_a_genuinely_new_gap_is_reported(session: Session) -> None:
    _library_with_gap(session)
    scan_job.prime_seen_gaps(session)

    fresh = scan_job._record_new(
        session, ItemType.MOVIE.value, {306: ("Beverly Hills Cop III", "Collection")}
    )

    assert [item.tmdb_id for item in fresh] == [306]


def test_movies_and_shows_are_tracked_separately(session: Session) -> None:
    """tmdb ids are only unique within a type, so a film and a show can share one."""
    scan_job._record_new(session, ItemType.MOVIE.value, {500: ("A Film", "")})

    fresh = scan_job._record_new(session, ItemType.SHOW.value, {500: ("A Show", "")})

    assert [item.tmdb_id for item in fresh] == [500]


def test_the_first_ever_scan_does_not_notify(session: Session, monkeypatch) -> None:
    """Everything missing on a fresh install is the state of the world, not news. A first
    message listing 227 films is how someone learns to mute the channel -- and a schedule set
    through SCAN_SCHEDULE_CRON never passes through the settings page that primes explicitly."""
    _library_with_gap(session)
    _plex_row(session)
    set_setting(session, SettingKey.TMDB_API_KEY, "k" * 32)
    set_setting(session, SettingKey.WEBHOOK_URL, HOOK)
    session.commit()

    sent = []
    monkeypatch.setattr(notifier, "send", lambda *a, **k: sent.append(a) or True)
    # The scan itself will fail to reach Plex; what matters is the notify decision.
    monkeypatch.setattr(scan_job.scan_service, "scan_movie_libraries",
                        lambda *a, **k: scan_job.scan_service.ScanSummary())
    monkeypatch.setattr(scan_job.scan_service, "scan_show_libraries",
                        lambda *a, **k: scan_job.scan_service.ScanSummary())
    monkeypatch.setattr(scan_job.instance_service, "refresh_all", lambda s: [])
    monkeypatch.setattr(scan_job.sonarr_instance_service, "refresh_all", lambda s: [])

    result = scan_job.run(session)

    assert result.report.total == 1, "the gap was still recorded"
    assert sent == [], "but nothing was announced on the first run"
    assert result.notified is False


def test_the_second_scan_does_notify_about_something_new(session: Session, monkeypatch) -> None:
    _library_with_gap(session)
    _plex_row(session)
    set_setting(session, SettingKey.TMDB_API_KEY, "k" * 32)
    set_setting(session, SettingKey.WEBHOOK_URL, HOOK)
    session.commit()

    for name in ("scan_movie_libraries", "scan_show_libraries"):
        monkeypatch.setattr(scan_job.scan_service, name,
                            lambda *a, **k: scan_job.scan_service.ScanSummary())
    monkeypatch.setattr(scan_job.instance_service, "refresh_all", lambda s: [])
    monkeypatch.setattr(scan_job.sonarr_instance_service, "refresh_all", lambda s: [])

    scan_job.run(session)  # first run primes

    # A new film appears in the collection.
    session.add(TmdbCollectionMovie(collection_id=COLLECTION, tmdb_movie_id=306,
                                    title="Beverly Hills Cop III", release_year=1994,
                                    release_date="1994-05-24", position=2))
    session.commit()

    sent = []
    monkeypatch.setattr(notifier, "send", lambda *a, **k: sent.append(a) or True)
    result = scan_job.run(session)

    assert [item.tmdb_id for item in result.report.new_movies] == [306]
    assert len(sent) == 1, "the genuinely new film is announced"


def test_a_scan_without_plex_configured_reports_why(session: Session) -> None:
    result = scan_job.run(session, notify=False)

    assert result.ok is False
    assert any("media server" in error for error in result.errors)


def test_a_scan_without_tmdb_configured_reports_why(session: Session) -> None:
    _plex_row(session)
    session.commit()

    result = scan_job.run(session, notify=False)

    assert any("TMDb" in error for error in result.errors)


def _plex_row(session: Session) -> None:
    """The scan reads whichever servers exist; the test's library rows already made one, so
    give it the address the mocks answer on."""
    server = session.get(MediaServer, ensure_server(session))
    server.url = "http://plex.test:32400"
    session.add(server); session.commit()


def _configured(session: Session) -> None:
    _plex_row(session)
    set_setting(session, SettingKey.TMDB_API_KEY, "k" * 32)
    session.commit()


def test_a_first_scan_defers_enrichment_and_a_later_one_does_not(session: Session, monkeypatch) -> None:
    """On a real library the enrichment steps -- every film's credits, every franchise's roster
    -- are ten minutes on top of a three-minute scan. A new user clicking "Scan" waits for the
    three, and the rest follows in a second job."""
    _library_with_gap(session)
    _configured(session)
    seen: list[bool] = []

    def fake_scan(*a, enrich=True, **k):
        seen.append(enrich)
        return scan_job.scan_service.ScanSummary()

    monkeypatch.setattr(scan_job.scan_service, "scan_movie_libraries", fake_scan)
    monkeypatch.setattr(scan_job.scan_service, "scan_show_libraries", fake_scan)
    monkeypatch.setattr(scan_job.instance_service, "refresh_all", lambda s: [])
    monkeypatch.setattr(scan_job.sonarr_instance_service, "refresh_all", lambda s: [])

    first = scan_job.run(session)
    assert first.enrichment_deferred is True
    assert seen == [False, False], "core only on the first scan"

    second = scan_job.run(session)
    assert second.enrichment_deferred is False
    assert seen[2:] == [True, True], "a later scan does everything, cheaply, inside the TTL"


def test_the_enrichment_job_runs_both_halves_and_stops_on_a_dead_key(session: Session, monkeypatch) -> None:
    _configured(session)
    calls: list[str] = []

    def movies(session, tmdb, ttl, summary, progress=None):
        calls.append("movies")

    def shows(session, wikidata, tmdb, ttl, summary, progress=None):
        calls.append("shows")

    monkeypatch.setattr(scan_job.scan_service, "enrich_movies", movies)
    monkeypatch.setattr(scan_job.scan_service, "enrich_shows", shows)
    assert scan_job.run_enrichment(session) == []
    assert calls == ["movies", "shows"]

    def movies_dead_key(session, tmdb, ttl, summary, progress=None):
        calls.append("movies")
        summary.errors.append("TMDb rejected that API key.")
        summary.tmdb_auth_failed = True

    calls.clear()
    monkeypatch.setattr(scan_job.scan_service, "enrich_movies", movies_dead_key)
    errors = scan_job.run_enrichment(session)
    assert calls == ["movies"], "the TV half is not attempted with a key TMDb just rejected"
    assert errors == ["TMDb rejected that API key."]
