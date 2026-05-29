# v6.7.8 Revision Retry Accounting & Continuity Semantics — Completion Report

## Summary

Fixed revision retry accounting so internal compression failures no longer consume chapter-level retries, added deterministic status-fact filter with hard-contradiction guard, and improved story facts compliance to reduce false positives.

## Changes Made

### Revision Retry Accounting (`novel_factory/workflow/nodes.py`)

1. **Internal compression no longer consumes chapter-level retries**: Author and Polisher internal word-count auto-compression failures (when `_try_compress_overlong_output`/`_try_compress_overlong_polish` fails) are now marked with `consume_revision_retry: false` in the quality gate. The `_handle_retryable_quality_gate` function checks this field and uses `internal_repair` task type instead of `revise`, preserving the chapter-level retry counter.

2. **Internal repair attempt cap with per-run isolation**: New `get_chapter_internal_repair_count(workflow_run_id)` repository method and `MAX_INTERNAL_REPAIR_ATTEMPTS = 2` constant. Count is scoped to `workflow_run_id` so old runs and cross-agent repairs don't pollute each other's budget. After the cap is reached within a run, internal repairs are escalated to chapter-level retries (consuming `retry_count`), preventing infinite agent loops.

3. **Distinct event types for internal repairs vs chapter retries**: Internal repairs emit `internal_repair_attempt` events (with `repair_scope` payload) instead of `quality_gate_retry`. This eliminates UI/audit confusion between agent-internal compression attempts and genuine chapter-level revision retries.

### Story Facts Compliance (`novel_factory/agents/editor.py`)

1. **Deterministic status-fact filter with hard-contradiction guard**: Editor's `_run_story_facts_compliance` includes a deterministic post-LLM filter that downgrades `blocking` violations to `warning` when the fact is a status-type description (恐惧/被围住/瘫软/狼狈/被控制等) and the violation text contains consistent-action keywords (强撑/虚张声势/挣扎/颤抖/嘴硬/色厉内荏等). A hard-contradiction guard (`_HARD_CONTRADICTION_PHRASES`) prevents downgrading when the text also contains unambiguously incompatible behavior (从容指挥安保/大步离开/自由离开/调动安保/etc.), fixing the false-negative risk.

2. **Expanded keyword coverage**: Added real-log trigger phrases (强行维持/摇摇欲坠/声音粗重/声音干涩/声音发颤/强作镇定/咬牙撑住/etc.) to the consistent-action keyword list.

3. **Refined LLM compliance prompt**: The editor's story facts compliance system prompt now explicitly instructs the LLM that status-type facts combined with subsequent actions/dialogue are not contradictions, and only explicit behavioral contradictions (freely commanding security, walking away unimpeded) should be flagged.

### Version (`novel_factory/version.py`)

- Updated from `6.7.7` to `6.7.8`

### Frontend Version (`frontend/package.json`)

- Updated from `6.7.7` to `6.7.8`

### Desktop Version (`desktop/package.json`)

- Updated from `6.7.7` to `6.7.8`

### Tests (`tests/test_v678_revision_retry_accounting.py`)

16 tests in 2 test classes:

- **TestRevisionRetryAccounting** (8 tests): internal compression does not consume retry, chapter retry increments on real revision, max retries boundary, retry count isolation per run, internal repair cap escalation, internal repair event type, chapter retry event type, retry count preserved after internal repair
- **TestStatusFactFilter** (5 tests): status-type fact downgrades blocking to warning, hard contradiction prevents downgrade, expanded keyword coverage, non-status fact stays blocking, no facts no filter
- **TestVersionAlignment** (3 tests): runtime version, frontend version, desktop version

## Verification

| Check | Result |
|-------|--------|
| v6.7.8 dedicated tests | 16/16 passing |
| Full test suite | 2953/2953 passing (1 skipped) |
| Version alignment tests | all passing |
| Linter | 0 errors |

## Key Fixes

1. **Revision retry leakage**: Internal compression failures were consuming chapter-level retries, causing premature retry exhaustion
2. **False positive story facts**: Status-type facts (恐惧/被围住) were incorrectly blocking when followed by consistent actions (强撑/挣扎)
3. **UI confusion**: Internal repairs and chapter retries shared the same event type, making audit trails unclear
4. **Cross-run pollution**: Internal repair counts were not scoped to workflow_run_id

## Known Limitations

1. **Status-fact filter heuristic**: The deterministic filter uses keyword matching and may miss edge cases. The hard-contradiction guard mitigates false negatives.
2. **Internal repair cap**: Fixed at 2 per run. May need tuning for complex chapters with multiple agents.
