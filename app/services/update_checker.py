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

#: The releases *list* rather than `/releases/latest`, deliberately. Forgejo answers 404 on
#: `/releases/latest` when a repository has no releases yet, which is indistinguishable from a
#: broken URL; the list endpoint returns `[]` instead. Both Forgejo and GitHub return that list
#: newest-first with the same field names, so the eventual GitHub migration is a hostname change
#: rather than a code change. Overridable per install via the `update_releases_url` setting, for
#: forks and for anyone who would rather it asked nothing at all.
DEFAULT_RELEASES_URL = (
    "https://api.github.com/repos/prophetizer/franchisarr/releases?per_page=20"
)

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


def releases_url(session=None) -> str:
    """The URL to ask, honouring a per-install override."""
    if session is None:
        return DEFAULT_RELEASES_URL

    from app.services.settings_service import SettingKey, get_setting

    return (get_setting(session, SettingKey.UPDATE_RELEASES_URL) or "").strip() or DEFAULT_RELEASES_URL


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

    # `/releases` gives a list, `/releases/latest` a single object. Accept either, so pointing
    # this at a different forge or endpoint doesn't need a code change.
    candidates = payload if isinstance(payload, list) else [payload]
    candidates = [c for c in candidates if isinstance(c, dict)]

    # Drafts and pre-releases are never announced: "an update is available" would send people to
    # something not meant for them yet.
    candidates = [c for c in candidates if not (c.get("draft") or c.get("prerelease"))]

    # The highest version, not the first in the list. A forge sorts by creation time, and that
    # is not the same thing: Forgejo once stamped a release with the epoch because the tag push
    # and the release request landed together, and it sorted last -- so every install would
    # have been told it was up to date when it was not. Version numbers are the fact; list order
    # is someone else's implementation detail.
    best = None
    for candidate in candidates:
        tag = candidate.get("tag_name") or candidate.get("name")
        if not tag:
            continue
        version = str(tag).lstrip("v")
        if not _VERSION_PART.findall(version):
            continue  # a tag with no digits in it is not a version
        if best is None or _as_tuple(version) > _as_tuple(best[0]):
            best = (version, candidate)

    if best is None:
        return UpdateStatus(current=__version__)
    tag, payload = best

    return UpdateStatus(current=__version__, latest=tag, url=payload.get("html_url"))
