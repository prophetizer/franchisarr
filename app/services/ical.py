"""The Upcoming page as an iCalendar feed.

Calendar apps subscribe to a URL and poll it; that is the one notification channel that needs no
webhook, no Discord, and no account -- and release dates are the one thing in this app that are
dates. Written by hand rather than with a library: the subset we need is a dozen lines of RFC
5545, and every dependency has to build for arm64 (docs/DESIGN.md challenge #20).

Each film is an all-day event on its release date, with the collection and how much of it is
owned in the description. Undated films are left out -- a calendar cannot show "some day".
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.services.upcoming_service import UpcomingFilm

PRODID = "-//Franchisarr//Upcoming//EN"


def _escape(text: str) -> str:
    """RFC 5545 3.3.11: backslash, semicolon and comma are escaped; newlines become \\n."""
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """Lines longer than 75 octets continue on the next line after a single space (3.1)."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts: list[str] = []
    while encoded:
        chunk = encoded[:75]
        # Never split inside a multi-byte character.
        while chunk and (chunk[-1] & 0xC0) == 0x80 and len(chunk) < len(encoded):
            chunk = chunk[:-1]
        parts.append(chunk.decode("utf-8"))
        encoded = encoded[len(chunk):]
        if encoded:
            encoded = b" " + encoded  # the continuation line's leading space counts
    return "\r\n".join(parts)


def _event(film: UpcomingFilm, *, stamp: str, domain: str, link: str | None) -> list[str]:
    day: date = film.release  # type: ignore[assignment]  -- callers filter undated films
    description = f"{film.collection_name} — you have {film.owned_count} of {film.total_count}."
    lines = [
        "BEGIN:VEVENT",
        f"UID:franchisarr-{film.tmdb_id}@{domain}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
        f"SUMMARY:{_escape(film.title)}",
        f"DESCRIPTION:{_escape(description)}",
        f"CATEGORIES:{_escape(film.collection_name)}",
    ]
    if link:
        lines.append(f"URL:{link}")
    lines.append("END:VEVENT")
    return lines


def calendar(films: list[UpcomingFilm], *, domain: str = "franchisarr", link_base: str | None = None,
             now: datetime | None = None) -> str:
    """The whole feed. `link_base` is the app's public collections URL, when the caller knows it."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Franchisarr — coming to franchises you own",
        "REFRESH-INTERVAL;VALUE=DURATION:P1D",
        "X-PUBLISHED-TTL:P1D",
    ]
    for film in films:
        if film.release is None:
            continue
        link = f"{link_base}/{film.collection_id}" if link_base else None
        lines.extend(_event(film, stamp=stamp, domain=domain, link=link))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
