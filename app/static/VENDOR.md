# Vendored front-end assets

Franchisarr serves these from its own `/static` path rather than a CDN. A self-hosted app on a
home network should not need outbound internet access to render its own UI, and pinning the files
here means a CDN outage, a network policy, or an upstream release cannot change what users get.
There is no build step and no npm (PROJECT_PLAN.md, "Frontend stack").

| File | Package | Version | Licence | SHA-256 |
|---|---|---|---|---|
| `pico.min.css` | `@picocss/pico` | 2.1.1 | MIT | `fbc9a63fc9fc9f72d12fd7fc9806e11fa9f77ae4f9cad146b27003a1119ba3db` |
| `htmx.min.js` | `htmx.org` | 2.0.10 | Zero-Clause BSD | `71ea67185bfa8c98c39d31717c6fce5d852370fcdfd129db4543774d3145c0de` |
| `alpine.min.js` | `alpinejs` (`dist/cdn.min.js`) | 3.16.3 | MIT | `e31d6d92aefd41979d3c66f994d3a6b77fafa5062aec67d13f3ec5099d70d5d6` |

## Updating

Fetch the pinned version from jsDelivr, then update the version and checksum above in the same
commit so the change is reviewable:

```sh
curl -sS -o app/static/pico.min.css "https://cdn.jsdelivr.net/npm/@picocss/pico@<version>/css/pico.min.css"
curl -sS -o app/static/htmx.min.js   "https://cdn.jsdelivr.net/npm/htmx.org@<version>/dist/htmx.min.js"
curl -sS -o app/static/alpine.min.js "https://cdn.jsdelivr.net/npm/alpinejs@<version>/dist/cdn.min.js"
sha256sum app/static/*.css app/static/*.js
```
