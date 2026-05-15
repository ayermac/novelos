#!/bin/bash
# Standalone smoke test for the frozen sidecar binary.
#
# Run from repo root:
#   bash packaging/scripts/smoke-sidecar.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# ── Detect platform/arch ────────────────────────────────────────
PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$PLATFORM" in
    darwin)
        case "$ARCH" in
            x86_64)  ARCH_KEY="darwin-x64" ;;
            arm64)   ARCH_KEY="darwin-arm64" ;;
            *)       echo "Unsupported architecture: $ARCH"; exit 1 ;;
        esac
        ;;
    *)
        echo "Unsupported platform: $PLATFORM"
        exit 1
        ;;
esac

SIDECAR_BIN="${REPO_ROOT}/desktop/resources/sidecar/${ARCH_KEY}/novelos-sidecar"
DB_PATH="/tmp/novelos-sidecar-smoke.db"

# ── Find sidecar ────────────────────────────────────────────────
if [ ! -f "$SIDECAR_BIN" ]; then
    echo "Error: Sidecar binary not found at $SIDECAR_BIN"
    echo "Build it first: bash packaging/scripts/build-sidecar.sh"
    exit 1
fi

echo "Sidecar binary: $SIDECAR_BIN"

# ── Clean up previous smoke DB ──────────────────────────────────
rm -f "$DB_PATH"
rm -f "$DB_PATH-shm"
rm -f "$DB_PATH-wal"

# ── Find a free port ────────────────────────────────────────────
PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()")
echo "Using port: $PORT"

# ── Start sidecar in background ─────────────────────────────────
echo "Starting sidecar..."
"$SIDECAR_BIN" \
    --host 127.0.0.1 \
    --port "$PORT" \
    --db-path "$DB_PATH" \
    --llm-mode stub \
    &
SIDECAR_PID=$!

# ── Health check poll ───────────────────────────────────────────
echo "Polling /api/health..."
HEALTHY=false
for i in {1..30}; do
    if curl -sf "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    sleep 1
done

if [ "$HEALTHY" != "true" ]; then
    echo "Error: Sidecar failed health check"
    kill "$SIDECAR_PID" 2>/dev/null || true
    exit 1
fi

echo "Health check OK"

# ── Verify DB was created ───────────────────────────────────────
if [ ! -f "$DB_PATH" ]; then
    echo "Error: Database was not created at $DB_PATH"
    kill "$SIDECAR_PID" 2>/dev/null || true
    exit 1
fi
echo "Database created: $DB_PATH"

# ── Stop sidecar ────────────────────────────────────────────────
echo "Stopping sidecar (PID $SIDECAR_PID)..."
kill "$SIDECAR_PID" 2>/dev/null || true
wait "$SIDECAR_PID" 2>/dev/null || true

# ── Cleanup ─────────────────────────────────────────────────────
rm -f "$DB_PATH"
rm -f "$DB_PATH-shm"
rm -f "$DB_PATH-wal"

echo ""
echo "=========================================="
echo "  Sidecar smoke test PASSED"
echo "=========================================="
