#!/bin/bash
# Build the Novelos frozen sidecar binary for the current platform.
#
# Run from repo root:
#   bash packaging/scripts/build-sidecar.sh
#
# Prerequisites:
#   pip install pyinstaller

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# ── Prerequisites ───────────────────────────────────────────────
if ! command -v pyinstaller &>/dev/null; then
    echo "Error: pyinstaller is not installed."
    echo "Install with: pip install pyinstaller"
    exit 1
fi

# ── Determine platform/arch key ─────────────────────────────────
PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$PLATFORM" in
    darwin)
        case "$ARCH" in
            x86_64)  ARCH_KEY="darwin-x64" ;;
            arm64)   ARCH_KEY="darwin-arm64" ;;
            *)       echo "Unsupported macOS architecture: $ARCH"; exit 1 ;;
        esac
        ;;
    linux)
        case "$ARCH" in
            x86_64)  ARCH_KEY="linux-x64" ;;
            *)       echo "Unsupported Linux architecture: $ARCH"; exit 1 ;;
        esac
        ;;
    *)
        echo "Unsupported platform: $PLATFORM"
        exit 1
        ;;
esac

echo "Building sidecar for: $ARCH_KEY"

# ── Clean previous PyInstaller output ───────────────────────────
rm -rf "${REPO_ROOT}/build/novelos-sidecar"
rm -rf "${REPO_ROOT}/dist/novelos-sidecar"

# ── Run PyInstaller ─────────────────────────────────────────────
echo "Running PyInstaller..."
pyinstaller \
    --clean \
    "${REPO_ROOT}/packaging/pyinstaller/novelos-sidecar.spec"

# ── Copy to Electron resources ──────────────────────────────────
DEST_DIR="${REPO_ROOT}/desktop/resources/sidecar/${ARCH_KEY}"
mkdir -p "$DEST_DIR"

# Copy entire onedir bundle
SOURCE_DIR="${REPO_ROOT}/dist/novelos-sidecar"
if [ ! -d "$SOURCE_DIR" ]; then
    echo "Error: PyInstaller output not found at $SOURCE_DIR"
    exit 1
fi

cp -R "${SOURCE_DIR}/"* "$DEST_DIR/"

# Make main binary executable
chmod +x "${DEST_DIR}/novelos-sidecar"

# ── Summary ─────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  Sidecar build complete"
echo "=========================================="
echo "  Platform:    $ARCH_KEY"
echo "  Binary:      $DEST_DIR/novelos-sidecar"
echo "  Bundle size: $(du -sh "$DEST_DIR" | cut -f1)"
echo ""
