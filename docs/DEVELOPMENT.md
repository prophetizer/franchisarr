# Development notes

How Franchisarr is built, and the rules the code holds itself to. Read this before changing
anything that touches a route, an external API, or the database.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI |
| Data | SQLite via SQLModel, migrations via Alembic |
| Frontend | Server-rendered Jinja2 + htmx + Alpine.js + Pico.css — no build step, no npm |
| Scheduling | APScheduler, in-process |
| CLI | Typer, a thin HTTP client against the app's own API |
| Packaging | One multi-arch (amd64/arm64) image, non-root with PUID/PGID |
| Tests | pytest, external APIs mocked with `responses` |

Local setup: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`, then
`.venv/bin/pytest`. The image and CI target Python 3.12. CI also runs `pip-audit` against the
pins; a published advisory for a pinned version fails the build, so bump and re-pin.

## Conventions

Numbered because code comments cite them.

1. **Base URL.** Every route, redirect, htmx target and static link is built from the configured
   `BASE_URL`, never hardcoded to `/`. `tests/test_base_url.py` guards this; use `url()` and
   `asset()` in templates and `get_settings().base_url` in code, never a module-level constant.
2. **No live network in tests.** Plex, TMDb, Radarr, Sonarr, Wikidata and fanart.tv are always
   mocked. A test that reaches the internet is a bug.
3. **Secrets are never rendered or logged.** API keys are masked in the UI (last four
   characters), scrubbed from log output, and never echoed in error messages.
4. **Instance-aware everything.** There is never "the Radarr": there are N Radarr and N Sonarr
   instances, and any code path touching one takes an instance id.
5. **TMDb is the only required metadata source.** Wikidata and fanart.tv are enrichment; the
   app works with a TMDb key alone. No TVDb dependency.
6. **Migrations, always.** Every schema change ships with an Alembic migration.
   `tests/test_migrations.py` fails if the models drift from them. When a migration adds a
   column that existing cached rows should be refetched to fill, date those rows to the epoch.
7. **Nothing auto-adds.** Suggestions require a click; import lists are polled by the user's own
   Radarr/Sonarr under their rules. Franchisarr sends nothing to an *arr on its own.

## Things worth knowing before you touch them

- **plexapi refetches items behind your back.** Reading an attribute that came back empty on a
  listing-built object reloads it from the server. `plex_client.py` disables that; a test asserts
  a listing makes zero `/library/metadata/` calls.
- **Delete-then-insert in one flush is not ordered.** SQLAlchemy may emit the INSERTs first. To
  replace child rows, bulk `delete()` then `flush()`, and write the test with overlapping ids —
  with fresh ids it passes against the broken code.
- **A rejected TMDb key must stop every later step**, not just the one that saw the 401.
  `ScanSummary.tmdb_auth_failed` is the flag.
- **Caches hide configuration changes.** Collections, shows, franchises and filmographies are
  cached for a TTL. "Refresh everything" (`force_refresh`) bypasses it and must stay reachable
  from the UI.
- **Never a colour literal in `app.css`.** Every colour is a Pico variable so a theme.park
  stylesheet can repaint the UI. `tests/test_theming.py` enforces it.
- **Static assets are versioned** (`?v=<version>`); pages are `Cache-Control: no-cache`. Use
  `asset()` for anything under `/static/`.
- **Check layout at phone width.** The test suite cannot see layout. Two Pico defaults have bitten:
  `nav ul` never wraps, and `aria-busy` brings `white-space: nowrap`.
- **Wikidata:** no `UNION` in a query with a `VALUES` batch (it times out where the two halves
  alone take a tenth of a second); use direct `wdt:P31` rather than the `P279*` walk in bulk
  queries; the label service returns one row per class of an entity, so dedupe by entity before
  counting. The client documents which properties are used and why.
- **Never look things up per row inside a read-time service.** Build the lookup once per call.
- **A paged list and its heading count different things.** `pagination.paginate()` slices what
  the grid renders; the counts in the heading ("1,103 collections, missing 2,208 films") describe
  the whole library and must be taken before the slice, or they silently become "120". Pagers
  below the 250-item threshold render nothing at all, so a normal library sees no change — which
  also means a bug up here only shows on a big one. Two pagers on one page need different
  `page_param`s.
- **Select columns, not rows, when you only need values; let loop locals die.** A dict of
  `LibraryItem` rows that outlived its loop kept 20,000 objects in the session, and every later
  commit expired them all — the scan went O(n²). Materialising 25,000 ORM objects to read two
  columns of each is most of a page. `python scripts/loadtest.py --films 20000 --shows 2000`
  (no network; every client faked) is the check after touching a scan step or a read-time
  service — the 0.20.0 changelog has the numbers to beat.
- **Wait a few seconds between pushing a tag and creating its release.** A release created in the
  same instant as the tag push has been stamped with the epoch and sorted last.

## Media servers

`app/clients/media_server.py` is the boundary: four methods and two neutral item types, and
nothing downstream knows which server it is talking to. `PlexClient` and `EmbyLikeClient`
(Jellyfin and Emby, one client, `kind` is configuration) implement it;
servers are rows in `media_servers`, and `media_server_service.client_for(server)` builds the
client for one. There is never "the media server": the scan takes a list of `ScanSource`s and
every `IncludedLibrary` and `LibraryItem` carries a `server_id`. Ownership is a set of TMDb ids,
so a film on two servers is owned once; `ownership_service` adds which servers hold it and whether
it was watched on any. Sign-in: Plex by PIN with a server-access check against every known Plex
row (owning any of them administers); Jellyfin/Emby by the person's own username and password
against the server they pick, which is the same authorisation in different clothes. Watched state
is per account, and an API key is nobody's, so a Jellyfin/Emby row names a `watched_user`
(default: the first administrator); Plex reports the token owner's. Measured before building: both of the developer's servers carry a TMDb id on
99.7–100% of items, so matching is id-first with the IMDb `/find` fallback for the rest.

## Optional data sources

- **fanart.tv** (`FANART_API_KEY`): franchise wordmarks for collection headings. Measured as
  having no poster TMDb lacks, so it is never used for posters.
- **Wikidata** (no key): spin-offs, continuations across media, franchise membership. Batched,
  rate-limited, and sent with an identifying User-Agent as its operators ask.
