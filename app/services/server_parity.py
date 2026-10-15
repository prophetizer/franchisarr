"""Server parity (0.73.0, michael's pick): for an install with several media servers, the films
one has and another doesn't, pair by pair, so the copies can be kept in step. Deliberately reads
every server that has been scanned -- a paused one too, labelled with when it was last seen --
since comparing servers is the whole point here; nothing on this page decides what's "owned"."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from itertools import permutations

from sqlmodel import Session, col, func, select

from app.models import ItemType, LibraryItem, MediaServer


@dataclass
class Side:
    id: int
    name: str
    kind: str
    enabled: bool
    films: int
    last_seen: datetime | None


@dataclass
class Gap:
    """Films `have` holds that `lacks` doesn't."""
    have: Side
    lacks: Side
    films: list[tuple[int, str, int | None]] = field(default_factory=list)


def compare(session: Session) -> tuple[list[Side], list[Gap]]:
    sides = []
    for sid, name, kind, enabled in session.exec(select(MediaServer.id, MediaServer.name, MediaServer.kind,
                                                        MediaServer.enabled)):
        count, last = session.exec(select(func.count(func.distinct(LibraryItem.tmdb_id)), func.max(LibraryItem.last_seen_at))
                                   .where(col(LibraryItem.server_id) == sid,
                                          col(LibraryItem.item_type) == ItemType.MOVIE.value,
                                          col(LibraryItem.tmdb_id).is_not(None))).one()
        if count:
            sides.append(Side(sid, name, kind or "plex", bool(enabled), count, last))
    if len(sides) < 2:
        return sides, []
    films: dict[int, dict[int, tuple[str, int | None]]] = defaultdict(dict)
    for sid, tmdb_id, title, year in session.exec(
            select(LibraryItem.server_id, LibraryItem.tmdb_id, LibraryItem.title, LibraryItem.year)
            .where(col(LibraryItem.item_type) == ItemType.MOVIE.value, col(LibraryItem.tmdb_id).is_not(None),
                   col(LibraryItem.needs_review) == False)):  # noqa: E712
        films[sid].setdefault(tmdb_id, (title, year))
    gaps = []
    for have, lacks in permutations(sides, 2):
        missing = [(tid, *films[have.id][tid]) for tid in films[have.id].keys() - films[lacks.id].keys()]
        missing.sort(key=lambda f: (f[1].casefold(), f[2] or 0))
        gaps.append(Gap(have, lacks, missing))
    return sides, gaps
