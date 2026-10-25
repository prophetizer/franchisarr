# Franchisarr

Franchisarr compares what is in a household's media library with the groups of films and shows
those titles belong to, and names what is missing. These are the words it uses for that.

## Sets

**Set**:
A group of titles a library is measured against: a collection, a franchise, or a director's
filmography.
_Avoid_: Series, saga, group

**Collection**:
A set of films that TMDb groups as one series, such as *Beverly Hills Cop* I–III.
_Avoid_: Franchise (for a collection), film series

**Franchise**:
A set of films and shows that belong to one fictional world, which may hold several collections.
_Avoid_: Universe, collection (for a franchise)

**Filmography**:
The films one director has directed, as a set.
_Avoid_: Director collection

## Where a title stands

**Owned**:
In the library, on a media server that is switched on.
_Avoid_: In your library (as a term), have, collected

**Wanted**:
Not owned, but already on its way: Radarr or Sonarr has it or is fetching it, or it has been
requested through Seerr.
_Avoid_: Requested, known, in Radarr, queued

**Missing**:
Released, neither owned nor wanted, and counted against its set.
_Avoid_: Gap (for a single title)

**Upcoming**:
Announced but not yet released, whether or not it has a date; never counted as missing.
_Avoid_: Coming soon, not out yet, announced, unreleased

**Below the rating floor**:
Missing, but rated under the household's minimum rating, so folded rather than counted.
_Avoid_: Hidden (for this), filtered

**Not interested**:
A title one person has said they don't want; it stops being suggested to them.
_Avoid_: Dismissed, hidden (for a title)

**Hidden**:
A whole set one person has taken out of their own lists.
_Avoid_: Excluded, removed

**Folded**:
Collapsed into its own section on the page it came from, rather than counted or deleted.
_Avoid_: Filtered out, removed

**Complete**:
A set with nothing missing; upcoming and folded titles don't count against it.
_Avoid_: Finished, full

**TV film**:
A feature-length film made for television rather than cinemas.
_Avoid_: TV movie, extra

**Special**:
A one-off programme tied to a set, such as a holiday special.
_Avoid_: Extra, bonus

**Short**:
A film too short to count as a feature.
_Avoid_: Extra, short film

## Shows

**Spin-off**:
A show that grew out of one the household owns: a spin-off, sequel or prequel.
_Avoid_: Related show, follow-up

**Possible**:
A spin-off suggested on weaker evidence, which a person should check before trusting.
_Avoid_: Heuristic, unconfirmed, suggested

**Continuation**:
A film or show that carries an owned title into the other medium, such as the series a film led to.
_Avoid_: Crossover, cross-media

## Order

**Release order**:
A set's titles in the order they came out.
_Avoid_: Timeline (for release order)

**Story order**:
A set's titles in the order their stories happen, kept once for the whole household.
_Avoid_: Chronological, timeline order, in-universe order

## Household

**Household**:
Everyone who can sign in to one install of Franchisarr.
_Avoid_: Users, family, instance

**Administrator**:
A member of the household who runs the install: adds titles, scans, and changes household settings.
_Avoid_: Admin user, owner

**Member**:
Someone who signs in through a media server shared with them, only if an administrator allows it.
_Avoid_: Guest, friend, user

**Preference**:
A choice one person makes for themselves, such as how the app looks.
_Avoid_: Setting (for a personal choice)

**Household setting**:
A choice that applies to everyone using the install, made by an administrator.
_Avoid_: Preference (for a household choice), global setting

**Switched off**:
Said of a media server whose titles stop counting as owned until it is switched on again.
_Avoid_: Paused, disabled, turned off

**Version**:
One file of a film in the library; a film can have several.
_Avoid_: Copy (for a file), duplicate

**Copy**:
A playlist as it exists on one media server.
_Avoid_: Replica, instance

## Activity

**Scan**:
Reading the library from the media servers and working out what is missing.
_Avoid_: Rescan, refresh, sync (for a scan)

**Refresh everything**:
A scan that also fetches every set afresh from TMDb instead of using what it already knows.
_Avoid_: Full scan, force refresh

## Appearance

**Look**:
How the app is drawn for one person: Classic or Showcase.
_Avoid_: Theme, style, skin

**Light/dark mode**:
The colour scheme, light or dark.
_Avoid_: Theme (for light/dark)

**Theme**:
A theme.park stylesheet that repaints the app to match the rest of a homelab.
_Avoid_: Skin, look
