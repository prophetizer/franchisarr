"""Outgoing webhooks when a scheduled scan finds something new.

Three payload shapes (docs/DESIGN.md decision log): a plain generic JSON body, and pre-shaped
Discord and Slack ones, since those two are what this community actually uses.

The limits are the interesting part. A first scan on a real library found 227 missing films, and
every one of these services rejects an oversized payload outright -- Discord allows 10 embeds of
25 fields each and 2000 characters of content, Slack's blocks have their own caps. A notifier
that works during testing and then silently fails on the one scan that mattered would be worse
than not having it, so everything here truncates to a stated cap and says how many it left out.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import requests

from app.models import ItemType, WebhookFormat

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15

#: Items listed in a notification before it switches to "...and N more". Well under every
#: service's cap, and past a couple of dozen nobody is reading the list anyway.
MAX_LISTED = 15

#: Discord rejects a message whose content exceeds this.
DISCORD_CONTENT_LIMIT = 2000

#: Discord's own blurple, so the embed doesn't render with a default grey bar.
DISCORD_COLOUR = 0x5865F2


class NotifierError(RuntimeError):
    """The webhook could not be delivered."""


@dataclass
class NewItem:
    item_type: str
    tmdb_id: int
    title: str
    detail: str = ""

    @property
    def label(self) -> str:
        return f"{self.title} — {self.detail}" if self.detail else self.title


@dataclass
class ScanReport:
    """What a scan turned up that hadn't been seen before."""

    new_movies: list[NewItem] = field(default_factory=list)
    new_shows: list[NewItem] = field(default_factory=list)
    #: Announced films in owned franchises that gained a release date, or whose date moved.
    release_dates: list[NewItem] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.new_movies) + len(self.new_shows) + len(self.release_dates)

    @property
    def has_news(self) -> bool:
        return self.total > 0

    def summary(self) -> str:
        parts = []
        if self.new_movies:
            count = len(self.new_movies)
            parts.append(f"{count} missing film{'' if count == 1 else 's'}")
        if self.new_shows:
            count = len(self.new_shows)
            parts.append(f"{count} spin-off{'' if count == 1 else 's'}")
        if self.release_dates:
            count = len(self.release_dates)
            parts.append(f"{count} release date{'' if count == 1 else 's'}")
        if not parts:
            return "nothing new"
        return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _listed(items: list[NewItem]) -> tuple[list[NewItem], int]:
    """Return the items to show and how many were left out."""
    return items[:MAX_LISTED], max(0, len(items) - MAX_LISTED)


def _sections(report: ScanReport) -> tuple[tuple[str, list[NewItem]], ...]:
    return (
        ("Missing films", report.new_movies),
        ("Spin-offs", report.new_shows),
        ("Release dates", report.release_dates),
    )


def build_generic(report: ScanReport) -> dict:
    """A plain body for anyone wiring this into their own automation.

    Not truncated: a machine consumer wants the whole list, and there is no third-party limit to
    respect when the recipient is the user's own endpoint.
    """
    return {
        "event": "franchisarr.scan_complete",
        "summary": report.summary(),
        "total_new": report.total,
        "movies": [
            {"tmdb_id": item.tmdb_id, "title": item.title, "collection": item.detail}
            for item in report.new_movies
        ],
        "shows": [
            {"tmdb_id": item.tmdb_id, "title": item.title, "relation": item.detail}
            for item in report.new_shows
        ],
        "release_dates": [
            {"tmdb_id": item.tmdb_id, "title": item.title, "detail": item.detail}
            for item in report.release_dates
        ],
    }


def build_discord(report: ScanReport) -> dict:
    """A Discord embed.

    Fields are used rather than one long description because Discord renders them readably and
    each has its own 1024-character cap, which a list of film titles will not approach.
    """
    fields = []
    for title, items in _sections(report):
        if not items:
            continue
        shown, omitted = _listed(items)
        lines = [f"• {item.label}" for item in shown]
        if omitted:
            lines.append(f"…and {omitted} more")
        fields.append({"name": f"{title} ({len(items)})", "value": "\n".join(lines)[:1024]})

    return {
        "username": "Franchisarr",
        "content": f"Franchisarr found {report.summary()}."[:DISCORD_CONTENT_LIMIT],
        "embeds": [
            {
                "title": "Scan complete",
                "color": DISCORD_COLOUR,
                "fields": fields,
            }
        ],
    }


def build_slack(report: ScanReport) -> dict:
    """A Slack message.

    `text` is set as well as blocks: it is what appears in the notification popup and in clients
    that don't render blocks, and omitting it gives people a blank alert.
    """
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Franchisarr* found {report.summary()}."},
        }
    ]

    for title, items in _sections(report):
        if not items:
            continue
        shown, omitted = _listed(items)
        lines = [f"• {item.label}" for item in shown]
        if omitted:
            lines.append(f"_…and {omitted} more_")
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title} ({len(items)})*\n" + "\n".join(lines),
                },
            }
        )

    return {"text": f"Franchisarr found {report.summary()}.", "blocks": blocks}


BUILDERS = {
    WebhookFormat.GENERIC.value: build_generic,
    WebhookFormat.DISCORD.value: build_discord,
    WebhookFormat.SLACK.value: build_slack,
}


def build_payload(report: ScanReport, webhook_format: str) -> dict:
    builder = BUILDERS.get(webhook_format)
    if builder is None:
        logger.warning("Unknown webhook format %r; sending the generic payload", webhook_format)
        builder = build_generic
    return builder(report)


def send(url: str, report: ScanReport, webhook_format: str, *, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """Post the notification. Returns True on success.

    Never raises to its caller: a failed webhook must not fail the scan that produced it. The
    scan's actual work is already committed by this point, and losing it because a Discord
    outage returned a 500 would be absurd.
    """
    if not url:
        return False
    if not report.has_news:
        logger.debug("Nothing new found; no webhook sent")
        return False

    payload = build_payload(report, webhook_format)
    try:
        response = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        logger.warning("Could not deliver the webhook: %s", exc)
        return False

    if response.status_code >= 400:
        logger.warning("Webhook rejected with %s", response.status_code)
        return False

    logger.info("Notified: %s", report.summary())
    return True
