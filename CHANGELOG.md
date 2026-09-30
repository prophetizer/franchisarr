# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.54.0] — 2026-09-30

### Added

- **▶ Trailers**, for everyone: a play button on missing films' tiles (collection, franchise and
  director pages), on the Surprise me card, on the back of a turned-over poster, and in Showcase's
  spotlight (the film that would finish that set). The trailer TMDb lists — an official one first,
  English first, a teaser if that's all there is — plays in a pop-up; Esc or a click outside
  closes it.

### Security

- The Content-Security-Policy gains `frame-src https://www.youtube-nocookie.com`, YouTube's
  privacy-enhanced player, and nothing else. Nothing from YouTube loads until a trailer is played.
  That one frame sends your install's origin as its referrer (the rest of the app still sends
  referrers only to itself), because YouTube's player refuses to play without one.

## [0.53.0] — 2026-09-30

### Added

- **🎲 Surprise me**, on the home page for everyone and at the top of Showcase's Ctrl+K box: a
  missing film picked at random from your collections and directors' lists — rated 6.5 or more on
  TMDb by at least 50 people, not one you've dismissed — with its plot, genres, where it's from, an
  Add button and **Spin again** (which never lands on the same film twice running). In Showcase
  the posters spin past like a slot machine before it lands.

### Fixed

- Showcase's shrinking spotlight kept pinning to where it started when something above it
  changed height after the page loaded (the scan status appearing, a Surprise me card); it
  re-measures now.

## [0.52.0] — 2026-09-30

### Added

- **Trophy case** (Browse → Trophy case), for everyone: every collection, franchise and
  director's filmography the library has finished, collections newest first (those complete
  before 0.49.0 started counting come after, undated), with milestone badges — first complete
  collection, then 10, 25, 50 and up — and how many to go for the next of each. Showcase frames
  the posters in gold, with a glint on hover, and a trophy from the last month glows.

## [0.51.0] — 2026-09-30

### Added

Showcase:

- **Posters turn over.** Click a missing film's poster, or rest the pointer on it, and its card
  flips to the plot, genres and TMDb score, with the card's own buttons; the pointer leaving, or
  ↺, turns it back.
- **Previews.** Pausing on a collection or franchise card opens a preview of its backdrop and
  the posters of what it's missing.
- **Completeness rings** beside each card's bar, and **a light running round** any card one film
  from done.
- **Ambient light**: the page's backdrop, blurred to nothing but colour, behind the whole page.
- **Quick search**: Ctrl+K (Cmd+K) opens a search box over any page; results as you type, the
  arrow keys and Enter to go.
- **Seasons**: in October a horror collection or franchise glows pumpkin as a few leaves fall;
  in December the top bar frosts over and a little snow falls on the home page.

Phones get the flips, rings, light and search, but no previews or ambient light.

### Upgrading

- The first scan after upgrading refetches every cached collection from TMDb once, to pick up
  each film's plot and genres (they weren't kept before). It takes a little longer than usual;
  until it's run, a flipped poster asks TMDb directly, and no page counts as horror yet.

## [0.50.1] — 2026-09-30

### Fixed

- Showcase's dashed frame round a missing film ran on below its poster whenever the card was
  taller than the picture, and took the page's colour even when that clashed. It now fits the
  poster and is a quiet grey, lighting up in the page's colour only when pointed at.

## [0.50.0] — 2026-09-30

### Added

Showcase:

- **The spotlight shrinks as you scroll.** It stays where it is and shrinks to a slim strip, its
  kicker and bar folding away, so the poster rows come up twice as fast; then it scrolls off.
  Phones and "reduce motion" get a shorter spotlight that stays put.
- **A frosted top bar**, pinned while you scroll, tinted with the page's colour and more compact
  than Classic's.
- **Posters sharpen in** from a blur as they load, with a shimmer where each will be.
- **Missing films as gaps on the shelf.** On collection, franchise and director pages the films
  you don't have are dimmed in a dashed outline and come up in colour when pointed at; the ones
  you have are shown at full strength.
- **A loading bar** — a thin glow across the top while an add, scan, sync or saved form works.

## [0.49.1] — 2026-09-29

### Changed

- Showcase's spotlight leads with the best-known collections one or two films from done — the most
  TMDb votes across their films — so The Lion King and Star Trek come before Frosty the Snowman.
  Sorting by size (0.49.0) changed little on a library whose nearly-done sets are all small.

## [0.49.0] — 2026-09-29

### Added

Showcase, step 3:

- **Confetti for a completed collection.** When a scan finds a collection newly complete, each
  person in the Showcase look gets a "Collection complete!" message and a burst of confetti, once,
  on their next visit to the home page or that collection. (No confetti on phones or with reduce
  motion; the message still shows.) A collection is celebrated the first time only.
- **A film reel while a scan runs**, and the progress bar running like film.

### Changed

- The spotlight leads with the collections fewest films from done, and among those the bigger
  sets and ones with a logo — no more three-film sets ahead of a nearly-finished big one.

### Upgrading

- Collections already complete when you upgrade aren't celebrated: the first scan after it
  records them quietly.

## [0.48.0] — 2026-09-29

### Added

Showcase, step 2:

- **Spotlight** on the home page: a full-width banner of the collections you're closest to
  completing — backdrop, logo, "one film away" — turning every seven seconds (pausing while
  pointed at), with dots to choose; the page's glow follows the slide. Poster rows get arrows to
  slide them along, and their cards arrive in turn.
- **The release strip plays** when it comes on screen: posters fly in in release order, the ones
  you own light up from grey, their ticks pop, and a ring beside the heading fills to how much of
  the set you have.
- **A poster grows into the page it opens**, and a spotlight's backdrop into the collection's
  banner, using the browser's view transitions (Chrome, Edge, Safari 18.2+; others just navigate).

Classic is unchanged; the spotlight and the ring are in the page but hidden there (their images
aren't fetched).

## [0.47.0] — 2026-09-29

### Added

- **Showcase look**, per person: **✦ Showcase look** under your name (and in the phone menu)
  switches your account from Classic — which stays the default for everyone — to a flashier look:
  - franchise and collection banners full-width, the backdrop slowly zooming and scrolling slower
    than the page, the title and poster sliding in;
  - the page glowing with its artwork's colour;
  - headline numbers counting up;
  - cards and posters tilting toward the pointer with a glare, and lifting on hover; grids and
    completeness bars animating in.
  Phones keep the fades and the glow but not the parallax or tilt; "reduce motion" turns the
  motion off. **◻ Classic look** switches back.

### Changed

- A banner's backdrop sits in its own clipping frame (no visible change in Classic).

## [0.46.3] — 2026-09-29

### Fixed

- A franchise with no TMDb collection at all (Arrowverse, Cloverfield) showed no poster; it now
  shows its earliest title's own, as 0.46.2 did for franchises spread over several collections.

## [0.46.2] — 2026-09-29

### Fixed

- Franchise titles without a poster are now filled on every scan. 0.46.1 filled them only when
  the franchise data itself refreshed, which is weekly, so its "after the next scan" was wrong.
- A franchise with too few posters for a mosaic, and no collection that stands for it, shows its
  earliest title's own poster instead of none.

## [0.46.1] — 2026-09-29

### Fixed

- **A franchise wore the wrong collection's artwork.** The Marvel Cinematic Universe's page read
  "Iron Man", logo and poster, because it borrowed from whichever collection came first. A
  franchise now takes a collection's logo only when the collection has its name (Star Wars → Star
  Wars Collection), and its poster only then or when the collection holds most of its films.
  Otherwise the page is headed with the franchise's own name and its poster is a 2×2 mosaic of its
  films. Search's franchise cards follow the same rule.
- **Owned titles in no collection had no poster** on franchise pages and in the release strip
  (The Incredible Hulk, the Marvel One-Shots). The next scan looks each one up on TMDb, once.
- The release strip counted what's coming in its total ("54 of 56") where the banner didn't
  ("54 of 55"); it now says "54 of 55, 1 coming".

### Upgrading

- The missing posters appear after the franchise data next refreshes — see 0.46.2, which makes
  that the next scan.

## [0.46.0] — 2026-09-29

### Changed

- **Playlists → Your playlists**: each server's playlists are a collapsible section, closed to
  start, with a count of playlists, how many sync and how many have a problem in its heading.
- **Filter chips** — All, Syncing, Not syncing, Problems — beside the text filter; a filter opens
  the sections with matches and closes them again when cleared. "Tick every playlist" ticks the
  ones shown.
- **Status chips** replace the lines under each synced playlist: one per server (✓ Attic 18/20,
  ⚠ Attic blocked, ✕ for an error), opening in place for the details, the missing titles with Add,
  and Link them.
- A **save bar** stays at the bottom of the screen once anything has changed, counting the
  changes, with Save and sync and Undo.
- **Playlists → Franchisarr's** is grouped into collapsible Franchises, Collections and Directors
  sections, each playlist with a thumbnail and a chip per server.

## [0.45.0] — 2026-09-29

### Added

- **The set in release order**, at the top of every franchise and collection page: a strip of
  posters with what you own in colour and what you don't dimmed, so the holes in the run show at a
  glance. Picking a dimmed one opens the add dialog.
- **Poster rows on the home page**: the collections closest to complete, films coming in the next
  90 days in franchises you own, and titles just added to your library from sets you're
  collecting. The summary cards are still there, smaller, below them.

### Upgrading

- "Just added" starts empty and fills as scans find new titles: when earlier ones arrived was
  never recorded (migration 0031 adds the date). A fresh install's first scan doesn't count
  either — that's the whole library, not what's new.

## [0.44.0] — 2026-09-29

### Added

- **How complete each set is, at a glance**: a thin progress bar under the counts on every
  collection, franchise and director card. (Sort by **Completeness** to put the nearly-finished
  ones first.)

### Changed

- **The playlist control moved into the page's banner** on franchise, collection and director
  pages: one **Make a playlist** menu instead of a row of buttons, and once Franchisarr is keeping
  one, "✓ Playlist kept on …" beside a **Refresh playlist** button.
- **Quieter tiles**: titles you own no longer repeat why they're in a franchise ("Wikidata files
  it under …"); **Not part of this collection** moved behind a ⋯ on each missing film; card
  titles are underlined only when pointed at.
- **Collections toolbar**: sort, the started-watching filter and the rating floor sit on one row,
  with **Rescan my library** beside the heading. The rating floor's explanation is its tooltip.
- The **Playlists** link in the top bar lines up with the menus beside it.

## [0.43.0] — 2026-09-29

### Added

- **Playlist sync works both ways.** A title added to a synced playlist on any server is added
  on the others at the next sync, after the title it followed; one removed on any server comes
  off the others. The original's order wins. A title a server can't hold is never read as
  removed there, and titles only one server can hold (a home video, a library Franchisarr doesn't
  scan) stay where they are.
- **Renames follow**: renaming a synced playlist on any server renames it on the others.
- **Link them** on a copy that's blocked by a same-named playlist: that playlist becomes the copy
  and the two lists are merged, so titles from either end up in both.
- **Add** beside a title that couldn't be copied: a film Radarr doesn't have, or an episode's show
  Sonarr doesn't have, opens the usual add dialog. The page also lists what the original's own
  server is missing from the others.

### Changed

- Deleting a copy on its server now stops copying there (that server is unticked for the
  playlist) instead of the copy being made again at the next sync. Deleting the original still
  deletes its copies.
- A copy is edited in place rather than deleted and recreated, so it keeps its id and poster.
- A Plex smart playlist stays one-way: its contents follow its rules.

### Upgrading

- Nothing changes on your playlists by upgrading. The first sync after it treats each synced
  playlist's original as it stands, as the one-way sync did (so edits made to a copy since the
  last sync are replaced one last time); from the sync after that, edits on any server count.

## [0.42.0] — 2026-09-29

### Added

- **Franchisarr's playlists are kept current.** A playlist made from a franchise, collection or
  director page now joins a set Franchisarr keeps: after every scan (and at every sync) the
  titles you've added go in where they belong and the ones you've removed come out. It's edited
  in place, so it keeps its poster and its spot in your apps, and a new server gets it at the
  next sync. Deleting one on any server deletes it on the others and drops it from the set; a
  server that's off or can't be reached is never taken for a deletion.
- **One Playlists page with tabs** — Your playlists, Franchisarr's, Clean up, History — in place
  of the four-item menu. Above the tabs: a status line (what's syncing and kept, the last run,
  titles that couldn't be copied), **Sync now**, and the schedule.
- **Schedule presets**: only after scans, or also every hour, 6 hours, 12 hours, daily at 04:00,
  or a cron schedule of your own.
- **Default "copy to" servers** for playlist sync, with **change** on any playlist that should go
  somewhere else — instead of a row of server boxes on every playlist.
- The **Franchisarr's** tab lists every kept playlist with what it holds on each server, a
  **Remove** button, **Put them on** for which servers they go on, and **Add many at once**.

### Changed

- "Sync every playlist" is now **Tick new playlists automatically**, beside the default servers
  at the top of the checklist; the separate switches form is gone.
- **Clean up** on one server also stops Franchisarr's playlists going to that server, rather
  than having the next sync read it as someone deleting them.
- Syncs no longer replace a playlist by deleting and recreating it anywhere: every change is an
  edit by id. On Jellyfin 12.1, which refuses to move an entry, the order is fixed by rewriting
  from the first out-of-place title onward.

### Removed

- The **Keep Franchisarr's playlists on every server** switch: keeping them on every server is
  what the set does now.

### Upgrading

- The first sync after upgrading (the next scan, or **Sync now**) takes the "… (Franchisarr)"
  playlists already on your servers into the set and brings each up to date in place, adding
  titles you've got since it was made. If you'd rather it didn't keep one, **Remove** it on the
  Franchisarr's tab, or delete it on any server.
- Bookmarks to `/playlists/add-all` and `/playlists/delete` still work; they open the tab that
  holds them now.

## [0.41.1] — 2026-09-29

### Fixed

- The Sync page described its schedule as "Next scheduled scan"; it now says "Next scheduled
  sync", and "No sync schedule" when none is set.

## [0.41.0] — 2026-09-29

### Added

- **A Playlists menu:** Sync, Add playlists, Delete playlists and History, all in one place. Bulk
  add and delete moved there from the Servers page, and Playlists moved out of Manage.
- **A sync checklist.** The Sync page lists every playlist on every server with a checkbox, a
  filter and a tick-all per server; Save and sync applies the choice and syncs at once.
- **Choose which servers get each copy.** Every synced playlist has a box per other server,
  all ticked by default — which also includes servers added later. Unticking one deletes the
  copy sync made there.
- **A sync schedule** of its own, a cron expression like the scan schedule's, alongside syncing
  after every scan and Sync now.
- **Sync history:** the last 30 syncs, what started each, and what it created, updated,
  deleted, blocked or failed.

### Upgrading

- Migration 0028. Playlists already syncing keep copying to every other server; no schedule is
  set until you add one.

## [0.40.0] — 2026-09-28

### Changed

- **A menu instead of one long line of links.** The top bar is now **Browse ▾** (Franchises,
  Collections, Spin-offs, Upcoming, Directors), **Manage ▾** for administrators (Servers,
  Libraries, Instances, Playlists, Users, Settings, Activity — Playlists and Users were missing
  from the bar before), a menu under your name (Preferences, Password, light/dark, Sign out;
  Activity for household members), and search at the far right. Menus open on click or tap,
  one at a time, and close on a click elsewhere or Esc; the one holding the page you're on is
  highlighted. On a phone the bar is the logo, search and a ☰ that lays every section out.
  Pressing **/** anywhere outside a text box goes to Search.

## [0.39.0] — 2026-09-28

### Added

- **Sync every playlist.** A switch on the Playlists page makes every video playlist on every
  server sync, including ones made later. Any one can still be switched off (Don't sync / Stop
  syncing), and it stays off. Turning the switch off stops what it started and leaves playlists
  you picked by hand syncing; copies stay as ordinary playlists.
- **Keep Franchisarr's playlists on every server.** A second switch: a "… (Franchisarr)"
  playlist on one server is built on the others from their own libraries — each complete for
  its server, not a copy trimmed to the titles both hold — and deleting it on any server
  deletes it everywhere. Sync remembers which servers each was on, so a server that can't be
  reached is never taken for a deletion.

### Upgrading

- Migration 0027. Both switches start off.

## [0.38.0] — 2026-09-28

### Added

- **Playlist sync.** A new Playlists page (linked from Servers and Settings) lists every
  playlist on each server with a Sync switch. A synced playlist is copied from its home server
  to every other server that's on — after each scan, and on Sync now — matched title by title
  through TMDb (films by their own id, episodes by show, season and episode). Titles another
  server doesn't have are left out and listed with the reason. Copies take the same name and the
  source's own poster; edits to a copy are overwritten at the next sync, deleting the source
  deletes its copies (only ones sync made), and a same-named playlist sync didn't make is never
  touched — that copy shows as blocked. Plex smart playlists are copied as they stand at each
  sync. It uses the accounts Franchisarr already uses, leaves out Franchisarr's own and
  music/photo playlists, and notifies only when a sync fails.

### Upgrading

- Migration 0026 adds two tables for playlist sync. Nothing syncs until you switch a playlist on.

## [0.37.0] — 2026-09-28

### Added

- **Playlist bulk actions** on the Servers page, each on one server or every server:
  - **Add playlists** for every franchise, collection and/or director (ticked, with how many
    each would make). It runs in the background with a progress bar and a Stop button, and
    skips a set with fewer than two titles on a server. An existing playlist is rebuilt.
  - **Delete Franchisarr's playlists**, as before.
  - **Delete all playlists** in the account Franchisarr uses — the Plex token's owner, or the
    Jellyfin/Emby *watched as* user — including ones made by hand. It lists every playlist first
    and needs DELETE typed (checked by the server, not only the page). Jellyfin 12 doesn't say
    who owns a playlist, so on Jellyfin and Emby a playlist shared with that account may be
    included, and the warning says so.

### Changed

- The per-server **Delete playlists** buttons moved into Bulk actions.

## [0.36.0] — 2026-09-28

### Added

- **Search.** A magnifying glass in the top bar opens a search over everything Franchisarr
  knows: collections and franchises you own part of, directors with a page, and every film and
  show it has met — in the library, a collection, a franchise, a director's filmography or a
  spin-off list. Results update as you type (the address follows, so a reload or a shared link
  keeps the search) and are grouped by kind. Each title says whether it's in your library and
  on which server, already in Radarr/Sonarr or requested, hidden by you, not out yet, or
  missing, and links to the pages it belongs to; missing ones have Add (administrators) and Not
  interested. Matching ignores case, accents and punctuation. It's local — no TMDb request per
  keystroke — and at 20,000 films answers in about a second.

## [0.35.0] — 2026-09-28

### Changed

- **The sign-in page asks how you want to sign in.** A "Sign in with" dropdown lists every way
  in the install offers — each Emby or Jellyfin server, Plex, and the local account last — and
  shows only that form, where it used to stack them all on one page. Several Jellyfin or Emby
  servers are each an entry of their own, replacing the server picker inside the form. The
  choice is remembered in the browser, and a sign-in that fails comes back on the method that
  failed. With a single way in there's no dropdown.

## [0.34.0] — 2026-09-28

### Changed

- **Music-video collections no longer lead a director's missing films.** A music-video
  director's credits are full of compilations — Madonna's *The Immaculate Collection*, Michael
  Jackson's *Video Greatest Hits: HIStory* — and with a few dozen votes at 8+ they topped
  Scorsese's and Fincher's lists and went into the directors import list. They're now folded
  into their own collapsed section on the director's page. They're recognised by TMDb's `video`
  flag with Music as the only genre, which on twelve filmographies picked out exactly those
  and nothing else (the flag alone would also catch *Grindhouse*).
- **The README screenshots show a fuller sample library:** eight directors and eight
  franchises, three of them across film and TV, and each shot is cut to its page instead of
  ending in empty space.

### Upgrading

- The next scan re-reads every director's filmography once, so it takes a few minutes longer
  than usual on a large library.

## [0.33.3] — 2026-09-28

### Fixed

- **Pages that said "Plex" to everyone.** Change Password told Jellyfin and Emby accounts that
  they sign in with Plex and that their password lives at plex.tv; it now names the server
  they actually sign in with. The backup warning in Settings said the full download holds "your
  Plex token" when it holds every media server's credentials (and the Seerr and fanart.tv keys,
  which it didn't mention). Adding a Jellyfin or Emby server no longer suggests naming it
  "Living room Plex".

## [0.33.2] — 2026-09-28

### Fixed

- **The home page no longer calls every library a Plex library.** "Scanning 6 Plex libraries"
  counted Jellyfin's and Emby's too, and libraries on servers that were turned off. It now says
  what a scan reads, per server: "Scanning 6 libraries: 2 on Emby, 2 on Jellyfin, 2 on Plex."
  The home and Collections pages' other "your Plex libraries" wording now says "your libraries".

## [0.33.1] — 2026-09-28

### Fixed

- **A scan that can't start now says why.** Without a TMDb key (or a media server), pressing Scan
  did nothing at all: the refusal was an error response the page silently dropped, and nothing
  was logged. The reason now appears next to the button with a link to fix it, the home page
  says so before you press anything, and the log records it. A missing TMDb key is also logged
  at startup.
- **A TMDb key added to `.env` after the first start is picked up.** The first boot saved an
  empty key and never read the environment again. `TMDB_API_KEY` now fills the setting at every
  start while it's still empty. A key already saved is never overwritten, and the log names any
  other `.env` value that's being ignored in favour of the saved one.

### Added

- **TMDb and fanart.tv keys in Settings.** Both can be added or changed in the app, as the README
  always said. Keys are masked to the last four characters, leaving a field blank keeps the
  saved key, and a new TMDb key is checked with TMDb before it's saved.

## [0.33.0] — 2026-09-28

### Added

- **A playlist on one server, or on all of them.** With more than one server, "Make a playlist"
  on a franchise, collection or director page becomes a row of buttons: On every server, and
  one for each server.
- **Delete Franchisarr's playlists.** The Servers page has Delete playlists on each server and
  Delete playlists on every server. Pressing one deletes nothing: it lists exactly which
  playlists would go, from where, with a warning, and deletes only when you press
  "Yes, delete N playlists". Only playlists named "… (Franchisarr)" are ever deleted, on
  Jellyfin and Emby including copies in other users' accounts; playlists anyone made by hand
  are never touched.

## [0.32.0] — 2026-09-27

### Added

- **Turn a server off and on in one click.** Each server on the Servers page has a Turn off /
  Turn on button, instead of Edit and a checkbox.
- **Use only this server.** Turns every other server off, remembering which ones it turned off.
  While it's on, a banner on every page names them and offers to turn them back on, so
  films that look missing are never a mystery. Signing in through a server it paused still works,
  so a session that lapses mid-test can't lock you out.
- **Scan one server.** Each server has its own Scan button, which reads only that server's
  libraries and leaves the others as they were.

### Changed

- **A server that's turned off now holds nothing.** It was already skipped by scans and
  playlists, but what it had scanned still counted as owned and still showed as "on" it, so
  turning a server off changed nothing on the pages. Now its titles stop counting until it's
  back on. Nothing is deleted, so turning it back on is instant. A title a server that's off
  holds is never announced as a new gap in notifications.

### Upgrading

- If you have a server turned off, titles only it holds now show as missing. Turn it back on
  under Servers if you want them counted.

## [0.31.1] — 2026-09-27

### Security

- **Printing a database row no longer shows its credential.** The text form of a media server,
  instance, user or session record included its token, key or hash, so a stray print or log
  line could reveal it. Those fields are now left out of it.

## [0.31.0] — 2026-09-27

### Added

- **Playlists on Jellyfin and Emby**, with the same release order, square poster and rebuild
  behaviour as Plex. The button, now **Make a playlist**, builds one on every server that holds
  titles from the page. On Jellyfin and Emby the playlist goes to the server's "watched as" user.
  Tested against real Jellyfin 12.1.0 and Emby 4.10.0.40 servers: building, rebuilding in place,
  the order, the counts and the poster.

### Fixed

- **Jellyfin 12 requests now use camelCase parameter names** (`userId`, not `UserId`).
  Jellyfin 12 matches them case-sensitively, so some requests were ignored and others refused.
  Library scans happened to be unaffected, but playlists and per-user lookups weren't.

## [0.30.2] — 2026-09-27

### Fixed

- **Jellyfin 12 rejected Franchisarr's API key.** Jellyfin 12 no longer accepts the key in the
  `X-Emby-Token` header, and answered every request with 401, so a Jellyfin 12 server couldn't
  be tested, listed or scanned. Franchisarr now sends it in Jellyfin's
  `Authorization: MediaBrowser … Token="…"` header, which older Jellyfin versions accept too.
  Emby is unchanged. Checked against real Jellyfin 12.1.0 and Emby 4.10.0.40 servers.

## [0.30.1] — 2026-09-27

### Changed

- **Playlist posters and the result message count shows as well as films and episodes**, e.g.
  "13 films · 3 shows · 279 episodes". Anything that's zero is left out.
- `playlist_service.repost_all()` gives every existing Franchisarr playlist a fresh poster
  without touching its contents, reading the counts from the playlist in Plex.

## [0.30.0] — 2026-09-27

### Changed

- **Sorting is a dropdown and a direction button** instead of a row of links, the same on every
  list page. The dropdown picks what to sort by, and applies at once. The button beside it says
  which way the list runs ("↓ Most first", "↑ Oldest first", "A → Z") and reverses it, so every
  sort now works both ways.
- Options merged now that direction is separate:
  - "almost complete" is **Missing, fewest first**;
  - "newest" and "oldest" are one **Release date / First aired** option;
  - Upcoming's "soonest" is **Release date, soonest first**.
- Items with no date or no rating stay at the end in both directions, and fully owned
  collections and directors still trail.

### Upgrading

- Sorts saved in 0.29.0 carry over, including "almost complete", and old `?sort=` links still
  work.

## [0.29.0] — 2026-09-27

### Added

- **Sort options on every list**, as "Sort by" links like Collections already had:
  - **Franchises:** most owned, most missing, most complete, newest, name.
  - **Collections and Directors** gain most missing, almost complete (one or two missing first),
    most complete and newest missing.
  - **Spin-offs:** by show, name, newest, oldest.
  - **Upcoming:** soonest, collection, name.
  - **The tiles on a collection, franchise or director page:** release date, rating, name.
    Franchise pages offer release date and name only, since their titles carry no rating.
- **Each page remembers your last sort on your account** (migration 0024), so it's the same on
  every device. A link with `?sort=` always wins, so bookmarks and shared links mean what they say.

## [0.28.1] — 2026-09-27

### Fixed

- **Playlist posters are square.** Plex shows playlists square, so the tall poster was cropped
  to its middle and lost "In release order" and the counts. The poster is now the whole
  backdrop across the top, uncropped, above a dark panel with the name and counts. Long names
  wrap to two lines, and a director's poster grid fits the number of films so no cell is empty.

## [0.28.0] — 2026-09-27

### Added

- **Playlists get their own poster** in place of Plex's four-tile mosaic. It's the franchise or
  collection backdrop, darkened at the foot, with the name, "In release order" and the number of
  films and episodes; director playlists, having no backdrop, get a mosaic of the director's
  films. Franchisarr downloads the artwork from TMDb and uploads the poster to Plex, so this
  is the one time the server itself fetches images (not with `SHOW_ARTWORK=false`). If the
  poster can't be made, the playlist is still built.
- New dependency: Pillow, to compose the poster. The Noto Sans font it uses ships with the app,
  with its licence.

## [0.27.0] — 2026-09-27

Plex playlists of a franchise, collection or director, in release order.

### Added

- **Make a Plex playlist** on franchise, collection and director pages (administrators only).
  Everything you own on the page goes into one Plex playlist in the order it was released:
  films by release date, and every episode of the franchise's shows placed by its air date, so
  films and TV interleave as they were broadcast. Specials are left out. The playlist is named
  "*name* (Franchisarr)", and pressing the button again rebuilds it. Plex only for now;
  Jellyfin and Emby titles are left out, and the result says how many.

## [0.26.0] — 2026-09-26

The rest of the security review's findings, and a Users page.

### Added

- **Settings → Users**: everyone who has signed in, with sign out everywhere, revoke API key
  and remove. Accounts are still made only by signing in.
- A **Revoke the key** button next to your API key.

### Security

- **Admin rights follow the media server at every sign-in.** They used to be added but never
  taken away, so someone who handed their Plex server over, or was demoted on Jellyfin, stayed
  an admin here.
- **A crafted backup could make a stranger an admin.** Importing now accepts only known settings
  and each section's own fields, checks their values, ignores ids and server identities, and adds
  media servers switched off until you review them.
- **API keys are stored as hashes**, as session tokens already were, and keys in URLs
  (`?api_key=`) no longer appear in logs after a restart.
- **The webhook/Apprise URL is no longer shown in full** on the Settings page. It's masked, and a
  blank field keeps it. A crafted notification format can no longer run script there.
- **Requests from sibling subdomains are refused.** An XSS in another app on your domain could
  otherwise have posted to Franchisarr with your session.
- **Uploads are capped as they arrive.** The 2 MB limit only checked the declared size, so an
  undeclared (chunked) upload of any size was read, even when anonymous.
- **Open redirect after Plex sign-in closed**: a `next` link with a backslash sent you elsewhere.
- Smaller fixes:
  - release links must be `https`;
  - calendar titles can't inject lines;
  - a long run of spaces in a title no longer stalls matching;
  - huge page numbers no longer cause errors;
  - login timing no longer reveals which usernames exist;
  - `/docs` and `/openapi.json` are gone;
  - logout is POST-only;
  - settings pages and downloads are never cached;
  - the database is readable only by the app's user.

### Upgrading

- Existing API keys keep working: they're hashed in place on first start. Downgrading afterwards
  clears them, so generate new ones if you ever go back.
- Media servers in an imported backup now arrive switched off — switch them on under Servers.
- `PUID=0` / `PGID=0` are refused (the container won't start), and an `ADMIN_PASSWORD` under 8
  characters no longer creates the first-boot admin account.
- Anyone who was an admin here but no longer is on the media server loses admin at their next
  sign-in.

## [0.25.1] — 2026-09-26

Two sign-in fixes from a security review. Update if Franchisarr can be reached from the internet.

### Security

- **The sign-in rate limit could be bypassed.** It counted failures against the first address in
  the `X-Forwarded-For` header, which the visitor writes themselves, so a different made-up
  address on every attempt meant unlimited password guesses — against the local admin, and
  through the Jellyfin/Emby form against those servers' accounts. The header is now believed
  only when the request comes from a proxy on your own network, and only the part that proxy
  added. Failures are also counted per username across all addresses, so spreading guesses
  over many real addresses doesn't help either.
- **The Plex sign-in PIN could be guessed.** The browser held plex.tv's PIN number in a cookie,
  and those numbers are sequential; someone who guessed the number of a PIN you were signing in
  with could collect your session. The PIN now stays on the server; the browser gets a random
  handle that works once. Starting a Plex sign-in is rate-limited.

### Added

- `TRUSTED_PROXY_HOPS` (default 1): how many reverse proxies are in front of the app. Set 2 if
  another proxy sits in front of your usual one, such as Cloudflare's proxy in front of
  Traefik, so the rate limit sees visitors' real addresses.

## [0.25.0] — 2026-09-26

Only administrators can sign in now, unless you choose otherwise.

### Security

- **Sign-in is limited to administrators by default.** Before, anyone your Plex server was shared
  with could sign in, as could any account on a configured Jellyfin or Emby server. Now only the
  Plex server's owner, Jellyfin/Emby administrators and the local admin account are let in.
  **Settings → Who can sign in** lets everyone else in if you want that.
- **People who aren't administrators can only browse and hide titles for themselves.** Before,
  they could also add to Radarr and Sonarr, request through Seerr, start scans, and change
  household settings, including the scan schedule and the **notification webhook URL**, as well
  as "not part of this collection", spin-off mappings and preferences. All of that is admin-only
  now, and the controls are hidden from them. The Servers, Instances, Libraries and Settings
  pages are admin-only too.

### Upgrading

- If people who aren't administrators already use your install, they are signed out after this
  update, and their API keys stop working, until you turn on **Settings → Who can sign in**.
  Administrators aren't affected.

## [0.24.0] — 2026-09-25

Every page that lists films or shows now uses the same tiles as the Collections page.

### Changed

- The collection, franchise and director pages show each film or show as a poster tile, in the
  same grid as the Collections page, not as a row in a list. Missing and coming-soon titles
  get full tiles with their buttons; titles already in your library get smaller tiles below them.
- Upcoming is one grid in date order. It used to put each month under its own heading, which
  usually meant one tile per heading and a single column down the page. Each tile now shows
  its month and date, with undated films labelled "No date yet" at the end.
- On Spin-offs, your confirmed mappings, the possible matches from "Search a single show" and
  the show library it searches from are tiles too, with posters.
- Film and show posters load at TMDb's 185 px size, not 92 px, so they stay sharp at tile size
  on a high-resolution screen.

### Fixed

- The README's spin-offs screenshot showed *Alvin and the Chipmunks* as a spin-off of *Friends*:
  the sample library used the wrong TMDb id for *Joey*.

## [0.23.2] — 2026-09-25

A correctness pass over the README and the app's own wording, each claim checked against the
code rather than memory.

### Fixed

- The Settings page said notifications are "sent after a scheduled scan". They go out after any
  scan that finds something new, scheduled or started by hand -- never the very first.
- `cli.py --help` described `scan` as scanning "your Plex libraries" and `instances` as managing
  "Radarr instances"; it covers every media server, and Sonarr instances too.

### Documentation

- The README's CLI example, `python cli.py scan movies`, failed ("unexpected extra argument"):
  `scan` takes no argument and covers films and TV together.
- The development instructions crashed on a fresh checkout, because the database defaults to
  `/config`; they now set `DB_PATH` and an admin account.
- "Environment variables are only read on first boot" was wrong for about half of them --
  `BASE_URL`, `TZ`, `PUID`/`PGID`, `LOG_LEVEL`, `SESSION_COOKIE_SECURE`, `SHOW_ARTWORK`, the
  `TP_*` variables and `UPDATE_CHECK` are read on every start. The README now says which is which.
- "Every feature was measured against a real library before it shipped" overstated it: the core
  was, the integrations weren't all -- now said precisely, with a link to what's been tested.
- The Seerr history described a rename and an abandonment; per Seerr's own announcement of
  10 February 2026, the Overseerr and Jellyseerr teams merged into it.
- Smaller corrections: the import lists answer to Sonarr's settings as well as Radarr's; servers
  in `.env` are seeded on first boot only; the theme note no longer implies the whole app
  fetches nothing; the example version, host and username are current and generic.

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

- **The request target is called Seerr.** The Overseerr and Jellyseerr teams merged into
  [Seerr](https://github.com/seerr-team/seerr) in February 2026 and Overseerr's repository was
  archived, so
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
