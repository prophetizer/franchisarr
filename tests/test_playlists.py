"""Franchise, collection and director playlists on Plex, in release order."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.local_admin import create_local_admin
from app.clients import plex_client
from app.clients.plex_client import PlaylistEntry, _delete_playlists, _playlist_entries, _replace_playlist
from app.db import get_engine
from app.models import (
    Franchise, FranchiseMember, IncludedLibrary, ItemType, LibraryItem, MatchSource, MediaServer,
)
from app.services import playlist_service
from tests.conftest import seed_server

BASE = "/franchisarr"
PASSWORD = "correct horse battery staple"


# ------------------------------------------------------------------ fakes for plexapi objects


class FakeItem:
    """Stands in for a plexapi Movie/Episode: attributes live in __dict__, as _attr reads them."""

    def __init__(self, key: int, aired=None, year=None, season=None, index=None):  # noqa: ANN001
        self.__dict__.update(ratingKey=key, originallyAvailableAt=aired, year=year,
                             parentIndex=season, index=index, listType="video")


@dataclass
class FakePlaylist:
    title: str
    items: list = field(default_factory=list)
    deleted: bool = False

    def delete(self) -> None:
        self.deleted = True

    def addItems(self, items) -> None:  # noqa: ANN001, N802
        self.items.extend(items)


class FakeShow:
    def __init__(self, episodes):  # noqa: ANN001
        self._episodes = episodes

    def episodes(self):  # noqa: ANN201
        return list(self._episodes)


class FakeServer:
    def __init__(self, films: dict[int, FakeItem], shows: dict[int, FakeShow],
                 playlists: list[FakePlaylist] | None = None) -> None:
        self.films, self.shows = films, shows
        self._playlists = playlists or []
        self.fetch_calls: list[str] = []
        self.created: list[FakePlaylist] = []

    def fetchItems(self, ekey: str):  # noqa: ANN201, N802
        self.fetch_calls.append(ekey)
        keys = ekey.rsplit("/", 1)[1].split(",")
        return [self.films[int(k)] for k in keys if int(k) in self.films]

    def fetchItem(self, key: int):  # noqa: ANN201, N802
        from plexapi.exceptions import NotFound

        if key not in self.shows:
            raise NotFound("gone")
        return self.shows[key]

    def playlists(self):  # noqa: ANN201
        return list(self._playlists)

    def createPlaylist(self, title: str, items):  # noqa: ANN001, ANN201, N802
        playlist = FakePlaylist(title, list(items))
        self.created.append(playlist)
        return playlist


class FakeClient:
    def __init__(self, server: FakeServer) -> None:
        self.server = server


# ------------------------------------------------------------------ ordering


def test_films_and_episodes_interleave_by_release_date() -> None:
    """The MCU case: a show's episodes fall between the films as they were broadcast."""
    film_a = PlaylistEntry(raw="Avengers", aired=date(2012, 5, 4))
    film_b = PlaylistEntry(raw="Iron Man 3", aired=date(2013, 5, 3))
    ep1 = PlaylistEntry(raw="S1E1", aired=date(2013, 9, 24), show_key="shield", season=1, episode=1)
    ep0 = PlaylistEntry(raw="pilot-before", aired=date(2012, 12, 1), show_key="shield", season=1, episode=0)
    undated = PlaylistEntry(raw="Untitled", aired=None)

    ordered = playlist_service.order_entries([undated, ep1, film_b, ep0, film_a])

    assert [e.raw for e in ordered] == ["Avengers", "pilot-before", "Iron Man 3", "S1E1", "Untitled"]


def test_on_a_shared_date_a_film_comes_first_and_a_show_keeps_its_episode_order() -> None:
    day = date(2020, 1, 1)
    ordered = playlist_service.order_entries([
        PlaylistEntry(raw="E2", aired=day, show_key="s", season=1, episode=2),
        PlaylistEntry(raw="E1", aired=day, show_key="s", season=1, episode=1),
        PlaylistEntry(raw="Film", aired=day),
    ])
    assert [e.raw for e in ordered] == ["Film", "E1", "E2"]


# ------------------------------------------------------------------ talking to Plex


def test_entries_batch_the_films_skip_specials_and_date_undated_episodes_after_the_last() -> None:
    films = {1: FakeItem(1, aired=datetime(1977, 5, 25)), 2: FakeItem(2, year=1980)}
    show = FakeShow([
        FakeItem(11, aired=datetime(2019, 11, 12), season=1, index=1),
        FakeItem(12, aired=None, season=1, index=2),              # no date on Plex
        FakeItem(10, aired=datetime(2019, 1, 1), season=0, index=1),  # a special
    ])
    server = FakeServer(films, {100: show})

    entries = _playlist_entries(FakeClient(server), ["1", "2"], ["100", "999"])

    assert len(server.fetch_calls) == 1, "films come back in one batched request"
    by_key = {e.raw.ratingKey: e for e in entries}
    assert set(by_key) == {1, 2, 11, 12}, "the special and the vanished show are left out"
    assert by_key[2].aired == date(1980, 1, 1), "a film with only a year sorts by its year"
    assert by_key[12].aired == date(2019, 11, 12), "an undated episode stays after the one before it"


def test_replacing_touches_only_our_own_playlist_and_chunks_big_ones(monkeypatch) -> None:
    ours = FakePlaylist("Star Wars (Franchisarr)")
    theirs = FakePlaylist("Star Wars")
    server = FakeServer({}, {}, playlists=[ours, theirs])
    monkeypatch.setattr(plex_client, "PLAYLIST_CHUNK", 3)
    items = [FakeItem(k) for k in range(8)]

    _replace_playlist(FakeClient(server), "Star Wars (Franchisarr)", items)

    assert ours.deleted and not theirs.deleted
    created = server.created[0]
    assert created.title == "Star Wars (Franchisarr)"
    assert [i.ratingKey for i in created.items] == list(range(8)), "all of them, in order"


# ------------------------------------------------------------------ the service end to end


def _library(session: Session, kind: str = "plex") -> int:
    server = seed_server(session, kind, name="Living room" if kind == "plex" else "Attic")
    session.add(IncludedLibrary(server_id=server.id, library_key="1", library_name="Films",
                                library_type="movie", enabled=True))
    for tmdb_id, key, item_type in ((11, "1", "movie"), (1891, "2", "movie"), (82856, "100", "show")):
        session.add(LibraryItem(server_id=server.id, library_key="1", item_key=key, item_type=item_type,
                                title=str(tmdb_id), tmdb_id=tmdb_id, match_source=MatchSource.GUID.value))
    session.commit()
    return server.id


def test_build_orders_and_reports_what_went_in(session: Session, monkeypatch) -> None:
    _library(session)
    server = FakeServer(
        {1: FakeItem(1, aired=datetime(1977, 5, 25)), 2: FakeItem(2, aired=datetime(1980, 5, 21))},
        {100: FakeShow([FakeItem(101, aired=datetime(2019, 11, 12), season=1, index=1)])},
    )
    from app.services import media_server_service

    monkeypatch.setattr(media_server_service, "client_for", lambda s: _AsPlexClient(server))

    result = playlist_service.build(session, "Star Wars", [
        (ItemType.MOVIE.value, 11), (ItemType.MOVIE.value, 1891), (ItemType.SHOW.value, 82856)])

    assert result.title == "Star Wars (Franchisarr)" and result.made_any
    assert (result.servers[0].films, result.servers[0].shows, result.servers[0].episodes) == (2, 1, 1)
    assert [i.ratingKey for i in server.created[0].items] == [1, 2, 101]


class _AsPlexClient(FakeClient):
    def playlist_entries(self, films, shows):  # noqa: ANN001, ANN201
        return _playlist_entries(self, films, shows)

    def replace_playlist(self, title, items):  # noqa: ANN001, ANN201
        return _replace_playlist(self, title, items)


def test_jellyfin_and_emby_servers_get_playlists_too(session: Session, monkeypatch) -> None:
    from app.clients.media_server import PlaylistEntry
    from app.services import media_server_service

    _library(session, kind="jellyfin")
    built = []

    class Jelly:
        def playlist_entries(self, films, shows):  # noqa: ANN001, ANN201
            return [PlaylistEntry(raw=f, aired=None) for f in films]

        def replace_playlist(self, title, items):  # noqa: ANN001, ANN201
            built.append((title, items))

    monkeypatch.setattr(media_server_service, "client_for", lambda s: Jelly())

    result = playlist_service.build(session, "Star Wars", [(ItemType.MOVIE.value, 11)])

    assert result.made_any and built == [("Star Wars (Franchisarr)", ["1"])]


def test_a_plex_failure_is_reported_not_raised(session: Session, monkeypatch) -> None:
    _library(session)
    from app.services import media_server_service

    class Broken:
        def playlist_entries(self, *a):  # noqa: ANN002, ANN201
            raise ConnectionError("plex is down")

    monkeypatch.setattr(media_server_service, "client_for", lambda s: Broken())

    result = playlist_service.build(session, "Star Wars", [(ItemType.MOVIE.value, 11)])

    assert result.servers[0].error and "ConnectionError" in result.servers[0].error
    assert not result.made_any


# ------------------------------------------------------------------ the page


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            _library(session)
            session.add(Franchise(wikidata_id="Q462", name="Star Wars", kind="media franchise"))
            for tmdb_id, item_type in ((11, "movie"), (1891, "movie"), (82856, "show")):
                session.add(FranchiseMember(franchise_id="Q462", item_type=item_type, tmdb_id=tmdb_id,
                                            title=str(tmdb_id), year=2000))
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def test_the_franchise_page_offers_the_button_and_the_route_builds(client: TestClient, monkeypatch) -> None:
    page = client.get(f"{BASE}/franchises/Q462").text
    assert "Make a playlist" in page and f'hx-post="{BASE}/franchises/Q462/playlist"' in page

    server = FakeServer({1: FakeItem(1, aired=datetime(1977, 5, 25)), 2: FakeItem(2, aired=datetime(1980, 5, 21))},
                        {100: FakeShow([FakeItem(101, aired=datetime(2019, 11, 12), season=1, index=1)])})
    from app.services import media_server_service

    monkeypatch.setattr(media_server_service, "client_for", lambda s: _AsPlexClient(server))
    body = client.post(f"{BASE}/franchises/Q462/playlist").text

    assert "Star Wars (Franchisarr)" in body and "2 films, 1 show (1 episode)" in body


def test_the_page_offers_every_server_and_each_one_and_builds_on_the_one_asked(
    client: TestClient, monkeypatch
) -> None:
    with Session(get_engine()) as session:
        attic = _library(session, kind="jellyfin")
        living_room = session.exec(select(MediaServer).where(MediaServer.name == "Living room")).one().id
    page = client.get(f"{BASE}/franchises/Q462").text
    assert "On every server" in page and "On Living room" in page and "On Attic" in page
    assert f'hx-vals=\'{{"server": "{attic}"}}\'' in page

    built = []

    class Recorder:
        def __init__(self, server) -> None:  # noqa: ANN001
            self.server = server

        def playlist_entries(self, films, shows):  # noqa: ANN001, ANN201
            from app.clients.media_server import PlaylistEntry as Entry

            return [Entry(raw=f, aired=None) for f in films]

        def replace_playlist(self, title, items):  # noqa: ANN001, ANN201
            built.append(self.server.name)

    from app.services import media_server_service

    monkeypatch.setattr(media_server_service, "client_for", lambda s: Recorder(s))

    client.post(f"{BASE}/franchises/Q462/playlist", data={"server": str(attic)})
    assert built == ["Attic"], "only the server asked for"

    built.clear()
    client.post(f"{BASE}/franchises/Q462/playlist", data={"server": "all"})
    assert sorted(built) == ["Attic", "Living room"]

    assert client.post(f"{BASE}/franchises/Q462/playlist", data={"server": "999"}).status_code == 404
    assert living_room


def test_a_server_that_holds_none_of_it_says_so(session: Session) -> None:
    _library(session)
    empty = seed_server(session, "emby", name="Empty")

    result = playlist_service.build(session, "Star Wars", [(ItemType.MOVIE.value, 11)], server_id=empty.id)

    assert result.servers == [] and result.only == "Empty"


# ------------------------------------------------------------------ deleting ours


def test_plex_deletes_only_playlists_franchisarr_made() -> None:
    ours, other = FakePlaylist("Alien (Franchisarr)"), FakePlaylist("Alien")
    server = FakeServer({}, {}, playlists=[ours, other])

    assert _delete_playlists(FakeClient(server), " (Franchisarr)") == ["Alien (Franchisarr)"]
    assert ours.deleted and not other.deleted


class _Shelf:
    """A server's playlists, for the delete tests."""

    def __init__(self, titles, fail=False) -> None:  # noqa: ANN001
        self.titles, self.fail, self.deleted = list(titles), fail, []

    def playlists_ending(self, suffix):  # noqa: ANN001, ANN201
        if self.fail:
            raise ConnectionError("down")
        return sorted(t for t in self.titles if t.endswith(suffix))

    def delete_playlists(self, suffix):  # noqa: ANN001, ANN201
        gone = self.playlists_ending(suffix)
        self.deleted += gone
        self.titles = [t for t in self.titles if t not in gone]
        return gone

    def playlist_titles(self):  # noqa: ANN201
        return list(self.titles)

    def delete_all_playlists(self):  # noqa: ANN201
        return self.delete_playlists("")


def test_deleting_asks_first_then_deletes_one_server_or_all(client: TestClient, monkeypatch) -> None:
    with Session(get_engine()) as session:
        attic = _library(session, kind="jellyfin")
    shelves = {"Living room": _Shelf(["Alien (Franchisarr)", "Road trip"]),
               "Attic": _Shelf(["Alien (Franchisarr)", "Star Wars (Franchisarr)"])}
    from app.services import media_server_service

    monkeypatch.setattr(media_server_service, "client_for", lambda s: shelves[s.name])

    page = client.get(f"{BASE}/media-servers").text
    assert 'id="bulk"' in page
    assert "Add playlists…" in page and "Delete all playlists…" in page and "s playlists…" in page
    assert f'hx-get="{BASE}/playlists/delete?scope=ours"' in page and 'hx-include="#bulk-server"' in page
    assert f'<option value="{attic}">Attic</option>' in page and '<option value="all">every server</option>' in page
    assert "Delete playlists</button>" not in page, "the per-server buttons moved into Bulk actions"

    warning = client.get(f"{BASE}/playlists/delete?server={attic}").text
    assert "This deletes 2 playlists" in warning and "Star Wars (Franchisarr)" in warning
    assert "Yes, delete 2 playlists" in warning
    assert shelves["Attic"].deleted == [], "the warning deletes nothing"

    done = client.post(f"{BASE}/playlists/delete", data={"server": str(attic)}).text
    assert "Attic: deleted 2 playlists" in done
    assert shelves["Living room"].deleted == [], "only the server asked for"

    warning = client.get(f"{BASE}/playlists/delete?server=all").text
    assert "This deletes 1 playlist" in warning and "Road trip" not in warning
    client.post(f"{BASE}/playlists/delete", data={"server": "all"})
    assert shelves["Living room"].deleted == ["Alien (Franchisarr)"], "never a playlist someone made"


def test_an_unreachable_server_is_named_in_the_warning(client: TestClient, monkeypatch) -> None:
    from app.services import media_server_service

    monkeypatch.setattr(media_server_service, "client_for", lambda s: _Shelf([], fail=True))

    warning = client.get(f"{BASE}/playlists/delete?server=all").text

    assert "Living room: Couldn" in warning and "No Franchisarr playlists to delete" in warning


def test_deleting_every_playlist_needs_delete_typed_and_lists_peoples_own(client: TestClient, monkeypatch) -> None:
    with Session(get_engine()) as session:
        attic = _library(session, kind="jellyfin")
    shelves = {"Living room": _Shelf(["Alien (Franchisarr)", "Road trip"]), "Attic": _Shelf(["Mine"])}
    from app.services import media_server_service

    monkeypatch.setattr(media_server_service, "client_for", lambda s: shelves[s.name])

    warning = client.get(f"{BASE}/playlists/delete?server=all&scope=all").text
    assert "This deletes 3 playlists" in warning and "Road trip" in warning and "Mine" in warning
    assert "including ones you made yourself" in warning and 'name="confirm"' in warning
    assert "may be in this list" in warning, "Jellyfin can't say who owns a playlist"

    refused = client.post(f"{BASE}/playlists/delete", data={"server": "all", "scope": "all", "confirm": "yes"}).text
    assert "Type DELETE to confirm." in refused and shelves["Living room"].deleted == []

    client.post(f"{BASE}/playlists/delete", data={"server": str(attic), "scope": "all", "confirm": "DELETE"})
    assert shelves["Attic"].deleted == ["Mine"] and shelves["Living room"].deleted == [], "only the server asked"


def test_plex_alone_gets_no_shared_playlist_caveat(client: TestClient, monkeypatch) -> None:
    from app.services import media_server_service

    monkeypatch.setattr(media_server_service, "client_for", lambda s: _Shelf(["Road trip"]))

    warning = client.get(f"{BASE}/playlists/delete?server=all&scope=all").text

    assert "Road trip" in warning and "may be in this list" not in warning


def test_a_set_too_small_for_a_server_is_skipped_there(session: Session, monkeypatch) -> None:
    _library(session)
    from app.services import media_server_service

    monkeypatch.setattr(media_server_service, "client_for", lambda s: _AsPlexClient(FakeServer({}, {})))

    result = playlist_service.build(session, "Just one", [(ItemType.MOVIE.value, 11)], min_items=2)

    assert result.servers == [] and result.skipped == 1


def test_bulk_add_builds_every_set_and_tallies(session: Session, monkeypatch) -> None:
    from app.services import playlist_bulk

    made = []

    def fake_build(session, name, refs, art=None, *, server_id=None, min_items=1):  # noqa: ANN001, ANN202
        made.append((name, server_id, min_items))
        result = playlist_service.PlaylistResult(title=name)
        if name == "Tiny":
            result.skipped = 1
        elif name == "Broken":
            result.servers.append(playlist_service.ServerResult(server="Plex", error="refused"))
        else:
            result.servers.append(playlist_service.ServerResult(server="Plex"))
        return result

    monkeypatch.setattr(playlist_service, "build", fake_build)
    monkeypatch.setattr(playlist_bulk, "sets", lambda s, kinds: [
        playlist_bulk.PlaylistSet("franchises", n, [("movie", 1), ("movie", 2)]) for n in ("Alien", "Tiny", "Broken")])

    playlist_bulk._set(running=True, stopping=False, made=0, skipped=0, failed=0, errors=())
    playlist_bulk.run(session, ["franchises"], 7, "Plex")
    state = playlist_bulk.current()

    assert [m[0] for m in made] == ["Alien", "Tiny", "Broken"] and {m[1:] for m in made} == {(7, 2)}
    assert (state.made, state.skipped, state.failed, state.done, state.total) == (1, 1, 1, 3, 3)
    assert state.errors == ("Broken on Plex: refused",)


def test_stop_ends_a_bulk_add_between_playlists(session: Session, monkeypatch) -> None:
    from app.services import playlist_bulk

    made = []

    def fake_build(session, name, refs, art=None, **kw):  # noqa: ANN001, ANN202
        made.append(name)
        playlist_bulk.stop()   # the person presses Stop while the first is being made
        return playlist_service.PlaylistResult(title=name, servers=[playlist_service.ServerResult(server="Plex")])

    monkeypatch.setattr(playlist_service, "build", fake_build)
    monkeypatch.setattr(playlist_bulk, "sets", lambda s, kinds: [
        playlist_bulk.PlaylistSet("collections", n, [("movie", 1), ("movie", 2)]) for n in ("A", "B", "C")])

    playlist_bulk._set(running=True, stopping=False, made=0, skipped=0, failed=0, errors=())
    playlist_bulk.run(session, ["collections"], None, "every server")

    assert made == ["A"] and playlist_bulk.current().made == 1
    playlist_bulk._set(running=False, stopping=False)


def test_the_add_form_offers_each_kind_with_its_count_and_starts_the_job(client: TestClient, monkeypatch) -> None:
    from app.services import playlist_bulk

    monkeypatch.setattr(playlist_bulk, "counts", lambda s: {"franchises": 207, "collections": 409, "directors": 148})
    started = []
    monkeypatch.setattr(playlist_bulk, "run_in_background", lambda kinds, server_id, where: started.append((kinds, server_id, where)) or True)

    form = client.get(f"{BASE}/playlists/add-all?server=all").text
    assert "franchise (207)" in form and "collection (409)" in form and "director (148)" in form

    assert "Pick at least one kind" in client.post(f"{BASE}/playlists/add-all", data={"server": "all"}).text
    client.post(f"{BASE}/playlists/add-all", data={"server": "all", "kinds": ["franchises", "directors", "bogus"]})
    assert started == [(["franchises", "directors"], None, "every server")]


# ------------------------------------------------------------------ posters


def _solid(colour):  # noqa: ANN001, ANN202
    from PIL import Image

    return Image.new("RGB", (1280, 720), colour)


def test_the_poster_is_a_backdrop_with_the_name(monkeypatch) -> None:
    from PIL import Image
    import io

    from app.services import playlist_poster

    monkeypatch.setattr(playlist_poster, "_fetch", lambda url: _solid((200, 30, 30)))
    data = playlist_poster.render("Star Wars", films=13, episodes=279, backdrop_url="https://x/b.jpg")

    image = Image.open(io.BytesIO(data))
    assert image.size == (1000, 1000) and image.format == "JPEG", "square: Plex shows playlists square"
    top, panel = image.getpixel((500, 100)), image.getpixel((20, 900))
    assert top[0] > 150 and panel[0] < 40, "the backdrop across the top, the text on a dark panel"


def test_a_long_name_wraps_rather_than_shrinking_to_nothing() -> None:
    from PIL import Image, ImageDraw

    from app.services import playlist_poster

    draw = ImageDraw.Draw(Image.new("RGB", (1000, 1000)))
    lines, font = playlist_poster._name_lines(draw, "DC Universe Animated Original Movies")
    assert len(lines) == 2 and font.size >= 56
    lines, font = playlist_poster._name_lines(draw, "Alien")
    assert lines == ["Alien"] and font.size == 104


@pytest.mark.parametrize("count,columns", [(12, 5), (9, 4), (6, 3), (4, 4), (1, 1)])
def test_the_director_mosaic_leaves_no_empty_cell(monkeypatch, count: int, columns: int) -> None:
    from app.services import playlist_poster

    sizes: list[tuple[int, int]] = []
    monkeypatch.setattr(playlist_poster, "_fetch", lambda url: _solid((50, 50, 50)))
    real_fit = playlist_poster._fit
    monkeypatch.setattr(playlist_poster, "_fit", lambda img, w, h: (sizes.append((w, h)), real_fit(img, w, h))[1])

    playlist_poster._poster_rows([f"https://x/{i}.jpg" for i in range(count)])

    assert sizes and all(w == 1000 // columns for w, _ in sizes)
    rows = 1 if count < 6 else 2
    assert len(sizes) == columns * rows, "every cell filled"


def test_no_backdrop_falls_back_to_a_mosaic_and_no_art_means_no_poster(monkeypatch) -> None:
    from app.services import playlist_poster

    monkeypatch.setattr(playlist_poster, "_fetch", lambda url: _solid((30, 200, 30)))
    assert playlist_poster.render("Christopher Nolan", films=11, episodes=0,
                                  poster_urls=["https://x/1.jpg", "https://x/2.jpg"])
    assert playlist_poster.render("Nothing", films=1, episodes=0) is None


def test_a_poster_failure_or_artwork_switched_off_returns_none(monkeypatch) -> None:
    from app.services import playlist_poster

    def boom(url):  # noqa: ANN001, ANN202
        raise ConnectionError("tmdb down")

    monkeypatch.setattr(playlist_poster, "_fetch", boom)
    assert playlist_poster.render("X", films=1, episodes=0, backdrop_url="https://x/b.jpg") is None

    monkeypatch.setattr(playlist_poster, "_fetch", lambda url: _solid((1, 2, 3)))
    monkeypatch.setenv("SHOW_ARTWORK", "false")
    assert playlist_poster.render("X", films=1, episodes=0, backdrop_url="https://x/b.jpg") is None


def test_the_poster_is_uploaded_to_our_playlist_only() -> None:
    from app.clients.plex_client import _set_playlist_poster

    uploaded: dict[str, bytes] = {}

    class Uploadable(FakePlaylist):
        def uploadPoster(self, filepath: str) -> None:  # noqa: N802
            with open(filepath, "rb") as handle:
                uploaded[self.title] = handle.read()

    server = FakeServer({}, {}, playlists=[Uploadable("Star Wars"), Uploadable("Star Wars (Franchisarr)")])

    assert _set_playlist_poster(FakeClient(server), "Star Wars (Franchisarr)", b"\xff\xd8jpeg") is True
    assert uploaded == {"Star Wars (Franchisarr)": b"\xff\xd8jpeg"}
    assert _set_playlist_poster(FakeClient(server), "Gone (Franchisarr)", b"x") is False


def test_build_puts_the_poster_on_and_a_poster_failure_keeps_the_playlist(session: Session, monkeypatch) -> None:
    _library(session)
    server = FakeServer({1: FakeItem(1, aired=datetime(1977, 5, 25))}, {})
    posters: list[tuple[str, bytes]] = []

    class WithPoster(_AsPlexClient):
        def set_playlist_poster(self, title, image):  # noqa: ANN001, ANN201
            posters.append((title, image))
            return True

    from app.services import media_server_service, playlist_poster

    monkeypatch.setattr(media_server_service, "client_for", lambda s: WithPoster(server))
    monkeypatch.setattr(playlist_poster, "_fetch", lambda url: _solid((9, 9, 9)))
    art = playlist_service.PosterArt(backdrop_url="https://x/b.jpg")

    result = playlist_service.build(session, "Star Wars", [(ItemType.MOVIE.value, 11)], art)
    assert result.servers[0].poster and posters[0][0] == "Star Wars (Franchisarr)"

    monkeypatch.setattr(playlist_poster, "render", lambda *a, **k: None)
    again = playlist_service.build(session, "Star Wars", [(ItemType.MOVIE.value, 11)], art)
    assert again.made_any and again.servers[0].poster is False


def test_the_caption_counts_films_shows_and_episodes_leaving_out_zeros() -> None:
    from app.services.playlist_poster import _caption

    assert _caption(13, 279, 3) == "13 films · 3 shows · 279 episodes"
    assert _caption(1, 1, 1) == "1 film · 1 show · 1 episode"
    assert _caption(11, 0, 0) == "11 films"


def test_reposting_finds_each_playlists_page_and_counts_from_plex(session: Session, monkeypatch) -> None:
    from app.services import media_server_service, playlist_service

    _library(session)
    session.add(Franchise(wikidata_id="Q462", name="Star Wars", kind="media franchise"))
    session.commit()

    class Ep:
        TYPE = "episode"

        def __init__(self, show):  # noqa: ANN001
            self.__dict__["grandparentRatingKey"] = show

    class Film:
        TYPE = "movie"

    class Listed:
        def __init__(self, title: str) -> None:
            self.title = title

        def items(self):  # noqa: ANN201
            return [Film(), Film(), Ep(1), Ep(1), Ep(2)]

    server = FakeServer({}, {}, playlists=[Listed("Star Wars (Franchisarr)"), Listed("My own list")])
    calls = []
    from app.clients.plex_client import _playlist_counts, _playlist_titles

    class Counting(FakeClient):
        def playlist_titles(self):  # noqa: ANN201
            return _playlist_titles(self)

        def playlist_counts(self, title):  # noqa: ANN001, ANN201
            return _playlist_counts(self, title)

    monkeypatch.setattr(media_server_service, "client_for", lambda s: Counting(server))
    monkeypatch.setattr(playlist_service, "apply_poster",
                        lambda client, title, name, films, episodes, art, shows=0:
                        calls.append((title, films, shows, episodes)) or True)

    assert playlist_service.repost_all(session) == [("Star Wars (Franchisarr)", True)]
    assert calls == [("Star Wars (Franchisarr)", 2, 2, 3)], "our playlist only, counted from Plex"
