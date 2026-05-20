# Changelog

This file tracks the project-level version history for Novelos.

Detailed implementation notes still live in:

- `docs/codex/specs/`
- `docs/codex/reports/`
- `docs/codex/reviews/`

Use this file as the short, canonical version ledger: version, commit(s), key changes, verification, and known follow-up risk.

## Unreleased

- Fixed the sidebar version badge so the client UI reads from `frontend/package.json` instead of a stale hardcoded `v5.5.9`.
- Synchronized frontend and desktop package-lock root versions to `6.6.16`.
- Hardened Genesis initialization fallback: completion patches now deduplicate repeatable sections instead of appending duplicates, scaffold instructions are chapter-specific, and scaffold previews are shown as recovery panels rather than normal drafts.
- Fixed Genesis real-LLM failure recovery: invalid or incomplete JSON now produces a reviewable `local_recovery` draft based on the project premise instead of an automatically blocked scaffold template; true scaffold fallback reports now score `0`.

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
- Full test suite: **2596 passed**
- Frontend typecheck/lint/build: passed
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
