"""The weekly digest (0.73.0, michael's pick): one notification a week instead of one after every
scan. In weekly mode a scan still records what it found -- so nothing is news twice -- but banks
it in DIGEST_PENDING instead of sending it; the digest job sends the bank as one message and
empties it once delivered. A failed delivery keeps the bank for next week."""

from __future__ import annotations

import json
import logging

from sqlmodel import Session

from app.services import notifier
from app.services.settings_service import SettingKey, get_setting, set_setting

logger = logging.getLogger(__name__)

MODES = ("each", "weekly")
_SECTIONS = ("new_movies", "new_shows", "release_dates")


def weekly(session: Session) -> bool:
    return get_setting(session, SettingKey.NOTIFY_MODE) == "weekly"


def _load(session: Session) -> dict[str, list[dict]]:
    try:
        stored = json.loads(get_setting(session, SettingKey.DIGEST_PENDING) or "{}")
    except ValueError:
        stored = {}
    return {s: [i for i in stored.get(s, []) if isinstance(i, dict)] for s in _SECTIONS}


def bank(session: Session, report: notifier.ScanReport) -> int:
    """Add a scan's news to the week's. A film already banked isn't banked twice -- except a
    release date, where the newest word replaces the older one. Returns the bank's size."""
    pending = _load(session)
    for section in _SECTIONS:
        items = pending[section]
        for item in getattr(report, section):
            entry = {"item_type": item.item_type, "tmdb_id": item.tmdb_id, "title": item.title, "detail": item.detail}
            same = next((i for i in items if i.get("item_type") == item.item_type and i.get("tmdb_id") == item.tmdb_id), None)
            if same is None:
                items.append(entry)
            elif section == "release_dates":
                same.update(entry)
    set_setting(session, SettingKey.DIGEST_PENDING, json.dumps(pending))
    session.commit()
    return sum(len(v) for v in pending.values())


def pending_report(session: Session) -> notifier.ScanReport:
    pending = _load(session)
    return notifier.ScanReport(
        **{s: [notifier.NewItem(i.get("item_type", ""), int(i.get("tmdb_id") or 0), str(i.get("title", "")),
                                str(i.get("detail", ""))) for i in pending[s]] for s in _SECTIONS},
        period="this week")


def send(session: Session) -> bool:
    """Send the week's bank, if there is news and somewhere to send it; empty it once delivered."""
    report = pending_report(session)
    url = get_setting(session, SettingKey.WEBHOOK_URL)
    if not report.has_news or not url:
        return False
    if notifier.send(url, report, get_setting(session, SettingKey.WEBHOOK_FORMAT) or "generic"):
        set_setting(session, SettingKey.DIGEST_PENDING, "")
        session.commit()
        logger.info("Weekly digest sent: %s", report.summary())
        return True
    logger.warning("The weekly digest couldn't be delivered; keeping it for next time")
    return False
