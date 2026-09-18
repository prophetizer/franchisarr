# Franchisarr

Franchisarr looks at your Plex library and finds two things you probably want and don't have:

- **Films missing from collections you already own part of.** You have *Beverly Hills Cop* and
  *II* but not *III* — one click sends it to Radarr.
- **Spin-offs of shows you already watch.** You have *NCIS* but not *NCIS: Los Angeles* — one
  click sends it to Sonarr. Found through Wikidata, so it also knows *Family Guy* → *American
  Dad!* and *Serenity* → *Firefly*, which no name search could.

And, built on the same data: **franchise pages** that put films and TV together (*Star Trek —
you have 6 of 27*), **director pages** (*you own 11 Nolan films; missing* Following *and*
Insomnia), an **Upcoming** page of announced films in franchises you own with release-date
notifications, and **import lists** Radarr and Sonarr can poll so you never have to click Add.

It supports multiple Radarr and Sonarr instances, signs you in with Plex, scans on a schedule,
shouts into Discord or Slack when it finds something new, and has a web UI and a CLI. Everything
it hides — low-rated films, TV specials, shorts — is a preference, folded away rather than
deleted.

**Status:** pre-1.0 and in daily use against a real library of ~3,400 films and ~660 shows.
Images are published to GHCR for amd64 and arm64.

## Quick start

```bash
mkdir franchisarr && cd franchisarr
curl -fsSLO https://raw.githubusercontent.com/prophetizer/franchisarr/master/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/prophetizer/franchisarr/master/.env.example -o .env
# edit .env — at minimum: PLEX_URL, PLEX_TOKEN, TMDB_API_KEY, ADMIN_USERNAME, ADMIN_PASSWORD
docker compose up -d
```

The image is `ghcr.io/prophetizer/franchisarr` (`latest`, or a version like `0.10.0`). To build
from source instead, clone the repository and change `image:` to `build: .` in the compose file.

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
| `FANART_API_KEY` | Optional; adds franchise logos to collection headings |
| `SHOW_ARTWORK` | `false` turns off all poster and logo images |
| `RADARR_URL`, `RADARR_API_KEY` | Optional first Radarr; more can be added in the UI |
| `SONARR_URL`, `SONARR_API_KEY` | Optional first Sonarr |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Fallback login, created on first boot only |
| `BASE_URL` | e.g. `/franchisarr` when behind a reverse proxy subpath |
| `SCAN_SCHEDULE_CRON` | e.g. `0 3 * * *`; empty disables scheduled scans |
| `TZ` | Which timezone the schedule runs in |
| `PUID`, `PGID` | Ownership of the config volume, as in the linuxserver.io images |

### Spin-offs

Spin-offs of shows you own are discovered from [Wikidata](https://www.wikidata.org) during a
scan — no key or account needed — and matched on TMDb ids rather than titles, so it finds the
ones whose names give nothing away (*Family Guy* → *American Dad!*). Weaker evidence is marked
*possible*, and nothing is ever added without you clicking.

### Import lists for Radarr and Sonarr

Rather than clicking Add per film, let the *arrs pull from Franchisarr. Under **Settings →
Import lists**, generate a key; then in Radarr, *Settings → Import Lists → Add → Custom List*
and paste a films URL, for example:

```
https://franchisarr.example.com/api/lists/films.json?api_key=YOUR_KEY&min_rating=7
```

Sonarr takes the `shows` URL the same way. Radarr's own settings then decide what to monitor
and where — Franchisarr never adds anything itself. Your dismissals and preferences apply to the
lists; `min_rating` on the URL overrides the household floor for that list only.

### Artwork

Collection screens show posters from TMDb. Adding a free
[fanart.tv key](https://fanart.tv/get-an-api-key/) additionally puts the franchise wordmark over
a backdrop at the top of each collection — the only thing that key is used for.

Both are fetched by the browser from `image.tmdb.org` and `assets.fanart.tv`, so a client with no
internet access, or anyone who would rather nothing left their network, can set
`SHOW_ARTWORK=false` for a text-only interface.

### Connecting to Radarr and Sonarr

Use their address on your own network, not a public one:

```yaml
services:
  franchisarr:
    networks: [arrs]          # the network Radarr and Sonarr are already on
networks:
  arrs:
    external: true
```

```
RADARR_URL=http://radarr:7878
SONARR_URL=http://sonarr:8989
```

A public URL behind a login proxy — Authelia, Authentik, Cloudflare Access — will **not** work:
those answer API requests with a login page, and an API key can't get past one. Franchisarr says
so rather than blaming your API key. If you'd rather keep the public URL, add a bypass rule in
the proxy for `/api` so API-key requests are let through.

## Signing in

**Sign in with Plex** is the main route — Franchisarr never sees your Plex password. Only accounts
that can actually reach *your* Plex server are admitted, so having a Plex account isn't enough;
the server's owner becomes an administrator and people you share with get ordinary accounts.

The local admin account from `ADMIN_USERNAME`/`ADMIN_PASSWORD` is the fallback for when Plex isn't
configured yet or plex.tv is unreachable. It's created on **first boot only**, so changing those
variables later has no effect — if you forget the password:

```bash
docker exec -it franchisarr python scripts/reset_admin_password.py            # lists accounts
docker exec -it franchisarr python scripts/reset_admin_password.py michael    # prompts for a new one
```

If the Plex button isn't offered, Franchisarr couldn't reach your Plex server at startup — it has
to know which server it belongs to before it can check that a Plex account is allowed in. Check
`PLEX_URL`/`PLEX_TOKEN` and restart.

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

Dark by default, with a light toggle. [theme.park](https://theme-park.dev) themes are set by
environment variable, using theme.park's own names — so if your stack already sets these,
Franchisarr picks the theme up with no per-app configuration:

```yaml
environment:
  TP_THEME: nord
  TP_DOMAIN: theme-park.dev     # or your own self-hosted copy
  TP_SCHEME: https
  TP_COMMUNITY_THEME: "false"
```

`THEME_CSS_URL` overrides those with a literal stylesheet URL.

If you theme centrally by injecting a stylesheet at the proxy — nginx `sub_filter`, a Traefik
plugin, theme.park's Docker mod — that works with **nothing set here at all**. Franchisarr always
loads a small adapter mapping theme.park's custom properties onto the ones it paints with, so an
injected theme-options stylesheet takes effect on its own.

If you host your own theme.park, `contrib/theme-park/franchisarr-base.css` is a base stylesheet
ready to drop in as `css/base/franchisarr/franchisarr-base.css`. See
[`contrib/theme-park/README.md`](contrib/theme-park/README.md). It isn't in the upstream
theme.park yet.

Leave it all unset and nothing is fetched from anywhere but your own server.

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
the conventions this codebase holds itself to, and `docs/DESIGN.md` for the design and the
28 documented technical challenges behind it.

## License

[MIT](LICENSE)

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.
