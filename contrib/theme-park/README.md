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
