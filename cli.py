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


@scan.command("tv")
def scan_tv(
    force: Annotated[bool, typer.Option(help="Ignore the TMDb cache and refetch everything.")] = False,
) -> None:
    """Walk the enabled TV libraries and refresh show details."""
    typer.echo("Scanning TV…")
    result = _call("POST", "/api/scan/tv", params={"force": force}, timeout=SCAN_TIMEOUT)
    typer.echo(f"{result['items_seen']} shows across {result['libraries_scanned']} library(ies)")
    typer.echo(f"  matched:       {result['matched']}")
    typer.echo(f"  needs review:  {result['needs_review']}")
    typer.echo(f"  unmatched:     {result['unmatched']}")
    for error in result["errors"]:
        typer.secho(f"  ! {error}", fg="yellow", err=True)


@app.command()
def spinoffs() -> None:
    """List spin-offs of your shows that you don't have."""
    result = _call("GET", "/api/spinoffs")

    if not result["suggestions"]:
        typer.echo("No spin-offs suggested.")
        if not result["mappings"]:
            typer.secho(
                "Your mapping list is empty — it starts that way, because TMDb has no spin-off "
                "data to import. Confirm suggestions from the Spin-offs page to build it up.",
                dim=True,
            )
        return

    for suggestion in result["suggestions"]:
        year = f" ({suggestion['year']})" if suggestion["year"] else ""
        typer.echo(
            f"{suggestion['name']}{year}  [tmdb:{suggestion['tmdb_id']}]"
            f"  — spin-off of {suggestion['source_show_name']}"
        )


@app.command("map-spinoff")
def map_spinoff(
    source_tmdb_id: Annotated[int, typer.Argument(help="TMDb id of the original show.")],
    spinoff_tmdb_id: Annotated[int, typer.Argument(help="TMDb id of the spin-off.")],
) -> None:
    """Record that one show is a spin-off of another."""
    result = _call("POST", "/api/spinoffs/mappings", json={
        "source_show_tmdb_id": source_tmdb_id, "spinoff_show_tmdb_id": spinoff_tmdb_id,
    })
    if result.get("created"):
        typer.secho("Mapping saved.", fg="green")
    else:
        typer.echo(result.get("reason", "Nothing changed."))


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


instances = typer.Typer(help="Manage Radarr instances.")
app.add_typer(instances, name="instances")


@instances.command("list")
def instances_list() -> None:
    """Show configured Radarr instances."""
    result = _call("GET", "/api/instances/radarr")
    if not result["instances"]:
        typer.echo("No Radarr instances configured yet.")
        return

    for instance in result["instances"]:
        marks = []
        if instance["is_default"]:
            marks.append("default")
        if instance["preferred"]:
            marks.append("your last choice")
        suffix = f"  ({', '.join(marks)})" if marks else ""
        typer.secho(f"[{instance['id']}] {instance['name']}{suffix}", bold=True)
        typer.echo(f"      {instance['url']}")
        if instance["default_root_folder"]:
            typer.echo(f"      root folder: {instance['default_root_folder']}")


@instances.command("test")
def instances_test(instance_id: Annotated[int, typer.Argument(help="Instance id.")]) -> None:
    """Check that an instance is reachable and the API key works."""
    result = _call("GET", f"/api/instances/radarr/{instance_id}/test")
    if result.get("ok"):
        typer.secho(f"Reachable — Radarr {result['version']}", fg="green")
        return
    typer.secho(result.get("error", "Could not reach the instance."), fg="red", err=True)
    raise typer.Exit(1)


@instances.command("options")
def instances_options(instance_id: Annotated[int, typer.Argument(help="Instance id.")]) -> None:
    """List the quality profiles and root folders an instance offers."""
    result = _call("GET", f"/api/instances/radarr/{instance_id}/options")
    if not result.get("ok"):
        typer.secho(result.get("error", "Could not reach the instance."), fg="red", err=True)
        raise typer.Exit(1)

    typer.secho("Quality profiles:", bold=True)
    for profile in result["quality_profiles"]:
        default = "  (default)" if profile["id"] == result["default_quality_profile_id"] else ""
        typer.echo(f"    [{profile['id']}] {profile['name']}{default}")

    typer.secho("Root folders:", bold=True)
    for folder in result["root_folders"]:
        default = "  (default)" if folder["path"] == result["default_root_folder"] else ""
        space = f"  {folder['label']}" if folder["label"] else ""
        typer.echo(f"    {folder['path']}{space}{default}")


@instances.command("refresh")
def instances_refresh() -> None:
    """Re-read what each instance holds, so gap lists reflect it."""
    result = _call("POST", "/api/instances/radarr/refresh", timeout=300)
    for instance in result["instances"]:
        if instance["ok"]:
            typer.echo(f"{instance['name']}: {instance['movies']} films, {instance['queued']} queued")
        else:
            typer.secho(f"{instance['name']}: {instance['error']}", fg="yellow", err=True)


@app.command()
def add(
    tmdb_id: Annotated[int, typer.Argument(help="TMDb id of the film to add.")],
    instance_id: Annotated[int | None, typer.Option("--instance", help="Radarr instance id.")] = None,
    profile: Annotated[int | None, typer.Option(help="Quality profile id.")] = None,
    root_folder: Annotated[str | None, typer.Option(help="Root folder path.")] = None,
    no_search: Annotated[bool, typer.Option("--no-search", help="Add without searching now.")] = False,
) -> None:
    """Add one film to Radarr, monitored and searched immediately."""
    result = _call("POST", "/api/radarr/add", json={
        "tmdb_id": tmdb_id,
        "instance_id": instance_id,
        "quality_profile_id": profile,
        "root_folder_path": root_folder,
        "search_on_add": not no_search,
    }, timeout=120)

    searched = "searching now" if result["searched"] else "not searched"
    typer.secho(f"Added {result['title']} to {result['instance']} ({searched}).", fg="green")


@app.command("add-show")
def add_show(
    tmdb_id: Annotated[int, typer.Argument(help="TMDb id of the show to add.")],
    instance_id: Annotated[int | None, typer.Option("--instance", help="Sonarr instance id.")] = None,
    profile: Annotated[int | None, typer.Option(help="Quality profile id.")] = None,
    root_folder: Annotated[str | None, typer.Option(help="Root folder path.")] = None,
    monitor: Annotated[
        str | None,
        typer.Option(help="all | future_only | first_season. Defaults to the instance's last choice."),
    ] = None,
    no_search: Annotated[bool, typer.Option("--no-search", help="Add without searching now.")] = False,
) -> None:
    """Add one show to Sonarr."""
    result = _call("POST", "/api/sonarr/add", json={
        "tmdb_id": tmdb_id,
        "instance_id": instance_id,
        "quality_profile_id": profile,
        "root_folder_path": root_folder,
        "monitor_mode": monitor,
        "search_on_add": not no_search,
    }, timeout=180)

    searched = "searching now" if result["searched"] else "not searched"
    typer.secho(f"Added {result['title']} to {result['instance']} ({searched}).", fg="green")


@instances.command("sonarr")
def instances_sonarr() -> None:
    """Show configured Sonarr instances."""
    result = _call("GET", "/api/instances/sonarr")
    if not result["instances"]:
        typer.echo("No Sonarr instances configured yet.")
        return
    for instance in result["instances"]:
        marks = []
        if instance["is_default"]:
            marks.append("default")
        if instance["preferred"]:
            marks.append("your last choice")
        suffix = f"  ({', '.join(marks)})" if marks else ""
        typer.secho(f"[{instance['id']}] {instance['name']}{suffix}", bold=True)
        typer.echo(f"      {instance['url']}")
        typer.echo(f"      monitors: {instance['default_monitor_mode']}")


@app.command("add-collection")
def add_collection(
    collection_id: Annotated[int, typer.Argument(help="TMDb collection id.")],
    instance_id: Annotated[int | None, typer.Option("--instance", help="Radarr instance id.")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation.")] = False,
    delay: Annotated[float, typer.Option(help="Seconds between adds.")] = 2.0,
) -> None:
    """Add every missing film from one collection.

    Adds are staggered on purpose. Each one triggers an immediate search, so firing a whole
    collection at once means N simultaneous searches hitting your indexers -- which is a good way
    to get rate-limited or banned by them (technical challenge #12).
    """
    import time

    gaps = _call("GET", "/api/collections/gaps")["collections"]
    match = next((c for c in gaps if c["collection_id"] == collection_id), None)
    if match is None:
        typer.secho(f"No collection {collection_id} with missing films.", fg="red", err=True)
        raise typer.Exit(1)

    missing = match["missing"]
    typer.echo(f"{match['name']}: {len(missing)} film(s) to add")
    for movie in missing:
        typer.echo(f"    {movie['title']} ({movie['year']})")

    if not yes:
        typer.confirm(
            f"Add {len(missing)} film(s), each triggering a search?", abort=True
        )

    added = failed = 0
    for index, movie in enumerate(missing):
        if index:
            time.sleep(delay)
        try:
            _call("POST", "/api/radarr/add", json={
                "tmdb_id": movie["tmdb_id"], "instance_id": instance_id,
            }, timeout=120)
            typer.secho(f"  added {movie['title']}", fg="green")
            added += 1
        except typer.Exit:
            # _call already explained the failure; one bad film shouldn't abandon the rest.
            failed += 1

    typer.echo(f"Added {added}, failed {failed}.")


@app.command()
def activity(
    limit: Annotated[int, typer.Option(help="How many entries to show.")] = 20,
) -> None:
    """Show what Franchisarr has added."""
    result = _call("GET", "/api/activity", params={"limit": limit})
    if not result["entries"]:
        typer.echo("Nothing added yet.")
        return

    for entry in result["entries"]:
        when = entry["timestamp"][:19].replace("T", " ")
        typer.echo(f"{when}  {entry['title']}  [{entry['trigger_source']}]")
    typer.secho(result["note"], dim=True)


@app.command("api-key")
def api_key() -> None:
    """Generate a new API key for this account, invalidating any previous one."""
    result = _call("POST", "/api/me/api-key")
    typer.echo(result["api_key"])
    typer.secho(result["note"], fg="yellow", err=True)


if __name__ == "__main__":
    app()
