"""Classic or Showcase (0.47.0): each person's choice of look, saved to their account so it
follows them across devices. Classic -- the Pico look everyone has had -- is the default and
the only look anyone gets without choosing; Showcase adds motion and the page's own colour on
top of it (static/showcase.css and showcase.js), and nothing else about a page changes."""

from __future__ import annotations

from sqlmodel import Session, col, select

from app.models import UserPreference

CLASSIC, SHOWCASE = "classic", "showcase"
KEY = "look"


def get(session: Session, user_id: int | None) -> str:
    if user_id is None:
        return CLASSIC
    value = session.exec(select(UserPreference.value).where(
        col(UserPreference.user_id) == user_id, col(UserPreference.key) == KEY)).first()
    return SHOWCASE if value == SHOWCASE else CLASSIC


def set_look(session: Session, user_id: int, value: str) -> str:
    from app.services.sorting import _save

    value = SHOWCASE if value == SHOWCASE else CLASSIC
    _save(session, user_id, KEY, value)
    return value


def of(user) -> str:  # noqa: ANN001 - a User, or None on the sign-in page
    """For the base template, which has the user but no session."""
    if user is None or getattr(user, "id", None) is None:
        return CLASSIC
    from app.db import get_engine

    with Session(get_engine()) as session:
        return get(session, user.id)
