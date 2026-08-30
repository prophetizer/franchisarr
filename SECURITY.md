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

Report vulnerabilities privately by emailing **franchisarr@ihatemikeg.com**.

Once the project moves to GitHub, GitHub's private security advisories will become available as an
alternative route; this address will remain valid either way.

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
