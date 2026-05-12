# v5.5.14 Release Stabilization

## 背景

v5.5.11-v5.5.13 已经把作者工作台、自动生产控制、宽屏 IA、状态文案和真实 LLM 护栏补齐。当前项目不再缺主功能，短期目标应从“继续扩功能”切换到“稳定收尾”：让作者能放心用它完成一本书，而不是被 stale run、obsolete session、重复 CTA、隐藏 token 消耗和状态矛盾打断。

本版本只做发布稳定化，不引入新的生产能力。

## 目标

1. 作者看到的生产状态必须有单一真相源。
2. 卡住、断线、过期、阻塞、待发布等状态必须能被一键处理或明确跳转。
3. 自动生产不能再表现为无人驾驶黑盒，而应是可预算、可停止、可恢复的批量执行器。
4. 用真实项目《绝世仙帝在都市》完成端到端验收，确保第 1-4 章生产路径不再出现状态矛盾。

## 范围

### 1. 状态真相源收口

统一优先级：

```text
chapter workflow run > chapter status > auto-run session > frontend local stream
```

要求：
- Overview、ChapterWorkspace、RunDetail、RunHealthPanel 使用同一组状态推导规则。
- auto-run session 只能解释“批量执行器状态”，不能覆盖章节 workflow 的真实状态。
- 旧断线 session 若目标章节已经 reviewed/published/blocking，必须自动过期，不再显示“重新接入”。

### 2. 项目健康修复入口

新增或收敛一个作者可理解的健康入口：

- 检测 stale running workflow run。
- 检测 obsolete disconnected auto-run session。
- 检测 running workflow 与章节状态不一致。
- 检测 pending memory updates 阻塞下一步。
- 提供明确动作：标记卡住、清理旧会话、跳转记忆收件箱、跳转待发布章节。

不要求自动修复所有问题；但不能让用户猜。

### 3. 自动生产收口

自动生产 UI 需要表达为“批量建议执行器”：

- 明确本次会处理的章节范围、最大步数和预算。
- 每一步显示目标章节和动作。
- 遇到待发布、记忆应用、阻塞、预算上限时停下，并告诉用户下一步。
- 不允许在目标章节已有 running workflow 时继续启动新生成。

### 4. 真实项目验收

以 `novel_3v2o`（《绝世仙帝在都市》）为验收项目：

- 第 1-2 章 published 不再显示旧阻塞/旧断线为主状态。
- 第 3 章 reviewed 时 Overview 主动作应指向记忆应用或发布前置步骤，而不是“重新接入”。
- 记忆应用完成后，第 3 章能清晰进入确认发布。
- 第 3 章发布后，第 4 章启动时 workflow 页面能立即显示真实运行状态。

## 非目标

- 不新增新的 LLM provider。
- 不新增多版本生成对比。
- 不重构所有前端数据获取。
- 不新增自动发布。
- 不扩大自动生产的无人值守能力。

## 验收标准

```bash
python3 -m pytest -q
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
cd frontend && npm run test -- --run
```

手工验收：

1. 打开 `/projects/novel_3v2o?module=overview`，主状态与 `production-next` 一致。
2. 打开第 3 章 workflow 页，不能再出现十几小时“润色中”的假 running。
3. 旧 auto-run session 不再显示为“连接已断开，可重新接入”。
4. 待发布章节有明确的发布入口。
5. 卡住运行有明确的处理入口。

