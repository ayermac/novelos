# v6.9.1 开发 Prompt

你是一个专精于 Python FastAPI 和 LangGraph 工作流的高级后端工程师。你的任务是在 `novel_factory` 项目中实现 v6.9.1：Editor Skillization。

## 上下文

- 当前分支：`v6.9.0-creative-factory-capability-upgrade`
- 上一提交回退了 `editor_lenses`（旁路节点架构），恢复 `editor` 为单一审核节点
- 详细规划文档：`docs/codex/planning/novel-factory-v6.9.1-editor-skillization-spec.md`
- 当前 editor 实现：`novel_factory/agents/editor.py`
- 当前 skill 系统：`novel_factory/agent_runtime/skill_hooks.py`（`run_agent_skills`）
- 当前策略层：`novel_factory/quality/editor_strategy.py`
- skill 目录：`novel_factory/skills/`
- editor 角色配置：`novel_factory/agent_runtime/roles/editor.yaml`

## 核心设计约束（必须遵守）

1. **不新建 workflow 节点**：所有检查在 `editor` 节点内部完成，不要重复 v6.9.0 `editor_lenses` 的弯路
2. **不删除现有 quality/validators 模块**：它们被 skill 封装后仍可独立调用
3. **LLM 评审保持单次调用**：五维评分仍是 editor 的核心职责，不要拆成多个 LLM skill
4. **skill 输出统一 schema**：`{passed, score?, findings[], summary}`，findings 每项含 `severity, code, message, suggestion`
5. **向后兼容**：旧项目无 skill 配置时行为不变

## 开发任务（按 Phase 顺序执行）

### Phase 1: 去硬编码

将 `editor.py` 内所有硬编码 skill 调用改为配置驱动。

**具体步骤：**
1. 在 `novel_factory/skills/base.py` 新增 `SkillFinding` dataclass 和 `parse_skill_findings(data)` 函数
2. 删除 `_run_advisory_quality_check()` 中的硬编码 `skill_ids` 列表，改为 `skill_registry.list_skills(agent="editor", stage="advisory")`
3. 删除 `_run_before_review_skills()` 中对 `ai-style-detector` 的 `if skill_id == ...` 特殊分支，统一用 `parse_skill_findings()` 解析
4. 完善已有 skill 文件（`continuity_gate_skill.py`、`chapter_seam_skill.py`、`word_count_gate_skill.py`），确保输出符合统一 schema
5. 新建 `death_penalty_skill.py`（或复用现有），封装 `check_death_penalty_structured()`，注册到 `editor.before_review`
6. `_run_continuity_gate()` 和 `_run_chapter_seam_check()` 保留兼容层但内部改调对应 skill

**验收标准：**
- `editor.py` 搜索不到任何硬编码 skill_id
- `python3 -m pytest tests/test_workflow.py tests/test_v516_langgraph_activation.py -q` 通过
- `skill_runs` 表新增 `death-penalty`、`continuity-gate`、`chapter-seam` 执行记录

### Phase 2: 新增编辑专项 Skill

将原 editor_lenses 的评审维度转化为可插拔 skill。

**具体步骤：**
1. 新建 `novel_factory/skills/commercial_viability_checker.py`：检测钩子强度、付费点密度、追读吸引力
2. 新建 `novel_factory/skills/pacing_profile_checker.py`：检测段落分布、高潮位置、节奏曲线
3. 新建 `novel_factory/skills/character_voice_checker.py`：检测角色口吻一致性、工具人风险
4. 新建 `novel_factory/skills/mystery_integrity_checker.py`：检测伏笔债务、揭示节奏（默认关闭，悬疑 genre 自动启用）
5. 升级 `style_bible_checker.py` 输出为统一 schema，增加 `score` 字段
6. 在 `skills/config.yaml`（或等效配置）中注册所有新 skill

**验收标准：**
- 每个新 skill 在 stub 模式下产出有效统一 schema 输出
- 悬疑项目 `mystery-integrity-check` 自动启用
- editor 评审结果 issues/suggestions 中包含新 skill 的 findings

### Phase 3: 策略层聚合升级

让 `editor_strategy.py` 聚合 LLM 评分和 skill 结果。

**具体步骤：**
1. 修改 `EditorPolicyInput`，新增：`skill_weighted_score`、`blocking_skill_count`、`warning_skill_count`
2. 新增 `aggregate_skill_scores(skill_scores, editor_weights) -> float`
3. 修改 `classify_editor_result()`：
   - `blocking_skill_count > 0` → 强制 revision
   - `skill_weighted_score < 70` → revision
   - `skill_weighted_score >= 85` 且无 blocking → pass
4. 向后兼容：无 skill 结果时回退到 LLM 原始 score

**验收标准：**
- `editor_strategy.py` 单元测试覆盖加权评分路径
- blocking skill 强制不通过的测试通过
- 旧项目评审行为不变

### Phase 4: 动态 Skill 调度（可选）

根据 genre、章节位置动态启用 skill。

**具体步骤：**
1. 新建 `novel_factory/skills/editor_skill_resolver.py`，实现 `resolve_active_skills(project_id, chapter_number, genre_contract, repo)`
2. 规则：首章追加 `opening-hook-check`；悬疑 genre 追加 `mystery-integrity-check`
3. Skill manifest 支持 `sampling_mode` 和 `sampling_interval`

**验收标准：**
- 首章自动启用 `opening-hook-check`
- 连续通过的 skill 正确进入 sampling skip

## 测试要求

- 每完成一个 Phase 运行：`python3 -m pytest tests/test_workflow.py tests/test_v516_langgraph_activation.py tests/test_v58_workflow_observability.py tests/test_v690_e2e.py -q`
- 最终回归：`python3 -m pytest -q`（2600+ 测试全部通过）
- 新增测试文件：`tests/test_v691_editor_skillization.py`、`tests/test_v691_skill_aggregation.py`

## 参考资料

- 详细 Spec：`docs/codex/planning/novel-factory-v6.9.1-editor-skillization-spec.md`
- v6.8.0 skill 化先例：`docs/codex/planning/novel-factory-v6.8.0-skillized-quality-gates-spec.md`
- v6.9.0 回退记录：`docs/codex/reports/novel-factory-v6.9.0-completion-report.md`

## 输出要求

- 每次修改后提交 atomic commit（一个 Phase 一到两个 commit）
- commit message 格式：`feat(v6.9.1): <phase>-<description>`
- 最终提交附带 CHANGELOG 更新
