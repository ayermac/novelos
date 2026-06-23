# Novel Factory v6.10.12 — 生产稳定性硬化计划

> 状态：规划阶段 | 基于 v6.10.11 story_facts 去重修复后的未决问题

---

## 问题总结（v6.10.11 暴露）

v6.10.11 已修复 story_facts 矛盾事实导致的 editor 误判问题，但 Chapter 21 仍暴露三个系统性缺陷：

1. **作者过度扩展** — 修订时字数连续膨胀（+1338、+1779、+2449），超出系统允许的扩展阈值却仍被生成
2. **核心循环漂移** — `state_delta:魂源`、`state_delta:统帅值` 在所有重试中均未被检测到，editor 无法确认状态变化
3. **事实账本历史包袱** — 数据库中存在大量过期事实仍标记为 `active`，需要清理和版本化管理

---

## 设计缺陷定位

| 层面 | 当前状态 | 问题 |
|------|----------|------|
| **Author** | 有修订长度回归检测，但只处理"变短"；对过度扩展仅警告和回退 | 过度扩展的内容被生成后回退，导致时间浪费和重试计数消耗 |
| **QualityGate** | 核心循环检查使用硬编码正则，模式严格 | 无法识别自然语言描述的状态变化，导致 `state_delta` 漏报 |
| **MemoryCurator** | 创建新事实但不失效旧事实 | 同一个 `subject.attribute` 存在多个 `active` 值，需要下游去重兜底 |

---

## v6.10.12 改进方案

### 目标

将 v6.10.11 的**下游去重兜底**升级为**上游控制 + 检测增强 + 数据治理**，从设计层面消除生产稳定性风险。

---

### 1. 作者过度扩展控制

#### 1.1 系统提示增强

```python
# novel_factory/agents/author.py 中的提示构建
AUTHOR_SYSTEM_PROMPT += """
【修订长度约束 v6.10.12】
1. 修订时严格控制篇幅：与上一版相比，字数增长不得超过 15%（约 {limit} 字）。
2. 如果 editor 未明确要求扩写，不要新增场景、支线或背景描写。
3. 仅针对被指出的问题做最小修改，保留其他已成立段落。
"""
```

#### 1.2 硬性字数上限检查（对称处理）

```python
# novel_factory/agents/author.py
# 在 _try_repair_revision_length_regression 旁边新增 _try_repair_revision_length_overexpansion

def _try_repair_revision_length_overexpansion(
    self, state, output, chapter, revision_review, fallback_context
):
    """Repair a revision candidate that grew too much."""
    if state.get("llm_mode") != "real":
        return None
    if self._revision_requests_compression(revision_review):
        return None

    chapter_number = state["chapter_number"]
    current_body = strip_chapter_heading(...).strip()
    candidate_body = strip_chapter_heading(...).strip()
    current_len = count_words(current_body)
    candidate_len = count_words(candidate_body)
    if current_len <= 0:
        return None

    expansion_limit = max(500, int(current_len * 0.15))
    expansion_tolerance = max(80, int(current_len * 0.03))
    if candidate_len - current_len <= expansion_limit + expansion_tolerance:
        return None

    # 调用压缩/合并，生成符合长度约束的修订稿
    maximum_len = current_len + expansion_limit
    ...
```

#### 1.3 修订长度强制约束

```python
# 在作者返回前进行硬校验
if overexpanded:
    # 不再仅返回错误，而是尝试自动修复
    repaired = self._try_repair_revision_length_overexpansion(...)
    if repaired:
        output = repaired
        overexpanded = False
```

---

### 2. 核心循环漂移检测增强

#### 2.1 扩展检测模式

```python
# novel_factory/quality/core_loop_checker.py
# 在 _extract_state_deltas 中补充自然语言模式

_EXTRA_STATE_DELTA_PATTERNS = [
    # 归零 / 清空 / 耗尽
    rf"{key}[^。\n，,；;]{{0,20}}(归零|清零|耗尽|见底|归零|归零|耗尽)",
    # 恢复 / 回升
    rf"{key}[^。\n，,；;]{{0,20}}(恢复|回升|上涨|增长)",
    # 失去 / 获得
    rf"(失去|获得|得到|失去).{{0,18}}{key}",
    # 所剩无几
    rf"{key}[^。\n，,；;]{{0,20}}(所剩无几|所剩无几|所剩无多|见底)",
]
```

#### 2.2 LLM 语义检测补充（可选）

```python
# 当 deterministic 检测未找到 state_delta 时，启用轻量 LLM 二次确认
if not evidence.state_deltas and previous_states:
    llm_evidence = _llm_detect_state_deltas(content, previous_states)
    evidence.state_deltas.extend(llm_evidence)
```

#### 2.3 作者提示明确要求数值变化

```python
AUTHOR_SYSTEM_PROMPT += """
【数值状态书写规范 v6.10.12】
当涉及数值型状态变化（如魂源、统帅值、积分、血量）时，必须明确写出：
"{属性名} 从 {旧值} 变为 {新值}"
例如："魂源 从 14.5 变为 0"、"统帅值 10/10 → 0/10"
"""
```

---

### 3. 事实账本版本管理与清理

#### 3.1 事实版本管理

```sql
-- 方案 A：使用 status 字段区分
-- 创建/更新事实时，将同 subject.attribute 的旧事实标记为 superseded
UPDATE story_facts
SET status = 'superseded'
WHERE project_id = ? AND subject = ? AND attribute = ? AND status = 'active'
  AND id != ?;
```

```python
# 方案 B：在 StoryFactRepositoryMixin 中添加 upsert 时失效旧事实
class StoryFactRepositoryMixin:
    def supersede_facts_by_subject_attribute(
        self, project_id: str, subject: str, attribute: str, keep_fact_id: str
    ) -> int:
        ...
```

#### 3.2 自动冲突检测

```python
# novel_factory/agents/memory_curator.py
# 在创建事实前检测同 subject.attribute 的冲突
existing_facts = self.repo.list_story_facts(
    project_id, status="active"
)
conflicting = [
    f for f in existing_facts
    if f.get("subject") == subject and f.get("attribute") == attribute
    and f.get("value_json") != value_json
]
if conflicting:
    # 标记旧事实为 superseded，并创建事件记录
    for old_fact in conflicting:
        self.repo.update_story_fact(old_fact["id"], {"status": "superseded"})
```

#### 3.3 清理工具

```python
# scripts/cleanup_story_facts.py
"""一次性清理指定项目的重复 story_facts。"""

def cleanup_duplicate_story_facts(repo, project_id: str) -> dict:
    facts = repo.list_story_facts(project_id)
    grouped = defaultdict(list)
    for fact in facts:
        key = f"{fact.get('subject', '')}.{fact.get('attribute', '')}" or fact.get("fact_key", "")
        grouped[key].append(fact)

    stats = {"superseded": 0, "kept": 0}
    for key, group in grouped.items():
        if len(group) <= 1:
            stats["kept"] += 1
            continue
        # 保留 source_chapter 最大的 active 事实
        latest = max(
            group,
            key=lambda f: int(f.get("source_chapter") or f.get("last_changed_chapter") or 0)
        )
        for fact in group:
            if fact["id"] != latest["id"] and fact.get("status") == "active":
                repo.update_story_fact(fact["id"], {"status": "superseded"})
                stats["superseded"] += 1
        stats["kept"] += 1
    return stats
```

---

## 验收标准

### 必须完成（MVP）

1. [ ] 作者系统提示中新增修订长度约束和数值状态书写规范
2. [ ] 新增 `_try_repair_revision_length_overexpansion` 并在过度扩展时自动触发
3. [ ] 核心循环检测模式扩展至 8 种以上自然语言表达
4. [ ] `memory_curator` 创建事实时自动失效同 subject.attribute 的旧 active 事实
5. [ ] 提供 `scripts/cleanup_story_facts.py` 清理工具

### 验证测试

1. [ ] 运行 `python3 -m pytest tests/test_v6107_core_loop_evidence.py -q` 全部通过
2. [ ] 新增测试：作者修订稿增长超过阈值时自动压缩
3. [ ] 新增测试：同 subject.attribute 的旧事实被正确标记为 superseded
4. [ ] 运行 `python3 -m pytest tests/ -q` 无新增失败（当前 27 个预存失败除外）

---

## 风险与延后项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 过度扩展自动压缩可能丢失有效内容 | 中 | 使用 LLM 合并而非简单截断，保留原稿作为底稿 |
| 核心循环模式扩展可能引入误报 | 中 | 先在测试集验证，再逐步放宽 |
| 事实版本化可能破坏旧查询 | 低 | 所有 story_facts 查询已使用 `status="active"` 过滤 |
| LLM 语义检测成本高 | 中 | 作为可选降级方案，默认关闭 |

**延后项（P2）**：
- 完整的事实版本管理 schema 重构（添加 `version` 字段）
- 跨项目的全局事实清理工具 UI
- LLM 语义检测作为生产默认开启项

---

## 实施顺序

1. **P0（第 1 周）**
   - 作者系统提示增强
   - 清理工具脚本
   - memory_curator 自动失效旧事实

2. **P1（第 2 周）**
   - 核心循环检测模式扩展
   - 作者过度扩展自动修复

3. **P2（第 3-4 周）**
   - LLM 语义检测可选开关
   - 事实版本管理 schema 升级
   - 完整回归测试与文档更新

---

## 版本号

基线：`6.10.11`（已提交 story_facts 去重修复）

目标：`6.10.12`

---

## 相关文档

- `docs/codex/planning/novel-factory-v6.10.9-core-loop-evidence-governance.md`
- `docs/codex/planning/novel-factory-v6.10.11-story-facts-dedup-fix.md`（如已创建）
- `docs/codex/reports/novel-factory-v6.10.11-completion-report.md`（待创建）
