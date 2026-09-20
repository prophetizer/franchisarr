# theme.park base stylesheet

`franchisarr-base.css` is Franchisarr's base stylesheet for
[theme.park](https://theme-park.dev), for anyone hosting their own copy or submitting it upstream.

Install it as `css/base/franchisarr/franchisarr-base.css` and load it with a theme-options file,
exactly like any other app:

```html
<link rel="stylesheet" href="https://<your-theme-park>/css/base/franchisarr/franchisarr-base.css">
<link rel="stylesheet" href="https://<your-theme-park>/css/theme-options/nord.css">
```

## Why it's so short

Base sheets for other apps run to tens of kilobytes of deeply-nested selectors because they have
to override hardcoded colours in markup that was never meant to be themed. Franchisarr paints
entirely from CSS custom properties, so theming it means setting those properties — there is
nothing to fight, and no need for `!important`.

That also makes it durable: it targets variables rather than DOM structure, so a redesign of the
pages won't break it.

## You may not need it

Franchisarr ships the same mapping internally and always loads it, so pointing a theme-options
stylesheet at it — by `TP_THEME`, or by injecting the link at your reverse proxy — themes the app
without this file. This exists so Franchisarr can be themed through the standard theme.park
mechanism alongside everything else in a stack, and so it keeps working if the app ever stops
shipping its own copy.

## Keeping it honest

`tests/test_theme_park_base.py` in the Franchisarr repo checks that every class this file targets
still exists in the rendered pages, so a rename in the app shows up as a failing test rather than
as a quietly unthemed component.

## Submitting upstream

theme.park adds apps by pull request against `develop` of
[GilbN/theme.park](https://github.com/GilbN/theme.park); the docs are a second repository,
[themepark-dev/tp-docs](https://github.com/themepark-dev/tp-docs). Everything needed is here:

1. Copy `franchisarr-base.css` to `css/base/franchisarr/franchisarr-base.css`. Nothing else in
   the repo needs touching — `themes.py` generates the per-theme wrappers in CI.
2. The PR must show the app in every official theme option. `screenshots/` has the collection
   page under all eleven (aquamarine, dark, dracula, hotline, hotpink, maroon, nord, organizr,
   overseerr, plex, space-gray), captured through the app's own `TP_THEME` at 1440px.
3. For tp-docs, add a page under `docs/themes/` following any existing app page, and an entry in
   `mkdocs.yml`. `docs-page.md` here is a ready draft.
