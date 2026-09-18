"""Wikidata spin-off discovery.

The shapes here were taken from real SPARQL responses. What matters most is that this stays
*optional*: a Wikidata outage must cost the suggestions and nothing else, because the scan's
actual job -- the library snapshot -- has already been done by the time this runs.
"""

from __future__ import annotations

import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError
from sqlmodel import Session, select

from app.clients.wikidata_client import (
    SPARQL_ENDPOINT,
    SpinoffRelation,
    WikidataClient,
    WikidataError,
)
from app.models import MappingConfidence, MappingSource, SpinoffMapping
from app.services import tv_spinoff_service


def _client(**kwargs) -> WikidataClient:
    return WikidataClient(max_requests_per_second=10_000, **kwargs)


def _binding(source: int, spin: int, name: str, prop: str | None = None) -> dict:
    row = {
        "tmdb": {"value": str(source)},
        "spin": {"value": f"http://www.wikidata.org/entity/Q{spin}"},
        "spinLabel": {"value": name},
        "spinTmdb": {"value": str(spin)},
    }
    if prop:
        row["prop"] = {"value": f"http://www.wikidata.org/entity/{prop}"}
    return row


def _sparql(*rows: dict) -> dict:
    return {"results": {"bindings": list(rows)}}


def _respond(*responses_in_order: dict) -> None:
    for payload in responses_in_order:
        responses.add(responses.GET, SPARQL_ENDPOINT, json=payload)


@responses.activate
def test_finds_a_spinoff_whose_name_does_not_quote_its_parent() -> None:
    """The whole reason this exists. No name heuristic can get from Family Guy to American Dad!"""
    _respond(_sparql(), _sparql(_binding(1434, 1433, "American Dad!", "P144")))

    found = _client().spinoffs_for([1434])

    assert len(found) == 1
    assert found[0].spinoff_name == "American Dad!"
    assert found[0].spinoff_tmdb_id == 1433


@responses.activate
def test_an_explicit_spinoff_statement_is_recorded_as_such() -> None:
    _respond(_sparql(_binding(4614, 17610, "NCIS: Los Angeles")), _sparql())

    found = _client().spinoffs_for([4614])

    assert found[0].relation == "P2512"
    assert found[0].is_explicit_spinoff


@responses.activate
def test_a_weaker_relation_is_not_dressed_up_as_an_explicit_one() -> None:
    """'follows' means a successor, which is usually but not always a spin-off. The distinction
    reaches the user, so it must not be lost here."""
    _respond(_sparql(), _sparql(_binding(1, 2, "Successor", "P155")))

    assert not _client().spinoffs_for([1])[0].is_explicit_spinoff


@responses.activate
def test_an_explicit_statement_wins_when_both_directions_return_the_same_pair() -> None:
    _respond(_sparql(_binding(1, 2, "Both ways")), _sparql(_binding(1, 2, "Both ways", "P155")))

    found = _client().spinoffs_for([1])

    assert len(found) == 1, "the same pair was recorded twice"
    assert found[0].is_explicit_spinoff


@responses.activate
def test_a_show_without_a_tmdb_id_is_skipped() -> None:
    """Wikidata knows of spin-offs that TMDb has no record of. They cannot be added to Sonarr, so
    listing them would only be an invitation to click a button that cannot work."""
    row = _binding(1, 2, "Obscure")
    del row["spinTmdb"]
    _respond(_sparql(row), _sparql())

    assert _client().spinoffs_for([1]) == []


@responses.activate
def test_a_show_is_never_its_own_spinoff() -> None:
    _respond(_sparql(_binding(7, 7, "Itself")), _sparql())

    assert _client().spinoffs_for([7]) == []


@responses.activate
def test_ids_are_batched() -> None:
    _respond(*([_sparql()] * 20))

    _client(batch_size=2).spinoffs_for([1, 2, 3, 4, 5])

    # Three batches of at most two ids, two queries each (forward and inverse).
    assert len(responses.calls) == 6


@responses.activate
def test_one_failing_batch_does_not_lose_the_others() -> None:
    """Partial spin-off data is worth having."""
    responses.add(responses.GET, SPARQL_ENDPOINT, status=500)          # batch 1 forward
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())      # batch 1 inverse
    responses.add(responses.GET, SPARQL_ENDPOINT,
                  json=_sparql(_binding(3, 9, "Survivor")))            # batch 2 forward
    responses.add(responses.GET, SPARQL_ENDPOINT, json=_sparql())      # batch 2 inverse

    found = _client(batch_size=2).spinoffs_for([1, 2, 3])

    assert [r.spinoff_name for r in found] == ["Survivor"]


@responses.activate
def test_an_unreachable_endpoint_raises_rather_than_returning_nothing() -> None:
    """Silently returning [] would be indistinguishable from 'this library has no spin-offs'."""
    responses.add(responses.GET, SPARQL_ENDPOINT, body=RequestsConnectionError("boom"))

    with pytest.raises(WikidataError):
        _client()._run("SELECT * WHERE {}")


@responses.activate
def test_a_response_that_is_not_sparql_json_is_an_error() -> None:
    responses.add(responses.GET, SPARQL_ENDPOINT, json={"unexpected": True})

    with pytest.raises(WikidataError):
        _client()._run("SELECT * WHERE {}")


def test_no_ids_asks_wikidata_nothing() -> None:
    assert _client().spinoffs_for([]) == []


def test_requests_identify_themselves() -> None:
    """The query service is donated infrastructure and its operators ask callers to say who they
    are, so they can get in touch rather than block."""
    client = _client()

    agent = client._session.headers["User-Agent"]
    assert "Franchisarr" in agent and "github.com/prophetizer/franchisarr" in agent


# ------------------------------------------------------------------ importing


def _relation(source: int, spin: int, relation: str = "P2512") -> SpinoffRelation:
    return SpinoffRelation(
        source_tmdb_id=source, spinoff_tmdb_id=spin, spinoff_name=f"Show {spin}",
        relation=relation, wikidata_id=f"Q{spin}",
    )


def test_discovered_relations_become_mappings(session: Session) -> None:
    """Only "based on" is marked possible: a sequel, prequel or spin-off statement is specific
    enough to state as fact, while "based on" is the property remakes also use."""
    added, refreshed = tv_spinoff_service.import_wikidata_relations(
        session, [_relation(1, 2), _relation(1, 3, "P155"), _relation(1, 4, "P144")]
    )

    assert (added, refreshed) == (3, 0)
    rows = session.exec(select(SpinoffMapping)).all()
    assert {r.spinoff_show_tmdb_id: r.confidence for r in rows} == {
        2: MappingConfidence.CONFIRMED.value,
        3: MappingConfidence.CONFIRMED.value,
        4: MappingConfidence.HEURISTIC.value,
    }
    assert all(r.source == MappingSource.WIKIDATA.value for r in rows)


def test_importing_the_same_relations_twice_adds_nothing(session: Session) -> None:
    """Every scan re-runs this, so it has to be idempotent."""
    tv_spinoff_service.import_wikidata_relations(session, [_relation(1, 2)])
    added, refreshed = tv_spinoff_service.import_wikidata_relations(session, [_relation(1, 2)])

    assert (added, refreshed) == (0, 0)
    assert len(session.exec(select(SpinoffMapping)).all()) == 1


def test_a_relation_that_gets_upgraded_is_refreshed(session: Session) -> None:
    tv_spinoff_service.import_wikidata_relations(session, [_relation(1, 2, "P144")])
    added, refreshed = tv_spinoff_service.import_wikidata_relations(session, [_relation(1, 2)])

    assert (added, refreshed) == (0, 1)
    row = session.exec(select(SpinoffMapping)).one()
    assert row.confidence == MappingConfidence.CONFIRMED.value
    assert row.origin_ref == "P2512"


def test_a_mapping_the_user_added_is_never_overwritten(session: Session) -> None:
    """Their judgement outranks Wikidata's, and a scan runs unattended."""
    tv_spinoff_service.add_mapping(session, source_show_tmdb_id=1, spinoff_show_tmdb_id=2)

    added, refreshed = tv_spinoff_service.import_wikidata_relations(
        session, [_relation(1, 2, "P144")]
    )

    assert (added, refreshed) == (0, 0)
    row = session.exec(select(SpinoffMapping)).one()
    assert row.source == MappingSource.LOCAL.value
    assert row.confidence == MappingConfidence.CONFIRMED.value


def test_a_relation_pointing_at_itself_is_ignored(session: Session) -> None:
    added, _ = tv_spinoff_service.import_wikidata_relations(session, [_relation(5, 5)])

    assert added == 0
    assert session.exec(select(SpinoffMapping)).all() == []


# ------------------------------------------------------------------ remakes are not spin-offs


def _based_on(parent: str, spin_name: str, parent_lang: str | None, spin_lang: str | None) -> dict:
    row = _binding(1, 2, spin_name, "P144")
    row["seriesLabel"] = {"value": parent}
    if parent_lang:
        row["srcLang"] = {"value": f"http://www.wikidata.org/entity/{parent_lang}"}
    if spin_lang:
        row["spinLang"] = {"value": f"http://www.wikidata.org/entity/{spin_lang}"}
    return row


@responses.activate
def test_a_foreign_language_remake_is_not_offered_as_a_spinoff() -> None:
    """Brooklyn Nine-Nine -> Escouade 99 is a French remake. "Based on" is the property both a
    remake and a spin-off use, and on the real library it was almost exactly half each."""
    _respond(_sparql(), _sparql(_based_on("Brooklyn Nine-Nine", "Escouade 99", "Q1860", "Q150")))

    assert _client().spinoffs_for([1]) == []


@responses.activate
def test_a_remake_that_keeps_the_original_title_is_not_offered_either() -> None:
    """The other remake signature: Ghosts -> Ghosts, The Night Manager -> The Night Manager."""
    _respond(_sparql(), _sparql(_based_on("Ghosts", "Ghosts", None, None)))

    assert _client().spinoffs_for([1]) == []


@responses.activate
def test_a_real_spinoff_survives_the_remake_filter() -> None:
    """Same language, different title -- The Big Bang Theory -> Georgie & Mandy's First Marriage,
    Letterkenny -> Shoresy. Dropping these would gut the property's value."""
    _respond(_sparql(), _sparql(
        _based_on("Letterkenny", "Shoresy", "Q1860", "Q1860")))

    assert [r.spinoff_name for r in _client().spinoffs_for([1])] == ["Shoresy"]


@responses.activate
def test_the_remake_filter_only_applies_to_based_on() -> None:
    """"Follows" is a franchise successor, where sharing a title is normal and unremarkable."""
    row = _binding(1, 2, "Ghosts", "P155")
    row["seriesLabel"] = {"value": "Ghosts"}
    _respond(_sparql(), _sparql(row))

    assert len(_client().spinoffs_for([1])) == 1


@responses.activate
def test_an_item_with_no_english_label_is_skipped() -> None:
    """Wikidata's label service echoes the Q-id when there is no label, and "Q140674509" is not
    something to show a user."""
    _respond(_sparql(_binding(1, 2, "Q140674509")), _sparql())

    assert _client().spinoffs_for([1]) == []



# ------------------------------------------------------------------ direction and labels


@responses.activate
def test_a_show_that_is_followed_by_an_owned_one_is_its_prequel() -> None:
    """P156 was not queried at all before this, so prequels were never found: own Yellowstone,
    and 1883 never surfaced. Both halves of the succession are asked for now."""
    _respond(_sparql(), _sparql(_binding(1, 2, "1883", "P156")))

    found = _client().spinoffs_for([1])

    assert found[0].relation == "P156"
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(responses.calls[1].request.url).query)["query"][0]
    assert "wdt:P156" in query


@responses.activate
def test_the_most_specific_statement_wins_for_a_pair() -> None:
    """Yellowstone states 1923 as both a spin-off and a successor; "spin-off" is the one to keep."""
    _respond(_sparql(_binding(1, 2, "1923")), _sparql(_binding(1, 2, "1923", "P155")))

    found = _client().spinoffs_for([1])

    assert len(found) == 1 and found[0].relation == "P2512"


def test_relation_labels_read_after_the_title() -> None:
    from app.clients.wikidata_client import relation_label

    assert relation_label("P2512") == "spin-off of"
    assert relation_label("P155") == "follows"
    assert relation_label("P156") == "precedes"
    assert relation_label("P144") == "based on"
    assert relation_label(None) is None
