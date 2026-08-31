# Franchisarr

Franchisarr looks at your Plex library and finds two things you probably want and don't have:

- **Films missing from collections you already own part of.** You have *Beverly Hills Cop* and
  *II* but not *III* — one click sends it to Radarr.
- **Spin-offs of shows you already watch.** You have *NCIS* but not *NCIS: Los Angeles* — one
  click sends it to Sonarr.

It supports multiple Radarr and Sonarr instances, signs you in with Plex, scans on a schedule,
and can shout into Discord or Slack when it finds something new. There's a web UI and a CLI.

**Status:** feature-complete and running against a real library, but not yet released. Version
`0.1.0` is the first tag.

## Quick start

```bash
git clone <this-repo>
cd franchisarr
cp .env.example .env      # at minimum: PLEX_URL, PLEX_TOKEN, TMDB_API_KEY, ADMIN_* 
docker compose up -d
```

Then open <http://localhost:8000>, sign in, choose which Plex libraries to scan, and run a scan.

You need a **TMDb API key** — the free v3 one from
[themoviedb.org/settings/api](https://www.themoviedb.org/settings/api). Note it's the *shorter*
value on that page; the v4 Read Access Token won't work, and Franchisarr will tell you so if you
paste it by mistake.

## Configuration

Everything can be set in the app's Settings page. Environment variables are a convenience for
docker-compose deployments and are only read on first boot — after that the database wins, so
changing a variable later has no effect. See [`.env.example`](.env.example) for the full list.

| Variable | Purpose |
|---|---|
| `PLEX_URL`, `PLEX_TOKEN` | Your Plex server |
| `TMDB_API_KEY` | Your own free v3 key |
| `RADARR_URL`, `RADARR_API_KEY` | Optional first Radarr; more can be added in the UI |
| `SONARR_URL`, `SONARR_API_KEY` | Optional first Sonarr |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Fallback login, created on first boot only |
| `BASE_URL` | e.g. `/franchisarr` when behind a reverse proxy subpath |
| `SCAN_SCHEDULE_CRON` | e.g. `0 3 * * *`; empty disables scheduled scans |
| `TZ` | Which timezone the schedule runs in |
| `PUID`, `PGID` | Ownership of the config volume, as in the linuxserver.io images |

### If Radarr or Sonarr sit behind a login proxy

Authelia, Authentik, Cloudflare Access and friends answer API requests with a login page, and an
API key can't get past one. Franchisarr will say so rather than blaming your API key. Either:

- point it at the internal address (`http://radarr:7878`) — put both on the same Docker network
  and use the container name; or
- add a bypass rule in the proxy for `/api` so API-key requests are let through.

## Signing in

**Sign in with Plex** is the main route — Franchisarr never sees your Plex password. Only accounts
that can actually reach *your* Plex server are admitted, so having a Plex account isn't enough;
the server's owner becomes an administrator and people you share with get ordinary accounts.

The local admin account from `ADMIN_USERNAME`/`ADMIN_PASSWORD` is the fallback for when Plex isn't
configured yet or plex.tv is unreachable.

## Command line

The CLI talks to Franchisarr's own API, so it works through `docker exec` or from anywhere that
can reach the app.

```bash
export FRANCHISARR_URL=http://localhost:8000
export FRANCHISARR_API_KEY=...          # Settings, or `cli.py api-key`
python cli.py scan movies
python cli.py gaps
python cli.py add 176 --instance 1
```

`scan movies` / `scan tv` walk your libraries; `gaps` and `spinoffs` list what's missing;
`review` shows matches that need confirming; `add`, `add-show` and `add-collection` send things to
Radarr/Sonarr; `instances` and `activity` inspect the rest.

## Theming

Franchisarr ships dark by default with a light toggle, and supports
[theme.park](https://theme-park.dev) themes: paste any theme-options stylesheet URL into Settings
and the whole UI takes it on. Off by default — when it's off, nothing is fetched from anywhere but
your own server. A self-hosted theme.park works too; it's a URL field, not a fixed list.

## Backing up

Settings has a config download. **The full one contains your Plex token and every API key in plain
text** — treat it like a password. There's a redacted download alongside it with those blanked
out; that's the one to paste into a forum thread when asking for help.

## Troubleshooting: items aren't being matched

Franchisarr can only work with a Plex item if it can resolve it to a TMDb ID. To see what your own
libraries look like:

```bash
export PLEX_URL=http://your-plex-host:32400
export PLEX_TOKEN=your-plex-token
python scripts/plex_guid_audit.py
```

It's read-only. For each library it reports how many items carry a TMDb ID, which GUID formats are
in use, and a sample of what didn't resolve. Libraries of home videos, concert rips or test clips
will legitimately show 0% — untick those in Franchisarr rather than trying to match them.

If it ends with an `UNRECOGNISED AGENTS` section, please report it: your library uses a GUID format
Franchisarr doesn't parse yet, and that section says exactly what's needed.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

Tests never touch the network — Plex, TMDb, Radarr and Sonarr are all mocked. See `docs/DEVELOPMENT.md` for
the conventions this codebase holds itself to, and `PROJECT_PLAN.md` for the design and the
28 documented technical challenges behind it.

## License

[MIT](LICENSE)

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.
