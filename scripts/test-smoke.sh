#!/bin/bash
# test-smoke.sh — Run core smoke tests for quick feedback.
# Use before commits. Full suite runs in CI/nightly.
#
# Usage:
#   ./scripts/test-smoke.sh           # run smoke tests
#   ./scripts/test-smoke.sh --verbose  # with verbose output

set -e
cd "$(dirname "$0")/.."

echo "Running smoke tests..."
python3 -m pytest \
    tests/test_agents.py \
    tests/test_workflow.py \
    tests/test_v64_editor_quality_gates.py \
    tests/test_v61_acceptance_fixes.py \
    tests/test_v662_context_inheritance.py \
    tests/test_v5512_llm_runtime_reliability.py \
    -q --tb=short "$@"

echo "Smoke tests passed."
