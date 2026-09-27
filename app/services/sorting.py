"""How each list page can be sorted, and remembering each person's last choice per page.

Every page shows the same control (partials/sort_control.html): a dropdown of what to sort by,
and a button that flips the direction and says which way the list runs ("↓ Most first",
"A → Z"). Picking a new field starts it in that field's natural direction. The choice is saved
to the signed-in account (user_preferences) as "field:direction", so the page comes back the same
on any device; ?sort=&dir= in the URL always wins, so a shared or bookmarked link means what it
says.

Two things hold whichever way a list runs: finished sets trail on the collection and director
pages (those pages are about what's missing), and titles with no date or no rating go last --
"oldest first" leading with a dozen undated announcements would be noise.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import Session, col, select

from app.models import UserPreference

ASC, DESC = "asc", "desc"


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    default_dir: str
    #: What the direction button says for each direction.
    asc_label: str
    desc_label: str


def _count(key: str, label: str, dir_: str = DESC) -> Option:
    return Option(key, label, dir_, "↑ Fewest first", "↓ Most first")


NAME = Option("name", "Name", ASC, "A → Z", "Z → A")
RELEASE_NEW = Option("release", "Release date", DESC, "↑ Oldest first", "↓ Newest first")
RELEASE_OLD = Option("release", "Release date", ASC, "↑ Oldest first", "↓ Newest first")
RATING = Option("rating", "Rating", DESC, "↑ Lowest first", "↓ Highest first")
BEST_MISSING = Option("rating", "Best missing film", DESC, "↑ Lowest first", "↓ Highest first")
COMPLETE = Option("complete", "Completeness", DESC, "↑ Least complete", "↓ Most complete")

OPTIONS: dict[str, tuple[Option, ...]] = {
    "franchises": (_count("owned", "Owned"), _count("missing", "Missing"), COMPLETE, RELEASE_NEW, NAME),
    "collections": (BEST_MISSING, _count("missing", "Missing"), COMPLETE,
                    Option("release", "Newest missing film", DESC, "↑ Oldest first", "↓ Newest first"), NAME),
    "directors": (_count("owned", "Films owned"), BEST_MISSING, _count("missing", "Missing"), COMPLETE,
                  Option("release", "Newest missing film", DESC, "↑ Oldest first", "↓ Newest first"), NAME),
    "spinoffs": (Option("show", "Show", ASC, "A → Z", "Z → A"), NAME,
                 Option("release", "First aired", DESC, "↑ Oldest first", "↓ Newest first")),
    "upcoming": (Option("release", "Release date", ASC, "↑ Soonest first", "↓ Latest first"),
                 Option("collection", "Collection", ASC, "A → Z", "Z → A"), NAME),
    # The tiles on a collection, franchise or director page: one choice for all three.
    "detail": (RELEASE_OLD, RATING, NAME),
}

#: Values saved before the direction button existed (0.29.0), and old ?sort= links.
_LEGACY = {"almost": ("missing", ASC), "newest": ("release", DESC), "oldest": ("release", ASC),
           "soonest": ("release", ASC), "source": ("show", ASC)}


def _option(page: str, key: str) -> Option | None:
    return next((o for o in OPTIONS[page] if o.key == key), None)


def default(page: str) -> tuple[str, str]:
    first = OPTIONS[page][0]
    return first.key, first.default_dir


def _parse(page: str, key: str | None, dir_: str | None) -> tuple[str, str] | None:
    if not key:
        return None
    if key in _LEGACY and _option(page, key) is None:
        key, legacy_dir = _LEGACY[key]
        dir_ = dir_ or legacy_dir
    option = _option(page, key)
    if option is None:
        return None
    return key, dir_ if dir_ in (ASC, DESC) else option.default_dir


def resolve(session: Session, user_id: int | None, page: str, requested: str | None,
            direction: str | None = None) -> tuple[str, str]:
    """(field, direction) to use: the one asked for (and remembered), else the remembered one,
    else the page's default. Unknown values are ignored rather than saved."""
    pref = f"sort:{page}"
    chosen = _parse(page, requested, direction)
    if chosen is not None:
        if user_id is not None:
            _save(session, user_id, pref, f"{chosen[0]}:{chosen[1]}")
        return chosen
    if user_id is not None:
        saved = session.exec(select(UserPreference.value).where(
            col(UserPreference.user_id) == user_id, col(UserPreference.key) == pref)).first()
        if saved:
            key, _, dir_ = saved.partition(":")
            parsed = _parse(page, key, dir_ or None)
            if parsed is not None:
                return parsed
    return default(page)


def _save(session: Session, user_id: int, key: str, value: str) -> None:
    row = session.exec(select(UserPreference).where(
        col(UserPreference.user_id) == user_id, col(UserPreference.key) == key)).first()
    if row is None:
        row = UserPreference(user_id=user_id, key=key, value=value)
    elif row.value == value:
        return
    row.value = value
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()


def control(page: str, current: tuple[str, str], action: str, *, hidden: dict | None = None,
            exclude: tuple[str, ...] = ()) -> dict:
    """What partials/sort_control.html draws. `action` is the page's own URL; `hidden` carries
    other query parameters the page must keep (e.g. Collections' started=1)."""
    key, dir_ = current
    option = _option(page, key) or OPTIONS[page][0]
    flip = ASC if dir_ == DESC else DESC
    return {
        "action": action,
        "options": [{"key": o.key, "label": o.label, "selected": o.key == key}
                    for o in OPTIONS[page] if o.key not in exclude],
        "dir": dir_,
        "dir_label": option.asc_label if dir_ == ASC else option.desc_label,
        "flip": flip,
        "flip_label": option.asc_label if flip == ASC else option.desc_label,
        "hidden": {k: v for k, v in (hidden or {}).items() if v is not None},
    }


# ---------------------------------------------------------------------- orderings


def _ordered(items: Sequence, value: Callable, dir_: str, *, tie: Callable,
             last: Callable | None = None) -> list:
    """Sort by `value` in `dir_`, ties by `tie` ascending whichever way; items whose value is
    None go last, then anything `last` says trails."""
    known = [i for i in items if value(i) is not None]
    unknown = [i for i in items if value(i) is None]
    result = sorted(sorted(known, key=tie), key=value, reverse=dir_ == DESC) + sorted(unknown, key=tie)
    if last is not None:
        result = [i for i in result if not last(i)] + [i for i in result if last(i)]
    return result


def _release(item) -> str | None:  # noqa: ANN001 - a MissingMovie, DirectorTitle, Title or UpcomingFilm
    value = (getattr(item, "release_date", None) or getattr(item, "release_year", None)
             or getattr(item, "year", None))
    return str(value) if value else None


def _title(item) -> str:  # noqa: ANN001
    return (getattr(item, "title", None) or getattr(item, "name", None) or "").casefold()


def sort_groups(groups: list, page: str, current: tuple[str, str]) -> list:
    """Collections, directors or franchises. Each group has a name, and owned/missing that are
    either lists or (for franchises) counts with the lists alongside."""
    key, dir_ = current

    def owned_n(g) -> int:  # noqa: ANN001
        return g.owned if isinstance(g.owned, int) else len(g.owned)

    def missing_n(g) -> int:  # noqa: ANN001
        return g.missing if isinstance(g.missing, int) else len(g.missing)

    def missing_list(g) -> Sequence:  # noqa: ANN001
        return g.missing if not isinstance(g.missing, int) else list(g.missing_films) + list(g.missing_shows)

    def all_titles(g) -> Sequence:  # noqa: ANN001
        if not isinstance(g.owned, int):
            return list(g.owned) + list(missing_list(g))
        return list(g.owned_films) + list(g.owned_shows) + list(missing_list(g))

    def newest(g) -> str | None:  # noqa: ANN001
        dates = [d for d in map(_release, all_titles(g) if page == "franchises" else missing_list(g)) if d]
        return max(dates) if dates else None

    def complete(g) -> float:  # noqa: ANN001
        total = owned_n(g) + missing_n(g)
        return owned_n(g) / total if total else 0.0

    def best(g) -> float | None:  # noqa: ANN001
        rating = getattr(g, "best_rating", -1.0)
        return rating if rating is not None and rating >= 0 else None

    values = {"owned": owned_n, "missing": missing_n, "complete": complete, "rating": best,
              "release": newest, "name": lambda g: g.name.casefold()}
    finished = None if page == "franchises" else (lambda g: missing_n(g) == 0)
    return _ordered(groups, values.get(key, values["name"]), dir_,
                    tie=lambda g: g.name.casefold(), last=finished)


def sort_titles(titles: Sequence, current) -> list:  # noqa: ANN001 - (field, dir) or a field
    """The tiles on a detail page: release date, rating or name, in either direction."""
    key, dir_ = current if isinstance(current, tuple) else (current, None)
    option = _option("detail", key) or OPTIONS["detail"][0]
    dir_ = dir_ or option.default_dir
    values = {"release": _release, "rating": lambda t: getattr(t, "rating", None), "name": _title}
    return _ordered(titles, values.get(option.key, _release), dir_, tie=_title)


def sort_spinoffs(suggestions: list, current: tuple[str, str]) -> list:
    key, dir_ = current
    values = {
        "show": lambda s: (s.source_show_name.casefold(), s.spinoff_name.casefold()),
        "name": lambda s: s.spinoff_name.casefold(),
        "release": lambda s: s.first_air_year,
    }
    return _ordered(suggestions, values.get(key, values["show"]), dir_,
                    tie=lambda s: s.spinoff_name.casefold())


def sort_upcoming(films: list, current: tuple[str, str]) -> list:
    key, dir_ = current
    values = {
        "release": lambda f: f.release_date,
        "collection": lambda f: f.collection_name.casefold(),
        "name": lambda f: f.title.casefold(),
    }
    # Within a collection, soonest first: the tie-breaker is the date, then the title.
    return _ordered(films, values.get(key, values["release"]), dir_,
                    tie=lambda f: (f.release_date is None, f.release_date or "", f.title.casefold()))
