#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${MODE:-real}"
OUTPUT="${OUTPUT:-}"

args=(--mode "${MODE}")
if [[ -n "${CONFIG_PATH:-}" ]]; then
  args+=(--config "${CONFIG_PATH}")
fi
if [[ -n "${DB_PATH:-}" ]]; then
  args+=(--db-path "${DB_PATH}")
fi
if [[ -n "${OUTPUT}" ]]; then
  args+=(--output "${OUTPUT}")
fi
if [[ "${KEEP_DB:-0}" == "1" ]]; then
  args+=(--keep-db)
fi

cd "${ROOT_DIR}"
python3 scripts/verify_v64_real_llm.py "${args[@]}"
