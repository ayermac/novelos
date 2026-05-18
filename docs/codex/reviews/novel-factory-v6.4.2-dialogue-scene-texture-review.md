# v6.4.2 Dialogue and Scene Texture Pass — Review

## Review 范围

- `novel_factory/agents/polisher.py`
- `novel_factory/llm/stub_provider.py`
- `tests/test_v64_polisher_scene_texture.py`
- `docs/codex/planning/novel-factory-v6.4-chapter-quality-closure-spec.md`

## Findings

### P1 — 无

无阻塞性问题。未修改 workflow 拓扑、未新增 hard gate、未破坏现有 schema。

### P2 — 建议关注

1. **Polisher self-check 与 Author self-check 部分重复**
   - `_run_polisher_warnings` 中的 `scene_texture_low`、`excessive_explanation` 与 Author v6.4.1 的 heuristic 有重叠
   - 缓解：这是有意设计。Author 负责初稿质量，Polisher 负责润色后质量。两层检测允许观察 Polisher 是否有效改善了问题
   - 如果未来阈值需要统一调整，建议将 sensory_words 和 straight_patterns 提取到共享模块

2. **对白口语化标记检测较简单**
   - 仅统计"啊/呢/吧/嘛/哦/呀/哈/哼/呸"等语气词出现频率
   - 缓解：v6.4.2 为 heuristic warning，精确度要求不高。v6.4.3 skill 层将引入更精确的 DialogueNaturalizer

### P3 — 轻微

1. **Stub provider changed_scope 增加字段不影响现有测试**
   - 测试 `test_polisher_polishes_content` 只断言 `content` 不为空和状态推进，不断言 `changed_scope` 内容
   - 确认通过

2. **Pydantic schema 未修改**
   - spec 中原本规划新增可选字段 `dialogue_quality`/`scene_texture`/`rhythm_score`
   - v6.4.2 实现中未修改 `PolisherOutput`，保持最小改动原则，推迟到后续版本评估必要性

## 回归风险

| 风险点 | 评估 |
|--------|------|
| workflow 状态推进 | 低风险 — 未修改状态机逻辑 |
| QualityHub check_polished | 无风险 — 未修改 QualityHub |
| Editor 审核 | 无风险 — 未修改 Editor |
| fact_lock 验证 | 无风险 — 未修改 fact_lock 逻辑 |
| 字数质量门 | 无风险 — 未修改 word gate |
| death_penalty | 无风险 — 未修改 death_penalty 规则 |

## Overall Verdict

**PASS**

v6.4.2 在最小改动范围内完成了 Polisher 层对白和场景质感的增强。所有新增内容均为 prompt 层和 heuristic warning，不引入 hard gate，不影响 workflow 路由。测试覆盖充分。

## 是否建议 merge

**建议 merge**。实现范围与 spec 一致，无回归风险。
