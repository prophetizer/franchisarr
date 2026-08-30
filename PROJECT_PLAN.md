# Franchisarr — Project Plan

A self-hosted *arr-stack companion app: scans your Plex library, finds movies missing from franchise/collections and TV spin-offs you don't have, and lets you add them to Radarr/Sonarr in one click. Built to be shared publicly with the *arr community, not just for personal use.

## Decisions log

| Area | Decision |
|---|---|
| Media server | Plex only for v1 (adapter pattern so Emby/Jellyfin can be added later) |
| Movie collection source | TMDb Collections (e.g. "Beverly Hills Cop Collection") as source of truth |
| TV spin-off source | Curated JSON mapping (`spinoffs.json`), **starts empty** — grows from real use via a UI action, no upfront seed/research pass. Built on **TMDb only** (see TVDb row below) |
| Interface | CLI (scanning/scheduled runs) + local web UI (browse results, one-click add) |
| Frontend stack | htmx + Jinja2 templates + Alpine.js (small client-side bits) + Pico.css. Server-rendered, no build step, no npm |
| Backend stack | Python (FastAPI), single Docker container |
| Storage | SQLite — scan cache, TMDb lookups, dismissed items, settings, instance configs |
| "Already queued in Radarr/Sonarr" = not missing | **Per-user settings toggle**, not a fixed rule |
| Radarr/Sonarr instances | **Multiple instances supported** (e.g. 4K + 1080p Radarr) from v1 |
| Instance routing on "Add" | Dropdown at add-time, defaulting to a marked default instance — not fully automatic |
| Auth | **Plex OAuth primary** ("Sign in with Plex," like Overseerr), **local admin account as fallback/recovery** |
| Connection setup | **Both**: env vars for bootstrap/docker-compose, plus an in-app setup wizard + settings UI for changes afterward |
| License | MIT |
| Name | **Franchisarr** |
| Hosting during development | Private Forgejo repo now; migrate to GitHub when ready to share publicly |
| Library size (yours, for testing) | ~3,600 movies, ~16,000 TV episodes (a few hundred shows) — needs batching/caching, not huge-scale |
| Base URL / reverse proxy | Configurable base URL (e.g. `/franchisarr`) supported from v1, like Radarr/Sonarr's own `URL_BASE` |
| Scheduled scans | Built into v1 — configurable cron-style schedule, plus optional outgoing webhook (Discord/Slack/generic) when a scan finds new gaps/spin-offs |
| Spin-off dataset sharing | Schema designed now for a future community-shared/synced dataset; the sync mechanism itself is **not** built in v1 |
| DB / ORM | SQLModel + Alembic — typed models double as API schemas, Alembic gives versioned migrations for other people's databases |
| TMDb API key | **Each user brings their own** (free, instant signup) — no bundled/shared key, avoids cross-install rate-limit contention and TMDb ToS issues with redistributing a key |
| Add-to-Radarr/Sonarr default | **Monitored + search immediately** on add — matches manually adding through Radarr/Sonarr's own UI with "search on add" checked |
| Health checks & logging | **Yes** — `/health` endpoint for Docker `HEALTHCHECK`/reverse-proxy monitoring, plus structured (leveled, timestamped) logs to stdout |
| Collection data quirks (re-releases, director's cuts, etc.) | **Per-collection exclude**, separate from the global per-user dismiss list — scoped to just that one collection view |
| Quality profile / root folder dropdowns | **Fetched live** from the target instance's API at add-time, pre-selected to your saved default, changeable per-add |
| Fuzzy TMDb matching (no TMDb ID on the Plex item) | **Confidence-tiered**: strong title+year match auto-used; weak matches surface a "confirm the right title?" prompt instead of guessing |
| Cross-instance "already have it" (e.g. 4K vs. 1080p Radarr) | **Instances independent by default**, with a **settings toggle** to treat "in any instance" as not-missing, for setups that split by content type rather than quality tier |
| Testing / CI | **Pytest with mocked external APIs** (no live network calls in CI); CI runs the suite on every push |
| Plex library scope | **User selects which libraries to include** (checkboxes in setup/settings), not an automatic "every movie/TV library" scan |
| TVDb dependency | **TMDb only for v1** — TVDb's paywalled v4 API isn't required to ship; schema/clients kept swappable so an optional TVDb key can be added later |
| UI theme | **Dark by default** (matches Radarr/Sonarr/Overseerr's own look), with Pico's light theme available as a toggle |
| Self-update checks | **Yes** — a scheduled check against the repo's latest release tag shows an "update available" banner; no auto-update |
| Docker architecture | **Multi-arch (amd64 + arm64)** via Buildx in CI from v1 — covers Raspberry Pi/ARM NAS/Apple Silicon hosts common in this community |
| Container user | **Non-root, with PUID/PGID env vars** (linuxserver.io convention) — matches Radarr/Sonarr/Plex's own containers, avoids config-volume permission headaches |
| Sonarr season monitoring on add | **Asked each time** via a monitor-mode dropdown (All / Future Only / First Season) alongside quality profile and root folder, remembered as the next default |
| CLI architecture | **CLI is a thin HTTP client** against the app's own local API (`http://localhost:PORT/api/...`), not a direct DB/service caller — same code path as the web UI, usable via `docker exec` or (with an API key) remotely later |
| Activity/audit log | **Yes** — a UI page logging every add (what, when, which instance, which user/trigger: manual or scheduled scan) |
| Versioning/changelog | **SemVer tags + a maintained `CHANGELOG.md`** in Keep a Changelog format — gives the update-checker something meaningful to compare against |
| Security policy | **Yes** — a basic `SECURITY.md` (supported versions, private vulnerability-reporting process) added now, not deferred to the GitHub migration |
| Config export/import | **Yes** — a Settings "download config backup" (JSON) / import pair, in addition to (not instead of) documenting direct SQLite file backup |
| Schema migration timing | **Applied automatically at app startup**, not left to the operator — the app is upgraded by pulling a new image tag, so an install that needs a manual `alembic upgrade` is an install that breaks (added Phase 1) |
| Constrained columns | Stored as **plain VARCHAR with `str` enums in Python**, not `sa.Enum`. SQLite has no native enum and `sa.Enum` emits a CHECK constraint, which would turn "accept one more value" into a table-rebuild migration on other people's databases (added Phase 1) |
| Front-end assets | **Vendored into `app/static/` at pinned versions with recorded checksums**, never CDN-linked — a self-hosted app on a home network must render without outbound internet access (added Phase 1) |
| theme.park themes | **Supported via an optional stylesheet-URL setting, default off** — the *arr community's theming convention, and theme.park's `theme-options/*.css` files are app-agnostic variable blocks, so mapping them onto Pico's `--pico-*` variables makes every theme work without upstream involvement. A `franchisarr-base.css` contributed upstream is a nice-to-have after public release, not a prerequisite. The one deliberate exception to the vendored-assets rule above: opt-in, self-host-friendly (URL, not a fixed host), and clearly labelled as a third-party fetch (requested 2026-08-30; scheduled for Phase 5 so the movie UI is themeable from its first screen) |

## 1. What the app does

**Movies:** For every movie in your Plex library, resolve its TMDb ID, check whether it belongs to a TMDb Collection, and if so, fetch the full list of movies in that collection. Diff against your Plex library (and, per your settings toggle — either per-instance or "any instance counts" — what's already queued in Radarr) to produce a "missing from this collection" list. Each missing item gets an "Add" button — pick a Radarr instance, then quality profile and root folder dropdowns populate live from that instance's own API (pre-selected to your last choice) — and it's sent via the Radarr API.

**TV:** For every show in your library, resolve its TMDb ID and check the curated spin-off mapping (plus optional lower-confidence heuristic candidates) for shows you don't have. Diff against your library and Sonarr, offer one-click add to a chosen Sonarr instance — the add dialog includes a season-monitoring dropdown (All / Future Only / First Season) alongside instance, quality profile, and root folder, remembering your last choice.

**Both:** results are cached in SQLite so re-scanning is fast; you can dismiss/ignore a suggestion so it stops showing up; everything is scoped per logged-in user's own dismiss/ignore list, but Radarr/Sonarr instance configs and the spin-off mapping are shared/global (single-household tool, not fully multi-tenant). Adding something sends it to Radarr/Sonarr as **monitored, with an immediate search triggered** — same as manually adding through Radarr/Sonarr's own UI with "search on add" checked. Within a single collection's gap view, an item can also be marked "not part of my collection" (e.g. a re-release, a director's cut TMDb lists as a separate movie) — this hides it from that one collection's missing-list without touching your broader per-user dismiss list, since it's really a data-quality correction, not a personal preference.

## 2. Why TMDb collections/spin-offs need care

- TMDb's "Collection" object is reliable for franchises like Beverly Hills Cop — every movie has a `belongs_to_collection` field. Solid, low-effort win for the movie side.
- TMDb has **no built-in "spin-off" relation** for TV — no clean field to walk. So TV spin-off detection is a hybrid: a maintained JSON file (`spinoffs.json`) mapping known franchises (NCIS → NCIS: LA/NOLA/Hawaii/Sydney, Chicago Fire → Chicago P.D./Med, etc.), which starts **empty** and grows as users (starting with you) add mappings from a show's detail page — plus optional heuristics (keyword/network/cast overlap from TMDb credits) that surface only as a clearly separate, lower-confidence "possible spin-off, confirm?" tier. Nothing in that tier is ever auto-added.
- TVDb often has cleaner TV metadata (including some show-relation data) than TMDb, but its v4 API now sits behind a paid subscription tier for meaningful use, which would force every Franchisarr user to go get and pay for a second API key just to unlock TV features. v1 stays TMDb-only for both movies and TV; the `tmdb_client.py`/matcher boundary is kept clean enough that an optional `tvdb_client.py` could be added later purely as an enrichment layer for users willing to bring that key, without restructuring the diff logic.
- Because this ships to other people's libraries, the spin-off mapping's DB schema is designed now for an eventual **community-shared, versioned dataset**: each mapping row carries `source` (`local` | `community`), `confidence` (`confirmed` | `heuristic`), and `origin_ref` (nullable — e.g. a future upstream ID) fields from day one, even though v1 only ever writes `source=local`. This means adding a "sync from the project's shared list" feature later is a new service that populates existing columns, not a schema migration plus a rewrite of every place that reads a mapping.

## 3. High-level architecture

**Single Docker container**, served behind a reverse proxy at a configurable base path (e.g. `https://host/franchisarr/`) — routes, redirects, and static asset links are generated relative to a `BASE_URL` setting rather than hardcoded to root.

- **Web UI** (htmx + Jinja2 + Alpine + Pico, dark theme by default) and **CLI** (Typer/Click, a thin HTTP client against this same API — not a direct DB caller) both talk to the same **FastAPI backend**, which exposes: `/health` (liveness, unauthenticated), `/auth/plex/*` (OAuth login), `/api/libraries` (list + toggle included Plex libraries), `/api/scan/{movies|tv}`, `/api/collections/{id}/gaps`, `/api/collections/{id}/exclude/{tmdb_id}`, `/api/spinoffs/{show}`, `/api/instances/{radarr|sonarr}`, `/api/radarr/{instance_id}/add`, `/api/sonarr/{instance_id}/add` (accepts a `monitor_mode`), `/api/activity` (audit log), `/api/settings/export`, `/api/settings/import`, `/api/settings`, `/api/version` (current version + latest known release, backing the update-available banner).
- **Scheduler** (APScheduler running inside the same process) triggers scan jobs on a configurable cron-style schedule, a periodic release-check job for the update banner, and, when new gaps/spin-offs are found, hands off to a **webhook notifier** (generic POST, with presets for Discord/Slack payload shapes).
- **SQLite (`app.db`)**, via SQLModel + Alembic migrations, holds: library snapshot, TMDb lookup cache, dismissed items, users (Plex + local admin), `radarr_instances[]`, `sonarr_instances[]`, and settings (including `base_url`, `webhook_url`, and the scan schedule).
- External calls out to: the Plex API (library scan), plex.tv (OAuth), the TMDb API (collections/shows), and the Radarr/Sonarr APIs (one call set per configured instance).

## 4. Project structure (proposed)

```
franchisarr/
├── app/
│   ├── main.py                    # FastAPI app, mounts routes + static UI, /health endpoint
│   ├── config.py                   # env-based bootstrap settings (fallback/first-run only), incl. BASE_URL
│   ├── logging_config.py            # structured (leveled, timestamped, stdout) logging setup, secret redaction
│   ├── db.py                       # engine/session factory, DB_PATH resolution, migrate-on-startup
│   ├── templating.py                # Jinja2 env + the BASE_URL-aware url() global
│   ├── models.py                   # SQLModel table definitions
│   ├── migrations/                 # Alembic env + versioned migration scripts
│   ├── auth/
│   │   ├── plex_oauth.py            # plex.tv PIN-based OAuth flow, session handling
│   │   └── local_admin.py           # fallback local admin login (bcrypt-hashed password)
│   ├── clients/
│   │   ├── plex_guid.py             # Plex GUID -> external ID parsing (both agent generations), I/O-free
│   │   ├── plex_client.py           # plexapi wrapper: list movies/shows, get GUIDs
│   │   ├── tmdb_client.py           # TMDb wrapper: collection lookup, show details, rate-limited
│   │   ├── radarr_client.py         # Radarr v3 API, instance-aware
│   │   └── sonarr_client.py         # Sonarr v3 API, instance-aware
│   ├── services/
│   │   ├── movie_gap_service.py     # core diff logic for collections
│   │   ├── tv_spinoff_service.py    # core diff logic for spin-offs
│   │   ├── matcher.py                # Plex item -> TMDb ID resolution (via GUIDs/agents)
│   │   ├── instance_router.py        # resolves default/chosen Radarr/Sonarr instance for an add
│   │   ├── scheduler.py               # APScheduler setup, reads schedule from settings
│   │   ├── notifier.py                # webhook dispatch (generic/Discord/Slack payload shapes)
│   │   ├── library_service.py          # list/toggle included Plex libraries
│   │   ├── update_checker.py           # polls repo release API, feeds /api/version + UI banner
│   │   ├── activity_log.py             # records every add (what/when/instance/user/trigger)
│   │   └── config_backup.py            # settings/instances/spinoff_mappings JSON export + import
│   ├── data/
│   │   └── spinoffs.schema.json      # documents the mapping schema (incl. source/confidence/origin_ref
│   │                                  # fields reserved for a future community-sync feature)
│   ├── templates/                   # Jinja2 templates + htmx partials
│   └── static/
│       ├── htmx.min.js
│       ├── alpine.min.js
│       ├── app.css                   # Franchisarr's own styles, layered on Pico
│       ├── VENDOR.md                 # pinned versions, licences and checksums of the vendored assets
│       └── pico.min.css              # configured for dark-by-default via data-theme, light toggle available
├── cli.py                          # Typer CLI: thin HTTP client against the app's own API (`scan movies`,
│                                    # `scan tv`, `add radarr <id> --instance X`, needs an API key/local access)
├── tests/
│   ├── fixtures/                   # recorded Plex/TMDb/Radarr/Sonarr response fixtures
│   ├── test_matcher.py              # fuzzy-match confidence threshold cases
│   ├── test_movie_gap_service.py
│   ├── test_tv_spinoff_service.py
│   └── test_auth.py
├── .forgejo/workflows/ci.yml        # pytest on every push + multi-arch (amd64/arm64) Buildx image build;
│                                    # swap to .github/workflows at GitHub migration
├── Dockerfile                       # non-root, PUID/PGID entrypoint (linuxserver.io-style s6/entrypoint script)
├── docker-compose.yml
├── .env.example                    # bootstrap-only env vars (see below)
├── alembic.ini                      # migration tooling config (the app builds its own at runtime)
├── requirements.txt                 # incl. sqlmodel, alembic, apscheduler
├── LICENSE                          # MIT
├── SECURITY.md                       # supported versions + private vulnerability-reporting process
├── CHANGELOG.md                      # Keep a Changelog format, updated per SemVer-tagged release
└── README.md
```

## 5. Multi-instance & auth data model

- **`radarr_instances` / `sonarr_instances` tables:** `id`, `name` (e.g. "4K Radarr"), `url`, `api_key`, `default_root_folder`, `default_quality_profile_id`, `is_default` (bool), `hide_if_queued` (bool, per-instance override of the global toggle). Root folder/quality profile *options* shown at add-time are fetched live from each instance's API, not stored — only the *default selection* is persisted here. `sonarr_instances` additionally has `default_monitor_mode` (`all`|`future_only`|`first_season`) as the add-dialog dropdown's pre-selection.
- **`users` table addition:** `api_key` (nullable, generated on request from Settings) — lets the CLI (and any future remote/API use) authenticate to the app's own HTTP API without a browser session.
- **`settings` table addition:** `cross_instance_dedup` (bool, default off) — when on, a movie/show present in *any* configured instance of that type counts as "already have it" everywhere, instead of each instance's gap list being independent.
- **`users` table:** `id`, `plex_user_id` (nullable), `plex_username` (nullable), `local_username` (nullable, only for the fallback admin), `password_hash` (nullable), `is_admin`. A Plex-authenticated user is auto-provisioned on first login if their Plex account has access to the configured Plex server (checked via Plex's shared-server API, so randos with a Plex account can't log in to your instance).
- **`dismissed_items` table:** scoped by `user_id` so each person's ignore list is their own; instance configs and spin-off mappings remain shared/global.
- **`spinoff_mappings` table:** `id`, `source_show_tmdb_id`, `spinoff_show_tmdb_id`, `source` (`local`|`community`), `confidence` (`confirmed`|`heuristic`), `origin_ref` (nullable), `added_by_user_id`. v1 only ever writes `source=local`; the other values exist so a future sync feature is additive.
- **`settings` table:** key/value, includes `base_url`, `webhook_url`, `webhook_format` (`generic`|`discord`|`slack`), `scan_schedule_cron`, `tmdb_cache_ttl_days`, and `tmdb_api_key` — entered once per install during setup (like the Radarr/Sonarr API keys, not per individual logged-in user), since the scan cache and TMDb lookups are shared across everyone using that install.
- **`collection_excludes` table:** `id`, `tmdb_collection_id`, `tmdb_movie_id`, `added_by_user_id`. Scoped to one collection, distinct from `dismissed_items` — corrects TMDb data quirks (re-releases, director's cuts counted as separate movies) rather than expressing "I don't want this."
- **`included_libraries` table:** `id`, `plex_library_key`, `plex_library_name`, `library_type` (`movie`|`show`), `enabled` (bool). Populated from Plex's own library list on connect; only `enabled` libraries are included in scans — lets you exclude a "Home Videos" or kids-only library from gap scanning.
- **`activity_log` table:** `id`, `timestamp`, `item_type` (`movie`|`show`), `tmdb_id`, `title`, `instance_id`, `triggered_by` (`user_id` nullable, null when the trigger was a scheduled scan), `trigger_source` (`manual`|`scheduled`). Append-only; the UI's Activity page just paginates it. Export/import (`config_backup.py`) covers instances, settings, spinoff_mappings, collection_excludes, and included_libraries — **not** the activity log or the scan cache itself, since those are re-derivable/local-history rather than configuration.

## 6. Setup flow (env vars + wizard, both)

- **Bootstrap via env vars** (for docker-compose/Unraid-style deployment): `PLEX_URL`, `PLEX_CLIENT_ID` (for OAuth), `TMDB_API_KEY`, plus optionally `RADARR_URL`/`RADARR_API_KEY` and `SONARR_URL`/`SONARR_API_KEY` for a single default instance. These seed the DB on first boot if the tables are empty — they're a convenience, not the only path.
- **In-app setup wizard** on first run (no env vars set, or user visits `/setup`): walks through Plex server connection + OAuth app registration, a TMDb API key field with a link to https://www.themoviedb.org/settings/api and a short "why do I need my own key" note, then add-an-instance forms for Radarr/Sonarr (repeatable, "Add another instance"), each with a "Test Connection" button before saving.
- **Settings UI** after initial setup: add/edit/remove instances, edit the global/per-instance "hide if queued" toggle, manage users, TMDb cache TTL.

## 7. Key technical challenges to solve early

1. **Plex → TMDb ID matching.** Plex stores external IDs in `guid`/`Guid` fields (format differs: new Plex agent vs. legacy). Need a robust resolver with a title+year fuzzy-match fallback against TMDb search. *(Phase 1: implemented in `plex_guid.py` and validated against a real 4,318-item server. Both agent generations coexist on one server, including two spellings of "unmatched" — legacy `com.plexapp.agents.none` and new `tv.plex.agents.none` — so both must be recognised as legitimately ID-free.)*
2. **Plex OAuth flow.** Uses plex.tv's PIN-based auth (`https://plex.tv/api/v2/pins`), then verifying the returned auth token actually has access to the specific Plex server this instance is configured for (via `https://plex.tv/api/v2/shared_servers` or `/api/resources`) — otherwise anyone with a Plex account could log in. *(Phase 2: implemented via `/api/v2/resources`, filtered to entries that `provide` a server. The check fails closed — an unknown machine identifier refuses sign-in rather than assuming it, and the button is hidden until the Plex connection has been made. The same response's `owned` flag decides who gets admin, so the server owner administers the install and a shared user does not.)*
3. **Multi-instance routing.** The add-dialog dropdown needs to show instance name + a hint (e.g. "4K Radarr — /movies-4k") so it's obvious which is which; remember the last-used instance per user as the default pre-selection, not just a global default.
4. **Rate limiting.** TMDb allows ~40–50 req/s in practice; cache aggressively (collection/show data rarely changes), TTL-based refresh (configurable, default ~7 days).
5. **Radarr/Sonarr "already have it" check.** Per-instance `hide_if_queued` toggle, applied at diff time — checked against every configured instance, not just the default.
6. **Confidence tiers for spin-offs.** Curated mapping = confident, normal suggestion. Heuristic-matched = separate "possible spin-off, confirm?" section, never auto-addable without an explicit click, and clicking it prompts "save this as a confirmed mapping?" to grow the curated list.
7. **Incremental scans.** Avoid full rescans on every page load — scan on demand or on a schedule (cron inside the container), serve from cache otherwise. Matters more here since a public tool will run on libraries much larger than yours.
8. **Secrets handling.** Radarr/Sonarr API keys and the Plex OAuth client secret must never be rendered into HTML/logs; mask them in the settings UI (show last 4 chars only, require re-entry to change).
9. **Scheduled scans + webhooks.** APScheduler running a background job inside the same process (no separate worker container needed at this scale); the job reuses the same diff services as a manual scan. On completion, if new (non-dismissed) items were found since the last run, `notifier.py` posts to the configured webhook URL — with a `webhook_format` setting choosing between a plain generic JSON payload and pre-shaped Discord/Slack embed formats, since those two are the most common in the *arr community.
10. **Base URL correctness.** Every internal link, htmx `hx-get`/`hx-post` target, redirect, and static asset reference must be built from the configured `base_url` rather than assumed to be `/` — worth a small test that boots the app with a non-root base URL and checks nothing 404s, since this is an easy thing to regress on a later PR.
11. **Per-user TMDb key validation.** The setup wizard's "Test Connection" for TMDb should catch the common failure modes early: a v4 read-access token pasted where a v3 key is expected, an unactivated new account (TMDb sometimes has a short delay before a fresh key works), or a key that's valid but rate-limited from a prior burst.
12. **Add-on-add vs. bulk adds.** "Search immediately" is the right default for a single click, but adding an entire collection's worth of missing movies at once (a "add all missing" bulk action) means N simultaneous searches hitting your indexers — worth throttling bulk adds (e.g. staggered, or a confirmation showing the count first) even though a single add fires right away.
13. **Collection excludes vs. re-scans.** A `collection_excludes` row needs to survive a TMDb cache refresh — if the collection's movie list is re-fetched and the excluded TMDb ID is still present, it must still be filtered out, not just filtered out of that one scan's transient results.
14. **Fuzzy-match confidence threshold.** Needs an actual defined bar (e.g. normalized title similarity above X% AND year exact-or-±1) rather than a vague notion of "strong match" — worth tuning against real mismatched-title cases in your own library (anthology re-releases, alternate international titles) during Phase 3, and surfacing anything below the bar in a small "needs review" list rather than silently skipping it. *(Phase 1 measurement, real library: 3,425 of 3,427 movies and 656 of 656 shows already carry a TMDb ID directly. Exactly one movie had an IMDb ID but no TMDb ID, and one had no IDs at all. The fuzzy-match path is therefore a rare fallback rather than a hot path — an IMDb→TMDb lookup covers more of the real gap than title+year matching does, and this challenge is lower-risk than assumed. Junk libraries — calibration clips, concert rips, DJ sets — account for all 236 remaining unresolved items and are excluded via `included_libraries` rather than matched.)*
15. **Live profile/folder fetch failure handling.** If a Radarr/Sonarr instance is unreachable when the add-dialog opens, the dropdown fetch fails — show a clear "can't reach this instance right now" state rather than an empty/broken dropdown, and don't let the add button submit with no profile selected.
16. **Mocking three different external APIs for tests.** Plex, TMDb, and Radarr/Sonarr each need recorded fixture responses (e.g. via `responses` or VCR-style cassettes) covering the tricky cases already listed above (missing TMDb ID, ambiguous collection matches, instance unreachable) so the test suite actually exercises the edge cases, not just the happy path.
17. **Library selection UX.** The setup wizard needs to call Plex's library list endpoint and distinguish movie vs. show libraries so the checkboxes group sensibly; changing which libraries are enabled after initial setup should trigger a rescan (or at least invalidate the cached "existing in library" set) rather than silently going stale.
18. **Update check without leaking install details.** The release-check call should hit the repo's public release API (no telemetry about the user's own library/config) and fail silently/log-only if the repo is unreachable (private Forgejo instance, offline host, etc.) — never block app startup or normal use on this check succeeding.
19. **PUID/PGID entrypoint.** The container starts as root just long enough to `chown` the mounted config/DB volume to the requested PUID/PGID, then drops to that user before running the app (standard linuxserver.io pattern) — needs a small shell entrypoint script, not just a Dockerfile `USER` directive, since the UID is only known at container start, not build time.
20. **Multi-arch build correctness.** Any Python dependency with C extensions (e.g. bcrypt, sqlite bindings) needs to actually have arm64 wheels available or build cleanly under QEMU emulation in CI — worth a quick dependency audit before assuming Buildx "just works," since a missing arm64 wheel silently falls back to a slow source build or fails outright.
21. **CLI auth.** Since the CLI is an HTTP client rather than in-process, it needs its own credential — a per-user API key (generated in Settings) sent as a header, separate from the browser session cookie used by the web UI, so `docker exec franchisarr cli.py scan movies` doesn't require a logged-in browser session to exist.
22. **Monitor-mode mapping to Sonarr's actual API.** Sonarr's `addOptions.monitor` field has specific accepted values that don't map 1:1 to a friendly "All/Future Only/First Season" UI — worth confirming Sonarr's current v3 API enum values during Phase 6/7 rather than assuming the UI labels translate directly.
23. **Config export secrets handling.** A config-backup JSON necessarily includes Radarr/Sonarr API keys and the TMDb key to be actually restorable — needs a clear on-screen warning that the exported file is sensitive (treat like a password), and import should validate the file's shape before touching the DB rather than trusting it blindly.
24. **Activity log vs. Radarr/Sonarr's own history.** The log only records the *add* action Franchisarr took (not download/import status, which stays Radarr/Sonarr's job) — worth a one-line UI note pointing at the instance's own history for what happened after the add, so the activity page doesn't imply it's tracking download progress it isn't.
25. **plexapi's implicit per-item metadata refetch.** *(found in Phase 1, resolved)* plexapi reloads an entire object from the server whenever an attribute reads back as `None` or `[]` on an object built from a listing — and it does this from inside its own `_loadData`, so it cannot be avoided by being careful about which attributes are touched. A movie with no year, or a show whose listing omits `childCount`, silently becomes its own HTTP request: a 3,600-movie scan would have made thousands of requests instead of a handful. `plex_client.py` disables the behaviour via plexapi's own config flag before the server object is constructed, and a regression test asserts that listing a library makes zero `/library/metadata/` calls. Anything genuinely needing full metadata must call `fetch_external_ids()` explicitly, so the request is a decision rather than a side effect — relevant to the Phase 3 matcher's fallback path for servers whose listings omit `<Guid>` children.
26. **Unreleased films in TMDb collections.** *(found in Phase 3, resolved)* TMDb collections include announced sequels that do not exist yet, and there are far more than you would guess. On a real 3,428-film library, 155 of 382 reported gaps had a future release date or no release date at all, and 126 of 239 collections with "gaps" had no released film missing whatsoever — so over half the list was noise, including entries like "Untitled Beetlejuice 3". `movie_gap_service` now splits these into a separate `upcoming` bucket that does not drive the has-gaps signal. They are deliberately not discarded: adding one to Radarr is sensible, since Radarr monitors and grabs on release. Phase 5's UI should present them as a clearly secondary "coming soon" section, not mixed into the actionable list.

## 8. Suggested build phases

1. **Phase 0 — CI + repo hygiene skeleton — ✅ COMPLETE (CI green on Forgejo):** Forgejo Actions workflow that installs deps and runs `pytest` (empty suite passes trivially at first), a multi-arch (amd64/arm64) Buildx image-build job with a quick dependency audit for arm64 wheel availability, plus `LICENSE`, `SECURITY.md`, and an empty `CHANGELOG.md` (Keep a Changelog format) committed from the start — set up before real code lands so every subsequent phase is covered from its first commit, not bolted on at the end.
2. **Phase 1 — Foundations — ✅ COMPLETE:** SQLModel schema + first Alembic migration (users incl. `api_key`, instances, settings, spinoff_mappings, collection_excludes, included_libraries), env-var bootstrap incl. `BASE_URL`, structured logging setup, `/health` endpoint, Plex client (list libraries, movies/shows) with fixture-backed tests, dark-by-default Pico theme wired into the base template, Docker skeleton with PUID/PGID entrypoint that runs and connects to Plex.
3. **Phase 2 — Auth — ✅ COMPLETE:** Plex OAuth login flow + local admin fallback, session handling, library-selection step (checkboxes) in the post-login/setup flow, basic "logged in" shell UI, confirm the app works correctly when `BASE_URL` is set to a subpath, tests for the OAuth token/server-access check.
4. **Phase 3 — Movie collections — ✅ COMPLETE (validated against a real 3,428-film library):** TMDb client, Plex→TMDb matcher with a defined fuzzy-match confidence threshold (tested against real mismatch cases from your library), collection-gap diff logic. Establish the CLI-as-HTTP-client pattern here (API key auth, `cli.py scan movies` hitting `/api/scan/movies`) since every later CLI command follows the same shape. Validate against your library before building UI.
5. **Phase 4 — Radarr integration + multi-instance:** Radarr client (incl. live profile/root-folder fetch with an unreachable-instance failure state), instance CRUD + setup wizard step, cross-instance dedup toggle, "add missing movie" (monitored + search-on-add) with instance dropdown, wired into web UI, each add recorded to `activity_log`.
6. **Phase 5 — Web UI polish for movies:** collections-with-gaps list, missing/existing view (with upcoming/unreleased films kept visually separate per technical challenge #26), per-user dismiss action, per-collection "not part of my collection" exclude action, plus **theme.park theme support** — the optional stylesheet-URL setting and the mapping from theme.park's custom properties onto Pico's. Themeability lands here rather than with the rest of the settings work in Phase 9 so the first real screens are built against a themeable variable set, instead of being audited for hardcoded colours afterwards.
7. **Phase 6 — TV spin-offs:** `spinoff_mappings` table starts empty, TV matcher, diff logic, CLI output, "add a spin-off mapping" UI action (always writes `source=local`).
8. **Phase 7 — Sonarr integration + TV UI:** mirror phases 4–5 for TV, including multi-instance, cross-instance dedup, and the season-monitoring dropdown mapped to Sonarr's actual `addOptions.monitor` API values.
9. **Phase 8 — Scheduling & notifications:** APScheduler job wired to the existing diff services, settings UI for cron schedule + webhook URL/format, webhook notifier with generic/Discord/Slack payloads.
10. **Phase 9 — Activity log, settings, setup wizard polish, and packaging:** Activity log UI page, config export/import (with the secrets warning and shape validation from technical challenge #23), full setup wizard, remaining settings page items (incl. light/dark toggle, library selection editing), update-checker job + banner, README/docs, Dockerfile hardening, docker-compose.yml example.
11. **Phase 10 — Pre-release hardening (before GitHub migration):** review for secret leakage (incl. the config export path), fill any gaps in test coverage (target: diff logic, auth flow, base-URL routing, instance-unreachable handling all covered), first real `CHANGELOG.md` entry and `v0.1.0` tag, write install docs aimed at other *arr users (not just you).

## 9. Config reference

**Bootstrap env vars** (`.env.example`):
```
PLEX_URL=
PLEX_TOKEN=            # or OAuth client id/secret, TBD during Phase 2
TMDB_API_KEY=          # your own free key from themoviedb.org/settings/api — not bundled
BASE_URL=/             # e.g. /franchisarr if served under a reverse-proxy subpath
LOG_LEVEL=INFO         # DEBUG | INFO | WARNING | ERROR, structured lines to stdout
DB_PATH=               # optional; defaults to franchisarr.db inside the mounted config volume
TMDB_CACHE_TTL_DAYS=7
CROSS_INSTANCE_DEDUP=false
PUID=1000              # matches Radarr/Sonarr/Plex's own containers — sets ownership of the config volume
PGID=1000
# Optional single-instance bootstrap (further instances added via UI):
RADARR_URL=
RADARR_API_KEY=
SONARR_URL=
SONARR_API_KEY=
ADMIN_USERNAME=
ADMIN_PASSWORD=        # fallback local admin, hashed on first boot
# Optional scheduling/notifications bootstrap (also editable in Settings UI):
SCAN_SCHEDULE_CRON=    # e.g. "0 3 * * *" for nightly at 3am; empty disables scheduled scans
WEBHOOK_URL=
WEBHOOK_FORMAT=generic  # generic | discord | slack
```

Comments in `.env` must be on their own line: Docker's `env_file` parser does not strip a trailing
`# comment`, so `BASE_URL=/   # a comment` sets the base URL to the whole string after the `=`.

**Everything else** (additional instances, quality profiles, root folders, toggles) is managed via the in-app setup wizard/settings UI and stored in SQLite — not re-editable only through env vars, so the app is usable without shell access after first boot.

## 10. Distribution plan

- **Now:** private repo on your Forgejo instance. Standard git flow, README written as if public from day one (forces good docs habits early).
- **CI:** Forgejo Actions (or plain shell scripts run manually for now) building the Docker image; revisit CI once migrated to GitHub (GitHub Actions, GHCR push).
- **At public-release time:** migrate repo to GitHub, publish Docker image to GHCR, write install docs (docker-compose example, env var reference, screenshot of the setup wizard). Unraid Community Apps template and other packaging can follow once there's real usage/feedback — not a v1 blocker.
- **License:** MIT, added now even while private, so it's not a scramble later.
- **Versioning:** SemVer tags (`v0.1.0`, `v0.2.0`, ...) starting at Phase 10's first tag, with `CHANGELOG.md` maintained per release from the start (Phase 0) rather than reconstructed retroactively.
- **Security:** `SECURITY.md` added in Phase 0, covering supported versions and a private reporting channel (email for now; GitHub private security advisories once migrated).

## 11. Open items to revisit as we build

- ~~Exact Plex OAuth implementation detail (plex.tv PIN flow vs. a registered Plex "app" with client ID)~~ — **resolved Phase 2**: the PIN flow, with `X-Plex-Client-Identifier` set to a UUID generated once per install and kept in settings. No registration with Plex is required. Sign-in uses a popup plus polling rather than plex.tv's `forwardUrl` redirect, so no absolute callback URL has to be reconstructed from `X-Forwarded-*` headers behind a subpath proxy.
- Whether dismiss/ignore lists should ever be shared across users in the same household vs. always per-user — flagged as per-user for now, easy to revisit.
- Whether/when to actually build the community spin-off sync feature itself (schema is ready for it per section 5, but the sync mechanism — where the shared list lives, how updates are pulled, moderation of submissions — is deliberately undesigned until there's a real second install to test it against).
- Exact webhook payload shape for each `webhook_format` — worth checking a couple of real Discord/Slack webhook examples from other *arr tools (e.g. Sonarr's own webhook connection) for a format users may already be reusing.
- Whether "search immediately" on add should have any safety valve for bulk adds (see technical challenge #12) — e.g. a confirmation dialog above some threshold, or always staggering searches for anything beyond a single item.
- Whether the Docker `HEALTHCHECK` directive should just hit `/health`, or also verify the last scheduled scan actually completed recently (more useful signal, more complexity) — start with the simple liveness check and revisit.
- Update-check cadence (e.g. once per day is plenty) and exactly which repo API it hits pre- vs. post-GitHub migration — Forgejo's release API differs from GitHub's, so `update_checker.py` needs a small abstraction either way.
- Whether toggling a library off after initial setup should trigger an immediate rescan or just mark the cache stale until the next scheduled/manual scan — leaning toward "stale until next scan" to avoid surprise TMDb calls, but worth confirming once the UI exists.
- Sonarr's exact `addOptions.monitor` enum values (technical challenge #22) — needs a quick check against current Sonarr v3 API docs during Phase 7 rather than assuming the friendly UI labels map 1:1.
- Whether the CLI's API key should be scoped (e.g. read-only vs. can-trigger-adds) or all-or-nothing for v1 — leaning all-or-nothing for simplicity since it's typically used by the same admin who has web UI access anyway, but worth a second look before public release.
- ~~What email/contact address `SECURITY.md` should list before the GitHub migration~~ — **resolved 2026-08-30**: `franchisarr@ihatemikeg.com`, a project-specific address rather than a personal one. GitHub's private security advisories become an additional route after the migration; the address stays valid either way.
- Whether config export should offer a "redact secrets" option (safe to share for troubleshooting) alongside the full export needed for actual migration — full-only is simplest for v1, but a redacted mode would be nice for e.g. asking for help in a Discord without pasting API keys.
