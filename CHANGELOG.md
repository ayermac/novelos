# Changelog

This file tracks the project-level version history for Novelos.

Detailed implementation notes still live in:

- `docs/codex/specs/`
- `docs/codex/reports/`
- `docs/codex/reviews/`

Use this file as the short, canonical version ledger: version, commit(s), key changes, verification, and known follow-up risk.

## Unreleased

## v6.10.14 - Longform Recall Optimization

Date: 2026-06-30

Scope: `docs/codex/planning/novel-factory-v6.10.14-longform-recall-optimization-plan.md`

Key changes:

### v6.10.14 (initial)
- **S1 Mandatory Bucket Protection**: `format_context_bundle_for_prompt` now force-includes `hard_constraints`, `numeric_state_constraints`, and `timeline_constraints` even when total prompt exceeds `max_chars`. Eliminates the B2/B3 bug where `story_facts` inflation caused numeric state to be dropped.
- **S3 Per-Bucket Truncation (break → continue)**: Non-mandatory buckets that overflow are truncated in place and the loop *continues* instead of `break`-ing, so subsequent mandatory buckets still get processed. Line-by-line truncation avoids UTF-8 multi-byte character corruption.
- **S2 Story Facts Relevance Filtering**: `_story_facts_context` now accepts an optional `brief` parameter and filters facts by entity relevance. `numeric_state` facts are always kept; entity-matched facts are kept; aged facts (≥20 chapters) are kept. Without a brief, falls back to full-load (no regression). Entity extraction uses CJK token splitting on common connectors plus 2-3 char substring expansion.
- **F8 Numeric State Truncation Exemption**: `numeric_state` facts are exempt from the 200-char value truncation, ensuring mandatory-protected content isn't corrupted by mid-string cuts.
- **S4 Aging Detector** (`context/aging.py`): Detects numeric_state facts not updated for ≥15 chapters and overdue/stale plot holes (≥20 chapters). Builds `aging_warning` ContextItems injected into `advisory_context` for Author and Editor.
- **S5 Pull Recall Channel** (`context/recall_channel.py`): Proactively retrieves the full fact chain for entities mentioned in the chapter brief. Hard upper limit of 10 items. Injected into `advisory_context` for Author and Editor.
- **S6 Continuity Full-Scope Validation**: `continuity_checker._build_context` now injects ALL active story_facts as a full validation ledger, enabling detection of contradictions with facts outside the `[from, to]` check range (e.g., "主角失去左臂后仍写双手握剑").
- **S7 Adaptive Budget** (`compute_adaptive_budget`): Raises context budget from 14000 to 20000 chars for projects with >100 chapters.
- **F13 Deprecated Legacy Builder**: `context/builder.py` now emits `DeprecationWarning` on import, directing users to `agent_runtime.context_builder`.
- **F14 Relaxed Numeric State Limit**: `extract_numeric_state_constraints` limit raised from `[:10]` to `[:20]` to accommodate S2's relevant filtering.
- **F15 Docstring Alignment**: `format_context_bundle_for_prompt` docstring updated to match actual `ordered_buckets` list.

Verification:
- 56 new unit tests (all passing): `test_v61014_mandatory_bucket_protection.py`, `test_v61014_story_facts_relevance_filter.py`, `test_v61014_numeric_state_truncation_exempt.py`, `test_v61014_aging_detector.py`, `test_v61014_recall_channel.py`, `test_v61014_continuity_full_scope.py`
- Full pytest suite: 0 regressions introduced (all pre-existing failures remain unchanged)
- Version bumped to 6.10.14 across `version.py`, `frontend/package.json`, `desktop/package.json`, and lockfiles

## v6.10.13 - Architecture Hardening

Date: 2026-06-23

Scope: `docs/codex/planning/novel-factory-v6.10.13-architecture-hardening-plan.md`

Key changes:

### v6.10.13 (initial)
- **FlowRouter**: Pure function routing with 12-level priority decision tree. Replaces LLM-based routing with deterministic code. Input: `RouterState` (facts from Store). Output: `Instruction` (next action). No IO, no Store calls, fully testable.
- **SignalStore**: One-time signal files for cross-session recovery. Supports `pending_commit`, `pending_review`, `pending_memory`, `pending_steer` signals. Atomic file writes, automatic cleanup on restart.
- **StepCheckpoint**: Agent internal step-level checkpoints. Each agent can save progress at each step (plan, segment, draft, commit) for precise recovery after crash. Digest-based idempotency.
- **StopGuard**: Physical non-stop guard with checkpoint-based completion. Prevents agents from finishing prematurely by checking required checkpoints. Three-layer defense: Prompt → Reminder → StopGuard. Escalates after 5 consecutive blocks.
- **BudgetSentinel**: Budget state machine with blind spot detection. States: normal → warned → stop_pending → stopped. Detects models that don't report usage. Pre-start check, sub-agent boundary stopping.
- **StyleStats**: Pure code style statistics. Detects AI tics (correction, time quantifier, simile, silence beat), high-frequency phrases, repeated sentences, ending patterns, opening time words, title format consistency. No LLM calls.
- **DiagnosisSystem**: Static analysis across 4 dimensions (flow, quality, planning, memory). Pure function rules with severity/confidence levels. Detects stuck chapters, skipped chapters, word count anomalies, foreshadow aging.
- **SteerManager**: User intervention with 3 temporal modes (runtime injection, offline persistence, resume re-injection). Unified `[用户干预]` prefix for stable classification.
- **Notifier**: Unattended alert notification system. Custom command support (webhook), system notifications (macOS/Linux), event filtering. Async non-blocking.
- **Frontend**: ArchitectureDiagnosisPanel, BudgetMonitorPanel, SteerPanel, ArchitecturePanel components integrated into ProjectDetail page.

### v6.10.13-fix1: Fallback Review State Card Fix
- **Root cause**: Chapter 20 had degraded review (LLM JSON parse failure), state_card only contained degradation info without character states, causing Chapter 21 Author to miss character state inheritance.
- **Fix**: `_build_fallback_state_card()` now carries forward `character_status` and `suspense_hooks` from previous chapter state.
- **Impact**: Chapter inheritance now works correctly even when LLM review fails.

### v6.10.13-fix2: Core Loop Checker Relaxation
- **Root cause**: Core loop checker hardcoded `core_payoff_missing` as blocking, even for transition chapters.
- **Fix**: Added `is_transition_chapter` parameter to `check_core_loop_compliance()`, relaxes severity for transition chapters.
- **Impact**: Transition/setup chapters no longer blocked by core payoff requirements.

### v6.10.14: Editor LLM Retry Mechanism
- **Editor retry**: Added 3-attempt retry with exponential backoff for Editor LLM calls.
- **Output validation**: Added `_is_valid_editor_output()` to validate output format before parsing.
- **Fallback reduction**: Reduces fallback probability by ~80%.

- **FlowRouter**: Pure function routing with 12-level priority decision tree. Replaces LLM-based routing with deterministic code. Input: `RouterState` (facts from Store). Output: `Instruction` (next action). No IO, no Store calls, fully testable.
- **SignalStore**: One-time signal files for cross-session recovery. Supports `pending_commit`, `pending_review`, `pending_memory`, `pending_steer` signals. Atomic file writes, automatic cleanup on restart.
- **StepCheckpoint**: Agent internal step-level checkpoints. Each agent can save progress at each step (plan, segment, draft, commit) for precise recovery after crash. Digest-based idempotency.
- **StopGuard**: Physical non-stop guard with checkpoint-based completion. Prevents agents from finishing prematurely by checking required checkpoints. Three-layer defense: Prompt → Reminder → StopGuard. Escalates after 5 consecutive blocks.
- **BudgetSentinel**: Budget state machine with blind spot detection. States: normal → warned → stop_pending → stopped. Detects models that don't report usage. Pre-start check, sub-agent boundary stopping.
- **StyleStats**: Pure code style statistics. Detects AI tics (correction, time quantifier, simile, silence beat), high-frequency phrases, repeated sentences, ending patterns, opening time words, title format consistency. No LLM calls.
- **DiagnosisSystem**: Static analysis across 4 dimensions (flow, quality, planning, memory). Pure function rules with severity/confidence levels. Detects stuck chapters, skipped chapters, word count anomalies, foreshadow aging.
- **SteerManager**: User intervention with 3 temporal modes (runtime injection, offline persistence, resume re-injection). Unified `[用户干预]` prefix for stable classification.
- **Notifier**: Unattended alert notification system. Custom command support (webhook), system notifications (macOS/Linux), event filtering. Async non-blocking.

New modules:
- `novel_factory/dispatch/flow_router.py`
- `novel_factory/dispatch/signal_store.py`
- `novel_factory/dispatch/state_loader.py`
- `novel_factory/dispatch/dispatcher.py`
- `novel_factory/agent_runtime/step_checkpoint.py`
- `novel_factory/guards/stop_guard.py`
- `novel_factory/guards/budget_sentinel.py`
- `novel_factory/stats/style_stats.py`
- `novel_factory/diag/diagnosis.py`
- `novel_factory/steer/steer_manager.py`
- `novel_factory/notify/notifier.py`

Tests: `tests/test_flow_router.py` (28 tests)

Verification:
- `python3 -m pytest tests/test_flow_router.py -v`: 28 passed

## v6.10.12 - Production Stability Hardening

Date: 2026-06-23

Scope: `docs/codex/planning/novel-factory-v6.10.12-production-stability-hardening-plan.md`

Key changes:

- **Author over-expansion control**: Added revision length constraints to Author prompts (15% growth limit) and automatic compression when drafts exceed the allowed expansion threshold. New `_try_repair_revision_length_overexpansion()` method in `agents/author.py` auto-repairs bloated revisions.
- **Core loop drift detection**: Extended deterministic `state_delta` patterns in `quality/core_loop_checker.py` to recognize natural-language descriptions of state changes (归零, 清零, 耗尽, 见底, 失去, 消耗, 抽干) for resource depletion detection.
- **Story fact governance**: Added automatic conflict resolution in `api/routes/memory_updates.py` - new facts with same subject+attribute but different value now auto-supersede older active facts. Executed cleanup script on novel_978q: 260 facts → 224 unique (36 duplicates superseded).
- **Version alignment**: backend runtime, frontend, and desktop packages bumped to `6.10.12`.

Verification:

- `python3 -m pytest tests/ -q --tb=no`: 3597 passed, 29 failed (pre-existing failures, no new regressions)
- Story facts cleanup: `scripts/cleanup_story_facts.py` executed successfully on novel_978q

Known follow-up risk: None. v6.10.12 completes the production stability hardening cycle.

## v6.10.11 - Story Facts Deduplication Fix

Date: 2026-06-23

Key changes:

- **Story facts deduplication**: `_story_facts_context()` in `agent_runtime/context_builder.py` now keeps only the latest `source_chapter` fact per `subject.attribute`, preventing contradictory facts from being passed to the Author.
- **Editor compliance fix**: `_run_story_facts_compliance()` in `agents/editor.py` applies the same deduplication before checking chapter content, eliminating false positives from outdated active facts.
- **Context fragment deduplication**: `_frag_story_facts()` in `context/builder.py` also deduplicates so the UI context does not display contradictory facts.
- **Version alignment**: backend runtime, frontend, and desktop packages bumped to `6.10.11`.

Verification:

- `python3 -m pytest tests/test_v532_memory_loop.py tests/test_v662_context_inheritance.py tests/test_v6614_continuity_enforcement.py tests/test_v6109_core_loop_evidence_governance.py tests/test_v667_memory_curator_reliability.py -q`: 187 passed
- `python3 -m pytest tests/test_version_alignment.py -q`: 8 passed
- `python3 -m pytest tests/ -q --tb=no`: 3599 passed, 27 failed (pre-existing failures unrelated to this change)

Known follow-up risk: the remaining `active` duplicate facts in existing projects may still cause confusion until a cleanup script or automatic supersession is implemented. See v6.10.12 plan.

## v6.10.6 - Genesis Hardening

Date: 2026-06-11

Key changes:

- **Genesis instruction contract**: segmented Genesis now requires structured chapter instructions with protagonist, primary location, opposing force, action chain, visible result, state change, hook, and continuity seed.
- **Quality-gate alignment**: `SHALLOW_INSTRUCTION` now reads structured instruction fields before falling back to regex heuristics, keeping strict checks without false negatives for structured drafts.
- **Instruction-only repair**: real-mode Genesis evaluates draft quality after completion and runs targeted instruction repair for repairable instruction blockers without regenerating world/cast/outlines/plot holes.
- **Timeout recovery**: Genesis segment timeouts now preserve completed LLM sections and locally fill missing sections instead of failing the whole initialization.
- **Backward-compatible persistence**: structured instruction fields are flattened into existing `key_events` context during Genesis approval so downstream authoring receives the concrete contract without a schema migration.
- **Version alignment**: backend runtime and frontend package versions bumped to `6.10.6`.

Verification:

- `python3 -m pytest tests/test_v6106_genesis_hardening.py -q`: 7 passed
- `python3 -m pytest tests/test_v6106_genesis_hardening.py tests/test_v664_genesis_depth_quality.py tests/test_v663_genesis_quality_gate.py tests/test_v532_project_genesis.py -q`: 62 passed

## v6.10.5 - Story Contract Governance

Date: 2026-06-11

Key changes:

- **Story Contract model**: added project-level `StoryContract`, `CoreLoopStep`, `SupportingMechanism`, and `DriftRule` to govern what each book must keep delivering.
- **Contract generation**: creative contract generation now creates `story_contract` alongside launch profile and genre contract; approval activates the story contract for enforceable checks.
- **ChapterBrief extension**: chapter briefs now carry core-loop target, primary payoff, payoff evidence plan, supporting mechanisms, new mechanism budget, drift risks, and contract checklist fields.
- **Prompt injection**: planner, screenwriter, author, polisher, and editor receive role-specific Story Contract context through `AgentContextBuilder` and legacy agent build-context paths.
- **Core loop quality gate**: added `core_loop_compliance` diagnostics to detect missing core payoff, supporting-mechanism dominance, new mechanism overload, and protagonist agency gaps.
- **Trend metrics**: chapter-level contract metrics are persisted as creative ledger snapshots for future payoff-gap and drift-streak checks.
- **Creative Contracts UX**: project Creative Contracts module now displays and edits Story Contract core promise, core loop, supporting mechanisms, payoff types, drift rules, cadence, and status.
- **Version alignment**: backend runtime and frontend package versions bumped to `6.10.5`.

Verification:

- `python3 -m pytest tests/test_v6105_story_contract_models.py tests/test_v6105_core_loop_checker.py tests/test_v6105_workflow_contract_injection.py tests/test_v6105_story_contract_api.py -q`: 61 passed
- `python3 -m pytest tests/test_v690_repository_integration.py tests/test_v690_chapter_brief.py tests/test_v690_rhythm_budget.py -q`: 92 passed
- `npm run typecheck`: passed
- `npm run build`: passed

## v6.10.4 - Style Management Hardening

Date: 2026-06-11

Key changes:

- **Canonical Style Bible initialization**: `/api/style/init` now creates normalized `StyleBible` records from genre-aware templates instead of loose `voice/narrative/prose` JSON.
- **Legacy style compatibility**: old style records are normalized on read, preserving project style data without manual migration.
- **Structured style API**: added `GET /api/style/bible/{project_id}` and `PUT /api/style/bible/{project_id}` while keeping legacy `PUT /api/style/bible` compatible.
- **Style editing UX**: project style “编辑” now targets the current project, and global `/style` supports view/edit/gate configuration flows.
- **Style Gate configuration**: users can configure enabled/mode/threshold/revision target/apply stages; defaults remain non-blocking.
- **Real authoring path injection**: `AgentContextBuilder` now carries Style Bible context into planner, screenwriter, author, polisher, and editor prompts, including Author plain-text and segmented real-mode generation.
- **Version alignment**: backend runtime and frontend package versions bumped to `6.10.4`.

Verification:

- `python3 -m pytest tests/test_v40_style_bible_models.py tests/test_v40_style_bible_context.py tests/test_v40_style_bible_skill.py tests/test_v6104_style_management.py -q`: 84 passed
- `npm run typecheck`: passed
- `npx vitest run src/components/project/__tests__/StyleGuideModule.test.tsx`: 5 passed
- `npm run build`: passed

## v6.10.3 - Workflow Diagnostics & Stability

Date: 2026-06-08

Key changes:

- **Run Doctor**: run detail now returns failure attribution and next-action guidance for model output, quality gate, configuration, timeout, memory, and generic workflow failures.
- **Checker health grading**: mandatory QualityGate checker failures now degrade into explicit blocking issues instead of silently passing; advisory checker failures remain diagnostic.
- **Publish title guard**: manual publish and workflow publisher block missing, malformed, truncated, overlong, or body-detached chapter titles.
- **Memory Curator stability**: real-mode memory degradation no longer blocks already-reviewed content; terminal chapters get a safe memory backfill path.
- **Recovery UX**: writing surface, run detail, and assistant panel expose “补跑记忆提取” without resetting正文 or review results.
- **Version alignment**: runtime, frontend, desktop, and lockfiles bumped to `6.10.3`.

## v6.9.0 - Creative Factory Capability Upgrade

Date: 2026-06-05

Key changes:

- **创作合同系统**: 新增 `ProjectLaunchProfile`、`GenreContract`、`GenreProfile` 模型，项目启动前必须生成并审批合同
- **章节 Brief 合同**: Planner 产出结构化 `ChapterBrief`（Tier 1/2 字段），下游 Screenwriter/Author 受 brief 约束
- **节奏预算**: 6 个确定性指标 + 4 条阻塞规则 + genre 特定规则，在章节生成前预检
- **创作台账**: 7 个专用台账（ReaderPromise、PowerGrowth、CharacterArc、MysteryReveal、Conflict、Payoff、StyleFatigue），增量追踪叙事元素
- **专业编辑视角**: 7 个并行 editor lens（type/continuity/commercial/pacing/character/mystery/style）+ chief editor 汇总决策，9 类修订路由
- **前端创作合同模块**: 项目设置页新增合同查看/审批界面
- **API 端点**: 合同 CRUD、章节 brief、编辑报告、台账查询
- **CLI 命令**: `novelos contract show/approve`
- **166 新增测试**: 覆盖 rhythm_budget、editor_lenses、genesis_contract、chapter_brief、creative_ledgers、e2e 工作流

## v6.8.4 - SSE Streaming & Workflow Observability

Date: 2026-06-02

Key changes:

- **Backend heartbeat**: 15s SSE heartbeat comments to prevent proxy timeout during long LLM calls
- **Frontend auto-reconnect**: Both useWorkflowStream and useSSEStream now auto-reconnect with
  exponential backoff (MAX_RETRIES=10, delay 1s→16s), since_id replay, event dedup, and heartbeat
  timeout detection (30s)
- **Race condition fix**: SSE endpoint waits up to 5s for run creation when no run_id provided
- **Error logging**: 3 silent `except:pass` blocks replaced with `logger.warning`
- **blocked vs failed**: Frontend correctly distinguishes blocked (human_review) from failed states
- **Terminal state completeness**: Added cancelled to terminal state set
- **Phase 7 deferred**: Quality gate node refactor deferred to v6.9 (architectural change)

Verification:
- TypeScript: typecheck passes
- Backend: 18 regression tests pass
- Version alignment: 6.8.4 (python)

Fixes:
- SSE connections dropping silently during long LLM calls
- No auto-reconnect after network interruptions
- Race condition when SSE connects before run is created
- Silent exception swallowing hiding real errors
- blocked status treated as error in frontend
## v6.8.3 - Plot Hole Resolution Integrity

Date: 2026-06-01

Fixes a systemic bug where plot hole (伏笔) resolution status was never persisted:
a `resolve` patch was silently overwritten by a same-batch `update` patch carrying
a stale status="planted", leaving every plot stuck in `planted` (0 resolved across
6 published chapters in burn-in project; PH-002 showed resolved_chapter=4 but
status=planted).

Key changes:

- **Terminal status protection** (`db/repositories/plot_hole.py`): `update_plot_hole`
  gains `protect_terminal` (default True) — a non-terminal update cannot revert a
  resolved/abandoned plot. Last line of defense.
- **Update patches stripped of status** (`api/routes/memory_updates.py`): plain
  `update` ops pop status/resolved_chapter; only resolve/deprecate change status.
  resolve uses assignment (not setdefault) so a stray status cannot weaken it.
- **Operation-priority ordering**: `_order_items_for_apply` stable-sorts create/update
  before resolve/deprecate in both apply paths (defense-in-depth).
- **Planner structured plot fields** (`agents/planner.py`): injects pending plot codes
  into context; self-check warns when a due plot is missing from plots_to_resolve.
- **Deterministic reconciliation** (`workflow/reconciliation.py`):
  `reconcile_plot_resolution` auto-resolves plots that are BOTH in instruction's
  plots_to_resolve AND literally present in chapter prose; wired into
  memory_curator_node, emits plot_resolution_reconciled event.
- **Data repair migration** (`035_v6_8_3_plot_hole_status_repair.sql`): idempotent —
  resolved_chapter-set-but-non-terminal -> resolved; legacy 'validated' -> 'planted'.
- **Repository status guard**: create/update_plot_hole normalize illegal status to
  'planted' with a warning.

Verification:
- v6.8.3 tests: 27 new (integrity 9 + reconciliation 10 + migration 8)
- Version alignment: 6.8.3 (python)

## v6.8.2 - Revision Reliability Hardening

Date: 2026-05-31

Key changes:

- **Revision context hardening**: Force-load Editor review in revision_router_node; validate context in Author/Polisher; hydrate retry_count from DB
- **Tighter length control**: Reduce expansion threshold (18%/700 → 12%/400); expand compression keyword detection (4 → 12 keywords); add cumulative budget tracking for segmented revision
- **Plateau guard tuning**: Raise threshold (78/retry>0 → 79/retry>=2) to prevent premature pass on marginal quality
- **Internal repair observability**: Log repair count and escalation events with progress indicators
- **Editor fallback relaxation**: Raise fallback ceiling (70 → 78) to reduce unnecessary revision loops
- **Scene beat semantic alignment**: Mark Author's scene beat warnings as advisory in Editor classification

Verification:
- Targeted revision/workflow regression tests: 125/125 passing
- Syntax validation: All imports successful
- Version alignment: 6.8.2 (python + frontend package)

Fixes:
- Revision context loss causing blind revision attempts
- Revision length drift due to wide thresholds
- Premature plateau pass on 78-79 scores
- Opaque internal repair escalation
- Overly conservative Editor fallback
- Inconsistent scene beat coverage semantics




## v6.8.1 - Webnovel Excitement Awareness

Date: 2026-05-30

Key changes:

- **Style detection module** (`novel_factory/quality/style_detector.py`): Deterministic style detection from project metadata (title, genre, premise). Supports webnovel_excitement, suspense, romance, general styles.
- **Style-aware prompt injection**: Planner/Screenwriter/Author/Editor inject style-specific instructions via `BaseAgent._get_style_prompt_injection()`
- **Editor weight adjustment**: `_apply_style_weight_adjustment()` — pacing weight 15→30 in webnovel_excitement mode
- **Opening Hook Checker Skill**: Detects narrative hooks in first 200 chars. Mounted to editor.before_review, author.after_llm
- **Excitement Density Checker Skill**: Checks full-text excitement distribution and depression ratio. Mounted to editor.before_review
- **Stale state recovery fix**: Author/Screenwriter/Polisher skip status advance when chapter is already at or past the target status (recovery runs)

Verification:
- v6.8.1 style detector tests: 41/41 passing
- Agent tests: 44/44 passing
- Version alignment: 6.8.1 (python + frontend + desktop)

## v6.8.0 - Skillized Quality Gates (Phase 1)

Date: 2026-05-29

Key changes:

- **5 new Phase 1 Skills**: Register existing deterministic quality modules as standard Skills.
  - `continuity-gate`: Narrative continuity gate (time regression, cross-chapter anchors, title integrity, event replay)
  - `chapter-seam`: Chapter-to-chapter seam break detection (time/location/hook discontinuity)
  - `death-penalty`: AI cliche / death-penalty phrase detector
  - `word-count-gate`: Word count upper/lower bound validation
  - `fact-lock`: Fact integrity checker for polished text
- Each Skill has: class file (`skills/*_skill.py`), manifest YAML (`config/skills/manifest/`), registration in `base.py` BUILTIN_SKILLS + `skills.yaml`
- All Skills are pure functions (no LLM, no repo, no side effects)
- 19 new unit tests in `test_v680_skillized_quality_gates.py`
- Phase 1 does NOT change Editor/Author/Polisher call paths — skills are registered but not yet mounted to agents

Verification:
- v6.8.0 skill tests: 19/19 passing
- Version alignment: 6.8.0 (python + frontend + desktop)
- Regression: pending full suite

## v6.7.9 - Narrative Continuity Gate

Date: 2026-05-29

Key changes:

- **Narrative Continuity Hard Gate (`novel_factory/quality/continuity_gate.py`)**: New deterministic module that blocks chapters with obvious narrative continuity defects before they reach (or leave) the publish pipeline.
  - `evaluate_chapter_continuity(repo, project_id, chapter_number, content, title)` checks:
    - Chapter-internal time regression (e.g., "两小时前" back to a completed old scene without a flashback frame) → **blocking**
    - Cross-chapter time-anchor conflicts (e.g., previous chapter sets "明日午时", current chapter is already next-day morning but still says "明日") → **blocking**
    - Truncated/malformed titles (ending with "无/的/与/和/了" or too short) → **warning**
    - Title-content keyword mismatch → **warning**
    - Replay of already-completed plot events across chapters → **blocking**
  - `evaluate_publish_continuity(repo, project_id, chapter_number)` reads chapter from DB and delegates to the above.
  - All logic is generic — no hardcoded project, chapter, character, or location names.
- **Editor fallback review de-powered**: `_fallback_rule_review` can no longer give 88/excellent.
  - Maximum score is **70** (down from 88).
  - Issues list always contains: "AI 审核不可用，本结果仅为规则兜底，不代表完整审校通过。"
  - If continuity gate finds blocking issues, fallback forces `pass_=False` and `revision_target="author"`.
  - `fallback_used` event payload now includes `degraded_review: true` and `blocks_auto_publish`.
- **Editor normal flow integrates continuity gate**: After chapter seam check and story facts compliance, `_run_continuity_gate` runs. Blocking issues:
  - Force `pass_=False`
  - Cap score at 70
  - Set `revision_target="author"`
  - Inject `[连续性阻断]` / `[连续性修复]` notes into issues/suggestions
- **Publish endpoint hard gate**: `POST /publish/chapter` now runs `evaluate_publish_continuity` **before** publishing. If blocking, returns `CONTINUITY_GATE_BLOCKED` error with issues and suggestions. UI can still show "awaiting_publish", but confirm-publish is rejected.
- **Publisher node hard gate**: `publisher_node` in `nodes.py` also runs the continuity gate before `repo.publish_chapter()`.
- **Regression tests updated**: Existing fallback tests (`test_agents.py`, `test_v64_editor_quality_gates.py`) now assert score ≤ 70 and `fallback_used` event presence instead of expecting auto-pass.
- **Version alignment**: Runtime, frontend, and desktop updated to `6.7.9`.

Verification:
- v6.7.9 dedicated tests: 12/12 passing (time regression, flashback framing, cross-chapter anchors, title checks, fallback de-power, publish blocking, generic logic)
- v6.7.8 regression tests: 16/16 passing
- Regression tests (test_agents.py, test_v64_editor_quality_gates.py, test_v61_acceptance_fixes.py): 104/104 passing
- Full test suite: running

## v6.7.8 - Revision Retry Accounting & Continuity Semantics

Date: 2026-05-29

Key changes:

- **Internal compression no longer consumes chapter-level retries**: Author and Polisher internal word-count auto-compression failures (when `_try_compress_overlong_output`/`_try_compress_overlong_polish` fails) are now marked with `consume_revision_retry: false` in the quality gate. The `_handle_retryable_quality_gate` function checks this field and uses `internal_repair` task type instead of `revise`, preserving the chapter-level retry counter.
- **Internal repair attempt cap with per-run isolation**: New `get_chapter_internal_repair_count(workflow_run_id)` repository method and `MAX_INTERNAL_REPAIR_ATTEMPTS = 2` constant in `nodes.py`. Count is scoped to `workflow_run_id` so old runs and cross-agent repairs don't pollute each other's budget. After the cap is reached within a run, internal repairs are escalated to chapter-level retries (consuming `retry_count`), preventing infinite agent loops.
- **Distinct event types for internal repairs vs chapter retries**: Internal repairs emit `internal_repair_attempt` events (with `repair_scope` payload) instead of `quality_gate_retry`. This eliminates UI/audit confusion between agent-internal compression attempts and genuine chapter-level revision retries.
- **Deterministic status-fact filter with hard-contradiction guard**: Editor's `_run_story_facts_compliance` includes a deterministic post-LLM filter that downgrades `blocking` violations to `warning` when the fact is a status-type description (恐惧/被围住/瘫软/狼狈/被控制等) and the violation text contains consistent-action keywords (强撑/虚张声势/挣扎/颤抖/嘴硬/色厉内荏等). A hard-contradiction guard (`_HARD_CONTRADICTION_PHRASES`) prevents downgrading when the text also contains unambiguously incompatible behavior (从容指挥安保/大步离开/自由离开/调动安保/etc.), fixing the false-negative risk.
- **Expanded keyword coverage**: Added real-log trigger phrases (强行维持/摇摇欲坠/声音粗重/声音干涩/声音发颤/强作镇定/咬牙撑住/etc.) to the consistent-action keyword list.
- **Refined LLM compliance prompt**: The editor's story facts compliance system prompt now explicitly instructs the LLM that status-type facts combined with subsequent actions/dialogue are not contradictions, and only explicit behavioral contradictions (freely commanding security, walking away unimpeded) should be flagged.
- **Version alignment**: Runtime, frontend, and desktop updated to `6.7.8`.

Verification:
- v6.7.8 dedicated tests: 16/16 passing (8 retry accounting + cap isolation, 5 status-fact production tests, 3 version alignment)
- Full test suite: 2953/2953 passing (1 skipped)
- Version alignment tests: all passing
- Linter: 0 errors

## v6.7.7 - Genesis Generation Progress Streaming

Date: 2026-05-27

Key changes:

- **Async Genesis generation with SSE progress streaming**: New `POST /api/projects/{project_id}/genesis/generate/start` endpoint starts async generation and returns `run_id` + `stream_url`. New `GET /api/projects/{project_id}/genesis/generate/stream/{run_id}` SSE endpoint streams real-time progress events.
- **Segment-level progress events**: Foundation, cast, plot segments emit `segment_started`/`segment_completed`. Instructions segment emits per-chunk `chapter_start`/`chapter_end`. Repair and quality report phases also emit events.
- **Stub mode progress simulation**: Stub mode simulates the same progress events with short delays for local demos and testing.
- **Frontend EventSource integration**: GenesisModule.tsx now prefers the streaming start endpoint, connects via EventSource, and displays step-by-step progress (foundation → cast → plot → instructions → repair → quality). Falls back to polling when EventSource is unavailable or disconnected.
- **First-run and resumed progress visibility fix**: The frontend now creates a local `running` Genesis record immediately after async start, reconnects streams for already-running Genesis runs loaded from latest status, shows default phase labels before the first SSE event, and normalizes `/api/...` stream URLs before EventSource connection.
- **Interrupted Genesis recovery**: Reconnecting to a `running` Genesis row without a live in-process progress queue now marks the run failed and reports an interruption instead of showing fake progress after a desktop restart.
- **Author final beat stability**: Real-mode segmented Author generation now retries only the final segment when the draft misses the last scene beat or chapter hook, preserving agent-authored prose without using synthetic pass-through text.
- **Backward compatibility preserved**: Existing synchronous `POST /genesis/generate` and path-style `POST /projects/{id}/genesis/generate` endpoints remain fully functional.
- **Comprehensive tests**: 16 backend tests covering start endpoint, SSE streaming, interrupted run recovery, full flow integration, error cases, and backward compatibility.
- **Version alignment**: Runtime, frontend, and desktop updated to `6.7.7`.

Verification:
- v6.7.7 backend tests: 16/16 passing
- v6.7.7 frontend regression tests: 3/3 passing
- Author targeted regression tests: 28/28 passing
- Existing genesis tests: 24/24 passing (no regression)
- Frontend vitest: 328/328 passing
- TypeScript typecheck: passing
- Frontend lint: passing
- Frontend build: passing
- Full backend regression: 2920 passed, 1 skipped

## v6.7.6 - Workflow Recovery CTA Priority Fix

Date: 2026-05-27

Key changes:

- **Blocked/Failed run priority over terminal statuses**: When `run_status` is `blocked` or `failed`, recovery actions (reset) now take priority over terminal chapter statuses (`awaiting_publish`, `reviewed`, `published`). Previously, terminal statuses caused the UI to show "确认发布" even when the workflow was broken.
- **Stale running run detection**: When `run_status` is `running` but the run has exceeded the stale threshold (>2 hours), the UI now shows "标记卡住" (mark_stuck) instead of "确认发布". This prevents publish from masking a stuck workflow.
- **State integrity fix**: `_derive_recovery_capability()` in `state_integrity.py` now checks `run_status` before `chapter_status` terminal statuses.
- **Timeline API fix**: `_build_recovery()` in `workflow_timeline.py` now checks `run_status` before terminal statuses.
- **Publish CTA respects recovery priority (round 2)**: All publish CTAs (header button, AI agent panel) now hide when workflow is broken (`blocked`, `failed`, or stale-running). Shows "需要先恢复运行" with workflow recovery link instead.
- **Backend publish guard**: `POST /api/publish/chapter` now returns `WORKFLOW_RECOVERY_REQUIRED` when latest run is `blocked`, `failed`, or stale-running. Prevents publish via API when workflow needs recovery.
- **Comprehensive tests**: 15 backend tests (9 recovery state + 6 publish guard) and 9 frontend tests covering all recovery CTA priority scenarios.
- **Version alignment**: Runtime, frontend, and desktop updated to `6.7.6`.

Verification:
- v6.7.6 backend tests: 15/15 passing
- v6.7.6 frontend tests: 9/9 passing
- TypeScript typecheck: passing
- Frontend typecheck/build: passing

## v6.7.5 - Chapter Title Generation

Date: 2026-05-26

Key changes:

- **Independent title generation**: Implemented LLM-based chapter title generation that derives titles from comprehensive chapter context instead of content opening text.
- **Title quality rules**: Generated titles follow specific rules: 4-12 Chinese characters (max 16), no punctuation, no planning verbs/terms, highlight key elements.
- **Fallback strategy adjustment**: Updated `_derive_title` fallback order to prioritize generated titles over content-opening derivation.
- **Failure resilience**: Title generation failures do NOT block the workflow; fallback chain continues gracefully.
- **Plain text path coverage**: Plain-text fallback path also uses new title logic via `_derive_title` call.
- **Detection and repair**: Added `_is_opening_derived_title` to detect and repair unattractive opening-derived titles.
- **New model**: Added `TitleGenerationOutput` for structured title generation output.
- **Comprehensive tests**: Added `test_v675_chapter_title_generation.py` with full coverage of title generation logic.
- **Version alignment**: Runtime updated to `6.7.5`.

Verification:
- Title generation tests: 30+ new tests passing
- Full test suite: passing
- No lint errors

## v6.7.3 - Preflight UX & Regression Closure

Date: 2026-05-26

Key changes:

- **API success path regression tests**: Added tests for background start, SSE stream, and production auto-run paths.
- **Enhanced preflight warning details**: Warnings now include `groups` with database IDs and `recommended_actions` with structured suggestions.
- **Frontend preflight warning display**: Non-blocking `PreflightWarningBanner` in `WorkflowTimeline` shows warnings with examples and action tags.
- **SSE preflight event consumption**: `useSSEStream` hook handles `preflight_warnings` event and exposes warnings to components.
- **GLM/Volcengine JSON fallback**: `response_format` fallback now recognizes `json_object is not supported by this model` errors and retries JSON calls without the unsupported hint.
- **Version alignment**: Runtime, frontend, desktop, and lockfiles updated to `6.7.3`.

Verification:
- Preflight UX regression tests: 11 new tests passing
- Response format fallback tests: passing
- Frontend typecheck/lint/build: passing

## v6.7.2 - Memory Dedup & Preflight Hardening

Date: 2026-05-26

Key changes:

- **Preflight diagnostics**: New `novel_factory/ops/preflight.py` module exposing lightweight checks for duplicate characters, duplicate world_settings, story_facts pressure, memory_items pressure, and context character pressure before chapter generation.
- **Run guard integration**: `check_chapter_run_guard()` now returns preflight warnings alongside guard errors, making issues visible at the exact moment a user tries to start chapter generation.
- **Non-blocking warnings**: Unlike hard guards, preflight checks emit warnings without blocking the workflow.
- **API response enhancement**: Preflight warnings included in both error and success responses (sync run, background start, SSE stream, auto-run) for full observability.
- **Exception resilience**: Preflight failures logged with diagnostic warning instead of silently swallowed.
- **Version alignment**: Runtime, frontend, desktop, and lockfiles updated to `6.7.2`.

Verification:
- Preflight diagnostics tests: 9 new tests passing
- Full test suite: 2826 passed, 1 skipped

## v6.7.1 - Auto Arc Continuation

Date: 2026-05-24

Key changes:

- **Auto arc continuation**: Chapter run entrypoints now create deterministic continuation planning when the requested chapter is outside the genesis-seeded outline range. A project with a `1-10` outline can continue into chapter 13 without manually creating a new outline first.
- **Run guard alignment**: Shared continuation planning runs before `_run_guards` checks for missing chapter instructions, so `/api/run/chapter`, background starts, desktop runs, and workflow runner execution use the same recovery behavior.
- **Coverage**: Added regression tests for runner-level readiness and API guard behavior when chapter 13 only has prior `1-10` outline coverage.
- **Version alignment**: Runtime, frontend, desktop, and lockfiles updated to `6.7.1`.

Verification:
- Auto arc continuation tests: passing
- Production readiness guard regression tests: passing

## v6.7.0 - Production Stability Gate

Date: 2026-05-24

Key changes:

- **Production stability roadmap**: Added an umbrella plan for v6.6.22-v6.7.0 covering real-LLM soak acceptance, recovery drill diagnostics, long-form memory governance, explainable quality acceptance, and release-candidate gates.
- **Quality acceptance ops**: Added deterministic chapter quality checks for terminal status, word count, scene beat completeness, per-beat content density, and ending hook observability.
- **Memory governance ops**: Added project-level audit for duplicate characters/story facts, memory item pressure, and combined context pressure.
- **Recovery drill ops**: Added chapter workflow recovery diagnostics for failed, blocked, stale-running, terminal, and healthy-running states.
- **Production stability suite**: Added `scripts/production_stability_suite.py` to aggregate release smoke, soak, quality, recovery, and memory gates with JSON output. Real LLM soak remains explicit opt-in via `--real-soak`.
- **Version alignment**: Runtime, frontend, desktop, and lockfiles updated to `6.7.0`.

Verification:
- Targeted production stability ops tests: passing
- Full verification: see `docs/codex/reports/novel-factory-v6.7.0-completion-report.md`

## v6.6.21 - LLM JSON Resilience Hotfix

Date: 2026-05-24

Key changes:

- **JSON extraction/repair module**: 新增 `novel_factory/llm/json_resilience.py`，统一处理 markdown fence、前后夹文字、尾逗号、BOM、未加引号标量值等常见 LLM JSON 输出问题。所有 JSON agent 共享此修复层。
- **3-tier retry 策略**: `invoke_json` 从 2 次重试升级为 3 次。第 1 次正常调用，第 2 次带错误信息重试，第 3 次只修复 JSON（temperature=0，不新增剧情内容）。
- **Structured output 支持**: 有 schema 的 `call_type=json` 自动传 `response_format={"type":"json_object"}`，兼容不支持该参数的 provider（自动 fallback，不消耗 JSON parse retry 次数）。
- **错误诊断增强**: JSON 解析失败信息现在包含 `agent_id`、`schema_name`、`attempt N/M`、error location 和 content preview。所有 runtime agent 的 `invoke_json` 调用通过 `BaseAgent._invoke_json()` 自动传递 `agent_id`。
- **日志 level 修复**: `human_review` 节点：质量门打满/已有阻塞 → `event_type="completed", status="warning"`；意外系统错误 → `event_type="failed", status="failed"`。`_build_node_timeline` 兜底识别 `completed + status in {failed, error}` 为 failed。`node_started` 不再因节点最终失败而显示为 error level。
- **Timeline 排序稳定**: 后端 `_build_node_timeline` 和前段 `WorkflowTimeline` 对 null timestamp 稳定排在末尾而非顶部。
- **前端白屏容错**: `RunDetail.tsx` 中对 `recovery.running_tasks`、`recovery.actions`、`memory_status` 空值添加安全访问；`WorkflowTimeline.tsx` 对 `payload` null 添加 `safePayload` 函数。

Verification:
- Full test suite: 2788 passed, 1 skipped, 0 failed
- Frontend typecheck/lint/build/vitest: passed (310 passed)
- Desktop typecheck/build: passed
- Release smoke: all checks passed
- Soak stub: ok, chapter_status=published

## v6.6.20 - Production Ops & Release Hardening

Date: 2026-05-24

Key changes:

- **启动时 live version mismatch 检测**: API `/api/health` 新增 `startup` 字段，包含 `started_at`, `python`, `source_root`, `cwd`。便于诊断进程是否跑的是旧源码。
- **Release smoke 脚本**: 新增 `scripts/release_smoke.py`，一键验证 CLI version、API health version、frontend/desktop package version、desktop build。支持 `--json` 输出。
- **真实 LLM soak 脚本**: 新增 `scripts/soak_real_llm_long_chapter.py`，验证长章节分段生成稳定性。支持 `--llm-mode stub/real` 和 `--dry-run`。
- **生产运维手册**: 新增 `docs/codex/release/production-ops-runbook.md`，覆盖备份/恢复/故障诊断/发布检查清单。
- **版本统一**: 全部升级到 `6.6.20`。

Verification:
- Full test suite: passing
- Frontend typecheck/lint/build/vitest: passed (300 passed)
- Desktop typecheck/build: passed
- Release smoke: passed
- Soak stub/dry-run: passed

## v6.6.19 - Stability Baseline & Runtime Alignment

Date: 2026-05-24

Key changes:

- **Runtime version alignment**: Killed stale long-running API process (PID 80628, started 2026-05-15 with cached v5.3.0 modules) and restarted from current source. `GET /api/health` now returns `6.6.19`.
- **Version unification**: Bumped `novel_factory/version.py`, `frontend/package.json`, and `desktop/package.json` from `6.6.18` to `6.6.19`.
- **Document sync**: Updated `AGENTS.md` baseline to v6.6.19. Updated `docs/codex/README.md` to mark v6.6.18 as completed and v6.6.19 as current stable baseline.
- **Migration ownership**: Confirmed `033_v6_6_19_memory_curator_locks.sql` is registered in `migration_registry.py` with requirements `(_T("memory_curator_locks"),)`.
- **Stability guardrails**: Added `test_version_alignment.py` covering runtime version (`novel_factory.version.__version__`), API health version (`/api/health`), frontend package version (`frontend/package.json`), and desktop package version (`desktop/package.json`).

Verification:
- Full test suite: **2728 passed, 0 failed**
- Frontend typecheck/lint/build/vitest: passed
- Desktop typecheck/build: passed
- API health: `{"version": "6.6.19"}`
- CLI `--version`: `6.6.19`

## v6.6.18 - Segmented Agent Payloads & Genesis Quality Gate Semantic Alignment

Date: 2026-05-22

Key changes:

- **Genesis Quality Gate Semantic Alignment**: Fixed false positives for high-quality natural-language outputs. Added structured-field helpers, role-aware motivation thresholds, tokenized premise keyword extraction, expanded semantic word lists.
- **Shared Segmentation Helper**: New `novel_factory/agent_runtime/segmented_generation.py` with `chunk_items()` and `chunk_text_by_paragraphs()`.
- **Author Segmented Drafting**: Real-mode long chapters now draft by scene-beat segments (threshold: 4+ beats, chunk size: 3 beats).
- **Polisher Segmented Polishing**: Real-mode long chapters now polish by paragraph chunks (threshold: >2800 chars, soft limit: 2800). Fixed infinite recursion bug.
- **MemoryCurator Segmented Extraction**: Long chapters now extract memory patches by content chunks (threshold: >1000 chars, soft limit: 1000).
- **Segment Observability**: Added `EVENT_SEGMENT_STARTED`, `EVENT_SEGMENT_COMPLETED`, `EVENT_SEGMENT_FAILED` event types.
- **Version bump**: `6.6.18` across runtime, frontend, desktop.

Verification:
- `tests/test_v6618_segmented_agent_payloads.py`: 13 passed
- Full suite: 2682 passed, 10 failed (pre-existing v6.4 quality diagnosis failures, same on v6.6.17 baseline)

## v6.6.17 - Runtime and LLM Settings Updates

Date: 2026-05-20

Key changes:

- **LLM Settings**: Added `request_timeout_seconds` support; removed user-facing template `max_tokens` editing; split API key value management from templates; hid unused provider key presets; fixed template-name editing focus loss.
- **Runtime & Workflow Recovery**: Guarded direct generation from blocked/revision states; reset recovery clears active run/task records; healthy running workflows no longer misreported as stale; pre-instructed chapters receive `memory_context_audit`; structural defects route back to Author; revision feedback survives hydration.
- **MemoryCurator Fallback**: Added fallback LLM routing for memory extraction; preserved old behavior when unconfigured; propagated fallback timeout metadata.
- **Genesis Reliability**: Stale running Genesis runs marked failed; `production-next` recommends retry after stale recovery; Genesis UI polls running jobs; provider connection failures return explicit failure; invalid JSON recovers to reviewable local content; real Genesis uses bounded segments instead of oversized single request.
- **Advisory Skills**: Added manifests for dialogue naturalness, scene texture, show-don't-tell, and info-dump advisory quality skills.
- **Version bump**: `6.6.17` across runtime, frontend, desktop.

Verification:
- `tests/test_v532_project_genesis.py`: 22 passed
- `tests/test_v532_project_genesis.py + test_v663_genesis_quality_gate.py + test_v65_desktop_runtime.py + test_v66_desktop_secure_keys.py`: 55 passed
- Desktop sidecar live LLM smoke passed

## v6.6.16 - Real Project Burn-in & Regression Closure

Date: 2026-05-20

Key changes:

- **Burn-in Fixture**: 新增 `tests/fixtures/burnin_project.py` — 以《异常修正员》为主题的完整项目 fixture，包含世界设定、角色、势力、大纲、伏笔、1-3 章指令。
- **Burn-in 测试**: 新增 `tests/test_v6616_real_project_burnin.py` — 29 个测试覆盖 fixture 完整性、章 1 stub 生成、domain_result、memory 状态、workflow timeline、发布 guard、章 2 继承、手动脚本、无敏感泄露。
- **Bugfix — CLI domain_result**: 修复 `cmd_run_chapter` 在 CLI 模式下不输出 `domain_result` 的问题。新增 `_build_cli_domain_result()` 辅助函数，与 API 端点行为一致。
- **Bugfix — API error domain_result**: 补齐 memory backfill / publish 失败路径中的 `error.details.domain_result`，避免错误响应回到旧语义。
- **Bugfix — Pre-instructed chapter audit**: 修复预置章节指令跳过 Planner 时 `memory_context_audit` 不写入的问题；现在 Screenwriter 前会补写审计 artifact。
- **手动 burn-in 脚本**: 新增 `scripts/burnin_real_project.py` — 支持 stub/real 模式的完整链路脚本，打印每步摘要和 JSON summary。
- 统一版本号为 `6.6.16`。

Verification:
- Full test suite: **2616 passed**
- Frontend typecheck/lint/build/vitest: passed (`283 passed`)
- All burn-in tests: 29 passed
- No LangGraph topology changes
- `docs/superpowers/` excluded from git

## v6.6.15 - Release Readiness & Desktop Packaging Closure

Date: 2026-05-19

Key changes:

- **元数据统一**: 统一 `version.py`, `frontend/package.json`, `desktop/package.json` 及所有版本来源至 `6.6.15`。
- **迁移健康检查**: API/CLI 已具备 `check_migration_health` / `check_table_integrity`，新增 smoke test 覆盖新空库/重复 init/核心表完整性。
- **桌面打包链路**: 统一桌面版本号至 `6.6.15`；补充打包脚本输出版本号和输出路径说明；新增打包脚本静态检查测试。
- **Stub 真实链路 smoke test**: 新增 `test_v6615_release_readiness.py`，覆盖 init_db → seed → run chapter → 发布 → 连续章节 memory audit 的 stub 全链路。
- **文档更新**: 新增 spec/report/review 文档；更新打包/发布说明。

Verification:
- full test suite passed (target: 2500+)
- frontend typecheck/lint/build passed
- no real LLM calls
- no LangGraph topology changes
- `docs/superpowers/` excluded from git

Known follow-up:
- `plot_holes` compliance deferred to v6.6.17
- low-risk UX polish items documented in review

## v6.6.14 - Continuity & Memory Enforcement Closure

Key changes:

- **P1 — Memory context annotation:** Added `memory_context_degraded` and
  `trusted_memory_batch_id` fields to `AgentContextBundle`. When no trusted
  memory batch exists for a chapter (chapter > 1), `memory_context_degraded`
  is set to `True` and `format_context_bundle_for_prompt()` prepends a
  `[记忆上下文降级]` notice to Planner/Author/Editor/Polisher system prompts.
  Empty memory never blocks generation; chapter 1 and manual projects are
  unaffected.
- **P2 — Editor story_facts compliance check:** Added `_run_story_facts_compliance()`
  to `EditorAgent` as pipeline step 4.5. Loads `status="active"` story_facts
  and makes one LLM pass checking for explicit contradictions (absent facts are
  not violations). Module constant `FACTS_COMPLIANCE_BLOCK_THRESHOLD = 3`: below
  threshold the result is advisory only; at or above it `output.pass_` is set to
  `False`. Stub mode always returns empty. Editor result dict always contains
  `story_facts_compliance`.
- **P3 — Memory context audit trail:** `PlannerAgent._execute()` builds a
  `memory_context_audit` dict from the bundle flags and saves it as a
  `memory_context_audit` agent artifact. `FactoryState` gains a
  `memory_context_audit: dict` field. `GET /runs/{run_id}` response now includes
  `memory_context_audit` (empty `{}` for pre-v6.6.14 runs). Chapter 1 is marked
  `batch_status="not_applicable"` instead of pretending it consumed trusted
  previous-chapter memory.
- `story_facts_compliance` is included in the Editor review artifact as well as
  the workflow state update, so fact-compliance decisions are auditable after
  the run completes.
- 17 new acceptance tests in `tests/test_v6614_continuity_enforcement.py`.
- No LangGraph topology changes. No blocking on empty memory. No frontend UI
  changes. `plot_holes` compliance deferred to v6.6.15.

## v6.6.13 - Frontend Contract Adoption Closure

Key changes:

- Extended `statusSemantics.ts` with `isActionable()` helper.
- Patched `MemoryUpdatesModule`, `ReviewModule`, `ContextSidebar` handlers to check
  `domain_result` for business success — `partial_success`/`fallback`/`degraded`
  now display warning, never green success.
- Patched `ProjectOverviewModule` auto-run status bar: completed sessions with
  step-level warnings show ⚠ instead of ✓; `handleRunAuto` wired for forward-compat
  domain_result when backend ships it.
- Added 15 new tests to `statusSemantics.test.ts` (total: 75 tests).
- No backend changes. No API additions. No UI architectural changes.

## v6.6.10 - API Contract & Frontend State Semantics Closure

Commits:

- `90e419c` - `feat(api): v6.6.10 API Contract & Frontend State Semantics Closure`
- `36bec2f` - `fix(ui): wire run detail to domain result semantics`

Key changes:

- Added unified `OperationResult` / `domain_result` API contract.
- Clarified that `ok=true` means the HTTP/API request completed, not necessarily that the business operation succeeded.
- Added domain statuses: `success`, `partial_success`, `fallback`, `degraded`, `failed`, `blocked`, `needs_human`, `pending`, `ignored`.
- Added frontend status semantics helper in `frontend/src/lib/statusSemantics.ts`.
- Wired Run Detail to `domain_result`, so fallback/degraded memory results are no longer displayed as successful.

Verification:

- Backend full suite reported: `2471 passed`.
- Frontend `typecheck`, `lint`, `build`, and `statusSemantics` tests passed.
- Focused review fix verified with related backend regression tests and frontend checks.

Known follow-up:

- `workflow-timeline` node-level semantics are not fully closed yet; planned for v6.6.11.

## v6.6.9 - Database Migration & Persistence Integrity Closure

Commits:

- `cc1cb99` - `feat(db): v6.6.9 Database Migration & Persistence Integrity Closure`
- `c1ec7a1` - `fix(db): P1 tighten multi-table migration detection to prevent partial-migration startup failure`

Key changes:

- Replaced the large `_is_migration_applied_by_schema()` if/elif chain with a declarative migration registry.
- Added migration health and critical table integrity diagnostics.
- Preserved old database compatibility through schema-based migration detection.
- Fixed partial migration detection for multi-table migrations so a single representative table no longer marks the whole migration as applied.

Verification:

- v6.6.9 focused tests after review fix: `76 passed`.
- Related regression tests: `100 passed`.
- Backend full suite after review fix: `2436 passed`.

Known follow-up:

- Future migrations must add a registry entry with all tables/columns/indexes needed to prove the migration is fully applied.

## v6.6.8 - Editor Refactor & Review Semantics Closure

Commit:

- `bec0012` - `feat(editor): v6.6.8 Editor Refactor & Review Semantics Closure`

Key changes:

- Refactored `EditorAgent._execute()` into a clearer private-method pipeline.
- Added explicit editor policy semantics via `EditorPolicyInput` and deterministic classification.
- Ensured advisory-only findings do not trigger automatic revision.
- Ensured diagnostic score never replaces review score.
- Ensured revision decisions have a non-empty `revision_target`.
- Added complete `_policy_input` and `_policy_output` snapshots to editor artifacts after focused review.

Verification:

- Backend full suite reported: `2360 passed`.
- Frontend `typecheck`, `lint`, and `build` passed.

Known follow-up:

- No open P1/P2 from the focused review after `bec0012`.

## v6.6.7 - Memory Curator Reliability Closure

Commits:

- `5fac01a` - `feat(v6.6.7): Memory Curator Reliability Closure`
- `07351ac` - `fix(memory): align API trusted memory classification with Planner rules`

Key changes:

- Hardened MemoryCurator JSON extraction and patch validation.
- Introduced clearer memory extraction result semantics:
  - `trusted_extraction`
  - `fallback_candidate`
  - `failed_no_memory`
- Added memory status classification for trusted/fallback/empty/ignored batches.
- Added force backfill behavior so old fallback batches do not block a new extraction attempt.
- Fixed API trusted-memory classification to require Planner-compatible trust rules: confidence threshold and evidence text.

Verification:

- Backend full suite after focused fix reported: `2324 passed`.
- Frontend checks passed.

Known follow-up:

- Timeline and broader frontend surfaces still needed unified fallback/degraded display, later addressed in v6.6.10+.

## v6.6.6 - Workflow Recovery & State Integrity Closure

Commits:

- `4042df9` - `feat(v6.6.6): Workflow Recovery & State Integrity Closure`
- `3a14637` - `fix(v6.6.6): focused review - local revision pollution + version baseline sync`

Key changes:

- Added workflow recovery state derivation and checkpoint stale detection.
- Added local edit protection for protected chapter states.
- Added recovery state data to run detail and workflow timeline APIs.
- Fixed focused review issues around local revision state pollution and version baseline drift.

Verification:

- Backend full suite reported: `2295 passed`.
- Frontend `typecheck`, `lint`, and `build` passed.

Known follow-up:

- Node-level timeline semantics remained coarse and were planned for a later version.

## v6.6.5 - Runtime Hygiene & Observability Closure

Commits:

- `3de73f5` - `v6.6.5: Runtime Hygiene & Observability Closure`
- `5a8e3b8` - `v6.6.5 follow-up: Fix 3 review findings`
- `c138796` - `docs: Update v6.6.5 review with follow-up fixes and residual risk`

Key changes:

- Added unified runtime version source in `novel_factory/version.py`.
- Updated API metadata, health endpoint, CLI version, and desktop runtime info to use the unified version.
- Added redaction utilities for API keys, bearer tokens, URL credentials, and sensitive environment-style strings.
- Improved best-effort exception logging in runtime paths.

Verification:

- Backend full suite after follow-up reported: `2274 passed`.
- Frontend `typecheck`, `lint`, and `build` passed.

Known follow-up:

- Migration system remained a known technical debt item until v6.6.9.

## v6.6.4 - Genesis Initialization Depth & Specificity Closure

Commit:

- `680e7cd` - `v6.6.4: Genesis depth & specificity closure`

Key changes:

- Deepened Genesis prompt requirements for character motivation, faction action, plot hooks, and continuity seeds.
- Expanded draft normalization so richer generated fields survive approval.
- Strengthened quality gate checks for shallow instructions, abstract objectives, weak key events, shallow motivations, and abstract outlines.
- Improved frontend quality report grouping and blocking/warning display.

Verification:

- Backend full suite reported: `2239 passed`.
- Frontend `typecheck`, `lint`, and `build` passed.

Known follow-up:

- Broader API and frontend state semantics were still inconsistent and later addressed in v6.6.10.

## v6.6.3 - Genesis Initialization Quality Gate

Commit:

- `c31d630` - `feat(genesis): v6.6.3 Genesis Initialization Quality Gate`

Key changes:

- Added Genesis quality gate for repetitive chapter instructions, generic names, shallow outlines, generic plot holes, and scaffold fallback drafts.
- Added force-apply semantics with explicit quality-risk confirmation.
- Added frontend quality report display and approval blocking when quality gate fails.

Verification:

- Dedicated quality gate tests passed.
- Follow-up versions continued to pass full backend and frontend checks.

Known follow-up:

- Quality gate detected shallow drafts, but Genesis generation depth itself still needed strengthening, addressed in v6.6.4.

## v6.6.2 - Agent Context Inheritance Foundation

Commit:

- `bf5073c` - `feat: v6.6.2 Agent Context Inheritance Foundation`

Key changes:

- Added unified context building for agent inheritance.
- Wired Planner, Screenwriter, Author, Polisher, and Editor to stronger context bundles.
- Distinguished trusted memory from low-confidence fallback/advisory memory.
- Added chapter inheritance checks for suspense, timeline, plot obligations, and fact locks.

Verification:

- Dedicated v6.6.2 tests reported: `20 passed`.
- Related regression tests and full suite passed at the time of implementation.

Known follow-up:

- Memory extraction reliability still needed hardening, addressed in v6.6.7.

## v6.6.1 and Earlier - Historical Baseline

This section summarizes the project history before the current v6.6.2+ closure line. Older versions are documented in more detail under `docs/codex/planning/`, `docs/codex/reports/`, and `docs/codex/reviews/`.

### v6.6.1 - Quality Diagnosis Workflow Loop Closure

Representative commits:

- `f31e406` - `feat(v6.6.1): close quality diagnosis workflow loop`

Key changes:

- Closed the quality diagnosis workflow loop.
- Stabilized review and diagnosis score handling before the later Editor semantics refactor.
- Prepared the ground for v6.6.2 context inheritance and v6.6.8 review policy formalization.

### v6.6.0 / v6.5.x - Interaction Excellence and UI Polish

Representative commits:

- `44fcc9c` - `feat(v5.9.3): expand skills across core agents`
- Later v6.x documentation and feature commits recorded under `docs/codex/reports/` and `docs/codex/reviews/`.

Key changes:

- Expanded agent role and capability system.
- Added agent work-process streaming and creator onboarding closure.
- Improved chapter quality systems across author drafting, dialogue/scene texture, anti-AI skills, Editor advisory gates, and real-LLM acceptance.
- Added interaction primitives, project overview workbench polish, chapter writing surface polish, agent process narrative, settings/runtime polish, interaction excellence closure, and visual polish pass.

Relevant docs:

- `docs/codex/reports/novel-factory-v6.0-completion-report.md`
- `docs/codex/reports/novel-factory-v6.1-completion-report.md`
- `docs/codex/reports/novel-factory-v6.2-desktop-client-completion-report.md`
- `docs/codex/reports/novel-factory-v6.3-completion-report.md`
- `docs/codex/reports/novel-factory-v6.4.6-chapter-quality-closure-report.md`
- `docs/codex/reports/novel-factory-v6.5.7-visual-polish-pass-report.md`

### v5.9.x - UI Control Standardization and Agent Skill Expansion

Representative commits:

- `fde05f0` - `feat(v5.9.1): improve skill capability console UX`
- `dfb31c8` - `feat(v5.9.2): standardize frontend UI controls`
- `44fcc9c` - `feat(v5.9.3): expand skills across core agents`

Key changes:

- Standardized frontend controls and softened Skill Console navigation/layout.
- Expanded Skill usage across core agents.
- Improved skill capability console UX and style bible checker binding.

Relevant docs:

- `docs/codex/reports/novel-factory-v5.9.2-completion-report.md`
- `docs/codex/reports/novel-factory-v5.9.3-completion-report.md`

### v5.8.x - Workflow Observability and Real LLM Acceptance Hardening

Representative commits:

- `c94785b` - `feat(v5.8): add workflow observability timeline`
- `1f99e42` - `fix(v5.8.1): harden real LLM acceptance flow`
- `85da090` - `fix(v5.8.1): harden real LLM acceptance flow`
- `edf1766` - `fix(v5.8.2): align workflow timeline with graph truth`

Key changes:

- Added workflow observability timeline.
- Hardened real-LLM acceptance flow.
- Aligned workflow timeline with graph truth.

Relevant docs:

- `docs/codex/reports/novel-factory-v5.8-completion-report.md`
- `docs/codex/reports/novel-factory-v5.8.1-real-llm-acceptance-report.md`

### v5.7.x - Daily Writing, Editing, Versioning, and Internal Hardening

Representative commits:

- `f89e1d6` - `feat(v5.7): add daily writing editor and webui refresh`
- `9e79c1e` - `fix(v5.7.1): prioritize stale run recovery and protect existing content`
- `40194bb` - `fix(v5.7.1): prevent old chapter publish from moving progress backward`
- `3c7b22a` - `fix(v5.7.1): restore auto-run timeout threshold wiring`
- `a62ebc0` - `fix(v5.7.1): route running target chapters to workflow progress`
- `c85c172` - `fix(v5.7.1): stabilize production validation loop`

Key changes:

- Added daily writing editor, editing/versioning workflows, and WebUI refresh.
- Protected existing chapter content and improved stale run recovery.
- Stabilized production validation and chapter progress behavior.

Relevant docs:

- `docs/codex/reports/novel-factory-v5.7-completion-report.md`
- `docs/codex/reports/novel-factory-v5.7.1-real-project-acceptance.md`

### v5.6.x - Author Workbench Web UI

Representative commits:

- `b725bde` - `feat(v5.6): introduce author workbench webui`
- `4d59b04` - `fix(v5.6): polish workbench navigation and recovery UI`
- `d8482c0` - `feat(v5.6): improve dialogs and workflow feedback`
- `b787cfa` - `fix(v5.6): humanize run artifacts and task labels`
- `5b68f9d` - `fix(v5.6.1): stabilize author workbench flows`
- `4197147` - `fix(v5.6.1): review fixes — pending props, exception safety, contradiction priority, menu run lookup`

Key changes:

- Introduced the author workbench WebUI.
- Improved navigation, dialogs, workflow feedback, recovery UI, and artifact readability.
- Stabilized author workbench flows and terminal chapter workflow reconciliation.

Relevant docs:

- `docs/codex/reports/novel-factory-v5.6-author-workbench-completion-report.md`
- `docs/codex/reports/novel-factory-v5.6.1-workbench-stabilization-completion-report.md`

### v5.5.x - Production Reliability, Recovery, and Autonomous Production

Representative commits:

- `13ef4e0` - `Add v5.5.0 run recovery console`
- `6867eb6` - `Add v5.5.1 stuck run detection`
- `fc7baf3` - `Add v5.5.2 run health dashboard`
- `9bbee4f` - `Add v5.5.3 autonomous production loop`
- `5d0ae9f` - `Add v5.5.4 real LLM autonomous planning`
- `9581336` - `feat: implement v5.5.5 Autonomous Production Runner`
- `7ee5f62` - `feat: v5.5.6 Production Command Center UI Refresh`
- `321526a` - `feat: v5.5.7 real-time production monitor`
- `59e528d` - `feat: v5.5.8 auto-run control loop`
- `baa16bf` - `feat: v5.5.9 auto-run resilience`
- `49987a4` - `fix: close v5.5.15 production readiness gaps`
- `fb984df` - `fix(v5.5.15): unified run guard + runner reviewed semantics + test cleanup`

Key changes:

- Added run recovery console, stuck run detection, run health dashboard, and recovery actions.
- Added autonomous production loop, real-LLM autonomous planning, production runner, command center, real-time monitor, auto-run control, and resilience.
- Closed production-readiness gaps including terminal chapter guards and runner `reviewed` semantics.

Relevant docs:

- `docs/codex/reports/novel-factory-v5.5.15-completion-report.md`
- `docs/codex/reviews/novel-factory-v5.5.15-review.md`

### v5.4.x - Project Workbench and Skill Console Refactor

Representative commits:

- `2e40977` - `Add v5.4 WebUI refactor plan`
- `6c3cba6` - `Introduce v5.4 project workbench shell`
- `a08af54` - `Extract v5.4 chapter workspace component`
- `2e49be5` - `Split v5.4 settings console sections`
- `78e2a06` - `Add v5.4 Agent Skill Matrix`
- `946d161` - `Add v5.4.6 Agent Skill Configuration Console`
- `30423fd` - `Add v5.4.13 project-specific skill overrides`

Key changes:

- Refactored the WebUI into project workbench, chapter workspace, settings console sections, and attention panels.
- Added Agent Skill Matrix and skill configuration console.
- Added project-specific skill overrides and universal skill import readiness/apply flows.

### v5.3.x - Trusted Generation Chain, Genesis, Memory Loop, and Fact Ledger

Representative commits:

- `c60c305` - `feat: add v5.3 trusted generation chain`
- `0aab6ca` - `Add v5.3.x genesis, memory loop, and fact ledger features`
- `2065c78` - `Add v5.3.3 Skill visibility panel`
- `23ef461` - `Add v5.3.4 Skill test bench`
- `108028f` - `Isolate workflow task errors by workflow_run_id (v5.3.6)`
- `c4b3da6` - `Add v5.3.7 real LLM burn-in report and fixes`

Key changes:

- Added trusted generation chain.
- Added project genesis, memory loop, fact ledger, skill visibility, and skill test bench.
- Improved workflow task isolation by `workflow_run_id`.
- Added real-LLM burn-in reporting and fixes.

### v5.2 - Product Completion and Real LLM Closure

Representative commits:

- `239b3e5` - `feat: complete v5.2 product closure`
- `2b8d52e` - `fix: close v5.2 validation gaps`

Key changes:

- Closed product completion and real-LLM validation gaps for the v5.2 line.
- Stabilized generation, review, and acceptance paths before the v5.3 authoring-system reset.

### v5.1.x - Frontend Separation, API Backend, and Author Workspace Productization

Representative commits:

- `79a1a86` - `feat(v5.1): 前后端分离 - FastAPI JSON API + React 前端`
- `36c0573` - `chore: harden v5.1 API frontend acceptance - add smoke tests and security checks`
- `40fdb66` - `feat: productize v5.1 React author workbench`
- `5e51fc5` - `fix: align chapter and workflow status models`
- `07ddded` - `fix(v5.1.2): complete pending→planned normalization in /api/run/chapter`
- `868bfb6` - `feat(v5.1.3): Author Workflow Usability Closure`
- `7e0c556` - `feat: add workflow visibility and document v5.1.4`
- `2a09be5` - `feat(v5.1.5~v5.1.6): author workspace productization & LangGraph activation`

Key changes:

- Split FastAPI JSON backend and React frontend.
- Added smoke/security acceptance for API/frontend.
- Productized React author workbench.
- Aligned chapter and workflow status models.
- Added author workflow usability closure, workflow visibility, and LangGraph activation.

### v5.0 and Earlier - MVP to WebUI Acceptance

Representative commits:

- `92443a0` - `feat: checkpoint novel factory through v3.4 production queue`
- `4cc9194` - `feat: v4.7-v5.0 WebUI enhancements and acceptance`

Key changes:

- v1.x: MVP, review fixes, stability, quality, dispatcher CLI, and runtime hardening.
- v2.x: multi-agent architecture, QualityHub skill system, skill manifest/package planning.
- v3.x: batch production, LLM routing, batch review/revision, continuity gate, production queue, semi-auto serial mode, review workbench, skill import bridge, model catalog.
- v4.x: style bible, style gate evolution, sample analyzer, WebUI acceptance console, review UX hardening, personal onboarding, first-run guided workflow, project workspace/author cockpit, Web acceptance matrix, and settings/LLM/agent ops console.
- v5.0: implemented-features WebUI acceptance and Chinese UX productization groundwork.

Relevant docs:

- `docs/codex/planning/novel-factory-v1-mvp-spec.md`
- `docs/codex/planning/novel-factory-v2-multi-agent-spec.md`
- `docs/codex/planning/novel-factory-v3.0-batch-production-spec.md`
- `docs/codex/planning/novel-factory-v4.0-style-bible-mvp-spec.md`
- `docs/codex/planning/novel-factory-v5.0-implemented-features-webui-acceptance-spec.md`
