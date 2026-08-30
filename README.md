# Franchisarr

Franchisarr scans your Plex library and finds:

- **Movies missing from a collection/franchise** you already own part of (e.g. you have *Beverly
  Hills Cop* and *Beverly Hills Cop II* but not *III*) — sourced from TMDb Collections — with
  one-click add to Radarr.
- **TV spin-offs of shows you already have** that you don't own yet (e.g. you have *NCIS* but not
  *NCIS: Los Angeles*) — from a curated, user-extensible mapping — with one-click add to Sonarr.

Franchisarr is a self-hosted companion for the *arr stack: Plex + Radarr + Sonarr, with support for
multiple Radarr/Sonarr instances, Plex sign-in, scheduled scans with webhook notifications, and a
web UI plus a CLI.

**Status:** early development — not yet ready to run. This README will grow into real install docs
as Phase 1+ lands. See `PROJECT_PLAN.md` (if present in your checkout) for the full design and
build-phase plan.

## Planned quick start (not yet functional)

```bash
git clone <this-repo>
cd franchisarr
cp .env.example .env   # fill in PLEX_URL, TMDB_API_KEY, etc.
docker compose up -d
```

Then open `http://localhost:8000` (or your configured `BASE_URL`) and follow the setup wizard.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

## Troubleshooting: items aren't being matched

Franchisarr can only work with a Plex item if it can resolve that item to a TMDb ID. Plex stores
those IDs differently depending on which agent matched the item, and libraries matched by an
unusual or very old agent may not resolve.

To see exactly what your own libraries look like:

```bash
export PLEX_URL=http://your-plex-host:32400
export PLEX_TOKEN=your-plex-token
python scripts/plex_guid_audit.py
```

It reads `PLEX_URL`/`PLEX_TOKEN` from a local `.env` if they aren't already set, so an existing
docker-compose setup needs no extra configuration. The script is read-only — it writes nothing to
Plex and nothing to Franchisarr's database.

For each library it reports how many items carry a TMDb ID, which GUID formats are in use, and a
sample of items that didn't resolve. Useful options: `--library "TV Shows"` to check just one
(repeatable), and `--samples N` to change how many examples are shown.

A healthy library looks like this:

```
=== Movies  [movie]  agent=tv.plex.agents.movie
    3427 items in 27.3s
    TMDb id: 3425 (99.9%) | other id only: 1 | no id at all: 1
```

Libraries of home videos, concert rips or test clips will legitimately show 0% — nothing in them
exists on TMDb. Untick those in Franchisarr's library selection rather than trying to match them.

**If the script ends with an `UNRECOGNISED AGENTS` section, please report it** (it also exits
non-zero, so it can gate a check). That means your library uses a GUID format Franchisarr doesn't
parse yet. Include that section's output in the issue — adding support is usually a small,
contained change, and the script tells us exactly what's needed.

## License

[MIT](LICENSE)

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.
