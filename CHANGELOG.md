# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.23.1] — 2026-09-24

Found by testing against a real Seerr 3.4.1 for the first time -- every one of these passed
against the fake server the tests used.

### Fixed

- **Seerr's Test button passed with a wrong API key.** `/status` is public in Seerr, so it
  answered 200 to a made-up key and the button reported success for an instance that would
  refuse every request. Test now also asks `/auth/me`, which needs the key.
- **Failed Seerr requests were hidden.** Seerr has five request statuses -- pending, approved,
  declined, failed, completed -- though its published API spec documents three. Everything
  except "declined" was treated as handled, so a request that failed to reach Radarr made its
  film vanish from the lists with nothing on its way. Only pending, approved and completed now
  count; declined and failed come back as gaps.
- A rejected Seerr key was reported as "Radarr rejected the API key" -- a shared error helper
  ignored the app name it was given.
- The request dialog, the Instances page and the README said Seerr "may hold the request for
  approval". Seerr's API key acts as its administrator, whose requests are approved
  automatically, so a request from Franchisarr normally goes straight through. The wording now
  says so; the result still reports it when a request does wait.

### Added

- **The update check can be turned off**, under Settings → Update check or with
  `UPDATE_CHECK=false`, which overrides the checkbox and is read live (so it works on an
  existing install, unlike a seeded setting). It is the only connection the app makes that the
  user didn't set up; turned off, it makes none.
- A README section, **What it connects to**, listing every outside service and when.

## [0.23.0] — 2026-09-23

### Changed

- **The request target is called Seerr.** Jellyseerr was renamed
  [Seerr](https://github.com/seerr-team/seerr) and Overseerr was archived in February 2026, so
  the UI, the dialogs and the docs lead with Seerr. Nothing breaks: all three speak the same
  `/api/v1` with the same request shapes (checked against Seerr's own `seerr-api.yml`), an
  existing instance keeps its label and keeps working, and the Instances form still offers
  Overseerr and Jellyseerr for installs that run them. New instances default to Seerr.

## [0.22.1] — 2026-09-22

### Changed

- The paging threshold is 250 items, not 120. On the library this was built against, Upcoming
  (147) and Directors (148) sat just above 120 and picked up a pager they did not need --
  measured only after 0.22.0 was deployed. A 20,000-film page is ~225 KB instead of ~110 KB,
  still down from a megabyte.

## [0.22.0] — 2026-09-22

### Changed

- **The long list pages are paged.** At 20,000 films the Collections, Spin-offs, Upcoming and
  Directors pages each rendered around a megabyte of HTML -- slow to parse, heavy on a phone,
  and nobody scrolls eleven hundred cards. Lists longer than 250 items are cut into pages;
  below that no pager is rendered and the page is exactly what it was. The headings count the
  whole library rather than the page, and a pager link keeps the sort and filter you were
  looking at. Spin-offs has two independent pagers, since the owned-show list behind "Search a
  single show" is its own long list.

  Measured at 20,000 films and 2,000 shows: Collections 1,005 KB → 114 KB, Spin-offs
  1,454 KB → 245 KB, Upcoming 1,008 KB → 120 KB, Directors 1,152 KB → 96 KB (at the 120-item
  threshold 0.22.0 shipped with; 0.22.1 raised it to 250, so roughly double those). This caps
  the HTML, not the work behind it -- the read-time services still assemble the full list
  before slicing, because that is what the totals describe.

## [0.21.0] — 2026-09-22

### Added

- **Apprise notifications.** Settings → Notifications takes Apprise URLs, one per line --
  Telegram, Pushover, ntfy, Gotify, Matrix, email and a hundred-odd more -- delivered from
  inside the app by the `apprise` library (pure Python; no build on arm64). Or, for a
  household that already runs apprise-api, its `/notify` endpoint. Same message as the
  webhooks: a title and a Markdown body, fifteen titles a section then "…and N more", so
  Telegram's and Pushover's length caps are never hit. `WEBHOOK_FORMAT=apprise|apprise_api`.

### Changed

- The notification URL is now treated as a credential: a Discord webhook URL lets anyone post
  to the channel and an Apprise URL carries the service token. It is registered with the log
  redactor on save and at boot, and the redacted config export blanks it.
- The notifications form: format first, and the URL field is a textarea that accepts
  non-HTTP schemes.

## [0.20.0] — 2026-09-22

### Added

- **Overseerr / Jellyseerr as an add target.** Configured on the Instances page alongside
  Radarr and Sonarr; every Add dialog then offers "Request via Overseerr" next to the direct
  add. Seerr chooses the *arr, profile and folder itself and may hold the request for
  approval -- the dialog says which happened. Open requests (pending or approved) are cached
  on every scan and keep a title out of the lists, like a queued Radarr add. Requests appear on
  the Activity page labelled with the Seerr instance; the config export carries the instances
  (redacted copy blanks the key); keys are masked in the UI and redacted in logs.
- `/api/lists/stats.json?api_key=…` -- the headline numbers as one flat document for a
  dashboard widget (Homepage `customapi`, Glance, Dashy), cached for a minute. README has a
  Homepage example.
- Web app manifest and apple-touch-icon, so a phone can put Franchisarr on its home screen
  with the icon; `start_url` and icon paths follow `BASE_URL`.
- Unraid Community Applications template in `contrib/unraid/`, with the submission steps.

### Changed

- **Measured at 20,000 films / 2,000 shows** with a new `scripts/loadtest.py` (every external
  client faked; nothing from anyone's library). Before: the first scan never finished -- every
  library row stayed in the session through the collection and director passes, so each of
  the thousands of commits paid to expire all of them, O(n²) -- and the pages that did render
  took eleven seconds. After: first scan 48 s, enrichment 71 s, steady state 38 s; every page
  under 1.5 s (home 11.3 → 1.3 s, Collections 11.3 → 0.7 s, one collection 7.1 → 0.4 s,
  Franchises 9.6 → 1.5 s, Upcoming 5.3 → 0.6 s). Read-time services select columns rather than
  building tens of thousands of ORM objects, `collection_gaps` runs three queries instead of
  three per collection, and the detail pages compute one collection, franchise or director
  rather than all of them.

## [0.18.0] — 2026-09-22

### Added

- **Download diagnostics** on the Settings page: a redacted JSON bundle for bug reports --
  version, platform, media servers and libraries, instance counts, library and cache counts,
  up to 200 unmatched and 200 needs-review titles, the last scan's outcome and recent activity.
  Credentials are blanked twice over (the redacted config export, then the logging redactor).
- Issue forms on GitHub for bugs, matching problems and feature requests, each asking for the
  diagnostics file; security reports are routed to private reporting.

## [0.17.1] — 2026-09-21

### Fixed

- 0.17.0's Content-Security-Policy blocked theme.park themes injected by a reverse proxy
  (traefik-themepark, nginx `sub_filter`): it allowed stylesheets only from the app and the
  host in `THEME_URL`, and a proxy-injected theme lives on a host the app never sees. Styles,
  images and fonts may now load from any HTTPS origin; scripts, framing, plugins, `<base>` and
  form targets stay as restricted as before.

## [0.17.0] — 2026-09-21

### Security

- **Sign-in is rate-limited**: ten failed attempts per address in fifteen minutes, then 429
  with `Retry-After`. Only failures count; a success clears the count. Applies to the local
  form and the Jellyfin/Emby form, which relays attempts to that server.
- **Cross-site POSTs are refused** using `Sec-Fetch-Site` / `Origin`, alongside the existing
  `SameSite=Lax` cookie. Clients that send neither (curl, the CLI, an *arr) are unaffected.
- **Security headers on every response**: a Content-Security-Policy scoped to this app, TMDb,
  fanart.tv and the theme host; `frame-ancestors 'none'`; `nosniff`; same-origin referrer.
  Verified against every page, the htmx dialogs, Alpine and a theme.park theme with zero
  violations.
- **Request bodies are capped at 2 MB.**
- `SECURITY.md` now lists what the app does on its own behalf.

## [0.16.1] — 2026-09-21

### Fixed

- The "Confirmed spin-off mappings" section listed every mapping a scan had found from
  Wikidata under a heading that said "your own list". It lists only what you added or confirmed.

### Changed

- README screenshots are regenerated automatically on every UI change, from a fixed sample
  library fetched from TMDb (`scripts/screenshots.py`), so they can't drift.

## [0.16.0] — 2026-09-20

### Added

- **Calendar feed.** `/api/lists/upcoming.ics` is the Upcoming page as an iCalendar
  subscription: one all-day event per announced film, with the collection and how much of it
  you own, linking back to the collection page. Same key as the import lists; the URL is on
  the Settings page. Written without a dependency; validated against a strict parser.

## [0.15.11] — 2026-09-20

### Security

- Media-server credentials already in the database are registered with the log redactor at
  startup. Before, a Jellyfin or Emby key that pre-dated the current boot was only registered
  when something first built a client for it, so it could reach a log line before the first
  scan. Found by the post-release security review; no evidence any install logged one.

## [0.15.10] — 2026-09-19

### Changed

- **Upcoming uses the compact cards** too, grouped by month as before. A card without artwork
  now shows a muted poster-shaped placeholder on every card page, so its text lines up with its
  neighbours.

## [0.15.9] — 2026-09-19

### Changed

- **Spin-offs page uses the same compact cards** as Collections, Franchises and Directors —
  poster, title with links, relationship, Add / Not interested — for all three of its lists.

## [0.15.8] — 2026-09-19

### Changed

- **Uniform cards everywhere.** The header and footer bands are gone from every card, not just
  the compact ones; the home page's section cards sit in a grid instead of stacking full-width;
  and buttons are the size of their label rather than stretched across the form.

## [0.15.7] — 2026-09-19

### Fixed

- **Compact cards no longer drift apart.** Cards in a row share a height, and the grid inside
  each card was stretching its rows to fill it, so title, counts and list floated apart by
  however tall the neighbour was. Rows hug their content now, the header band is gone, and the
  columns are a little wider.

## [0.15.6] — 2026-09-19

### Changed

- **The header is the banner lockup**: icon, name and tagline, built from live text so a theme
  recolours it; the tagline hides on phones.

### Fixed

- The header icon lost parts under theme.park themes (the page background there is a gradient,
  which is not a colour; the icon's tile and dark parts are fixed colours now) and could drop
  shapes in Safari (variables referenced from attributes rather than styles).

## [0.15.5] — 2026-09-19

### Fixed

- **Everything was too big on a wide screen.** Pico scales its root font size with the
  viewport, up to 131% at 1536px and beyond, so on a desktop monitor the nav and buttons were a
  third larger than on a laptop. The root is pinned at 16px now, and nav links and buttons sit
  a step under that.

## [0.15.4] — 2026-09-19

### Changed

- **New icon: Found.** A film reel and a TV, and a magnifying glass below them showing the
  dashed outline of what's missing — movies, shows, and the finding. Theme-aware in the
  header as before; favicon and GitHub images updated.

## [0.15.3] — 2026-09-19

### Fixed

- **theme.park gradient themes** (hotline, space-gray, and any theme whose `--main-bg-color` is
  a gradient or image) now paint the page and cards; they used to fall back to the default
  palette because a gradient is not a colour.
- **The icon under theme.park themes**: `--accent-color` is an RGB triplet there, not a colour,
  so the icon's dashed accent was invalid on every theme.park theme. Verified against all
  eleven official theme options.
- `contrib/theme-park/franchisarr-base.css` updated to match, ready to submit upstream.

## [0.15.2] — 2026-09-19

### Changed

- **New icon: clapper and lens** — a clapperboard with one stripe missing from its bar, under a
  magnifying glass. Theme-aware in the header as before.

## [0.15.1] — 2026-09-19

### Changed

- **New icon: the fanned stack** — three posters fanned like cards, the front one only an
  outline. In the header it is inline SVG painted with the page's own colour variables, so a
  theme.park theme (or the light toggle) recolours it; the favicon and the GitHub images are
  static copies in the default palette.

## [0.15.0] — 2026-09-19

### Changed

- **Nord is the default theme**, dark and light (the toggle switches between Nord's two halves).
  theme.park themes override it exactly as before; nothing changes for an install that sets one.

## [0.14.1] — 2026-09-19

### Fixed

- The header showed the simplified three-bar favicon instead of the five-bar shelf icon.

## [0.14.0] — 2026-09-19

### Added

- **Director photos**, from TMDb, on the Directors cards and page headings. New credits carry
  the photo for free; directors credited before this release are looked up once each on the
  next scan (only those shown, so ~150 requests on a large library, never repeated).

### Changed

- **Collections and Directors use the compact card** the Franchises page got in 0.13.2: poster
  or photo as a thumbnail beside the text, three or four across.
- The header icon is bigger.

## [0.13.2] — 2026-09-18

### Changed

- The icon sits beside the name in the header.
- **Franchises page cards are compact**: the poster is a thumbnail beside the text instead of
  the whole card, so three or four franchises fit across a screen instead of one giant poster.

## [0.13.1] — 2026-09-18

### Fixed

- **The Directors page crashed** for any director with both rated and unrated missing films —
  the preview sorted on a rating that is `None` under ten votes. Present since 0.8.0.
- A watched film showed two ticks on collection, franchise and director pages; it is a small
  *watched* label now.

### Added

- **An icon.** A shelf of numbered spines with one dashed gap — I, II, _, IV, V — as the
  favicon, a 512px app icon (`app/static/icon.svg`) and the README header (`docs/brand/`).
- README screenshots of the main pages.

## [0.13.0] — 2026-09-18

### Added

- **Several media servers at once.** Plex, Jellyfin and Emby are now rows under a new
  *Servers* page rather than one setting: add every server you use, tick libraries on each, and
  one scan reads them all. A film on any of them counts as owned — once, however many hold it —
  and the collection page says which servers hold each. Every filled-in pair in `.env` becomes a
  server on first boot; `MEDIA_SERVER` now only limits that seeding to one kind. Plex sign-in
  accepts an account that can reach any configured Plex; Jellyfin/Emby sign-in offers a server
  choice when there is more than one.
- **Watched state.** Each scan records whether you've watched each owned film or started each
  show — Plex from the token owner's play state, Jellyfin/Emby from the *watched as* user on the
  server (default: its first administrator). Owned titles get a tick on collection, franchise
  and director pages, and the Collections page can be filtered to franchises you've started.
  Measured on the developer's three servers in one pass: 9,373 film rows → 3,445 distinct films,
  670 shows, 0 errors.

### Changed

- Migration 0020 creates `media_servers`, seeds it from the old settings, attaches every scanned
  library and item to that server, and removes the old `plex_url`/`jellyfin_*`/`emby_*`/
  `media_server` settings. Config exports carry the servers (credentials redacted in the shared
  form) and name the server each library belongs to; exports from 0.12 and earlier still import,
  with their single server translated into a row.

## [0.12.1] — 2026-09-18

### Fixed

- **The scan button on a Jellyfin or Emby install.** It still asked for the Plex connection
  before starting and answered 409 without one, so a Jellyfin-only install could not scan from
  the page (the scheduled scan was fine). The empty-libraries message also named Plex whatever
  the server was.

## [0.12.0] — 2026-09-18

### Added

- **Jellyfin and Emby.** Set `JELLYFIN_URL` + `JELLYFIN_API_KEY` (or the Emby pair) instead of
  the Plex ones and everything works the same: libraries, scans, every page. Sign in with your
  Jellyfin or Emby username and password; an administrator there administers here. One media
  server per install for now — several at once is the next release. Matching is simpler than
  on Plex, because both servers hand over TMDb ids directly: 99.7–100% of items on the test
  servers, no GUID parsing. Sign-in was verified live against Jellyfin 10.11.11 and Emby
  4.9.5.0 with a throwaway account.

### Changed

- Database columns named for Plex (`plex_library_key`, `rating_key`, `plex_user_id`…) are
  renamed neutrally by migrations 0018 and 0019. Data is untouched. Config exports made before
  this release import fine.

## [0.11.1] — 2026-09-18

### Security

- **Dependencies upgraded for published advisories.** Starlette 0.41 → 1.6 (a Range-header
  denial of service in `FileResponse`, which serves this app's static files; form-parsing limits
  not enforced; `Host`-header URL reconstruction), python-multipart 0.0.20 → 0.0.32 (several
  form-parsing denial-of-service issues), Jinja2 3.1.5 → 3.1.6. FastAPI moves to 0.141 to carry
  them. No behaviour change; the full suite passes and `pip-audit` is clean.

## [0.11.0] — 2026-09-18

### Changed

- **Franchisarr lives on GitHub now** — https://github.com/prophetizer/franchisarr — and the image
  is published to GHCR for amd64 and arm64 on every release: `ghcr.io/prophetizer/franchisarr`.
  The quick start no longer needs a clone. The update checker reads GitHub's releases (and now
  looks at twenty of them rather than one, which had been quietly undoing the 0.6.0 fix that
  picks the highest version). Security reports can use GitHub's private advisories.

## [0.10.0] — 2026-09-18

The pre-public release: the things a stranger's install hits that the developer's never did,
and the feature the *arr community actually wants.

### Added

- **Import lists.** Everything Franchisarr finds, as JSON Radarr and Sonarr can poll as a
  *Custom List*: `collections`, `upcoming`, `directors`, `franchises`, `films` (all of those,
  each film once) and `shows`. Point Radarr at one and its own rules — monitor, root folder,
  quality, search — take over; Franchisarr still adds nothing itself. `min_rating` on the URL
  overrides the household floor for that list; `include_upcoming` adds announced films; your
  dismissals and preferences apply. The key sits in the URL, as with any *arr list — read-only
  and revocable. Settings shows the URLs and mints the key, shown once.
- **Adds are tagged `franchisarr`** in Radarr and Sonarr, the convention Overseerr set, so what
  came from here is visible and filterable later. The tag is created if missing; tagging
  failing never fails an add.
- **Config export now includes dismissals** — every "Not interested" ever clicked, keyed by
  username so they land on the right person on a new install. A dismissal whose person hasn't
  signed in yet is counted and skipped, never handed to whoever ran the import.

### Fixed

- **The Spin-offs page's "TV from films you own" and every franchise page were far slower than
  they needed to be** — 62 seconds and 59 seconds on the test library — because a title lookup
  recomputed the collection gaps once per row. Both are now under two seconds. Found by timing
  the import lists, which inherited it.

### Changed

- **A first scan is two passes.** Plex, TMDb and collections first, so the pages fill in a few
  minutes; directors, spin-offs, continuations and franchises follow in a second background job
  with its own progress. Same total work, but a new install sees results in three minutes
  instead of fifteen. Later scans are one pass, cheaply, inside the cache.

## [0.9.0] — 2026-09-18

### Added

- **A Preferences page, shown once on a fresh install** right after you choose libraries, and
  under Settings forever after. Four taste settings, each with an example of what it changes:
  the rating floor, which directors get a page, whether TV films and specials in a franchise
  count as missing, and whether shorts in a filmography do. Skip keeps the defaults. Nothing
  these hide is thrown away — every page keeps a folded section of what its settings filtered.
- **TV films, specials and shorts in franchise rosters are a preference now**, off by default.
  Wikidata files *The Star Wars Holiday Special* and the LEGO tie-ins under Star Wars as
  "television film" and "short film"; they used to be either listed as gaps or dropped
  entirely. They sit in a folded section until you say you want them.
- **Shorts in director filmographies are a preference now**, off by default. TMDb's credits
  carry no runtime, so it is learned once per unowned film (about 1,500 requests on the test
  library, then never again); under forty minutes is a short, and an unknown runtime never is.

## [0.8.1] — 2026-09-18

### Fixed

- **The menu no longer scrolls sideways on a phone.** The 0.8.0 fix relied on flex wrapping and
  was verified in Chromium; an iPhone still scrolled. On small screens the nav is now plain
  block flow with inline links — the one layout every engine wraps identically — and pages are
  sent `Cache-Control: no-cache` so a phone cannot keep a pre-deploy page pointing at an old
  stylesheet.
- **Stylesheets and scripts now carry the app version in their URL**, so a release invalidates
  every browser's cached copy. Without it a phone kept the previous `app.css` straight across
  the deploy that fixed its layout — the files have an ETag but no `Cache-Control`, and Safari's
  heuristic freshness was enough to skip asking.

## [0.8.0] — 2026-09-17

The last of the feature run. Director pages are the one new thing; the seventh idea — anime
relations via AniList — was measured against the real library and not built, because after
what Wikidata already finds it would have added one suggestion. The measurement is in the
repository so nobody has to make it twice.

### Added

- **Director pages.** "You own 11 Nolan films — missing *Following* and *Insomnia*." Every
  director you own five or more films by (the floor is yours to set), their filmography against
  your library, rated and addable to Radarr. Documentaries and unreleased films are listed apart;
  the rating filter from Collections applies here too. On the test library: 148 directors, and
  the missing lists are *Schindler's List*, *Fargo*, *Black Hawk Down*, *Ed Wood*, *Contact*.
  Credits are read once per owned film — 3,400 requests the first time, a few minutes — and
  never again; filmographies refresh on the seven-day cache.

### Fixed

- **The layout no longer runs off the edge of a phone.** Two causes, neither the theme. The nav
  was one unwrapped row, and with eleven items that is wider than a phone — which pushed the
  whole page wide, so every card below sized to it and its text ran off screen. And the scan
  panel's spinner came with a `white-space: nowrap` from Pico, meant for buttons, so its text
  couldn't wrap at all. The nav wraps now, compactly on small screens, and the scan panel wraps.

## [0.7.0] — 2026-09-17

Three more features from the run, and the one they were building towards. Upcoming films in
franchises you own, continuations that cross between film and TV, and franchise pages that put
all of it — films, shows, gaps, what's coming — on one page per franchise. Also a fix to the
update checker that this release itself would have tripped over.

### Added

- **Franchise pages.** One page per franchise, across both media: *Star Trek — you have 6 of 27*,
  with the TOS films, TNG, DS9 and Voyager listed as missing; *Stargate — 5 of 9*, with SG-1.
  Franchises come from how Wikidata files things ("media franchise", "part of the series"),
  folded so *The Infinity Saga* lands under *Marvel Cinematic Universe* and the twenty
  franchises Wikidata keeps as two unlinked items (*Jurassic Park*, *James Bond*, *Terminator*…)
  are one. Each page pulls together the collection gaps of its films, the spin-offs and
  continuations of its shows, upcoming films, and a third source that is new: every whole film
  or series Wikidata itself files under the franchise — the only way to learn about *Deep Space
  Nine* from owning *Voyager*. Each missing title says which of those it came from. On the test
  library: 206 franchises, 72 spanning both films and TV, 481 missing titles between them.
  Discovery runs on the seven-day cache like collections do — it is the longest Wikidata step.


- **Continuations across media.** The Spin-offs page gains two sections: *TV from films you
  own* — the series a film was drawn from or continued (*Firefly* for *Serenity*, *Bates Motel*
  for *Psycho*, *The Sarah Connor Chronicles* for *Terminator 2*) and the original series behind
  a remake you have (*The A-Team*, *CHiPs*, *21 Jump Street*) — and *Films from shows you own*.
  Each routes to the other *arr. On the test library: 51 series and 9 films. Measured before it
  was built, which is how it learned to exclude pornographic parodies (three of the first
  fourteen films) and why the show-to-film direction is presented as the small one it is.


- **An Upcoming page: what's coming to franchises you already own.** Announced-but-unreleased
  films in collections you have part of, grouped by month, soonest first, with how much of each
  franchise you have — "*Shrek 5* · Shrek Collection · you have 4 of 5 · 2027-06-30 · in 288
  days". Undated announcements gather at the end. Nothing else in the *arr stack can show this:
  Radarr's calendar knows what has been added, this knows what you'd want added.

  Scans now notice when one of these films **gains a release date, or its date moves**, and the
  webhook says so — once, when it happens, not every night. On the test library that is 150
  films, 46 dated, 11 due within 90 days.

### Fixed

- **The update banner picks the highest version, not the first release listed.** Forges sort
  releases by creation time, and Forgejo stamped one with the epoch when the tag push and the
  release request landed together — so it sorted last, and every install would have been told it
  was up to date when it was not. Version numbers are the fact; list order is not.

## [0.6.0] — 2026-09-15

The first two of a run of features being built and tried one at a time against a real library.
Both are about the same thing: the lists were complete but unordered and unexplained, and a list
of 215 films or 38 shows needs to say what is worth looking at and why.

### Added

- **Spin-off suggestions say how a show relates**, and find the other half of every succession.
  "Dragon Ball GT — follows Dragon Ball Z"; "Bosch — precedes Bosch: Legacy"; "American Dad! —
  spin-off of Family Guy"; "Escouade 99 — based on Brooklyn Nine-Nine · possible". Before, every
  row said "spin-off of", which made *1923 → Yellowstone* read backwards. The labels come from
  which Wikidata property stated the relation, and only "based on" — the property remakes also
  use — is still marked *possible*.

  Wikidata's "followed by" was never queried, so the *earlier* half of a succession — usually the
  original series of a franchise you own the continuation of — was never found. On the test
  library that was 40 relations: *Sons of Anarchy* for *Mayans M.C.*, *Star Trek: Enterprise*
  for *Discovery*, *Vikings* for *Valhalla*, *The Tracey Ullman Show* for *The Simpsons*.

  A show related to several you own is listed once — *Dexter* precedes three shows in the test
  library and used to be three rows with three Add buttons.

- **Gaps are ranked, and can be filtered, by rating.** Every missing film shows its TMDb score,
  collections are ordered by their best missing film — *A Quiet Place Part II* before *Sinister
  Squad* — and a household threshold ("hide films rated below 6.0") folds the straight-to-video
  tail into a collapsed section on each collection's page rather than deleting it. Films with
  fewer than ten votes are never hidden: unknown is not the same as bad. On the test library,
  91% of missing films carry a usable rating and a 6.0 floor hid 54 of 215. Sort by name is one
  click away for finding a known collection.

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

[Unreleased]: https://github.com/prophetizer/franchisarr/compare/v0.16.0...HEAD
[0.16.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.16.0
[0.15.11]: https://github.com/prophetizer/franchisarr/releases/tag/v0.15.11
[0.15.10]: https://github.com/prophetizer/franchisarr/releases/tag/v0.15.10
[0.15.9]: https://github.com/prophetizer/franchisarr/releases/tag/v0.15.9
[0.15.8]: https://github.com/prophetizer/franchisarr/releases/tag/v0.15.8
[0.15.7]: https://github.com/prophetizer/franchisarr/releases/tag/v0.15.7
[0.15.6]: https://github.com/prophetizer/franchisarr/releases/tag/v0.15.6
[0.15.5]: https://github.com/prophetizer/franchisarr/releases/tag/v0.15.5
[0.15.4]: https://github.com/prophetizer/franchisarr/releases/tag/v0.15.4
[0.15.3]: https://github.com/prophetizer/franchisarr/releases/tag/v0.15.3
[0.15.2]: https://github.com/prophetizer/franchisarr/releases/tag/v0.15.2
[0.15.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.15.1
[0.15.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.15.0
[0.14.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.14.1
[0.14.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.14.0
[0.13.2]: https://github.com/prophetizer/franchisarr/releases/tag/v0.13.2
[0.13.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.13.1
[0.13.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.13.0
[0.12.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.12.1
[0.12.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.12.0
[0.11.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.11.1
[0.11.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.11.0
[0.10.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.10.0
[0.9.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.9.0
[0.8.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.8.1
[0.8.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.8.0
[0.7.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.7.0
[0.6.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.6.0
[0.5.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.5.0
[0.4.2]: https://github.com/prophetizer/franchisarr/releases/tag/v0.4.2
[0.4.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.4.1
[0.4.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.4.0
[0.3.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.3.0
[0.2.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.2.1
[0.2.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.2.0
[0.1.1]: https://github.com/prophetizer/franchisarr/releases/tag/v0.1.1
[0.1.0]: https://github.com/prophetizer/franchisarr/releases/tag/v0.1.0
