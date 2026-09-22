"""Paging for the card grids.

A 3,400-film library produces 108 collections with gaps and fits on one page comfortably. A
20,000-film one produces about 1,100, and the page became a megabyte of HTML -- slow to parse,
heavy on a phone, and pointless, since nobody scrolls eleven hundred cards
(`scripts/loadtest.py` measured it).

So: below `DEFAULT_SIZE` items nothing changes at all -- no pager is rendered and the page is
exactly what it was. Above it the list is cut into pages. This caps the *HTML*, not the work
behind it: the read-time services still assemble the whole list before it is sliced, because
the totals in the heading ("1,103 collections, 2,208 films missing") describe everything, not
the page you are looking at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from urllib.parse import urlencode

#: Items per page. Chosen so a real library still sees no pager: measured on the developer's
#: library after this shipped, its lists are 109 collections with gaps, 148 directors and 147
#: upcoming films -- 120 would have paged the last two, which is the sort of thing that only
#: shows up once it is deployed. A page is roughly 0.9 KB a card, so this caps one at ~225 KB
#: against the megabyte a 20,000-film library produced unpaged.
DEFAULT_SIZE = 250


@dataclass(frozen=True)
class Pager:
    """One page of a list, and the links to its neighbours."""

    items: list
    page: int
    size: int
    total: int
    path: str
    params: dict = field(default_factory=dict)
    #: Appended to every link, so a pager inside a <details> returns you to it.
    anchor: str = ""
    #: The query parameter this pager moves. Two pagers on one page (Spin-offs has the
    #: suggestion grid and the owned-show list) must not write the same one, or paging either
    #: resets the other.
    page_param: str = "page"

    @property
    def pages(self) -> int:
        return max(1, ceil(self.total / self.size))

    @property
    def needed(self) -> bool:
        """False when everything fits on one page -- then the template renders no pager."""
        return self.total > self.size

    @property
    def first_index(self) -> int:
        return (self.page - 1) * self.size + 1

    @property
    def last_index(self) -> int:
        return min(self.total, self.page * self.size)

    def _link(self, page: int) -> str:
        query = {k: v for k, v in self.params.items() if v not in (None, "", False)}
        query[self.page_param] = page
        return f"{self.path}?{urlencode(query)}{self.anchor}"

    @property
    def previous(self) -> str | None:
        return self._link(self.page - 1) if self.page > 1 else None

    @property
    def next(self) -> str | None:
        return self._link(self.page + 1) if self.page < self.pages else None


def paginate(
    items: list, page: int, *, path: str, params: dict | None = None,
    size: int = DEFAULT_SIZE, anchor: str = "", page_param: str = "page",
) -> Pager:
    """Cut `items` into pages. A page number past the end lands on the last page rather than
    showing an empty list, which is what a stale bookmark or a shrinking library produces."""
    total = len(items)
    pages = max(1, ceil(total / size))
    page = max(1, min(page, pages))
    start = (page - 1) * size
    return Pager(items=items[start:start + size], page=page, size=size, total=total,
                 path=path, params=params or {}, anchor=anchor, page_param=page_param)
