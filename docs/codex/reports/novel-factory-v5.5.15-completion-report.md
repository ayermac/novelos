# v5.5.15 Completion Report

## Summary

v5.5.15 Production Readiness Closure has passed review and real-project acceptance. Novelos is now in a short-term usable closure state for the current production-readiness line.

## Review Results

| # | Check | Result | Notes |
| --- | --- | --- | --- |
| 1 | `WORKFLOW_ALREADY_RUNNING` handled by all generation entries | Pass | 5 entries protected: `/run/chapter`, Overview button, 2 ChapterWorkspace entries, `auto_generate=1` |
| 2 | `health-summary.contradictions` rendered as understandable Overview actions | Pass | Contradiction items render in health cards with `action_label` buttons |
| 3 | Obsolete sessions do not show "reconnect" as the primary CTA | Pass | `!isSessionObsolete` gating plus "清理旧会话" replacement CTA |
| 4 | `novel_3v2o` real-project acceptance | Pass | 5 acceptance checks passed |
| 5 | README has no stale version baseline count residue | Pass | No `X/X passed` pattern residue in the planning README |

## Review Fixes

Key findings and fixes across two review rounds:

### Round 1

`POST /run/chapter` only checked `WORKFLOW_ALREADY_RUNNING` for running workflows. It did not prevent chapters in terminal states such as `reviewed`, `awaiting_publish`, or `published` from being generated again.

Fixes:

- `run.py`: added `CHAPTER_ALREADY_COMPLETED` blocking for terminal chapter states.
- `production.py`: added terminal-state and running-workflow checks for `generate_chapter` and `continue_next_chapter` auto-run steps.

### Round 2 — Unified Guard + Runner Semantics

The initial terminal-state guard was implemented inline in `run.py`, but `GET /run/chapter/stream` (SSE) and auto-run paths duplicated partial checks with inconsistent behavior. This meant an SSE client could bypass the guard and trigger duplicate generation for a terminal chapter.

Fixes:

- Extracted `_run_guards.py` with `check_chapter_run_guard()` — a single guard function covering `CHAPTER_ALREADY_COMPLETED` and `WORKFLOW_ALREADY_RUNNING`. All three generation entry points (`POST /run/chapter`, `GET /run/chapter/stream`, auto-run) now import from this module.
- `runner.py` direct-call path (`run_with_graph` / `run_with_graph_stream`) short-circuits on terminal statuses. Previously `reviewed` always returned `requires_human=False`, but in real mode `reviewed` semantically means "awaiting human publish". Now `reviewed + llm_mode == "real"` returns `requires_human=True` / `awaiting_publish=True`, matching the HTTP route semantics. `published` and stub-mode `reviewed` remain non-blocking.
- `runs.py` SSE endpoint now uses the unified guard instead of its own inline check.
- Split accidentally merged test `test_published_chapter_with_stale_workflow_contradiction` back into an independent function; removed unused `import ast`.

## Real Project Acceptance: `novel_3v2o`

| Acceptance Item | Result |
| --- | --- |
| Chapter 3 (`published`) cannot start generation again | Pass: `CHAPTER_ALREADY_COMPLETED` |
| Overview does not show old disconnected session as primary state | Pass: `obsolete_sessions=0` |
| Stale running workflow has a clear handling entry | Pass: `action_label="查看章节"` |
| `production-next` recommends a non-generation action | Pass: `recover_blocked_run` |
| Chapter 5 (`planned`) can start normally | Pass: `workflow_status=completed` |

## Test Baseline

- pytest: 1844/1844 passed (v5.5.15 closure final)
- vitest: 67/67 passed
- frontend typecheck: passed
- frontend lint: passed
- frontend production build: passed

## Commits

- `49987a4`: v5.5.15 core implementation
- `3c8cd22`: `CHAPTER_ALREADY_COMPLETED` terminal-state guard
- `fb984df`: unified run guard + runner reviewed semantics + test cleanup

## Conclusion

v5.5.15 Review passed. The project enters a short-term usable closure state. Future planning should not continue expanding recovery-only work by default; the next direction should be selected from the personal author workbench priorities documented under `docs/codex/next/`.
