"""The A-Z jump rail on long lists (0.72.0, michael's pick): Collections, Franchises and
Directors. A letter jumps to the first name starting with it -- on whichever page that is, in
name order, so a list sorted some other way switches to A-Z on the way."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

LETTERS = "#ABCDEFGHIJKLMNOPQRSTUVWXYZ"
#: Shorter lists fit on a screen or two; a rail there is clutter.
AT_LEAST = 30


@dataclass(frozen=True)
class Letter:
    letter: str
    #: Where it jumps; None when no name starts with it.
    href: str | None

    @property
    def anchor(self) -> str:
        return anchor_for(self.letter)


def letter_of(name: str) -> str:
    """The rail letter a name files under: its first letter, or "#" for a digit or anything else."""
    for ch in name.casefold():
        if ch.isalnum():
            upper = ch.upper()
            return upper if "A" <= upper <= "Z" else "#"
    return "#"


def anchor_for(letter: str) -> str:
    return "az-num" if letter == "#" else f"az-{letter}"


def rail(by_name: list, *, path: str, size: int, params: dict | None = None) -> list[Letter]:
    """One entry per letter for a list in name order (each item has a `name`). Empty for a short
    list. `params` are carried into the links (a filter), sort and page set here."""
    if len(by_name) < AT_LEAST:
        return []
    first: dict[str, int] = {}
    for n, item in enumerate(by_name):
        first.setdefault(letter_of(item.name), n)
    extra = {k: v for k, v in (params or {}).items() if v is not None and k not in ("sort", "dir", "page")}
    letters = []
    for letter in LETTERS:
        n = first.get(letter)
        if n is None:
            letters.append(Letter(letter, None))
            continue
        query = urlencode({"sort": "name", "dir": "asc", "page": n // size + 1, **extra})
        letters.append(Letter(letter, f"{path}?{query}#{anchor_for(letter)}"))
    return letters


def anchors(page_items: list, current: tuple[str, str]) -> dict[int, str]:
    """The card ids the rail's links land on: the first card of each letter on this page, when
    the list is in A-Z order -- otherwise none, as no link points at a list in another order."""
    if tuple(current) != ("name", "asc"):
        return {}
    seen: dict[str, int] = {}
    for n, item in enumerate(page_items):
        seen.setdefault(letter_of(item.name), n)
    return {n: anchor_for(letter) for letter, n in seen.items()}
