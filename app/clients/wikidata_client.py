"""Wikidata as a spin-off data source.

Franchisarr shipped without one. TMDb models no relation between a show and its spin-offs, so v1
fell back on a name heuristic ("NCIS" -> "NCIS: Los Angeles") plus mappings the user added by
hand. That misses every spin-off whose title does not quote its parent, which is most of the
interesting ones: Family Guy -> American Dad!, black-ish -> Mixed-ish, Young Sheldon -> Georgie &
Mandy's First Marriage, Reacher -> Neagley.

Wikidata does model it, and it joins cleanly: 641 of this library's 656 shows (98%) resolve to a
Wikidata item through their TMDb id (P4983), so nothing here matches on names.

Which properties, measured rather than assumed:

- P2512 "has spin-off" is the explicit one, and it is the *sparse* one -- only 2% of matched
  shows carry it. On its own it is not worth the request.
- The productive direction is the inverse: works that point back at a show the user owns, via
  P144 "based on", P155 "follows", or P807 "separated from". That found 78 relations on the same
  library against P2512's 15.

So both directions are queried, and they are not treated as equal: P2512 says "spin-off" and is
recorded as confirmed, while the inverse properties say something weaker ("follows" is really a
successor, not a spin-off) and are recorded as heuristic for the user to judge.

No API key, no account, no rate limit published -- but the query service is donated
infrastructure, so requests are batched, spaced, and sent with an identifying User-Agent as its
operators ask.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from app import __version__
from app.clients.rate_limit import RateLimiter

logger = logging.getLogger(__name__)

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
DEFAULT_TIMEOUT = 60

#: WDQS asks callers to identify themselves so they can be contacted rather than blocked.
USER_AGENT = (
    f"Franchisarr/{__version__} "
    "(https://github.com/prophetizer/franchisarr) python-requests"
)

#: Measured: 40 ids per query is reliable, while 150 drew intermittent 502s from the endpoint.
BATCH_SIZE = 40

#: Donated infrastructure. One query every other second is far below anything WDQS objects to.
MAX_REQUESTS_PER_SECOND = 1

MAX_RETRIES = 3

#: Wikidata's class for a broadcast programme. Filtering on it keeps video games and soundtracks
#: -- both of which are legitimately "spin-offs" of a TV show -- out of a list meant for Sonarr.
BROADCAST_PROGRAMME = "wd:Q15416"


class WikidataError(RuntimeError):
    """Any Wikidata failure. Never fatal: spin-off discovery is an enrichment, not the feature."""


@dataclass(frozen=True)
class SpinoffRelation:
    """One show-to-show relation, already resolved to TMDb ids on both ends."""

    source_tmdb_id: int
    spinoff_tmdb_id: int
    spinoff_name: str
    #: The Wikidata property that produced this, e.g. "P2512". Stored as the mapping's origin_ref
    #: so a wrong suggestion can be traced back to the statement that caused it.
    relation: str
    wikidata_id: str | None = None

    @property
    def is_explicit_spinoff(self) -> bool:
        """P2512 is literally "has spin-off". The others are weaker relations that usually, but
        not always, mean the same thing."""
        return self.relation == "P2512"


def _values_clause(tmdb_ids: list[int]) -> str:
    # TMDb ids are stored as strings on Wikidata, and these are ints from our own database, so
    # there is nothing here that a caller could inject.
    return " ".join(f'"{int(i)}"' for i in tmdb_ids)


def _forward_query(tmdb_ids: list[int]) -> str:
    """Shows the user owns that declare a spin-off."""
    return f"""
    SELECT ?tmdb ?spin ?spinLabel ?spinTmdb WHERE {{
      VALUES ?tmdb {{ {_values_clause(tmdb_ids)} }}
      ?series wdt:P4983 ?tmdb .
      ?series wdt:P2512 ?spin .
      ?spin wdt:P31/wdt:P279* {BROADCAST_PROGRAMME} .
      ?spin wdt:P4983 ?spinTmdb .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """


def _inverse_query(tmdb_ids: list[int]) -> str:
    """Shows that point back at something the user owns. The productive direction.

    Both works' original language and title come back too, because P144 "based on" is the
    property a foreign-language *remake* uses -- and a remake is not a spin-off.
    """
    return f"""
    SELECT ?tmdb ?series ?seriesLabel ?spin ?spinLabel ?spinTmdb ?prop ?srcLang ?spinLang WHERE {{
      VALUES ?tmdb {{ {_values_clause(tmdb_ids)} }}
      ?series wdt:P4983 ?tmdb .
      ?spin ?p ?series .
      VALUES ?p {{ wdt:P144 wdt:P155 wdt:P807 }}
      ?spin wdt:P31/wdt:P279* {BROADCAST_PROGRAMME} .
      ?spin wdt:P4983 ?spinTmdb .
      ?prop wikibase:directClaim ?p .
      OPTIONAL {{ ?series wdt:P364 ?srcLang . }}
      OPTIONAL {{ ?spin   wdt:P364 ?spinLang . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """


def _is_bare_entity_id(label: str) -> bool:
    """Wikidata's label service returns the Q-id itself when nothing has an English label. Such
    an item is unusable here -- there is no name to show the user."""
    return bool(label) and label[0] == "Q" and label[1:].isdigit()


def _looks_like_a_remake(parent_name: str, spin_name: str,
                         parent_lang: str | None, spin_lang: str | None) -> bool:
    """Distinguish a remake from a spin-off among "based on" statements.

    Measured on the real library, where P144 was almost exactly half each. Two signals separate
    them: a remake is usually in another language (Brooklyn Nine-Nine -> Escouade 99, Ghosts ->
    Ta Fantasmata, New Amsterdam -> Hayat Bugun) and it usually keeps the original's title
    (Ghosts -> Ghosts, The Night Manager -> The Night Manager). A spin-off does neither.
    """
    if parent_lang and spin_lang and parent_lang != spin_lang:
        return True
    return parent_name.strip().casefold() == spin_name.strip().casefold()


class WikidataClient:
    def __init__(
        self,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        batch_size: int = BATCH_SIZE,
        max_requests_per_second: int = MAX_REQUESTS_PER_SECOND,
        session: requests.Session | None = None,
    ) -> None:
        self._timeout = timeout
        self._batch_size = max(1, batch_size)
        self._limiter = RateLimiter(max_requests_per_second)
        self._session = session or requests.Session()
        # Assigned, not setdefault: requests ships its own "python-requests/x.y" User-Agent, so a
        # setdefault silently never applies -- and a generic agent is exactly what WDQS throttles.
        self._session.headers["User-Agent"] = USER_AGENT

    def _run(self, query: str) -> list[dict]:
        for attempt in range(MAX_RETRIES):
            self._limiter.wait()
            try:
                response = self._session.get(
                    SPARQL_ENDPOINT,
                    params={"query": query, "format": "json"},
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                raise WikidataError("Could not reach Wikidata") from exc

            # WDQS answers overload with 429 and 502 more or less interchangeably.
            if response.status_code in (429, 502, 503, 504):
                delay = 2 ** attempt
                logger.debug("Wikidata returned %s; retrying in %ss",
                             response.status_code, delay)
                time.sleep(delay)
                continue
            if response.status_code >= 400:
                raise WikidataError(f"Wikidata returned {response.status_code}")

            try:
                return response.json()["results"]["bindings"]
            except (ValueError, KeyError) as exc:
                raise WikidataError("Wikidata returned a response in an unexpected shape") from exc

        raise WikidataError("Wikidata kept refusing the query; try again later")

    @staticmethod
    def _parse(rows: list[dict], default_relation: str) -> list[SpinoffRelation]:
        found: list[SpinoffRelation] = []
        for row in rows:
            try:
                source_id = int(row["tmdb"]["value"])
                spin_id = int(row["spinTmdb"]["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if source_id == spin_id:
                continue

            name = str(row.get("spinLabel", {}).get("value") or "")
            if not name or _is_bare_entity_id(name):
                continue

            relation = default_relation
            prop_uri = row.get("prop", {}).get("value", "")
            if prop_uri:
                relation = prop_uri.rsplit("/", 1)[-1]

            if relation == "P144" and _looks_like_a_remake(
                str(row.get("seriesLabel", {}).get("value") or ""),
                name,
                row.get("srcLang", {}).get("value"),
                row.get("spinLang", {}).get("value"),
            ):
                continue

            entity = row.get("spin", {}).get("value", "")
            found.append(
                SpinoffRelation(
                    source_tmdb_id=source_id,
                    spinoff_tmdb_id=spin_id,
                    spinoff_name=name,
                    relation=relation,
                    wikidata_id=entity.rsplit("/", 1)[-1] or None,
                )
            )
        return found

    def spinoffs_for(self, tmdb_ids: list[int]) -> list[SpinoffRelation]:
        """Every known spin-off relation for these shows, both directions, deduplicated.

        A batch that fails is logged and skipped rather than aborting the rest: partial spin-off
        data is worth having, and this is decoration on a scan that has already done its job.
        """
        unique = sorted({int(i) for i in tmdb_ids})
        if not unique:
            return []

        relations: dict[tuple[int, int], SpinoffRelation] = {}
        for start in range(0, len(unique), self._batch_size):
            batch = unique[start:start + self._batch_size]
            for builder, default_relation in (
                (_forward_query, "P2512"),
                (_inverse_query, "P144"),
            ):
                try:
                    rows = self._run(builder(batch))
                except WikidataError as exc:
                    logger.warning("Wikidata batch failed, continuing without it: %s", exc)
                    continue
                for relation in self._parse(rows, default_relation):
                    key = (relation.source_tmdb_id, relation.spinoff_tmdb_id)
                    # An explicit "has spin-off" beats a weaker inverse relation for the same pair.
                    existing = relations.get(key)
                    if existing is None or (
                        relation.is_explicit_spinoff and not existing.is_explicit_spinoff
                    ):
                        relations[key] = relation

        logger.info("Wikidata returned %d spin-off relation(s) for %d show(s)",
                    len(relations), len(unique))
        return sorted(relations.values(), key=lambda r: (r.source_tmdb_id, r.spinoff_tmdb_id))
