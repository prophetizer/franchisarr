"""Upcoming as a calendar (0.71.0, michael's pick): each month that has a release in it, as a
grid of weeks with every film's poster on its day. The list stays the default; the choice is
each person's own and is remembered."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session, col, select

from app.models import UserPreference

KEY = "upcoming_view"
LIST, CALENDAR = "list", "calendar"
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass
class Day:
    day: date
    films: list = field(default_factory=list)
    is_today: bool = False


@dataclass
class Month:
    label: str
    #: Monday-first weeks; None for the days of the months either side.
    weeks: list[list[Day | None]]


def view(session: Session, user_id: int, asked: str | None) -> str:
    """The view asked for (and remembered), else the one this person chose last, else the list."""
    from app.services.sorting import _save

    if asked in (LIST, CALENDAR):
        _save(session, user_id, KEY, asked)
        return asked
    stored = session.exec(select(UserPreference.value).where(
        col(UserPreference.user_id) == user_id, col(UserPreference.key) == KEY)).first()
    return CALENDAR if stored == CALENDAR else LIST


def months(films, today: date) -> list[Month]:  # noqa: ANN001 - UpcomingFilms
    """Every month with a dated film in it, in order; films on a day keep the order given."""
    by_day: dict[date, list] = {}
    for film in films:
        if film.release is not None:
            by_day.setdefault(film.release, []).append(film)
    shown = sorted({(d.year, d.month) for d in by_day})
    grid = calendar.Calendar(firstweekday=0)
    result = []
    for year, month in shown:
        weeks = [[Day(d, by_day.get(d, []), d == today) if d.month == month else None for d in week]
                 for week in grid.monthdatescalendar(year, month)]
        result.append(Month(date(year, month, 1).strftime("%B %Y"), weeks))
    return result
