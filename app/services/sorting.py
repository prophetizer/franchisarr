"""How each list page can be sorted, and remembering each person's last choice per page.

Every page offers its options as "Sort by a · b · c" links (partials/sort_links.html). Choosing
one saves it to the signed-in account (user_preferences), so the page comes back sorted the
same way on any device; a URL with ?sort= always wins, so a shared or bookmarked link means
what it says. The orderings themselves live here too, so a page's options and what they do
can't drift apart.

"Complete" lists trail on the collection and director pages whatever the sort: those pages are
about what's missing, and a finished set leading the list would be noise.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from sqlmodel import Session, col, select

from app.models import UserPreference

#: page -> ((key, label), ...). The first is the default.
OPTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "franchises": (("owned", "most owned"), ("missing", "most missing"), ("complete", "most complete"),
                   ("newest", "newest"), ("name", "name")),
    "collections": (("rating", "best missing film"), ("missing", "most missing"),
                    ("almost", "almost complete"), ("complete", "most complete"),
                    ("newest", "newest missing"), ("name", "name")),
    "directors": (("owned", "films owned"), ("rating", "best missing film"), ("missing", "most missing"),
                  ("almost", "almost complete"), ("complete", "most complete"),
                  ("newest", "newest missing"), ("name", "name")),
    "spinoffs": (("source", "show"), ("name", "name"), ("newest", "newest"), ("oldest", "oldest")),
    "upcoming": (("soonest", "soonest"), ("collection", "collection"), ("name", "name")),
    # The tiles on a collection, franchise or director page: one choice for all three.
    "detail": (("release", "release date"), ("rating", "rating"), ("name", "name")),
}


def default(page: str) -> str:
    return OPTIONS[page][0][0]


def resolve(session: Session, user_id: int | None, page: str, requested: str | None) -> str:
    """The sort to use: the one asked for (and remembered), else the remembered one, else the
    page's default. An unknown value is ignored rather than saved."""
    valid = {key for key, _ in OPTIONS[page]}
    key = f"sort:{page}"
    if requested in valid:
        if user_id is not None:
            _save(session, user_id, key, requested)
        return requested
    if user_id is not None:
        saved = session.exec(select(UserPreference.value).where(
            col(UserPreference.user_id) == user_id, col(UserPreference.key) == key)).first()
        if saved in valid:
            return saved
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


def links(page: str, current: str, url_for: Callable[[str], str],
          exclude: tuple[str, ...] = ()) -> list[dict]:
    """What partials/sort_links.html draws: label, href, whether it's the current one. `exclude`
    drops options a particular page can't honour (franchise titles carry no rating)."""
    return [{"key": key, "label": label, "url": url_for(key), "active": key == current}
            for key, label in OPTIONS[page] if key not in exclude]


# ---------------------------------------------------------------------- orderings


def _date(value) -> str:  # noqa: ANN001
    """A sortable date string from a release_date, a year, or nothing ("" sorts first)."""
    if value is None:
        return ""
    return str(value)


def _release(item) -> str:  # noqa: ANN001 - a MissingMovie, DirectorTitle, Title or UpcomingFilm
    return _date(getattr(item, "release_date", None) or getattr(item, "release_year", None)
                 or getattr(item, "year", None))


def _title(item) -> str:  # noqa: ANN001
    return (getattr(item, "title", None) or getattr(item, "name", None) or "").casefold()


def _newest(items: Sequence) -> str:
    return max((_release(i) for i in items), default="")


def _complete(owned: int, missing: int) -> float:
    total = owned + missing
    return owned / total if total else 0.0


def sort_groups(groups: list, page: str, how: str) -> list:
    """Collections, directors or franchises. Each group has a name, and owned/missing that are
    either lists or (for franchises) counts with the lists alongside."""

    def owned_n(g) -> int:  # noqa: ANN001
        return g.owned if isinstance(g.owned, int) else len(g.owned)

    def missing_n(g) -> int:  # noqa: ANN001
        return g.missing if isinstance(g.missing, int) else len(g.missing)

    def missing_list(g) -> Sequence:  # noqa: ANN001
        if not isinstance(g.missing, int):
            return g.missing
        return list(g.missing_films) + list(g.missing_shows)

    def all_titles(g) -> Sequence:  # noqa: ANN001
        if not isinstance(g.owned, int):
            return list(g.owned) + list(missing_list(g))
        return list(g.owned_films) + list(g.owned_shows) + list(missing_list(g))

    name = lambda g: g.name.casefold()  # noqa: E731
    finished = (lambda g: missing_n(g) == 0) if page != "franchises" else (lambda g: False)
    keys = {
        "owned": lambda g: (finished(g), -owned_n(g), name(g)),
        "missing": lambda g: (finished(g), -missing_n(g), name(g)),
        "complete": lambda g: (finished(g), -_complete(owned_n(g), missing_n(g)), name(g)),
        "almost": lambda g: (finished(g), missing_n(g), -_complete(owned_n(g), missing_n(g)), name(g)),
        "rating": lambda g: (finished(g), -g.best_rating, name(g)),
        "name": lambda g: (finished(g), name(g)),
    }
    if how == "newest":
        # Newest missing on collections/directors; newest anything in a franchise.
        pick = all_titles if page == "franchises" else missing_list
        ordered = sorted(groups, key=name)
        ordered.sort(key=lambda g: _newest(pick(g)), reverse=True)
        return sorted(ordered, key=finished)
    return sorted(groups, key=keys.get(how, keys["name"]))


def sort_titles(titles: Sequence, how: str) -> list:
    """The tiles on a detail page: release date (oldest first), rating (best first, unrated
    last), or name."""
    if how == "rating":
        return sorted(titles, key=lambda t: (getattr(t, "rating", None) is None,
                                             -(getattr(t, "rating", None) or 0), _title(t)))
    if how == "name":
        return sorted(titles, key=_title)
    return sorted(titles, key=lambda t: (_release(t) == "", _release(t), _title(t)))


def sort_spinoffs(suggestions: list, how: str) -> list:
    if how == "name":
        return sorted(suggestions, key=lambda s: s.spinoff_name.casefold())
    if how in ("newest", "oldest"):
        undated = [s for s in suggestions if s.first_air_year is None]
        dated = sorted((s for s in suggestions if s.first_air_year is not None),
                       key=lambda s: (s.first_air_year, s.spinoff_name.casefold()), reverse=how == "newest")
        return dated + undated
    return list(suggestions)      # "source": the service's own order, grouped by show


def sort_upcoming(films: list, how: str) -> list:
    if how == "collection":
        return sorted(films, key=lambda f: (f.collection_name.casefold(), f.release_date is None,
                                            f.release_date or "", f.title.casefold()))
    if how == "name":
        return sorted(films, key=lambda f: f.title.casefold())
    return list(films)            # "soonest": the service's own date order
