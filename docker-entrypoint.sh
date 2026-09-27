#!/bin/sh
# Standard linuxserver.io-style PUID/PGID entrypoint (docs/DESIGN.md technical challenge #19):
# the container starts as root just long enough to create a matching user/group and chown the
# mounted config volume, then re-execs the real command as that user via gosu.
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# The point of this entrypoint is to *not* run as root; PUID=0 would quietly undo that.
if [ "${PUID}" = "0" ] || [ "${PGID}" = "0" ]; then
    echo "[entrypoint] refusing to run as root (PUID/PGID 0). Set PUID and PGID to your user." >&2
    exit 1
fi

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
# The database holds every credential the app uses (media server token, *arr keys), so only
# the app's own user may read it -- on the host too, where the volume is a plain directory.
chmod -R go-rwx "${FRANCHISARR_CONFIG_DIR:-/config}"
umask 077

exec gosu "${USER_NAME}:${GROUP_NAME}" "$@"
