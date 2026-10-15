"""Collections and franchises one person has hidden from their own lists (0.73.0, michael's
pick). A taste filter like the others: hidden sets fold into a section at the foot of the list
rather than disappearing, and they leave the home page's rows. The household-wide version, for a
TMDb collection that's simply wrong, is still the collection exclude."""

from __future__ import annotations

from sqlmodel import Session, col, delete, select

from app.models import UserHiddenSet

KINDS = ("collection", "franchise")


def hidden(session: Session, user_id: int | None, kind: str) -> set[str]:
    """The refs (collection ids as text, Wikidata ids) this person hides, of one kind."""
    if user_id is None:
        return set()
    return set(session.exec(select(UserHiddenSet.ref).where(
        col(UserHiddenSet.user_id) == user_id, col(UserHiddenSet.kind) == kind)).all())


def is_hidden(session: Session, user_id: int | None, kind: str, ref: str | int) -> bool:
    return str(ref) in hidden(session, user_id, kind)


def set_hidden(session: Session, user_id: int, kind: str, ref: str | int, hide: bool) -> bool:
    if kind not in KINDS:
        raise ValueError(kind)
    ref = str(ref)
    existing = session.exec(select(UserHiddenSet).where(
        col(UserHiddenSet.user_id) == user_id, col(UserHiddenSet.kind) == kind,
        col(UserHiddenSet.ref) == ref)).first()
    if hide and existing is None:
        session.add(UserHiddenSet(user_id=user_id, kind=kind, ref=ref))
    elif not hide and existing is not None:
        session.exec(delete(UserHiddenSet).where(col(UserHiddenSet.id) == existing.id))
    session.commit()
    return hide


def split(items: list, refs: set[str], ref_of) -> tuple[list, list]:  # noqa: ANN001
    """(shown, hidden), each in the order given."""
    shown = [i for i in items if str(ref_of(i)) not in refs]
    folded = [i for i in items if str(ref_of(i)) in refs]
    return shown, folded
