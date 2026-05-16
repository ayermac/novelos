#!/bin/bash
# One-command desktop packaging verification pipeline for macOS.
#
# Run from repo root (or any cwd):
#   bash packaging/scripts/verify-desktop-mac.sh
#
# Steps:
#   1. Build frontend
#   2. Build frozen sidecar
#   3. Build desktop TypeScript
#   4. Package Electron app (dir mode)
#   5. Smoke-test frozen sidecar
#   6. Smoke-test packaged desktop app
#
# Outputs:
#   - desktop/release/verification-report.json (machine-readable)
#
# Prerequisites:
#   - Node.js 18+, npm
#   - Python 3.9+, pyinstaller
#   - macOS with curl and lsof

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

# Derive expected Electron Builder output path
# electron-builder --mac --dir writes to release/mac-<eb-arch>/Novelos.app
APP_DIR="$REPO_ROOT/desktop/release/mac-$EB_ARCH/Novelos.app"
REPORT_PATH="$REPO_ROOT/desktop/release/verification-report.json"
SIDECAR_PATH="$REPO_ROOT/desktop/resources/sidecar/$ARCH_KEY/novelos-sidecar"

# ── Git / version info ──────────────────────────────────────────
COMMIT="$(git rev-parse HEAD 2>/dev/null || echo "unknown")"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    BRANCH="${BRANCH}-dirty"
fi
DESKTOP_VERSION="$(node -p "require('./desktop/package.json').version" 2>/dev/null || echo "unknown")"

# ── Helpers ─────────────────────────────────────────────────────
step() {
    echo ""
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
}

die() {
    echo ""
    echo "  FAILED: $1"
    echo "============================================================"
    FAIL=$((FAIL + 1))
    write_report "failed" "$1"
    echo "  Report: $REPORT_PATH"
    exit 1
}

PASS=0
SKIP=0
FAIL=0

write_report() {
    local status="$1"
    local message="${2:-}"
    local app_exists="false"
    local sidecar_exists="false"
    if [ -d "$APP_DIR" ]; then app_exists="true"; fi
    if [ -f "$SIDECAR_PATH" ]; then sidecar_exists="true"; fi
    mkdir -p "$REPO_ROOT/desktop/release"
    cat > "$REPORT_PATH" <<EOF
{
  "schema_version": 1,
  "status": "$status",
  "message": "$message",
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "platform": "$ARCH_KEY",
  "commit": "$COMMIT",
  "branch": "$BRANCH",
  "desktop_version": "$DESKTOP_VERSION",
  "counts": {
    "passed": $PASS,
    "skipped": $SKIP,
    "failed": $FAIL
  },
  "paths": {
    "app_bundle": "$APP_DIR",
    "sidecar_binary": "desktop/resources/sidecar/$ARCH_KEY/novelos-sidecar"
  },
  "checks": {
    "app_bundle_exists": $app_exists,
    "sidecar_binary_exists": $sidecar_exists
  }
}
EOF
}

report() {
    if [ "$1" = "PASS" ]; then
        echo "  [PASS] $2"
        PASS=$((PASS + 1))
    elif [ "$1" = "SKIP" ]; then
        echo "  [SKIP] $2"
        SKIP=$((SKIP + 1))
    else
        echo "  [FAIL] $2"
        FAIL=$((FAIL + 1))
    fi
}

# ── Step 1: Build frontend ──────────────────────────────────────
step "Step 1/6: Build frontend"
cd "$REPO_ROOT/frontend"
if npm run build >/dev/null 2>&1; then
    report PASS "Frontend build succeeded"
else
    die "Frontend build failed"
fi

# ── Step 2: Build frozen sidecar ────────────────────────────────
step "Step 2/6: Build frozen sidecar"
cd "$REPO_ROOT"
if bash packaging/scripts/build-sidecar.sh >/dev/null 2>&1; then
    report PASS "Frozen sidecar build succeeded"
else
    die "Frozen sidecar build failed"
fi

# ── Step 3: Build desktop TypeScript ────────────────────────────
step "Step 3/6: Build desktop TypeScript"
cd "$REPO_ROOT/desktop"
if npm run build >/dev/null 2>&1; then
    report PASS "Desktop TypeScript build succeeded"
else
    die "Desktop TypeScript build failed"
fi

# ── Step 4: Package Electron app ────────────────────────────────
step "Step 4/6: Package Electron app (dir mode)"
cd "$REPO_ROOT/desktop"
if npm run pack:mac >/dev/null 2>&1; then
    report PASS "Electron app packaged"
else
    die "Electron app packaging failed"
fi

if [ -d "$APP_DIR" ]; then
    report PASS "App bundle exists at $APP_DIR"
else
    die "App bundle not found at $APP_DIR"
fi

# ── Step 5: Smoke-test frozen sidecar ───────────────────────────
step "Step 5/6: Smoke-test frozen sidecar"
cd "$REPO_ROOT"
if bash packaging/scripts/smoke-sidecar.sh >/dev/null 2>&1; then
    report PASS "Sidecar smoke passed"
else
    # smoke-sidecar exits 0 on SKIP, so if it exits non-zero it's a real failure
    report FAIL "Sidecar smoke failed"
fi

# ── Step 6: Smoke-test packaged desktop app ─────────────────────
step "Step 6/6: Smoke-test packaged desktop app"
cd "$REPO_ROOT"
# Use a dedicated temp user data dir for this run
export NOVELOS_DESKTOP_USER_DATA_DIR="/tmp/novelos-verify-$(date +%s)"
if bash packaging/scripts/smoke-desktop-app-mac.sh >/dev/null 2>&1; then
    report PASS "Desktop app smoke passed"
else
    report FAIL "Desktop app smoke failed"
fi

# ── Summary ─────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Desktop Packaging Verification Summary"
echo "============================================================"
echo "  Platform:       $ARCH_KEY"
echo "  App bundle:     $APP_DIR"
echo "  Sidecar binary: desktop/resources/sidecar/$ARCH_KEY/novelos-sidecar"
echo ""
if [ "$FAIL" -eq 0 ]; then
    echo "  ALL PASSED ($PASS passed, $SKIP skipped)"
    write_report "passed" "ALL PASSED"
else
    echo "  FAILED ($FAIL failures, $PASS passed, $SKIP skipped)"
    write_report "failed" "Verification failed"
fi
echo "  Report:         $REPORT_PATH"
echo "============================================================"

if [ "$FAIL" -ne 0 ]; then
    exit 1
fi
