#!/bin/bash
# Full deployment (equivalent of the old monorepo deploy.sh): API first, then frontend.
# Expects TTC-Front cloned next to this repo (override with FRONT_DIR).
# Usage: ./deploy-all.sh [--import]     (flags are passed to the backend deploy.sh)

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
FRONT_DIR="${FRONT_DIR:-$HERE/../TTC-Front}"

if [ ! -x "$FRONT_DIR/deploy.sh" ]; then
    echo "TTC-Front introuvable ($FRONT_DIR) — clone-le à côté de TTC-Back ou définis FRONT_DIR." >&2
    exit 1
fi

echo "=== 1/2 Backend ==="
(cd "$HERE" && ./deploy.sh "$@")

echo "=== 2/2 Frontend ==="
(cd "$FRONT_DIR" && ./deploy.sh)
