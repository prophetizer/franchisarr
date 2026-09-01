# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `contrib/theme-park/franchisarr-base.css`, a base stylesheet for anyone hosting their own
  [theme.park](https://theme-park.dev), so Franchisarr can be themed through the standard
  mechanism alongside the rest of a stack.

## [0.2.0] — 2026-09-01

### Changed — action needed if you set a theme

**Themes are now set by environment variable instead of in Franchisarr's settings page.** If you
had chosen one in the app, it is no longer applied: set `TP_THEME` on the container instead.

```yaml
environment:
  TP_THEME: nord
  TP_DOMAIN: theme-park.dev     # or your own copy
  TP_SCHEME: https
  TP_COMMUNITY_THEME: "false"
```

The reason for the change is that this is how theming is actually done: a homelab running
[theme.park](https://theme-park.dev) across a dozen services sets it once, centrally, and expects
every app to follow. Asking you to open each app and paste a URL was the wrong shape. These are
theme.park's own variable names, so a stack already setting them needs nothing new.
`THEME_CSS_URL` overrides with a literal stylesheet URL. The settings page shows what is active
and where it came from, and no longer offers to change it.

### Fixed

- **Themes injected by a reverse proxy now work**, with nothing configured in Franchisarr at all.
  If you theme centrally — nginx `sub_filter`, a Traefik plugin, theme.park's Docker mod — the
  stylesheet that maps theme.park's properties onto the ones the app paints with is now always
  loaded. It previously loaded only when Franchisarr rendered the theme link itself, so an
  injected theme defined its colours and nothing used them.

  Note there is still no `franchisarr-base.css` at theme.park, so injecting a *base* stylesheet
  the way you would for Sonarr finds nothing; the theme-options file plus the built-in adapter is
  what does the work.

## [0.1.1] — 2026-08-31

### Fixed

- **Sign in with Plex never appeared on a new install.** Franchisarr only learned which Plex
  server it belongs to when someone opened the library page — a page you have to be signed in to
  reach. It now finds out at startup, so the Plex button is there the first time you load the
  login page. An install configured with Plex but no local admin account previously had no way to
  sign in at all.

### Added

- `scripts/reset_admin_password.py`, for when the local admin password is forgotten. The in-app
  change screen asks for the current password, which is no use in that situation.

## [0.1.0] — 2026-08-31

First release.

Franchisarr scans your Plex library and finds two things: films missing from collections you
already own part of, and spin-offs of shows you already watch. What you pick goes to Radarr or
Sonarr with one click. Nothing is ever added on your behalf.

### Movies

- Finds films missing from TMDb collections your library already touches. Only collections you
  own something from are considered, so this stays a report on your own library rather than a
  catalogue of every franchise in existence.
- Announced sequels that aren't out yet are listed separately from films you can actually go and
  get. On a 3,400-film library that was the difference between 382 "missing" films and 227 real
  ones.
- Two distinct ways to hide something, because they mean different things: "not interested" is
  yours alone, while "not part of this collection" corrects TMDb's data for everyone and applies
  only within that collection.

### TV

- Finds spin-offs of shows you already watch. TMDb has no spin-off data to import, so the mapping
  list starts empty and grows as you confirm suggestions — the app says so rather than looking
  broken.
- A "possible spin-offs" search finds shows named after one you own, like *NCIS: Los Angeles*.
  These are clearly-labelled guesses, and nothing is added from them without you saying yes.
  Spin-offs that don't carry the parent's name — Chicago Fire and Chicago P.D. — can't be found
  this way, and the app tells you so instead of implying none exist.

### Radarr and Sonarr

- One-click add, monitored and searched immediately, matching what you'd get adding through
  their own UI. Quality profiles and root folders are read live at add time, and an instance that
  can't be reached says so rather than silently offering nothing.
- Multiple instances supported throughout. They're treated independently by default, so a
  4K/1080p split still shows both; `CROSS_INSTANCE_DEDUP` suits instances split by content type
  instead. A per-instance setting decides whether a film already downloading counts as had.
- For TV, a choice of how much to monitor — all seasons, future episodes only, or the first
  season — remembered as the default for next time.
- An instance behind an authentication proxy is identified as such, rather than being reported as
  a rejected API key.

### Plex and matching

- Sign in with Plex; Franchisarr never sees your Plex password. Only accounts that can reach your
  own Plex server are admitted, so having a Plex account isn't enough. The server's owner becomes
  an administrator; people you share with get ordinary accounts.
- A local admin account as the fallback, so a misconfigured Plex connection can't lock you out.
- You choose which Plex libraries are scanned. New ones start switched off, so home videos and
  concert rips are never scanned by accident.
- Items are matched to TMDb by the id Plex already holds, falling back to IMDb, TVDb, and finally
  a title-and-year search. A title-only match needs the release year to agree before it's
  trusted; anything less confident is listed for you to confirm rather than acted on or silently
  dropped.

### Running it

- Scheduled scans on a cron schedule, in the container's local time. Webhook notifications —
  generic, Discord or Slack — sent only when something new turns up, never on the first scan.
- Activity log of everything added, what triggered it, and where it went.
- Config backup in two forms: a full one that restores an install, and a redacted one safe to
  share when asking for help.
- Command line client covering scanning, gaps, spin-offs, adding, instances and activity. It
  talks to Franchisarr's own API, so it works over `docker exec`.
- Dark by default with a light toggle, and support for any [theme.park](https://theme-park.dev)
  theme, self-hosted or otherwise.
- Runs behind a reverse proxy at a subpath. Multi-arch image (amd64/arm64), non-root with
  PUID/PGID.

### Known limitations

- Anime matched by the HAMA Plex agent is supported but has only been tested against recorded
  fixtures, not a real HAMA library.
- The spin-off search only finds shows named after the original; others need a mapping added by
  hand.

[Unreleased]: https://github.com/prophetizer/franchisarr/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.2.0
[0.1.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.1.1
[0.1.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.1.0
