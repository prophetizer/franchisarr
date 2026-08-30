"""Tests for the diagnostic script's aggregation.

The script needs a live Plex server, but its summarising is a pure function, so the part that
could silently go wrong is testable here. Without this the script would rot unnoticed, since
nothing else in CI imports it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.clients.plex_client import PlexMovie
from app.clients.plex_guid import ExternalIds
from scripts.plex_guid_audit import audit_items, load_env_file


def _movie(title: str, ids: ExternalIds, *guids: str, year: int | None = 2001) -> PlexMovie:
    return PlexMovie(
        rating_key="1", title=title, year=year, external_ids=ids, guids=tuple(guids)
    )


def test_counts_split_by_how_well_an_item_resolves() -> None:
    audit = audit_items(
        [
            _movie("Resolved", ExternalIds(tmdb_id=90), "tmdb://90"),
            _movie("Resolved too", ExternalIds(tmdb_id=91), "tmdb://91"),
            _movie("IMDb only", ExternalIds(imdb_id="tt1"), "imdb://tt1"),
            _movie("Nothing", ExternalIds(), "local://5"),
        ]
    )

    assert audit.total == 4
    assert audit.with_tmdb == 2
    assert audit.other_id_only == 1
    assert audit.no_ids == 1
    assert audit.tmdb_percent == 50.0


def test_percentage_of_an_empty_library_does_not_divide_by_zero() -> None:
    assert audit_items([]).tmdb_percent == 0.0


def test_guid_schemes_are_counted() -> None:
    audit = audit_items(
        [
            _movie("A", ExternalIds(tmdb_id=1), "tmdb://1", "plex://movie/abc"),
            _movie("B", ExternalIds(tmdb_id=2), "tmdb://2", "plex://movie/def"),
        ]
    )

    assert audit.schemes["tmdb"] == 2
    assert audit.schemes["plex"] == 2


def test_unrecognised_agents_are_flagged() -> None:
    audit = audit_items([_movie("Odd", ExternalIds(), "brand.new.agent://7")])

    assert audit.unknown_schemes["brand.new.agent"] == 1


def test_unmatched_items_are_not_flagged_as_unrecognised() -> None:
    """An item Plex couldn't match is a normal state, and both agent generations spell it
    differently. Flagging these would bury a genuinely new format in noise."""
    audit = audit_items(
        [
            _movie("Local", ExternalIds(), "local://1"),
            _movie("Legacy unmatched", ExternalIds(), "com.plexapp.agents.none://abc?lang=xn"),
            _movie("Modern unmatched", ExternalIds(), "tv.plex.agents.none://519433"),
        ]
    )

    assert audit.unknown_schemes == {}
    assert audit.no_ids == 3


def test_examples_are_capped_and_only_cover_unresolved_items() -> None:
    items = [_movie(f"Bad {n}", ExternalIds(), "local://1") for n in range(20)]
    items.append(_movie("Good", ExternalIds(tmdb_id=5), "tmdb://5"))

    audit = audit_items(items, sample_limit=3)

    assert len(audit.examples) == 3
    assert all(title.startswith("Bad") for title, _ in audit.examples)


def test_examples_handle_a_missing_year() -> None:
    audit = audit_items([_movie("No year", ExternalIds(), "local://1", year=None)])

    assert audit.examples[0][0] == "No year (no year)"


def test_env_file_does_not_override_the_real_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("PLEX_URL=http://from-file:32400\nPLEX_TOKEN=file-token\n")
    monkeypatch.setenv("PLEX_URL", "http://from-environment:32400")

    supplied = load_env_file(env_file)

    assert supplied == ["PLEX_TOKEN"]
    assert os.environ["PLEX_URL"] == "http://from-environment:32400"
    assert os.environ["PLEX_TOKEN"] == "file-token"


def test_env_file_ignores_comments_and_blank_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# a comment\n\nPLEX_TOKEN=abc\nnot-a-pair\n")
    monkeypatch.delenv("PLEX_TOKEN", raising=False)

    assert load_env_file(env_file) == ["PLEX_TOKEN"]


def test_missing_env_file_is_not_an_error(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "nope.env") == []
