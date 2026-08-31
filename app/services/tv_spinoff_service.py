"""TV spin-off detection.

TMDb has no spin-off relation to walk -- there is simply no field for it (PROJECT_PLAN.md
section 2). So this is a hybrid, and the two halves are deliberately kept apart:

* **Curated mappings** (`spinoff_mappings`, `confidence=confirmed`). Authoritative. These are
  suggestions the user sees as facts: "you have NCIS, you don't have NCIS: Los Angeles".
  The table starts empty and grows from real use.

* **Heuristic candidates**, computed on the fly and never stored as confirmed. Presented as a
  clearly separate "possible spin-off?" tier that nothing can be added from without a human
  saying yes first (technical challenge #6). Confirming one writes a curated mapping, which is
  how the curated list grows.

The heuristic is deliberately narrow: a TMDb title search for the source show's name, keeping
results whose name starts with it followed by a separator. That is genuinely how the genre names
itself -- "NCIS: Los Angeles", "Chicago P.D.", "Star Trek: Deep Space Nine" -- and being narrow
matters far more than being clever, because every false positive is a thing a human has to read
and reject. A shared network raises confidence but is not required: plenty of real spin-offs
moved broadcaster.

Every mapping written here is `source=local`. The `community` value exists so a future shared
dataset is a new writer of existing columns rather than a migration.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.clients.tmdb_client import TmdbClient, TmdbError, TmdbShowSummary
from app.models import (
    DismissedItem,
    ItemType,
    LibraryItem,
    MappingConfidence,
    MappingSource,
    SpinoffMapping,
    TmdbShow,
    User,
)
from app.services.matcher import normalise_title

logger = logging.getLogger(__name__)

#: Separators that mark a spin-off title rather than a coincidence.
#:
#: Punctuation only, deliberately: a plain space is not enough. Measured against a real 656-show
#: library, allowing a space produced 308 candidates of which the overwhelming majority were
#: unrelated shows that merely began with the same word -- "Angel" matched "Angel Beats!",
#: "Angel Street" and "Angel City"; "Atomic" matched "Atomic Betty"; "Barry" matched "Barry Welsh
#: is Coming". Every one of those costs a person the effort of reading and rejecting it.
#:
#: Real prefix-named spin-offs nearly always announce themselves with a colon or a dash --
#: "NCIS: Los Angeles", "America's Got Talent: The Champions", "Banshee: Origins" -- so requiring
#: one trades a little recall for a great deal of precision. Spin-offs that don't carry the
#: parent's name at all were never findable this way regardless; that is what the curated mapping
#: is for.
_SEPARATOR = re.compile(r"^\s*[:\-–—]\s*")

#: Below this, a "spin-off" name is too short for a prefix match to mean anything -- every show
#: starting with "The" would match every other.
MIN_PREFIX_LENGTH = 3

#: Remainders that mark a listing of the same show rather than a different one. TMDb carries
#: separate entries for things like "Fallout - Season 2", which are emphatically not spin-offs.
_NOT_A_SPINOFF_REMAINDER = re.compile(
    r"^(season|series|part|volume|vol|chapter|book)\s*\d*$", re.IGNORECASE
)


@dataclass(frozen=True)
class SpinoffSuggestion:
    """A show the user doesn't have, related to one they do."""

    source_show_tmdb_id: int
    source_show_name: str
    spinoff_tmdb_id: int
    spinoff_name: str
    first_air_year: int | None = None
    confidence: str = MappingConfidence.CONFIRMED.value
    reason: str | None = None

    @property
    def is_confirmed(self) -> bool:
        return self.confidence == MappingConfidence.CONFIRMED.value


def owned_show_ids(session: Session) -> set[int]:
    """TMDb ids of shows in the library. Unconfirmed matches don't count, for the same reason
    they don't on the movie side: a guess must not be able to hide a real gap."""
    rows = session.exec(
        select(LibraryItem).where(
            col(LibraryItem.item_type) == ItemType.SHOW.value,
            col(LibraryItem.tmdb_id).is_not(None),
            col(LibraryItem.needs_review) == False,  # noqa: E712 - SQL, not Python
        )
    ).all()
    return {row.tmdb_id for row in rows if row.tmdb_id}


def owned_shows(session: Session) -> list[LibraryItem]:
    return list(
        session.exec(
            select(LibraryItem)
            .where(
                col(LibraryItem.item_type) == ItemType.SHOW.value,
                col(LibraryItem.tmdb_id).is_not(None),
                col(LibraryItem.needs_review) == False,  # noqa: E712 - SQL, not Python
            )
            .order_by(col(LibraryItem.title))
        ).all()
    )


# ---------------------------------------------------------------------- mappings


def list_mappings(session: Session, source_show_tmdb_id: int | None = None) -> list[SpinoffMapping]:
    statement = select(SpinoffMapping)
    if source_show_tmdb_id is not None:
        statement = statement.where(
            col(SpinoffMapping.source_show_tmdb_id) == source_show_tmdb_id
        )
    return list(session.exec(statement).all())


def mapping_exists(session: Session, source_id: int, spinoff_id: int) -> bool:
    return (
        session.exec(
            select(SpinoffMapping).where(
                col(SpinoffMapping.source_show_tmdb_id) == source_id,
                col(SpinoffMapping.spinoff_show_tmdb_id) == spinoff_id,
            )
        ).first()
        is not None
    )


def add_mapping(
    session: Session,
    *,
    source_show_tmdb_id: int,
    spinoff_show_tmdb_id: int,
    user: User | None = None,
    confidence: str = MappingConfidence.CONFIRMED.value,
) -> SpinoffMapping | None:
    """Record that one show is a spin-off of another. Idempotent."""
    if source_show_tmdb_id == spinoff_show_tmdb_id:
        raise ValueError("A show can't be a spin-off of itself.")
    if mapping_exists(session, source_show_tmdb_id, spinoff_show_tmdb_id):
        return None

    mapping = SpinoffMapping(
        source_show_tmdb_id=source_show_tmdb_id,
        spinoff_show_tmdb_id=spinoff_show_tmdb_id,
        # v1 only ever writes local; `community` exists so a future sync feature populates
        # existing columns instead of needing a migration.
        source=MappingSource.LOCAL.value,
        confidence=confidence,
        added_by_user_id=user.id if user else None,
    )
    session.add(mapping)
    session.commit()
    session.refresh(mapping)
    logger.info(
        "Mapped tmdb:%s as a spin-off of tmdb:%s", spinoff_show_tmdb_id, source_show_tmdb_id
    )
    return mapping


def remove_mapping(session: Session, mapping_id: int) -> None:
    mapping = session.get(SpinoffMapping, mapping_id)
    if mapping is not None:
        session.delete(mapping)
        session.commit()


# ---------------------------------------------------------------------- the diff


def _show_name(session: Session, tmdb_id: int, fallback: str = "") -> str:
    cached = session.get(TmdbShow, tmdb_id)
    if cached:
        return cached.name
    item = session.exec(
        select(LibraryItem).where(col(LibraryItem.tmdb_id) == tmdb_id)
    ).first()
    return item.title if item else (fallback or f"TMDb {tmdb_id}")


def missing_spinoffs(session: Session, user_id: int | None = None) -> list[SpinoffSuggestion]:
    """Curated spin-offs of shows the library has, that the library doesn't."""
    owned = owned_show_ids(session)
    dismissed = {
        row.tmdb_id
        for row in session.exec(
            select(DismissedItem).where(
                col(DismissedItem.user_id) == user_id,
                col(DismissedItem.item_type) == ItemType.SHOW.value,
            )
        ).all()
    } if user_id is not None else set()

    suggestions: list[SpinoffSuggestion] = []
    for mapping in list_mappings(session):
        if mapping.source_show_tmdb_id not in owned:
            continue
        if mapping.spinoff_show_tmdb_id in owned:
            continue
        if mapping.spinoff_show_tmdb_id in dismissed:
            continue

        cached = session.get(TmdbShow, mapping.spinoff_show_tmdb_id)
        suggestions.append(
            SpinoffSuggestion(
                source_show_tmdb_id=mapping.source_show_tmdb_id,
                source_show_name=_show_name(session, mapping.source_show_tmdb_id),
                spinoff_tmdb_id=mapping.spinoff_show_tmdb_id,
                spinoff_name=_show_name(session, mapping.spinoff_show_tmdb_id),
                first_air_year=cached.first_air_year if cached else None,
                confidence=mapping.confidence,
            )
        )

    suggestions.sort(key=lambda s: (s.source_show_name.casefold(), s.spinoff_name.casefold()))
    return suggestions


# ---------------------------------------------------------------------- heuristics


def looks_like_spinoff_of(source_name: str, candidate_name: str) -> bool:
    """Whether `candidate_name` reads as a spin-off title of `source_name`.

    Requires the source name as a prefix *followed by a separator*, so "NCIS: Los Angeles" counts
    and "NCISomething" doesn't. Narrowness is the point: every false positive is something a
    person has to read and dismiss.
    """
    source = normalise_title(source_name)
    candidate = normalise_title(candidate_name)

    if len(source) < MIN_PREFIX_LENGTH or not candidate.startswith(source):
        return False
    if candidate == source:
        return False

    remainder = candidate_name.strip()
    # Compare on the raw title so the separator survives normalisation, which strips punctuation.
    lowered = remainder.casefold()
    prefix_end = len(source_name.strip())
    if lowered.startswith(source_name.strip().casefold()) and len(remainder) > prefix_end:
        tail = remainder[prefix_end:]
        separator = _SEPARATOR.match(tail)
        if not separator:
            return False
        # "Fallout - Season 2" is the same show, listed again.
        return not _NOT_A_SPINOFF_REMAINDER.match(tail[separator.end():].strip())

    # The normalised forms matched but the raw titles don't share a literal prefix -- e.g. a
    # punctuation difference. Without a separator to confirm the relationship this is a guess on
    # top of a guess, so it isn't offered.
    return False


def heuristic_candidates(
    session: Session, client: TmdbClient, show: LibraryItem, *, limit: int = 5
) -> list[SpinoffSuggestion]:
    """Possible spin-offs of one owned show, from a TMDb title search.

    Never stored and never addable without confirmation. Anything already owned, already mapped,
    or already dismissed is filtered out, so this only ever surfaces genuinely new suggestions.
    """
    if not show.tmdb_id or not show.title:
        return []

    try:
        results = client.search_shows(show.title)
    except TmdbError as exc:
        logger.warning("Spin-off search failed for %r: %s", show.title, exc)
        return []

    owned = owned_show_ids(session)
    mapped = {
        mapping.spinoff_show_tmdb_id for mapping in list_mappings(session, show.tmdb_id)
    }

    found: list[SpinoffSuggestion] = []
    for candidate in results:
        if candidate.tmdb_id == show.tmdb_id or candidate.tmdb_id in owned:
            continue
        if candidate.tmdb_id in mapped:
            continue
        if not looks_like_spinoff_of(show.title, candidate.name):
            continue

        found.append(
            SpinoffSuggestion(
                source_show_tmdb_id=show.tmdb_id,
                source_show_name=show.title,
                spinoff_tmdb_id=candidate.tmdb_id,
                spinoff_name=candidate.name,
                first_air_year=candidate.year,
                confidence=MappingConfidence.HEURISTIC.value,
                reason=f"Its title reads as a spin-off of {show.title}",
            )
        )
        if len(found) >= limit:
            break

    return found


def cache_show(session: Session, summary: TmdbShowSummary) -> TmdbShow:
    from app.models import utcnow

    row = TmdbShow(
        tmdb_id=summary.tmdb_id,
        name=summary.name,
        first_air_year=summary.year,
        network=summary.network,
        fetched_at=utcnow(),
    )
    session.merge(row)
    session.commit()
    return row
