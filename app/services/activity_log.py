"""Append-only record of what Franchisarr actually did.

Records the *add* and nothing more. What happens afterwards -- grabbed, downloaded, imported,
failed -- is Radarr's business and Radarr's history page tells it far better than a mirror of it
here ever would (technical challenge #24). The UI should say so plainly rather than implying it
tracks download progress.
"""

from __future__ import annotations

import logging

from sqlmodel import Session, col, desc, select

from app.models import ActivityLogEntry, ItemType, TriggerSource, User

logger = logging.getLogger(__name__)


def record_add(
    session: Session,
    *,
    item_type: str,
    tmdb_id: int,
    title: str,
    instance_id: int | None,
    user: User | None,
    trigger_source: str = TriggerSource.MANUAL.value,
    target: str | None = None,
) -> ActivityLogEntry:
    entry = ActivityLogEntry(
        item_type=item_type,
        tmdb_id=tmdb_id,
        title=title,
        instance_id=instance_id,
        target=target,
        # Null means a scheduled scan did it, which is why this is the user id rather than a
        # name: the row must stay meaningful if the account is later renamed.
        triggered_by=user.id if user else None,
        trigger_source=trigger_source,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def recent(session: Session, limit: int = 50, offset: int = 0) -> list[ActivityLogEntry]:
    return list(
        session.exec(
            select(ActivityLogEntry)
            .order_by(desc(col(ActivityLogEntry.timestamp)))
            .offset(offset)
            .limit(limit)
        ).all()
    )


def count(session: Session) -> int:
    return len(session.exec(select(ActivityLogEntry)).all())
