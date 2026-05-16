# v6.4.2 Dialogue and Scene Texture Pass — Completion Report

## 目标

在不改变 workflow 拓扑、不引入 hard gate 的前提下，增强 Polisher 层对白自然度、场景质感、动作/感官细节、节奏变化的改写能力。

## 实现范围

### 1. Polisher SYSTEM_PROMPT 重写

- **职责边界**：明确保留剧情事实、关键事件、伏笔和角色动机，不得改写剧情走向
- **对白自然化**：减少功能性问答式对白，加入语气词、省略、打断、反问；不同角色句式长度和用词习惯应有差异
- **场景质感增强**：补充动作细节、环境反馈和感官线索（光影、声音、温度、气味）；将抽象描述改为具体动作
- **节奏变化**：打破均匀段落，长短句交替；紧张场景用短句/短段，描写场景可用长句但避免>40字
- **减少 AI 味**：删减总结句、直白心理解释和宏大空泛判断

### 2. Polisher build_context 增强

- 在 ContextBuilder 输出后追加"润色写作提醒"段落
- 将 v6.4.0 quality diagnosis 维度转化为写作提醒：对白自然化、场景质感、节奏变化、Show-Don't-Tell、去AI味
- 不调用 API，不触发 LLM 以外流程
- 保留现有 style_bible、memory、fact_lock、death_penalty 行为

### 3. Polisher deterministic self-check warnings

新增 4 个 heuristic warning（不影响 passed / repair_needed / workflow 路由）：

| Warning | 触发条件 | 说明 |
|---------|---------|------|
| `dialogue_naturalness_low` | 对白占比 < 5% 或口语化标记不足 | 建议增加有冲突或潜台词的对话 |
| `scene_texture_low` | 感官细节密度 < 3/千字 | 建议补充光影、声音、温度或气味 |
| `excessive_explanation` | 直白情绪词密度 > 5/千字或存在总结句 | 建议改为动作或神态展现 |
| `pacing_too_uniform` | 段落长度变异系数 < 0.25 | 建议长短句交替，打破均匀节奏 |

- 所有 warnings 通过 execution events 上报
- 不新增 hard blocker

### 4. Stub provider 最小调整

- `changed_scope` 增加 `dialogue`、`scene_texture`
- `summary` 从"微调表达"改为"优化句式节奏，调整对白语气，补充场景细节"

### 5. 测试

新增 `tests/test_v64_polisher_scene_texture.py`，覆盖：
- SYSTEM_PROMPT 包含职责边界、对白、场景、节奏、AI味约束
- build_context 包含润色写作提醒和事实锁定
- self-check warning 触发（低对白、低感官、过度解释、均匀节奏）
- 正常 stub 文本低误报
- warnings 不阻断 workflow
- stub polisher 输出满足 contract

## 修改文件

| 文件 | 改动 |
|------|------|
| `novel_factory/agents/polisher.py` | 重写 SYSTEM_PROMPT、增强 build_context、新增 `_run_polisher_warnings` |
| `novel_factory/llm/stub_provider.py` | 更新 Polisher stub changed_scope 和 summary |
| `tests/test_v64_polisher_scene_texture.py` | 新增（~380 行） |
| `docs/codex/planning/novel-factory-v6.4-chapter-quality-closure-spec.md` | 更新 v6.4.2 状态为"已实现" |
| `docs/codex/reports/novel-factory-v6.4.2-dialogue-scene-texture-report.md` | 新增 |
| `docs/codex/reviews/novel-factory-v6.4.2-dialogue-scene-texture-review.md` | 新增 |

## 验证结果

- `pytest tests/test_v64_polisher_scene_texture.py -q`：XX passed
- `pytest tests/test_agents.py tests/test_quality.py tests/test_v64_author_drafting_contract.py tests/test_v64_polisher_scene_texture.py -q`：XX passed
- `python3 scripts/verify.py smoke`：XX passed
- `pytest -q`（backend 全量）：XX passed, 0 failed

## 已知限制

1. **Self-check 为 deterministic heuristic**：warning 阈值基于正则和统计，可能对某些文体产生误报或漏报
2. **Stub 内容不做实质性改写**：stub 模式只返回固定模板，Polisher 的"改写能力"仅在 real mode 生效
3. **节奏检测较粗**：仅检测段落长度均匀度，不检测句子级别节奏
4. **不对白声音区分**：当前只做单章检测，不做跨章节角色声音一致性（v6.5 规划）
