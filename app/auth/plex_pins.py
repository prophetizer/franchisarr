"""Which plex.tv PIN belongs to which browser, kept server-side.

The browser used to hold the PIN id itself in a cookie. PIN ids are plain integers handed out
by plex.tv in sequence, and every PIN this install creates is polled with the same client id --
so anyone who could guess the number of a PIN the owner was signing in with could poll it from
their own browser and be handed the owner's session. Now the browser holds only a random
256-bit handle; the PIN id never leaves the server, a handle works once, and it expires with
the PIN (plex.tv gives a PIN fifteen minutes).

In memory, like the sign-in limiter: one process, and a restart mid-sign-in just means
pressing the button again.
"""

from __future__ import annotations

import secrets
import threading
import time

#: How long a handle stays valid: plex.tv's own PIN lifetime.
PIN_LIFETIME_SECONDS = 15 * 60
#: More pending sign-ins than this at once is not a household; drop the oldest.
MAX_PENDING = 1_000

_pending: dict[str, tuple[int, float]] = {}
_lock = threading.Lock()


def _drop_expired(now: float) -> None:
    for handle in [h for h, (_, expires) in _pending.items() if expires <= now]:
        del _pending[handle]


def remember(pin_id: int) -> str:
    """Store a PIN id and return the opaque handle to give the browser."""
    handle = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _lock:
        _drop_expired(now)
        _pending[handle] = (pin_id, now + PIN_LIFETIME_SECONDS)
        while len(_pending) > MAX_PENDING:
            del _pending[next(iter(_pending))]
    return handle


def lookup(handle: str | None) -> int | None:
    """The PIN id behind a handle, or None if it is unknown or expired."""
    if not handle:
        return None
    now = time.monotonic()
    with _lock:
        _drop_expired(now)
        entry = _pending.get(handle)
    return entry[0] if entry else None


def forget(handle: str | None) -> None:
    """Spend a handle: after a sign-in completes (or is refused) it must not work again."""
    if handle:
        with _lock:
            _pending.pop(handle, None)


def reset() -> None:
    with _lock:
        _pending.clear()
