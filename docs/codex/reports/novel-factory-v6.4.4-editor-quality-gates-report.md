# v6.4.4 Editor Quality Gates & Tests 报告

## 目标

让 Editor 阶段使用 v6.4.0-6.4.3 的质量诊断/anti-AI skill 信号，输出更明确的章节质量评审和修订建议。不改变 workflow 拓扑，不新增 hard blocker，不自动重写正文。

## 改动摘要

### 1. Editor SYSTEM_PROMPT 增强

- 新增"文字质量子维度"段落：
  - AI 痕迹：无模板句式、无直白情绪词、无机械解释
  - 叙事质感：感官细节充足、动作描写具体、对白自然
  - 节奏控制：段落长短有变化、紧张场景用短句/短段
  - 设定展现：无旁白式 info dump、设定通过动作/对话展现
  - 对白人物化：对白有角色目的、潜台词或冲突
- 新增"评审原则"：只评审和给修订建议，**不直接改写正文**
- 新增 revision_target 规则：info dump / 直白情绪 → "author"；文风/对白/场景 → "polisher"

### 2. Editor `_run_advisory_quality_check` 新增

- 直接调用 4 个 deterministic anti-AI skills：
  - `show-dont-tell`
  - `info-dump-detector`
  - `scene-texture`
  - `dialogue-naturalness`
- 将 findings 映射为 `[v6.4质量信号] {code}: {message}` 格式
- suggestions 映射为 `[{code}] {suggestion}` 格式
- 按 severity 排序，上限 3 条，避免 review 噪音爆炸
- **只追加到 issues/suggestions，不改变 pass/fail/score/revision_target**
- 不调用额外 LLM

### 3. Editor `_fallback_rule_review` 增强

- fallback 评分也调用 `_run_advisory_quality_check`
- 使 LLM 降级审核仍有质量信号覆盖

### 4. 新增测试

- `tests/test_v64_editor_quality_gates.py`：21 个测试
  - Prompt contract（7 个）
  - Advisory 单元测试（7 个）
  - Integration 测试（4 个）
  - Routing 不变性测试（3 个）

## 验证结果

| 测试 | 结果 |
|------|------|
| `pytest tests/test_v64_editor_quality_gates.py -q` | **21 passed** |
| `pytest tests/test_v64_quality_diagnosis.py tests/test_v64_antiai_skills.py tests/test_v64_polisher_scene_texture.py tests/test_v64_author_drafting_contract.py tests/test_v64_editor_quality_gates.py -q` | **89 passed** |
| `python3 scripts/verify.py smoke` | **通过** |
| `pytest -q`（backend 全量） | **2069 passed, 0 failed** |

## 已知限制

1. **Advisory issues 上限 3 条**：如果 4 个 skill 都产生多个 findings，只会取前 3 条最高 severity 的。低 severity 的 info-level findings 可能被丢弃。
2. **未挂载到 skill hooks**：advisory check 由 Editor 直接调用，不通过 `run_agent_skills` 管道。因此不占用 agent stage 执行时间，但也不受 skills.yaml 的 stage/agent 配置控制。
3. **Deterministic heuristic 精度**：与 v6.4.3 相同，基于正则和统计，对特定文体可能有误报/漏报。
4. **不影响 Editor 已有评分逻辑**：advisory issues 不改变 LLM 返回的 pass_/score，但已有的 before_review hooks（ai-style-detector, narrative-quality）和 final_gate 仍可能根据内容质量修改 score 和 pass 状态。advisory check 与这些机制独立运行。

## 是否可进入下一版本

**可以进入。**

v6.4.4 完成了 Editor 阶段的 advisory quality gates，为 v6.4 系列画上了闭环。所有 4 个 anti-AI skill 的信号已被 Editor 复用，且通过测试验证不阻断 workflow。2069 项全量测试通过。
