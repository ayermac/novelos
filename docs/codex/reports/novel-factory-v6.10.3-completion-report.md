# v6.10.3 Completion Report

## Summary

v6.10.3 implements workflow diagnostics and stability hardening. The release focuses on making failures explainable without increasing normal creative blocking: Run Doctor classifies run failures, QualityGate distinguishes mandatory checker health from advisory diagnostics, publish-time title validation catches malformed titles, and Memory Curator failures no longer trap already-reviewed content in human review.

## Delivered Changes

### Workflow Diagnostics

- Added `novel_factory/workflow/run_doctor.py`.
- Added `run_doctor` to `GET /api/runs/{run_id}`.
- Classifies: model output failure, deterministic quality failure, configuration failure, runtime timeout, memory failure, workflow failure.

### QualityGate Checker Health

- Mandatory checker failures now produce `[门禁降级]` blocking issues.
- Advisory checker failures remain diagnostic warnings.
- `checker_health` diagnostics record mandatory/advisory failures and policy.

### Publish Title Guard

- Added `novel_factory/quality/title_guard.py`.
- Blocks publication for missing, truncated, malformed, overlong, or body-detached titles.
- Integrated into both LangGraph `publisher_node` and manual publish API.

### Memory Curator Stability

- Real-mode Memory Curator degraded/fallback extraction routes to `awaiting_publish` instead of `human_review` when content is already ready for publication.
- Timeout recovery now releases same-run memory locks.
- Timeline and UI expose “补跑记忆提取” for terminal chapters with Memory Curator failure.

### Frontend Recovery UX

- Writing surface safe actions support `backfill_memory`.
- Run detail fallback area shows “补跑记忆提取”.
- Right Agent panel prioritizes memory backfill CTA when Memory Curator is the failing node.
- Run detail and chapter workflow fallback view show Run Doctor diagnosis category, summary, and recommended action.
- Fixed existing SSE hook lint dependency warnings using callback refs.

### Version Alignment

- Runtime version: `6.10.3`.
- Frontend package and lock: `6.10.3`.
- Desktop package and lock: `6.10.3`.

## Tests Added

- `tests/test_v6103_workflow_diagnostics.py`
  - title guard blocks malformed title before manual publish
  - mandatory checker error blocks QualityGate
  - Run Doctor classifies QualityGate failure
  - run detail includes Run Doctor
  - title guard accepts a good matching title
- Memory Curator timeout lock release regression in `tests/test_v6619_memory_curator_lock.py`.
- Timeline/backfill regressions in existing v5.3/v5.8 tests.

## Verification

Targeted verification run during implementation:

```bash
python3 -m pytest tests/test_v6103_workflow_diagnostics.py tests/test_workflow.py::TestRouteByReviewResult tests/test_workflow.py::TestRouteByQualityGate tests/test_workflow.py::TestRouteAfterMemoryCurator tests/test_v6101_workflow_stability.py tests/test_v685_quality_gate_node.py tests/test_v676_publish_guard.py tests/test_version_alignment.py tests/test_v53_project_modules.py::TestReviewModule::test_memory_backfill_releases_source_timeout_lock tests/test_v58_workflow_observability.py::TestWorkflowTimelineApi::test_memory_curator_blocked_terminal_run_recommends_backfill tests/test_v6619_memory_curator_lock.py::test_memory_curator_node_timeout_releases_source_lock -q
# 72 passed

npm run lint
# passed

npm run typecheck
# passed

npm run build
# passed
```

## Known Follow-up

- Run Doctor is visible in run detail and chapter workflow fallback view; a richer historical/trend dashboard remains a future improvement.
- Quality trend persistence (`chapter_quality_metrics`) is deferred to P1.
- Core sell-point cadence detection for sign-in/power fantasy is deferred to P1.
- Concept budget integration with fact ledger is deferred to P1.
- Skill policy matrix remains a governance follow-up.
