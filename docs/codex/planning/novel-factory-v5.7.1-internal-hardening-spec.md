# Novelos v5.7.1 内部构建完整与稳定规格

## 状态

- 类型：可执行规划规格
- 状态：completed
- 基线：v5.7 Daily Writing Editing and Versioning
- 产品目标：把现有个人作者工作台压实到“自己每天可用、可恢复、可验证”的内部稳定状态
- 技术目标：完成真实项目验收、修复真实数据路径问题、统一验证入口和文档基线，为 v5.8 工作流可观测增强做准备
- 完成日期：2026-05-14
- 最终验证：`python3 scripts/verify.py full` 通过，pytest `1866 passed`，vitest `125 passed`，frontend typecheck/lint/build passed

## 背景

v5.5.15 完成了生产稳定性闭环，v5.6/v5.6.1 完成了 Author Workbench 的工作台与交互稳定化，v5.7 完成了正文编辑、版本、对比、回滚和局部返修的最小创作者闭环。

当前项目已经具备继续扩展的基础，但还不适合立刻进入新功能堆叠。下一段时间应先做内部构建完整和稳定：

- 用真实项目 `novel_3v2o` 验证当前链路，而不是只相信测试夹具；
- 清理历史运行状态污染和页面展示矛盾；
- 确认编辑、保存、版本、回滚、导出、局部返修都能在真实数据上跑通；
- 让验证脚本、文档状态、测试基线和开发节奏一致；
- 明确 v5.8 之前不再做大范围 UI 重构或企业化能力。

## 产品定位

v5.7.1 是内部稳定版本，不是新功能版本。

```text
已有能力真实可用 > 新功能扩张
```

它的目标是让 Novelos 从“功能已经实现”进入“系统可以持续迭代”的状态。

## 非目标

- 不做多租户、组织、RBAC、计费或企业后台。
- 不做 Creator Knowledge Base / RAG。
- 不做完整长篇记忆治理。
- 不重写 LangGraph 主生产链路。
- 不再次大规模重构 WebUI 视觉。
- 不引入大型富文本编辑器。
- 不做 DOCX/EPUB 导出。
- 不做 v5.8 的节点日志、AgentOps replay 和运行复盘完整能力。

## 核心原则

1. 真实项目验收优先于新增功能。
2. 所有恢复入口必须能解释“当前是什么状态、为什么这样、下一步做什么”。
3. 测试要分层，日常反馈要快，稳定基线才跑 full。
4. 文档只记录当前真实状态，不能让完成版本继续显示 planned。
5. 修复要小而准，避免把稳定化阶段变成新一轮重构。

## 范围一：真实项目验收

使用 `novel_3v2o` 作为真实验收项目。

### 验收清单

1. 打开项目工作台，默认进入作者工作台而不是旧 overview。
2. 打开第 4 章，确认当前章节状态、工作流状态和右侧 AI 助手状态一致。
3. 如果存在 stale running / blocked 历史运行，页面必须给出清晰恢复入口。
4. 对已发布章节验证默认只读。
5. 对可编辑章节进入编辑模式，修改一小段并保存。
6. 保存后版本列表出现 `manual_edit`，且主文案为中文可读标签。
7. 查看版本详情。
8. 对比当前版本和上一版本。
9. 回滚到上一版本，确认当前正文刷新且产生 `rollback` 版本。
10. 选择一段正文执行局部返修，确认 AI 候选不会直接覆盖正文。
11. 接受候选后保存，确认产生可识别版本记录。
12. 导出 TXT 和 Markdown，确认中文文件名不触发 500。
13. 在工作流页停留时，运行状态能自动刷新或给出明确刷新机制。
14. 章节菜单、左侧项目菜单、工作台路由不跳错章节。
15. v5.5.15 的重复生成、终态 guard、running guard 不回归。

### 输出

新增真实验收报告：

```text
docs/codex/reports/novel-factory-v5.7.1-real-project-acceptance.md
```

报告必须包含：

- 验收日期；
- 使用项目；
- 每个验收项结果；
- 发现的问题；
- 修复 commit；
- 最终结论。

## 范围二：运行状态与恢复一致性

重点处理真实项目中容易出现的状态矛盾：

- 章节已经 `published/reviewed/awaiting_publish`，但仍存在 running workflow；
- 章节是 `revision/blocking`，但菜单给出不合适的生成动作；
- `recent_runs` 列表不包含老章节运行，导致恢复入口找不到目标；
- 工作流页面显示“正在推进”，但实际已超过卡住阈值；
- 第 N 章已发布，第 N-1 章仍显示 running。

验收：

1. 终态章节 + running workflow 优先显示“状态矛盾”。
2. stale running 超过阈值时有明确“标记阻塞 / 清理恢复”动作。
3. 章节级恢复不依赖 `recent_runs` 最近 10 条。
4. 清理恢复后，工作流视图立即刷新，不发空 run_id 请求。
5. 菜单动作和章节状态一致，不给作者误导入口。

## 范围三：编辑、版本、导出稳定

### 编辑与版本

验收：

1. 保存失败时按钮恢复可点击。
2. 创建修订版失败时按钮恢复可点击。
3. 回滚失败时使用站内弹窗，不使用原生浏览器弹窗。
4. `published` 章节不能直接保存。
5. `reviewed` 保存后不能保持可直接发布状态。
6. diff 不能跨章节比较版本。
7. 版本 source、artifact 名称、内部 key 不作为主文案暴露给作者。

### 导出

验收：

1. 中文项目名导出不触发响应头编码错误。
2. TXT 和 Markdown 均可通过前端 `/api` 代理下载。
3. 导出空项目返回可理解错误。
4. Content-Disposition 使用 ASCII fallback + UTF-8 `filename*`。

## 范围四：验证与测试分层

保留并校准 `scripts/verify.py`：

```bash
python3 scripts/verify.py smoke
python3 scripts/verify.py v57
python3 scripts/verify.py frontend
python3 scripts/verify.py full
python3 scripts/verify.py durations
```

验收：

1. `smoke` 覆盖 v5.5.15 guard 与 v5.7 编辑版本关键回归。
2. `v57` 覆盖编辑器、版本 API、前端编辑器组件。
3. `frontend` 使用非 watch 模式，适合自动化。
4. `full` 作为稳定基线闸门。
5. README 中测试基线与实际结果一致。

## 范围五：文档与版本状态整理

必须更新：

- `docs/codex/README.md`
- `docs/codex/planning/novel-factory-v5.7-daily-writing-editing-versioning-spec.md`
- 新增 v5.7.1 完成报告
- 新增 v5.7.1 Review 记录
- 新增 v5.7.1 真实项目验收报告

文档规则：

1. 已完成版本的规格状态应为 `completed`。
2. `reports/` 记录完成事实，不写未来范围。
3. `reviews/` 记录问题、修复和验证。
4. `next/` 只保留方向，不作为执行规格。

## 文件范围

优先涉及：

```text
docs/codex/README.md
docs/codex/planning/novel-factory-v5.7.1-internal-hardening-spec.md
docs/codex/reports/novel-factory-v5.7.1-completion-report.md
docs/codex/reports/novel-factory-v5.7.1-real-project-acceptance.md
docs/codex/reviews/novel-factory-v5.7.1-review.md
scripts/verify.py
tests/test_project_export.py
tests/test_v57_chapter_editing_versions.py
tests/test_v5515_production_readiness.py
frontend/src/components/project/*
frontend/src/pages/ProjectDetail.tsx
frontend/src/lib/api.ts
novel_factory/api/routes/projects.py
novel_factory/api/routes/versions.py
novel_factory/api/routes/production.py
novel_factory/api/routes/run.py
novel_factory/api/routes/runs.py
novel_factory/workflow/runner.py
```

不要为了 v5.7.1 主动改动无关模块。

## 推荐实施顺序

1. 运行 `python3 scripts/verify.py smoke`，确认当前基础绿灯。
2. 打开 `novel_3v2o` 执行真实项目验收，记录每个问题。
3. 按问题最小修复，不做新功能扩展。
4. 为每个修复补充定向测试。
5. 跑 `python3 scripts/verify.py v57` 和 `python3 scripts/verify.py frontend`。
6. 跑真实导出 smoke。
7. 跑 `python3 scripts/verify.py full`。
8. 写 completion report、review、real project acceptance。
9. 更新 README 当前基线和测试基线。
10. commit 并 push。

## 完成标准

v5.7.1 完成必须满足：

1. `novel_3v2o` 真实项目验收通过，并有报告。
2. 编辑、版本、回滚、局部返修、导出在真实数据上可用。
3. 历史 running/blocked 状态不会误导作者。
4. 工作台路由、菜单、章节上下文不跳错。
5. v5.5.15 guard、v5.6.1 recovery、v5.7 editing/versioning 不回归。
6. `python3 scripts/verify.py full` 通过。
7. README、completion report、review 文档完成。
8. 当前分支干净，并推送远程。

## 给实现 Agent 的开发 Prompt

按以下规格执行 `v5.7.1 Internal Hardening`：

```text
docs/codex/planning/novel-factory-v5.7.1-internal-hardening-spec.md
```

目标不是新增大功能，而是把现有个人作者工作台压实到内部稳定：真实项目验收、运行状态一致性、编辑/版本/导出稳定、验证脚本与文档基线统一。

必须使用 `novel_3v2o` 做真实项目验收。发现问题后做最小修复，并为修复补定向测试。不要做多租户、权限、RAG、长篇记忆治理、DOCX/EPUB、大型 UI 重构或 LangGraph 主链路重写。

完成后必须运行：

```bash
python3 scripts/verify.py full
```

并新增：

```text
docs/codex/reports/novel-factory-v5.7.1-completion-report.md
docs/codex/reports/novel-factory-v5.7.1-real-project-acceptance.md
docs/codex/reviews/novel-factory-v5.7.1-review.md
```
