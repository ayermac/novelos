# v6.9.0 Phase Execution Plan

本文档为 v6.9.0 的 6 个 Phase 提供详细的执行清单，设计为每个 Phase 可分配给独立的 agent 执行。

---

## Phase 0: Foundation（基础设施）

**Agent 任务**：搭建数据模型、数据库迁移、存储层。

### 上下文

- 当前版本：v6.8.5
- 已有基础设施：`novel_factory/models/`、`novel_factory/db/migrations/`、`novel_factory/db/repositories/`
- 参考现有模型风格：`novel_factory/models/` 下的 Pydantic 模型
- 参考现有迁移风格：`novel_factory/db/migrations/` 下已有迁移脚本

### 分步任务

#### Step 0.1: 创作合同模型
- 创建 `novel_factory/models/creative_contracts.py`
- 定义 Pydantic 模型：
  - `ProjectLaunchProfile`（12 字段：target_reader, market_lane, genre_family, subgenre, title_promise, core_hook, primary_payoff_loop, secondary_payoff_loops, protagonist_growth_engine, commercial_comps, first_30_chapter_strategy, hard_do_not_drift_rules）
  - `GenreContract`（~15 字段：genre_id, promise_statement, reader_expectations, must_have_beats, allowed_dark_lines, forbidden_drift, payoff_cadence, pressure_limits, upgrade_cadence, relationship_cadence, mystery_reveal_cadence, style_constraints, editor_weights, approved, approved_at）
  - `GenreProfile`（~10 字段：profile_id, default_reader_expectations, default_payoff_loop, opening_requirements, chapter_rhythm_defaults, common_poison_points, style_noise_patterns, editor_weight_profile, profile_specific_rules）
- 所有模型使用 `pydantic.BaseModel`，字段带 `Field(description=...)`
- 添加 `from_dict` 和 `to_dict` 方法（或利用 pydantic 的 `.model_dump()`）

#### Step 0.2: 章节合同模型
- 创建 `novel_factory/models/chapter_contracts.py`
- 定义 `ChapterBrief`（Tier 1: chapter_goal, reader_payoff, protagonist_agency, forbidden_moves; Tier 2: pressure_budget, payoff_budget, upgrade_or_skill_use, character_arc_moves, mystery_actions, conflict_actions, ledger_debts_to_pay, new_debts_allowed, scene_count_target, opening_hook, ending_hook, quality_threshold_overrides）
- 定义 `EditorLensReport`（lens_type, verdict: PASS/FAIL/WARN, score, findings, suggestions）
- 定义 `RhythmBudgetResult`（deterministic_pass, llm_pass, blocking_issues, warnings, style_fatigue_score）

#### Step 0.3: 创作台账模型
- 创建 `novel_factory/models/creative_ledgers.py`
- 定义 `CreativeLedger` 基类（project_id, chapter_number, ledger_type, entries, summary）
- 定义 7 个子类：`ReaderPromiseLedger`, `PowerGrowthLedger`, `CharacterArcLedger`, `MysteryRevealLedger`, `ConflictLedger`, `PayoffLedger`, `StyleFatigueLedger`
- 每个子类添加类型特定的 entry schema

#### Step 0.4: 数据库迁移
- 创建 `novel_factory/db/migrations/v690_creative_contracts.py`
- 参考现有迁移脚本写法（查找 `novel_factory/db/migrations/` 下的最新迁移）
- 创建 4 张表：`project_creative_contracts`, `chapter_briefs`, `creative_ledger_snapshots`, `editor_lens_reports`
- 包含 `up()` 和 `down()` 函数
- 在迁移注册表中注册新迁移

#### Step 0.5: Repository 层
- 参考现有 repository 风格（`novel_factory/db/repositories/`）
- 创建 `ProjectCreativeContractRepository`：`save(project_id, contract_type, data)`, `get(project_id, contract_type)`, `exists(project_id, contract_type)`
- 创建 `ChapterBriefRepository`：`save(project_id, chapter_number, data, workflow_run_id)`, `get(project_id, chapter_number)`
- 创建 `CreativeLedgerSnapshotRepository`：`save(project_id, chapter_number, ledger_type, data, patch)`, `get_latest(project_id, ledger_type)`, `get_all_for_chapter(project_id, chapter_number)`
- 创建 `EditorLensReportRepository`：`save(project_id, chapter_number, lens_type, data, workflow_run_id)`, `get_all_for_chapter(project_id, chapter_number)`

#### Step 0.6: CreativeLedgerCurator 骨架
- 创建 `novel_factory/agents/creative_ledger_curator.py`
- 继承 `novel_factory/agent_runtime/` 下的 `BaseAgent`
- 实现空壳方法：`update_ledgers(chapter_context, draft) -> list[CreativeLedger]`
- 确保可被导入且不报错

### 验证清单
- [ ] `python3 -c "from novel_factory.models.creative_contracts import ProjectLaunchProfile, GenreContract, GenreProfile"` 成功
- [ ] `python3 -c "from novel_factory.models.chapter_contracts import ChapterBrief, EditorLensReport, RhythmBudgetResult"` 成功
- [ ] `python3 -c "from novel_factory.models.creative_ledgers import ReaderPromiseLedger"` 成功
- [ ] 迁移脚本执行成功且可回滚
- [ ] Repository 基本 CRUD 测试通过
- [ ] `python3 -c "from novel_factory.agents.creative_ledger_curator import CreativeLedgerCurator"` 成功

---

## Phase 1: Launch Profile & Genre Contract

**Agent 任务**：新项目必须生成合同才能启动章节生产。

### 上下文

- Phase 0 已完成，模型和存储层就绪
- 现有 Genesis 逻辑在 `novel_factory/quality/genesis_quality_gate.py`
- 现有 API 路由在 `novel_factory/api/routes/`
- 现有 CLI 在 `novel_factory/cli_app/`

### 分步任务

#### Step 1.1: Genre Profile 配置
- 创建 `config/genre_profiles/` 目录
- 创建 3 个 YAML 文件，参考 spec 4.3 节的结构：
  - `urban_sign_in_power_fantasy.yaml`
  - `suspense_mystery.yaml`
  - `cultivation_upgrade.yaml`
- 每个 YAML 包含：profile_id, default_reader_expectations, default_payoff_loop, opening_requirements, chapter_rhythm_defaults, common_poison_points, style_noise_patterns, editor_weight_profile, profile_specific_rules

#### Step 1.2: GenreProfile 加载器
- 创建 `novel_factory/config/genre_profile_loader.py`
- 实现 `load_genre_profile(profile_id: str) -> GenreProfile`
- 实现 `get_all_profile_ids() -> list[str]`
- 对未完善的 profile（7 个），返回通用默认 GenreProfile

#### Step 1.3: Genesis 扩展
- 在 `novel_factory/quality/genesis_quality_gate.py` 中新增方法：
  - `generate_launch_profile(user_idea: str, genre_profile: GenreProfile) -> ProjectLaunchProfile`
  - `generate_genre_contract(launch_profile: ProjectLaunchProfile, genre_profile: GenreProfile) -> GenreContract`
- 需要 LLM 调用：构造 prompt，要求 LLM 输出 JSON，解析为对应模型
- 在 stub 模式下返回确定性输出

#### Step 1.4: 项目就绪检查
- 在 `novel_factory/quality/genesis_quality_gate.py` 中新增：
  - `check_project_ready_for_production(project_id: str) -> bool`
  - 检查 `project_creative_contracts` 表中是否存在 `launch_profile` 和 `genre_contract` 记录
  - 检查 `genre_contract` 的 `approved` 字段

#### Step 1.5: API 端点
- 新增 `GET /api/projects/{id}/creative-contracts`：返回 launch_profile 和 genre_contract
- 新增 `POST /api/projects/{id}/creative-contracts/approve`：设置 genre_contract.approved = True
- 新增 `POST /api/projects/{id}/creative-contracts/generate`：触发 Genesis 生成合同

#### Step 1.6: CLI 命令
- 新增 `novelos contract show --project-id <id>`：显示合同
- 新增 `novelos contract approve --project-id <id>`：审批合同

#### Step 1.7: 前端
- 在项目设置页面新增"创作合同"标签页
- 显示 launch_profile 和 genre_contract 内容
- 提供"审批"按钮（调用 POST /approve API）
- 项目未审批时，在章节生成按钮旁显示警告

### 验证清单
- [ ] `novelos contract show --project-id demo` 显示合同内容
- [ ] `novelos contract approve --project-id demo` 审批成功
- [ ] 未审批的项目调用 `check_project_ready_for_production()` 返回 False
- [ ] 前端可查看和审批合同

---

## Phase 2: Chapter Brief Contract

**Agent 任务**：Planner 产出结构化 ChapterBrief，下游节点受 brief 约束。

### 上下文

- Phase 0-1 已完成
- 现有 Planner 在 `novel_factory/agents/planner.py`
- 现有 Screenwriter 在 `novel_factory/agents/screenwriter.py`
- 现有 Author 在 `novel_factory/agents/author.py`
- 现有工作流节点在 `novel_factory/workflow/nodes.py`

### 分步任务

#### Step 2.1: Planner 扩展
- 扩展 Planner 的 prompt 模板，在输出中增加 `ChapterBrief` JSON 块
- 要求输出 Tier 1 的 4 个必填字段
- 尽量输出 Tier 2 的 12 个字段
- 在 stub 模式下返回确定性 brief

#### Step 2.2: Brief 验证器
- 创建 `novel_factory/quality/chapter_brief_validator.py`
- 实现 `validate_chapter_brief(brief: dict) -> tuple[bool, list[str]]`
- Tier 1 字段缺失 → blocking（返回 False + 缺失字段列表）
- Tier 2 字段缺失 → 用 genre profile 默认值填充，不 blocking
- 实现 `fill_missing_tier2_fields(brief: dict, genre_profile: GenreProfile) -> dict`

#### Step 2.3: 工作流集成
- 在 `novel_factory/workflow/nodes.py` 中新增 `brief_validation_node` 函数
- 在 `novel_factory/workflow/graph.py` 中插入 `brief_validation` 节点（planner 之后）
- 新增条件边：Tier 1 缺失 → 回到 planner；通过 → 进入 rhythm_budget_preflight

#### Step 2.4: Screenwriter 更新
- 更新 Screenwriter prompt：注入 brief 的 `forbidden_moves` 和 `ledger_debts_to_pay`
- 确保生成的节拍不违反 brief 约束

#### Step 2.5: Author 更新
- 更新 Author prompt：注入 brief 约束
- 确保起草的文本遵守 brief 的 `chapter_goal` 和 `protagonist_agency`

#### Step 2.6: API 端点
- 新增 `GET /api/projects/{id}/chapters/{n}/brief`：返回章节 brief

### 验证清单
- [ ] Planner 在 stub 模式下输出有效 ChapterBrief JSON
- [ ] `validate_chapter_brief` 正确检测 Tier 1 缺失
- [ ] Tier 2 缺失字段用默认值填充
- [ ] `GET /api/projects/demo/chapters/1/brief` 返回 brief 内容

---

## Phase 3: Rhythm Budget & Creative Ledgers

**Agent 任务**：节奏预检 + 7 个创作台账的读写和更新。

### 上下文

- Phase 0-2 已完成
- 现有 MemoryCurator 在 `novel_factory/agents/memory_curator.py`
- 现有上下文构建在 `novel_factory/context/builder.py`

### 分步任务

#### Step 3.1: RhythmBudget 确定性层
- 创建 `novel_factory/quality/rhythm_budget.py`
- 实现 6 个确定性指标检测函数：
  - `detect_pressure_streak(chapters: list) -> int`
  - `detect_passive_protagonist_streak(chapters: list) -> int`
  - `detect_payoff_gap(chapters: list) -> int`
  - `detect_visible_upgrade_gap(chapters: list) -> int`
  - `count_new_mysteries(brief: ChapterBrief) -> int`
  - `detect_mystery_answer_gap(chapters: list) -> int`
- 实现 `evaluate_deterministic(chapters, brief, genre_contract) -> RhythmBudgetResult`
- 4 条默认 blocking 规则（见 spec 4.6.2）

#### Step 3.2: RhythmBudget LLM 辅助层
- 创建 `novel_factory/quality/rhythm_budget_llm.py`
- 实现 4 个 LLM 辅助检测（仅当确定性层 PASS 时运行）：
  - `check_style_fatigue(draft, ledger) -> float`
  - `detect_character_tooling(draft, ledger) -> list[str]`
  - `check_breathing_room(draft, chapters) -> bool`
  - `check_relationship_movement(draft, ledger) -> bool`

#### Step 3.3: 工作流集成
- 在 `nodes.py` 中新增 `rhythm_budget_preflight_node`
- 在 `graph.py` 中插入节点（brief_validation 之后）
- 条件边：PASS → screenwriter；FAIL → planner（修订 brief）

#### Step 3.4: CreativeLedgerCurator 实现
- 完善 `novel_factory/agents/creative_ledger_curator.py`
- 实现 `update_ledgers(chapter_context, draft, chapter_number) -> dict[str, CreativeLedger]`
- 为每个 ledger 构造 prompt，要求 LLM 输出增量更新
- 读取上一章 ledger 快照作为上下文
- 使用 `CreativeLedgerSnapshotRepository` 保存

#### Step 3.5: Ledger 上下文
- 创建 `novel_factory/context/ledger_context.py`
- 实现 `load_ledgers_for_planner(project_id, chapter_number) -> dict`
- 从 `CreativeLedgerSnapshotRepository` 读取最新快照，构建 Planner 上下文

#### Step 3.6: 工作流集成
- 在 `nodes.py` 中新增 `creative_ledger_curator_node`
- 在 `graph.py` 中插入节点（publisher 之后）
- 条件边：始终 → END

#### Step 3.7: Planner 更新
- 更新 Planner prompt：注入 ledger 上下文（来自 `load_ledgers_for_planner`）

#### Step 3.8: API 端点
- 新增 `GET /api/projects/{id}/ledgers`：返回所有 ledger 最新快照
- 新增 `GET /api/projects/{id}/ledgers/{ledger_type}`：返回特定 ledger 历史

### 验证清单
- [ ] `rhythm_budget.py` 确定性层 6 个指标全部有单元测试覆盖
- [ ] 4 条默认 blocking 规则正确触发
- [ ] `creative_ledger_curator.py` 在 stub 模式下更新 ledger
- [ ] `load_ledgers_for_planner` 返回正确的 ledger 数据
- [ ] `GET /api/projects/demo/ledgers` 返回 ledger 数据

---

## Phase 4: Specialized Editor Lenses

**Agent 任务**：拆分评审为 8 个视角，主编统一决策。

### 上下文

- Phase 0-3 已完成
- 现有 Editor 在 `novel_factory/agents/editor.py`
- 现有 editor strategy 在 `novel_factory/quality/editor_strategy.py`

### 分步任务

#### Step 4.1: type_editor 和 continuity_editor
- 创建 `novel_factory/agents/editor_lenses/` 目录
- 创建 `type_editor.py`：对比 draft 与 GenreContract，检查 forbidden_drift、promise_statement 匹配
- 创建 `continuity_editor.py`：检查事实一致性（复用现有 continuity 逻辑）
- 两者优先使用确定性规则，必要时才调用 LLM

#### Step 4.2: commercial_editor, pacing_editor, character_editor
- 创建 `commercial_editor.py`：检查钩子、回报、主角能动性、追读吸引力
- 创建 `pacing_editor.py`：检查压力/奖励节奏、场景多样性
- 创建 `character_editor.py`：检查动机、能动性、关系推进、工具人风险

#### Step 4.3: mystery_editor, style_editor
- 创建 `mystery_editor.py`：检查线索债务、揭示节奏、术语过载
- 创建 `style_editor.py`：检查重复意象、AI 模板、紧张措辞

#### Step 4.4: chief_editor
- 创建 `chief_editor.py`
- 汇总所有 lens 报告
- 根据 editor_weights 做出最终 PASS/FAIL 决策
- 确定修订类别和路由目标

#### Step 4.5: Fast-path 跳过逻辑
- 创建 `novel_factory/quality/editor_lens_scheduler.py`
- 实现 `should_skip_lens(lens_type, project_id, chapter_number) -> bool`
- 规则：连续 3 章该 lens 无违规 → 跳过 LLM 重评

#### Step 4.6: 工作流集成
- 在 `graph.py` 中新增 `editor_lenses` fan-out 节点（7 个 lens 并行）
- 新增 `chief_editor` fan-in 节点
- 条件边：PASS → publisher；FAIL → 修订路由

#### Step 4.7: 修订路由更新
- 在 `conditions.py` 中新增 9 个修订类别路由
- 实现 `route_revision(revision_category) -> str`（返回目标节点名）

#### Step 4.8: API 端点
- 新增 `GET /api/projects/{id}/chapters/{n}/editor-reports`：返回所有 lens 报告

### 验证清单
- [ ] 每个 editor lens 在 stub 模式下产出有效报告
- [ ] `should_skip_lens` 在连续 3 章无违规时正确跳过
- [ ] `chief_editor` 正确汇总并做出决策
- [ ] 修订路由正确映射到目标节点
- [ ] `GET /api/projects/demo/chapters/1/editor-reports` 返回报告

---

## Phase 5: Integration, Burn-In & Polish

**Agent 任务**：端到端验证、回归测试、真实 LLM burn-in。

### 上下文

- Phase 0-4 已完成
- 现有测试在 `tests/` 目录
- 版本号在 `novel_factory/version.py`

### 分步任务

#### Step 5.1: 端到端集成测试
- 创建 `tests/test_v690_e2e.py`
- stub 模式完整流程测试：health_check → planner → brief_validation → rhythm_budget → screenwriter → author → polisher → editor_lenses → chief_editor → publisher → creative_ledger_curator
- 覆盖 3 个 genre profile

#### Step 5.2: 回归测试
- 运行 `python3 -m pytest -q`
- 确保现有 2600+ 测试全部通过
- 如有失败，修复或记录

#### Step 5.3: 新增确定性测试
- `tests/test_v690_rhythm_budget.py`：6 个指标 + 4 条规则 + genre-specific 规则
- `tests/test_v690_editor_lenses.py`：每个 lens 的 PASS/FAIL 场景
- `tests/test_v690_genesis_contract.py`：合同生成和审批流程
- `tests/test_v690_chapter_brief.py`：brief 验证和填充
- `tests/test_v690_creative_ledgers.py`：ledger 读写和增量更新

#### Step 5.4: 新项目创建流程测试
- 在 `tests/test_v690_genesis_contract.py` 中：
  - idea → launch profile → genre contract → 审批 → 章节生成
  - 未审批的 blocking 测试

#### Step 5.5: 前端集成测试
- 合同查看、审批、brief 查看、editor report 查看的 vitest 测试

#### Step 5.6: 真实 LLM burn-in
- 使用 `--llm-mode real` 创建 3 个新项目（对应 3 个 genre）
- 每个项目生成 5 章
- 使用 LLM-as-judge 评估（参考 spec 第 9 节）
- 对比 v6.8 基线输出
- 输出 burn-in 报告

#### Step 5.7: 版本号更新
- 修改 `novel_factory/version.py`：`__version__ = "6.9.0"`

#### Step 5.8: 文档更新
- 创建 `docs/codex/reports/novel-factory-v6.9.0-completion-report.md`
- 包含：完成总结、测试结果、burn-in 数据、已知问题

### 验证清单
- [ ] `python3 -m pytest -q` 全部通过
- [ ] `python3 -m pytest tests/test_v690_e2e.py -q` 通过
- [ ] 前端 `npm run test -- --run` 通过
- [ ] 前端 `npm run typecheck` 通过
- [ ] 3 个 genre 的 burn-in 均有报告
- [ ] 版本号已更新为 6.9.0
- [ ] 完成报告已创建
