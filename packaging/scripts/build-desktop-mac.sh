#!/bin/bash
# Build a macOS Novelos desktop bundle from repo root.
#
# Default output is the unsigned .app directory for fast local validation.
# Use --dmg to also create a DMG through electron-builder.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODE="dir"
SKIP_SIDECAR="false"

usage() {
    cat <<'EOF'
Usage: bash packaging/scripts/build-desktop-mac.sh [--dir|--dmg] [--skip-sidecar]

Options:
  --dir           Build release/mac-arm64/Novelos.app only. This is the default.
  --dmg           Build the .app and DMG installer.
  --skip-sidecar  Reuse the existing desktop/resources/sidecar bundle.
  -h, --help      Show this help text.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dir)
            MODE="dir"
            ;;
        --dmg)
            MODE="dmg"
            ;;
        --skip-sidecar)
            SKIP_SIDECAR="true"
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
    shift
done

cd "$REPO_ROOT"

echo "=========================================="
echo "  Novelos Desktop macOS build"
echo "=========================================="
echo "  Mode:          $MODE"
echo "  Skip sidecar:  $SKIP_SIDECAR"
echo ""

echo "Step 1/3: Building frontend..."
(cd frontend && npm run build)

if [ "$SKIP_SIDECAR" = "true" ]; then
    echo "Step 2/3: Skipping sidecar build."
else
    echo "Step 2/3: Building frozen sidecar..."
    bash packaging/scripts/build-sidecar.sh
fi

echo "Step 3/3: Packaging Electron app..."
if [ "$MODE" = "dmg" ]; then
    (cd desktop && npm run dist:mac)
else
    (cd desktop && npm run pack:mac)
fi

echo ""
echo "=========================================="
echo "  Desktop build complete"
echo "=========================================="
echo "  App: desktop/release/mac-arm64/Novelos.app"
if [ "$MODE" = "dmg" ]; then
    echo "  DMG: desktop/release/Novelos-*.dmg"
fi
