"""Chronological playlists and story orders (0.74.0): built-in orders for the big franchises, a
household's own order for any collection or franchise, and a "<name> — Chronological
(Franchisarr)" playlist beside the release-order one."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import FranchisarrPlaylist, ItemType
from app.services import chronology, franchisarr_playlists, playlist_service, playlist_sync
from app.services.chronology_data import ORDERS
from tests.test_franchisarr_playlists import BASE, _own, client, world  # noqa: F401 - fixtures

M = ItemType.MOVIE.value
CHRONO = "Star Wars — Chronological (Franchisarr)"


# ------------------------------------------------------------------ the data


def test_every_built_in_order_is_well_formed() -> None:
    """The ids were checked against TMDb when written (219 titles, 2026-10-17); CI has no network,
    so here: no title twice, real item types, and an order worth having."""
    for name, entries in ORDERS.items():
        keys = [(t, i) for t, i, _ in entries]
        assert len(keys) == len(set(keys)), f"{name} lists a title twice"
        assert all(t in ("movie", "show") for t, _ in keys), name
        assert len(entries) >= 2 and all(title for _, _, title in entries), name


# ------------------------------------------------------------------ story order


def test_a_built_in_order_places_what_it_knows_and_the_rest_follows_in_release_order(session: Session) -> None:
    release = [(M, 11), (M, 1891), (M, 330459), (M, 99999)]          # 99999: a title no order knows
    story = chronology.story(session, "franchises", "Q462", release)
    assert story.order == [(M, 330459), (M, 11), (M, 1891), (M, 99999)]
    assert story.source == "Star Wars" and story.unplaced == 1
    assert chronology.story(session, "collections", "1", [(M, 11), (M, 99999)]) is None, "one placed title is no order"


def test_the_households_own_order_wins_and_can_be_put_back(session: Session) -> None:
    titles = [(M, 11), (M, 1891), (M, 330459)]
    chronology.save(session, "franchises", "Q462", [(M, 1891), (M, 11), (M, 1891)])
    story = chronology.story(session, "franchises", "Q462", titles)
    assert story.source == "yours" and story.order == [(M, 1891), (M, 11), (M, 330459)]
    chronology.save(session, "franchises", "Q462", [(M, 11), (M, 1891)])          # replacing, ids overlapping
    assert chronology.custom(session, "franchises", "Q462") == [(M, 11), (M, 1891)]
    chronology.reset(session, "franchises", "Q462")
    assert chronology.story(session, "franchises", "Q462", titles).source == "Star Wars"


# ------------------------------------------------------------------ the playlists


def test_a_chronological_playlist_sits_beside_the_release_one(session: Session, world) -> None:  # noqa: F811
    living, attic, fakes = world
    _own(session, living, 1893)                                          # The Phantom Menace, on Plex
    refs = [(M, 11), (M, 1891), (M, 1893)]
    art = playlist_service.PosterArt(backdrop_url="https://x/b.jpg")
    franchisarr_playlists.make(session, "franchises", "Q462", "Star Wars", refs, art, server_id=living.id)
    result = franchisarr_playlists.make(session, "franchises", "Q462", "Star Wars", refs, art,
                                        server_id=living.id, variant="chronological")

    plex = fakes["Living room"]
    [release_id] = plex.titled("Star Wars (Franchisarr)")
    [chrono_id] = plex.titled(CHRONO)
    assert plex.keys(release_id) == ["p11", "p1891", "p1893"], "release order, as before"
    assert plex.keys(chrono_id) == ["p1893", "p11", "p1891"], "Episode I first: the story's order"
    assert result.title == CHRONO and result.story_source == "Star Wars"
    rows = session.exec(select(FranchisarrPlaylist.variant)).all()
    assert sorted(rows) == ["chronological", "release"]
    assert franchisarr_playlists.kept_on(session, "franchises", "Q462", "chronological") == ["Living room"]


def test_rearranging_the_story_rebuilds_the_chronological_playlist(session: Session, world) -> None:  # noqa: F811
    living, attic, fakes = world
    _own(session, living, 1893)
    refs = [(M, 11), (M, 1891), (M, 1893)]
    franchisarr_playlists.make(session, "franchises", "Q462", "Star Wars", refs, None, server_id=living.id,
                               variant="chronological")
    chronology.save(session, "franchises", "Q462", [(M, 1891), (M, 11), (M, 1893)])
    playlist_sync.run(session)
    plex = fakes["Living room"]
    [chrono_id] = plex.titled(CHRONO)
    assert plex.keys(chrono_id) == ["p1891", "p11", "p1893"], "the order is part of what's kept current"


# ------------------------------------------------------------------ the pages


def test_the_button_builds_either_or_both(client: TestClient) -> None:  # noqa: F811
    page = client.get(f"{BASE}/franchises/Q462").text
    assert 'name="order" value="release" checked' in page and 'value="chronological"' in page
    assert 'hx-include="closest .playlist-control"' in page and f'href="{BASE}/story-order/franchises/Q462"' in page

    both = client.post(f"{BASE}/franchises/Q462/playlist",
                       data={"server": "all", "order": ["release", "chronological"]}).text
    assert "Star Wars (Franchisarr)" in both and CHRONO in both and "in story order" in both
    page = client.get(f"{BASE}/franchises/Q462").text
    assert "✓ Chronological kept on" in page and "✓ Playlist kept on" in page

    only = client.post(f"{BASE}/franchises/Q462/playlist", data={"server": "all", "order": ["chronological"]}).text
    assert CHRONO in only and "Star Wars (Franchisarr)" not in only.replace(CHRONO, "")


def test_without_a_story_order_chronological_says_how_to_get_one(client: TestClient) -> None:  # noqa: F811
    from app.db import get_engine

    with Session(get_engine()) as session:
        from app.models import FranchiseMember
        for row in session.exec(select(FranchiseMember)).all():   # no built-in order knows these ids
            row.tmdb_id += 900000
            session.add(row)
        session.commit()
    body = client.post(f"{BASE}/franchises/Q462/playlist", data={"server": "all", "order": ["chronological"]}).text
    assert "no story order yet" in body


def test_the_story_order_page_saves_and_resets(client: TestClient) -> None:  # noqa: F811
    page = client.get(f"{BASE}/story-order/franchises/Q462").text
    assert "built-in order for Star Wars" in page and 'name="order" value="movie:1893"' in page
    assert page.index('value="movie:1893"') < page.index('value="movie:11"'), "Episode I first"

    saved = client.post(f"{BASE}/story-order/franchises/Q462",
                        data={"order": ["movie:11", "movie:1891", "movie:999", "show:1893"]},   # strangers dropped
                        follow_redirects=True)
    assert saved.url.path == f"{BASE}/story-order/franchises/Q462" and "Saved." in saved.text
    assert saved.history[0].headers["location"] == "?saved=1", "nothing from the request in the Location"
    page = client.get(f"{BASE}/story-order/franchises/Q462").text
    assert "This is your order" in page
    assert page.index('value="movie:11"') < page.index('value="movie:1891"') < page.index('value="movie:1893"')

    client.post(f"{BASE}/story-order/franchises/Q462", data={"reset": "1"})
    assert "built-in order for Star Wars" in client.get(f"{BASE}/story-order/franchises/Q462").text
    assert client.get(f"{BASE}/story-order/elsewhere/1").status_code == 404


def test_a_chronological_playlists_poster_says_so(session: Session, world, monkeypatch) -> None:  # noqa: F811
    from app.services import playlist_poster

    living, attic, fakes = world
    _own(session, living, 1893)
    said = []
    monkeypatch.setattr(playlist_poster, "render", lambda *a, **k: said.append(k.get("order")) or b"\xff\xd8poster")
    art = playlist_service.PosterArt(backdrop_url="https://x/b.jpg")
    refs = [(M, 11), (M, 1891), (M, 1893)]
    franchisarr_playlists.make(session, "franchises", "Q462", "Star Wars", refs, art, server_id=living.id)
    franchisarr_playlists.make(session, "franchises", "Q462", "Star Wars", refs, art, server_id=living.id,
                               variant="chronological")
    assert said == ["IN RELEASE ORDER", "IN STORY ORDER"]
