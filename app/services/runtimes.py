"""How long a set runs (0.72.0, michael's pick): the running time of the films you own in it and
how much of that you haven't watched, from what the media server reports at scan time. TMDb's
collection data has no runtimes, and asking for them is a request per film, so a missing film
counts for nothing here and the line only speaks for what's owned."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class SetRuntime:
    films: int
    #: Minutes across the owned films whose runtime is known.
    total: int
    #: Minutes of those not yet watched; None when no server reports watched state.
    left: int | None
    #: Some owned films have no runtime yet (the scan before 0.72.0 didn't keep it).
    partial: bool


def summary(owned: Iterable) -> SetRuntime | None:  # noqa: ANN001 - owned titles of any page
    films = [t for t in owned if (getattr(t, "item_type", None) or "movie") == "movie"]
    timed = [t for t in films if getattr(t, "runtime", None)]
    if not timed:
        return None
    known = any(getattr(t, "watched", None) is not None for t in films)
    return SetRuntime(
        films=len(films),
        total=sum(t.runtime for t in timed),
        left=sum(t.runtime for t in timed if not t.watched) if known else None,
        partial=len(timed) < len(films),
    )


def watched_of(owned: Iterable) -> int | None:  # noqa: ANN001
    """How many owned titles have been watched; None when no server says either way (the cards'
    watched bar, 0.72.0)."""
    titles = list(owned)
    if not any(getattr(t, "watched", None) is not None for t in titles):
        return None
    return sum(1 for t in titles if t.watched)


def hours(minutes: int | None) -> str:
    """142 -> "2h 22m"; 50 -> "50m"; 120 -> "2h"."""
    if not minutes:
        return "0m"
    h, m = divmod(int(minutes), 60)
    if not h:
        return f"{m}m"
    return f"{h}h {m}m" if m else f"{h}h"
