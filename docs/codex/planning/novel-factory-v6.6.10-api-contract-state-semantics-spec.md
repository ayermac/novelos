# v6.6.10 API Contract & Frontend State Semantics Closure — Spec

## Problem

Multiple recurring issues stem from inconsistent API response semantics and frontend status interpretation:

1. `ok=true` masks business failures — MemoryCurator fallback/degraded results show as "success"
2. Frontend displays fallback/degraded/failed as "成功" (success green)
3. Manual backfill creates new trusted memory but UI still shows old fallback
4. `awaiting_publish` + memory fallback displays as "全部成功" (all success)
5. Different endpoints use inconsistent `ok`/`message`/`status` patterns
6. Status display logic scattered across components with hardcoded string comparisons

## Goals

1. **Unified OperationResult contract** — every API response carries a domain-level status
2. **MemoryCurator semantics** — trusted/fallback/degraded/failed clearly distinguished
3. **Workflow run semantics** — partial_success when memory is degraded
4. **Frontend statusSemantics** — single source of truth for badge/display/retry logic
5. **No data leakage** — API responses must not expose API keys, tokens, or full content

## Design

### Backend: OperationResult (`novel_factory/api/contracts.py`)

New module with:
- `DomainStatus` — 9 values: success, partial_success, fallback, degraded, failed, blocked, needs_human, pending, ignored
- `OperationResult` — dataclass with ok, domain_status, message, user_message, technical_message, retryable, blocking, next_action, action_label, severity, flags, details
- Helper constructors: `success()`, `partial_success()`, `fallback()`, `degraded()`, `failed()`, `blocked()`, `needs_human()`, `ignored()`
- `memory_status_to_domain_result()` — maps trusted/fallback/failed/missing to OperationResult
- `workflow_run_to_domain_status()` — derives domain result from workflow + chapter + memory state
- Automatic sensitive data scrubbing in `to_dict()`

### Endpoint Integration

| Endpoint | Added Field | Notes |
|----------|-------------|-------|
| `GET /api/runs/{run_id}` | `domain_result` | Workflow + memory combined |
| `POST /api/runs/{run_id}/memory/backfill` | `domain_result` | In response body or error details |
| Error responses for backfill | `domain_result` in `details` | Preserves backward compat |

### Frontend: `statusSemantics.ts`

New module with:
- `OperationResult` type matching backend
- `normalizeOperationResult(raw)` — handles both new and legacy responses
- `getStatusBadge(result)` — badge label, severity, CSS class, icon
- `isBusinessSuccess(result)` — only true for `success`, not fallback/degraded
- `isRetryable(result)`, `isBlocking(result)` — query helpers
- `getActionHint(result)` — what the user should do next
- `getMemoryStatusDisplay(status)` — label, severity, user message
- `severityColor()`, `severityBadgeClass()` — CSS custom properties for dark mode

### Key Semantic Rules

| Domain Status | ok | Severity | Display | Retryable | Blocking |
|---------------|----|----------|---------|-----------|----------|
| success | true | success | 成功 (green) | no | no |
| partial_success | true | warning | 部分完成 (amber) | yes | no |
| fallback | true | warning | 降级完成 (amber) | yes | no |
| degraded | true | warning | 降级 (amber) | yes | no |
| failed | false | error | 失败 (red) | yes | no |
| blocked | false | error | 阻塞 (red) | no | yes |
| needs_human | false | warning | 需人工介入 (amber) | yes | yes |
| pending | true | info | 进行中 (blue) | no | no |
| ignored | true | info | 已忽略 (blue) | no | no |

## Constraints

- No LangGraph topology changes
- No MemoryCurator extraction logic rewrite
- No full frontend state management rewrite
- No large state machine library
- Old API fields preserved; new fields are additive
- Fallback does not block publishing (unless existing policy blocks it)
- No destructive migrations
- Python 3.9 compatible

## Verification

- `python3 -m pytest tests/test_v6610_api_contract_semantics.py -q` — 35 tests
- `cd frontend && npm run test -- statusSemantics` — 34 tests
- `python3 -m pytest -q` — 2471 passed
- `cd frontend && npm run typecheck && npm run lint && npm run build` — all pass
