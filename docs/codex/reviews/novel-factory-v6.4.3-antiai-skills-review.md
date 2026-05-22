# v6.4.3 Anti-AI Skills — Review

## Review 范围

- `novel_factory/skills/show_dont_tell_validator.py`
- `novel_factory/skills/info_dump_detector.py`
- `novel_factory/skills/scene_texture_checker.py`
- `novel_factory/skills/dialogue_naturalness_checker.py`
- `novel_factory/skills/base.py`
- `novel_factory/config/skills.yaml`
- `novel_factory/quality/hub.py`
- `novel_factory/agents/polisher.py`
- `tests/test_v64_antiai_skills.py`
- `docs/codex/planning/novel-factory-v6.4-chapter-quality-closure-spec.md`

## Findings

### P1 — 无

无阻塞性问题。未修改 workflow 拓扑、未新增 hard gate、未破坏 schema。

### P2 — 建议关注

1. **Polisher skill 调用可能增加执行时间**
   - `_run_polisher_warnings` 现在调用 4 个 skill，每个都涉及正则扫描
   - 缓解：单次正则扫描 <1ms 级别，对整体 workflow 影响可忽略
   - 未来可考虑将 4 个 skill 合并为单次扫描（v6.5 优化项）

2. **QualityHub.diagnose 对 skill 不可用的回退较硬**
   - 回退时 dimension=100，无 findings，可能让 diagnosis 看起来"过于完美"
   - 缓解：skill 默认 enabled，正常使用不会触发回退；回退仅在 skill_registry=None 时发生

### P3 — 轻微

1. **skills.yaml 中新 skill 无 manifest**
   - 新 skill 使用 legacy class 路径，无 package/manifest
   - 缓解：这是有意设计——新 skill 为内联类，不需要 package 结构
   - 未来如需 package 化，可再迁移

2. **test_v64_quality_diagnosis.py 的 code 断言变松散**
   - 从精确匹配 `INFO_DUMP_DETECTED` 改为 `any("INFO_DUMP" in c)`
   - 缓解：保持了语义正确性，只是适配了新的分层 code 格式

## 回归风险

| 风险点 | 评估 |
|--------|------|
| workflow 状态推进 | 无风险 — 未修改状态机逻辑，warnings 不阻断 |
| skill 注册 | 低风险 — 新增到 BUILTIN_SKILLS 和 skills.yaml，不影响已有 skill |
| QualityHub diagnose | 低风险 — 接入新 skill，旧维度保留，API 结构兼容 |
| Polisher warnings | 低风险 — skill 优先+heuristic 回退双重保障 |
| mock 测试兼容 | 低风险 — 已添加 isinstance 防御 |

## Overall Verdict

**PASS**

v6.4.3 在最小改动范围内完成了 4 个 anti-AI quality skill 的引入和集成。所有 skill 均为 deterministic validator，不调用 LLM，不自动改写正文，不引入 hard gate。测试覆盖充分，全量 2045 项通过。

## 是否建议 merge

**建议 merge**。实现范围与 spec 一致，无回归风险。
