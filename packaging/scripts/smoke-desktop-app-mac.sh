#!/bin/bash
# Smoke test for the packaged Novelos macOS desktop app.
#
# Usage:
#   bash packaging/scripts/smoke-desktop-app-mac.sh
#
# Environment:
#   NOVELOS_DESKTOP_USER_DATA_DIR  — optional override for test isolation.
#
# Requirements:
#   - The app must already be built (e.g. via build-desktop-mac.sh --dir).
#   - macOS with curl and lsof available.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_PATH="$REPO_ROOT/desktop/release/mac-arm64/Novelos.app"
BINARY_PATH="$APP_PATH/Contents/MacOS/Novelos"
FRONTEND_DIST="$APP_PATH/Contents/Resources/frontend/dist/index.html"
SIDECAR_PATH="$APP_PATH/Contents/Resources/sidecar/darwin-arm64/novelos-sidecar"

# Use isolated user data dir to avoid polluting real user data
export NOVELOS_DESKTOP_USER_DATA_DIR="${NOVELOS_DESKTOP_USER_DATA_DIR:-/tmp/novelos-smoke-$(date +%s)}"

echo "=========================================="
echo "  Novelos Desktop App Smoke Test"
echo "=========================================="
echo "  App:       $APP_PATH"
echo "  UserData:  $NOVELOS_DESKTOP_USER_DATA_DIR"
echo ""

PASS=0
FAIL=0

report() {
  if [ "$1" = "PASS" ]; then
    echo "  [PASS] $2"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $2"
    FAIL=$((FAIL + 1))
  fi
}

# ── Checks ─────────────────────────────────────────────────────

if [ -d "$APP_PATH" ]; then
  report PASS "App bundle exists"
else
  report FAIL "App bundle missing at $APP_PATH"
  echo ""
  echo "Build first: bash packaging/scripts/build-desktop-mac.sh --dir --skip-sidecar"
  exit 1
fi

if [ -f "$FRONTEND_DIST" ]; then
  report PASS "Frontend dist exists"
else
  report FAIL "Frontend dist missing at $FRONTEND_DIST"
fi

if grep -q 'src="./assets/' "$FRONTEND_DIST" 2>/dev/null || grep -q 'href="./assets/' "$FRONTEND_DIST" 2>/dev/null; then
  report PASS "Frontend asset paths are relative (./assets/)"
else
  # Also accept absolute paths that already start with ./
  if grep -q 'assets/' "$FRONTEND_DIST" 2>/dev/null; then
    report PASS "Frontend contains assets references"
  else
    report FAIL "Frontend asset paths may be absolute (/assets/)"
  fi
fi

if [ -f "$SIDECAR_PATH" ]; then
  report PASS "Frozen sidecar exists"
else
  echo "  [SKIP] Frozen sidecar missing at $SIDECAR_PATH"
  echo "         Build it first: bash packaging/scripts/build-sidecar.sh"
fi

if [ -x "$SIDECAR_PATH" ]; then
  report PASS "Frozen sidecar is executable"
else
  echo "  [SKIP] Frozen sidecar is not executable"
fi

# ── Launch ─────────────────────────────────────────────────────

echo ""
echo "Launching app..."

# Cleanup on exit
cleanup() {
  if [ -n "${APP_PID:-}" ] && kill -0 "$APP_PID" 2>/dev/null; then
    echo ""
    echo "Cleaning up app process $APP_PID..."
    kill -TERM "$APP_PID" 2>/dev/null || true
    sleep 2
    kill -KILL "$APP_PID" 2>/dev/null || true
  fi
  # Also ensure no sidecar is left behind on the detected port
  if [ -n "${DETECTED_PORT:-}" ]; then
    local PIDS
    PIDS="$(lsof -ti tcp:"$DETECTED_PORT" 2>/dev/null || true)"
    if [ -n "$PIDS" ]; then
      echo "Killing leftover sidecar processes on port $DETECTED_PORT..."
      echo "$PIDS" | xargs kill -9 2>/dev/null || true
    fi
  fi
}
trap cleanup EXIT

# Start the app in background and capture logs
mkdir -p "$NOVELOS_DESKTOP_USER_DATA_DIR/logs"
LOG_FILE="$NOVELOS_DESKTOP_USER_DATA_DIR/logs/smoke.log"

"$BINARY_PATH" > "$LOG_FILE" 2>&1 &
APP_PID=$!

echo "  PID: $APP_PID"
echo "  Log: $LOG_FILE"

# Wait for port selection in logs
# The main process logs: [INFO] Sidecar command: ... --port 60028 ...
DETECTED_PORT=""
for i in $(seq 1 60); do
  DETECTED_PORT="$(grep -oE -- '--port [0-9]+' "$LOG_FILE" 2>/dev/null | tail -1 | awk '{print $2}' || true)"
  if [ -n "$DETECTED_PORT" ]; then
    break
  fi
  sleep 1
done

if [ -n "$DETECTED_PORT" ]; then
  report PASS "Selected port detected: $DETECTED_PORT"
else
  report FAIL "Could not detect selected port from logs"
  # Try to find any port mention
  echo "  Log tail:"
  tail -n 20 "$LOG_FILE" || true
fi

# Wait for health
HEALTH_OK=false
if [ -n "$DETECTED_PORT" ]; then
  for i in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:${DETECTED_PORT}/api/health" > /dev/null 2>&1; then
      HEALTH_OK=true
      break
    fi
    sleep 1
  done
fi

if [ "$HEALTH_OK" = true ]; then
  report PASS "Health check passed on port $DETECTED_PORT"
else
  report FAIL "Health check failed"
  echo "  Log tail:"
  tail -n 30 "$LOG_FILE" || true
fi

# ── Data checks ────────────────────────────────────────────────

sleep 1

if [ -f "$NOVELOS_DESKTOP_USER_DATA_DIR/data/novelos.db" ]; then
  report PASS "Database created"
else
  report FAIL "Database not found"
fi

if [ -f "$NOVELOS_DESKTOP_USER_DATA_DIR/config/local.yaml" ]; then
  report PASS "Config file created"
else
  report FAIL "Config file not found"
fi

if [ -d "$NOVELOS_DESKTOP_USER_DATA_DIR/logs" ]; then
  report PASS "Logs directory exists"
else
  report FAIL "Logs directory not found"
fi

# ── Shutdown ───────────────────────────────────────────────────

echo ""
echo "Shutting down app..."
kill -TERM "$APP_PID" 2>/dev/null || true

for i in $(seq 1 10); do
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    break
  fi
  sleep 1
done

if kill -0 "$APP_PID" 2>/dev/null; then
  kill -KILL "$APP_PID" 2>/dev/null || true
fi

# ── Residual check ─────────────────────────────────────────────

sleep 1

if [ -n "${DETECTED_PORT:-}" ]; then
  RESIDUAL="$(lsof -ti tcp:"$DETECTED_PORT" 2>/dev/null || true)"
  if [ -z "$RESIDUAL" ]; then
    report PASS "No residual sidecar process on port $DETECTED_PORT"
  else
    report FAIL "Residual sidecar process detected on port $DETECTED_PORT"
    echo "$RESIDUAL" | xargs kill -9 2>/dev/null || true
  fi
fi

# ── Summary ────────────────────────────────────────────────────

echo ""
echo "=========================================="
if [ "$FAIL" -eq 0 ]; then
  echo "  ALL PASSED ($PASS/$((PASS+FAIL)))"
else
  echo "  FAILED ($FAIL/$((PASS+FAIL)))"
fi
echo "=========================================="

if [ "$FAIL" -ne 0 ]; then
  exit 1
fi
