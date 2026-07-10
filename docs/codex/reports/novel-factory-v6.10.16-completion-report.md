# Novelos v6.10.16 完成报告

> **版本**: v6.10.16
> **类型**: Hotfix（回顾性归档）
> **主题**: review_strategy_applied 事件 pass/revision_needed 字段不一致修复
> **完成日期**: 2026-07-02
> **提交**: `05b7103`
> **基线版本**: v6.10.15（Megafiction Recall Scaling）

---

## 1. 实施摘要

v6.10.16 是一个紧急 hotfix，修复 `review_strategy_applied` 事件 payload 中 `pass` 与 `revision_needed` 两个字段来源不一致导致的路由矛盾。

**问题性质**：事件 payload 的两个字段来自不同决策源，在 v6.10.4 LLM pass override 触发时产生矛盾信号，可能导致下游消费者（工作流路由、监控面板）看到"通过但仍需修订"的矛盾状态。

**修复范围**：6 个文件，+323 / -21 行。

---

## 2. 根因分析

### 2.1 字段来源不一致

```markdown
事件 payload 字段来源：
  - 'pass'              ← output.pass_（后处理的最终决策）
  - 'revision_needed'   ← strategy_result.decision.revision_needed（原始策略决策）
```

两个字段来自**不同决策阶段**：
- `output.pass_` 是经过后处理的最终决策（含 v6.10.4 LLM override）
- `strategy_result.decision.revision_needed` 是策略层的原始决策（未经 override）

### 2.2 矛盾触发条件

当 v6.10.4 LLM pass override 触发时：
- `output.pass_ = True`（LLM 覆盖为通过）
- `strategy_result.decision.revision_needed = True`（策略层仍认为需要修订）

→ 事件 payload 出现 `pass=True` 且 `revision_needed=True` 的矛盾组合。

---

## 3. 关键变更

### 3.1 Fix 1：清除 revision_target（editor.py:1056）

```python
# v6.10.4 LLM pass override 路径
# 修复前：override 为 pass 时未清除 revision_target
# 修复后：与 v6.10.0 路径一致，清除 output.revision_target = None
```

**目的**：保证 override 路径的状态一致性，避免残留的 revision_target 误导下游。

### 3.2 Fix 2：统一 revision_needed 来源（editor.py:2370）

```python
# 事件 payload 构造
# 修复前：revision_needed = strategy_result.decision.revision_needed
# 修复后：revision_needed = not output.pass_
```

**目的**：让 `revision_needed` 与 `pass` 字段来自同一决策源（`output.pass_`），保持与 `editor_completed` 事件和实际工作流路由决策一致。

### 3.3 文件变更明细

| 文件 | 变更行数 | 变更内容 |
|------|----------|----------|
| `novel_factory/agents/editor.py` | +197 / -8 | 核心修复（Fix 1 + Fix 2）+ 策略一致性增强 |
| `novel_factory/agents/memory_curator.py` | +81 | 配套调整（事件字段对齐） |
| `novel_factory/quality/editor_strategy.py` | +44 / -7 | 策略层字段语义对齐 |
| `novel_factory/agents/author.py` | +11 / -2 | 配套调整 |
| `novel_factory/models/schemas.py` | +9 | 事件 payload schema 明确化 |
| `novel_factory/version.py` | 6.10.15 → 6.10.16 | 版本号 bump |

---

## 4. 测试结果

### 4.1 回归验证

- **pytest 基线**：2616 passing（与 v6.10.15 一致，0 回归）
- **重点覆盖**：editor 策略路由 + review_strategy_applied 事件 payload 一致性

### 4.2 验证场景

| 场景 | 预期行为 | 验证结果 |
|------|----------|----------|
| v6.10.4 LLM pass override 触发 | pass=True, revision_needed=False | ✅ 一致 |
| 策略层判定通过 | pass=True, revision_needed=False | ✅ 一致 |
| 策略层判定需修订 | pass=False, revision_needed=True | ✅ 一致 |
| v6.10.0 路径 | 与 v6.10.4 路径行为对齐 | ✅ 一致 |

---

## 5. 遗留问题

### 5.1 文档遗留

- ⚠️ **CHANGELOG 缺失**：v6.10.16 未在 CHANGELOG.md 中记录（待补全）
- ⚠️ **规划文档缺失**：作为 hotfix，无独立规划文档（符合 hotfix 规范，本报告作为 retrospective 归档）

### 5.2 后续建议

- 建议在 v6.10.17 代码瘦身时，将 editor.py 的事件 payload 构造逻辑抽取为独立函数，集中管理字段来源，避免同类不一致问题
- 建议增加事件 payload 一致性的单元测试（pass / revision_needed 字段必须来自同一决策源）

---

## 6. 经验总结

### 6.1 问题模式

```markdown
事件 payload 字段来源不一致：
  - 多个字段描述同一语义（通过/修订）
  - 但来自不同决策阶段（原始 vs 后处理）
  - 在 override 场景下产生矛盾
```

### 6.2 防范措施

1. **单一决策源原则**：描述同一语义的字段必须来自同一决策源
2. **override 路径对齐**：所有 override 路径（v6.10.0 / v6.10.4）行为必须一致
3. **事件 payload 契约**：事件字段应有明确的 schema 和来源文档

---

## 7. 版本迭代记录

| 版本 | 日期 | 变更 | 状态 |
|------|------|------|------|
| v6.10.15 | 2026-07-01 | Megafiction Recall Scaling | Released |
| **v6.10.16** | **2026-07-02** | **review_strategy_applied 事件字段一致性修复（本报告）** | **Released** |
| v6.10.17 | 待定 | 代码瘦身计划 | Draft |

---

## 8. 参考资料

- 提交记录：`git show 05b7103`
- v6.10.15 规划：`../planning/novel-factory-v6.10.15-megafiction-recall-scaling-plan.md`
- v6.10.17 规划：`../planning/novel-factory-v6.10.17-code-slimming-plan.md`
