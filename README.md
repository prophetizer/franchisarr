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

## License

[MIT](LICENSE)

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.
