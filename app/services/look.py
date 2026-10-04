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


#: Showcase's franchise intros (0.58.0): on unless this person turns them off in their menu.
INTROS_KEY = "intros"


def intros_on(session: Session, user_id: int | None) -> bool:
    if user_id is None:
        return True
    value = session.exec(select(UserPreference.value).where(
        col(UserPreference.user_id) == user_id, col(UserPreference.key) == INTROS_KEY)).first()
    return value != "off"


def set_intros(session: Session, user_id: int, on: bool) -> bool:
    from app.services.sorting import _save

    _save(session, user_id, INTROS_KEY, "on" if on else "off")
    return on


def intros_of(user) -> bool:  # noqa: ANN001 - a User, or None
    """For the base template, as `of` is."""
    if user is None or getattr(user, "id", None) is None:
        return True
    from app.db import get_engine

    with Session(get_engine()) as session:
        return intros_on(session, user.id)


#: Showcase's effects dial (0.71.0): "full" (everything), "calm" (the looks, nothing that loops or
#: flashes) or "off" (no motion at all, as with the system's reduce-motion setting).
EFFECTS_KEY = "effects"
EFFECTS = ("full", "calm", "off")


def effects(session: Session, user_id: int | None) -> str:
    if user_id is None:
        return "full"
    value = session.exec(select(UserPreference.value).where(
        col(UserPreference.user_id) == user_id, col(UserPreference.key) == EFFECTS_KEY)).first()
    return value if value in EFFECTS else "full"


def set_effects(session: Session, user_id: int, value: str) -> str:
    from app.services.sorting import _save

    value = value if value in EFFECTS else "full"
    _save(session, user_id, EFFECTS_KEY, value)
    return value


def effects_of(user) -> str:  # noqa: ANN001 - a User, or None
    """For the base template, as `of` is."""
    if user is None or getattr(user, "id", None) is None:
        return "full"
    from app.db import get_engine

    with Session(get_engine()) as session:
        return effects(session, user.id)


def next_effects(value: str) -> str:
    """What the menu's button switches to: full, calm, off, then round again."""
    return EFFECTS[(EFFECTS.index(value) + 1) % len(EFFECTS)] if value in EFFECTS else "calm"
