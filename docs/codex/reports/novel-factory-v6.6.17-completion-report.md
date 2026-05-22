# v6.6.17 Runtime LLM Settings & Genesis Reliability Completion Report

## Status

Completed implementation baseline on branch `codex-v6.6.17-memory-curator-fallback`.

Runtime version source:

```text
novel_factory/version.py -> __version__ = "6.6.17"
```

## Delivered Changes

### LLM Settings

- Added `request_timeout_seconds` support to desktop/runtime LLM profile configuration.
- Removed user-facing template `max_tokens` editing from the LLM profile UI.
- Split API key value management from LLM profile templates.
- Let templates select an API key environment name instead of configuring key name/value per profile.
- Hid unused provider key presets from the Settings UI.
- Fixed template-name editing focus loss.
- Preserved secure-key guarantees: desktop config APIs do not return plaintext key values.

### Runtime And Workflow Recovery

- Guarded direct generation from blocked/revision states that require recovery.
- Reset recovery now clears active run/task records into an explicit recovery marker.
- Healthy running workflows are not misreported as stale.
- Pre-instructed chapters that skip Planner still receive `memory_context_audit`.
- Structural writing defects route back to Author when revision requires drafting repair.
- Revision feedback survives state hydration and Author to Polisher handoff.

### MemoryCurator

- Added fallback LLM routing for memory extraction.
- Preserved old behavior when `fallback_llm` is not configured.
- Propagated fallback timeout metadata.
- Kept degraded/no-op extraction distinct from trusted success.

### Genesis

- Stale running Genesis runs are marked failed so generation can retry.
- `production-next` recommends Genesis generation after stale recovery instead of waiting forever.
- The Genesis UI polls running jobs.
- Provider connection failures now return failure instead of local/template success.
- Invalid/incomplete JSON can still recover to reviewable local content when project context is sufficient.
- Real Genesis generation now uses bounded segments instead of one oversized all-sections request.

### Advisory Skill Manifests

- Added manifests for dialogue naturalness, scene texture, show-dont-tell, and info-dump advisory quality skills.

## Commits

- `f623467 Prepare v6.6.17 runtime and LLM settings updates`
- `784266a Hide unused API key presets`
- `0445f07 Add manifests for advisory quality skills`
- `f564b3c Recover stale genesis runs`
- `30e0142 Poll running genesis status`
- `f5b3ef8 Recover genesis from provider connection failures`
- `560e81b Segment genesis generation to reduce provider payloads`

## Verification

Targeted verification already run during implementation:

```text
python3 -m pytest tests/test_v532_project_genesis.py -q
22 passed
```

```text
python3 -m pytest tests/test_v532_project_genesis.py tests/test_v663_genesis_quality_gate.py tests/test_v65_desktop_runtime.py tests/test_v66_desktop_secure_keys.py -q
55 passed
```

Desktop sidecar live LLM smoke also succeeded against the configured OpenAI-compatible endpoint, proving base URL/key connectivity independent of the original long Genesis payload failure.

## Known Follow-Up

1. Genesis segmentation fixes only Genesis. Author, Polisher, and MemoryCurator still need broader segmented long-output/long-input migration.
2. Genesis quality gate still has heuristic false positives around natural-language character/faction detail and premise keyword extraction.
3. Full backend/frontend verification should be rerun before declaring v6.6.17 as a long-term stable baseline.

## Next Candidate

v6.6.18: segmented agent payloads across Author, Polisher, and MemoryCurator, using Genesis segmentation as the reference pattern.

