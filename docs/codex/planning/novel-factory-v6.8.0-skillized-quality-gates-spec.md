# v6.8.0 — Skillized Quality Gates

**Status**: Planned
**Date**: 2026-05-29
**Previous**: v6.7.9 Narrative Continuity Gate

---

## 1. Problem Statement

v6.7.9 新增了确定性叙事连续性门控（`continuity_gate.py`），但该模块是直接被 Editor/Publisher 调用的独立 Python 模块，**未走 Skill 体系**。

当前项目的质量检查分散在三个层面：

| 层面 | 位置 | 数量 | 问题 |
|------|------|------|------|
| Agent 内嵌方法 | `editor.py` / `author.py` / `polisher.py` | ~15 个 | 与 Agent 耦合，不可复用，不可配置 |
| 独立 quality 模块 | `quality/continuity_gate.py` 等 | ~9 个 | 直接调用，不经过 Skill Registry，无 `skill_runs` 审计 |
| 已注册 Skills | `skills/` 目录 | 12 个 | 运作正常，但覆盖面不足 |

**根本矛盾**：确定性质量检查越来越多，但它们不走 Skill 体系，导致：
- 无法通过 `skills.yaml` 统一配置启用/禁用
- 无法在 `skill_runs` 表中追踪执行历史
- 无法按项目粒度覆盖（`project_overrides`）
- 无法被 `run_agent_skills` 的 failure policy 统一管理
- 无法被 `default_capability_packs` 在角色配置中声明

## 2. Goal

将散落在 Agent 和 quality 模块中的确定性质量检查，**注册为标准 Skills**，让主流程更薄、质量闸门更可配置、执行历史可审计。

### Non-Goals

- **不重写检查逻辑** — 现有 `continuity_gate.py`、`chapter_seam.py`、`death_penalty.py` 等模块的检测算法不变
- **不把 LLM 调用封装成 Skill** — Skill manifest 禁止 `call_llm`
- **不把整个 Agent 主职责搬进 Skill** — Agent 负责流程编排和 LLM 调用，Skill 负责可复用的确定性检查
- **不针对特定项目/角色/章节写死** — 所有逻辑必须通用

## 3. Skills to Extract

### 3.1 Phase 1 — Register Existing Quality Modules as Skills

以下模块已经是确定性实现，只需注册到 Skill 体系：

#### `continuity-gate` (validator)

- **来源**: `novel_factory/quality/continuity_gate.py` → `evaluate_chapter_continuity()`
- **当前调用方**: Editor `_run_continuity_gate()`, Publisher node, API publish endpoint
- **提取方式**: 创建 `skills/continuity_gate_skill.py`，封装 `evaluate_chapter_continuity()` 为 `ValidatorSkill.run()`
- **输入 schema**: `{content, title, project_id, chapter_number}`
- **输出 schema**: `{passed, severity, issues, suggestions, should_block_publish, evidence}`
- **挂载**: `editor.before_review`（替换 Editor 内的直接调用）
- **Publisher 保留直接调用**: Publisher node 和 API endpoint 继续直接调用 `evaluate_publish_continuity()`（Publisher 不走 `run_agent_skills`）

#### `chapter-seam` (validator)

- **来源**: `novel_factory/quality/chapter_seam.py` → `evaluate_chapter_seam()`
- **当前调用方**: Editor `_run_chapter_seam_check()`
- **提取方式**: 创建 `skills/chapter_seam_skill.py`
- **输入 schema**: `{content, project_id, chapter_number}`
- **输出 schema**: `{passed, severity, issues, suggestions, blocking_count}`
- **挂载**: `editor.before_review`

#### `death-penalty` (validator)

- **来源**: `novel_factory/validators/death_penalty.py` → `check_death_penalty_structured()`
- **当前调用方**: Editor, Author, Polisher, QualityHub（4 处）
- **提取方式**: 创建 `skills/death_penalty_skill.py`
- **输入 schema**: `{text}` 或 `{content}`
- **输出 schema**: `{has_critical, violations, score, issues}`
- **挂载**: `editor.before_review`, `author.after_llm`, `polisher.before_save`

#### `word-count-gate` (validator)

- **来源**: `novel_factory/validators/chapter_checker.py` → `check_word_count_quality_gate()` + `check_word_count_upper_gate()`
- **当前调用方**: Author, Polisher, Editor（3 处）
- **提取方式**: 创建 `skills/word_count_gate_skill.py`
- **输入 schema**: `{text, word_target, tolerance_ratio}`
- **输出 schema**: `{passed, word_count, target, lower_bound, upper_bound, issues}`
- **挂载**: `editor.before_review`, `author.after_llm`

#### `fact-lock` (validator)

- **来源**: `novel_factory/validators/fact_lock.py` → `check_fact_integrity()` + `extract_fact_lock()`
- **当前调用方**: Polisher `validate_output()`, QualityHub `check_polished()`
- **提取方式**: 创建 `skills/fact_lock_skill.py`
- **输入 schema**: `{original_text, polished_text, fact_lock_items}`
- **输出 schema**: `{passed, risk_level, changed_facts, issues}`
- **挂载**: `polisher.before_save`

### 3.2 Phase 2 — Extract Agent-Embedded Checks into Skills

以下检查当前嵌入在 Agent 代码中，需要提取为独立 Skill：

#### `revision-regression-check` (validator)

- **来源**: Author `_should_reject_revision_continuity_regression()` + `VersionRegressionGuard.should_reject_new_draft()`
- **合并**: 将两个检查合并为一个 Skill
- **输入 schema**: `{current_content, new_content, word_target, revision_issues, continuity_anchors}`
- **输出 schema**: `{should_reject, reason, regression_type}`
- **挂载**: `author.after_llm`（在生成修订稿后、保存前检查）

#### `scene-beat-coverage` (validator)

- **来源**: Author `_scene_beat_coverage_issues()` — 检查尾段是否覆盖 scene beat 和 ending hook
- **提取方式**: 创建 `skills/scene_beat_coverage_skill.py`
- **输入 schema**: `{content, scene_beats, ending_hook}`
- **输出 schema**: `{passed, coverage_ratio, missing_beats, issues}`
- **挂载**: `author.after_llm`

#### `title-quality` (validator)

- **来源**: Author `_is_usable_chapter_title()` + `_is_opening_derived_title()` + `continuity_gate._check_title()`
- **合并**: 将 Author 的标题验证和 continuity_gate 的标题检查合并
- **输入 schema**: `{title, content}`
- **输出 schema**: `{passed, issues, suggestions}`
- **挂载**: `editor.before_review`, `author.after_llm`

#### `beat-completeness` (validator)

- **来源**: Screenwriter `_self_check_wrap()` — 检查每个 beat 有 5 个必填字段
- **提取方式**: 创建 `skills/beat_completeness_skill.py`
- **输入 schema**: `{scene_beats}`
- **输出 schema**: `{passed, incomplete_beats, issues}`
- **挂载**: `screenwriter.after_llm`

### 3.3 Phase 3 — New Skills for Uncovered Gaps

#### `publish-readiness` (validator)

- **来源**: 新建，综合 Editor review 状态 + continuity gate + title check
- **输入 schema**: `{project_id, chapter_number}`
- **输出 schema**: `{ready, blockers, warnings}`
- **挂载**: 不挂载到任何 Agent（由 Publisher node 和 API endpoint 直接调用 `SkillRegistry.run_skill()`）
- **注意**: 此 Skill 调用其他 Skills（continuity-gate, title-quality），是组合型 Skill

#### `foreshadowing-debt` (validator)

- **来源**: `novel_factory/quality/chapter_inheritance.py` + `validators/plot_verifier.py`
- **输入 schema**: `{content, instruction, prev_state}`
- **输出 schema**: `{planted, resolved, debt, issues}`
- **挂载**: `planner.after_llm`, `editor.before_review`

## 4. Mounting Plan

### 4.1 Updated `skills.yaml` Agent-Skill Mounts

| Agent | Stage | Current Skills | New Skills |
|-------|-------|---------------|------------|
| `planner` | `after_llm` | `chapter-objective-checker` | + `foreshadowing-debt` |
| `screenwriter` | `after_llm` | `scene-conflict-checker` | + `beat-completeness` |
| `author` | `after_llm` | `event-coverage-checker` | + `death-penalty`, `word-count-gate`, `revision-regression-check`, `scene-beat-coverage`, `title-quality` |
| `polisher` | `after_llm` | `humanizer-zh` | *(不变)* |
| `polisher` | `before_save` | `ai-style-detector` | + `fact-lock`, `death-penalty` |
| `editor` | `before_review` | `ai-style-detector`, `narrative-quality`, `style-bible-checker`, `show-dont-tell`, `info-dump-detector`, `scene-texture`, `dialogue-naturalness` | + `continuity-gate`, `chapter-seam`, `death-penalty`, `word-count-gate`, `title-quality`, `foreshadowing-debt` |
| `memory_curator` | `after_extract` | `memory-patch-validator` | *(不变)* |
| `publisher` | — | *(无)* | *(不变 — Publisher 直接调用，不走 run_agent_skills)* |

### 4.2 Editor 调用路径变更

**Before (v6.7.9)**:
```
Editor._execute()
  → Step 4.6: self._run_continuity_gate()  # 直接调用
  → Step 4.5: self._run_chapter_seam_check()  # 直接调用
  → Step 5: self._apply_review_strategy()  # 内含 death_penalty, word_count
  → before_review: run_agent_skills()  # 7 个已注册 Skills
```

**After (v6.8.0)**:
```
Editor._execute()
  → before_review: run_agent_skills()  # 13 个 Skills（含 continuity-gate, chapter-seam, death-penalty, word-count-gate, title-quality, foreshadowing-debt）
  → Step 5: self._apply_review_strategy()  # 仅做编排决策，不再重复调用检查
```

Editor 代码变得更薄：`_run_continuity_gate()`、`_run_chapter_seam_check()` 等方法的**检查逻辑**迁入 Skill，Editor 仅从 `AgentSkillHookResult.validation_issues` 中读取结果并注入 `output.issues`。

## 5. Implementation Constraints

### 5.1 Skill Manifest Constraints（已有，不可违反）

```yaml
permissions:
  call_llm: false          # Skill 不能调用 LLM
  call_network: false      # Skill 不能发起网络请求
  write_chapter_content: false  # Skill 不能写正文
  update_chapter_status: false  # Skill 不能改状态
```

### 5.2 新增约束

- 每个 Skill 的 `run()` 必须是**纯函数**（相同输入 → 相同输出），不依赖外部状态
- Skill 可以读取 `payload` 中的数据，但不能访问 `repo`（数据库读取由调用方在 payload 中提供）
- Skill 返回的 `data` 必须包含 `issues: list[str]` 和 `suggestions: list[str]`（与现有 Skills 格式一致）
- blocking/warning 级别的判定逻辑保留在 Skill 内部，通过 `data.blocking: bool` 或 `data.severity: str` 暴露

### 5.3 向后兼容

- Phase 1 阶段，Editor 的 `_run_continuity_gate()` 方法**保留**但改为从 Skill 结果中读取（而非直接调用 `evaluate_chapter_continuity`）
- Publisher node 和 API endpoint **不改为走 run_agent_skills**（Publisher 没有 Agent 生命周期，直接调用 Skill 的 `run()` 方法）
- 现有 12 个 Skills 的行为不变

## 6. Testing Strategy

### 6.1 Skill 单元测试

每个新 Skill 新增独立测试文件：

| 测试文件 | 覆盖 |
|----------|------|
| `tests/test_skill_continuity_gate.py` | Skill 注册、payload 验证、blocking/warning/advisory 输出 |
| `tests/test_skill_chapter_seam.py` | Skill 注册、seam 断裂检测 |
| `tests/test_skill_death_penalty.py` | Skill 注册、critical violation 检测 |
| `tests/test_skill_word_count_gate.py` | Skill 注册、上下界检查 |
| `tests/test_skill_fact_lock.py` | Skill 注册、事实变更检测 |
| `tests/test_skill_revision_regression.py` | Skill 注册、返修回退检测 |
| `tests/test_skill_scene_beat_coverage.py` | Skill 注册、beat 覆盖率 |
| `tests/test_skill_title_quality.py` | Skill 注册、标题截断/脱节 |
| `tests/test_skill_beat_completeness.py` | Skill 注册、字段完整性 |
| `tests/test_skill_publish_readiness.py` | Skill 注册、综合阻断判定 |
| `tests/test_skill_foreshadowing_debt.py` | Skill 注册、伏笔债务检测 |

### 6.2 集成测试

- `tests/test_v680_skillized_quality_gates.py` — 验证 Skill 被正确挂载到 Agent、执行结果正确注入 review output
- 回归测试：`tests/test_agents.py`, `tests/test_v64_editor_quality_gates.py`, `tests/test_v679_continuity_gate.py`

### 6.3 回归验证命令

```bash
# Skill 单元测试
python3 -m pytest tests/test_skill_*.py -q

# 集成测试
python3 -m pytest tests/test_v680_skillized_quality_gates.py -q

# 回归测试
python3 -m pytest tests/test_agents.py tests/test_v64_editor_quality_gates.py tests/test_v679_continuity_gate.py -q

# 全量测试
python3 -m pytest -q

# 前端构建
cd frontend && npm run build
```

## 7. Phased Delivery

### Phase 1: Skill 骨架 + 注册（不改变主流程行为）

- 创建 5 个 Skill 类文件（continuity-gate, chapter-seam, death-penalty, word-count-gate, fact-lock）
- 注册到 `skills.yaml`
- 创建 manifest YAML
- 添加 `BUILTIN_SKILLS` 白名单
- 编写 Skill 单元测试
- **不改变** Editor/Author/Polisher 的调用路径

### Phase 2: Editor 集成（薄化 Editor）

- 将 `_run_continuity_gate()` 和 `_run_chapter_seam_check()` 的检查逻辑迁入 Skill
- Editor 改为从 `run_agent_skills()` 结果中读取 continuity/seam 检查结果
- 将 `_apply_review_strategy()` 中的 death-penalty 和 word-count 检查迁入 Skill
- 更新 `skills.yaml` 的 `agent_skills` 挂载
- 更新回归测试

### Phase 3: Author/Polisher/Screenwriter 集成

- 提取 `revision-regression-check`, `scene-beat-coverage`, `title-quality`, `beat-completeness` 为 Skills
- 薄化 Author/Polisher/Screenwriter 的内嵌检查
- 新增 `publish-readiness` 组合型 Skill

### Phase 4: 伏笔债务 + 配置化

- 实现 `foreshadowing-debt` Skill
- 支持按项目粒度启用/禁用 Skills（`project_overrides`）
- 更新角色配置 `default_capability_packs`

## 8. Acceptance Criteria

| # | 标准 | 验证方式 |
|---|------|----------|
| 1 | 每个新 Skill 有独立 manifest、class、test | `pytest tests/test_skill_*.py` |
| 2 | Skill 在 `skills.yaml` 中正确注册 | `SkillRegistry.validate_all().ok` |
| 3 | Skill 被正确挂载到 Agent/stage | `get_skills_for_agent()` 返回包含新 Skill |
| 4 | Skill `run()` 是纯函数（无 repo、无 LLM、无副作用） | 代码审查 |
| 5 | Editor 调用路径变薄（`_run_continuity_gate` 等方法不再直接调用 quality 模块） | 代码审查 |
| 6 | Publisher node 和 API endpoint 行为不变 | 集成测试 |
| 7 | 全量测试通过 | `pytest -q` |
| 8 | 前端构建通过 | `npm run build` |
| 9 | 所有逻辑通用、无硬编码 | `test_no_hardcoded_project_names` |

## 9. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Skill payload 缺少必要字段导致检查失败 | Medium | 在 Skill `run()` 中做 payload 验证，缺字段时返回 `{ok: False, error: "..."}` |
| Editor 薄化后 Skill 结果注入路径错误 | High | 保留原 `_run_continuity_gate()` 作为 fallback，Phase 2 先并行运行新旧路径对比结果 |
| Skill 执行顺序影响结果 | Low | 当前所有 Skill 是独立检查，无顺序依赖；`skills.yaml` 中的顺序仅影响执行顺序，不影响结果 |
| 性能问题（Skill 数量从 7 增到 13） | Low | 所有 Skill 是纯 regex/keyword 检查，单次执行 <10ms |
