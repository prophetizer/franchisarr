"""Titles marked Not interested, and titles marked not part of a collection, as folds with Undo
(0.77.0, michael). Both used to vanish from the page with no way back, though the README promised
that everything hidden is folded, never deleted (GLOSSARY.md: not interested, folded).

Not interested is one person's (DismissedItem); "not part of this collection" is the household's
correction to TMDb's data, scoped to one collection (CollectionExclude), so only an administrator
can undo it.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, col, delete, select

from app.models import CollectionExclude, DismissedItem, ItemType


@dataclass(frozen=True)
class Marked:
    """A title in a Not interested (or not-part-of-this-collection) fold."""

    item_type: str
    tmdb_id: int
    title: str
    year: int | None = None
    poster_path: str | None = None
    #: Wanted titles only: Radarr holds it but isn't fetching it.
    unmonitored: bool = False

    @property
    def poster(self) -> str | None:
        from app.services.artwork import CARD_SIZE, poster_url

        return poster_url(self.poster_path, CARD_SIZE)

    @property
    def is_show(self) -> bool:
        return self.item_type == ItemType.SHOW.value


def undo(session: Session, user_id: int, item_type: str, tmdb_id: int) -> bool:
    """Take a title off this person's Not interested list. True if it was on it."""
    result = session.exec(delete(DismissedItem).where(
        col(DismissedItem.user_id) == user_id, col(DismissedItem.item_type) == item_type,
        col(DismissedItem.tmdb_id) == tmdb_id))
    session.commit()
    return bool(result.rowcount)


def undo_exclude(session: Session, collection_id: int, tmdb_id: int) -> bool:
    """Put a film back in a collection the household had said it wasn't part of."""
    result = session.exec(delete(CollectionExclude).where(
        col(CollectionExclude.tmdb_collection_id) == collection_id,
        col(CollectionExclude.tmdb_movie_id) == tmdb_id))
    session.commit()
    return bool(result.rowcount)


def shows(session: Session, user_id: int | None) -> list[Marked]:
    """The shows this person marked Not interested, for the Spin-offs page's fold."""
    from app.models import TmdbShow

    if user_id is None:
        return []
    ids = session.exec(select(DismissedItem.tmdb_id).where(
        col(DismissedItem.user_id) == user_id, col(DismissedItem.item_type) == ItemType.SHOW.value)).all()
    if not ids:
        return []
    known = {tid: (name, year, poster) for tid, name, year, poster in session.exec(
        select(TmdbShow.tmdb_id, TmdbShow.name, TmdbShow.first_air_year, TmdbShow.poster_path)
        .where(col(TmdbShow.tmdb_id).in_(ids))).all()}
    out = [Marked(ItemType.SHOW.value, tid, *(known.get(tid) or (f"TMDb show {tid}", None, None))) for tid in ids]
    return sorted(out, key=lambda m: m.title.casefold())
