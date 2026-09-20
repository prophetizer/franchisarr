# Franchisarr

[Franchisarr](https://github.com/prophetizer/franchisarr) finds the films and TV shows missing
from the sets you already partly own — you have *Beverly Hills Cop* I and II but not III — and
sends them to Radarr or Sonarr.

## Setup

Franchisarr reads theme.park's variables natively, so the simplest install is its own
environment variable:

```yaml
environment:
  TP_THEME: nord
  # TP_DOMAIN: theme-park.dev     # or your self-hosted copy
  # TP_COMMUNITY_THEME: "false"
```

Or inject the stylesheet at your reverse proxy exactly as for any other app:

```html
<link rel="stylesheet" href="https://theme-park.dev/css/base/franchisarr/nord.css">
```

There is no Docker mod: Franchisarr ships its own image with the variable above built in.

## Screenshots

| Theme | |
|---|---|
| aquamarine | ![](../assets/franchisarr/aquamarine.jpg) |
| dark | ![](../assets/franchisarr/dark.jpg) |
| dracula | ![](../assets/franchisarr/dracula.jpg) |
| hotline | ![](../assets/franchisarr/hotline.jpg) |
| hotpink | ![](../assets/franchisarr/hotpink.jpg) |
| maroon | ![](../assets/franchisarr/maroon.jpg) |
| nord | ![](../assets/franchisarr/nord.jpg) |
| organizr | ![](../assets/franchisarr/organizr.jpg) |
| overseerr | ![](../assets/franchisarr/overseerr.jpg) |
| plex | ![](../assets/franchisarr/plex.jpg) |
| space-gray | ![](../assets/franchisarr/space-gray.jpg) |
