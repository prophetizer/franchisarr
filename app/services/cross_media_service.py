"""Continuations across media: films related to shows the user owns, and shows related to films.

The two halves of this app each know one medium. This is what falls between them: the series a
film was drawn from or continued (Firefly, for someone who owns Serenity), the film that closed
a show, the original series behind a remake. Each suggestion routes to the *other* arr from the
thing the user owns.

Measured on the real library before being built, and shaped by what came back: film-to-show is
the productive direction (53 series), show-to-film is small (14 films, three of them pornographic
parodies until the query learned to exclude the genre). Both are kept -- the small direction is
occasionally exactly right -- but neither is inflated into more than it is.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace

from sqlmodel import Session, col, select

from app.clients.tmdb_client import TmdbClient, TmdbError
from app.clients.wikidata_client import CrossMediaRelation, relation_label
from app.models import (
    CrossMediaMapping, DismissedItem, ItemType, MappingConfidence, MappingSource,
)
from app.services import movie_gap_service, tv_spinoff_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CrossMediaSuggestion:
    """Something in the other medium, related to something the user owns."""

    target_type: str
    target_tmdb_id: int
    target_title: str
    target_year: int | None
    target_poster_path: str | None
    relation: str
    confidence: str
    source_type: str
    source_tmdb_id: int
    source_title: str
    also: tuple[tuple[str, str], ...] = ()

    @property
    def poster(self) -> str | None:
        from app.services.artwork import THUMB_SIZE, poster_url

        return poster_url(self.target_poster_path, THUMB_SIZE)

    @property
    def relationship(self) -> str:
        return relation_label(self.relation) or "related to"

    @property
    def relationships(self) -> str:
        by_phrase: dict[str, list[str]] = {}
        for phrase, name in ((self.relationship, self.source_title), *self.also):
            by_phrase.setdefault(phrase, []).append(name)
        parts = []
        for phrase, names in by_phrase.items():
            joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            parts.append(f"{phrase} {joined}")
        return "; ".join(parts)

    @property
    def tmdb_url(self) -> str:
        kind = "movie" if self.target_type == ItemType.MOVIE.value else "tv"
        return f"https://www.themoviedb.org/{kind}/{self.target_tmdb_id}"


def import_relations(
    session: Session, relations: Iterable[CrossMediaRelation], tmdb: TmdbClient | None
) -> tuple[int, int]:
    """Record discovered relations. Returns (added, refreshed).

    Display details for a new target are fetched from TMDb once, here, and kept on the row: a
    film that is in no owned collection has nowhere else to borrow a title and poster from.
    """
    added = refreshed = 0
    for relation in relations:
        confidence = (
            MappingConfidence.CONFIRMED.value if relation.is_precise
            else MappingConfidence.HEURISTIC.value
        )
        existing = session.exec(
            select(CrossMediaMapping).where(
                col(CrossMediaMapping.source_type) == relation.source_type,
                col(CrossMediaMapping.source_tmdb_id) == relation.source_tmdb_id,
                col(CrossMediaMapping.target_type) == relation.target_type,
                col(CrossMediaMapping.target_tmdb_id) == relation.target_tmdb_id,
            )
        ).first()

        if existing is not None:
            if (existing.confidence, existing.relation) != (confidence, relation.relation):
                existing.confidence, existing.relation = confidence, relation.relation
                session.add(existing)
                refreshed += 1
            continue

        title, year, poster = relation.target_name, None, None
        if tmdb is not None:
            try:
                if relation.target_type == ItemType.MOVIE.value:
                    details = tmdb.get_movie(relation.target_tmdb_id)
                    title, year = details.title or title, details.year
                    poster = getattr(details, "poster_path", None)
                else:
                    show = tmdb.get_show(relation.target_tmdb_id)
                    title, year, poster = show.name or title, show.year, show.poster_path
            except TmdbError as exc:
                logger.debug("No TMDb details for %s %s: %s",
                             relation.target_type, relation.target_tmdb_id, exc)

        session.add(
            CrossMediaMapping(
                source_type=relation.source_type,
                source_tmdb_id=relation.source_tmdb_id,
                target_type=relation.target_type,
                target_tmdb_id=relation.target_tmdb_id,
                target_title=title,
                target_year=year,
                target_poster_path=poster,
                relation=relation.relation,
                source=MappingSource.WIKIDATA.value,
                confidence=confidence,
            )
        )
        added += 1

    session.commit()
    if added or refreshed:
        logger.info("Cross-media: %d added, %d refreshed", added, refreshed)
    return added, refreshed


def _source_title(session: Session, source_type: str, tmdb_id: int) -> str:
    if source_type == ItemType.SHOW.value:
        return tv_spinoff_service._show_name(session, tmdb_id)
    for gap in movie_gap_service.collection_gaps(session):
        for movie in gap.owned:
            if movie.tmdb_id == tmdb_id:
                return movie.title
    from app.models import TmdbMovie

    cached = session.get(TmdbMovie, tmdb_id)
    return cached.title if cached else f"TMDb {tmdb_id}"


def suggestions(
    session: Session, target_type: str, user_id: int | None = None
) -> list[CrossMediaSuggestion]:
    """Everything in `target_type` related to something the user owns, that they don't have.

    Owned, already-in-the-arr and dismissed targets are removed, using the same rules the two
    single-medium lists use -- a show already in Sonarr is not a gap whichever way it was found.
    """
    if target_type == ItemType.MOVIE.value:
        have = movie_gap_service.owned_tmdb_ids(session) | movie_gap_service.radarr_known_ids(session)
        owned_sources = tv_spinoff_service.owned_show_ids(session)
        source_type = ItemType.SHOW.value
    else:
        have = tv_spinoff_service.owned_show_ids(session) | tv_spinoff_service.sonarr_known_ids(session)
        owned_sources = movie_gap_service.owned_tmdb_ids(session)
        source_type = ItemType.MOVIE.value

    dismissed = {
        row.tmdb_id for row in session.exec(
            select(DismissedItem).where(
                col(DismissedItem.user_id) == user_id,
                col(DismissedItem.item_type) == target_type,
            )
        ).all()
    } if user_id is not None else set()

    rows = session.exec(
        select(CrossMediaMapping).where(
            col(CrossMediaMapping.source_type) == source_type,
            col(CrossMediaMapping.target_type) == target_type,
        )
    ).all()

    grouped: dict[int, CrossMediaSuggestion] = {}
    for row in sorted(rows, key=lambda r: (r.confidence != MappingConfidence.CONFIRMED.value,
                                            r.target_title.casefold())):
        if row.source_tmdb_id not in owned_sources:
            continue
        if row.target_tmdb_id in have or row.target_tmdb_id in dismissed:
            continue
        entry = CrossMediaSuggestion(
            target_type=row.target_type, target_tmdb_id=row.target_tmdb_id,
            target_title=row.target_title, target_year=row.target_year,
            target_poster_path=row.target_poster_path, relation=row.relation,
            confidence=row.confidence, source_type=row.source_type,
            source_tmdb_id=row.source_tmdb_id,
            source_title=_source_title(session, row.source_type, row.source_tmdb_id),
        )
        first = grouped.get(row.target_tmdb_id)
        if first is None:
            grouped[row.target_tmdb_id] = entry
        else:
            grouped[row.target_tmdb_id] = replace(
                first, also=(*first.also, (entry.relationship, entry.source_title)))

    return sorted(grouped.values(), key=lambda s: s.target_title.casefold())
