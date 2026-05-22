# v6.6.10 API Contract & Frontend State Semantics Closure — Completion Report

## Summary

Established a unified API semantic contract (`OperationResult`) and frontend status interpretation layer (`statusSemantics.ts`). The core principle: `ok=true` means HTTP request processed, NOT business success. Domain-level outcomes are conveyed via `domain_status` with clear severity, retryability, and action hints.

## New Contract Fields

### OperationResult (backend)
- `ok: bool` — HTTP request success
- `domain_status: DomainStatus` — 9 values: success/partial_success/fallback/degraded/failed/blocked/needs_human/pending/ignored
- `message: str` — technical message
- `user_message: str` — user-facing message
- `technical_message: str | None` — optional debug info
- `retryable: bool` — can the user retry?
- `blocking: bool` — is further progress blocked?
- `next_action: str | None` — what to do next
- `action_label: str | None` — button label for next action
- `severity: Severity` — success/info/warning/error
- `flags: dict[str, bool]` — semantic flags (memory_trusted, memory_fallback, etc.)
- `details: dict[str, Any]` — structured details (sensitive data auto-scrubbed)

### Frontend statusSemantics.ts
- `normalizeOperationResult(raw)` — handles both new (with domain_result) and legacy (without) responses
- `getStatusBadge(result)` → label, severity, cssClass, icon
- `isBusinessSuccess(result)` — only true for domain_status="success"
- `getMemoryStatusDisplay(status)` → label, severity, userMessage, isBusinessSuccess
- `severityColor()` / `severityBadgeClass()` — CSS custom properties for dark mode

## Endpoints Integrated

| Endpoint | Added Field | Description |
|----------|-------------|-------------|
| `GET /api/runs/{run_id}` | `domain_result` | Combined workflow + memory domain status |
| `POST /api/runs/{run_id}/memory/backfill` (success) | `domain_result` | Trusted vs fallback extraction |
| `POST /api/runs/{run_id}/memory/backfill` (error) | `domain_result` in error details | Fallback/degraded/failed classification |

## Frontend Components That Can Use statusSemantics

The following components currently have hardcoded status logic and should be migrated to use `statusSemantics.ts`:

| Component | Current Pattern | Migration Path |
|-----------|----------------|----------------|
| `RunDetail.tsx` | Nested ternary for memory_status | `getMemoryStatusDisplay()` |
| `Dashboard.tsx` | Custom `getStatusColor()` | `severityColor()` + `severityBadgeClass()` |
| `WorkflowTimeline.tsx` | Custom `stepStatusClass()` | `getNodeStatusBadge()` |
| `MemoryUpdatesModule.tsx` | Local `STATUS_LABELS` Record | `getMemoryStatusDisplay()` |
| `GenesisModule.tsx` | Custom `statusClass()` | `severityBadgeClass()` |

Note: Component migration is not yet done — the spec says "不做大规模 UI 改版". The helpers are available for incremental adoption.

## Fallback/Degraded/Partial_Success/Failed Display Semantics

| Domain Status | Badge Label | Badge CSS | Color | Icon |
|---------------|-------------|-----------|-------|------|
| success | 成功 | badge-success | Green (--color-success) | ✓ |
| partial_success | 部分完成 | badge-warning | Amber (--color-warning) | ⚠ |
| fallback | 降级完成 | badge-warning | Amber (--color-warning) | ⚠ |
| degraded | 降级 | badge-warning | Amber (--color-warning) | ⚠ |
| failed | 失败 | badge-error | Red (--color-error) | ✗ |
| blocked | 阻塞 | badge-error | Red (--color-error) | ⊘ |
| needs_human | 需人工介入 | badge-warning | Amber (--color-warning) | ⚑ |
| pending | 进行中 | badge-info | Blue (--color-info) | ◌ |
| ignored | 已忽略 | badge-info | Blue (--color-info) | — |

Key rule: **fallback/degraded/partial_success MUST use warning (amber), NOT success (green)**.

## Test Results

| Test Suite | Result |
|-----------|--------|
| `test_v6610_api_contract_semantics.py` | 35 passed |
| `frontend statusSemantics.test.ts` | 34 passed |
| `test_v667/668/669` (adjacent) | 141 passed |
| Backend full suite | 2471 passed |
| Frontend typecheck | ✅ |
| Frontend lint | ✅ |
| Frontend build | ✅ |

## Unconnected Endpoint Risk List

The following endpoints do NOT yet include `domain_result` but could benefit from it:

| Endpoint | Risk | Priority |
|----------|------|----------|
| `POST /api/projects/{pid}/memory-batches/{bid}/apply` | Apply success/failure could be more structured | P2 |
| `POST /api/memory/apply` | Same as above (canonical route) | P2 |
| `GET /api/projects/{pid}/chapters/{cn}/workflow-timeline` | Timeline lacks domain_status for memory_curator node | P2 |
| `POST /api/run-chapter` | Chapter run result could use domain_result | P3 |
| All recovery endpoints | Recovery actions could use domain_result for clarity | P3 |

These are NOT blocking — the contract is additive and can be adopted incrementally.
