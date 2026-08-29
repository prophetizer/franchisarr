#!/bin/sh
# Standard linuxserver.io-style PUID/PGID entrypoint (PROJECT_PLAN.md technical challenge #19):
# the container starts as root just long enough to create a matching user/group and chown the
# mounted config volume, then re-execs the real command as that user via gosu.
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

echo "[entrypoint] starting with PUID=${PUID} PGID=${PGID}"

if ! getent group "${PGID}" >/dev/null 2>&1; then
    addgroup --gid "${PGID}" franchisarr
fi
GROUP_NAME="$(getent group "${PGID}" | cut -d: -f1)"

if ! getent passwd "${PUID}" >/dev/null 2>&1; then
    adduser --uid "${PUID}" --gid "${PGID}" --disabled-password --gecos "" franchisarr
fi
USER_NAME="$(getent passwd "${PUID}" | cut -d: -f1)"

mkdir -p "${FRANCHISARR_CONFIG_DIR:-/config}"
chown -R "${PUID}:${PGID}" "${FRANCHISARR_CONFIG_DIR:-/config}"

exec gosu "${USER_NAME}:${GROUP_NAME}" "$@"
