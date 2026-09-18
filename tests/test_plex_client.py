"""Plex client tests, driven by recorded Plex XML through `responses`.

The fixtures are fed to the real plexapi parsing path rather than mocking plexapi itself, so
these tests exercise the same code that will run against a real server -- including the bit most
likely to be wrong, which is how GUIDs actually arrive in a section listing.

No test here touches the network (docs/DEVELOPMENT.md convention 2): `responses` fails any unregistered
request rather than letting it out.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

from app.clients.plex_client import (
    DEFAULT_PAGE_SIZE,
    PlexClient,
    PlexLibraryNotFoundError,
    PlexUnauthorizedError,
    PlexUnreachableError,
)
from app.clients.plex_guid import ExternalIds

PLEX_URL = "http://plex.test:32400"


@pytest.fixture
def plex_fixtures(fixtures_dir: Path) -> Path:
    return fixtures_dir / "plex"


def _xml(plex_fixtures: Path, name: str) -> str:
    return (plex_fixtures / name).read_text()


def _register_server(mock: responses.RequestsMock, plex_fixtures: Path) -> None:
    """The handshake plexapi performs before it can reach a library section."""
    mock.add(
        responses.GET,
        f"{PLEX_URL}/",
        body=_xml(plex_fixtures, "root.xml"),
        content_type="application/xml",
    )
    mock.add(
        responses.GET,
        f"{PLEX_URL}/library",
        body=_xml(plex_fixtures, "library.xml"),
        content_type="application/xml",
    )
    mock.add(
        responses.GET,
        f"{PLEX_URL}/library/sections",
        body=_xml(plex_fixtures, "library_sections.xml"),
        content_type="application/xml",
    )


def _register_section(
    mock: responses.RequestsMock, plex_fixtures: Path, section: int, *fixture_names: str
) -> None:
    """Register one response per expected page, in order."""
    for name in fixture_names:
        mock.add(
            responses.GET,
            f"{PLEX_URL}/library/sections/{section}/all",
            body=_xml(plex_fixtures, name),
            content_type="application/xml",
        )


@pytest.fixture
def mocked_plex(plex_fixtures: Path):
    # assert_all_requests_are_fired is off because the handshake responses are registered for
    # every test whether or not that test reaches a section. Tests that care about request
    # counts assert on mock.calls explicitly instead.
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        _register_server(mock, plex_fixtures)
        yield mock


@pytest.fixture
def client() -> PlexClient:
    return PlexClient(PLEX_URL, "test-plex-token")


# --------------------------------------------------------------------------- libraries


def test_list_libraries_separates_movie_and_show_sections(
    mocked_plex: responses.RequestsMock, client: PlexClient
) -> None:
    libraries = client.list_libraries()

    by_title = {library.title: library for library in libraries}
    assert by_title["Movies"].library_type == "movie"
    assert by_title["Movies"].is_movie_library is True
    assert by_title["TV Shows"].library_type == "show"
    assert by_title["TV Shows"].is_show_library is True
    assert by_title["Movies"].key == "1"
    assert by_title["Movies"].agent == "tv.plex.agents.movie"


def test_list_libraries_skips_music_and_photo_sections(
    mocked_plex: responses.RequestsMock, client: PlexClient
) -> None:
    titles = {library.title for library in client.list_libraries()}

    assert "Music" not in titles
    assert titles == {"Movies", "TV Shows", "Legacy Movies", "Home Videos", "Anime"}


def test_unknown_library_key_is_reported_clearly(
    mocked_plex: responses.RequestsMock, client: PlexClient
) -> None:
    with pytest.raises(PlexLibraryNotFoundError):
        client.list_movies("99")


# --------------------------------------------------------------------------- new agent


def test_movies_from_a_new_agent_library(
    mocked_plex: responses.RequestsMock, plex_fixtures: Path, client: PlexClient
) -> None:
    """New Plex Movie agent: item guid is plex://, real ids are in child <Guid> elements."""
    _register_section(mocked_plex, plex_fixtures, 1, "section_1_movies.xml")

    movies = client.list_movies("1")

    assert [movie.title for movie in movies] == [
        "Beverly Hills Cop",
        "Beverly Hills Cop II",
        "An Unmatched Film",
    ]
    first = movies[0]
    assert first.item_key == "1001"
    assert first.year == 1984
    assert first.external_ids == ExternalIds(tmdb_id=90, imdb_id="tt0086960", tvdb_id=12345)
    assert first.has_external_ids is True
    assert "plex://movie/5d7768ba96b655001fdc0408" in first.guids
    assert first.watched is True, "viewCount=2 on the listing"
    assert movies[1].watched is False, "no viewCount attribute: plexapi casts it to 0"


def test_new_agent_item_with_no_guid_children_resolves_to_nothing(
    mocked_plex: responses.RequestsMock, plex_fixtures: Path, client: PlexClient
) -> None:
    """An unmatched item in an otherwise healthy library must not break the scan."""
    _register_section(mocked_plex, plex_fixtures, 1, "section_1_movies.xml")

    unmatched = client.list_movies("1")[2]

    assert unmatched.title == "An Unmatched Film"
    assert unmatched.has_external_ids is False
    assert unmatched.year is None


def test_shows_from_a_new_agent_library(
    mocked_plex: responses.RequestsMock, plex_fixtures: Path, client: PlexClient
) -> None:
    _register_section(mocked_plex, plex_fixtures, 2, "section_2_shows.xml")

    shows = client.list_shows("2")

    assert [show.title for show in shows] == ["NCIS", "Chicago Fire"]
    assert shows[0].external_ids == ExternalIds(tmdb_id=1621, imdb_id="tt0364845", tvdb_id=72108)
    assert shows[1].external_ids.tmdb_id == 44006
    assert shows[0].watched is True, "viewedLeafCount=12: some episodes played counts as started"
    assert shows[1].watched is None, "no viewedLeafCount on the listing: unknown, not unwatched"


# --------------------------------------------------------------------------- legacy agents


def test_movies_from_a_legacy_agent_library(
    mocked_plex: responses.RequestsMock, plex_fixtures: Path, client: PlexClient
) -> None:
    """Legacy agents send no <Guid> children at all -- the id is in the item's own guid."""
    _register_section(mocked_plex, plex_fixtures, 3, "section_3_legacy_movies.xml")

    movies = {movie.title: movie for movie in client.list_movies("3")}

    assert movies["Airplane!"].external_ids == ExternalIds(imdb_id="tt0080339")
    assert movies["Blade Runner"].external_ids == ExternalIds(tmdb_id=78)
    assert movies["Blade Runner (Director's Cut)"].external_ids == ExternalIds(imdb_id="tt0083658")
    assert all(movie.has_external_ids for movie in movies.values())


def test_shows_from_a_hama_anime_library(
    mocked_plex: responses.RequestsMock, plex_fixtures: Path, client: PlexClient
) -> None:
    """A separate anime library matched by HAMA is a real configuration for this project."""
    _register_section(mocked_plex, plex_fixtures, 5, "section_5_anime.xml")

    shows = {show.title: show for show in client.list_shows("5")}

    assert shows["One Piece"].external_ids == ExternalIds(tvdb_id=81797)
    assert shows["Cowboy Bebop"].external_ids == ExternalIds(anidb_id=4691)


# --------------------------------------------------------------------------- no ids at all


def test_library_with_no_external_ids_at_all(
    mocked_plex: responses.RequestsMock, plex_fixtures: Path, client: PlexClient
) -> None:
    """A Home Videos library: every item is local:// or unmatched. It must enumerate cleanly
    and simply report that nothing is resolvable, not raise."""
    _register_section(mocked_plex, plex_fixtures, 4, "section_4_no_ids.xml")

    movies = client.list_movies("4")

    assert len(movies) == 2
    assert all(not movie.has_external_ids for movie in movies)
    assert all(movie.external_ids == ExternalIds() for movie in movies)
    assert movies[0].title == "Christmas 2019"


def test_unrecognised_agent_is_logged_once_per_scheme(
    mocked_plex: responses.RequestsMock,
    plex_fixtures: Path,
    client: PlexClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mocked_plex.add(
        responses.GET,
        f"{PLEX_URL}/library/sections/1/all",
        body="""<MediaContainer size="2" totalSize="2">
          <Video ratingKey="1" guid="com.plexapp.agents.brandnew://1" type="movie" title="A"/>
          <Video ratingKey="2" guid="com.plexapp.agents.brandnew://2" type="movie" title="B"/>
        </MediaContainer>""",
        content_type="application/xml",
    )

    with caplog.at_level("WARNING"):
        movies = client.list_movies("1")

    assert len(movies) == 2
    warnings = [rec for rec in caplog.records if "Unrecognised Plex agent" in rec.getMessage()]
    assert len(warnings) == 1, "one line per unknown agent per scan, not one per item"


# --------------------------------------------------------------------------- paging


def test_listing_is_paged(
    mocked_plex: responses.RequestsMock, plex_fixtures: Path
) -> None:
    """Large libraries must arrive over several requests rather than one enormous document."""
    _register_section(mocked_plex, plex_fixtures, 1, "section_1_page1.xml", "section_1_page2.xml")

    client = PlexClient(PLEX_URL, "test-plex-token", page_size=2)
    movies = client.list_movies("1")

    assert [movie.title for movie in movies] == [
        "Beverly Hills Cop",
        "Beverly Hills Cop II",
        "Beverly Hills Cop III",
    ]
    section_calls = [call for call in mocked_plex.calls if "/library/sections/1/all" in call.request.url]
    assert len(section_calls) == 2
    assert section_calls[0].request.headers["X-Plex-Container-Start"] == "0"
    assert section_calls[1].request.headers["X-Plex-Container-Start"] == "2"


def test_iterators_do_not_materialise_the_whole_library(
    mocked_plex: responses.RequestsMock, plex_fixtures: Path
) -> None:
    """Only the first page is fetched if the caller stops early."""
    _register_section(mocked_plex, plex_fixtures, 1, "section_1_page1.xml", "section_1_page2.xml")

    client = PlexClient(PLEX_URL, "test-plex-token", page_size=2)
    first = next(client.iter_movies("1"))

    assert first.title == "Beverly Hills Cop"
    section_calls = [call for call in mocked_plex.calls if "/library/sections/1/all" in call.request.url]
    assert len(section_calls) == 1


@pytest.mark.parametrize(
    ("section", "fixture_name", "lister"),
    [
        (1, "section_1_movies.xml", "list_movies"),
        (5, "section_5_anime.xml", "list_shows"),
    ],
)
def test_listing_issues_no_per_item_metadata_requests(
    mocked_plex: responses.RequestsMock,
    plex_fixtures: Path,
    client: PlexClient,
    section: int,
    fixture_name: str,
    lister: str,
) -> None:
    """The scan must cost one request per page, not one per item.

    plexapi refetches an object from the server whenever an attribute reads back as None or []
    -- including from inside its own _loadData -- so an item with no year, or a show whose
    listing omits childCount, would quietly become its own HTTP request. Both fixtures contain
    exactly such items. On a 3,600-movie library that regression is the difference between a
    handful of requests and thousands.
    """
    _register_section(mocked_plex, plex_fixtures, section, fixture_name)

    items = getattr(client, lister)(str(section))

    assert items
    metadata_calls = [
        call for call in mocked_plex.calls if "/library/metadata/" in call.request.url
    ]
    assert metadata_calls == []


def test_default_page_size_is_sane() -> None:
    assert 100 <= DEFAULT_PAGE_SIZE <= 1000


# --------------------------------------------------------------------------- per-item fallback


def test_fetch_external_ids_for_a_single_item(
    mocked_plex: responses.RequestsMock, plex_fixtures: Path, client: PlexClient
) -> None:
    """Fallback for servers whose section listing omits <Guid> children."""
    mocked_plex.add(
        responses.GET,
        f"{PLEX_URL}/library/metadata/1003",
        body=_xml(plex_fixtures, "metadata_1003.xml"),
        content_type="application/xml",
    )

    ids = client.fetch_external_ids("1003")

    assert ids == ExternalIds(tmdb_id=278, imdb_id="tt0111161")


def test_fetch_external_ids_returns_empty_for_a_missing_item(
    mocked_plex: responses.RequestsMock, client: PlexClient
) -> None:
    mocked_plex.add(responses.GET, f"{PLEX_URL}/library/metadata/9999", status=404)

    assert client.fetch_external_ids("9999") == ExternalIds()


# --------------------------------------------------------------------------- failure modes


def test_bad_token_is_reported_as_unauthorized(plex_fixtures: Path) -> None:
    with responses.RequestsMock() as mock:
        mock.add(responses.GET, f"{PLEX_URL}/", status=401)
        with pytest.raises(PlexUnauthorizedError):
            PlexClient(PLEX_URL, "wrong-token").list_libraries()


def test_unreachable_server_is_reported_clearly() -> None:
    with responses.RequestsMock() as mock:
        mock.add(responses.GET, f"{PLEX_URL}/", body=RequestsConnectionError("refused"))
        with pytest.raises(PlexUnreachableError):
            PlexClient(PLEX_URL, "test-plex-token").list_libraries()


def test_error_message_never_contains_the_token() -> None:
    """Convention #3: a token must not travel out in something destined for a UI."""
    token = "super-secret-plex-token"
    with responses.RequestsMock() as mock:
        mock.add(responses.GET, f"{PLEX_URL}/", status=500, body=f"failed for {token}")
        with pytest.raises(PlexUnreachableError) as exc_info:
            PlexClient(PLEX_URL, token).list_libraries()

    assert token not in str(exc_info.value)


def test_constructing_a_client_performs_no_io() -> None:
    """Config can be saved before the server is known to be reachable."""
    with responses.RequestsMock():  # any request at all would fail this test
        PlexClient(PLEX_URL, "test-plex-token")


def test_connection_test_returns_the_server_name(
    mocked_plex: responses.RequestsMock, client: PlexClient
) -> None:
    assert client.test_connection() == "Test Plex Server"
