"""Checks whether a newer Franchisarr has been released (technical challenge #18).

Sends nothing about the install -- no library size, no configuration, no identifier. It is a
plain GET for a public releases list, so the only thing the far end learns is that some IP asked
about releases, which is what fetching any URL discloses.

Never blocks startup and never surfaces an error to the user. A private repository, an offline
host, or a rate-limited API are all ordinary states for a self-hosted app, and none of them is
the user's problem to solve. The banner simply doesn't appear.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests

from app import __version__

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10

#: Overridable so a fork, or the eventual GitHub move, doesn't need a code change here.
DEFAULT_RELEASES_URL = "https://api.github.com/repos/mikeg/franchisarr/releases/latest"

_VERSION_PART = re.compile(r"\d+")


@dataclass(frozen=True)
class UpdateStatus:
    current: str
    latest: str | None = None
    url: str | None = None

    @property
    def update_available(self) -> bool:
        if not self.latest:
            return False
        return _as_tuple(self.latest) > _as_tuple(self.current)


def _as_tuple(version: str) -> tuple[int, ...]:
    """Compare versions numerically. A pre-release suffix like '.dev0' sorts as its digits, which
    is close enough for deciding whether to show a banner."""
    return tuple(int(part) for part in _VERSION_PART.findall(version or "")) or (0,)


def check(url: str = DEFAULT_RELEASES_URL, *, timeout: int = DEFAULT_TIMEOUT) -> UpdateStatus:
    try:
        response = requests.get(url, timeout=timeout, headers={"Accept": "application/json"})
        if response.status_code >= 400:
            logger.debug("Update check returned %s; ignoring", response.status_code)
            return UpdateStatus(current=__version__)
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        # Entirely expected on a private repo or an offline host. Debug, not warning: this is
        # not a problem the operator needs to do anything about.
        logger.debug("Update check unavailable: %s", exc)
        return UpdateStatus(current=__version__)

    tag = payload.get("tag_name") or payload.get("name") if isinstance(payload, dict) else None
    if not tag:
        return UpdateStatus(current=__version__)

    return UpdateStatus(
        current=__version__,
        latest=str(tag).lstrip("v"),
        url=payload.get("html_url") if isinstance(payload, dict) else None,
    )
