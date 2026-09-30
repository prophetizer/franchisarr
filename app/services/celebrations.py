"""Showcase's celebrations (0.49.0): confetti when a scan finds a collection newly complete --
once per person, on their next visit to the home page or that collection (michael's call).

A scan records completions (`record`); a page asks what's due for this person (`due`) and marks
it seen as it shows it. Only the Showcase look celebrates, so only it marks anything seen: a
person in Classic hasn't had theirs yet. A completion stops being news after CELEBRATE_FOR."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, col, select

from app.models import CollectionCompletion

logger = logging.getLogger(__name__)

CELEBRATE_FOR = timedelta(days=30)
SEEN_KEY = "celebrated"
#: The seen list only needs the recent ones; older completions are past CELEBRATE_FOR anyway.
SEEN_KEEP = 200


def record(session: Session) -> list[str]:
    """After a scan: add every collection complete now that isn't recorded yet. The first time
    ever, they're recorded quietly -- a library full of complete collections isn't news. Returns
    the names newly celebrated."""
    from app.services import movie_gap_service

    complete = {g.collection_id: g.name for g in movie_gap_service.collection_gaps(session)
                if g.owned and not g.missing and not g.hidden}
    known = set(session.exec(select(CollectionCompletion.collection_id)).all())
    first_time = not known and session.exec(select(CollectionCompletion.id).limit(1)).first() is None
    new = []
    for collection_id, name in complete.items():
        if collection_id in known:
            continue
        session.add(CollectionCompletion(collection_id=collection_id, name=name, celebrate=not first_time))
        if not first_time:
            new.append(name)
    session.commit()
    if new:
        logger.info("Completed: %s", ", ".join(sorted(new)))
    return new


def _seen(session: Session, user_id: int) -> list[int]:
    from app.models import UserPreference

    raw = session.exec(select(UserPreference.value).where(
        col(UserPreference.user_id) == user_id, col(UserPreference.key) == SEEN_KEY)).first()
    try:
        return [int(i) for i in json.loads(raw)] if raw else []
    except (ValueError, TypeError):
        return []


def due(session: Session, user_id: int, collection_id: int | None = None) -> list[CollectionCompletion]:
    """What this person hasn't celebrated yet -- every one for the home page, or just this
    collection's -- marked seen as it's returned."""
    from app.services.sorting import _save

    since = datetime.now(timezone.utc) - CELEBRATE_FOR
    query = select(CollectionCompletion).where(col(CollectionCompletion.celebrate) == True,  # noqa: E712
                                               col(CollectionCompletion.completed_at) >= since)
    if collection_id is not None:
        query = query.where(col(CollectionCompletion.collection_id) == collection_id)
    seen = _seen(session, user_id)
    fresh = [c for c in session.exec(query.order_by(col(CollectionCompletion.completed_at))).all() if c.id not in seen]
    if fresh:
        _save(session, user_id, SEEN_KEY, json.dumps((seen + [c.id for c in fresh])[-SEEN_KEEP:]))
    return fresh


def for_page(session: Session, user, collection_id: int | None = None) -> list[CollectionCompletion]:  # noqa: ANN001
    """What a page celebrates for this person: nothing unless they're in the Showcase look."""
    from app.services import look

    if user is None or look.get(session, user.id) != look.SHOWCASE:
        return []
    return due(session, user.id, collection_id)
