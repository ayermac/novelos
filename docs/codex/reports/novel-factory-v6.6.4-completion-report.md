# v6.6.4 Genesis Initialization Depth & Specificity Closure 完成报告

## 完成状态：CLOSED

## 目标回顾

修复 Novelos "新建项目初始化资料空泛"的系统问题。让创世阶段产出的项目资料足够支撑后续章节工作流，而不是只满足字段完整。

## 交付内容

### A. Genesis Prompt 深化

- 文件：`novel_factory/api/routes/genesis.py`
- `_generate_real_draft` prompt 新增深度要求：
  - 每章指令必须包含 `ending_hook`、`continuity_seed`
  - 角色必须有目标、矛盾、利益关系
  - 势力必须有资源/手段、阶段行动
  - 伏笔必须有触发场景、表象、真相方向、预计兑现章节
  - 大纲必须有阶段冲突、转折、阶段结果
- `_build_genesis_completion_prompt` 同步更新深度要求。

### B. Draft Normalization 扩展

- `_coerce_instruction`：支持 `ending_hook`、`continuity_seed`；`key_events` 数组规范化（用"；"连接）。
- `_coerce_character`：将 `goal`/`desire`/`conflict`/`secret`/`interest_relation` 合并到 `description`。
- `_coerce_named_item`（势力）：将 `resources`/`means`/`attitude`/`action` 合并到 `description`。
- `_coerce_plot_hole`：将 `trigger_scene`/`appearance`/`truth_direction`/`resolve_plan` 合并到 `description`。
- `_coerce_outline`：将 `stage_conflict`/`twist`/`stage_result` 合并到 `content`。
- `_apply_genesis_to_project`：将 `ending_hook`/`continuity_seed` 合并到 `key_events`/`emotion_tone`，避免审批后丢失。

### C. Genesis Quality Gate 加强

- 文件：`novel_factory/quality/genesis_quality_gate.py`
- 新增/加强检查：
  - `SHALLOW_INSTRUCTION` (blocker)
  - `ABSTRACT_OBJECTIVE` (blocker)
  - `MISSING_CONTINUITY_SEED` (warning)
  - `WEAK_KEY_EVENTS` (warning)
  - `SHALLOW_CHARACTER_MOTIVATION` (warning)
  - `SHALLOW_FACTION_ACTION` (warning)
  - `WEAK_PLOT_HOLE_DESIGN` (warning)
  - `OUTLINE_TOO_ABSTRACT` (blocker)
  - `CONSECUTIVE_OBJECTIVE` 扩展为检测同义模板（warning）
- 评分逻辑不变：blocker 导致 blocked，warning 数量 >=3 导致 warning。

### D. 前端体验

- 文件：`frontend/src/components/project/GenesisModule.tsx`
- 质量报告按 section 分组展示。
- blocker 显示行动建议（"重新生成或人工补全后再批准"）。
- warning/advisory 不禁用批准按钮，但显示风险。
- scaffold_fallback 继续禁用批准。
- UI 不开放 force apply 按钮。

### E. API 语义

- `latest` 重新计算 `quality_report`。
- `latest` 保留 `draft_json._meta.forced_quality_apply` 审计信息。
- 错误文案更新为"创世草案质量不足"。

### F. 测试

- 新增 `tests/test_v664_genesis_depth_quality.py`（13 个测试）。
- 更新 `tests/test_v663_genesis_quality_gate.py` 中的高质量草案数据以适应新深度标准。

## 测试结果

| 测试集 | 结果 |
|---|---|
| `tests/test_v663_genesis_quality_gate.py` | 18 passed |
| `tests/test_v664_genesis_depth_quality.py` | 13 passed |
| `tests/test_v532_project_genesis.py` | 11 passed |
| `tests/test_v63_creator_onboarding.py` | 6 passed |
| `tests/test_v553_autonomous_production_loop.py` | 39 passed |
| 后端全量 pytest | **2239 passed, 0 failed** |
| 前端 lint | passed |
| 前端 typecheck | passed |
| 前端 build | passed |
| `git diff --check` | passed |

## 文档更新

- 新增：`docs/codex/planning/novel-factory-v6.6.4-genesis-depth-specificity-closure-spec.md`
- 新增：`docs/codex/reports/novel-factory-v6.6.4-completion-report.md`
- 新增：`docs/codex/reviews/novel-factory-v6.6.4-review.md`
- 更新：`docs/codex/README.md`
- 更新：`README.md`
- 更新：`README.zh-CN.md`
