"""The things a public announcement invites: brute-forced logins, cross-site form posts,
oversized uploads, and pages framed by someone else's site.

Everything here is deliberately small. A self-hosted app behind a reverse proxy gets most of
its protection from the proxy; these are the parts that belong to the app because only it knows
what a login attempt or a form post is.
"""

from __future__ import annotations

import ipaddress
import os
import threading
import time
from collections import deque
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# ---------------------------------------------------------------- login rate limit

#: Failed sign-ins allowed per client address in the window before the form answers 429.
LOGIN_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 15 * 60
#: Failed sign-ins allowed per *username* across every address. Higher than the per-address
#: limit, because it is shared by everyone who can reach the page: its job is to stop guesses
#: spread over many addresses, not to lock the owner out after a few typos.
USERNAME_ATTEMPTS = 20
#: Upper bound on how many addresses/usernames are tracked at once, so a flood of distinct keys
#: can't grow memory without limit. The oldest are dropped first.
MAX_TRACKED_KEYS = 10_000


class LoginLimiter:
    """A sliding window of failed attempts per client, in memory.

    In memory because there is one process and one worker; a restart forgets, which is fine --
    the point is to make a password guess cost fifteen minutes per ten tries, not to keep a
    ledger. Only *failures* count, so a household sharing an address is never locked out by
    successful sign-ins. The Jellyfin/Emby form relays every attempt to that server, which is
    the stronger reason to have this: it stops Franchisarr being a proxy for guessing someone's
    media-server password.
    """

    def __init__(self, attempts: int = LOGIN_ATTEMPTS, window: float = LOGIN_WINDOW_SECONDS,
                 max_keys: int = MAX_TRACKED_KEYS) -> None:
        self.attempts = attempts
        self.window = window
        self.max_keys = max_keys
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures.get(key)
        if q is None:
            q = self._failures[key] = deque()
        while q and q[0] <= now - self.window:
            q.popleft()
        return q

    def check(self, key: str) -> None:
        """Raise 429 when the client has used up its attempts."""
        with self._lock:
            if key not in self._failures:
                return
            q = self._prune(key, time.monotonic())
            if not q:
                del self._failures[key]
                return
            if len(q) >= self.attempts:
                retry = int(self.window - (time.monotonic() - q[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many sign-in attempts. Try again later.",
                    headers={"Retry-After": str(retry)},
                )

    def failed(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now).append(now)
            if len(self._failures) > self.max_keys:
                # Dicts keep insertion order: drop the longest-tracked keys first.
                for stale in list(self._failures)[: len(self._failures) - self.max_keys]:
                    del self._failures[stale]

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_limiter = LoginLimiter()
#: Per-username failures, keyed "local:<name>" or "server:<id>:<name>".
username_limiter = LoginLimiter(attempts=USERNAME_ATTEMPTS)
#: Starting a Plex sign-in creates a PIN at plex.tv under this install's client id; every start
#: counts, success or not, so nobody can make the install spam plex.tv.
plex_start_limiter = LoginLimiter(attempts=30)


def username_key(username: str, server_id: int | None = None) -> str:
    name = (username or "").strip().casefold()
    return f"server:{server_id}:{name}" if server_id is not None else f"local:{name}"


def _is_internal(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def trusted_proxy_hops() -> int:
    """How many reverse proxies sit in front of the app (TRUSTED_PROXY_HOPS, default 1)."""
    try:
        return max(1, int(os.environ.get("TRUSTED_PROXY_HOPS", "1")))
    except ValueError:
        return 1


def client_key(request: Request) -> str:
    """The address to count sign-in failures against.

    X-Forwarded-For is only believed when the request actually came from a proxy on the same
    network (a private or loopback peer) -- from anywhere else it's just a header the sender
    wrote. And even then only the entries *our* proxies appended count: each proxy appends the
    address it saw, so with N proxies in front the client is the Nth entry from the right.
    Everything to the left of that was supplied by the client and is ignored. Reading the
    first entry, as this used to, let anyone pick a fresh address per request and guess
    passwords without limit.
    """
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded or not _is_internal(peer):
        return peer
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    if not hops:
        return peer
    return hops[-min(trusted_proxy_hops(), len(hops))]


# ---------------------------------------------------------------- cross-site posts

def same_site(request: Request) -> bool:
    """Whether a state-changing request came from this site.

    The session cookie is SameSite=Lax, which already keeps it off cross-site POSTs in every
    current browser. This is the second lock: browsers send Sec-Fetch-Site on every request,
    and Origin on every POST, so a form post from another site is refused even where Lax has
    a gap (older browsers, a top-level navigation POST). Requests with neither header -- curl,
    the CLI, an *arr polling a list -- carry no cookie, so they are not cross-site attacks and
    are let through to be judged by their own credentials.
    """
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site:
        # Not "same-site": that includes every sibling subdomain, and a homelab's *.domain is
        # full of other apps -- one XSS in any of them could post here with the Lax cookie.
        return fetch_site in ("same-origin", "none")
    origin = request.headers.get("origin")
    if origin:
        host = request.headers.get("host", "")
        return urlparse(origin).netloc.lower() == host.lower()
    return True


class CrossSiteGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN001, ANN202
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not same_site(request):
            return Response("Cross-site request refused.", status_code=status.HTTP_403_FORBIDDEN)
        return await call_next(request)


# ---------------------------------------------------------------- request size

#: The largest body the app accepts. A config export is tens of kilobytes; a megabyte is
#: generous. Anything bigger is not a form or a backup.
MAX_BODY_BYTES = 2 * 1024 * 1024


class _BodyTooLarge(HTTPException):
    """An HTTPException so FastAPI's body parsing re-raises it as-is (as a 413) rather than
    folding it into a generic 400; the middleware below catches it if it gets that far."""

    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                         detail="Request body too large.")


class BodySizeLimit:
    """Refuse bodies over MAX_BODY_BYTES, counting what actually arrives.

    Checking Content-Length alone let a chunked upload (which has none) through at any size --
    and FastAPI reads a form body before it checks who is asking, so that was anonymous. Plain
    ASGI rather than BaseHTTPMiddleware so the byte count sits on the receive stream itself.
    """

    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES) -> None:  # noqa: ANN001
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope.get("headers") or []).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await _too_large(send)
            return

        received = 0
        started = False

        async def counting_receive():  # noqa: ANN202
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge()
            return message

        async def tracking_send(message) -> None:  # noqa: ANN001
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            if not started:
                await _too_large(send)


async def _too_large(send) -> None:  # noqa: ANN001
    await send({"type": "http.response.start", "status": status.HTTP_413_CONTENT_TOO_LARGE,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
    await send({"type": "http.response.body", "body": b"Request body too large."})


# ---------------------------------------------------------------- headers

#: Alpine evaluates x-data expressions, which needs unsafe-eval, and the theme toggle and the
#: list-URL filler are inline scripts; a stricter script policy would break the pages.
#:
#: Styles, images and fonts may come from any HTTPS origin. The first cut allowed only this app,
#: TMDb, fanart.tv and the theme host from THEME_URL -- and broke every install whose proxy
#: injects the theme.park stylesheet itself (traefik-themepark, nginx sub_filter), which is the
#: common way to run it and which the app cannot see. The theme's own @imports, fonts and
#: background images can sit on any host the theme author chose. With inline scripts already
#: allowed, a tight style policy bought nothing worth that breakage; what the CSP is here for
#: is the rest: no framing, no plugins, no base-tag tricks, forms post only to us and plex.tv.
def security_headers() -> dict[str, str]:
    csp = "; ".join([
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
        "style-src 'self' 'unsafe-inline' https:",
        "img-src 'self' data: https:",
        "font-src 'self' data: https:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self' https://app.plex.tv",
    ])
    return {
        "Content-Security-Policy": csp,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN001, ANN202
        response = await call_next(request)
        for name, value in security_headers().items():
            response.headers.setdefault(name, value)
        return response
