#!/usr/bin/env python3
"""Audit a Plex library against Franchisarr's GUID parsing.

Answers the question that decides whether Franchisarr can do anything useful with a library:
how many items resolve to a TMDb ID, and which agent formats are actually in use.

Read-only. It lists libraries and walks their items; it writes nothing to Plex and nothing to the
Franchisarr database.

Run it when items aren't matching, or when adding support for an agent format. Any GUID scheme
the parser doesn't recognise is flagged, and the exit status is non-zero so this can gate a
check. Recognised-but-ID-free agents (an item Plex simply couldn't match) are not flagged --
those are a normal state, not a parser gap.

Usage:

    export PLEX_URL=http://192.168.1.10:32400
    export PLEX_TOKEN=...
    python scripts/plex_guid_audit.py

Values are read from a local `.env` file when the environment doesn't already set them, so a
working docker-compose setup needs no extra configuration.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Allows `python scripts/plex_guid_audit.py` from the repo root without installing the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.clients.plex_client import PlexClient, PlexClientError, PlexItem  # noqa: E402
from app.clients.plex_guid import is_known_scheme  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402

DEFAULT_SAMPLE_LIMIT = 12


@dataclass
class LibraryAudit:
    """What one library's items add up to."""

    total: int = 0
    with_tmdb: int = 0
    other_id_only: int = 0
    no_ids: int = 0
    schemes: Counter[str] = field(default_factory=Counter)
    unknown_schemes: Counter[str] = field(default_factory=Counter)
    examples: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    @property
    def tmdb_percent(self) -> float:
        return (self.with_tmdb / self.total * 100) if self.total else 0.0


def audit_items(items: list[PlexItem], sample_limit: int = DEFAULT_SAMPLE_LIMIT) -> LibraryAudit:
    """Summarise a library's items. Pure -- no I/O, so it is unit-testable without a server."""
    audit = LibraryAudit()

    for item in items:
        audit.total += 1

        for guid in item.guids:
            scheme = guid.split("://", 1)[0]
            audit.schemes[scheme] += 1
            if not is_known_scheme(guid):
                audit.unknown_schemes[scheme] += 1

        ids = item.external_ids
        if ids.tmdb_id:
            audit.with_tmdb += 1
            continue

        if ids.imdb_id or ids.tvdb_id or ids.anidb_id:
            audit.other_id_only += 1
        else:
            audit.no_ids += 1

        if len(audit.examples) < sample_limit:
            year = item.year if item.year is not None else "no year"
            audit.examples.append((f"{item.title} ({year})", item.guids))

    return audit


def load_env_file(path: Path) -> list[str]:
    """Seed the environment from a .env file, without overriding anything already set.

    Returns the names it supplied, so the caller can say where the configuration came from --
    values are never printed.
    """
    if not path.is_file():
        return []

    supplied = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value
            supplied.append(key)
    return supplied


def print_library(name: str, library_type: str, agent: str | None, audit: LibraryAudit,
                  elapsed: float) -> None:
    print(f"=== {name}  [{library_type}]  agent={agent}")
    print(f"    {audit.total} items in {elapsed:.1f}s")
    print(
        f"    TMDb id: {audit.with_tmdb} ({audit.tmdb_percent:.1f}%)"
        f" | other id only: {audit.other_id_only}"
        f" | no id at all: {audit.no_ids}"
    )

    if audit.schemes:
        print("    guid schemes seen:")
        for scheme, count in audit.schemes.most_common():
            flag = "   <-- UNRECOGNISED" if scheme in audit.unknown_schemes else ""
            print(f"        {scheme}: {count}{flag}")

    if audit.examples:
        print("    examples without a TMDb id:")
        for title, guids in audit.examples:
            print(f"        {title}  {list(guids)}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--library",
        action="append",
        dest="libraries",
        metavar="KEY_OR_TITLE",
        help="Limit to this library (repeatable). Default: every movie and show library.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=DEFAULT_SAMPLE_LIMIT,
        help=f"Unresolved examples to show per library (default: {DEFAULT_SAMPLE_LIMIT}).",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=REPO_ROOT / ".env",
        help="File to read PLEX_URL/PLEX_TOKEN from when not already in the environment.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=500,
        help="Items per request when walking a library (default: 500).",
    )
    args = parser.parse_args(argv)

    configure_logging("WARNING")  # surfaces unrecognised-agent warnings, hides routine chatter

    from_file = load_env_file(args.env_file)
    if from_file:
        print(f"Read {', '.join(sorted(from_file))} from {args.env_file}\n")

    url, token = os.environ.get("PLEX_URL"), os.environ.get("PLEX_TOKEN")
    if not url or not token:
        parser.error(
            "PLEX_URL and PLEX_TOKEN must be set, in the environment or in the --env-file."
        )

    client = PlexClient(url, token, page_size=args.page_size)

    try:
        print(f"Connected to: {client.test_connection()}\n")
        libraries = client.list_libraries()
    except PlexClientError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.libraries:
        wanted = {value.lower() for value in args.libraries}
        libraries = [
            lib for lib in libraries if lib.key.lower() in wanted or lib.title.lower() in wanted
        ]
        if not libraries:
            print(f"error: no library matched {args.libraries}", file=sys.stderr)
            return 2

    print(f"{len(libraries)} movie/show libraries to audit\n")

    totals = LibraryAudit()
    unknown_overall: Counter[str] = Counter()

    for library in libraries:
        lister = client.iter_movies if library.is_movie_library else client.iter_shows
        started = time.time()
        try:
            items = list(lister(library.key))
        except PlexClientError as exc:
            print(f"=== {library.title}\n    error: {exc}\n", file=sys.stderr)
            continue

        audit = audit_items(items, sample_limit=args.samples)
        print_library(library.title, library.library_type, library.agent, audit,
                      time.time() - started)

        totals.total += audit.total
        totals.with_tmdb += audit.with_tmdb
        totals.other_id_only += audit.other_id_only
        totals.no_ids += audit.no_ids
        unknown_overall.update(audit.unknown_schemes)

    print("=== TOTAL ===")
    print(
        f"    {totals.total} items"
        f" | TMDb: {totals.with_tmdb} ({totals.tmdb_percent:.1f}%)"
        f" | other id only: {totals.other_id_only}"
        f" | no id: {totals.no_ids}"
    )

    if unknown_overall:
        print("\n=== UNRECOGNISED AGENTS ===")
        print("    These GUID formats have no parser support, so their items cannot be matched.")
        print("    Please report them — each one is a small, contained fix.")
        for scheme, count in unknown_overall.most_common():
            print(f"        {scheme}: {count} items")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
