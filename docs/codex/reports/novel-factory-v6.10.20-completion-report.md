# Novelos v6.10.20 — Completion Report

> **Version**: v6.10.20
> **Title**: Exception Unification Framework — Layered Exception Types + Pilot Migration
> **Status**: Shipped
> **Date**: 2026-07-10

---

## Summary

v6.10.20 establishes a 4-layer exception hierarchy (`AgentExecutionError`, `DBTransactionError`, `APIValidationError`, `LLMProviderError`) and pilots it across the agent runtime and 6 API route files, without touching any existing `except Exception:` blocks.

## Delivered Changes

### 4-Layer Exception Types

- `novel_factory/exceptions.py`: 4 domain-specific exception classes
  - `AgentExecutionError`: wraps agent + step + inner error for structured debugging
  - `DBTransactionError`: database/repository layer failures
  - `APIValidationError`: client request validation failures (4xx class) with `code` and `message` attributes
  - `LLMProviderError`: LLM provider call failures (rate limit, timeout, etc.)
- All inherit from `Exception` so existing `except Exception:` blocks continue to work
- New code should catch the specific type when possible

### Pilot Migration (Phase 1: Agent Runtime)

- `agent_runtime/base.py` `run()`: Agent execution failures now wrapped in `AgentExecutionError` with structured agent/step logging
- No existing `except Exception:` blocks were modified (backward compatible)

### Pilot Expansion (Phase 2: API Routes)

- `api/routes/runs.py` `batch_mark_stuck`: Empty run_ids and >50 limits now raise `APIValidationError`
- `api/routes/production.py` 4 endpoints migrated: `production-next`, `health-summary`, `auto-fill`, `arc-plan`
- `api/routes/genesis.py` 5 endpoints migrated: `generate`, `latest`, `impact`, `approve`, `reject`
- `api/routes/projects.py`, `chapter_readonly.py`, `chapter_briefs.py`: additional validation endpoints
- Each endpoint catches `APIValidationError` before generic `Exception`, preserving exact error codes

### Tests

- `tests/test_v61020_exceptions.py`: 13 tests covering construction, attributes, Exception-catch compatibility, tuple-catch, hierarchy

## Verification

- `pytest -q`: 3,762 passed, 1 skipped (full green)

## Known Follow-Up Risk

- Remaining `api/` routes and `workflow/` (86 `except Exception`) deferred to v6.10.21+ or v6.11.0
- `db/repositories/` and `llm/` full `DBTransactionError`/`LLMProviderError` coverage deferred

## Documentation

- `docs/codex/planning/novel-factory-v6.10.20-exception-unification-plan.md`: original plan
- `docs/codex/design/v6.10.20-exception-unification-spec.md`: design spec
- `CHANGELOG.md`: v6.10.20 entry
