# Security Policy

Franchisarr stores API keys for your Plex, Radarr, and Sonarr instances (and your own TMDb key), so
security issues affecting how those secrets are stored, transmitted, or exposed are treated as a
priority.

## Supported Versions

While Franchisarr is pre-1.0, only the latest tagged release is supported with security fixes.

| Version        | Supported          |
| -------------- | ------------------ |
| latest release | :white_check_mark: |
| older releases | :x:                |

This table will be expanded once the project reaches a stable 1.0 release with a longer support
window.

## Reporting a Vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report vulnerabilities privately through
[GitHub's private vulnerability reporting](https://github.com/prophetizer/franchisarr/security/advisories/new),
or by emailing **franchisarr@ihatemikeg.com**. Either route reaches the same person.

Please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce (or a proof of concept)
- The version/commit you tested against

We'll acknowledge reports as quickly as possible and aim to keep you updated as a fix is developed.
Please allow a reasonable disclosure window before publicizing an unpatched issue.

## Scope

Areas of particular sensitivity in this project:

- Storage and display of Plex/Radarr/Sonarr/TMDb API keys and the Plex OAuth flow
- The config export/import feature (exported files contain live credentials)
- Authentication (Plex OAuth token validation, local admin password handling, CLI API keys)
- The base URL / reverse-proxy handling (misconfigured routing could expose authenticated pages)

Issues in third-party dependencies should generally be reported upstream, but let us know if a
dependency vulnerability affects Franchisarr directly (e.g. we're pinned to a vulnerable version).

## What the app does on its own behalf

Most protection for a self-hosted app comes from the reverse proxy in front of it. These are
the parts that belong to the app, because only it knows what a sign-in or a form post is:

- **Secrets are never rendered or logged.** Keys show as their last four characters; a log
  redactor is loaded with every stored credential at startup, so a value cannot reach a log
  line through a third-party library either. The config export redacts on request.
- **Sign-in is rate-limited** per client address: ten failures in fifteen minutes, then 429.
  Only failures count. The Jellyfin/Emby form relays attempts to that server, so this also
  stops Franchisarr being used to guess a media-server password.
- **A Plex token is not an authorisation.** Sign-in is refused unless the account can reach
  this install's own Plex server.
- **Cross-site posts are refused** on `Sec-Fetch-Site` / `Origin`, on top of a `SameSite=Lax`,
  `HttpOnly` session cookie (`SESSION_COOKIE_SECURE=true` adds `Secure` behind HTTPS).
- **Security headers** on every response: a Content-Security-Policy that forbids framing
  (`frame-ancestors 'none'`), plugins and `<base>` tricks, keeps scripts and XHR to this app,
  and lets forms post only here and to plex.tv. Styles, images and fonts may load from any
  HTTPS origin, because a proxy-injected theme.park stylesheet (traefik-themepark, nginx
  `sub_filter`) and whatever it imports are on hosts the app never sees;
  `nosniff`, a same-origin referrer policy. Alpine.js needs `unsafe-eval`, so the script
  policy is not strict; treat the CSP as a limit on where content can come from, not as XSS
  protection.
- **Request bodies are capped** at 2 MB; a config backup is a few tens of kilobytes.
- **List and calendar URLs carry the key in the query string** because neither the *arrs nor a
  calendar app can send a header. The endpoints are read-only and the key is revocable from
  Settings.
- **Nothing auto-adds.** Only a click, or an import list the user configured inside Radarr or
  Sonarr, sends anything anywhere.

