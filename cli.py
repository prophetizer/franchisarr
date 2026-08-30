#!/usr/bin/env python3
"""Franchisarr command line.

A thin HTTP client against Franchisarr's own API, not a direct database caller
(PROJECT_PLAN.md decision log). Every command here goes through exactly the same endpoints the
web UI uses, so the two can't drift apart, and it works over `docker exec` or remotely.

Configure it with:

    export FRANCHISARR_URL=http://localhost:8000     # include the base URL path if you use one
    export FRANCHISARR_API_KEY=...                   # from `franchisarr api-key` or the web UI
"""

from __future__ import annotations

import os
import sys
from typing import Annotated, Any

import requests
import typer

app = typer.Typer(
    add_completion=False,
    help="Find films missing from collections you own, and spin-offs of shows you watch.",
)

DEFAULT_URL = "http://localhost:8000"
API_KEY_HEADER = "X-Api-Key"
#: A full scan walks the library and can make thousands of TMDb calls, so it needs a long rope.
SCAN_TIMEOUT = 3600


def _base_url() -> str:
    return os.environ.get("FRANCHISARR_URL", DEFAULT_URL).rstrip("/")


def _headers() -> dict[str, str]:
    api_key = os.environ.get("FRANCHISARR_API_KEY", "").strip()
    return {API_KEY_HEADER: api_key} if api_key else {}


def _call(method: str, path: str, *, timeout: int = 30, **kwargs: Any) -> Any:
    url = f"{_base_url()}{path}"
    try:
        response = requests.request(
            method, url, headers=_headers(), timeout=timeout, **kwargs
        )
    except requests.RequestException as exc:
        typer.secho(f"Could not reach Franchisarr at {url}: {exc}", fg="red", err=True)
        raise typer.Exit(2) from exc

    if response.status_code in (401, 403):
        typer.secho(
            "Not authorised. Set FRANCHISARR_API_KEY to a key generated from Settings "
            "(or `franchisarr api-key` while signed in).",
            fg="red",
            err=True,
        )
        raise typer.Exit(3)

    if response.status_code >= 400:
        detail = _detail(response)
        typer.secho(f"Request failed ({response.status_code}): {detail}", fg="red", err=True)
        raise typer.Exit(1)

    try:
        return response.json()
    except ValueError:
        typer.secho("Franchisarr returned a response that wasn't JSON.", fg="red", err=True)
        raise typer.Exit(1) from None


def _detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200] or response.reason
    if isinstance(payload, dict):
        return str(payload.get("detail") or payload.get("error") or payload)
    return str(payload)


@app.command()
def whoami() -> None:
    """Show which account the configured API key belongs to."""
    me = _call("GET", "/api/me")
    typer.echo(f"{me['username']}" + (" (admin)" if me["is_admin"] else ""))


@app.command("test-tmdb")
def test_tmdb() -> None:
    """Check that the configured TMDb API key works."""
    result = _call("GET", "/api/tmdb/test")
    if result.get("ok"):
        typer.secho("TMDb API key looks good.", fg="green")
        return
    typer.secho(result.get("error", "TMDb key check failed."), fg="red", err=True)
    raise typer.Exit(1)


scan = typer.Typer(help="Re-scan your libraries.")
app.add_typer(scan, name="scan")


@scan.command("movies")
def scan_movies(
    force: Annotated[bool, typer.Option(help="Ignore the TMDb cache and refetch everything.")] = False,
) -> None:
    """Walk the enabled movie libraries and refresh collection data."""
    typer.echo("Scanning… (this can take a few minutes on a large library)")
    result = _call("POST", "/api/scan/movies", params={"force": force}, timeout=SCAN_TIMEOUT)

    typer.echo(
        f"{result['items_seen']} items across {result['libraries_scanned']} librar"
        f"{'y' if result['libraries_scanned'] == 1 else 'ies'}"
    )
    typer.echo(f"  matched:       {result['matched']}")
    typer.echo(f"  needs review:  {result['needs_review']}")
    typer.echo(f"  unmatched:     {result['unmatched']}")
    typer.echo(f"  collections:   {result['collections_found']}")
    typer.echo(f"  TMDb lookups:  {result['tmdb_lookups']}")
    if result["removed"]:
        typer.echo(f"  removed:       {result['removed']} (no longer in Plex)")
    for error in result["errors"]:
        typer.secho(f"  ! {error}", fg="yellow", err=True)


@app.command()
def gaps(
    all: Annotated[bool, typer.Option(help="Include collections you already own in full.")] = False,
    upcoming: Annotated[
        bool, typer.Option(help="Also list announced films that aren't out yet.")
    ] = False,
) -> None:
    """List collections with films missing."""
    result = _call("GET", "/api/collections/gaps", params={"all": all})
    collections = result["collections"]

    if not collections:
        typer.echo("No gaps found. Either everything's complete, or nothing's been scanned yet.")
        return

    total_upcoming = 0
    for collection in collections:
        typer.secho(
            f"{collection['name']} "
            f"({collection['owned_count']} owned, {collection['missing_count']} missing)",
            bold=True,
        )
        for movie in collection["missing"]:
            year = f" ({movie['year']})" if movie["year"] else ""
            typer.echo(f"    {movie['title']}{year}  [tmdb:{movie['tmdb_id']}]")

        total_upcoming += collection.get("upcoming_count", 0)
        if upcoming:
            for movie in collection.get("upcoming", []):
                when = movie["release_date"] or "no date announced"
                typer.secho(f"    {movie['title']} — {when}", dim=True)

    if total_upcoming and not upcoming:
        typer.echo()
        typer.secho(
            f"{total_upcoming} announced film(s) aren't out yet — pass --upcoming to see them.",
            dim=True,
        )


@app.command()
def review() -> None:
    """Show matches that need confirming, and items nothing matched."""
    result = _call("GET", "/api/matches/review")

    if result["needs_review"]:
        typer.secho("Needs review (matched, but not confidently):", bold=True)
        for item in result["needs_review"]:
            year = f" ({item['year']})" if item["year"] else ""
            confidence = f"{item['confidence']:.0%}" if item["confidence"] else "?"
            typer.echo(f"    {item['title']}{year} -> tmdb:{item['tmdb_id']} ({confidence})")

    if result["unmatched"]:
        typer.secho("No TMDb match at all:", bold=True)
        for item in result["unmatched"]:
            year = f" ({item['year']})" if item["year"] else ""
            typer.echo(f"    {item['title']}{year}")

    if not result["needs_review"] and not result["unmatched"]:
        typer.secho("Everything matched cleanly.", fg="green")


@app.command("api-key")
def api_key() -> None:
    """Generate a new API key for this account, invalidating any previous one."""
    result = _call("POST", "/api/me/api-key")
    typer.echo(result["api_key"])
    typer.secho(result["note"], fg="yellow", err=True)


if __name__ == "__main__":
    app()
