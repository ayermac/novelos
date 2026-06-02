# Novel Factory v6.8.4 — SSE Streaming & Workflow Observability

**Version**: v6.8.4
**Type**: Bug Fix + Reliability Hardening + Architecture
**Priority**: HIGH
**Status**: Planning

---

## Overview

v6.8.4 fixes systemic defects in the SSE (Server-Sent Events) streaming pipeline that
cause silent disconnections, lost events, and misleading UI states during chapter
production workflows.

**Problem Statement**: Users experience SSE connections dropping silently during long
LLM calls (30-90s), losing real-time progress feedback. When the connection recovers,
the frontend has no mechanism to replay missed events. The UI also misreports workflow
blocking as errors.

**Root Causes**:
0. Quality gate runs inside agent node — timeline events out of order, debugging difficult
1. No heartbeat/keepalive — proxies kill idle connections during LLM calls
2. No frontend auto-reconnect — connection drops are permanent
3. Race condition — SSE connects before workflow_run record exists
4. Silent exception swallowing — real errors are invisible
5. `blocked` status treated as `failed` — misleading UI
6. Terminal state set incomplete — may miss some terminal states

---

## Goals

- **G1**: SSE connections survive long LLM calls through proxy layers
- **G2**: Frontend automatically reconnects on disconnect with event replay
- **G3**: Race conditions between run creation and SSE connection are handled
- **G4**: Errors are logged and visible, not silently swallowed
- **G5**: `blocked` and `failed` statuses are correctly distinguished in UI

---

## Technical Design

### Phase 1: Backend Heartbeat (P0)

**File**: `novel_factory/api/routes/workflow_timeline.py`

Add SSE heartbeat comments in the polling loop. Proxy servers (nginx, cloudflare,
AWS ALB) typically timeout idle connections at 60s. A 15s heartbeat keeps the
connection alive.

**Change**:
```python
# In the poll loop, after await asyncio.sleep(poll_interval):
heartbeat_counter += 1
if heartbeat_counter >= 10:  # every ~15s (10 * 1.5s interval)
    heartbeat_counter = 0
    yield ":heartbeat\n\n"
```

Also send heartbeat during the replay phase if there are many events (batched replay
can take >60s for long runs).

**Rationale**: Zero-cost, fixes the most common disconnect cause.

---

### Phase 2: Frontend Auto-Reconnect (P0)

**File**: `frontend/src/hooks/useWorkflowStream.ts`

Add exponential backoff reconnection when the SSE connection drops.

**Change**:
```typescript
// On error, instead of stopStream():
eventSource.onerror = () => {
    setIsConnected(false)
    eventSource.close()
    eventSourceRef.current = null

    // Auto-reconnect with exponential backoff
    if (!doneStatus && isActive) {
        const delay = Math.min(1000 * Math.pow(2, retryCount), 16000)
        retryCount++
        reconnectTimerRef.current = setTimeout(() => {
            if (!doneStatus && isActive) {
                const reconnectUrl = url + (lastEventId ? `&since_id=${lastEventId}` : '')
                connect(reconnectUrl)
            }
        }, delay)
    }
}
```

Track `lastEventId` from received events. Pass it as `since_id` on reconnect so the
backend replays only missed events.

Also update `useSSEStream.ts` with the same reconnection logic.

**Rationale**: Users no longer need to manually refresh after connection drops.

---

### Phase 3: Race Condition Fix (P1)

**File**: `novel_factory/api/routes/workflow_timeline.py`

When no `run_id` is provided and no run exists yet, wait briefly before giving up.

**Change**:
```python
if not target_run and not run_id:
    # Wait up to 5s for the run to be created (background task may be slow)
    for _ in range(10):
        await asyncio.sleep(0.5)
        runs = repo.get_workflow_runs_for_project(project_id, chapter_number=chapter_number, limit=1)
        if runs:
            target_run = runs[0]
            break
```

**Rationale**: Background task creates the run within 1-2s typically. A 5s wait
covers edge cases without blocking indefinitely.

---

### Phase 4: Error Logging (P1)

**File**: `novel_factory/api/routes/workflow_timeline.py`

Replace `except Exception: pass` with proper logging.

**Change** (3 locations):
```python
# Before:
except Exception:
    pass

# After:
except Exception as e:
    logger.warning("SSE event_generator error: %s", e, exc_info=True)
```

**Rationale**: Errors become visible in logs for debugging without breaking the stream.

---

### Phase 5: Blocked vs Failed Distinction (P2)

**File**: `frontend/src/hooks/useSSEStream.ts`

Treat `blocked` as a distinct state from `failed`. Blocked means the workflow needs
human intervention but completed its automated path normally.

**Change**:
```typescript
// Before:
if (status === 'failed' || status === 'blocked') {
    onError?.(message, ...)
    return
}

// After:
if (status === 'failed') {
    onError?.('章节生成失败', ...)
    return
}
if (status === 'blocked') {
    onComplete?.({ type: 'run_complete', run_id: runId, status: 'blocked' })
    return
}
```

**Rationale**: `blocked` is a valid terminal state, not an error. The UI should show
"需要人工处理" as a status, not an error banner.

---

### Phase 6: Terminal State Completeness (P2)

**File**: `novel_factory/api/routes/workflow_timeline.py`

Add all terminal states to the check.

**Change**:
```python
TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "blocked", "cancelled"})
```

Use in both the initial check (line 1000) and the polling check (line 1042).

---


### Phase 7: Quality Gate as Independent Node (P2 — Architecture)

**Files**: `novel_factory/workflow/nodes.py`, `novel_factory/workflow/graph.py`

Currently `_handle_retryable_quality_gate` runs **inside** each agent node (line 876):
```python
result = _handle_retryable_quality_gate(state, repo, agent.run(state))
```

This causes quality gate checks, state updates, retry_count increments, and
revision routing to all happen inside the agent node's execution context.
LangGraph only sees the final return value — it cannot observe the gate check
as a distinct workflow step.

**Problems**:
- Timeline events appear out of order (LLM started before revision_router)
- Debugging quality gate failures requires tracing inside agent node code
- Cannot independently monitor/retry quality gate logic

**Proposed Change**: Extract quality gate check into a dedicated LangGraph node
between each agent and the revision_router.

```
author → quality_gate_check → (pass) → polisher
                             → (fail) → revision_router
```

**Implementation**:
1. New `quality_gate_check_node(state, repo)` function in nodes.py
2. Agent nodes return raw result without `_handle_retryable_quality_gate`
3. New node applies quality gate logic, sets retry_count, routes
4. Update graph.py to add quality_gate_check nodes between each agent pair
5. Each agent pair gets its own gate node (author_gate, polisher_gate, etc.)

**Impact**: Cleaner timeline events, independent quality gate monitoring,
easier debugging. This is the root cause of issue #3 from v6.8.3 production
analysis (event ordering confusion).

**Note**: This is a larger refactor affecting all 6 agent nodes and the graph
construction. Should be done after SSE fixes are stable.

## Implementation Plan

### Sprint 1: P0 Core Fixes (Day 1)
- [ ] Phase 1: Backend heartbeat
- [ ] Phase 2: Frontend auto-reconnect with since_id replay
- [ ] Unit tests for heartbeat and reconnect

### Sprint 2: P1 Reliability (Day 2)
- [ ] Phase 3: Race condition fix
- [ ] Phase 4: Error logging
- [ ] Integration tests for race condition

### Sprint 3: P2 Polish & Architecture (Day 3-4)
- [ ] Phase 5: Blocked vs failed distinction
- [ ] Phase 6: Terminal state completeness
- [ ] Phase 7: Quality gate as independent node
- [ ] Frontend tests for blocked state handling

### Sprint 4: Validation (Day 4)
- [ ] Full test suite
- [ ] Manual validation with real project
- [ ] Docs: CHANGELOG, completion report

---

## Testing Strategy

### New Test Files
- `tests/test_v684_sse_heartbeat.py` — heartbeat emission timing
- `tests/test_v684_sse_race_condition.py` — run_id wait logic
- `tests/test_v684_sse_terminal_states.py` — all terminal states handled

### Critical Test Cases
1. Heartbeat comment emitted every ~15s during long poll
2. Frontend reconnects after simulated disconnect with correct since_id
3. SSE waits up to 5s when run_id not yet created
4. `blocked` status triggers `onComplete` not `onError` in frontend
5. All terminal states (completed/failed/blocked/cancelled) emit workflow_done

### Acceptance Criteria
- [ ] All existing tests pass
- [ ] New tests cover all 6 phases
- [ ] Manual: SSE survives a 90s LLM call through nginx proxy
- [ ] Manual: Browser tab switch + return shows correct progress
- [ ] Manual: blocked chapter shows "需要人工处理" not error

---

## Risks & Mitigations

**R1**: Heartbeat may increase bandwidth slightly
**Mitigation**: `:heartbeat\n\n` is 12 bytes per 15s, negligible.

**R2**: Auto-reconnect may cause event duplication
**Mitigation**: `since_id` ensures replay is idempotent; frontend deduplicates by event id.

**R3**: Race condition wait may delay legitimate "no run" responses
**Mitigation**: 5s max wait, only when no run_id is explicitly provided.

---

## Success Criteria
1. All 7 phases implemented and tested
2. Full test suite passes
3. SSE connection survives 90s+ LLM calls
4. Frontend auto-recovers from disconnects within 16s
5. `blocked` correctly distinguished from `failed` in UI

---

## References
- SSE endpoint: `novel_factory/api/routes/workflow_timeline.py:941`
- Frontend hooks: `frontend/src/hooks/useWorkflowStream.ts`, `useSSEStream.ts`
- Related: v6.8.2 revision reliability, v6.8.3 plot resolution, v6.8.4 LLM profile editing

---

**Spec Author**: Claude (Opus 4.8)
**Status**: Planning — awaiting implementation approval
