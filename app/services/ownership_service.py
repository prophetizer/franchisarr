"""What "owned" looks like when there are several servers.

A film is owned once however many servers hold it: the gap views work on sets of TMDb ids and
never counted copies. What the servers add is *where* it is and whether it has been *watched*,
which is what this module answers -- one query per page, keyed by TMDb id.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.models import ItemType, LibraryItem, MediaServer


@dataclass(frozen=True)
class Owned:
    #: Names of the servers holding it, in name order.
    servers: tuple[str, ...] = ()
    #: Watched on any server; None when no server said either way.
    watched: bool | None = None

    @property
    def where(self) -> str:
        return ", ".join(self.servers)


def owned_details(session: Session, item_type: str = ItemType.MOVIE.value) -> dict[int, Owned]:
    """Server names and watched state for every matched item of that type, by TMDb id."""
    rows = session.exec(
        select(LibraryItem.tmdb_id, LibraryItem.watched, MediaServer.name)
        .join(MediaServer, col(MediaServer.id) == col(LibraryItem.server_id))
        .where(
            col(LibraryItem.item_type) == item_type,
            col(LibraryItem.tmdb_id).is_not(None),
            col(LibraryItem.needs_review) == False,  # noqa: E712 - SQL, not Python
        )
    ).all()
    servers: dict[int, set[str]] = {}
    watched: dict[int, bool | None] = {}
    for tmdb_id, seen, name in rows:
        servers.setdefault(tmdb_id, set()).add(name)
        # True on any server wins; a False beats an unknown; unknown only when nobody said.
        current = watched.get(tmdb_id)
        if seen is True or current is True:
            watched[tmdb_id] = True
        elif seen is False or current is False:
            watched[tmdb_id] = False
        else:
            watched[tmdb_id] = None
    return {
        tmdb_id: Owned(servers=tuple(sorted(names)), watched=watched[tmdb_id])
        for tmdb_id, names in servers.items()
    }
