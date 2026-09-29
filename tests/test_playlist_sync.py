"""Playlist sync: chosen playlists copied from their home server to the others."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.clients.media_server import PlaylistEntry, PlaylistInfo, PlaylistItemRef
from app.db import get_engine
from app.models import LibraryItem, MatchSource, PlaylistCopy, PlaylistSync
from app.services import media_server_service, notifier, playlist_sync
from app.services.settings_service import SettingKey, set_setting
from tests.conftest import seed_server

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"


class FakeServer:
    """A server's playlists and library, as the sync sees them through its client."""

    def __init__(self, films: dict[str, str], episodes: dict[str, list[tuple[int, int, str]]]) -> None:
        self.films, self.episodes = films, episodes      # key -> title; show key -> (season, episode, key)
        self.playlists: dict[str, dict] = {}
        self.created: list[tuple[str, list]] = []
        self.deleted: list[str] = []
        self.posters: dict[str, bytes] = {}
        self.down = False
        self._next = 100

    def add(self, pid: str, title: str, items: list[PlaylistItemRef], **extra) -> None:
        self.playlists[pid] = {"title": title, "items": items, **extra}

    def list_playlists(self):  # noqa: ANN201
        if self.down:
            raise ConnectionError("down")
        return [PlaylistInfo(pid, p["title"], p.get("smart", False), p.get("video", True), len(p["items"]))
                for pid, p in self.playlists.items()]

    def playlist_items(self, pid):  # noqa: ANN001, ANN201
        return self.playlists[pid]["items"]

    def playlist_entries(self, films, shows):  # noqa: ANN001, ANN201
        out = [PlaylistEntry(raw=f"raw:{k}", aired=None, key=k) for k in films if k in self.films]
        for show in shows:
            out += [PlaylistEntry(raw=f"raw:{k}", aired=None, show_key=show, season=s, episode=e, key=k)
                    for s, e, k in self.episodes.get(show, [])]
        return out

    def create_playlist(self, title, raws):  # noqa: ANN001, ANN201
        self._next += 1
        pid = f"new{self._next}"
        self.playlists[pid] = {"title": title, "items": list(raws)}
        self.created.append((title, list(raws)))
        return pid

    def delete_playlist_id(self, pid):  # noqa: ANN001, ANN201
        self.playlists.pop(pid, None)
        self.deleted.append(pid)

    def playlist_poster(self, pid):  # noqa: ANN001, ANN201
        return self.playlists[pid].get("poster")

    def set_playlist_poster_id(self, pid, image):  # noqa: ANN001, ANN201
        self.posters[pid] = image
        return True


def _film(key: str, title: str) -> PlaylistItemRef:
    return PlaylistItemRef("movie", key, title)


def _episode(key: str, show_key: str, season: int, number: int, title: str) -> PlaylistItemRef:
    return PlaylistItemRef("episode", key, title, show_key=show_key, season=season, episode=number)


@pytest.fixture
def servers(session: Session, monkeypatch):
    """Plex and Jellyfin. Alien (11) is on both; Aliens (12) only on Plex; Breaking Bad (100) on
    both, but Jellyfin has only its first season."""
    plex, jelly = seed_server(session, "plex", name="Plex"), seed_server(session, "jellyfin", name="Jellyfin")
    for server, rows in ((plex, [("p11", "movie", 11), ("p12", "movie", 12), ("ps100", "show", 100)]),
                         (jelly, [("j11", "movie", 11), ("js100", "show", 100)])):
        for key, kind, tmdb in rows:
            session.add(LibraryItem(server_id=server.id, library_key="1", item_key=key, item_type=kind,
                                    title=key, tmdb_id=tmdb, match_source=MatchSource.GUID.value))
    session.commit()
    fakes = {
        "Plex": FakeServer({"p11": "Alien", "p12": "Aliens"}, {"ps100": [(1, 1, "pe1"), (2, 1, "pe2")]}),
        "Jellyfin": FakeServer({"j11": "Alien"}, {"js100": [(1, 1, "je1")]}),
    }
    monkeypatch.setattr(media_server_service, "client_for", lambda s: fakes[s.name])
    monkeypatch.setattr(playlist_sync, "_state", playlist_sync.SyncProgress())
    return plex, jelly, fakes


def _road_trip(fakes: dict, **extra) -> None:
    fakes["Plex"].add("pl1", "Road trip", [
        _film("p11", "Alien"), _film("p12", "Aliens"), _film("home1", "Holiday video"),
        _episode("pe1", "ps100", 1, 1, "Breaking Bad S01E01"), _episode("pe2", "ps100", 2, 1, "Breaking Bad S02E01"),
    ], **extra)


def _copy(session: Session) -> PlaylistCopy:
    session.expire_all()
    return session.exec(select(PlaylistCopy)).one()


# ------------------------------------------------------------------ copying


def test_a_synced_playlist_is_copied_in_order_with_what_is_missing_reported(session: Session, servers) -> None:
    plex, jelly, fakes = servers
    _road_trip(fakes, poster=b"\xff\xd8poster")
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")

    state = playlist_sync.run(session)

    assert fakes["Jellyfin"].created == [("Road trip", ["raw:j11", "raw:je1"])], "matched titles, source order"
    copy = _copy(session)
    assert (copy.status, copy.matched, copy.unmatched) == ("ok", 2, 3)
    assert "Aliens (not on Jellyfin)" in copy.unmatched_titles
    assert "Holiday video (not in a library Franchisarr scans)" in copy.unmatched_titles
    assert "Breaking Bad S02E01 (episode not on Jellyfin)" in copy.unmatched_titles
    assert fakes["Jellyfin"].posters == {copy.target_playlist_id: b"\xff\xd8poster"}, "the source's own poster"
    assert state.created == 1 and fakes["Plex"].created == [], "nothing is copied back to the source"


def test_nothing_changes_when_nothing_changed(session: Session, servers) -> None:
    plex, _, fakes = servers
    _road_trip(fakes)
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")
    playlist_sync.run(session)

    state = playlist_sync.run(session)

    assert state.unchanged >= 1 and len(fakes["Jellyfin"].created) == 1 and fakes["Jellyfin"].deleted == []


def test_an_edit_at_the_source_replaces_the_copy(session: Session, servers) -> None:
    plex, _, fakes = servers
    _road_trip(fakes)
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")
    playlist_sync.run(session)
    first = _copy(session).target_playlist_id

    fakes["Plex"].playlists["pl1"]["items"] = [_film("p11", "Alien")]
    fakes["Plex"].playlists["pl1"]["title"] = "Space trip"
    playlist_sync.run(session)

    copy = _copy(session)
    assert fakes["Jellyfin"].deleted == [first] and copy.target_playlist_id != first
    assert fakes["Jellyfin"].created[-1] == ("Space trip", ["raw:j11"]), "a rename follows the source"


def test_a_same_named_playlist_sync_didnt_make_is_never_touched(session: Session, servers) -> None:
    plex, _, fakes = servers
    _road_trip(fakes)
    fakes["Jellyfin"].add("mine", "Road trip", [])
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")

    state = playlist_sync.run(session)

    assert state.blocked == 1 and _copy(session).status == "blocked"
    assert fakes["Jellyfin"].created == [] and fakes["Jellyfin"].deleted == [] and "mine" in fakes["Jellyfin"].playlists


def test_nothing_in_common_makes_no_copy(session: Session, servers) -> None:
    plex, _, fakes = servers
    fakes["Plex"].add("pl2", "Only on Plex", [_film("p12", "Aliens")])
    playlist_sync.enable(session, plex.id, "pl2", "Only on Plex")

    playlist_sync.run(session)

    assert fakes["Jellyfin"].created == [] and _copy(session).status == "empty"


# ------------------------------------------------------------------ deletions


def test_deleting_the_source_deletes_its_copies_and_the_sync(session: Session, servers) -> None:
    plex, _, fakes = servers
    _road_trip(fakes)
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")
    playlist_sync.run(session)
    made = _copy(session).target_playlist_id

    del fakes["Plex"].playlists["pl1"]
    state = playlist_sync.run(session)

    assert fakes["Jellyfin"].deleted == [made] and state.deleted == 1
    assert session.exec(select(PlaylistSync)).all() == [] and session.exec(select(PlaylistCopy)).all() == []


def test_a_source_that_cant_be_reached_deletes_nothing(session: Session, servers) -> None:
    plex, _, fakes = servers
    _road_trip(fakes)
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")
    playlist_sync.run(session)

    fakes["Plex"].down = True
    state = playlist_sync.run(session)

    assert state.failed == 1 and fakes["Jellyfin"].deleted == [] and session.exec(select(PlaylistSync)).one()


def test_a_failure_is_notified_through_the_webhook(session: Session, servers, monkeypatch) -> None:
    set_setting(session, SettingKey.WEBHOOK_URL, "https://hooks.example.com/x")
    session.commit()
    sent = []
    monkeypatch.setattr(notifier, "send_message", lambda url, title, lines, fmt: sent.append((title, lines)) or True)

    playlist_sync._notify(playlist_sync.SyncProgress(failed=1, errors=("Road trip → Jellyfin: ConnectionError",)), session)

    assert sent == [("Franchisarr: playlist sync had 1 problem", ["Road trip → Jellyfin: ConnectionError"])]


# ------------------------------------------------------------------ choosing


def test_the_page_offers_video_playlists_other_than_franchisarrs_and_marks_copies(session: Session, servers) -> None:
    plex, jelly, fakes = servers
    _road_trip(fakes)
    fakes["Plex"].add("pl3", "Alien Collection (Franchisarr)", [])
    fakes["Plex"].add("pl4", "Workout mix", [], video=False)
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")
    playlist_sync.run(session)

    view = {entry.server.name: entry for entry in playlist_sync.page(session)}

    assert [r.title for r in view["Plex"].rows] == ["Road trip"]
    assert view["Plex"].rows[0].sync is not None and view["Plex"].rows[0].copies[0][0] == "Jellyfin"
    copy_row = view["Jellyfin"].rows[0]
    assert copy_row.copy_of == ("Road trip", "Plex"), "a copy is shown as one, not offered as a source"
    with pytest.raises(ValueError):
        playlist_sync.enable(session, jelly.id, copy_row.id, "Road trip")


@pytest.fixture
def client(app_factory, monkeypatch):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            seed_server(session, "plex", name="Plex"); seed_server(session, "jellyfin", name="Jellyfin")
        fakes = {"Plex": FakeServer({}, {}), "Jellyfin": FakeServer({}, {})}
        fakes["Plex"].add("pl1", "Road trip", [])
        monkeypatch.setattr(media_server_service, "client_for", lambda s: fakes[s.name])
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def test_the_checklist_saves_what_is_ticked_and_to_where(client: TestClient, monkeypatch) -> None:
    started = []
    monkeypatch.setattr(playlist_sync, "run_in_background", lambda trigger: started.append(trigger) or True)
    page = client.get(f"{BASE}/playlists").text
    assert 'name="on" value="1|pl1"' in page and 'name="target|1|pl1" value="2"' in page and "Save and sync" in page

    # Ticked, following the defaults: no servers of its own.
    response = client.post(f"{BASE}/playlists/save", data={
        "row": "1|pl1", "title|1|pl1": "Road trip", "on": "1|pl1", "target|1|pl1": "2"})
    assert response.status_code == 303 and started == ["saved"], "saving starts a sync"
    with Session(get_engine()) as session:
        sync = session.exec(select(PlaylistSync)).one()
    assert sync.enabled and sync.targets is None, "without `custom` the boxes don't count"
    assert "Save and sync" in client.get(f"{BASE}/playlists").text

    # "change": servers of its own.
    client.post(f"{BASE}/playlists/save", data={
        "row": "1|pl1", "title|1|pl1": "Road trip", "on": "1|pl1", "custom|1|pl1": "1", "target|1|pl1": "2"})
    with Session(get_engine()) as session:
        assert session.exec(select(PlaylistSync)).one().targets == "[2]"

    # Unticked: no longer synced.
    client.post(f"{BASE}/playlists/save", data={"row": "1|pl1", "title|1|pl1": "Road trip"})
    with Session(get_engine()) as session:
        assert session.exec(select(PlaylistSync)).all() == []


def test_the_schedule_is_saved_and_applied(client: TestClient, monkeypatch) -> None:
    from app.services import scheduler as scheduler_service

    applied = []
    monkeypatch.setattr(scheduler_service, "apply_playlist_sync_schedule", lambda cron: applied.append(cron))

    assert client.post(f"{BASE}/playlists/schedule", data={"preset": "0 */6 * * *"}).status_code == 303
    assert applied == ["0 */6 * * *"]
    assert '<option value="0 */6 * * *" selected>Also every 6 hours</option>' in client.get(f"{BASE}/playlists").text

    back = client.post(f"{BASE}/playlists/schedule", data={"preset": "custom", "cron": "15 3 * * *", "tab": "history"})
    assert back.headers["location"].endswith("/playlists/history?saved=1") and applied[-1] == "15 3 * * *"
    page = client.get(f"{BASE}/playlists/history").text
    assert '<option value="custom" selected>' in page and 'value="15 3 * * *"' in page

    bad = client.post(f"{BASE}/playlists/schedule", data={"preset": "custom", "cron": "nonsense"})
    assert "error=" in bad.headers["location"] and applied[-1] == "15 3 * * *"
    assert "error=" in client.post(f"{BASE}/playlists/schedule", data={"preset": "* * * * *"}).headers["location"]


def test_history_keeps_the_last_thirty(session: Session, servers) -> None:
    for n in range(35):
        playlist_sync._record(playlist_sync.SyncProgress(trigger=f"run {n}", created=n), session)

    runs = playlist_sync.history(session)

    assert len(runs) == 30 and runs[0].trigger == "run 34" and runs[-1].trigger == "run 5"


def test_unticking_a_server_deletes_the_copy_there_and_only_there(session: Session, servers) -> None:
    plex, jelly, fakes = servers
    emby = seed_server(session, "emby", name="Emby")
    session.add(LibraryItem(server_id=emby.id, library_key="1", item_key="e11", item_type="movie",
                            title="Alien", tmdb_id=11, match_source=MatchSource.GUID.value))
    session.commit()
    fakes["Emby"] = FakeServer({"e11": "Alien"}, {})
    _road_trip(fakes)
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")
    playlist_sync.run(session)
    jelly_copy = next(c for c in session.exec(select(PlaylistCopy)).all() if c.target_server_id == jelly.id)
    made_on_jellyfin = jelly_copy.target_playlist_id

    playlist_sync.save_checklist(session, {(plex.id, "pl1"): "Road trip"}, {(plex.id, "pl1")},
                                 {(plex.id, "pl1"): {emby.id}})
    playlist_sync.run(session)

    assert fakes["Jellyfin"].deleted == [made_on_jellyfin] and fakes["Emby"].deleted == []
    session.expire_all()
    assert [c.target_server_id for c in session.exec(select(PlaylistCopy)).all()] == [emby.id]


def test_a_plain_message_goes_out_in_the_webhooks_format() -> None:
    import json

    import responses as mock

    with mock.RequestsMock() as rsps:
        rsps.add(mock.POST, "https://hooks.example.com/d", status=204)
        rsps.add(mock.POST, "https://hooks.example.com/g", status=200)
        assert notifier.send_message("https://hooks.example.com/d", "Sync had 1 problem", ["A → B: Error"], "discord")
        assert notifier.send_message("https://hooks.example.com/g", "Sync had 1 problem", ["A → B: Error"], "generic")
        discord, generic = (json.loads(c.request.body) for c in rsps.calls)
    assert discord["embeds"][0]["title"] == "Sync had 1 problem" and "A → B: Error" in discord["embeds"][0]["description"]
    assert generic == {"event": "franchisarr.message", "title": "Sync had 1 problem", "lines": ["A → B: Error"]}


# ------------------------------------------------------------------ sync every playlist


def _switches(session: Session, *, every: bool = False) -> None:
    playlist_sync.set_sync_all(session, every)


def test_sync_every_playlist_adopts_new_ones_but_never_the_copies(session: Session, servers) -> None:
    plex, jelly, fakes = servers
    _road_trip(fakes)
    _switches(session, every=True)

    playlist_sync.run(session)
    assert [t for t, _ in fakes["Jellyfin"].created] == ["Road trip"]

    fakes["Plex"].add("pl9", "Date night", [_film("p11", "Alien")])       # made later
    playlist_sync.run(session)

    session.expire_all()
    sources = {(s.source_server_id, s.title) for s in session.exec(select(PlaylistSync)).all()}
    assert sources == {(plex.id, "Road trip"), (plex.id, "Date night")}, "Jellyfin's copies aren't adopted"
    assert fakes["Plex"].created == [], "nothing copied back"


def test_a_playlist_switched_off_stays_off_while_every_playlist_syncs(session: Session, servers) -> None:
    plex, _, fakes = servers
    _road_trip(fakes)
    fakes["Plex"].add("pl9", "Date night", [_film("p11", "Alien")])
    _switches(session, every=True)
    playlist_sync.exclude(session, plex.id, "pl9", "Date night")      # "Don't sync" before it's adopted

    playlist_sync.run(session)
    road = session.exec(select(PlaylistSync).where(PlaylistSync.title == "Road trip")).one()
    playlist_sync.disable(session, road.id)                            # "Stop syncing" afterwards
    playlist_sync.run(session)

    session.expire_all()
    assert {(s.title, s.enabled) for s in session.exec(select(PlaylistSync)).all()} == {
        ("Road trip", False), ("Date night", False)}
    assert [t for t, _ in fakes["Jellyfin"].created] == ["Road trip"], "Date night never synced"


def test_turning_every_playlist_off_keeps_the_ones_picked_by_hand(session: Session, servers) -> None:
    plex, _, fakes = servers
    _road_trip(fakes)
    fakes["Plex"].add("pl9", "Date night", [_film("p11", "Alien")])
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")          # picked by hand
    _switches(session, every=True)
    playlist_sync.run(session)

    _switches(session, every=False)

    session.expire_all()
    assert [s.title for s in session.exec(select(PlaylistSync)).all()] == ["Road trip"]


def test_tick_new_automatically_and_the_defaults_save_with_the_checklist(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(playlist_sync, "run_in_background", lambda trigger: True)
    page = client.get(f"{BASE}/playlists").text
    assert 'name="every"' in page and 'name="franchisarr"' not in page, "that switch is the Franchisarr's tab now"
    assert 'name="default" value="2"' in page and "→ Jellyfin (default)" in page

    client.post(f"{BASE}/playlists/save", data={"every": "1", "default": ["1"], "row": "1|pl1",
                                                "title|1|pl1": "Road trip", "on": "1|pl1"})

    page = client.get(f"{BASE}/playlists").text
    assert 'name="every" value="1" checked' in page
    assert 'name="on" value="1|pl1" checked' in page
    assert "→ nowhere (default)" in page, "Plex's playlist can't go to Plex, and Jellyfin was unticked"
    with Session(get_engine()) as session:
        assert playlist_sync.default_targets(session) == {1}
