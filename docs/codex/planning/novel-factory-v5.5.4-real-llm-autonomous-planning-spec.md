# v5.5.4 Real LLM Autonomous Planning 规格

## 目标

把 v5.5.3 已打通的自主生产循环从 stub 闭环推进到 real LLM 可验收闭环，确保 `auto-fill` 和 `arc-plan` 在真实 LLM 模式下不会静默降级、不会覆盖或重复用户已有资料。

## 范围

### 一、Real LLM Provider 配置错误显式化

`llm_mode=real` 时，API 依赖层必须创建 OpenAI-compatible Provider。

验收要求：
- 如果缺少 API key，`get_llm_provider()` 抛出配置错误。
- `/api/projects/{project_id}/production/auto-fill` 返回 `LLM_CONFIG_MISSING`。
- `/api/projects/{project_id}/production/arc-plan` 返回 `LLM_CONFIG_MISSING`。
- 禁止在 real mode 缺 key 时返回 `StubLLM()`，避免把配置错误伪装成 LLM 空输出。

### 二、Auto-fill 只补缺失类型

real-mode `auto-fill` 必须根据当前项目资料计算 `missing_types`，写库阶段也必须按 `missing_types` 强制过滤。

验收要求：
- 已存在世界观时忽略 LLM 返回的 `world_settings`。
- 已存在角色时忽略 LLM 返回的 `characters`。
- 已存在大纲时忽略 LLM 返回的 `outlines`。
- 已存在伏笔时忽略 LLM 返回的 `plot_holes`。
- 仅对目标范围内缺失的章节指令写入 `instructions`。
- 对被忽略的非缺失类型返回 warning，不覆盖、不追加重复资料。

### 三、Arc-plan 章节范围幂等

real-mode `arc-plan` 必须对 arc outline 做 range-level 幂等保护。

验收要求：
- 如果 LLM 返回的新大纲 title 不同但 `chapters_range` 与已有大纲完全一致，跳过创建。
- 已存在章节指令的章节不重复创建指令。
- 已存在 code 的伏笔不重复创建。
- 对跳过的重复章节范围返回 warning。

### 四、结构化 LLM 输出

新增 autonomous planning 输出 schema：
- `AutoFillLLMOutput`
- `ArcPlanLLMOutput`
- `GeneratedWorldSetting`
- `GeneratedCharacter`
- `GeneratedOutline`
- `GeneratedPlotHole`
- `GeneratedInstruction`

real-mode autonomous planner 使用 `invoke_json(..., schema=...)` 获取结构化 JSON，并在写库前执行 Pydantic 校验。

## 主要代码路径

- `novel_factory/api/deps.py`
  - `LLMConfigMissingError`
  - `get_llm_provider()`
- `novel_factory/api/routes/production.py`
  - real-mode `auto-fill`
  - real-mode `arc-plan`
- `novel_factory/agents/autonomous_planner.py`
  - `execute_autofill()`
  - `execute_arc_plan()`
- `novel_factory/models/schemas.py`
  - autonomous planning 输出 schema

## 测试要求

新增测试文件：`tests/test_v554_real_llm_autonomous_planning.py`

必须覆盖：
1. real-mode auto-fill 缺 API key 返回 `LLM_CONFIG_MISSING`。
2. real-mode arc-plan 缺 API key 返回 `LLM_CONFIG_MISSING`。
3. auto-fill 在 LLM 返回所有类型时只写入实际缺失类型。
4. arc-plan 重复执行同一 `chapters_range` 时不重复创建大纲。
5. real-mode auto-fill mock LLM 成功路径。
6. real-mode arc-plan mock LLM 成功路径。
7. auto-fill 空 LLM 输出返回 `NO_CONTENT_CREATED`。
8. arc-plan 空 LLM 输出返回 `NO_CONTENT_CREATED`。
9. auto-fill 非 dict LLM 输出返回 `LLM_OUTPUT_INVALID`。

## 验证命令

```bash
python3 -m pytest tests/test_v554_real_llm_autonomous_planning.py -q
python3 -m pytest tests/test_v553_autonomous_production_loop.py -q
```

当前已验证：
- `tests/test_v554_real_llm_autonomous_planning.py`: 10 passed
- `tests/test_v553_autonomous_production_loop.py`: 20 passed
- 全量基线：1755/1755 passed

## 非目标

- 不改变 v5.5.3 stub 模式确定性生产闭环。
- 不引入自动发布；real mode 仍需要人工审核发布。
- 不实现跨 range overlap 的复杂合并策略；本期至少保证完全相同 `chapters_range` 幂等。
