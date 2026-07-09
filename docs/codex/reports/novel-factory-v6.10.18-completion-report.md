# Novelos v6.10.18 完成报告

> **版本**: v6.10.18
> **类型**: Refactoring（验证体系简化 Phase 1）
> **主题**: ChapterBrief 部分统一 + 字段弃用标记 + DB migration 039 + 文件合并 + Store 设计
> **完成日期**: 2026-07-08
> **基线版本**: v6.10.17（Code Slimming）
> **验证基线**: `pytest -q` -> **3749 passed, 1 skipped, 0 failed**

---

## 1. 实施摘要

v6.10.18 是验证体系简化的第一阶段，采用**渐进式弃用**策略：标记 deprecated + 保留兼容，不删除字段/列。包含 4 个 Phase：

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 1 | ChapterBrief 部分统一 + deprecated 标记 | ✅ |
| Phase A | DB migration 039（4 新列） | ✅ |
| Phase B | Quality/Validators 文件合并 | ✅ |
| Phase C | v6.10.19 Store 接口设计文档 | ✅ |

---

## 2. Phase 1: ChapterBrief 部分统一

### 2.1 新建权威扁平类
`novel_factory/models/chapter_brief.py`：
- **10 目标字段**：chapter_goal, conflict(NEW), ending_hook, emotion_tone(NEW), notes(NEW), forbidden_moves, required_beats(NEW), emotion_target, payoff_points(NEW)
- **v6.10.9 保留字段**：core_loop, dialogue_target_ratio, fact_locks
- **25 弃用兼容字段**：17 个 Tier1/2 字段 + 5 个 schemas 传统字段 + 3 个 drift/contract 字段
- `@model_validator(mode='after')` 对非默认值的弃用字段发出 `DeprecationWarning`

### 2.2 schemas.py re-export
- `CoreLoopDesign` 从 schemas.py 迁移到 chapter_brief.py（消除循环导入）
- `schemas.ChapterBrief` = re-export 新扁平类
- 扁平消费方（Planner/screenwriter/author/context_builder/API）零改动兼容

### 2.3 chapter_contracts.py deprecated
- 嵌套 `ChapterBrief`/`ChapterBriefTier1`/`ChapterBriefTier2` 保留（core_loop_checker + test_v690 零改动）
- 加 deprecated docstring + `@model_validator` 警告

### 2.4 类型冲突归一
- `new_debts_allowed`：schemas.py `bool=True` -> 统一为 `list[str]`
- `scene_count_target`：schemas.py 默认 3 -> 统一为 0

---

## 3. Phase A: DB Migration 039

### 3.1 新增列
`novel_factory/db/migrations/039_v6_10_18_chapter_brief_new_fields.sql`：
```sql
ALTER TABLE instructions ADD COLUMN conflict TEXT DEFAULT '';
ALTER TABLE instructions ADD COLUMN notes TEXT DEFAULT '';
ALTER TABLE instructions ADD COLUMN payoff_points TEXT DEFAULT '[]';
ALTER TABLE instructions ADD COLUMN required_beats TEXT DEFAULT '[]';
```
（`emotion_tone` 已存在于 base schema，无需 migration）

### 3.2 Repository 更新
`novel_factory/db/repositories/instruction.py`：
- `create_instruction()`：INSERT 加入 4 新列
- `update_instruction()`：可更新字段列表加入 4 新列

### 3.3 Migration registry
`novel_factory/db/migration_registry.py`：添加 039 条目（4 个 `_C` 列级要求）

---

## 4. Phase B: Quality/Validators 文件合并

采用"内容合并 + 原 shim 保留"策略（零破坏现有导入）。`chapter_inheritance` 的 `AgentContextBundle` 导入改为 `TYPE_CHECKING` 延迟导入以打破循环依赖。

### 4.1 Quality 合并（19 -> 16 文件）
| 源文件 | 目标 | 行数 |
|--------|------|------|
| concept_budget.py | hub.py | (删除) |
| deadloop_detector.py | hub.py | (删除) |
| issue_codes.py | hub.py | shim |
| style_detector.py | hub.py | shim |
| rhythm_budget_llm.py | rhythm_budget.py | (删除) |
| chapter_inheritance.py | continuity_gate.py | shim |
| version_regression_guard.py | chapter_brief_validator.py | shim |

合并后 hub.py 1306 行（含 4 个微文件内容）。

### 4.2 Validators 合并（10 -> 10 文件，内容集中）
| 源文件 | 目标 |
|--------|------|
| word_count_policy.py | chapter_checker.py |
| plot_verifier.py | chapter_checker.py |
| editorial_meta.py | revision_classifier.py |

所有源文件保留为 re-export shim。

---

## 5. Phase C: Store 接口设计

`docs/codex/design/v6.10.19-store-interface-spec.md`：
- 8 个 Store 聚合层设计（ProgressStore, DraftStore, WorldStore, SummaryStore, CharacterStore, OutlineStore, SignalStore, CheckpointStore）
- BaseStore 基类接口
- 性能基准测试方案
- 双轨迁移策略（Phase A/B/C 分批）

纯设计文档，无实现代码。

---

## 6. 验证结果

### 6.1 测试基线
```bash
$ python3 -m pytest -q
3749 passed, 1 skipped, 2394 warnings in 362.24s
```

### 6.2 导入验证
- `from novel_factory.models.chapter_brief import ChapterBrief, CoreLoopDesign` ✅
- `from novel_factory.models.schemas import ChapterBrief`（re-export）✅
- `from novel_factory.models.chapter_contracts import ChapterBrief`（嵌套，deprecated）✅
- `schemas.ChapterBrief is chapter_brief.ChapterBrief` ✅

### 6.3 版本同步
- `version.py`: 6.10.18
- `frontend/package.json` + `package-lock.json`: 6.10.18
- `desktop/package.json` + `package-lock.json`: 6.10.18

---

## 7. 提交列表

| 提交 | 内容 |
|------|------|
| `819c408` | Phase 1: ChapterBrief 部分统一 + deprecated 标记 |
| `31f02a6` | concept_budget -> hub.py |
| `f9b633b` | deadloop_detector -> hub.py |
| `1a032fa` | merge-deadloop 分支合并 |
| `1835e90` | Phase A: migration 039 + Phase C: Store 设计文档 |
| `da79c86` | rhythm_budget_llm 删除 + 其他文件合并 |

---

## 8. 已知遗留与后续

### 8.1 v6.10.18 未做（推迟到 v6.10.19/v6.11.0）
- **统一验证器**（ChapterBriefValidator 含插件扩展点）- 计划 §4.2 核心，未实现
- **前端表单同步**（隐藏 deprecated 字段，新增字段输入）- 未做
- **数据迁移脚本**（旧字段值合并到 notes/payoff_points）- migration 039 仅加列，未迁数据
- **限制 deprecated 字段写入**（v6.10.19 阶段 2）

### 8.2 v6.10.19 计划
- Store Facade 实现（Phase 2: ProgressStore/DraftStore/WorldStore）
- 嵌套 ChapterBrief 消费方迁移到扁平模型
- 限制 deprecated 字段写入

### 8.3 v6.11.0 计划
- 删除 deprecated 字段/列
- 删除嵌套 chapter_contracts.py 类
- 统一异常类型

---

## 9. 风险评估修订

基于阶段 0 审计发现，v6.10.18 实际风险**显著低于**原计划估计：

| 风险 | 原计划 | 实际 |
|------|--------|------|
| Skill 体系失效 | 高 | 极低（skills 零字段依赖） |
| 前端表单破坏 | 中 | 低（frontend 极低耦合） |
| 字段缺失影响功能 | 高 | 中（渐进式弃用 + 真实引用数据） |
| 文件合并破坏导入 | 中 | 低（shim + TYPE_CHECKING 解决循环依赖） |
