# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Scheduled scans on a cron schedule you set in Settings, running in the container's local time
  (set `TZ`). A scan that's still running when the next is due is not started twice.
- Webhook notifications when a scheduled scan finds something new — generic JSON, Discord or
  Slack — with a "send a test" button. Only genuinely new gaps are announced, and the very first
  scan never notifies, so you aren't handed a list of everything that was already missing.
- One-click add to Sonarr for spin-offs, with a choice of how much to monitor: all seasons,
  future episodes only, or the first season. Your choice is remembered as the default for next
  time. Shows already in Sonarr stop being suggested, with the same per-instance and
  cross-instance settings as the movie side.
- TV spin-offs: shows related to ones you already watch that aren't in your library. Because TMDb
  has no spin-off data to import, the mapping list starts empty and grows as you confirm
  suggestions — the app says so rather than looking broken.
- A "possible spin-offs" search that finds shows named after one you own (like *NCIS: Los
  Angeles*). These are guesses, shown separately from confirmed mappings, and nothing is ever
  added from them without you saying yes. Spin-offs that don't carry the parent's name — Chicago
  Fire and Chicago P.D. — can't be found this way, and the app tells you so.
- `scan tv`, `spinoffs` and `map-spinoff` command line commands.
- Web UI for the movie side: a collections-with-gaps overview, a per-collection view separating
  what you own, what's missing and what hasn't been released yet, and an add dialog that reads
  quality profiles and root folders live from the chosen Radarr instance.
- Two distinct ways to hide a film, because they mean different things: "not interested" is
  yours alone, while "not part of this collection" corrects TMDb's data for everyone and applies
  only within that collection.
- **theme.park theme support.** Paste any theme-options stylesheet URL — from theme-park.dev or
  your own self-hosted copy — into Settings and the whole UI takes on that theme. Off by default;
  when it's off, nothing is fetched from anywhere but your own server.
- One-click add to Radarr, with support for multiple instances. Films are added monitored and
  searched immediately, matching what you'd get adding through Radarr's own UI. Quality profiles
  and root folders are read live from the instance at add time, and an instance that can't be
  reached says so rather than silently offering nothing.
- Films Radarr already has stop being reported as gaps. Instances are treated independently by
  default, so a 4K/1080p split still shows both; turn on `CROSS_INSTANCE_DEDUP` when your
  instances are split by content type instead. A per-instance setting decides whether a film
  that's currently downloading counts as already had.
- Activity log recording every add — what, when, which instance, and who or what triggered it.
- Command line additions: `instances list/test/options/refresh`, `add`, `add-collection` and
  `activity`. Bulk adds are staggered and confirm the count first, since each one triggers a
  search against your indexers.
- Finds films missing from collections you already partly own, sourced from TMDb Collections.
  Only collections you own something from are considered, so this stays a report on your own
  library rather than a catalogue of every franchise on TMDb.
- Announced sequels that haven't been released yet are listed separately from films you can
  actually go and get, so the gap list stays worth reading. On a 3,400-film library that was the
  difference between 382 "missing" films and 227 real ones.
- Plex items are matched to TMDb by the id Plex already holds where possible, falling back to an
  IMDb or TVDb lookup and finally a title-and-year search. Anything matched only on a title
  needs the release year to agree before it is trusted; plausible-but-unconfirmed matches are
  listed for you to confirm rather than being acted on or silently dropped.
- Command line client (`cli.py`): `scan movies`, `gaps`, `review`, `test-tmdb`, `api-key`. It
  talks to Franchisarr's own API over HTTP, so it works through `docker exec` and takes exactly
  the same code path as the web UI.
- Per-account API keys for the command line, sent as an `X-Api-Key` header.
- TMDb API key checking that names the actual problem — a v4 Read Access Token pasted in place of
  the v3 API Key, a truncated key, or a key too new to have activated yet.
- TMDb responses are cached with a configurable TTL (`TMDB_CACHE_TTL_DAYS`, default 7 days), so
  re-scanning an unchanged library makes no TMDb requests at all.
- Sign in with Plex, using plex.tv's PIN flow. Franchisarr never sees your Plex password. Accounts
  are only admitted if they can actually reach this install's Plex server, so having a Plex
  account is not by itself enough to log in; the server's owner becomes an administrator and
  people the library is shared with get ordinary accounts.
- Local admin account as a fallback and recovery login, seeded from `ADMIN_USERNAME` /
  `ADMIN_PASSWORD` on first boot, so a misconfigured Plex connection cannot lock you out.
- Sessions stored server-side, so signing out revokes the session immediately rather than only in
  that browser. Session cookies are scoped to `BASE_URL`.
- Library selection: pick which Plex movie and TV libraries Franchisarr scans. Newly discovered
  libraries start switched off, so home videos and concert rips are never scanned by accident.
- `SESSION_COOKIE_SECURE` environment variable, for installs served over HTTPS.
- SQLite data layer: SQLModel definitions for users, Radarr/Sonarr instances, settings, dismissed
  items, spin-off mappings, collection excludes, included libraries and the activity log, with the
  initial Alembic migration. Migrations are applied automatically at startup.
- Environment-variable bootstrap for the full `.env.example` set, seeding the settings table on
  first boot only. Values changed in the app are never overwritten by a stale environment.
- Structured stdout logging honouring `LOG_LEVEL`, with registered secrets redacted from every log
  line — including tracebacks and uvicorn's own access log.
- Plex client returning typed results, listing libraries, movies and shows, paged so large
  libraries arrive over several requests. Handles both the current and legacy Plex agent GUID
  formats, plus the HAMA anime and Kodi NFO agents.
- Dark-by-default web UI shell on Pico, with htmx, Alpine and Pico vendored locally at pinned
  versions — no CDN requests.
- `DB_PATH`, `TMDB_CACHE_TTL_DAYS` and `CROSS_INSTANCE_DEDUP` environment variables.
- `scripts/plex_guid_audit.py`, a read-only diagnostic reporting how many items in each Plex
  library resolve to a TMDb ID and which GUID formats are in use. Exits non-zero when it meets an
  agent format Franchisarr cannot parse, so unsupported libraries can be reported precisely.
- Project scaffolding: CI (Forgejo Actions), multi-arch Docker build skeleton, license, security
  policy, and changelog established ahead of Phase 1 feature work.

### Fixed

- An *arr instance behind an authentication proxy (Authelia, Authentik, Cloudflare Access) is no
  longer reported as "API key rejected". Franchisarr now recognises a login page and suggests
  either using an internal URL or allowing `/api` through the proxy.
- Asset links no longer depend on module import order when `BASE_URL` is a subpath: the base URL
  is now resolved per request rather than captured at import.
- Plex items left unmatched by a modern library agent (`tv.plex.agents.none`) are now recognised
  as legitimately carrying no external ID, instead of being reported as an unknown agent. Only
  the legacy spelling was handled; both occur on the same server.
- `.env.example` used trailing inline comments, which Docker's `env_file` parser does not strip —
  copying it to `.env` would have made each comment part of the value it followed.
