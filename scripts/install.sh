#!/usr/bin/env bash
#
# Installs the dependencies of the repository.
#
# The downloads are retried generously and they continue where they stopped:
# the cache of the installer lives in .cache/ of the repository, so an
# installation that was interrupted is resumed instead of being started over.
#
# Usage:
#   scripts/install.sh                 # the backend and the frontend
#   scripts/install.sh --backend       # only the python dependencies
#   scripts/install.sh --frontend      # only the node dependencies
#   scripts/install.sh --optional      # the optional python dependencies (implies --backend)
#   scripts/install.sh --dev           # the development dependencies (implies --backend)
#   scripts/install.sh --cpu           # the cpu build of torch (implies --backend)
#
# The environment variables:
#   UV_HTTP_RETRIES      the retries of a single request       (default 20)
#   UV_HTTP_TIMEOUT      the timeout of a single request       (default 120)
#   RETRY_ATTEMPTS       the attempts of the whole installation (default 5)
#   RETRY_DELAY          the seconds between two attempts      (default 5)
#
# The cpu build of torch is a few hundred megabytes, the cuda build is
# several gigabytes and is of no use without a gpu: --cpu installs the small
# one, which is enough to train the models of the catalog of this repository.
#
# The flags --optional, --dev and --cpu only change the python side, so they
# install the backend as well. A flag that installs nothing would print that
# the dependencies are installed when it installed none.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CACHE_DIR="$REPO_ROOT/.cache"
VENV_DIR="$REPO_ROOT/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"

# The cache of the installer lives in the repository: a wheel that was already
# downloaded is not downloaded again, and a partially downloaded one is
# continued.
export UV_CACHE_DIR="$CACHE_DIR/uv"
export UV_HTTP_RETRIES="${UV_HTTP_RETRIES:-20}"
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-120}"
export UV_HTTP_CONNECT_TIMEOUT="${UV_HTTP_CONNECT_TIMEOUT:-30}"
export PIP_CACHE_DIR="$CACHE_DIR/pip"
export npm_config_cache="$CACHE_DIR/npm"

RETRY_ATTEMPTS="${RETRY_ATTEMPTS:-5}"
RETRY_DELAY="${RETRY_DELAY:-5}"

DO_BACKEND=0
DO_FRONTEND=0
DO_OPTIONAL=0
DO_DEV=0
DO_CPU=0

# The index of the cpu build of torch.
CPU_INDEX="https://download.pytorch.org/whl/cpu"

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '3,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --backend)  DO_BACKEND=1 ;;
        --frontend) DO_FRONTEND=1 ;;
        --optional) DO_OPTIONAL=1 ;;
        --dev)      DO_DEV=1 ;;
        --cpu)      DO_CPU=1 ;;
        -h|--help)  usage ;;
        *)          die "unknown option: $1 (try --help)" ;;
    esac
    shift
done

# Without an argument, everything is installed.
if [ "$DO_BACKEND" -eq 0 ] && [ "$DO_FRONTEND" -eq 0 ] && [ "$DO_OPTIONAL" -eq 0 ] && [ "$DO_DEV" -eq 0 ] && [ "$DO_CPU" -eq 0 ]; then
    DO_BACKEND=1
    DO_FRONTEND=1
fi

# The flags that only change the python side install the backend as well:
# without the backend they would install nothing and still say that the
# dependencies are installed.
if [ "$DO_OPTIONAL" -eq 1 ] || [ "$DO_DEV" -eq 1 ] || [ "$DO_CPU" -eq 1 ]; then
    DO_BACKEND=1
fi

mkdir -p "$CACHE_DIR"

# Runs a command again when it fails: a network that hiccups does not have to
# start the whole installation over.
retry() {
    local attempt=1
    while true; do
        if "$@"; then
            return 0
        fi
        if [ "$attempt" -ge "$RETRY_ATTEMPTS" ]; then
            warn "the command failed after $attempt attempts: $*"
            return 1
        fi
        attempt=$((attempt + 1))
        warn "attempt $((attempt - 1)) failed, retrying in ${RETRY_DELAY}s: $*"
        sleep "$RETRY_DELAY"
    done
}

install_backend() {
    log "the python dependencies of the backend"

    if [ ! -x "$PYTHON_BIN" ]; then
        command -v uv >/dev/null 2>&1 || die "uv is not installed: https://docs.astral.sh/uv/getting-started/installation/"
        log "the virtual environment $VENV_DIR"
        retry uv venv --python 3.12 "$VENV_DIR"
    fi

    command -v uv >/dev/null 2>&1 || die "uv is not installed: https://docs.astral.sh/uv/getting-started/installation/"

    if [ "$DO_CPU" -eq 1 ]; then
        # The cpu build of torch is used instead of the cuda one: it is a few
        # hundred megabytes instead of several gigabytes, and it trains the
        # models of the catalog of this repository just as well.
        log "the python dependencies of the backend (the cpu build of torch)"
        retry uv pip install --python "$PYTHON_BIN" \
            --extra-index-url "$CPU_INDEX" \
            --index-strategy unsafe-best-match \
            -r backend/requirements.txt
    else
        log "the python dependencies of the backend"
        retry uv pip install --python "$PYTHON_BIN" -r backend/requirements.txt
    fi

    if [ "$DO_OPTIONAL" -eq 1 ]; then
        log "the optional python dependencies"
        # They are optional: a model that needs one of them fails with an
        # explicit message when it is missing, the rest of the catalog works.
        retry uv pip install --python "$PYTHON_BIN" google-generativeai umap-learn hdbscan || \
            warn "an optional dependency could not be installed, the models that need it will refuse to train"
    fi

    if [ "$DO_DEV" -eq 1 ]; then
        log "the development dependencies"
        retry uv pip install --python "$PYTHON_BIN" pytest pytest-asyncio httpx ruff
    fi
}

install_frontend() {
    log "the node dependencies of the frontend"
    command -v npm >/dev/null 2>&1 || die "npm is not installed"

    # --prefer-offline uses the cache first, and the retries make a flaky
    # network recoverable instead of fatal.
    retry npm --prefix frontend install \
        --prefer-offline \
        --no-audit \
        --no-fund \
        --fetch-retries=10 \
        --fetch-retry-mintimeout=10000 \
        --fetch-retry-maxtimeout=120000 \
        --fetch-timeout=600000
}

if [ "$DO_BACKEND" -eq 1 ]; then
    install_backend
fi

if [ "$DO_FRONTEND" -eq 1 ]; then
    install_frontend
fi

log "the dependencies are installed"
