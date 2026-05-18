#!/bin/bash
# Generate desktop release manifest from existing build artifacts.
#
# Run from repo root after verify-desktop-mac.sh has completed:
#   bash packaging/scripts/write-desktop-release-manifest.sh
#
# Generates:
#   desktop/release/release-manifest.json
#
# Prerequisites:
#   - verify-desktop-mac.sh has already produced the app bundle and verification report.
#   - Git is available.
#
# Behavior:
#   - If app bundle, sidecar binary, or verification report is missing, writes false checks
#     and exits with non-zero status.
#   - If DMG is missing, writes null (not a failure).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# ── Platform / arch detection ───────────────────────────────────
PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$PLATFORM" in
    darwin)
        case "$ARCH" in
            x86_64)  ARCH_KEY="darwin-x64"; EB_ARCH="x64" ;;
            arm64)   ARCH_KEY="darwin-arm64"; EB_ARCH="arm64" ;;
            *)       echo "Unsupported architecture: $ARCH"; exit 1 ;;
        esac
        ;;
    *)
        echo "Unsupported platform: $PLATFORM"
        exit 1
        ;;
esac

# ── Git info ────────────────────────────────────────────────────
COMMIT="$(git rev-parse HEAD 2>/dev/null || echo "unknown")"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    BRANCH="${BRANCH}-dirty"
fi

# ── Desktop version from package.json ───────────────────────────
DESKTOP_VERSION="$(node -p "require('./desktop/package.json').version" 2>/dev/null || echo "unknown")"

# ── Artifact paths ──────────────────────────────────────────────
APP_DIR="$REPO_ROOT/desktop/release/mac-$EB_ARCH/Novelos.app"
SIDECAR_BIN="$REPO_ROOT/desktop/resources/sidecar/$ARCH_KEY/novelos-sidecar"
VERIFICATION_REPORT="$REPO_ROOT/desktop/release/verification-report.json"
RELEASE_DIR="$REPO_ROOT/desktop/release"
MANIFEST_PATH="$RELEASE_DIR/release-manifest.json"

# ── DMG discovery ───────────────────────────────────────────────
DMG_PATH=""
if [ -d "$RELEASE_DIR" ]; then
    # Match DMG by desktop version and electron-builder arch to avoid stale artifacts
    DMG_MATCHES=()
    while IFS= read -r -d '' f; do
        DMG_MATCHES+=("$f")
    done < <(find "$RELEASE_DIR" -maxdepth 1 -name "Novelos-*-${EB_ARCH}.dmg" -print0 2>/dev/null)
    if [ ${#DMG_MATCHES[@]} -eq 1 ]; then
        DMG_PATH="${DMG_MATCHES[0]}"
    elif [ ${#DMG_MATCHES[@]} -gt 1 ]; then
        echo "ERROR: Multiple DMG files matched for ${EB_ARCH}:" >&2
        printf '  %s\n' "${DMG_MATCHES[@]}" >&2
        echo "Please clean old release artifacts or specify one explicitly." >&2
        exit 1
    fi
fi
if [ -z "$DMG_PATH" ]; then
    DMG_JSON="null"
    DMG_RELATIVE="null"
else
    # Use Python for portable relative path computation
    DMG_RELATIVE="$(python3 -c "import pathlib,sys; print(pathlib.Path(sys.argv[1]).relative_to(pathlib.Path(sys.argv[2])))" "$DMG_PATH" "$REPO_ROOT")"
    DMG_JSON="\"$DMG_RELATIVE\""
fi

# ── Existence checks ────────────────────────────────────────────
APP_EXISTS=false
SIDECAR_EXISTS=false
REPORT_EXISTS=false

if [ -d "$APP_DIR" ]; then
    APP_EXISTS=true
fi

if [ -f "$SIDECAR_BIN" ]; then
    SIDECAR_EXISTS=true
fi

if [ -f "$VERIFICATION_REPORT" ]; then
    REPORT_EXISTS=true
fi

# ── Write manifest ──────────────────────────────────────────────
mkdir -p "$RELEASE_DIR"

cat > "$MANIFEST_PATH" <<EOF
{
  "schema_version": 1,
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "commit": "$COMMIT",
  "branch": "$BRANCH",
  "desktop_version": "$DESKTOP_VERSION",
  "platform": "$ARCH_KEY",
  "artifacts": {
    "app_bundle": "$APP_DIR",
    "dmg": $DMG_JSON,
    "sidecar_binary": "desktop/resources/sidecar/$ARCH_KEY/novelos-sidecar",
    "verification_report": "desktop/release/verification-report.json"
  },
  "checks": {
    "app_bundle_exists": $APP_EXISTS,
    "sidecar_exists": $SIDECAR_EXISTS,
    "verification_report_exists": $REPORT_EXISTS
  }
}
EOF

# ── Terminal output ─────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Desktop Release Manifest"
echo "============================================================"
echo "  Platform:        $ARCH_KEY"
echo "  Desktop version: $DESKTOP_VERSION"
echo "  Commit:          $COMMIT"
echo "  Branch:          $BRANCH"
echo ""
echo "  Artifacts:"
echo "    App bundle:     $APP_DIR"
if [ "$DMG_JSON" = "null" ]; then
    echo "    DMG:            (not found)"
else
    echo "    DMG:            $DMG_RELATIVE"
fi
echo "    Sidecar binary: desktop/resources/sidecar/$ARCH_KEY/novelos-sidecar"
echo "    Verification:   desktop/release/verification-report.json"
echo ""
echo "  Checks:"
if [ "$APP_EXISTS" = true ]; then
    echo "    [PASS] App bundle exists"
else
    echo "    [FAIL] App bundle missing"
fi
if [ "$SIDECAR_EXISTS" = true ]; then
    echo "    [PASS] Sidecar binary exists"
else
    echo "    [FAIL] Sidecar binary missing"
fi
if [ "$REPORT_EXISTS" = true ]; then
    echo "    [PASS] Verification report exists"
else
    echo "    [FAIL] Verification report missing"
fi
echo ""
echo "  Manifest:        $MANIFEST_PATH"
echo "============================================================"

# ── Exit code ───────────────────────────────────────────────────
if [ "$APP_EXISTS" = false ] || [ "$SIDECAR_EXISTS" = false ] || [ "$REPORT_EXISTS" = false ]; then
    echo ""
    echo "  FAILED: One or more required artifacts are missing."
    echo "============================================================"
    exit 1
fi
