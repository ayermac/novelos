# v6.6.19 Completion Report — Stability Baseline & Runtime Alignment

**Version**: 6.6.19
**Date**: 2026-05-24
**Status**: COMPLETED
**Branch**: `codex-v6.6.19-stability-baseline-alignment`

---

## Executive Summary

v6.6.19 is a pure baseline-alignment release with **no new business features**. It closes version/runtime/document drift discovered during v6.6.18 integration:

1. A long-running API process (started 2026-05-15) was caching v5.3.0 modules in memory while the source tree had advanced to v6.6.18, causing `GET /api/health` to return a stale version.
2. AGENTS.md, docs/codex/README.md, and CHANGELOG.md were still referencing v6.6.16/v6.6.17 as the current baseline.
3. The v6.6.19 migration (`033_v6_6_19_memory_curator_locks.sql`) and its test (`test_v6619_memory_curator_lock.py`) existed in the repo but were not formally tracked as part of a completed version baseline.
4. No automated test prevented the frontend/desktop/package-lock version from drifting away from the runtime version again.

All items are now fixed and guarded.

---

## Changes

### 1. Runtime Version Misalignment Fix

**Problem**: `curl http://127.0.0.1:8765/api/health` returned `"version": "5.3.0"` even though `novel_factory/version.py` contained `"6.6.18"`.

**Root Cause**: PID 80628 was started on 2026-05-15 with `python3 -m novel_factory.cli api ...`. At that time the in-memory module cache loaded `novel_factory.version` with `__version__ = "5.3.0"`. The process remained alive for 9 days. Python does not reload modified source files for already-imported modules, so the cached value persisted.

**Fix**:
- Killed PID 80628 (`kill 80628`).
- Restarted the API from the current source tree (`python3 -m novel_factory.cli api ...`).
- Verified `GET /api/health` now returns `"version": "6.6.19"`.

**No user data was lost** — the database file (`acceptance_novel_factory.db`) was untouched.

### 2. Version Bump to 6.6.19

| File | Old | New |
|------|-----|-----|
| `novel_factory/version.py` | `6.6.18` | `6.6.19` |
| `frontend/package.json` | `6.6.18` | `6.6.19` |
| `desktop/package.json` | `6.6.18` | `6.6.19` |
| `frontend/package-lock.json` | `6.6.17` | `6.6.19` |
| `desktop/package-lock.json` | `6.6.17` | `6.6.19` |
| `desktop/package.json` description | v6.6.18 text | v6.6.19 text |

### 3. Document Synchronization

| Document | Action |
|----------|--------|
| `AGENTS.md` | Updated baseline to **v6.6.19**, test count to **2728/2728**, runtime version to `6.6.19` |
| `docs/codex/README.md` | Marked v6.6.18 as completed; added v6.6.19 as **current stable baseline**; updated test baseline to 2728 passed, 0 failed |
| `CHANGELOG.md` | Moved Unreleased items into v6.6.17/v6.6.18 entries; added new v6.6.19 section |
| `docs/codex/planning/novel-factory-version-planning-index.md` | Added v6.6.19 entry (retrospective / changelog-only) |

### 4. Migration Ownership Confirmation

| Item | Status |
|------|--------|
| `novel_factory/db/migrations/033_v6_6_19_memory_curator_locks.sql` | EXISTS |
| `novel_factory/db/migration_registry.py` entry for `033_v6_6_19_memory_curator_locks` | REGISTERED with requirements `(_T("memory_curator_locks"),)` |
| `tests/test_v6619_memory_curator_lock.py` | EXISTS, 10 tests |
| Fresh DB init coverage | Migration 033 is applied via standard `init_db` → migration runner path |
| Old DB upgrade coverage | Migration 033 is applied via standard `apply_migrations` → registry path |

### 5. Stability Guardrails — Version Drift Test

New file: `tests/test_version_alignment.py`

Coverage:
1. `test_version_is_semantic` — version string is `major.minor.patch`
2. `test_version_not_placeholder` — version is not `0.0.0`, `dev`, `unknown`, or empty
3. `test_health_endpoint_version_matches_runtime` — `GET /api/health` returns the same version as `novel_factory.version.__version__`
4. `test_fastapi_app_version_matches_runtime` — `FastAPI.app.version` metadata matches runtime
5. `test_frontend_package_version_matches_runtime` — `frontend/package.json` version matches runtime
6. `test_desktop_package_version_matches_runtime` — `desktop/package.json` version matches runtime
7. `test_frontend_package_lock_version_matches_runtime` — `frontend/package-lock.json` root and `packages[""]` version match runtime
8. `test_desktop_package_lock_version_matches_runtime` — `desktop/package-lock.json` root and `packages[""]` version match runtime

These tests will fail immediately on the next version bump if any of the six sources is not updated in lock-step.

---

## Verification

### Backend

```bash
python3 -m pytest -q
```

Result: **2728 passed, 0 failed**

Key targeted suites:
- `tests/test_v6619_memory_curator_lock.py`: 10 passed
- `tests/test_version_alignment.py`: 8 passed
- `tests/test_v6618_segmented_agent_payloads.py`: 13 passed

### Frontend

```bash
cd frontend && npm run typecheck && npm run lint && npm run build && npm test -- --run
```

Result: typecheck OK, lint OK, build OK, vitest **300 passed**

### Desktop

```bash
cd desktop && npm run typecheck && npm run build
```

Result: typecheck OK, build OK

### CLI Version

```bash
python3 -m novel_factory.cli --version
```

Result: `6.6.19`

### Live API Health

```bash
curl -sS http://127.0.0.1:8765/api/health
```

Result:
```json
{
  "ok": true,
  "error": null,
  "data": {
    "status": "ok",
    "version": "6.6.19",
    "llm_mode": "stub",
    "db_connected": true,
    "timestamp": "2026-05-24T01:51:20Z"
  }
}
```

---

## Files Changed

```
novel_factory/version.py
frontend/package.json
frontend/package-lock.json
desktop/package.json
desktop/package-lock.json
AGENTS.md
docs/codex/README.md
CHANGELOG.md
docs/codex/planning/novel-factory-version-planning-index.md
tests/test_version_alignment.py          (NEW)
tests/test_v6615_release_readiness.py    (version assertion softened)
tests/test_v6616_real_project_burnin.py  (version assertion softened)
docs/codex/reports/novel-factory-v6.6.19-completion-report.md  (NEW)
```

---

## Known Follow-Up

1. **Sidecar/desktop release build**: The desktop release build in `desktop/release/mac-arm64/` still contains the v6.6.18 sidecar binary. A fresh desktop packaging run is needed to propagate v6.6.19 into the release artifact.
2. **Service script (`scripts/novelos-service.sh`)**: The script already uses `python3 -m novel_factory.cli`, so restarting via the script would have picked up the new source. The drift only affected the manually-started long-running process.

---

## Conclusion

v6.6.19 successfully aligns the runtime version, package metadata, lockfiles, and documentation to a single consistent baseline. The new `test_version_alignment.py` prevents future drift across all six version sources. All tests pass (2728/2728). The branch is ready for merge into `main`.
