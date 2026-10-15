"""Duplicates (0.73.0, michael's pick): films in the library more than once, as a cleanup list.
Two ways a film turns up twice: a server groups several versions under one item (Plex's Media
elements -- `LibraryItem.copies`), or the same film sits under two items on one server (two
libraries, or Jellyfin/Emby showing separate files separately). Per server: the same film on
two different servers is the point of having two, not a duplicate (Server parity covers those).
Switched-off servers are left out, as everywhere that reads ownership."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlmodel import Session, col, select

from app.models import IncludedLibrary, ItemType, LibraryItem, MediaServer
from app.services.ownership_service import on_enabled_server


@dataclass
class Duplicate:
    tmdb_id: int | None
    title: str
    year: int | None
    server: str
    #: One line per copy's place: "Movies", "Movies (2 versions)", "4K Movies".
    places: list[str] = field(default_factory=list)
    copies: int = 0


def find(session: Session) -> list[Duplicate]:
    names = {sid: name for sid, name in session.exec(select(MediaServer.id, MediaServer.name))}
    libraries = {(sid, key): name for sid, key, name in session.exec(
        select(IncludedLibrary.server_id, IncludedLibrary.library_key, IncludedLibrary.library_name))}
    groups: dict[tuple, list] = defaultdict(list)
    for sid, key, tmdb_id, title, year, copies in session.exec(
            select(LibraryItem.server_id, LibraryItem.library_key, LibraryItem.tmdb_id, LibraryItem.title,
                   LibraryItem.year, LibraryItem.copies)
            .where(on_enabled_server(), col(LibraryItem.item_type) == ItemType.MOVIE.value,
                   col(LibraryItem.tmdb_id).is_not(None), col(LibraryItem.needs_review) == False)):  # noqa: E712
        groups[(sid, tmdb_id)].append((key, title, year, copies or 1))
    found = []
    for (sid, tmdb_id), rows in groups.items():
        total = sum(r[3] for r in rows)
        if total < 2:
            continue
        places = [libraries.get((sid, key), f"library {key}") + (f" ({copies} versions)" if copies > 1 else "")
                  for key, _, _, copies in sorted(rows)]
        title, year = rows[0][1], rows[0][2]
        found.append(Duplicate(tmdb_id, title, year, names.get(sid, "?"), places, total))
    found.sort(key=lambda d: (d.server.casefold(), d.title.casefold()))
    return found
