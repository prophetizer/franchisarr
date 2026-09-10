# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] — 2026-09-10

### Added

- **Posters and identifying links on TV spin-offs.** Each suggestion now shows the show's poster
  and links to IMDb, TVDB and TMDb — because a title and a year cannot tell you what *Glory Daze*
  or *Star City* actually is, and a link can. Only the ids TMDb actually holds are linked; TMDb
  itself is always there. Same on the per-show search results. Existing installs refetch their
  show cache on the next scan to fill these in; no extra TMDb requests, the ids ride along on the
  call that was already being made.

## [0.4.2] — 2026-09-03

### Added

- **"Refresh everything"**, beside the scan button. A normal scan honours the seven-day cache, so
  a configuration change is invisible until the cache expires — add a fanart.tv key and the
  franchise logos simply don't appear, because the collections that would carry them were fetched
  yesterday and won't be fetched again for a week. This refetches every collection and show now.
  The plumbing existed since the first scan service but was reachable only from Python.

## [0.4.1] — 2026-09-03

### Fixed

- **A scan crashed at the spin-off step** with `name 'TmdbShow' is not defined`. A missing import
  on the one branch no test executed: every scan test passed `wikidata=None`, so discovery was
  never run by the suite even though its client and its importer were both covered. The library
  snapshot, collections and artwork had all completed by then — only the spin-off step was lost —
  but the scan reported itself as failed. There is now a test that runs a TV scan with discovery
  switched on, and another that pulls the endpoint out from under it mid-scan.

## [0.4.0] — 2026-09-02

Spin-offs stop being a thing you have to go looking for, and two things that were only findable
by accident get fixed.

### Added

- **Spin-offs are discovered automatically, from Wikidata.** Previously the page showed nothing
  until you picked a show and searched it, one at a time — on a 656-show library that is not a
  feature. Scans now ask Wikidata which of your shows have spin-offs and list them up front.
  No key and no account: Wikidata is free and needs neither.

  It also finds the ones a name search never could, because it matches on TMDb ids rather than
  titles: Family Guy → *American Dad!*, black-ish → *Grown-ish*, Young Sheldon → *Georgie &
  Mandy's First Marriage*, Reacher → *Neagley*. On the test library, 98% of shows resolved to a
  Wikidata item and 24 spin-offs surfaced with no clicking at all.

  Suggestions are labelled: an explicit "has spin-off" statement is shown plainly, while weaker
  evidence ("follows", "based on") is marked *possible*. Foreign-language remakes are filtered
  out — *Brooklyn Nine-Nine → Escouade 99* is a remake, not a spin-off — as are entries Wikidata
  has no English name for. Nothing is ever added automatically; every suggestion still needs a
  click.

  The per-show search is still there, under "Search a single show", for when you think one has
  been missed.

### Fixed

- **You can start a scan from the home page and the spin-offs page.** It was only ever on the
  collections page, so on a fresh install the one action everything else depends on was somewhere
  you had no reason to look. All three pages now show the running scan's progress too, wherever
  it was started from.

- **"Sign in with Plex" spun forever instead of signing you in.** The sign-in itself worked — the
  session was created — but the page never moved, and reloading it by hand was the only way
  through. The popup window was held in the Alpine component's state, and Alpine makes that state
  reactive; reading a reactive-wrapped cross-origin window raises a SecurityError, which the
  window becomes the moment it goes to plex.tv. So the check that closes the popup threw, and
  took the redirect with it. The window is kept outside the component now, closing it can no
  longer block the redirect, and a failure while polling shows an error instead of spinning.

## [0.3.0] — 2026-09-01

Artwork, and a bug that had not gone off yet. If you have been running 0.2.x, the fix below is
the reason to take this one: the next scan after your collection cache turned seven days old
would have failed without it.

### Added

- Optional fanart.tv support. With a `FANART_API_KEY` set, a collection heading becomes a hero:
  the franchise wordmark over the collection's backdrop. fanart.tv has no collection endpoint, so
  the logo comes from the collection's earliest film, which is the entry that established the
  wordmark. Entirely optional — with no key, headings stay as text, which is what they were.
- Poster artwork on the collections screens — on the cards, in the per-collection view, and beside
  each film in the lists. Images come from TMDb's image CDN, which means each viewer's browser
  fetches them from TMDb rather than from your server; `SHOW_ARTWORK=false` turns them off for a
  text-only interface.

### Fixed

- Refreshing a cached TMDb collection failed with a unique-constraint error. Members were deleted
  with an ORM loop and re-added in the same flush, and SQLAlchemy does not order those DELETEs
  before the INSERTs — so any refetch whose membership overlapped the previous one failed, which
  is every refetch. It needed a collection to fall out of the seven-day cache to happen at all,
  so no install had reached it yet. The same bug was fixed in the Radarr cache in 0.1.0; this is
  the same fix in the other place it lived.

## [0.2.1] — 2026-09-01

The command line and the JSON API both change here. Both are treated as unstable before 1.0, so
this is a patch release rather than a minor one — but if you script against either, read the
Changed section.

### Fixed

- **Scanning no longer hangs the page.** "Scan my library" ran the whole scan inside the request,
  so on a real library the page sat frozen with no sign of progress for minutes and then timed
  out. Scans now run in the background: the button starts one and returns immediately, and the
  page shows what it's doing and how far along it is. You can navigate away — a scan already
  running shows up wherever you land, including one the scheduler started.

### Changed

- The command line's `scan movies` and `scan tv` are replaced by a single `scan`, which starts
  the background task and follows its progress. Interrupting it no longer stops the scan.
- `POST /api/scan/movies` and `POST /api/scan/tv` are replaced by `POST /api/scan`, which returns
  at once, plus `GET /api/scan/status` to poll.

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

[Unreleased]: https://github.com/prophetizer/franchisarr/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.5.0
[0.4.2]: https://github.com/prophetizer/franchisarr/releases/tag/v0.4.2
[0.4.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.4.1
[0.4.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.4.0
[0.3.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.3.0
[0.2.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.2.1
[0.2.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.2.0
[0.1.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.1.1
[0.1.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.1.0
