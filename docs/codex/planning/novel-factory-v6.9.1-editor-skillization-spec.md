# v6.9.1 — Editor Skillization: From Hard-coded Checks to Configurable Skill Layers

**Status**: Planned
**Date**: 2026-06-06
**Previous**: v6.9.0 Creative Factory Capability Upgrade (editor_lenses reverted)

---

## 1. Problem Statement

v6.9.0 引入了 `editor_lenses` 作为独立 workflow 节点，意图将编辑审核从单体黑盒拆分为多维评审系统。该设计因以下原因被回退：

1. **绕过 Skill 系统**：7 个 Lens 是硬编码 Python 类，不走 `run_agent_skills`，无 `skill_runs` 审计
2. **无 LLM 深度**：Lens 实现为纯正则/启发式规则，评分虚高（"满分 100、一针见血"）
3. **架构孤岛**：自定义 `lens_reports` 表、自定义聚合逻辑、自定义 API，与现有 editor/skill 体系不互通
4. **workflow 膨胀**：新增 `editor_lenses` 节点导致 graph 边数增加，LangGraph 编译复杂度上升

回退后，editor 重新成为单一审核节点，但其内部仍有大量**硬编码检查项**：

| 硬编码位置 | 内容 | 问题 |
|---|---|---|
| `_run_advisory_quality_check()` | 写死 4 个 skill_id (`show-dont-tell`, `info-dump-detector`, `scene-texture`, `dialogue-naturalness`) | 增删维度需改代码 |
| `_run_before_review_skills()` | 对 `ai-style-detector` 做特殊分支解析 | 新 skill 无法自动接入 |
| `_run_continuity_gate()` | 直接调用 `evaluate_chapter_continuity()` | 不走 registry，无持久化 |
| `_run_chapter_seam_check()` | 直接调用 `evaluate_chapter_seam()` | 同上 |
| `death_penalty` 检查 | 直接调用 `check_death_penalty_structured()` | 同上 |

**根本矛盾**：editor 节点越来越厚，质量检查维度越来越多，但新增维度只能硬编码进 editor.py，无法通过配置驱动、无法复用 skill 体系的追踪和 failure policy。

---

## 2. Goal

将 editor 节点内的**所有确定性质量检查**下沉为 Skill，editor 只保留三层职责：

1. **LLM 评审**：五维评分 + issues/suggestions
2. **Skill 编排**：通过 `run_agent_skills` 运行所有挂载的检查 skill
3. **策略聚合**：`editor_strategy.py` 统一决策 pass/fail/revision_target

### Non-Goals

- **不把 LLM 评审本身拆成 skill** — LLM 五维评分仍是 editor 的核心职责，保持单次调用以保证连贯性
- **不新建 workflow 节点** — 不重复 v6.9.0 的 `editor_lenses` 弯路，所有检查在 editor 节点内部完成
- **不改动 editor_strategy 的决策框架** — 先 skill 化输入，再升级聚合逻辑（Phase 3）
- **不删除现有 quality/validators 模块** — 它们被 skill 封装后仍可独立使用

---

## 3. Design Overview

```text
editor_node
  ├─ Step 1: _call_editor_llm() → EditorOutput (五维评分)
  ├─ Step 2: _run_before_review_skills() → skill_runs 持久化
  │           ├─ death-penalty-skill
  │           ├─ continuity-gate-skill
  │           ├─ chapter-seam-skill
  │           ├─ word-count-gate-skill
  │           ├─ ai-style-detector
  │           └─ (future) commercial-viability-check, mystery-integrity-check, ...
  ├─ Step 3: _run_advisory_quality_check() → 纯建议性 findings
  │           ├─ show-dont-tell
  │           ├─ info-dump-detector
  │           ├─ scene-texture
  │           └─ dialogue-naturalness
  ├─ Step 4: _run_final_gate() → QualityHub final check
  └─ Step 5: _apply_review_strategy() → editor_strategy 统一决策
```

**Skill 输出统一 Schema**：

```python
{
  "passed": bool,
  "score": float | None,      # 可选，用于 Phase 3 加权
  "findings": [
    {
      "severity": "blocking" | "warning" | "info",
      "code": str,
      "message": str,
      "suggestion": str,
    }
  ],
  "summary": str,
}
```

---

## 4. Phase Breakdown

### Phase 1: 去硬编码 — editor 内部 Skill 调用配置化

**目标**：editor.py 不出现任何硬编码 skill_id，所有检查项通过 skill registry 配置驱动。

#### Step 1.1: 统一 Skill 输出解析
- 在 `novel_factory/skills/base.py` 或 `skill_hooks.py` 中新增 `parse_skill_findings(data: dict) -> list[SkillFinding]`
- `SkillFinding` dataclass：`severity`, `code`, `message`, `suggestion`
- editor.py 中所有 skill 结果解析统一走此函数，删除 `ai-style-detector` 特殊分支

#### Step 1.2: advisory skills 配置化
- 删除 `_run_advisory_quality_check()` 中的硬编码 `skill_ids` 列表
- 改为 `self.skill_registry.list_skills(agent="editor", stage="advisory")`
- 统一调用 `run_skill(skill_id, payload, agent="editor", stage="advisory")`
- 统一解析 findings，按 severity 排序，cap 到 3 条

#### Step 1.3: before_review skills 去特殊分支
- 删除 `_run_before_review_skills()` 中对 `ai-style-detector` 的 `if skill_id == ...` 分支
- 改为统一遍历 `before_review_hook.skill_results`，每个 result 调用 `parse_skill_findings()`
- blocking findings 自动注入 `output.issues`，warning/info 注入 `output.suggestions`

#### Step 1.4: continuity_gate / chapter_seam / death_penalty 包装为 skill
- `continuity_gate_skill.py` 已存在，完善其 `run()` 方法，确保输出符合统一 schema
- `chapter_seam_skill.py` 已存在，同上
- 新建 `death_penalty_skill.py`（或复用现有文件），封装 `check_death_penalty_structured()`
- 在 `skills/config.yaml` 中注册：`death-penalty` → `editor.before_review`

#### Step 1.5: editor.py 精简
- `_run_continuity_gate()` 和 `_run_chapter_seam_check()` 保留为兼容层，但内部改为调用对应 skill（或直接删除，由 before_review skills 覆盖）
- 确保 word_count_gate 同样走 skill（已有 `word_count_gate_skill.py`）

**验证清单**：
- [ ] `editor.py` 中搜索不到任何硬编码 skill_id（`show-dont-tell`、`info-dump-detector` 等）
- [ ] `python3 -m pytest tests/test_workflow.py tests/test_v516_langgraph_activation.py -q` 通过
- [ ] stub 模式下 editor 产出与回退前一致的 pass/fail 行为
- [ ] `skill_runs` 表中新增 `death-penalty`、`continuity-gate`、`chapter-seam` 记录

---

### Phase 2: 新增编辑专项 Skill

**目标**：将 v6.9.0 `editor_lenses` 的 7 个评审维度转化为可插拔 skill，按需启用。

#### Step 2.1: continuity-deep-check
- 基于现有 `continuity_gate_skill.py` 升级
- 增加 LLM 辅助层：当规则层 pass 时，调用轻量 LLM 检查"角色动机一致性""时间线隐性矛盾"
- 输出统一 schema
- 默认启用（`editor.before_review`）

#### Step 2.2: commercial-viability-check
- 新建 `novel_factory/skills/commercial_viability_checker.py`
- 检测维度：首章 3000 字钩子强度、付费点密度、追读吸引力、主角能动性
- 输入：`content`, `chapter_number`, `genre_contract`, `launch_profile`
- 规则层实现（可运行时加 LLM 层）
- 默认启用，failure_policy: warn

#### Step 2.3: pacing-profile-check
- 新建 `novel_factory/skills/pacing_profile_checker.py`
- 检测维度：段落长短分布、高潮位置、场景多样性、压力/奖励节奏
- 规则层：统计段落长度方差、对话/描写比例、场景切换次数
- 默认启用

#### Step 2.4: character-voice-check
- 新建 `novel_factory/skills/character_voice_checker.py`
- 检测维度：角色口吻一致性、动机合理性、工具人风险
- 输入：`content`, `characters`（来自 repo）
- 规则层：检测同一角色对话风格突变、角色是否长期未出场
- 默认启用

#### Step 2.5: mystery-integrity-check（默认关闭）
- 新建 `novel_factory/skills/mystery_integrity_checker.py`
- 检测维度：伏笔债务、揭示节奏、误导合理性、术语过载
- 仅在 `genre_contract.genre` ∈ (悬疑, 推理, 惊悚) 时由项目 override 启用
- failure_policy: warn

#### Step 2.6: style-bible-compliance 升级
- 现有 `style_bible_checker.py` 输出改为统一 schema
- 增加 `score` 字段：Style Bible 违规程度 0-100
- 挂载到 `editor.before_review`

#### Step 2.7: Skill manifest 注册
- 在 `skills/config.yaml` 中新增上述 skill 条目
- 每个条目声明：`agent`, `stage`, `enabled`, `failure_policy`, `project_override_key`

**验证清单**：
- [ ] 每个新 skill 在 stub 模式下产出有效统一 schema 输出
- [ ] `skill_registry.list_skills(agent="editor", stage="before_review")` 返回包含新 skill
- [ ] 悬疑项目 `mystery-integrity-check` 自动启用，其他 genre 不启用
- [ ] 所有新 skill 执行记录写入 `skill_runs` 表
- [ ] editor 评审结果包含新 skill 的 findings（在 issues/suggestions 中可见）

---

### Phase 3: 策略层聚合升级

**目标**：`editor_strategy.py` 从"只看 LLM 五维评分"升级为"LLM 评分 + 多 skill 结果聚合"。

#### Step 3.1: Skill 结果收集
- 在 `_apply_review_strategy()` 中，收集所有 before_review / advisory skill 的结果
- 构建 `skill_scores: dict[str, float]` 和 `skill_findings: list[dict]`
- 统计 `blocking_skill_count`（产生 blocking severity 的 skill 数量）

#### Step 3.2: Genre 加权配置
- `GenreContract` 中已有 `editor_weights` 字段
- 示例结构：
  ```json
  {
    "continuity": 1.2,
    "commercial": 1.5,
    "pacing": 1.0,
    "character": 1.0,
    "mystery": 1.8,
    "style": 1.0
  }
  ```
- 若 `editor_weights` 缺失，默认所有权重 1.0

#### Step 3.3: 加权评分计算
- 新增 `aggregate_skill_scores(skill_scores, editor_weights) -> float`
- 计算方式：`weighted_score = Σ(score × weight) / Σ(weight)`
- LLM 原始总分与加权 skill 分数取 min 或加权平均（待 Phase 3 评审决定，默认取 min 以保守通过）

#### Step 3.4: 策略规则更新
- 修改 `EditorPolicyInput`，新增字段：
  - `skill_weighted_score: float`
  - `blocking_skill_count: int`
  - `warning_skill_count: int`
- 修改 `classify_editor_result()` 规则：
  - `blocking_skill_count > 0` → 强制不通过（category: revision）
  - `skill_weighted_score < 70` → 不通过
  - `skill_weighted_score >= 85` 且无 blocking → 通过
  - `70-84` → advisory / revision 由 issue 严重程度和 retry_count 决定

#### Step 3.5: 向后兼容
- 若项目中无 skill 结果（旧数据或 skill 全禁用），`skill_weighted_score` 回退到 LLM 原始 `score`
- 确保测试覆盖"无 skill"和"有 skill"两种路径

**验证清单**：
- [ ] `editor_strategy.py` 单元测试覆盖加权评分路径
- [ ] blocking skill 强制不通过的场景测试通过
- [ ] 旧项目（无 editor_weights）评审行为不变
- [ ] `python3 -m pytest tests/test_workflow.py -q` 通过

---

### Phase 4: 动态 Skill 调度（可选）

**目标**：根据项目 genre、章节位置、历史表现自动决定启用哪些 skill。

#### Step 4.1: 动态启用规则
- 在 `editor_strategy.py` 或新增 `novel_factory/skills/editor_skill_resolver.py` 中实现：
  ```python
  def resolve_active_skills(
      project_id: str,
      chapter_number: int,
      genre_contract: dict,
      repo: Repository,
  ) -> list[str]
  ```
- 规则示例：
  - 首章 (`chapter_number == 1`) → 追加 `opening-hook-check`
  - 悬疑 genre → 追加 `mystery-integrity-check`
  - 连续 3 章某 skill 无 warning → 该 skill 降级为 sampling 模式（每 N 章运行一次）

#### Step 4.2: 采样模式
- Skill manifest 新增 `sampling_mode: bool` 和 `sampling_interval: int`
- 在 `_run_before_review_skills()` 中，根据 `repo` 中历史 `skill_runs` 决定是否跳过本次运行
- 跳过时不阻塞 workflow，直接返回 `passed=True, summary="sampling skip"`

**验证清单**：
- [ ] 首章自动启用 `opening-hook-check`
- [ ] 悬疑项目自动启用 `mystery-integrity-check`
- [ ] 连续通过的 skill 正确进入 sampling skip
- [ ] skip 记录不写入 `skill_runs`（或写入标记为 skipped）

---

## 5. Migration & Backward Compatibility

| 项 | 处理 |
|---|---|
| `editor_lens_reports` 表 | v6.9.0 已删除，不再恢复 |
| `reviews` 表 | 继续使用，editor 节点仍然调用 `repo.save_review()` |
| `skill_runs` 表 | 已有 schema 兼容，新增 skill 记录自动写入 |
| 旧 editor 行为 | Phase 1-3 均为渐进式升级，每一步保持向后兼容 |
| API `/editor-reports` | v6.9.0 已重写为返回 `reviews` 表数据，不再变更 |

---

## 6. Verification & Acceptance

### 6.1 测试矩阵

| 测试 | 覆盖 |
|---|---|
| `tests/test_workflow.py` | editor 节点路由、策略决策不变 |
| `tests/test_v516_langgraph_activation.py` | graph 编译通过 |
| `tests/test_v58_workflow_observability.py` | timeline 节点标签正确 |
| `tests/test_v690_e2e.py` | stub 模式端到端通过 |
| 新增 `tests/test_v691_editor_skillization.py` | Phase 1-3 的专项测试 |
| 新增 `tests/test_v691_skill_aggregation.py` | 加权评分、blocking 强制失败 |
| 新增 `tests/test_v691_skill_resolver.py` | 动态启用、采样 skip |

### 6.2 回归基线

- `python3 -m pytest -q`：保持 2600+ 测试全部通过
- `python3 -m pytest tests/test_v690_e2e.py -q`：14 passed
- 前端 `npm run typecheck` + `npm run build`：通过

---

## 7. Risks & Mitigations

| 风险 | 影响 | 缓解 |
|---|---|---|
| Skill 化后 editor 运行时间增加 | 每个 skill 串行运行，可能延迟 editor 节点 | Phase 1 保持串行，Phase 3 可评估并行（async skill 调用） |
| Skill 输出 schema 不统一 | 新 skill 开发者不遵循 schema，导致解析失败 | 在 `parse_skill_findings()` 中做 defensive 处理，非标准输出降级为 warning |
| 加权评分改变 pass/fail 分布 | 原本通过的章节因 skill blocking 失败 | Phase 3 默认 conservative：`blocking_skill_count > 0` 才强制失败，加权评分仅影响边缘案例 |
| genre_weights 配置缺失 | 新项目无 editor_weights | 默认权重 1.0，行为等价于无加权 |

---

## 8. Timeline

| Phase | 预估工作量 | 前置条件 |
|---|---|---|
| Phase 1 | 1 天 | 无 |
| Phase 2 | 2-3 天 | Phase 1 完成 |
| Phase 3 | 1-2 天 | Phase 2 完成 |
| Phase 4 | 1 天 | Phase 3 完成（可选） |

---

## 9. References

- `novel_factory/agents/editor.py` — editor 主实现
- `novel_factory/quality/editor_strategy.py` — 策略决策
- `novel_factory/agent_runtime/skill_hooks.py` — skill 运行时
- `novel_factory/agent_runtime/roles/editor.yaml` — editor 角色配置
- `novel_factory/skills/` — skill 目录
- `docs/codex/planning/novel-factory-v6.9.0-phase-plan.md` — v6.9.0 原规划（已回退）
- `docs/codex/planning/novel-factory-v6.8.0-skillized-quality-gates-spec.md` — v6.8.0 skill 化先例
