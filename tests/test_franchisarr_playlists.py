"""Franchisarr's own playlists, kept current in place (0.42.0)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.clients.media_server import edit_in_place
from app.db import get_engine
from app.models import (
    Franchise, FranchiseMember, FranchisarrPlaylist, FranchisarrPlaylistCopy, IncludedLibrary, ItemType,
    LibraryItem, MatchSource, MediaServer,
)
from app.services import franchisarr_playlists, media_server_service, playlist_poster, playlist_service, playlist_sync
from app.services.settings_service import SettingKey, set_setting
from tests.conftest import seed_server
from tests.playlist_fakes import FakeMediaServer

BASE = "/franchisarr"
PASSWORD = "correct horse battery staple"
TITLE = "Star Wars (Franchisarr)"
REFS = [(ItemType.MOVIE.value, 11), (ItemType.MOVIE.value, 1891)]
DATES = {11: date(1977, 5, 25), 1891: date(1980, 5, 21), 1892: date(1983, 5, 25), 1893: date(1999, 5, 19)}


def _own(session: Session, server: MediaServer, tmdb_id: int) -> None:
    prefix = "p" if server.kind == "plex" else "j"
    session.add(LibraryItem(server_id=server.id, library_key="1", item_key=f"{prefix}{tmdb_id}",
                            item_type="movie", title=str(tmdb_id), tmdb_id=tmdb_id,
                            match_source=MatchSource.GUID.value))
    session.commit()


def _world(session: Session, monkeypatch) -> tuple[MediaServer, MediaServer, dict[str, FakeMediaServer]]:
    """Living room (Plex) and Attic (Jellyfin), each owning Star Wars and Empire; the franchise
    also has Jedi and The Phantom Menace, which nobody owns yet."""
    living, attic = seed_server(session, "plex", name="Living room"), seed_server(session, "jellyfin", name="Attic")
    for server in (living, attic):
        session.add(IncludedLibrary(server_id=server.id, library_key="1", library_name="Films",
                                    library_type="movie", enabled=True))
        for tmdb_id in (11, 1891):
            _own(session, server, tmdb_id)
    session.add(Franchise(wikidata_id="Q462", name="Star Wars", kind="media franchise"))
    for tmdb_id, when in DATES.items():
        session.add(FranchiseMember(franchise_id="Q462", item_type="movie", tmdb_id=tmdb_id, title=str(tmdb_id),
                                    year=when.year))
    session.commit()
    fakes = {name: FakeMediaServer({f"{prefix}{t}": d for t, d in DATES.items()})
             for name, prefix in (("Living room", "p"), ("Attic", "j"))}
    monkeypatch.setattr(media_server_service, "client_for", lambda s: fakes[s.name])
    monkeypatch.setattr(playlist_poster, "render", lambda *a, **k: b"\xff\xd8poster")
    monkeypatch.setattr(playlist_sync, "_state", playlist_sync.SyncProgress())
    return living, attic, fakes


@pytest.fixture
def world(session: Session, monkeypatch):
    return _world(session, monkeypatch)


def _make(session: Session, server_id: int | None = None):  # noqa: ANN202
    return franchisarr_playlists.make(session, "franchises", "Q462", "Star Wars", REFS,
                                      playlist_service.PosterArt(backdrop_url="https://x/b.jpg"),
                                      server_id=server_id)


def _only(fake: FakeMediaServer) -> str:
    (pid,) = fake.titled(TITLE)
    return pid


# ------------------------------------------------------------------ editing in place


@pytest.mark.parametrize("before,after", [
    (["a", "b", "c"], ["a", "b", "c"]),
    (["a", "b", "c"], ["a", "x", "b", "c"]),          # one added in the middle
    (["a", "b", "c"], ["x", "a", "b", "c"]),          # one added at the front
    (["a", "b", "c"], ["a", "c"]),                     # one removed
    (["a", "b", "c"], ["c", "b", "a"]),                # reversed
    (["a", "a", "b"], ["a", "b", "a"]),                # a title twice
    ([], ["a", "b"]),
    (["a", "b"], []),
])
def test_editing_in_place_reaches_exactly_the_wanted_order(before: list[str], after: list[str]) -> None:
    server = FakeMediaServer()
    server.add("p1", "Mine", before)
    kept = {e for e, k in server.playlists["p1"]["entries"] if k in after}

    changed = edit_in_place(server, "p1", [(k, k) for k in after])

    assert server.keys("p1") == after and changed == (before != after)
    assert "create" not in server.edits() and "delete" not in server.edits(), "the same playlist throughout"
    if before != after and set(before) <= set(after):
        assert kept <= {e for e, _ in server.playlists["p1"]["entries"]}, "nothing already there is re-added"


@pytest.mark.parametrize("before,after,removed", [
    (["a", "b", "c"], ["a", "b", "c", "d"], 0),       # a new one at the end: nothing removed
    (["a", "b", "c"], ["a", "x", "b", "c"], 2),       # in the middle: the tail from there
    (["a", "b", "c"], ["a", "c"], 2),
    (["a", "b", "c"], ["c", "b", "a"], 3),
])
def test_a_server_that_cant_move_entries_gets_the_tail_rewritten(before, after, removed) -> None:  # noqa: ANN001
    server = FakeMediaServer()
    server.can_move_playlist_entries = False
    server.add("p1", "Mine", before)

    edit_in_place(server, "p1", [(k, k) for k in after])

    assert server.keys("p1") == after and "move" not in server.edits()
    assert sum(op[2] for op in server.log if op[0] == "remove") == removed


def test_editing_in_place_waits_for_a_server_that_lists_an_addition_late(monkeypatch) -> None:
    from app.clients import media_server

    server = FakeMediaServer()
    server.add("p1", "Mine", ["a", "b"])
    real_items, late = server.playlist_items, {"reads": 0}

    def slow_items(pid):  # noqa: ANN001, ANN202 -- the first read after the add misses the new entry
        refs = real_items(pid)
        late["reads"] += 1
        return [r for r in refs if r.key != "x"] if late["reads"] == 2 else refs

    server.playlist_items = slow_items  # type: ignore[method-assign]
    pauses = []
    monkeypatch.setattr(media_server, "_pause", pauses.append)

    edit_in_place(server, "p1", [("x", "x"), ("a", "a"), ("b", "b")])

    assert server.keys("p1") == ["x", "a", "b"] and len(pauses) == 1


def test_a_pass_that_doesnt_read_back_right_is_run_again(monkeypatch) -> None:
    """Emby 4.10, now and then: an edit acts on the playlist as it was a moment before."""
    from app.clients import media_server

    monkeypatch.setattr(media_server, "_pause", lambda seconds: None)
    server = FakeMediaServer()
    server.add("p1", "Mine", ["a", "b", "c"])
    real_remove, calls = server.remove_playlist_entries, {"n": 0}

    def flaky_remove(pid, entry_ids):  # noqa: ANN001, ANN202 -- the first removal goes nowhere
        calls["n"] += 1
        if calls["n"] > 1:
            real_remove(pid, entry_ids)

    server.remove_playlist_entries = flaky_remove  # type: ignore[method-assign]

    assert edit_in_place(server, "p1", [("a", "a"), ("c", "c")]) is True
    assert server.keys("p1") == ["a", "c"] and calls["n"] == 2


def test_editing_in_place_skips_what_the_server_wont_take(monkeypatch) -> None:
    from app.clients import media_server

    monkeypatch.setattr(media_server, "_pause", lambda seconds: None)
    server = FakeMediaServer()
    server.add("p1", "Mine", ["a", "c"])
    real_append = server.append_to_playlist
    server.append_to_playlist = lambda pid, raws: real_append(pid, [r for r in raws if r != "gone"])  # type: ignore[method-assign]

    edit_in_place(server, "p1", [("gone", "gone"), ("a", "a"), ("b", "b"), ("c", "c")])

    assert server.keys("p1") == ["a", "b", "c"]


# ------------------------------------------------------------------ making one


def test_the_button_builds_it_on_every_server_in_release_order_and_adds_it_to_the_set(
    session: Session, world
) -> None:
    living, attic, fakes = world

    result = _make(session)

    assert result.made_any and [s.server for s in result.servers] == ["Living room", "Attic"]
    assert fakes["Living room"].keys(_only(fakes["Living room"])) == ["p11", "p1891"]
    assert fakes["Attic"].keys(_only(fakes["Attic"])) == ["j11", "j1891"]
    entry = session.exec(select(FranchisarrPlaylist)).one()
    assert (entry.kind, entry.ref, entry.servers) == ("franchises", "Q462", None)
    assert fakes["Living room"].posters, "with its poster"


def test_pressing_it_again_with_nothing_new_touches_nothing(session: Session, world) -> None:
    living, attic, fakes = world
    _make(session)
    fakes["Living room"].log.clear()

    _make(session)

    assert fakes["Living room"].edits() == [], "no entries fetched either: the library hasn't changed"


def test_on_one_server_builds_only_there_and_keeps_following_the_defaults(session: Session, world) -> None:
    living, attic, fakes = world

    result = _make(session, attic.id)

    assert result.only == "Attic" and fakes["Living room"].playlists == {} and fakes["Attic"].titled(TITLE)
    assert session.exec(select(FranchisarrPlaylist)).one().servers is None, "the defaults already cover Attic"


def test_on_a_server_the_defaults_leave_out_spells_the_servers_out(session: Session, world) -> None:
    living, attic, fakes = world
    franchisarr_playlists.set_default_servers(session, {living.id})

    _make(session, attic.id)

    assert session.exec(select(FranchisarrPlaylist)).one().servers == f"[{living.id}, {attic.id}]"


def test_a_server_holding_none_of_it_says_so(session: Session, world) -> None:
    living, attic, fakes = world
    empty = seed_server(session, "emby", name="Empty")
    fakes["Empty"] = FakeMediaServer()

    result = _make(session, empty.id)

    assert result.servers == [] and result.only == "Empty" and not fakes["Empty"].playlists


def test_add_many_skips_a_server_with_fewer_than_two(session: Session, world) -> None:
    living, attic, fakes = world
    session.delete(session.exec(select(LibraryItem).where(LibraryItem.item_key == "j1891")).one())
    session.commit()

    result = franchisarr_playlists.make(session, "franchises", "Q462", "Star Wars", REFS, None, min_items=2)

    assert [s.server for s in result.servers] == ["Living room"] and result.skipped == 1
    assert not fakes["Attic"].playlists


def test_a_failure_is_reported_not_raised(session: Session, world) -> None:
    living, attic, fakes = world
    fakes["Attic"].down = True

    result = _make(session)

    attic_result = next(s for s in result.servers if s.server == "Attic")
    assert "ConnectionError" in attic_result.error and fakes["Living room"].titled(TITLE)


# ------------------------------------------------------------------ keeping it current


def test_a_film_you_get_later_goes_in_where_it_belongs_in_the_same_playlist(session: Session, world) -> None:
    living, attic, fakes = world
    _make(session)
    before = _only(fakes["Living room"])
    _own(session, living, 1893)           # The Phantom Menace, 1999: at the end
    playlist_sync.run(session)
    assert fakes["Living room"].keys(before) == ["p11", "p1891", "p1893"]
    fakes["Living room"].log.clear()
    _own(session, living, 1892)           # Return of the Jedi, 1983: between Empire and Menace

    playlist_sync.run(session)

    assert _only(fakes["Living room"]) == before, "edited in place, not remade"
    assert fakes["Living room"].keys(before) == ["p11", "p1891", "p1892", "p1893"]
    assert "create" not in fakes["Living room"].edits() and "move" in fakes["Living room"].edits()
    assert fakes["Attic"].keys(_only(fakes["Attic"])) == ["j11", "j1891"], "Attic doesn't have them"
    assert fakes["Living room"].posters[before], "a new poster for the new counts"


def test_a_film_that_leaves_the_library_leaves_the_playlist(session: Session, world) -> None:
    living, attic, fakes = world
    _own(session, living, 1892)
    _make(session)
    session.delete(session.exec(select(LibraryItem).where(LibraryItem.item_key == "p1891")).one())
    session.commit()

    playlist_sync.run(session)

    assert fakes["Living room"].keys(_only(fakes["Living room"])) == ["p11", "p1892"]


def test_too_few_left_on_a_server_deletes_it_there_and_it_comes_back(session: Session, world) -> None:
    living, attic, fakes = world
    _make(session)
    for key in ("j11", "j1891"):
        session.delete(session.exec(select(LibraryItem).where(LibraryItem.item_key == key)).one())
    session.commit()

    playlist_sync.run(session)

    assert fakes["Attic"].titled(TITLE) == [] and fakes["Living room"].titled(TITLE)
    assert session.exec(select(FranchisarrPlaylist)).one(), "still in the set"
    _own(session, attic, 11)
    playlist_sync.run(session)
    assert fakes["Attic"].keys(_only(fakes["Attic"])) == ["j11"]


def test_a_new_server_gets_it_at_the_next_sync(session: Session, world) -> None:
    living, attic, fakes = world
    _make(session)
    emby = seed_server(session, "emby", name="Den")
    session.add(IncludedLibrary(server_id=emby.id, library_key="1", library_name="Films", library_type="movie",
                                enabled=True))
    _own(session, emby, 11)
    fakes["Den"] = FakeMediaServer({"j11": date(1977, 5, 25)})

    playlist_sync.run(session)

    assert fakes["Den"].keys(_only(fakes["Den"])) == ["j11"]


def test_untaking_a_server_from_the_defaults_deletes_them_there(session: Session, world) -> None:
    living, attic, fakes = world
    _make(session)

    franchisarr_playlists.set_default_servers(session, {living.id})
    playlist_sync.run(session)

    assert fakes["Attic"].titled(TITLE) == [] and fakes["Living room"].titled(TITLE)


def test_a_page_that_is_gone_leaves_its_playlists_alone(session: Session, world) -> None:
    living, attic, fakes = world
    _make(session)
    session.delete(session.get(Franchise, "Q462"))
    session.commit()
    fakes["Living room"].log.clear()

    playlist_sync.run(session)

    assert fakes["Living room"].titled(TITLE) and fakes["Living room"].edits() == []


# ------------------------------------------------------------------ deleting


def test_deleting_it_on_one_server_deletes_it_everywhere_and_drops_it(session: Session, world) -> None:
    living, attic, fakes = world
    _make(session)
    fakes["Attic"].delete_playlist_id(_only(fakes["Attic"]))

    state = playlist_sync.run(session)

    assert fakes["Living room"].titled(TITLE) == [] and state.deleted == 1
    assert session.exec(select(FranchisarrPlaylist)).all() == []
    assert session.exec(select(FranchisarrPlaylistCopy)).all() == []


def test_a_server_that_cant_be_reached_is_never_taken_for_a_deletion(session: Session, world) -> None:
    living, attic, fakes = world
    _make(session)
    fakes["Attic"].down = True

    playlist_sync.run(session)

    assert fakes["Living room"].titled(TITLE) and session.exec(select(FranchisarrPlaylist)).one()


def test_a_copy_on_a_server_thats_off_is_deleted_when_it_is_back(session: Session, world) -> None:
    living, attic, fakes = world
    _make(session)
    media_server_service.set_enabled(session, attic, False)
    fakes["Living room"].delete_playlist_id(_only(fakes["Living room"]))

    playlist_sync.run(session)

    assert fakes["Attic"].titled(TITLE), "Attic is off: untouched"
    assert session.exec(select(FranchisarrPlaylist)).one().removed_at is not None, "waiting for Attic"
    assert franchisarr_playlists.page(session) == [], "and gone from the page"

    media_server_service.set_enabled(session, attic, True)
    playlist_sync.run(session)

    assert fakes["Attic"].titled(TITLE) == [] and session.exec(select(FranchisarrPlaylist)).all() == []


def test_remove_on_the_page_deletes_it_everywhere(session: Session, world) -> None:
    living, attic, fakes = world
    _make(session)

    assert franchisarr_playlists.remove(session, session.exec(select(FranchisarrPlaylist)).one().id) is None

    assert not fakes["Living room"].titled(TITLE) and not fakes["Attic"].titled(TITLE)
    assert session.exec(select(FranchisarrPlaylist)).all() == []


def test_cleaning_up_one_server_doesnt_spread(session: Session, world) -> None:
    living, attic, fakes = world
    _make(session)
    fakes["Attic"].delete_playlist_id(_only(fakes["Attic"]))   # what Clean up does there

    franchisarr_playlists.forget_server(session, attic.id)
    playlist_sync.run(session)

    assert fakes["Living room"].titled(TITLE) and not fakes["Attic"].titled(TITLE), "and not rebuilt there"
    assert franchisarr_playlists.default_servers(session) == {living.id}


# ------------------------------------------------------------------ the upgrade


def test_existing_playlists_are_taken_in_once(session: Session, world) -> None:
    living, attic, fakes = world
    set_setting(session, SettingKey.FRANCHISARR_PLAYLISTS_TO_ADOPT, "true")   # what 0029 does
    session.commit()
    assert playlist_sync.has_work(session), "a sync runs to take them in, with nothing ticked"
    fakes["Living room"].add("old1", TITLE, ["p11"])
    fakes["Attic"].add("old2", TITLE, ["j11", "j1891"])
    fakes["Attic"].add("old3", "Nobody Knows (Franchisarr)", ["j11"])

    playlist_sync.run(session)

    entry = session.exec(select(FranchisarrPlaylist)).one()
    assert (entry.kind, entry.ref) == ("franchises", "Q462")
    assert fakes["Living room"].keys("old1") == ["p11", "p1891"], "adopted and brought up to date, same id"
    assert "old3" in fakes["Attic"].playlists, "a name that's no page here is left alone"

    session.delete(entry)
    session.commit()
    assert not playlist_sync.has_work(session), "nothing ticked, nothing kept, nothing waiting"
    playlist_sync.run(session)
    assert session.exec(select(FranchisarrPlaylist)).all() == [], "only once"


# ------------------------------------------------------------------ the page


@pytest.fixture
def client(app_factory, monkeypatch):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            fakes = _world(session, monkeypatch)[2]
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        test_client.fakes = fakes  # type: ignore[attr-defined]
        yield test_client


def test_the_franchise_button_builds_and_the_tab_lists_it(client: TestClient) -> None:
    page = client.get(f"{BASE}/franchises/Q462").text
    assert f'hx-post="{BASE}/franchises/Q462/playlist"' in page and "On every server" in page
    assert "Make a playlist" in page and "Playlist kept on" not in page

    body = client.post(f"{BASE}/franchises/Q462/playlist", data={"server": "all"}).text
    assert TITLE in body and "kept current after every scan" in body

    page = client.get(f"{BASE}/franchises/Q462").text
    assert "✓ Playlist kept on Attic, Living room" in page and "Refresh playlist" in page, "in the banner (0.44.0)"
    assert page.index('class="heading-actions"') < page.index('id="playlist-result"'), "the result goes below it"

    tab = client.get(f"{BASE}/playlists/franchisarr").text
    assert "<h1>Playlists</h1>" in tab and 'aria-current="page">Franchisarr' in tab
    assert f'href="{BASE}/franchises/Q462">Star Wars</a>' in tab and "Living room:" in tab and "2 items" in tab
    assert "1 Franchisarr playlist kept current" in tab


def test_remove_and_default_servers_from_the_tab(client: TestClient) -> None:
    client.post(f"{BASE}/franchises/Q462/playlist", data={"server": "all"})
    with Session(get_engine()) as session:
        entry = session.exec(select(FranchisarrPlaylist)).one().id
        living = session.exec(select(MediaServer).where(MediaServer.name == "Living room")).one().id

    saved = client.post(f"{BASE}/playlists/franchisarr/servers", data={"server": [str(living)]})
    assert saved.status_code == 303 and saved.headers["location"].endswith("/playlists/franchisarr?saved=1")
    with Session(get_engine()) as session:
        assert franchisarr_playlists.default_servers(session) == {living}

    client.post(f"{BASE}/playlists/franchisarr/{entry}/remove")
    assert not client.fakes["Living room"].titled(TITLE)  # type: ignore[attr-defined]
    assert "None yet" in client.get(f"{BASE}/playlists/franchisarr").text
