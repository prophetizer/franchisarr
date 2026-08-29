"""Table-driven coverage of every Plex GUID format we expect to meet in the wild.

This is technical challenge #1 in miniature. When a real library turns up a format that isn't
here, the fix should be one row in this table plus one branch in plex_guid.py.
"""

from __future__ import annotations

import pytest

from app.clients.plex_guid import (
    ExternalIds,
    extract_external_ids,
    is_known_scheme,
    parse_guid,
    unknown_schemes,
)


@pytest.mark.parametrize(
    ("guid", "expected"),
    [
        # --- New Plex agents: IDs arrive as child <Guid> elements ---
        ("tmdb://12345", ExternalIds(tmdb_id=12345)),
        ("imdb://tt0080339", ExternalIds(imdb_id="tt0080339")),
        ("tvdb://73244", ExternalIds(tvdb_id=73244)),
        # The item's own GUID under a new agent is Plex-internal and carries nothing useful.
        ("plex://movie/5d7768ba96b655001fdc0408", ExternalIds()),
        ("plex://show/5d9c07f4ad5437001f7b0d0e", ExternalIds()),
        # --- Legacy agents: the ID is in the item GUID itself ---
        ("com.plexapp.agents.themoviedb://78?lang=en", ExternalIds(tmdb_id=78)),
        ("com.plexapp.agents.imdb://tt0080339?lang=en", ExternalIds(imdb_id="tt0080339")),
        ("com.plexapp.agents.thetvdb://73244?lang=en", ExternalIds(tvdb_id=73244)),
        # Legacy TV GUIDs carry trailing season/episode path segments that must be stripped.
        ("com.plexapp.agents.thetvdb://73244/1/1?lang=en", ExternalIds(tvdb_id=73244)),
        ("com.plexapp.agents.thetvdb://73244/2?lang=en", ExternalIds(tvdb_id=73244)),
        # --- HAMA (community anime agent): namespace-prefixed body ---
        ("com.plexapp.agents.hama://tvdb-73244?lang=en", ExternalIds(tvdb_id=73244)),
        ("com.plexapp.agents.hama://anidb-4691?lang=en", ExternalIds(anidb_id=4691)),
        ("com.plexapp.agents.hama://tmdb-1234?lang=en", ExternalIds(tmdb_id=1234)),
        ("com.plexapp.agents.hama://imdb-tt0080339?lang=en", ExternalIds(imdb_id="tt0080339")),
        ("com.plexapp.agents.hama://anidb-4691/1/1?lang=en", ExternalIds(anidb_id=4691)),
        # --- Kodi NFO agents: bare id, namespace inferred from shape + which agent ---
        ("com.plexapp.agents.xbmcnfo://tt0080339?lang=en", ExternalIds(imdb_id="tt0080339")),
        ("com.plexapp.agents.xbmcnfo://550?lang=en", ExternalIds(tmdb_id=550)),
        ("com.plexapp.agents.xbmcnfotv://73244?lang=en", ExternalIds(tvdb_id=73244)),
        ("com.plexapp.agents.xbmcnfotv://tt0080339", ExternalIds(imdb_id="tt0080339")),
        # --- Recognised, but no external ID to give ---
        ("local://12345", ExternalIds()),
        ("com.plexapp.agents.none://12345?lang=en", ExternalIds()),
        ("com.plexapp.agents.localmedia://12345", ExternalIds()),
        ("mbid://f27ec8db-af05-4f36-916e-3d57f91ecf5e", ExternalIds()),
        # --- Malformed / unknown, must degrade quietly rather than raise ---
        ("", ExternalIds()),
        ("   ", ExternalIds()),
        ("not-a-guid", ExternalIds()),
        ("tmdb://", ExternalIds()),
        ("tmdb://not-a-number", ExternalIds()),
        ("imdb://12345", ExternalIds()),  # IMDb ids must look like tt<digits>
        ("brand.new.agent://999", ExternalIds()),
    ],
)
def test_parse_guid(guid: str, expected: ExternalIds) -> None:
    assert parse_guid(guid) == expected


def test_parse_guid_accepts_none() -> None:
    assert parse_guid(None) == ExternalIds()


def test_parse_guid_is_case_insensitive_on_the_agent() -> None:
    assert parse_guid("COM.PLEXAPP.AGENTS.THEMOVIEDB://78") == ExternalIds(tmdb_id=78)
    assert parse_guid("IMDB://TT0080339") == ExternalIds(imdb_id="tt0080339")


def test_new_agent_item_merges_all_child_guids() -> None:
    ids = extract_external_ids(
        item_guid="plex://movie/5d7768ba96b655001fdc0408",
        guids=["imdb://tt0080339", "tmdb://90", "tvdb://12345"],
    )
    assert ids == ExternalIds(tmdb_id=90, imdb_id="tt0080339", tvdb_id=12345)
    assert ids.is_empty is False


def test_legacy_agent_item_falls_back_to_its_own_guid() -> None:
    """No child <Guid> elements at all -- the legacy case."""
    ids = extract_external_ids(item_guid="com.plexapp.agents.themoviedb://78?lang=en", guids=[])
    assert ids == ExternalIds(tmdb_id=78)


def test_child_guids_win_over_the_item_guid() -> None:
    ids = extract_external_ids(
        item_guid="com.plexapp.agents.themoviedb://11111?lang=en",
        guids=["tmdb://22222"],
    )
    assert ids.tmdb_id == 22222


def test_item_guid_supplements_missing_child_ids() -> None:
    ids = extract_external_ids(
        item_guid="com.plexapp.agents.thetvdb://73244?lang=en",
        guids=["tmdb://90"],
    )
    assert ids == ExternalIds(tmdb_id=90, tvdb_id=73244)


def test_item_with_no_external_ids_at_all() -> None:
    ids = extract_external_ids(item_guid="local://48291", guids=[])
    assert ids == ExternalIds()
    assert ids.is_empty is True


def test_merge_keeps_the_first_writer() -> None:
    first = ExternalIds(tmdb_id=1)
    second = ExternalIds(tmdb_id=2, imdb_id="tt1")
    assert first.merge(second) == ExternalIds(tmdb_id=1, imdb_id="tt1")


@pytest.mark.parametrize(
    "guid",
    [
        "tmdb://1",
        "plex://movie/abc",
        "local://1",
        "com.plexapp.agents.hama://anidb-1",
        "com.plexapp.agents.none://1",
    ],
)
def test_known_schemes(guid: str) -> None:
    assert is_known_scheme(guid) is True


@pytest.mark.parametrize("guid", ["brand.new.agent://999", "garbage", ""])
def test_unknown_schemes(guid: str) -> None:
    assert is_known_scheme(guid) is False


def test_unknown_schemes_reports_only_the_unrecognised() -> None:
    assert unknown_schemes(
        item_guid="com.plexapp.agents.brandnew://5",
        guids=["tmdb://90", "somethingelse://7"],
    ) == ["somethingelse://7", "com.plexapp.agents.brandnew://5"]
