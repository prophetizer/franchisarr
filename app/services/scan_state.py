"""Live state of the running scan.

A scan of a real library takes minutes. Doing that inside a request means the page hangs with no
sign of life and eventually the proxy gives up, which is what happens today. So the scan runs on
a background thread and the page asks this module how it's going.

State lives in memory. That is the honest scope: a scan cannot outlive the process running it, so
persisting "in progress" would only ever produce a stuck flag after a restart. What *is* worth
keeping across restarts -- when the last scan finished and what it found -- goes in settings.

Every method is guarded by one lock. The scheduler thread writes progress while request threads
read it, and a torn read here would show nonsense like 4,000 of 3,428.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanProgress:
    running: bool = False
    #: What the scan is doing now, in words a user can read.
    phase: str = ""
    processed: int = 0
    total: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    #: How the last completed run went, kept so the page can say something after it ends.
    summary: str = ""
    errors: tuple[str, ...] = field(default_factory=tuple)
    trigger: str = ""

    @property
    def percent(self) -> int:
        if not self.total:
            return 0
        return min(100, round(self.processed / self.total * 100))

    @property
    def elapsed_seconds(self) -> int:
        if self.started_at is None:
            return 0
        end = self.finished_at or datetime.now(timezone.utc)
        return max(0, int((end - self.started_at).total_seconds()))


_lock = threading.Lock()
_state = ScanProgress()


def current() -> ScanProgress:
    with _lock:
        return _state


def begin(trigger: str) -> bool:
    """Claim the right to scan. False means one is already running.

    The claim and the check are one operation on purpose: two clicks half a second apart would
    otherwise both see "not running" and start two scans over the same library.
    """
    global _state
    with _lock:
        if _state.running:
            return False
        _state = ScanProgress(
            running=True,
            phase="Starting",
            started_at=datetime.now(timezone.utc),
            trigger=trigger,
        )
    logger.info("Scan started (%s)", trigger)
    return True


def update(phase: str | None = None, processed: int | None = None, total: int | None = None) -> None:
    global _state
    with _lock:
        if not _state.running:
            return
        _state = replace(
            _state,
            phase=phase if phase is not None else _state.phase,
            processed=processed if processed is not None else _state.processed,
            total=total if total is not None else _state.total,
        )


def finish(summary: str, errors: list[str] | None = None) -> None:
    global _state
    with _lock:
        _state = replace(
            _state,
            running=False,
            phase="Finished",
            finished_at=datetime.now(timezone.utc),
            summary=summary,
            errors=tuple(errors or ()),
        )
    logger.info("Scan finished: %s", summary)


def fail(message: str) -> None:
    """Record a scan that died. Without this the state stays 'running' forever and the button
    never comes back."""
    global _state
    with _lock:
        _state = replace(
            _state,
            running=False,
            phase="Failed",
            finished_at=datetime.now(timezone.utc),
            summary="The scan stopped early.",
            errors=(message,),
        )
    logger.error("Scan failed: %s", message)


def reset() -> None:
    """For tests."""
    global _state
    with _lock:
        _state = ScanProgress()
