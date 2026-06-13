# Novel Factory v6.10.7 Core Loop Evidence Governance Plan

## 背景

v6.10.5 已引入 Story Contract、核心循环提示注入和 `core_loop_compliance` 质量检查，但实际验证《全民觉醒：你管这叫召唤师？》前三章发现：第 3 章只有“噬源解锁”和追踪反制，没有明确完成召唤军团爽点兑现与魂源数值继承，现有 checker 仍判定 `score=100/pass=True`。

根因不是单一 LLM 输出能力，而是系统约束仍停留在“提示治理”：

- 泛关键词命中会误判“核心兑现已存在”。
- ChapterBrief 声明 payoff 后，未核验正文证据。
- `core_loop_steps_completed=[]` 不影响通过。
- 数值状态变化未进入核心循环门禁。
- 前端缺少可读诊断，用户只能看到章节过/不过，看不到缺哪类兑现。

## 目标

将 v6.10.5 的 Story Contract 从“提醒系统”升级为“证据治理系统”：

1. Author/Screenwriter/Editor 继续接收 Story Contract，但质量门必须验证正文证据。
2. 每章核心循环至少形成可解释诊断：奖励获得、奖励使用、状态变化、外部反噬。
3. 数值/能力类状态变化进入 contract metrics，后续章节可继承。
4. 质量门不因泛关键词误判通过；缺关键证据时至少 priority，已确认合同可升级阻断。
5. 前端展示核心循环诊断，让用户知道“缺了什么”。

## 范围

### P0：后端证据化校验

- 扩展 `ChapterContractMetrics`：记录 `evidence_spans`、`state_deltas`、`missing_evidence`、`reward_acquired`、`reward_used`、`enemy_consequence`。
- 修改 `core_loop_checker`：
  - 不再把 `brief.reader_payoff` / `primary_payoff` 直接作为通过依据。
  - 泛关键词只作为候选，不作为最终通过。
  - 对 reward/power/召唤类合同执行正文证据检查。
  - 检测“解锁/获得但未使用/未兑现”。
  - 检测数值锚点有旧值但无新值变化。
- 修改 `quality_gate_node`：
  - 核心循环缺证据进入 priority。
  - `active/confirmed` Story Contract 下关键证据缺失可阻断。
- 增加回归用例：前三章中的第 3 章应被识别为“解锁未兑现/魂源变化缺失”。

### P1：可视化诊断与人工可理解性

- 在 workflow timeline / run detail 已有 `quality_gate.diagnostics` 基础上，前端展示核心循环诊断摘要。
- 展示：是否完成核心兑现、缺失证据、状态变化、建议补写方向。
- 暂不做复杂人工编辑器；人工修正状态账本留到后续版本，避免引入新工作流入口风险。

## 非目标

- 不重新设计创世流程。
- 不新增 LLM 调用作为硬依赖。
- 不把所有类型小说都强行套“签到”模板。
- 不在本版本做完整状态账本 UI 编辑器。

## 验收标准

- `core_loop_checker` 不再因泛关键词导致第 3 章误判 `100/pass`。
- 获得/解锁能力但没有正文使用证据时，诊断明确输出 `reward_used=false` / `missing_evidence`。
- `魂源：14.5` 后续章节只有消耗/吞噬但无新数值时，诊断输出数值继承缺失。
- 已确认合同下，关键核心兑现缺失能进入 `blocking_issues` 或明确 priority，返修目标为 author。
- 前端章节工作台能看到核心循环诊断摘要。
- 相关后端测试和前端 typecheck 通过。
