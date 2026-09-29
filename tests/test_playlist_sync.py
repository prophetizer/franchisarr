"""Playlist sync: chosen playlists copied from their home server to the others."""

from __future__ import annotations

import json
from dataclasses import replace

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
    """A server's playlists and library, as the sync sees them through its client. A playlist's
    items are PlaylistItemRefs, each given an entry id when it goes in, as a real server does."""

    def __init__(self, films: dict[str, str], episodes: dict[str, list[tuple[int, int, str]]]) -> None:
        self.films, self.episodes = films, episodes      # key -> title; show key -> (season, episode, key)
        self.playlists: dict[str, dict] = {}
        self.created: list[tuple[str, list]] = []
        self.deleted: list[str] = []
        self.renamed: list[tuple[str, str]] = []
        self.posters: dict[str, bytes] = {}
        self.down = False
        self._next = 100
        self._entry = 0

    def add(self, pid: str, title: str, items: list[PlaylistItemRef], **extra) -> None:
        self.playlists[pid] = {"title": title, "items": items, **extra}

    def _stamp(self, refs: list[PlaylistItemRef]) -> list[PlaylistItemRef]:
        out = []
        for ref in refs:
            if not ref.entry_id:
                self._entry += 1
                ref = replace(ref, entry_id=f"x{self._entry}")
            out.append(ref)
        return out

    def _ref(self, raw: str) -> PlaylistItemRef:
        key = raw.removeprefix("raw:")
        if key in self.films:
            return PlaylistItemRef("movie", key, self.films[key])
        for show, rows in self.episodes.items():
            for season, number, k in rows:
                if k == key:
                    return PlaylistItemRef("episode", key, f"{show} S{season:02d}E{number:02d}", show_key=show,
                                           season=season, episode=number)
        return PlaylistItemRef("other", key, key)

    def keys(self, pid: str) -> list[str]:
        return [r.key for r in self.playlists[pid]["items"]]

    def list_playlists(self):  # noqa: ANN201
        if self.down:
            raise ConnectionError("down")
        return [PlaylistInfo(pid, p["title"], p.get("smart", False), p.get("video", True), len(p["items"]))
                for pid, p in self.playlists.items()]

    def playlist_items(self, pid):  # noqa: ANN001, ANN201
        self.playlists[pid]["items"] = self._stamp(self.playlists[pid]["items"])
        return list(self.playlists[pid]["items"])

    def playlist_entries(self, films, shows):  # noqa: ANN001, ANN201
        out = [PlaylistEntry(raw=f"raw:{k}", aired=None, key=k) for k in films if k in self.films]
        for show in shows:
            out += [PlaylistEntry(raw=f"raw:{k}", aired=None, show_key=show, season=s, episode=e, key=k)
                    for s, e, k in self.episodes.get(show, [])]
        return out

    def create_playlist(self, title, raws):  # noqa: ANN001, ANN201
        self._next += 1
        pid = f"new{self._next}"
        self.playlists[pid] = {"title": title, "items": [self._ref(r) for r in raws]}
        self.created.append((title, list(raws)))
        return pid

    def delete_playlist_id(self, pid):  # noqa: ANN001, ANN201
        self.playlists.pop(pid, None)
        self.deleted.append(pid)

    def remove_playlist_entries(self, pid, entry_ids):  # noqa: ANN001, ANN201
        self.playlists[pid]["items"] = [r for r in self.playlists[pid]["items"] if r.entry_id not in entry_ids]

    def append_to_playlist(self, pid, raws):  # noqa: ANN001, ANN201
        self.playlists[pid]["items"] = self._stamp(self.playlists[pid]["items"] + [self._ref(r) for r in raws])

    def move_playlist_entry(self, pid, entry_id, index, after):  # noqa: ANN001, ANN201
        items = self.playlists[pid]["items"]
        ref = next(r for r in items if r.entry_id == entry_id)
        items.remove(ref)
        items.insert(index, ref)

    def rename_playlist(self, pid, title):  # noqa: ANN001, ANN201
        self.playlists[pid]["title"] = title
        self.renamed.append((pid, title))

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
    missing = json.loads(copy.unmatched_titles)
    assert {"title": "Aliens", "why": "not on Jellyfin", "movie": 12} in missing, "with its id, for Add"
    assert {"title": "Holiday video", "why": "not in a library Franchisarr scans"} in missing
    assert {"title": "Breaking Bad S02E01", "why": "episode not on Jellyfin"} in missing
    assert fakes["Jellyfin"].posters == {copy.target_playlist_id: b"\xff\xd8poster"}, "the source's own poster"
    assert state.created == 1 and fakes["Plex"].created == [], "nothing is copied back to the source"


def test_nothing_changes_when_nothing_changed(session: Session, servers) -> None:
    plex, _, fakes = servers
    _road_trip(fakes)
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")
    playlist_sync.run(session)

    state = playlist_sync.run(session)

    assert state.unchanged >= 1 and len(fakes["Jellyfin"].created) == 1 and fakes["Jellyfin"].deleted == []


def test_an_edit_at_the_source_edits_the_copy_in_place(session: Session, servers) -> None:
    plex, _, fakes = servers
    _road_trip(fakes)
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")
    playlist_sync.run(session)
    first = _copy(session).target_playlist_id

    fakes["Plex"].playlists["pl1"]["items"] = [_film("p11", "Alien")]
    fakes["Plex"].playlists["pl1"]["title"] = "Space trip"
    playlist_sync.run(session)

    assert _copy(session).target_playlist_id == first and fakes["Jellyfin"].deleted == []
    assert fakes["Jellyfin"].keys(first) == ["j11"], "Breaking Bad S01E01 came off"
    assert fakes["Jellyfin"].playlists[first]["title"] == "Space trip", "a rename follows the source"


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


# ------------------------------------------------------------------ both ways (0.43.0)


def _synced(session: Session, servers) -> tuple:  # noqa: ANN001
    """Road trip synced once, so the next run is a two-way one; returns the copy's id too."""
    plex, jelly, fakes = servers
    _road_trip(fakes)
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")
    playlist_sync.run(session)       # the first sync copies, as one-way did
    return plex, jelly, fakes, _copy(session).target_playlist_id


def test_merge_takes_adds_and_removes_from_every_side() -> None:
    before = ["a", "b", "c"]
    merged = playlist_sync.merge(before, [(["a", "b", "c"], ["a", "b", "x", "c"]),     # x added after b
                                          (["a", "c"], ["c"]),                        # a removed
                                          (None, ["q"])])                             # no record: ignored
    assert merged == ["b", "x", "c"]


def test_merge_adds_a_title_added_on_two_sides_once_and_follows_the_source_order() -> None:
    assert playlist_sync.merge(["a"], [(["a"], ["a", "x"]), (["a"], ["x", "a"])]) == ["a", "x"]
    assert playlist_sync.merge(["a", "b", "c"], [(["a", "b", "c"], ["c", "a", "b"])], ["c", "a", "b"]) == ["c", "a", "b"]


def test_a_title_added_to_a_copy_goes_onto_the_source(session: Session, servers) -> None:
    plex, jelly, fakes, copy_id = _synced(session, servers)
    fakes["Plex"].films["p13"] = "Prometheus"
    fakes["Jellyfin"].films["j13"] = "Prometheus"
    for server, key in ((plex, "p13"), (jelly, "j13")):
        session.add(LibraryItem(server_id=server.id, library_key="1", item_key=key, item_type="movie",
                                title="Prometheus", tmdb_id=13, match_source=MatchSource.GUID.value))
    session.commit()
    items = fakes["Jellyfin"].playlists[copy_id]["items"]
    items.insert(1, _film("j13", "Prometheus"))                               # someone adds it on Jellyfin

    state = playlist_sync.run(session)

    assert fakes["Plex"].keys("pl1") == ["p11", "p13", "p12", "home1", "pe1", "pe2"], "after Alien, as on Jellyfin"
    assert fakes["Jellyfin"].keys(copy_id) == ["j11", "j13", "je1"] and state.updated >= 1


def test_a_title_removed_from_a_copy_comes_off_the_source(session: Session, servers) -> None:
    plex, jelly, fakes, copy_id = _synced(session, servers)
    fakes["Jellyfin"].playlists[copy_id]["items"] = [r for r in fakes["Jellyfin"].playlists[copy_id]["items"]
                                                     if r.key != "je1"]

    playlist_sync.run(session)

    assert fakes["Plex"].keys("pl1") == ["p11", "p12", "home1", "pe2"], "S01E01 is gone from the source too"
    assert fakes["Jellyfin"].keys(copy_id) == ["j11"]


def test_what_a_copy_cant_hold_is_never_taken_for_a_removal(session: Session, servers) -> None:
    plex, jelly, fakes, copy_id = _synced(session, servers)

    playlist_sync.run(session)
    playlist_sync.run(session)

    assert fakes["Plex"].keys("pl1") == ["p11", "p12", "home1", "pe1", "pe2"], "Aliens and the rest stay on Plex"


def test_the_source_decides_the_order(session: Session, servers) -> None:
    plex, jelly, fakes, copy_id = _synced(session, servers)
    items = fakes["Jellyfin"].playlists[copy_id]["items"]
    items.reverse()                                                            # reordered on the copy
    playlist_sync.run(session)
    assert fakes["Jellyfin"].keys(copy_id) == ["j11", "je1"], "put back in the source's order"

    source = fakes["Plex"].playlists["pl1"]["items"]
    source.insert(0, source.pop(3))                                            # S01E01 first on Plex
    playlist_sync.run(session)
    assert fakes["Jellyfin"].keys(copy_id) == ["je1", "j11"]


def test_deleting_a_copy_stops_copying_there(session: Session, servers) -> None:
    plex, jelly, fakes, copy_id = _synced(session, servers)
    del fakes["Jellyfin"].playlists[copy_id]

    playlist_sync.run(session)
    playlist_sync.run(session)

    session.expire_all()
    sync = session.exec(select(PlaylistSync)).one()
    assert sync.enabled and json.loads(sync.targets) == [], "Jellyfin unticked, the sync kept"
    assert fakes["Jellyfin"].playlists == {} and session.exec(select(PlaylistCopy)).all() == []
    assert "pl1" in fakes["Plex"].playlists, "the original stays"


def test_renaming_a_copy_renames_the_source(session: Session, servers) -> None:
    plex, jelly, fakes, copy_id = _synced(session, servers)
    fakes["Jellyfin"].playlists[copy_id]["title"] = "Holiday drive"

    playlist_sync.run(session)

    assert fakes["Plex"].playlists["pl1"]["title"] == "Holiday drive"
    assert session.exec(select(PlaylistSync)).one().title == "Holiday drive"


def test_a_server_that_cant_move_entries_keeps_what_it_cant_put_back(monkeypatch) -> None:
    """Jellyfin rewrites the tail to reorder; a home video in the tail couldn't be put back, so
    it isn't taken off -- the order is left as it is instead."""
    from app.clients import media_server
    from app.clients.media_server import edit_in_place

    monkeypatch.setattr(media_server, "_pause", lambda seconds: None)

    server = FakeServer({"a": "A", "b": "B"}, {})
    server.can_move_playlist_entries = False
    server.add("p", "Mine", [_film("a", "A"), PlaylistItemRef("other", "home", "Home video"), _film("b", "B")])

    edit_in_place(server, "p", [("b", "raw:b"), ("home", None), ("a", "raw:a")])

    assert sorted(server.keys("p")) == ["a", "b", "home"], "nothing lost"


def test_link_them_merges_a_same_named_playlist_into_the_sync(session: Session, servers) -> None:
    plex, jelly, fakes = servers
    _road_trip(fakes)
    fakes["Jellyfin"].films["j14"] = "Alien: Romulus"
    session.add(LibraryItem(server_id=jelly.id, library_key="1", item_key="j14", item_type="movie",
                            title="Alien: Romulus", tmdb_id=14, match_source=MatchSource.GUID.value))
    session.commit()
    fakes["Jellyfin"].add("mine", "Road trip", [_film("j14", "Alien: Romulus")])
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")
    playlist_sync.run(session)
    blocked = _copy(session)
    assert blocked.status == "blocked"

    assert playlist_sync.link(session, blocked.id) is None
    playlist_sync.run(session)

    assert fakes["Jellyfin"].keys("mine") == ["j14", "j11", "je1"], "its own title kept, the source's added"
    assert fakes["Jellyfin"].created == [], "the same playlist, linked"
    copy = _copy(session)
    assert copy.status == "ok" and copy.target_playlist_id == "mine"
    missing = json.loads(session.exec(select(PlaylistSync)).one().source_unmatched_titles)
    assert {"title": "Alien: Romulus", "why": "not on Plex", "movie": 14} in missing, "Plex can't hold it"


def test_a_smart_source_stays_one_way(session: Session, servers) -> None:
    plex, jelly, fakes = servers
    _road_trip(fakes, smart=True)
    playlist_sync.enable(session, plex.id, "pl1", "Road trip")
    playlist_sync.run(session)
    copy_id = _copy(session).target_playlist_id
    fakes["Jellyfin"].playlists[copy_id]["items"].pop()

    playlist_sync.run(session)

    assert fakes["Jellyfin"].keys(copy_id) == ["j11", "je1"], "the copy follows its rules"
    assert fakes["Plex"].keys("pl1") == ["p11", "p12", "home1", "pe1", "pe2"], "and nothing is written to it"


def test_a_sync_from_before_two_way_starts_as_one_way(session: Session, servers) -> None:
    """Upgrading: no record of what each side held, so the first run treats the source as it
    stands -- the copy's own edits since are overwritten one last time, nothing is lost from
    the source."""
    plex, jelly, fakes, copy_id = _synced(session, servers)
    sync = session.exec(select(PlaylistSync)).one()
    sync.merged = sync.source_seen = None
    copy = _copy(session)
    copy.seen = None
    session.add(sync); session.add(copy); session.commit()
    fakes["Jellyfin"].playlists[copy_id]["items"].pop(0)

    playlist_sync.run(session)

    assert fakes["Plex"].keys("pl1") == ["p11", "p12", "home1", "pe1", "pe2"]
    assert fakes["Jellyfin"].keys(copy_id) == ["j11", "je1"]


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
        test_client.fakes = fakes  # type: ignore[attr-defined]
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


def test_the_page_offers_add_for_whats_missing_and_link_for_a_blocked_copy(client: TestClient, monkeypatch) -> None:
    from app.models import RadarrInstance, RadarrMovie

    monkeypatch.setattr(playlist_sync, "run_in_background", lambda trigger: True)
    with Session(get_engine()) as session:
        sync = PlaylistSync(source_server_id=1, source_playlist_id="pl1", title="Road trip", merged="[]",
                            source_unmatched=1, source_unmatched_titles=json.dumps([
                                {"title": "Alien: Romulus", "why": "not on Plex", "movie": 14}]))
        session.add(sync); session.commit(); session.refresh(sync)
        session.add(PlaylistCopy(sync_id=sync.id, target_server_id=2, status="blocked",
                                 message="Jellyfin already has a playlist called “Road trip” that sync didn't make."))
        radarr = RadarrInstance(name="Radarr", url="http://radarr:7878", api_key="k" * 32)
        session.add(radarr); session.commit(); session.refresh(radarr)
        session.add(RadarrMovie(instance_id=radarr.id, tmdb_id=15, title="In Radarr already"))
        session.commit()
        copy_id = session.exec(select(PlaylistCopy)).one().id

    page = client.get(f"{BASE}/playlists").text
    assert f'hx-get="{BASE}/add/14"' in page and 'id="add-dialog"' in page, "Add for a film Radarr doesn't have"
    assert f'hx-post="{BASE}/playlists/copies/{copy_id}/link"' in page and "Link them" in page

    client.fakes["Jellyfin"].add("mine", "Road trip", [])  # type: ignore[attr-defined]
    linked = client.post(f"{BASE}/playlists/copies/{copy_id}/link", headers={"HX-Request": "true"})
    assert linked.status_code == 200 and linked.headers["HX-Redirect"].endswith("/playlists?saved=1")
    with Session(get_engine()) as session:
        copy = session.get(PlaylistCopy, copy_id)
        assert (copy.status, copy.target_playlist_id, copy.seen) == ("ok", "mine", "[]")
