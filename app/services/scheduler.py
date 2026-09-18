"""In-process APScheduler.

One background scheduler inside the web process (docs/DESIGN.md technical challenge #9). At a
few thousand items a scan is minutes of mostly-waiting, so a separate worker container would be
infrastructure for its own sake.

Two things this has to get right, both of which are about not surprising the operator:

* An invalid cron expression disables the schedule and says so, rather than stopping the app
  from starting. Someone typing a bad cron into a settings box should get an error message, not
  a container that crash-loops.
* Jobs don't overlap. A scan can take minutes; if one is still running when the next fires,
  running both would double the Plex and TMDb load for no benefit.

Schedules run in the container's local timezone, not UTC. "0 3 * * *" means 3am where the user
is, which is what anyone typing it expects and what Radarr and Sonarr do; set `TZ` in the
container to control it. Logs stay in UTC deliberately -- that is about correlating with other
services, which is a different problem.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session

from app.db import get_engine
from app.services import scan_job
from app.services.settings_service import SettingKey, get_setting

logger = logging.getLogger(__name__)

JOB_ID = "franchisarr-scan"

_scheduler: BackgroundScheduler | None = None


class InvalidSchedule(ValueError):
    """The cron expression could not be parsed."""


def validate_cron(expression: str) -> CronTrigger | None:
    """Parse a cron expression. Empty means "no schedule", which is valid."""
    value = (expression or "").strip()
    if not value:
        return None
    try:
        return CronTrigger.from_crontab(value)
    except (ValueError, TypeError) as exc:
        raise InvalidSchedule(
            f"{value!r} isn't a valid cron expression. Five fields, e.g. '0 3 * * *' for 3am daily."
        ) from exc


def describe(expression: str) -> str:
    """A human-readable note about when this will next run, for the settings page."""
    try:
        trigger = validate_cron(expression)
    except InvalidSchedule as exc:
        return str(exc)
    if trigger is None:
        return "No scheduled scans — Franchisarr will only scan when you ask it to."

    from datetime import datetime

    # Local time on purpose: the answer should be in the same frame as the question.
    next_run = trigger.get_next_fire_time(None, datetime.now().astimezone())
    if next_run is None:
        return "That schedule will never fire."
    return f"Next scheduled scan: {next_run.strftime('%Y-%m-%d %H:%M %Z')} (this server's time)"


def _run_scan() -> None:
    """The scheduled job.

    Goes through the same background runner a manual scan uses, so the two share one guard: a
    scheduled scan firing while someone is watching a manual one would otherwise run the same
    work twice against Plex and TMDb.
    """
    if not scan_job.run_in_background("scheduled"):
        logger.info("Skipping the scheduled scan: one is already running")


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        # No explicit timezone: APScheduler picks up the system one, so TZ in the container
        # decides when "3am" is. Pinning UTC here would silently shift everyone's schedule.
        _scheduler = BackgroundScheduler()
    return _scheduler


def apply_schedule(expression: str) -> str | None:
    """Install, replace or remove the scan job. Returns the active expression, or None."""
    scheduler = get_scheduler()

    try:
        trigger = validate_cron(expression)
    except InvalidSchedule as exc:
        # Deliberately not fatal: a bad value in the database must not stop the app booting.
        logger.error("Ignoring the configured scan schedule: %s", exc)
        trigger = None

    existing = scheduler.get_job(JOB_ID)
    if trigger is None:
        if existing:
            scheduler.remove_job(JOB_ID)
            logger.info("Scheduled scans disabled")
        return None

    scheduler.add_job(
        _run_scan,
        trigger=trigger,
        id=JOB_ID,
        replace_existing=True,
        # A scan can outlast its own interval; running two at once would double the load on
        # Plex and TMDb to produce the same answer.
        max_instances=1,
        # After a container restart, don't fire once for every run that was missed while it was
        # down -- just resume the schedule.
        coalesce=True,
        misfire_grace_time=3600,
    )
    logger.info("Scheduled scans enabled: %s", expression.strip())
    return expression.strip()


def start(session: Session) -> None:
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
    apply_schedule(get_setting(session, SettingKey.SCAN_SCHEDULE_CRON) or "")


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


def next_run_time():
    scheduler = get_scheduler()
    job = scheduler.get_job(JOB_ID)
    return job.next_run_time if job else None
