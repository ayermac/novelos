# v6.7.8 Revision Retry Accounting & Continuity Semantics — Spec

**Version**: 6.7.8
**Date**: 2026-05-29
**Branch**: `v6.7.8-revision-retry-accounting`
**Status**: Implemented

---

## Problem Statement

### 1. Revision Retry Accounting Error

Internal compression failures (Author/Polisher `_try_compress_overlong_output`/`_try_compress_overlong_polish`) were consuming chapter-level `retry_count`, causing:
- Premature retry exhaustion when compression fails multiple times
- Real revision retries skipped because budget was already spent on compression
- UI audit trail confusion (compression attempts and real revisions shared event type)

### 2. Timeline Facts Pollution

Old, completed timeline facts (e.g., "主角被围住" from chapter 3) were being treated as hard constraints in chapter 10, causing false positive story facts compliance violations when the character had long since escaped.

### 3. Author Revision Regression

Author revision drafts could regress to old chapter openings (e.g., reverting to chapter 1's opening when revising chapter 5), and the Editor had no mechanism to detect or block this regression.

### 4. Generic Ending Hook False Positives

Placeholder ending hooks (e.g., "待续") were triggering unnecessary retries when the actual chapter content was complete.

### 5. Proxy Pollution

`httpx` client was picking up system proxy settings (`HTTP_PROXY`/`HTTPS_PROXY`), causing LLM API calls to fail in environments with misconfigured proxies.

### 6. LLM Timeout Hanging

LLM calls without hard timeout could hang indefinitely, blocking the workflow.

---

## Solution

### A. Revision Retry Accounting Fix

**File**: `novel_factory/workflow/nodes.py`

1. Mark internal compression failures with `consume_revision_retry: false` in quality gate
2. `_handle_retryable_quality_gate` checks this field:
   - If `false`: uses `internal_repair` task type, preserves `retry_count`
   - If `true`: uses `revise` task type, increments `retry_count`
3. New `MAX_INTERNAL_REPAIR_ATTEMPTS = 2` constant
4. New `get_chapter_internal_repair_count(workflow_run_id)` repository method
5. After cap reached, escalate to chapter-level retries (consume `retry_count`)

### B. Distinct Event Types

**File**: `novel_factory/workflow/nodes.py`

- Internal repairs emit `internal_repair_attempt` event with `repair_scope` payload
- Chapter retries emit `quality_gate_retry` event (unchanged)
- Eliminates UI/audit confusion

### C. Status-Fact Filter with Hard-Contradiction Guard

**File**: `novel_factory/agents/editor.py`

1. Deterministic post-LLM filter in `_run_story_facts_compliance`
2. Downgrades `blocking` to `warning` when:
   - Fact is status-type (恐惧/被围住/瘫软/狼狈/被控制等)
   - Violation contains consistent-action keywords (强撑/虚张声势/挣扎/颤抖/嘴硬/色厉内荏等)
3. Hard-contradiction guard (`_HARD_CONTRADICTION_PHRASES`) prevents downgrade when text contains unambiguously incompatible behavior (从容指挥安保/大步离开/自由离开/调动安保等)

### D. Expanded Keyword Coverage

**File**: `novel_factory/agents/editor.py`

Added real-log trigger phrases:
- 强行维持/摇摇欲坠/声音粗重/声音干涩/声音发颤/强作镇定/咬牙撑住/强撑着/硬撑着/勉强维持

### E. Refined LLM Compliance Prompt

**File**: `novel_factory/agents/editor.py`

System prompt now explicitly instructs:
- Status-type facts + subsequent actions/dialogue = NOT contradictions
- Only explicit behavioral contradictions (freely commanding security, walking away unimpeded) should be flagged

### F. Generic Ending Hook Check

**File**: `novel_factory/agents/editor.py`

- Skip retry for generic ending hooks (待续/未完待续/下回分解/etc.)
- Only retry when ending_hook is specific and genuinely missing

### G. httpx trust_env=False

**File**: `novel_factory/llm/openai_compatible.py`

- Set `trust_env=False` on httpx client to prevent proxy pollution

### H. LLM Hard Timeout

**File**: `novel_factory/llm/openai_compatible.py`

- Wrap LLM calls with `asyncio.wait_for` hard timeout (default 120s)
- Prevents indefinite hanging

---

## Affected Files

| File | Change |
|------|--------|
| `novel_factory/workflow/nodes.py` | Internal repair cap, consume_revision_retry flag, event types |
| `novel_factory/db/repository.py` | `get_chapter_internal_repair_count(workflow_run_id)` method |
| `novel_factory/agents/editor.py` | Status-fact filter, expanded keywords, refined prompt, ending hook check |
| `novel_factory/llm/openai_compatible.py` | trust_env=False, hard timeout |
| `novel_factory/version.py` | Version bump to 6.7.8 |
| `frontend/package.json` | Version bump to 6.7.8 |
| `desktop/package.json` | Version bump to 6.7.8 |
| `tests/test_v678_revision_retry_accounting.py` | 16 dedicated tests |

---

## Acceptance Criteria

### Retry Accounting

1. ✅ Internal compression failure does NOT consume `retry_count`
2. ✅ Chapter revision failure DOES consume `retry_count`
3. ✅ `retry_count` correctly increments from 0 → 1 → 2 → max
4. ✅ `retry_count` is isolated per `workflow_run_id`
5. ✅ Internal repair cap (2) reached → escalate to chapter retry
6. ✅ Internal repairs emit `internal_repair_attempt` event
7. ✅ Chapter retries emit `quality_gate_retry` event
8. ✅ `retry_count` preserved after internal repair

### Status-Fact Filter

9. ✅ Status-type fact (恐惧) + consistent action (强撑) → downgrade to warning
10. ✅ Hard contradiction (从容指挥安保) prevents downgrade
11. ✅ Expanded keywords (强行维持/摇摇欲坠) recognized
12. ✅ Non-status fact stays blocking
13. ✅ No facts → no filter applied

### Version Alignment

14. ✅ Runtime version = 6.7.8
15. ✅ Frontend version = 6.7.8
16. ✅ Desktop version = 6.7.8

---

## Tests

**File**: `tests/test_v678_revision_retry_accounting.py`

16 tests in 3 test classes:

- **TestRevisionRetryAccounting** (8 tests)
- **TestStatusFactFilter** (5 tests)
- **TestVersionAlignment** (3 tests)

**Verification**: All 16 tests passing, full suite 2953/2953 passing

---

## Out of Scope

- Changing the Editor's LLM review logic (only deterministic filter added)
- Modifying the retry UI display (event types changed but UI adaptation is separate)
- Adding new Agent roles or skills
