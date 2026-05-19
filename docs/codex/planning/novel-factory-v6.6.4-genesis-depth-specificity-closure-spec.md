# v6.6.4 Genesis Initialization Depth & Specificity Closure 规格

## 目标

修复 Novelos "新建项目初始化资料空泛"的系统问题。让创世阶段产出的项目资料足够支撑后续章节工作流，而不是只满足字段完整。

核心原则：**阻止字段完整但内容空泛的初始化资料进入正式项目上下文**。

## 背景

v6.6.3 已加入 Genesis Quality Gate，能拦截重复章节指令、通用角色名、通用势力名、兜底模板草案，并在 force apply 时写入审计。但当前问题还没完全解决：Genesis 仍可能生成"完整但浅"的项目资料，例如章节指令虽然不完全重复，却只是换句话说；角色/势力/伏笔有字段但缺少可执行冲突；大纲只覆盖阶段，不足以支撑后续章节生产。

## 核心原则

1. 不针对某一本书硬编码。
2. 不放宽质量门来让测试通过。
3. 不把 scaffold fallback 伪装成真实高质量草案。
4. 不新增 LangGraph 主工作流节点。
5. 优先修 Genesis prompt、草案规范化、质量门、前端验收体验和测试覆盖。
6. 所有改动必须有自动化测试。

## 实施范围

### A. Genesis Prompt 深化

修改 `novel_factory/api/routes/genesis.py` 中真实 LLM 创世 prompt，新增深度要求：

- **每章 instructions 必须包含**：
  - `chapter_number`
  - `objective`：具体到本章的主角目标、阻力、结果变化
  - `key_events`：至少 3 个具体事件，不能只有"冲突升级/主角成长/势力入场"
  - `emotion_tone`
  - `ending_hook`：本章结尾钩子
  - `continuity_seed`：给下一章必须继承的悬念/时间/任务
  - `word_target`
- **相邻章节** `objective`/`key_events` 不得复用同一抽象目标。
- **角色**必须包含：具体姓名、角色功能、当前欲望/目标、内在矛盾或秘密、与主角的利益关系。
- **势力**必须包含：具体名称、资源/手段、对主角的态度、当前阶段会采取的行动。
- **伏笔**必须包含：触发场景、读者看到的表象、真相方向、预计推进/兑现章节。
- **大纲**不能只写"前期/中期/高潮"，必须写出阶段冲突、转折、阶段结果。

### B. Draft Normalization 扩展

增强 `_coerce_instruction` / `_normalize_genesis_draft`：

- 支持 `ending_hook`、`continuity_seed` 字段。
- 如果 LLM 返回 `key_events` 为数组，规范化为可读字符串或结构化 JSON 字符串，但不能丢信息。
- 如果 LLM 返回角色/势力/伏笔额外字段，保留在 `draft_json` 中，但写入正式表时至少把关键信息合并到 `description`/`content` 中，避免审批后信息丢失。
- 确保 approved genesis 写入 instructions 时，`ending_hook`/`continuity_seed` 不会完全丢失，可合并进 `key_events` 或 `emotion_tone` 后缀，直到数据库 schema 支持新字段。

### C. Genesis Quality Gate 加强

修改 `novel_factory/quality/genesis_quality_gate.py`，新增或加强以下检查：

| Code | Severity | 说明 |
|---|---|---|
| `SHALLOW_INSTRUCTION` | blocker | 章节指令缺少具体人物、地点、行动、结果变化 |
| `ABSTRACT_OBJECTIVE` | blocker | objective 只有"扩大冲突/推动剧情/获得主动权/进入复杂局面"等抽象表达 |
| `MISSING_CONTINUITY_SEED` | warning | 多章规划中缺少 ending_hook 或 continuity_seed |
| `WEAK_KEY_EVENTS` | warning | key_events 少于 2-3 个可区分事件 |
| `SHALLOW_CHARACTER_MOTIVATION` | warning | 角色缺少目标、矛盾、秘密、利益关系 |
| `SHALLOW_FACTION_ACTION` | warning | 势力缺少资源、手段或阶段行动 |
| `WEAK_PLOT_HOLE_DESIGN` | warning | 伏笔缺少触发场景、表象、真相方向或预计兑现章节 |
| `OUTLINE_TOO_ABSTRACT` | blocker | 大纲只有阶段标签，没有阶段冲突、转折、结果 |
| `CONSECUTIVE_OBJECTIVE` | warning | 相邻章节 objective 高度相似（同义模板） |

质量门语义分层：
- **blocker**：会导致后续章节无法生产或高度模板化的问题。
- **warning**：需要人工注意但不一定阻止。
- **advisory**：提示优化。
- **scaffold_fallback**：系统兜底草案，不建议直接批准。

### D. 前端体验

修改 `frontend/src/components/project/GenesisModule.tsx`：

- 质量报告按 section 分组展示：章节指令、角色、势力、大纲、伏笔/悬念、系统兜底。
- 对 blocker 显示明确行动建议："重新生成"或"人工补全后再批准"。
- 对 warning/advisory 不禁用批准按钮，但显示风险。
- 对 scaffold_fallback 继续禁用批准。
- 如果 blocked 但用户确实要强制应用，暂时不在 UI 开 force apply 按钮，保持后端能力即可。

### E. API 语义

保持：
- generate response 包含 `quality_report`。
- latest response 包含 `quality_report`。
- approve 时 quality_report 未通过则阻塞。
- `force_apply + confirm_quality_risk` 可强制应用，并持久化审计到 `draft_json._meta`。

补充：
- `latest` 返回的 `quality_report` 应基于当前 `draft_json` 重新计算。
- 如果 `draft_json` 中已有 `forced_quality_apply` 审计，`latest` 也应保留 `_meta`，不要覆盖。
- 错误文案明确是"创世草案质量不足"，不要误导成"项目资料缺失"。

### F. 测试要求

新增 `tests/test_v664_genesis_depth_quality.py`，覆盖：

1. 高质量 fantasy/urban/supernatural 创世草案能通过。
2. 完整但空泛的草案会被 `SHALLOW_INSTRUCTION` 或 `ABSTRACT_OBJECTIVE` 拦截。
3. 相邻章节同义但不完全相同的模板指令会被识别（`CONSECUTIVE_OBJECTIVE`）。
4. 缺 `ending_hook`/`continuity_seed` 的多章规划会 warning 或 blocker。
5. `key_events` 数组规范化不丢信息。
6. 角色缺目标/矛盾/利益关系会被标记。
7. 势力缺资源/行动会被标记。
8. 伏笔缺触发/表象/真相/兑现计划会被标记。
9. `latest` 重新返回 `quality_report`。
10. `force apply` 审计仍然持久化。
11. 现有 v6.6.3 测试继续通过。
12. 不破坏 production-next / run guard / onboarding 相关测试。

## 验证命令

```bash
python3 -m pytest tests/test_v663_genesis_quality_gate.py tests/test_v664_genesis_depth_quality.py -q
python3 -m pytest tests/test_v532_project_genesis.py tests/test_v63_creator_onboarding.py tests/test_v553_autonomous_production_loop.py -q
python3 -m pytest -q
cd frontend && npm run lint && npm run typecheck && npm run build
git diff --check
```

## 完成标准

1. 新项目初始化不再允许"字段齐全但内容模板化"的草案直接批准。
2. 章节指令必须逐章具体，能支撑 Planner/Screenwriter/Author 后续生产。
3. 角色、势力、伏笔、大纲必须具备可执行冲突信息。
4. UI 能清楚告诉用户为什么草案不能批准。
5. 全量测试通过后再提交。
