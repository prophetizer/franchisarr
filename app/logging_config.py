"""Structured logging to stdout.

Leveled, timestamped, one line per record, no file handlers -- the container runtime is what
collects logs, so writing them anywhere else just fills the config volume.

The secret handling here is deliberately belt-and-braces. "Don't log secrets" is a rule our own
code can follow, but an API key that a third-party library embeds in an exception message, or a
token that ends up in a URL inside a stack trace, is not our code's decision. `register_secret`
adds a value to the root handler's redacting formatter, so every record -- ours,
plexapi's, httpx's, uvicorn's -- is scrubbed on the way out (docs/DEVELOPMENT.md convention 3).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

REDACTED = "***REDACTED***"

#: Minimum length before a value is worth redacting. A one- or two-character "secret" would
#: match constantly and turn every log line into confetti; anything that short is not a key.
MIN_SECRET_LENGTH = 6

_secrets: set[str] = set()


class RedactingFormatter(logging.Formatter):
    """ISO-8601 UTC timestamps, with every registered secret scrubbed from the finished line.

    Redaction happens here rather than in a `logging.Filter` on purpose: filters run before the
    formatter, so at filter time `record.exc_text` is still None and a token inside a traceback
    would sail straight through. Formatting the record first and scrubbing the result covers the
    message, its args, and the traceback in one pass.
    """

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        moment = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            return moment.strftime(datefmt)
        return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def redact(text: str) -> str:
    """Replace any registered secret appearing in `text`."""
    for secret in _secrets:
        if secret in text:
            text = text.replace(secret, REDACTED)
    return text


def register_secret(value: str | None) -> None:
    """Mark a value as never-loggable. Safe to call repeatedly with the same value."""
    if value and len(value) >= MIN_SECRET_LENGTH:
        _secrets.add(value)


def clear_secrets() -> None:
    """Drop the registry. Exists for tests; production only ever adds."""
    _secrets.clear()


def mask_secret(value: str | None, visible: int = 4) -> str:
    """Render a secret for display: bullets plus the last few characters.

    Used by the Settings UI so a user can tell *which* key is configured without the page source
    containing it. Short values are masked entirely rather than mostly revealed.
    """
    if not value:
        return ""
    if len(value) <= visible:
        return "•" * len(value)
    return "•" * (len(value) - visible) + value[-visible:]


def configure_logging(level: str = "INFO") -> None:
    """Install the stdout handler. Idempotent -- re-running replaces the handler rather than
    stacking a second one, which would double every line."""
    resolved = getattr(logging, level.strip().upper(), logging.INFO)
    if not isinstance(resolved, int):
        resolved = logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        RedactingFormatter(fmt="%(asctime)s %(levelname)-8s %(name)s %(message)s")
    )

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(resolved)

    # These three are chatty at DEBUG and mostly report their own internals. They stay one step
    # quieter than the app unless the app itself is at DEBUG.
    for noisy in ("plexapi", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(max(resolved, logging.INFO))
