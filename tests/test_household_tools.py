"""0.73.0: Add all missing, the weekly digest, server parity, duplicates and hiding a set from
one person's lists."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import get_engine
from app.models import IncludedLibrary, ItemType, LibraryItem, MatchSource, RadarrInstance, User
from app.services import add_all, add_service, digest, duplicates, hidden_sets, notifier, server_parity
from app.services.settings_service import SettingKey, get_setting, set_setting
from tests.conftest import ensure_server, seed_server
from tests.test_movie_ui import BASE, COLLECTION, _seed_collection, client  # noqa: F401 - fixture
from tests.test_plex_client import _register_section, client as plex, mocked_plex, plex_fixtures  # noqa: F401


def _film(session: Session, server_id: int, key: str, tmdb_id: int, title: str, library: str = "1",
          copies: int | None = None) -> None:
    session.add(LibraryItem(server_id=server_id, library_key=library, item_key=key, item_type=ItemType.MOVIE.value,
                            title=title, year=2000, tmdb_id=tmdb_id, match_source=MatchSource.GUID.value,
                            copies=copies))


# ------------------------------------------------------------------ hide a set for me


def test_a_hidden_collection_folds_away_for_that_person_only(client: TestClient) -> None:  # noqa: F811
    _seed_collection()
    page = client.get(f"{BASE}/collections").text
    assert "Beverly Hills Cop Collection" in page and "you've hidden" not in page

    detail = client.get(f"{BASE}/collections/{COLLECTION}").text
    assert 'name="hide" value="true"' in detail and "Hide from my lists" in detail
    assert client.post(f"{BASE}/hidden-sets", data={"kind": "collection", "ref": str(COLLECTION), "hide": "true",
                                                   "back": f"{BASE}/collections/{COLLECTION}"}).status_code == 303

    page = client.get(f"{BASE}/collections").text
    listed, folded = page.split("1 collection you've hidden", 1)
    assert "Beverly Hills Cop Collection" in folded and "Beverly Hills Cop Collection" not in listed.split("<main")[-1], \
        "folded away, not listed -- and not gone"
    assert "Show in my lists" in client.get(f"{BASE}/collections/{COLLECTION}").text
    assert "Beverly Hills Cop" not in client.get(f"{BASE}/").text.split("Closest to complete")[-1].split("</section>")[0]

    with Session(get_engine()) as session:
        other = User(username="someone", is_admin=False)
        session.add(other)
        session.commit()
        assert hidden_sets.hidden(session, other.id, "collection") == set(), "only for the one who hid it"

    client.post(f"{BASE}/hidden-sets", data={"kind": "collection", "ref": str(COLLECTION), "hide": "false"})
    assert "you've hidden" not in client.get(f"{BASE}/collections").text


def test_only_collections_and_franchises_can_be_hidden(client: TestClient) -> None:  # noqa: F811
    assert client.post(f"{BASE}/hidden-sets", data={"kind": "director", "ref": "1"}).status_code == 400


# ------------------------------------------------------------------ add all missing


def test_add_all_adds_what_the_server_works_out_not_what_the_form_says(client: TestClient, monkeypatch) -> None:  # noqa: F811
    _seed_collection()
    with Session(get_engine()) as session:
        session.add(RadarrInstance(name="Radarr", url="http://radarr.test:7878", api_key="r" * 32,
                                   default_quality_profile_id=1, default_root_folder="/movies"))
        session.commit()
        batch = add_all.missing(session, None, "collection", str(COLLECTION))
        assert [f.title for f in batch.films] == ["Beverly Hills Cop II", "Beverly Hills Cop III"]
        assert add_all.missing(session, None, "collection", "nope") is None
        radarr_id = session.exec(select(RadarrInstance.id)).first()

    added = []

    def fake_add(session, *, instance, tmdb_id, **kwargs):  # noqa: ANN001, ANN003
        if tmdb_id == 306:
            raise add_service.AddFailed("Radarr already has it")
        added.append((instance.name, tmdb_id, kwargs["quality_profile_id"], kwargs["root_folder_path"]))

    monkeypatch.setattr(add_service, "add_movie", fake_add)
    page = client.post(f"{BASE}/add-all", data={"kind": "collection", "ref": str(COLLECTION), "target": "radarr",
                                               "instance_id": radarr_id, "quality_profile_id": 4,
                                               "root_folder_path": "/movies", "tmdb_ids": "999"}).text
    assert added == [("Radarr", 96, 4, "/movies")], "the films come from the collection, never the form"
    assert "Added 1 of 2 from Beverly Hills Cop Collection" in page and "Radarr already has it" in page


def test_the_button_shows_for_an_admin_when_more_than_one_film_is_missing(client: TestClient) -> None:  # noqa: F811
    _seed_collection()
    page = client.get(f"{BASE}/collections/{COLLECTION}").text
    assert f'hx-get="{BASE}/add-all/collection/{COLLECTION}"' in page and "Add all 2 missing" in page
    dialog = client.get(f"{BASE}/add-all/collection/{COLLECTION}").text
    assert "Add all missing from Beverly Hills Cop Collection" in dialog and "Beverly Hills Cop III" in dialog
    assert "No Radarr instance is configured yet" in dialog
    assert client.get(f"{BASE}/add-all/elsewhere/1").status_code == 404


# ------------------------------------------------------------------ weekly digest


def _report(*movies: tuple[int, str], dates: tuple = ()) -> notifier.ScanReport:
    return notifier.ScanReport(new_movies=[notifier.NewItem("movie", tid, title, "Set") for tid, title in movies],
                               release_dates=[notifier.NewItem("movie", tid, title, detail) for tid, title, detail in dates])


def test_the_digest_banks_a_weeks_news_once_and_keeps_the_latest_date(session: Session) -> None:
    digest.bank(session, _report((1, "A"), dates=((9, "Z", "dated 2027-01-01"),)))
    digest.bank(session, _report((1, "A"), (2, "B"), dates=((9, "Z", "moved to 2027-03-01"),)))
    week = digest.pending_report(session)
    assert [i.title for i in week.new_movies] == ["A", "B"]
    assert [i.detail for i in week.release_dates] == ["moved to 2027-03-01"]
    assert week.period == "this week" and week.found == "this week: 2 missing films and 1 release date"


def test_the_digest_empties_only_once_delivered(session: Session, monkeypatch) -> None:
    digest.bank(session, _report((1, "A")))
    set_setting(session, SettingKey.WEBHOOK_URL, "https://hooks.test/x")
    session.commit()
    sent = []
    monkeypatch.setattr(notifier, "send", lambda url, report, fmt: sent.append(report.found) or False)
    assert digest.send(session) is False and digest.pending_report(session).total == 1, "kept for next time"
    monkeypatch.setattr(notifier, "send", lambda url, report, fmt: sent.append(report.found) or True)
    assert digest.send(session) is True and digest.pending_report(session).total == 0
    assert sent == ["this week: 1 missing film"] * 2


def test_a_digest_reads_as_one_in_every_format() -> None:
    report = _report((1, "A"))
    report.period = "this week"
    assert notifier.build_discord(report)["embeds"][0]["title"] == "Weekly digest"
    assert notifier.build_slack(report)["text"] == "Franchisarr this week: 1 missing film."
    assert notifier.build_text(report)[0] == "Franchisarr: this week: 1 missing film"
    assert notifier.build_generic(report)["period"] == "this week"
    assert notifier.build_generic(_report((1, "A")))["period"] == "scan"


def test_the_settings_choose_the_mode_and_its_day_and_hour(client: TestClient) -> None:  # noqa: F811
    page = client.get(f"{BASE}/settings").text
    assert 'value="each" checked' in page and 'id="notifications"' in page
    assert client.post(f"{BASE}/settings/notify-mode", data={"mode": "weekly", "day": 5, "hour": 18}).status_code == 303
    with Session(get_engine()) as session:
        assert get_setting(session, SettingKey.NOTIFY_MODE) == "weekly"
        assert get_setting(session, SettingKey.DIGEST_CRON) == "0 18 * * 5"
    page = client.get(f"{BASE}/settings").text
    assert 'value="weekly" checked' in page and '<option value="5" selected>Friday</option>' in page


def test_a_backup_never_carries_the_banked_news() -> None:
    from app.services.config_backup import _importable_settings

    allowed = _importable_settings()
    assert SettingKey.NOTIFY_MODE in allowed and SettingKey.DIGEST_CRON in allowed
    assert SettingKey.DIGEST_PENDING not in allowed


def test_a_weekly_scan_banks_instead_of_sending() -> None:
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "services" / "scan_job.py").read_text()
    assert "if digest.weekly(session):\n            # Weekly digest (0.73.0): banked for the week's message, not sent now.\n            digest.bank(session, result.report)" in src


# ------------------------------------------------------------------ duplicates and parity


def test_duplicates_are_per_server_from_two_places_or_several_versions(session: Session) -> None:
    plex = ensure_server(session)
    jelly = seed_server(session, "jellyfin")
    session.add(IncludedLibrary(server_id=plex, library_key="1", library_name="Movies", library_type="movie", enabled=True))
    session.add(IncludedLibrary(server_id=plex, library_key="2", library_name="4K Movies", library_type="movie", enabled=True))
    _film(session, plex, "a1", 10, "Alien")
    _film(session, plex, "a2", 10, "Alien", library="2")               # two libraries
    _film(session, plex, "h1", 20, "Heat", copies=2)                    # two versions
    _film(session, plex, "m1", 30, "Matrix")
    _film(session, jelly.id, "m1", 30, "Matrix")                        # two servers: not a duplicate
    session.commit()

    found = {d.title: d for d in duplicates.find(session)}
    assert set(found) == {"Alien", "Heat"}
    assert found["Alien"].places == ["Movies", "4K Movies"] and found["Heat"].places == ["Movies (2 versions)"]


def test_parity_lists_what_each_server_lacks(session: Session) -> None:
    plex = ensure_server(session)
    jelly = seed_server(session, "jellyfin", enabled=False)
    _film(session, plex, "a", 10, "Alien")
    _film(session, plex, "b", 20, "Blade")
    _film(session, jelly.id, "b", 20, "Blade")
    _film(session, jelly.id, "c", 30, "Cars")
    session.commit()

    sides, gaps = server_parity.compare(session)
    assert [(s.name, s.films, s.enabled) for s in sides] == [("Plex", 2, True), ("Jellyfin", 2, False)]
    by_pair = {(g.have.name, g.lacks.name): [t for _, t, _ in g.films] for g in gaps}
    assert by_pair == {("Plex", "Jellyfin"): ["Alien"], ("Jellyfin", "Plex"): ["Cars"]}


def test_plex_counts_a_films_versions_from_the_listing(mocked_plex, plex_fixtures, plex) -> None:  # noqa: F811
    _register_section(mocked_plex, plex_fixtures, 1, "section_1_movies.xml")
    assert [m.copies for m in plex.list_movies("1")] == [1, 2, None]


def test_the_pages_render(client: TestClient) -> None:  # noqa: F811
    assert "No film is in your library twice" in client.get(f"{BASE}/duplicates").text
    assert "Needs two or more media servers" in client.get(f"{BASE}/parity").text
    nav = client.get(f"{BASE}/collections").text
    assert f'href="{BASE}/duplicates"' in nav and f'href="{BASE}/parity"' in nav


def test_the_preference_forms_send_you_back_only_inside_the_app(client: TestClient) -> None:  # noqa: F811
    """CodeQL py/url-redirection, 2026-10-16: the forms' own check let a backslash through
    ("/\\evil.com" is "//evil.com" to a browser); they use the sign-in page's check now."""
    for form, data in (("/look", {"look": "showcase"}), ("/preferences/intros", {"on": "true"}),
                       ("/preferences/effects", {"value": "calm"}), ("/preferences/density", {"value": "compact"}),
                       ("/hidden-sets", {"kind": "collection", "ref": "1"})):
        for back, expected in ((f"{BASE}/collections", f"{BASE}/collections"), (f"{BASE}/\\evil.com", f"{BASE}/"),
                               ("https://evil.com/", f"{BASE}/"), (f"{BASE}/x\tjs", f"{BASE}/")):
            location = client.post(f"{BASE}{form}", data={**data, "back": back}).headers["location"]
            assert location == expected, (form, back, location)
