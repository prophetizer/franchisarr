# Wikidata finds spin-offs

TMDb, Franchisarr's only metadata source, has no relation between a show and its spin-offs, so
spin-offs are found on Wikidata instead: shows are joined to Wikidata through their TMDb id (641
of 656 shows on the developer's library, 98%), and the relations pointing back at an owned show
(based on, follows, separated from) are what produce results, far more than the sparse explicit
"has spin-off". Matching on names is kept only as a search a person runs for one show, and its
results are marked possible.

## Considered Options

- **Name matching as the main source.** Finds "NCIS: Los Angeles" from "NCIS" but never *American
  Dad!* from *Family Guy*, and every loosening of the rule floods the list with unrelated shows
  that share a first word.
- **A community-maintained mapping file.** Planned in docs/DESIGN.md and never built: Wikidata
  already is that list, kept up by far more people than this project could gather.
- **AniList for anime.** Measured: of 190 related titles for 37 owned anime, 26 were series and
  the rest specials, OVAs, films and music videos; after what Wikidata already finds, it added
  one suggestion.

## Consequences

"Based on" also links foreign remakes, so those relations are filtered on original language and
title and anything left uncertain is marked possible rather than trusted. Spin-off discovery
depends on Wikidata's query service being reachable during a scan.
