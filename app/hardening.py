"""The things a public announcement invites: brute-forced logins, cross-site form posts,
oversized uploads, and pages framed by someone else's site.

Everything here is deliberately small. A self-hosted app behind a reverse proxy gets most of
its protection from the proxy; these are the parts that belong to the app because only it knows
what a login attempt or a form post is.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# ---------------------------------------------------------------- login rate limit

#: Failed sign-ins allowed per client address in the window before the form answers 429.
LOGIN_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 15 * 60


class LoginLimiter:
    """A sliding window of failed attempts per client, in memory.

    In memory because there is one process and one worker; a restart forgets, which is fine --
    the point is to make a password guess cost fifteen minutes per ten tries, not to keep a
    ledger. Only *failures* count, so a household sharing an address is never locked out by
    successful sign-ins. The Jellyfin/Emby form relays every attempt to that server, which is
    the stronger reason to have this: it stops Franchisarr being a proxy for guessing someone's
    media-server password.
    """

    def __init__(self, attempts: int = LOGIN_ATTEMPTS, window: float = LOGIN_WINDOW_SECONDS) -> None:
        self.attempts = attempts
        self.window = window
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        return q

    def check(self, key: str) -> None:
        """Raise 429 when the client has used up its attempts."""
        with self._lock:
            q = self._prune(key, time.monotonic())
            if len(q) >= self.attempts:
                retry = int(self.window - (time.monotonic() - q[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many sign-in attempts. Try again later.",
                    headers={"Retry-After": str(retry)},
                )

    def failed(self, key: str) -> None:
        with self._lock:
            self._prune(key, time.monotonic()).append(time.monotonic())

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_limiter = LoginLimiter()


def client_key(request: Request) -> str:
    """The address to count against. Behind a reverse proxy that is the first X-Forwarded-For
    entry, which the proxy sets; uvicorn already honours it for request.client when started
    with --proxy-headers, but not every install does."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


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
        return fetch_site in ("same-origin", "same-site", "none")
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


class BodySizeLimit(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN001, ANN202
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return Response("Request body too large.", status_code=status.HTTP_413_CONTENT_TOO_LARGE)
        return await call_next(request)


# ---------------------------------------------------------------- headers

#: Alpine evaluates x-data expressions, which needs unsafe-eval, and the theme toggle and the
#: list-URL filler are inline scripts; a stricter script policy would break the pages. What the
#: CSP does buy: no images or styles from anywhere but this app, TMDb, fanart.tv and the
#: configured theme host, no plugins, no framing.
def security_headers(theme_host: str | None) -> dict[str, str]:
    style_hosts = ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"]
    img_hosts = ["'self'", "data:", "https://image.tmdb.org", "https://assets.fanart.tv"]
    if theme_host:
        style_hosts.append(theme_host)
        img_hosts.append(theme_host)
    csp = "; ".join([
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
        f"style-src {' '.join(style_hosts)}",
        f"img-src {' '.join(img_hosts)}",
        "font-src 'self' https://fonts.gstatic.com",
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
        from app.services.theme_service import resolve

        theme_url = resolve().url
        theme_host = f"{urlparse(theme_url).scheme}://{urlparse(theme_url).netloc}" if theme_url else None
        for name, value in security_headers(theme_host).items():
            response.headers.setdefault(name, value)
        return response
