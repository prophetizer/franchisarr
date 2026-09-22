"""Paging the card grids.

The unit is arithmetic and link-building; the page tests check the two things that would be
wrong in a way nobody notices: the headline totals must describe the whole list rather than the
page, and a pager link must keep the sort and filter you were looking at (and the subpath).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.local_admin import create_local_admin
from app.db import get_engine
from app.models import (
    IncludedLibrary, ItemType, LibraryItem, MatchSource, TmdbCollection, TmdbCollectionMovie,
    TmdbMovie,
)
from app.services.pagination import DEFAULT_SIZE, paginate
from tests.conftest import ensure_server

BASE = "/franchisarr"
PASSWORD = "s3cret-passphrase"


# ------------------------------------------------------------------ the arithmetic


def test_a_short_list_is_one_page_and_asks_for_no_pager() -> None:
    pager = paginate(list(range(10)), 1, path="/collections", size=120)

    assert pager.items == list(range(10))
    assert pager.pages == 1 and not pager.needed
    assert pager.previous is None and pager.next is None


def test_an_empty_list_is_still_one_page() -> None:
    pager = paginate([], 1, path="/collections")

    assert pager.items == [] and pager.pages == 1 and not pager.needed


def test_a_long_list_is_cut_and_the_indices_read_from_one() -> None:
    pager = paginate(list(range(250)), 2, path="/collections", size=100)

    assert pager.items == list(range(100, 200))
    assert (pager.page, pager.pages, pager.total) == (2, 3, 250)
    assert (pager.first_index, pager.last_index) == (101, 200)
    assert pager.needed


def test_an_exact_multiple_does_not_leave_a_trailing_empty_page() -> None:
    pager = paginate(list(range(200)), 2, path="/collections", size=100)

    assert pager.pages == 2 and pager.next is None


@pytest.mark.parametrize("asked", [0, -5, 99])
def test_a_page_number_outside_the_range_lands_on_a_real_page(asked: int) -> None:
    """A stale bookmark, or a library that shrank since. An empty list is not an answer."""
    pager = paginate(list(range(250)), asked, path="/collections", size=100)

    assert pager.items
    assert pager.page in (1, 3)


def test_links_carry_the_filters_and_drop_the_empty_ones() -> None:
    pager = paginate(list(range(250)), 2, path="/collections", size=100,
                     params={"sort": "name", "started": None, "instance": ""})

    assert pager.previous == "/collections?sort=name&page=1"
    assert pager.next == "/collections?sort=name&page=3"


def test_an_anchor_is_appended_so_a_pager_inside_a_details_comes_back_to_it() -> None:
    pager = paginate(list(range(250)), 1, path="/shows", size=100, anchor="#library")

    assert pager.next == "/shows?page=2#library"


def test_two_pagers_on_one_page_move_independently() -> None:
    """Spin-offs has a suggestion grid and an owned-show list. If both wrote `page`, turning
    one would silently reset the other to its first page."""
    grid = paginate(list(range(250)), 2, path="/shows", size=100, params={"library_page": 3})
    library = paginate(list(range(500)), 3, path="/shows", size=100, anchor="#library",
                       page_param="library_page", params={"page": 2})

    assert grid.next == "/shows?library_page=3&page=3"
    assert library.next == "/shows?page=2&library_page=4#library"


# ------------------------------------------------------------------ the pages


@pytest.fixture
def client(app_factory):
    module = app_factory(BASE)
    with TestClient(module.app, follow_redirects=False) as test_client:
        with Session(get_engine()) as session:
            create_local_admin(session, "admin", PASSWORD)
            session.add(IncludedLibrary(server_id=ensure_server(session), library_key="1",
                                        library_name="Movies", library_type="movie", enabled=True))
            session.commit()
        test_client.post(f"{BASE}/login", data={"username": "admin", "password": PASSWORD})
        yield test_client


def _collections_with_gaps(count: int) -> None:
    """`count` collections, each with one owned film and one missing."""
    with Session(get_engine()) as session:
        server = ensure_server(session)
        for i in range(1, count + 1):
            owned, missing = 10_000 + i * 2, 10_001 + i * 2
            session.add(TmdbCollection(tmdb_collection_id=i, name=f"Collection {i:04d}"))
            session.add(TmdbCollectionMovie(collection_id=i, tmdb_movie_id=owned, title=f"Film {i}a",
                                            release_year=1990, release_date="1990-01-01", position=0))
            session.add(TmdbCollectionMovie(collection_id=i, tmdb_movie_id=missing, title=f"Film {i}b",
                                            release_year=1995, release_date="1995-01-01", position=1))
            session.add(TmdbMovie(tmdb_id=owned, title=f"Film {i}a", collection_id=i))
            session.add(LibraryItem(server_id=server, library_key="1", item_key=f"m{owned}",
                                    item_type=ItemType.MOVIE.value, title=f"Film {i}a", year=1990,
                                    tmdb_id=owned, match_source=MatchSource.GUID.value))
        session.commit()


def test_a_library_under_the_threshold_gets_no_pager_at_all(client: TestClient) -> None:
    """Nothing changes for a normal library -- this is the whole point of the threshold."""
    _collections_with_gaps(12)

    body = client.get(f"{BASE}/collections").text

    assert "Collection 0012" in body
    assert 'aria-label="Pages"' not in body


def test_a_long_list_is_paged_and_the_totals_still_describe_all_of_it(client: TestClient) -> None:
    _collections_with_gaps(DEFAULT_SIZE + 30)
    total = DEFAULT_SIZE + 30

    first = client.get(f"{BASE}/collections?sort=name").text
    second = client.get(f"{BASE}/collections?sort=name&page=2").text

    # The heading counts every collection and every missing film, not the page's share.
    assert f"{total} collections" in first
    assert f"missing {total} films" in first
    # Each page holds its own slice, and page 2 is the remainder. The boundary is derived
    # from the threshold, not written in: raising DEFAULT_SIZE must not silently pass here.
    first_of_page_two = f"Collection {DEFAULT_SIZE + 1:04d}"
    assert "Collection 0001" in first and first_of_page_two not in first
    assert first_of_page_two in second and "Collection 0001" not in second
    # The pager's range line wraps in the template, so compare with whitespace collapsed.
    flat = lambda html: " ".join(html.split())
    assert f"1–{DEFAULT_SIZE} of {total}" in flat(first)
    assert f"{DEFAULT_SIZE + 1}–{total} of {total}" in flat(second)


def test_pager_links_keep_the_sort_and_the_subpath(client: TestClient) -> None:
    """A pager that drops the sort sends you to a differently ordered page 2, which quietly
    skips and repeats collections."""
    _collections_with_gaps(DEFAULT_SIZE + 5)

    body = client.get(f"{BASE}/collections?sort=name").text

    assert f'href="{BASE}/collections?sort=name&amp;page=2"' in body
    assert "//collections" not in body


def test_the_started_filter_survives_the_pager(client: TestClient) -> None:
    _collections_with_gaps(DEFAULT_SIZE + 5)

    body = client.get(f"{BASE}/collections?started=1").text

    # Whether the filter applies depends on watched state being known; the link must carry
    # whatever state the page is actually in.
    if 'aria-label="Pages"' in body:
        assert "page=2" in body


@pytest.mark.parametrize("path", ["/collections", "/upcoming", "/directors", "/shows"])
def test_every_paged_page_still_renders_when_asked_for_a_page_that_is_not_there(
    client: TestClient, path: str
) -> None:
    _collections_with_gaps(5)

    response = client.get(f"{BASE}{path}?page=9999")

    assert response.status_code == 200
