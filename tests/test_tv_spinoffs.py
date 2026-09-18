"""TV spin-off mapping, diffing, and the heuristic tier.

Technical challenge #6 is the shape of this phase: curated mappings are treated as facts, while
heuristic guesses are a visibly separate tier that nothing can act on without a human confirming.
Most of these tests exist to keep those two apart.
"""

from __future__ import annotations

import pytest
import responses
from sqlmodel import Session, select

from app.clients.tmdb_client import TMDB_BASE_URL, TmdbClient
from app.models import (
    DismissedItem,
    ItemType,
    LibraryItem,
    MappingConfidence,
    MappingSource,
    MatchSource,
    SpinoffMapping,
    TmdbShow,
    User,
)
from app.services import tv_spinoff_service as svc

NCIS = 4614
NCIS_LA = 17610
NCIS_NOLA = 61387


def _own_show(session: Session, tmdb_id: int, title: str, **kwargs) -> LibraryItem:
    fields = {
        "library_key": "2",
        "item_key": str(tmdb_id),
        "item_type": ItemType.SHOW.value,
        "title": title,
        "year": 2003,
        "tmdb_id": tmdb_id,
        "match_source": MatchSource.GUID.value,
        **kwargs,
    }
    item = LibraryItem(**fields)
    session.add(item)
    session.commit()
    return item


def _user(session: Session) -> User:
    user = User(local_username="admin", is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# ------------------------------------------------------------------ the heuristic


@pytest.mark.parametrize(
    ("source", "candidate", "expected"),
    [
        ("NCIS", "NCIS: Los Angeles", True),
        ("NCIS", "NCIS: New Orleans", True),
        ("CSI", "CSI: Miami", True),
        ("Star Trek", "Star Trek: Deep Space Nine", True),
        ("Law & Order", "Law & Order: Special Victims Unit", True),
        # Same prefix, no separator -- a different show that happens to start the same way.
        ("NCIS", "NCISomething", False),
        # The show itself.
        ("NCIS", "NCIS", False),
        ("Doctor Who", "Doctor Who - Confidential", True),
        # Real spin-offs that this heuristic deliberately cannot find: they don't carry the
        # parent's name, so only a curated mapping will do.
        ("Chicago Fire", "Chicago P.D.", False),
        ("Breaking Bad", "Better Call Saul", False),
        ("The Walking Dead", "Fear the Walking Dead", False),
        # Unrelated shows that merely begin with the same word. Measured against a real 656-show
        # library, allowing a plain space as a separator made these the bulk of the output.
        ("Angel", "Angel Beats!", False),
        ("Angel", "Angel Street", False),
        ("Atlanta", "Atlanta Plastic", False),
        ("Atomic", "Atomic Betty", False),
        ("Barry", "Barry Welsh is Coming", False),
        # TMDb carries separate entries for seasons of the same show. Not spin-offs.
        ("Fallout", "Fallout - Season 2", False),
        ("Berserk", "Berserk: Season 3", False),
        ("Arcane", "Arcane: Part 2", False),
    ],
)
def test_title_heuristic(source: str, candidate: str, expected: bool) -> None:
    assert svc.looks_like_spinoff_of(source, candidate) is expected


def test_very_short_names_never_match_on_prefix() -> None:
    """Otherwise every show beginning with "The" is a spin-off of every other."""
    assert svc.looks_like_spinoff_of("Up", "Up: The Sequel") is False


@responses.activate
def test_heuristic_candidates_exclude_owned_and_mapped_shows(session: Session) -> None:
    """A suggestion the user can't act on is noise, and this tier's whole cost is human attention."""
    show = _own_show(session, NCIS, "NCIS")
    _own_show(session, NCIS_LA, "NCIS: Los Angeles")  # already owned
    svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_NOLA)

    responses.add(responses.GET, f"{TMDB_BASE_URL}/search/tv", json={"results": [
        {"id": NCIS, "name": "NCIS", "first_air_date": "2003-09-23"},
        {"id": NCIS_LA, "name": "NCIS: Los Angeles", "first_air_date": "2009-09-22"},
        {"id": NCIS_NOLA, "name": "NCIS: New Orleans", "first_air_date": "2014-09-23"},
        {"id": 157950, "name": "NCIS: Sydney", "first_air_date": "2023-11-10"},
    ]})

    found = svc.heuristic_candidates(session, TmdbClient("k" * 32), show)

    assert [c.spinoff_tmdb_id for c in found] == [157950]
    assert found[0].confidence == MappingConfidence.HEURISTIC.value


@responses.activate
def test_a_heuristic_candidate_is_never_treated_as_confirmed(session: Session) -> None:
    show = _own_show(session, NCIS, "NCIS")
    responses.add(responses.GET, f"{TMDB_BASE_URL}/search/tv", json={"results": [
        {"id": NCIS_LA, "name": "NCIS: Los Angeles", "first_air_date": "2009-09-22"},
    ]})

    found = svc.heuristic_candidates(session, TmdbClient("k" * 32), show)

    assert found[0].is_confirmed is False
    # Nothing was written: a guess is not a mapping until a person says so.
    assert session.exec(select(SpinoffMapping)).all() == []


@responses.activate
def test_a_tmdb_failure_yields_no_candidates_rather_than_an_error(session: Session) -> None:
    show = _own_show(session, NCIS, "NCIS")
    responses.add(responses.GET, f"{TMDB_BASE_URL}/search/tv", status=500)

    assert svc.heuristic_candidates(session, TmdbClient("k" * 32), show) == []


# ------------------------------------------------------------------ mappings


def test_a_mapping_is_always_written_as_local_and_confirmed(session: Session) -> None:
    """v1 never writes `community`; the value exists so a future sync is additive."""
    mapping = svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_LA)

    assert mapping.source == MappingSource.LOCAL.value
    assert mapping.confidence == MappingConfidence.CONFIRMED.value


def test_adding_the_same_mapping_twice_is_a_no_op(session: Session) -> None:
    svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_LA)

    assert svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_LA) is None
    assert len(session.exec(select(SpinoffMapping)).all()) == 1


def test_a_show_cannot_be_a_spinoff_of_itself(session: Session) -> None:
    with pytest.raises(ValueError):
        svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS)


def test_a_mapping_records_who_added_it(session: Session) -> None:
    user = _user(session)

    mapping = svc.add_mapping(
        session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_LA, user=user
    )

    assert mapping.added_by_user_id == user.id


def test_removing_a_mapping(session: Session) -> None:
    mapping = svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_LA)

    svc.remove_mapping(session, mapping.id)

    assert session.exec(select(SpinoffMapping)).all() == []


# ------------------------------------------------------------------ the diff


def test_a_mapped_spinoff_you_do_not_own_is_suggested(session: Session) -> None:
    _own_show(session, NCIS, "NCIS")
    session.add(TmdbShow(tmdb_id=NCIS_LA, name="NCIS: Los Angeles", first_air_year=2009))
    session.commit()
    svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_LA)

    suggestions = svc.missing_spinoffs(session)

    assert len(suggestions) == 1
    assert suggestions[0].spinoff_name == "NCIS: Los Angeles"
    assert suggestions[0].source_show_name == "NCIS"
    assert suggestions[0].first_air_year == 2009


def test_a_spinoff_you_already_own_is_not_suggested(session: Session) -> None:
    _own_show(session, NCIS, "NCIS")
    _own_show(session, NCIS_LA, "NCIS: Los Angeles")
    svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_LA)

    assert svc.missing_spinoffs(session) == []


def test_a_mapping_whose_source_you_do_not_own_is_not_suggested(session: Session) -> None:
    """Suggestions follow from what you watch. Otherwise the mapping list would recommend shows
    with no connection to the library at all."""
    svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_LA)

    assert svc.missing_spinoffs(session) == []


def test_a_dismissed_spinoff_is_hidden_for_that_user_only(session: Session) -> None:
    _own_show(session, NCIS, "NCIS")
    svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_LA)
    user = _user(session)
    session.add(
        DismissedItem(user_id=user.id, item_type=ItemType.SHOW.value, tmdb_id=NCIS_LA)
    )
    session.commit()

    assert svc.missing_spinoffs(session, user.id) == []
    assert svc.missing_spinoffs(session, user_id=None), "another user still sees it"


def test_a_dismissed_movie_does_not_hide_a_show_with_the_same_id(session: Session) -> None:
    """tmdb ids are only unique within a type, so the dismiss lookup has to filter on it."""
    _own_show(session, NCIS, "NCIS")
    svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_LA)
    user = _user(session)
    session.add(
        DismissedItem(user_id=user.id, item_type=ItemType.MOVIE.value, tmdb_id=NCIS_LA)
    )
    session.commit()

    assert len(svc.missing_spinoffs(session, user.id)) == 1


def test_an_unconfirmed_show_match_does_not_count_as_owned(session: Session) -> None:
    _own_show(session, NCIS, "NCIS")
    _own_show(session, NCIS_LA, "NCIS: LA", needs_review=True,
              match_source=MatchSource.TITLE.value, match_confidence=0.7)
    svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_LA)

    assert len(svc.missing_spinoffs(session)) == 1


def test_movies_are_not_mistaken_for_shows(session: Session) -> None:
    """The snapshot table holds both, so every query has to filter on item_type."""
    session.add(
        LibraryItem(library_key="1", item_key="x", item_type=ItemType.MOVIE.value,
                    title="A Film", tmdb_id=NCIS, match_source=MatchSource.GUID.value)
    )
    session.commit()
    svc.add_mapping(session, source_show_tmdb_id=NCIS, spinoff_show_tmdb_id=NCIS_LA)

    assert svc.owned_show_ids(session) == set()
    assert svc.missing_spinoffs(session) == []
