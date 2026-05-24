# v6.6.20 Completion Report — Production Ops & Release Hardening

**Version**: 6.6.20
**Date**: 2026-05-24
**Status**: COMPLETED
**Branch**: `codex-v6.6.20-production-ops-hardening`

---

## Executive Summary

v6.6.20 is a pure production-hardening release with **no new business features**. It closes the gap between "stable baseline" and "production-ready" by adding runtime diagnostics, release automation, soak testing infrastructure, and operational runbooks.

---

## Changes

### 1. Live Version Mismatch Detection

**Problem**: A long-running API process (PID 80628, started 2026-05-15) cached v5.3.0 modules in memory while source advanced to v6.6.x. There was no automated way to detect this drift.

**Fix**: Enhanced `GET /api/health` with `startup` metadata:

```json
{
  "data": {
    "version": "6.6.20",
    "startup": {
      "started_at": "2026-05-24T10:00:00Z",
      "python": "/Library/Developer/.../Python",
      "source_root": "/Users/chenchao/Workspace/AI-Project/novelos",
      "cwd": "/Users/chenchao/Workspace/AI-Project/novelos"
    }
  }
}
```

This enables operators to cross-check:
- Process start time vs. source modification time
- Source root vs. expected deployment path
- Python executable vs. expected interpreter

### 2. Release Smoke Script

New: `scripts/release_smoke.py`

Capabilities:
- Checks CLI version (`python3 -m novel_factory.cli --version`)
- Checks API health (version, db_connected, llm_mode, startup metadata)
- Checks frontend package.json version
- Checks desktop package.json version
- Checks desktop build (if node_modules present)
- Human-readable summary + `--json` machine output
- Exit code 0 if all required checks pass, 1 if any required check fails

```bash
python3 scripts/release_smoke.py --json
```

Output:
```json
{
  "ok": true,
  "version_expected": "6.6.20",
  "required_failed": 0,
  "optional_failed": 0,
  "checks": [...]
}
```

### 3. Real LLM Soak Script

New: `scripts/soak_real_llm_long_chapter.py`

Validates long chapter generation stability with segmented agents.

Modes:
- `--llm-mode stub` — fast structural validation
- `--llm-mode real --config config/local.yaml` — real provider soak
- `--dry-run` — seed project, skip generation

Checks:
- Project seeding with long scene beats (12 beats)
- Segment events: `segment_started`, `segment_completed`, `segment_failed`
- Final workflow state reaches reviewed/awaiting_publish
- Word count >= 15000 (when real)

API key safety:
- Explicitly checks for `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, or `DEEPSEEK_API_KEY`
- Missing key → exit code 2 with clear skipped message
- No accidental real calls without keys

### 4. Production Ops Runbook

New: `docs/codex/release/production-ops-runbook.md`

Covers:
- **Backup**: DB location, files to back up, online vs. offline methods, frequency
- **Recovery**: Stop/start service, DB restore, migration health check, smoke validation
- **Fault Diagnosis**:
  - Live API version mismatch → `/api/health`, PID, start time, source root
  - Port occupied → `lsof`, safe stop sequence
  - Real LLM failure → provider, timeout, token budget, segment events
  - Workflow stuck → run health dashboard, checkpoint records
  - Desktop sidecar failure → logs, version mismatch, manual start test
- **Sensitive Data**: API key redaction in diagnostics
- **Release Checklist**: Pre/post-deployment verification commands

### 5. Version Bump to 6.6.20

| File | Old | New |
|------|-----|-----|
| `novel_factory/version.py` | `6.6.19` | `6.6.20` |
| `frontend/package.json` | `6.6.19` | `6.6.20` |
| `frontend/package-lock.json` | `6.6.19` | `6.6.20` |
| `desktop/package.json` | `6.6.19` | `6.6.20` |
| `desktop/package-lock.json` | `6.6.19` | `6.6.20` |

### 6. Documentation Sync

| Document | Action |
|----------|--------|
| `AGENTS.md` | Baseline → v6.6.20 |
| `docs/codex/README.md` | v6.6.20 as current production ops baseline |
| `CHANGELOG.md` | v6.6.20 section added |
| `docs/codex/planning/novel-factory-version-planning-index.md` | v6.6.20 entry added |

---

## Test Coverage

### New Tests

- `tests/test_release_smoke.py` (9 tests, 1 skipped):
  - `test_smoke_skip_api_all_required_pass`
  - `test_smoke_json_output_structure`
  - `test_smoke_cli_version_check_passes`
  - `test_smoke_frontend_version_matches_runtime`
  - `test_smoke_desktop_version_matches_runtime`
  - `test_smoke_desktop_sidecar_version_matches`
  - `test_smoke_api_health_with_running_api` (skipped — requires running server)
  - `test_health_includes_startup_metadata`
  - `test_health_version_matches_runtime`

- `tests/test_version_alignment.py` (8 tests, extended from v6.6.19):
  - Added `TestLockfileVersions` covering frontend/desktop package-lock.json

### Verification Results

```bash
python3 -m pytest -q
```

Result: **2741 passed, 1 skipped, 0 failed**

```bash
cd frontend && npm run typecheck && npm run lint && npm run build && npm test -- --run
```

Result: typecheck OK, lint OK, build OK, vitest **300 passed**

```bash
cd desktop && npm run typecheck && npm run build
```

Result: typecheck OK, build OK

```bash
python3 -m novel_factory.cli --version
```

Result: `novelos 6.6.20`

```bash
python3 scripts/release_smoke.py --skip-api --json
```

Result: `{"ok": true, "version_expected": "6.6.20", ...}`

```bash
python3 scripts/soak_real_llm_long_chapter.py --llm-mode stub --dry-run --json
```

Result: `{"ok": true, "version": "6.6.20", "dry_run": true, ...}`

### Real LLM Soak

Real LLM soak not run in this review to avoid live provider cost; stub non-dry-run passed; real run remains manual verification.

---

## Files Changed

```
novel_factory/version.py
frontend/package.json
frontend/package-lock.json
desktop/package.json
desktop/package-lock.json
novel_factory/api/routes/health.py
AGENTS.md
docs/codex/README.md
CHANGELOG.md
docs/codex/planning/novel-factory-version-planning-index.md
scripts/release_smoke.py                        (NEW)
scripts/soak_real_llm_long_chapter.py           (NEW)
tests/test_release_smoke.py                     (NEW)
docs/codex/release/production-ops-runbook.md    (NEW)
docs/codex/reports/novel-factory-v6.6.20-completion-report.md  (NEW)
```

---

## Known Follow-Up

1. **Real LLM soak**: Requires API key to validate. The script structure is tested in stub/dry-run mode.
2. **Desktop release build**: `desktop/release/mac-arm64/` still contains v6.6.19 binary. Fresh packaging needed for release artifact.

---

## Conclusion

v6.6.20 successfully hardens the production readiness of the v6.6.19 baseline by adding runtime diagnostics, release smoke testing, soak infrastructure, and operational documentation. All automated tests pass. The branch is ready for merge into `main`.
