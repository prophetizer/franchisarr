"""Story order for a collection or franchise (0.74.0, michael's pick): what a "Chronological"
playlist follows. The household's own order for the set if it has one (Story order on the set's
page, `SetOrder` rows), else a built-in one (chronology_data.ORDERS) when it places two or more of
the set's titles, else none -- and then only the release-order playlist is offered.

Titles an order doesn't place -- a film added since, a show the order leaves out -- go after the
ones it does, in release order, rather than being dropped from a playlist.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, col, delete, select

from app.models import SetOrder, utcnow
from app.services.chronology_data import ORDERS

KINDS = ("collections", "franchises")
Key = tuple[str, int]


@dataclass(frozen=True)
class Story:
    #: The set's titles in story order: the placed ones, then the rest in release order.
    order: list[Key]
    #: "yours" for the household's own order, else the built-in order's name ("Star Wars").
    source: str
    #: Titles the order didn't place, now at the end.
    unplaced: int


def _builtin(titles: set[Key]) -> tuple[str, list[Key]] | None:
    """The built-in order placing most of these titles, if it places two or more."""
    best = None
    for name, entries in ORDERS.items():
        placed = [(kind, tid) for kind, tid, _ in entries if (kind, tid) in titles]
        if len(placed) >= 2 and (best is None or len(placed) > len(best[1])):
            best = (name, placed)
    return best


def custom(session: Session, kind: str, ref: str) -> list[Key]:
    return [(t, i) for t, i in session.exec(
        select(SetOrder.item_type, SetOrder.tmdb_id)
        .where(col(SetOrder.kind) == kind, col(SetOrder.ref) == str(ref))
        .order_by(col(SetOrder.position))).all()]


def story(session: Session, kind: str, ref: str, titles: list[Key]) -> Story | None:
    """The set's titles (given in release order) in story order, or None when there is none."""
    mine = custom(session, kind, ref)
    present = set(titles)
    if mine:
        placed, source = [k for k in mine if k in present], "yours"
    else:
        found = _builtin(present)
        if found is None:
            return None
        source, placed = found
    seen = set(placed)
    rest = [k for k in titles if k not in seen]
    return Story(placed + rest, source, len(rest))


def save(session: Session, kind: str, ref: str, ordered: list[Key]) -> None:
    """The household's own order for the set, replacing any before it (bulk delete, flush, then
    insert: CLAUDE.md's delete-then-insert gotcha)."""
    session.exec(delete(SetOrder).where(col(SetOrder.kind) == kind, col(SetOrder.ref) == str(ref)))
    session.flush()
    now = utcnow()
    seen: set[Key] = set()
    for position, key in enumerate(ordered):
        if key in seen:
            continue
        seen.add(key)
        session.add(SetOrder(kind=kind, ref=str(ref), item_type=key[0], tmdb_id=key[1], position=position,
                             updated_at=now))
    session.commit()


def reset(session: Session, kind: str, ref: str) -> None:
    session.exec(delete(SetOrder).where(col(SetOrder.kind) == kind, col(SetOrder.ref) == str(ref)))
    session.commit()


def set_titles(session: Session, user_id: int | None, kind: str, ref: str):  # noqa: ANN201
    """(name, release-order Steps) for a collection or franchise -- every title, owned or not, as
    its release strip shows them -- or None for no such set."""
    from app.services import timeline

    if kind == "collections":
        from app.services import movie_gap_service

        try:
            cid = int(ref)
        except ValueError:
            return None
        gap = next(iter(movie_gap_service.collection_gaps(session, user_id, only={cid})), None)
        if gap is None:
            return None
        return gap.name, timeline.build(gap.owned, gap.missing, gap.upcoming)
    if kind == "franchises":
        from app.services import franchise_service

        view = franchise_service.franchise_view(session, ref, user_id)
        if view is None:
            return None
        return view.name, timeline.build(view.owned_films + view.owned_shows,
                                         view.missing_films + view.missing_shows, view.upcoming_films)
    return None
