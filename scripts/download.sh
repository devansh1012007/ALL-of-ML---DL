#!/usr/bin/env bash
#
# Downloads a file, and continues where it stopped.
#
# The file that is already there is not downloaded again: the transfer picks
# up at the byte where it was interrupted, and a network that fails in the
# middle is retried instead of starting the file over.
#
# Usage:
#   scripts/download.sh <url> [target]
#
# The environment variables:
#   RETRY_ATTEMPTS   the attempts of the whole transfer  (default 20)
#   RETRY_DELAY      the seconds between two attempts   (default 5)
#   CURL_TIMEOUT     the timeout of a single request    (default 600)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RETRY_ATTEMPTS="${RETRY_ATTEMPTS:-20}"
RETRY_DELAY="${RETRY_DELAY:-5}"
CURL_TIMEOUT="${CURL_TIMEOUT:-600}"

usage() {
    sed -n '3,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

[ $# -ge 1 ] || usage
[ $# -le 2 ] || usage

URL="$1"
TARGET="${2:-}"

if [ -z "$TARGET" ]; then
    TARGET="$(basename "${URL%%\?*}")"
    [ -n "$TARGET" ] || die "the target cannot be derived from the url"
fi

command -v curl >/dev/null 2>&1 || { echo "curl is not installed" >&2; exit 1; }

mkdir -p "$(dirname "$TARGET")"

attempt=1
while true; do
    # --continue-at - resumes at the size of the file that is already there,
    # --retry makes curl try again when the connection breaks.
    if curl --fail --location \
            --continue-at - \
            --retry 5 \
            --retry-delay "$RETRY_DELAY" \
            --retry-connrefused \
            --retry-max-time 3600 \
            --connect-timeout 30 \
            --max-time "$CURL_TIMEOUT" \
            --output "$TARGET" \
            "$URL"; then
        echo "downloaded: $TARGET"
        exit 0
    fi

    if [ "$attempt" -ge "$RETRY_ATTEMPTS" ]; then
        echo "the download failed after $attempt attempts: $URL" >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    echo "attempt $((attempt - 1)) failed, retrying in ${RETRY_DELAY}s" >&2
    sleep "$RETRY_DELAY"
done
