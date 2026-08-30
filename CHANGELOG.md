# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
- Project scaffolding: CI (Forgejo Actions), multi-arch Docker build skeleton, license, security
  policy, and changelog established ahead of Phase 1 feature work.

### Fixed

- Plex items left unmatched by a modern library agent (`tv.plex.agents.none`) are now recognised
  as legitimately carrying no external ID, instead of being reported as an unknown agent. Only
  the legacy spelling was handled; both occur on the same server.
- `.env.example` used trailing inline comments, which Docker's `env_file` parser does not strip —
  copying it to `.env` would have made each comment part of the value it followed.
