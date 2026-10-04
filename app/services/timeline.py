"""A set in release order, for the poster strip at the top of a franchise or collection page
(0.45.0, michael's pick): what's owned in colour, what's missing and what's coming dimmed, so
the holes in the run show at a glance. The grids below keep the detail and the actions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    title: str
    year: int | None
    poster: str | None
    #: "owned", "missing" or "upcoming".
    status: str
    tmdb_id: int
    #: "movie" or "show" -- which add dialog a missing one opens.
    item_type: str


def _year(item) -> int | None:  # noqa: ANN001
    return getattr(item, "year", None) or getattr(item, "release_year", None)


def _when(item) -> str:  # noqa: ANN001
    """Sortable: the release date if there is one, else the year; undated last."""
    date = getattr(item, "release_date", None)
    if date:
        return str(date)
    year = _year(item)
    return f"{year}-99" if year else "9999"


def build(owned=(), missing=(), upcoming=()) -> list[Step]:  # noqa: ANN001
    """Every title of the set in release order. Items are the pages' own (franchise Titles or
    collection MissingMovies): each has a title, a TMDb id, a poster and a date or year."""
    tagged = [(item, status) for status, items in (("owned", owned), ("missing", missing), ("upcoming", upcoming))
              for item in items]
    tagged.sort(key=lambda pair: (_when(pair[0]), pair[0].title.casefold()))
    return [Step(item.title, _year(item), item.poster, status, item.tmdb_id,
                 getattr(item, "item_type", "movie") or "movie") for item, status in tagged]


def decade_marks(steps: list[Step]) -> dict[int, str]:
    """Where each decade starts along the strip (0.71.0): {index: "1990s"}. Empty for a strip
    within one decade, where a mark would only repeat the years under the posters."""
    marks: dict[int, str] = {}
    last = None
    for n, step in enumerate(steps):
        decade = f"{step.year // 10 * 10}s" if step.year else None
        if decade and decade != last:
            marks[n] = decade
        last = decade or last
    return marks if len(marks) > 1 else {}
