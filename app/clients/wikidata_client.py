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

#: Donated infrastructure, so this stays modest -- but the cross-media sweep is two hundred
#: queries that each answer in a tenth of a second, and at one per second it took four minutes
#: of a scan doing nothing but waiting. Three per second is still far below anything WDQS
#: objects to, and takes that step to about a minute.
MAX_REQUESTS_PER_SECOND = 3

MAX_RETRIES = 3

#: Wikidata's class for a broadcast programme. Filtering on it keeps video games and soundtracks
#: -- both of which are legitimately "spin-offs" of a TV show -- out of a list meant for Sonarr.
BROADCAST_PROGRAMME = "wd:Q15416"
#: Direct classes for the cross-media queries. Direct (P31) rather than the subclass walk used
#: above, because these run over the whole film library -- 86 batches on the test library --
#: and the walk inside that many queries is what turns a 0.1s answer into a 65s timeout.
FILM = "wd:Q11424"
TV_SERIES = "wd:Q5398426"
#: TMDb *movie* id, as distinct from P4983 for TV.
TMDB_MOVIE_ID = "P4947"
TMDB_TV_ID = "P4983"
#: Genres to exclude outright. Three of the fourteen films "based on" a show the test library
#: owned were pornographic parodies, each stated with a straight face on Wikidata. Both the
#: genre and its parody subgenre are listed, because one of the three carried only the latter --
#: and a subclass walk here would cost the query time this file is at pains to avoid.
PORNOGRAPHIC_GENRES = ("wd:Q185529", "wd:Q16254232")


#: What each property means for the *spin* relative to the *source*, as a phrase that reads
#: after the spin's title: "Dragon Ball GT -- follows Dragon Ball Z".
#:
#: "Follows" and "precedes" rather than "sequel" and "prequel", deliberately. On the real library
#: most P156 hits are *originals* -- Bosch before Bosch: Legacy, Dragon Ball before Dragon Ball Z
#: -- and an original is not a prequel; a prequel is made later and set earlier. And Wikidata
#: states succession in whichever order its editors had in mind (Yellowstone is "followed by"
#: nothing and "follows" 1923, which is story order). "Precedes" is true either way; "prequel"
#: is a claim the data does not make.
RELATION_LABELS = {
    "P2512": "spin-off of",
    "P807": "spin-off of",      # "separated from"
    "P155": "follows",          # spin *follows* source
    "P156": "precedes",         # spin is *followed by* source
    "P144": "based on",
}

#: Relations specific enough to state as fact rather than mark "possible".
PRECISE_RELATIONS = frozenset({"P2512", "P807", "P155", "P156"})

#: Most specific first, for when one pair of shows is stated more than one way.
RELATION_PRIORITY = {"P2512": 0, "P807": 1, "P156": 2, "P155": 2, "P144": 3}


def relation_label(relation: str | None) -> str | None:
    return RELATION_LABELS.get(relation or "")


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

    @property
    def is_precise(self) -> bool:
        """Whether the relation says something specific enough to state as fact. "Based on" is
        the one that does not: after remake filtering it is usually a spin-off, but "usually" is
        what the *possible* label is for."""
        return self.relation in PRECISE_RELATIONS

    @property
    def rank(self) -> int:
        """When one pair is stated several ways, keep the most specific statement."""
        return RELATION_PRIORITY.get(self.relation, 99)


@dataclass(frozen=True)
class CrossMediaRelation:
    """A film related to an owned show, or a show related to an owned film."""

    source_type: str          # "show" or "movie" -- what the user owns
    source_tmdb_id: int
    target_type: str          # the other one
    target_tmdb_id: int
    target_name: str
    relation: str
    wikidata_id: str | None = None

    @property
    def is_precise(self) -> bool:
        return self.relation in PRECISE_RELATIONS

    @property
    def rank(self) -> int:
        return RELATION_PRIORITY.get(self.relation, 99)


@dataclass(frozen=True)
class FranchiseGroup:
    wikidata_id: str
    name: str
    kind: str | None
    #: Other Wikidata items folded into this one -- sub-groups and same-named twins. The roster
    #: is queried for all of them, so nothing filed only on the twin is lost in the merge.
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class FranchiseTitle:
    """A film or series Wikidata files under a franchise, resolved to a TMDb id."""

    franchise_id: str
    item_type: str          # "movie" or "show"
    tmdb_id: int
    name: str


#: Group classes worth treating as a franchise. P179 "part of the series" points at all sorts
#: -- studio catalogues, Wikimedia list articles, "Batman in film" -- so it is admitted only
#: when the target is one of these. P8345 "media franchise" is trusted as it comes.
FRANCHISE_KINDS = frozenset({
    "media franchise", "film series", "film franchise", "anime film series",
    "animated film series", "shared universe", "brand", "crossover fiction",
    "television franchise", "literary cycle",
})

#: Labels that mark a P179 target as a catalogue rather than a franchise, whatever its class.
CATALOGUE_WORDS = ("list of", "feature films", "productions", "greatest", " in film")

#: Class labels that make a franchise member worth listing: whole films and whole series.
MEMBER_ALLOW = ("film", "series")
#: ...and the ones that don't, even when the item somehow carries a TMDb id. Star Wars has
#: 3,178 members on Wikidata and most of the ones with an id are one of these.
MEMBER_DENY = ("episode", "short", "project", "web series", "4d", "special", "trailer", "video game")


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

    P155 "follows" and P156 "followed by" are both asked for, because they are the two halves of
    one fact and Wikidata editors state whichever they think of first. A show that *follows* an
    owned one comes after it; one *followed by* an owned one comes before -- and without P156,
    the "before" half was never found at all. On the real library that half was 40 relations,
    mostly the original series of a franchise the user owns the continuation of.

    Both works' original language and title come back too, because P144 "based on" is the
    property a foreign-language *remake* uses -- and a remake is not a spin-off.
    """
    return f"""
    SELECT ?tmdb ?series ?seriesLabel ?spin ?spinLabel ?spinTmdb ?prop ?srcLang ?spinLang WHERE {{
      VALUES ?tmdb {{ {_values_clause(tmdb_ids)} }}
      ?series wdt:P4983 ?tmdb .
      ?spin ?p ?series .
      VALUES ?p {{ wdt:P144 wdt:P155 wdt:P156 wdt:P807 }}
      ?spin wdt:P31/wdt:P279* {BROADCAST_PROGRAMME} .
      ?spin wdt:P4983 ?spinTmdb .
      ?prop wikibase:directClaim ?p .
      OPTIONAL {{ ?series wdt:P364 ?srcLang . }}
      OPTIONAL {{ ?spin   wdt:P364 ?spinLang . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """


def _cross_media_query(
    tmdb_ids: list[int], *, mine_id_prop: str, other_class: str, other_id_prop: str,
    other_points_at_mine: bool,
) -> str:
    """One direction of one cross-media relation, kept flat on purpose.

    The obvious form -- a UNION of both directions in one query -- times out at WDQS's limit
    on a 40-id batch, while each half alone answers in a tenth of a second. Two cheap queries
    beat one that never returns.
    """
    pattern = "?other ?p ?mine ." if other_points_at_mine else "?mine ?p ?other ."
    return f"""
    SELECT ?tmdb ?mineLabel ?other ?otherLabel ?otherTmdb ?prop ?srcLang ?otherLang WHERE {{
      VALUES ?tmdb {{ {_values_clause(tmdb_ids)} }}
      ?mine wdt:{mine_id_prop} ?tmdb .
      {pattern}
      VALUES ?p {{ wdt:P2512 wdt:P144 wdt:P155 wdt:P156 wdt:P807 }}
      ?other wdt:P31 {other_class} .
      ?other wdt:{other_id_prop} ?otherTmdb .
      MINUS {{ ?other wdt:P136 ?excluded . VALUES ?excluded {{ {" ".join(PORNOGRAPHIC_GENRES)} }} }}
      ?prop wikibase:directClaim ?p .
      OPTIONAL {{ ?mine  wdt:P364 ?srcLang . }}
      OPTIONAL {{ ?other wdt:P364 ?otherLang . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """


def _membership_query(tmdb_ids: list[int], *, id_prop: str) -> str:
    """Which franchises each owned title belongs to, by either property, with the group's class
    so P179 targets can be filtered."""
    return f"""
    SELECT ?tmdb ?p ?fr ?frLabel ?frClassLabel WHERE {{
      VALUES ?tmdb {{ {_values_clause(tmdb_ids)} }}
      ?item wdt:{id_prop} ?tmdb .
      VALUES ?p {{ wdt:P8345 wdt:P179 }}
      ?item ?p ?fr .
      OPTIONAL {{ ?fr wdt:P31 ?frClass . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """


def _parents_query(franchise_ids: list[str]) -> str:
    """P361 "part of", so "The Infinity Saga" folds into "Marvel Cinematic Universe"."""
    values = " ".join(f"wd:{q}" for q in franchise_ids if q.startswith("Q") and q[1:].isdigit())
    return f"""
    SELECT ?child ?parent WHERE {{
      VALUES ?child {{ {values} }}
      ?child wdt:P361 ?parent .
    }}
    """


def _members_query(franchise_id: str) -> str:
    """Everything filed under one franchise that carries a TMDb id, with classes for filtering."""
    return f"""
    SELECT ?m ?mLabel ?tmdbF ?tmdbT ?classLabel WHERE {{
      ?m (wdt:P8345|wdt:P179) wd:{franchise_id} .
      {{ ?m wdt:{TMDB_MOVIE_ID} ?tmdbF . }} UNION {{ ?m wdt:{TMDB_TV_ID} ?tmdbT . }}
      OPTIONAL {{ ?m wdt:P31 ?class . }}
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
                    existing = relations.get(key)
                    if existing is None or relation.rank < existing.rank:
                        relations[key] = relation

        logger.info("Wikidata returned %d spin-off relation(s) for %d show(s)",
                    len(relations), len(unique))
        return sorted(relations.values(), key=lambda r: (r.source_tmdb_id, r.spinoff_tmdb_id))

    def cross_media_for(
        self, *, show_ids: list[int], movie_ids: list[int]
    ) -> list[CrossMediaRelation]:
        """Films related to owned shows, and shows related to owned films.

        Measured before it was built. On the test library the show-to-film direction is small
        (fourteen films, three of them pornographic parodies), while film-to-show is the real
        yield: 53 series, in two coherent kinds -- the series a film continued or was drawn from
        (Firefly for Serenity, Bates Motel for Psycho) and the original series behind a remake
        the user owns (The A-Team, CHiPs, Baywatch).
        """
        found: dict[tuple[str, int, str, int], CrossMediaRelation] = {}

        def sweep(ids: list[int], source_type: str, target_type: str,
                  mine_id_prop: str, other_class: str, other_id_prop: str) -> None:
            unique = sorted({int(i) for i in ids})
            for start in range(0, len(unique), self._batch_size):
                batch = unique[start:start + self._batch_size]
                for other_points_at_mine in (True, False):
                    query = _cross_media_query(
                        batch, mine_id_prop=mine_id_prop, other_class=other_class,
                        other_id_prop=other_id_prop, other_points_at_mine=other_points_at_mine,
                    )
                    try:
                        rows = self._run(query)
                    except WikidataError as exc:
                        logger.warning("Wikidata cross-media batch failed, continuing: %s", exc)
                        continue
                    for row in rows:
                        relation = self._parse_cross(row, source_type, target_type)
                        if relation is None:
                            continue
                        key = (relation.source_type, relation.source_tmdb_id,
                               relation.target_type, relation.target_tmdb_id)
                        existing = found.get(key)
                        if existing is None or relation.rank < existing.rank:
                            found[key] = relation

        sweep(show_ids, "show", "movie", TMDB_TV_ID, FILM, TMDB_MOVIE_ID)
        sweep(movie_ids, "movie", "show", TMDB_MOVIE_ID, TV_SERIES, TMDB_TV_ID)

        logger.info("Wikidata returned %d cross-media relation(s)", len(found))
        return sorted(found.values(), key=lambda r: (r.source_type, r.source_tmdb_id,
                                                     r.target_tmdb_id))

    def franchises_for(
        self, *, show_ids: list[int], movie_ids: list[int]
    ) -> tuple[list[FranchiseGroup], dict[tuple[str, int], set[str]]]:
        """Which franchises the library's titles belong to.

        Returns the groups and a membership map of (item_type, tmdb_id) -> franchise ids, with
        sub-groups folded into their parents: a film filed under "The Infinity Saga" is filed
        under "Marvel Cinematic Universe" here, because that is the page the user wants.

        Measured on the real library: P8345 "media franchise" gave 100 groups with two or more
        owned titles and is clean; P179 "part of the series" gave three times the statements but
        includes studio catalogues and Wikimedia list articles, so it is admitted only for group
        classes that mean "franchise" and labels that don't mean "catalogue". It has to be in:
        the MCU is 9 films under P8345 and 111 under P179.
        """
        groups: dict[str, FranchiseGroup] = {}
        membership: dict[tuple[str, int], set[str]] = {}

        for ids, id_prop, item_type in ((show_ids, TMDB_TV_ID, "show"),
                                         (movie_ids, TMDB_MOVIE_ID, "movie")):
            unique = sorted({int(i) for i in ids})
            for start in range(0, len(unique), self._batch_size):
                batch = unique[start:start + self._batch_size]
                try:
                    rows = self._run(_membership_query(batch, id_prop=id_prop))
                except WikidataError as exc:
                    logger.warning("Wikidata franchise batch failed, continuing: %s", exc)
                    continue
                for row in rows:
                    group = self._parse_group(row)
                    if group is None:
                        continue
                    groups.setdefault(group.wikidata_id, group)
                    try:
                        tmdb_id = int(row["tmdb"]["value"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    membership.setdefault((item_type, tmdb_id), set()).add(group.wikidata_id)

        # Fold sub-groups into any parent that is itself a group here.
        parents = self._parents(list(groups))
        def top(qid: str, seen: frozenset[str] = frozenset()) -> str:
            parent = parents.get(qid)
            if parent and parent in groups and parent not in seen:
                return top(parent, seen | {qid})
            return qid
        folded_to = {qid: top(qid) for qid in groups}

        # Then fold same-named groups into one. Wikidata routinely has a "media franchise" item
        # and a "film series" item with the same label and no link between them -- twenty of
        # them on the test library, Jurassic Park to Transformers. To the user they are one
        # thing. The franchise item is kept as canonical, since it is the broader of the two.
        by_name: dict[str, list[str]] = {}
        for qid in groups:
            by_name.setdefault(groups[qid].name.casefold(), []).append(qid)
        for qids in by_name.values():
            tops = sorted({folded_to[q] for q in qids})
            if len(tops) < 2:
                continue
            canonical = min(tops, key=lambda q: (groups[q].kind != "media franchise", q))
            # Every group that folded to one of the merged tops moves too -- a sub-group that
            # had already resolved to the film-series item must end at the franchise item.
            merged = set(tops) - {canonical}
            for q, target in folded_to.items():
                if target in merged:
                    folded_to[q] = canonical

        for key, ids in membership.items():
            membership[key] = {folded_to[q] for q in ids}
        kept = {q for ids in membership.values() for q in ids}
        aliases: dict[str, list[str]] = {}
        for q, target in folded_to.items():
            if q != target:
                aliases.setdefault(target, []).append(q)
        result = [
            FranchiseGroup(g.wikidata_id, g.name, g.kind, tuple(sorted(aliases.get(q, []))))
            for q, g in groups.items() if q in kept
        ]

        logger.info("Wikidata filed %d title(s) under %d franchise(s)", len(membership), len(result))
        return result, membership

    @staticmethod
    def _parse_group(row: dict) -> FranchiseGroup | None:
        qid = row.get("fr", {}).get("value", "").rsplit("/", 1)[-1]
        name = str(row.get("frLabel", {}).get("value") or "")
        if not qid or not name or _is_bare_entity_id(name):
            return None
        kind = (row.get("frClassLabel", {}).get("value") or "").strip().lower() or None
        prop = row.get("p", {}).get("value", "").rsplit("/", 1)[-1]
        if prop == "P179":
            if kind not in FRANCHISE_KINDS:
                return None
            if any(word in name.lower() for word in CATALOGUE_WORDS):
                return None
        return FranchiseGroup(wikidata_id=qid, name=name, kind=kind)

    def _parents(self, franchise_ids: list[str]) -> dict[str, str]:
        found: dict[str, str] = {}
        for start in range(0, len(franchise_ids), self._batch_size * 2):
            batch = franchise_ids[start:start + self._batch_size * 2]
            try:
                rows = self._run(_parents_query(batch))
            except WikidataError as exc:
                logger.warning("Wikidata parent lookup failed, continuing: %s", exc)
                continue
            for row in rows:
                child = row.get("child", {}).get("value", "").rsplit("/", 1)[-1]
                parent = row.get("parent", {}).get("value", "").rsplit("/", 1)[-1]
                if child and parent:
                    found.setdefault(child, parent)
        return found

    def franchise_titles(self, franchise_id: str) -> list[FranchiseTitle]:
        """Every whole film or series Wikidata files under a franchise that has a TMDb id.

        Filtered by class label: Star Wars has 3,178 members and the ones with a TMDb id are
        mostly episodes, shorts, a cancelled "film project" and LEGO specials. Whole films and
        whole series are what the user can add.
        """
        try:
            rows = self._run(_members_query(franchise_id))
        except WikidataError as exc:
            logger.warning("Wikidata members of %s unavailable: %s", franchise_id, exc)
            return []

        classes: dict[str, set[str]] = {}
        base: dict[str, tuple[str, str | None, str | None]] = {}
        for row in rows:
            qid = row.get("m", {}).get("value", "").rsplit("/", 1)[-1]
            if not qid:
                continue
            base.setdefault(qid, (
                str(row.get("mLabel", {}).get("value") or ""),
                row.get("tmdbF", {}).get("value"),
                row.get("tmdbT", {}).get("value"),
            ))
            label = (row.get("classLabel", {}).get("value") or "").lower()
            if label:
                classes.setdefault(qid, set()).add(label)

        # Keyed by TMDb id, not Wikidata item: a film and its extended edition are two items
        # on Wikidata carrying one TMDb id, and to Radarr they are one film.
        titles: dict[tuple[str, int], FranchiseTitle] = {}
        for qid, (name, film_id, tv_id) in base.items():
            if not name or _is_bare_entity_id(name):
                continue
            kinds = classes.get(qid, set())
            if any(deny in k for k in kinds for deny in MEMBER_DENY):
                continue
            if kinds and not any(allow in k for k in kinds for allow in MEMBER_ALLOW):
                continue
            if film_id and str(film_id).isdigit():
                titles.setdefault(("movie", int(film_id)),
                                  FranchiseTitle(franchise_id, "movie", int(film_id), name))
            elif tv_id and str(tv_id).isdigit():
                titles.setdefault(("show", int(tv_id)),
                                  FranchiseTitle(franchise_id, "show", int(tv_id), name))
        return list(titles.values())

    @staticmethod
    def _parse_cross(row: dict, source_type: str, target_type: str) -> CrossMediaRelation | None:
        try:
            source_id = int(row["tmdb"]["value"])
            target_id = int(row["otherTmdb"]["value"])
        except (KeyError, TypeError, ValueError):
            return None

        name = str(row.get("otherLabel", {}).get("value") or "")
        if not name or _is_bare_entity_id(name):
            return None

        relation = row.get("prop", {}).get("value", "").rsplit("/", 1)[-1] or "P144"
        # Only the language half of the remake test applies across media. A same title is the
        # *norm* for an adaptation -- Fargo the film, Fargo the series; 12 Monkeys; Limitless --
        # so the same-title rule that catches Ghosts -> Ghosts within TV would throw away the
        # best of these. A foreign-language series "based on" an owned film is still a remake.
        src_lang = row.get("srcLang", {}).get("value")
        other_lang = row.get("otherLang", {}).get("value")
        if relation == "P144" and src_lang and other_lang and src_lang != other_lang:
            return None

        entity = row.get("other", {}).get("value", "")
        return CrossMediaRelation(
            source_type=source_type, source_tmdb_id=source_id,
            target_type=target_type, target_tmdb_id=target_id,
            target_name=name, relation=relation,
            wikidata_id=entity.rsplit("/", 1)[-1] or None,
        )
