# v6.7.7 Genesis Generation Progress Streaming — Completion Report

## Summary

Implemented SSE-based progress streaming for Genesis generation, providing real-time visibility into the multi-segment generation pipeline.

## Changes Made

### Backend (`novel_factory/api/routes/genesis.py`)

1. **Progress event infrastructure**: Added in-memory `asyncio.Queue` store, `_push_progress()`, `_make_progress_event()`, and `GENESIS_SEGMENT_LABELS` constants
2. **Modified `_generate_stub_draft()`**: Added `run_id` and `progress` keyword arguments; emits `segment_started`/`segment_completed` for foundation/cast/plot segments and per-chunk `chapter_start`/`chapter_end` for instructions
3. **Modified `_generate_real_draft()`**: Same progress callback threading; emits events at each segment boundary
4. **Modified `_generate_real_draft_with_scaffold_fallback()`**: Passes progress callback through; emits repair phase events
5. **Modified `_complete_real_genesis_draft()`**: Accepts progress callback parameters
6. **New `start_genesis_generate()` endpoint**: `POST /api/projects/{project_id}/genesis/generate/start` — creates running genesis, launches background task, returns `run_id` + `stream_url`
7. **New `_run_genesis_background()`**: Background async task that runs full generation pipeline with progress events
8. **New `stream_genesis_progress()` endpoint**: `GET /api/projects/{project_id}/genesis/generate/stream/{run_id}` — SSE streaming endpoint with keepalive and terminal event handling
9. **Interrupted run handling**: A `running` Genesis row without a live in-memory queue is marked failed and reported via `genesis_failed`, preventing fake progress after desktop/API restart

### Version (`novel_factory/version.py`)

- Updated from `6.7.6` to `6.7.7`

### Author Stability (`novel_factory/agents/author.py`)

1. **Segment boundary merge**: Segmented real-mode Author drafts now merge overlapping segment tails instead of duplicating repeated paragraphs
2. **Final segment targeted repair**: When a segmented Author draft misses the final scene beat or chapter `ending_hook`, Author retries only the final segment with explicit final-beat context
3. **Quality preserved**: If the model still fails to write the final hook, the quality gate remains blocking; the system does not synthesize pass-through prose

### Frontend (`frontend/src/components/project/GenesisModule.tsx`)

1. Added `GenesisProgressStep` and `GenesisProgressState` interfaces
2. Added `createInitialProgress()` factory function
3. Added `progress` state and `eventSourceRef` ref
4. Added `connectProgressStream()` callback with full EventSource lifecycle management
5. Modified `handleGenerate()` to prefer start endpoint with SSE, fallback to sync
6. Creates a local `running` Genesis record immediately after async start so first-time generation shows progress without waiting for polling
7. Normalizes `/api/...` stream URLs before passing them through `apiUrl()` to avoid `/api/api/...` EventSource connections
8. Reconnects the EventSource when an already-running Genesis run is loaded from the latest-run endpoint
9. Shows default phase labels immediately for running Genesis runs, even before the first SSE event arrives
10. Updated running state UI to show step-by-step progress when streaming is active
11. Added CSS styles for progress steps (`.genesis-progress`, `.genesis-progress-step`, etc.)
12. Added cleanup `useEffect` for EventSource on unmount
13. Normalizes reconnect step ordering so later instruction events mark earlier phases complete instead of leaving impossible pending/running combinations

### Frontend Version (`frontend/package.json`)

- Updated from `6.7.6` to `6.7.7`

### Desktop Version (`desktop/package.json`)

- Updated from `6.7.6` to `6.7.7`

### Tests (`tests/test_v677_genesis_progress_streaming.py`)

16 tests in 3 test classes:

- **TestGenesisStartEndpoint** (4 tests): start returns run_id/stream_url, rejects empty input, rejects duplicate running, inherits project defaults
- **TestGenesisSSEStream** (7 tests): streams started event, streams segment events in order, streams completed event, immediate done for completed run, not found for invalid run, project mismatch, orphaned running run interruption
- **TestGenesisProgressIntegration** (5 tests): full flow, sync endpoint backward compat, path-style backward compat, failed genesis event, background task completion

### Author Tests (`tests/test_agents.py`)

- Added regression coverage for final scene beat/hook targeted repair
- Added regression coverage that missing-hook repairs do not fake-pass when the model still fails the final hook
- Added regression coverage for segmented boundary overlap merging

### Frontend Tests (`frontend/src/components/project/__tests__/v677-genesis-progress-streaming.test.tsx`)

- Added regression coverage proving async Genesis start immediately displays the running progress surface
- Added regression coverage proving `/api/...` stream URLs are normalized before EventSource connection
- Added regression coverage proving already-running Genesis runs reconnect to their stream and show progress labels
- Added regression coverage proving reconnecting to later instruction events marks prior phases complete

### Documentation

- `docs/codex/specs/novel-factory-v6.7.7-genesis-progress-streaming-spec.md` — Technical spec
- `docs/codex/reports/novel-factory-v6.7.7-completion-report.md` — This report
- `CHANGELOG.md` — Updated with v6.7.7 entry
- `docs/codex/README.md` — Updated current baseline links
- `docs/codex/planning/novel-factory-version-planning-index.md` — Added v6.7.7 row

## Verification

| Check | Result |
|-------|--------|
| v6.7.7 backend tests | 16/16 passing |
| v6.7.7 frontend regression tests | 3/3 passing |
| Author targeted regression tests | 28/28 passing |
| Author/segmented/title regression bundle | 130/130 passing |
| Existing genesis tests | 24/24 passing (no regression) |
| TypeScript typecheck | passing |
| Frontend vitest | 328/328 passing |
| Frontend lint | passing |
| Frontend build | passing |
| Full backend regression | 2920 passed, 1 skipped |

## Known Limitations

1. **In-memory queue**: Progress queues are stored in-process memory. Server restarts lose live streaming state; reconnecting to such a run marks it failed so the user can retry instead of seeing fake progress.
2. **No authentication**: SSE endpoints have no auth beyond project ownership validation.
3. **Queue cleanup**: Queues are cleaned up 5 seconds after completion. Very slow consumers may miss events.
