# v6.4.4 Editor Quality Gates & Tests Review

## 审查范围

- `novel_factory/agents/editor.py`：SYSTEM_PROMPT 增强、`_run_advisory_quality_check`、`_fallback_rule_review` 接入
- `tests/test_v64_editor_quality_gates.py`：21 个新增测试
- `docs/codex/planning/novel-factory-v6.4-chapter-quality-closure-spec.md`：v6.4.4 状态更新
- `docs/codex/reports/novel-factory-v6.4.4-editor-quality-gates-report.md`

## Findings

### P2 — `_run_advisory_quality_check` severity 过滤可能丢弃有用 info

```python
all_findings = [
    f for f in findings
    if any(f.get("code", "").startswith(p) for p in v64_prefixes)
    and f.get("severity") in ("warning", "medium", "high", "critical")
]
```

`info` severity 的 findings（如 `SUMMARY_SENTENCE`）被完全过滤。对于某些项目，总结句检测可能是有价值的 advisory signal。当前上限 3 条已经防止了噪音，过滤 info 可能过于严格。

**缓解**：当前行为可接受。info-level findings 数量较多且价值较低，v6.4.4 的保守策略优先避免 review 噪音。如需更细粒度，可在 v6.5 引入配置开关。

### P2 — `_fallback_rule_review` 中 advisory suggestions 仅在 passed 时返回

```python
suggestions=(advisory_suggestions if passed
             else (["请人工检查正文后再继续。"] + advisory_suggestions)),
```

fallback fail 时，advisory suggestions 被追加在通用建议之后。但如果 fail 原因是 death_penalty critical，advisory suggestions（如"补充感官细节"）可能与当前问题无关。

**缓解**：这不是 bug。fallback fail 通常意味着需要人工介入，advisory suggestions 作为额外参考信息无害。

### P3 — 未测试 `info` severity findings 被过滤的行为

测试 `test_good_text_low_false_positives` 断言 advisory_count <= 3，但没有直接验证 info-level findings 确实被过滤。

**缓解**：行为正确，测试覆盖通过 severity 排序和上限间接验证。

## 逐项核查

| 检查项 | 结论 | 说明 |
|---|---|---|
| SYSTEM_PROMPT 包含 v6.4 维度 | ✅ | AI 痕迹/叙事质感/节奏控制/设定展现/对白人物化 |
| SYSTEM_PROMPT 包含"不直接改写正文" | ✅ | 明确写入 prompt |
| `_run_advisory_quality_check` 调用 4 skills | ✅ | show-dont-tell, info-dump, scene-texture, dialogue-naturalness |
| findings 映射为 `[v6.4质量信号] code: message` | ✅ | 格式统一 |
| suggestions 映射为 `[code] suggestion` | ✅ | 格式统一 |
| 上限 3 条 | ✅ | `capped = all_findings[:3]` |
| 不改变 pass/fail/score | ✅ | 只追加 issues/suggestions |
| 不调用额外 LLM | ✅ | 仅调用 deterministic skills |
| fallback 也接入 advisory | ✅ | `_fallback_rule_review` 调用同一方法 |
| 无 schema 改动 | ✅ | EditorOutput 未修改 |
| 无 workflow 拓扑改动 | ✅ | 不修改 nodes.py / graph.py |
| 测试覆盖 prompt/单元/集成/路由 | ✅ | 21 个测试 |
| evidence 限长 | ✅ | skill 层已限制，映射后 issue 字符串 < 500 |
| 全量测试通过 | ✅ | 2069 passed |

## Overall Verdict

**PASS**

v6.4.4 完成了 Editor 阶段的 advisory quality gates。架构干净：advisory check 与已有 gate（death_penalty, before_review hooks, final_gate, word gate）完全解耦，只追加不覆盖。测试覆盖充分，2069 项全量通过。

## 是否可以进入下一版本

**可以进入。**

v6.4 系列（v6.4.0 ~ v6.4.4）已完成：
- v6.4.0 QualityHub diagnose 基线
- v6.4.1 Author prompt / drafting contract
- v6.4.2 Polisher 对白和场景质感 pass
- v6.4.3 Anti-AI skills（4 个 deterministic validator）
- v6.4.4 Editor advisory quality gates

 Editor 现在能使用所有 anti-AI skill 信号作为 advisory review 证据，不阻断 workflow，不自动改写。为 v6.5 的"跨章一致性"提供了稳定的单章质量检测基础设施。
