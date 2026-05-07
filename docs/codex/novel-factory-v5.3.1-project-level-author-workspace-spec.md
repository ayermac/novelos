# Novel Factory v5.3.1 Project-Level Author Workspace Spec

状态：规划中
日期：2026-04-28
上游依赖：v5.3.0 Trusted Generation Chain

## 背景

v5.3.0 已经把真实模式章节生成从“自动发布 demo 链路”收口为可信生成链路：上下文不完整时阻止生成，Planner 可作为前置规划入口，字数质量门会阻断不合格输出，真实模式 AI 审核通过后停在 `reviewed + awaiting_publish=true`，等待人工发布。

但 WebUI 仍然像“章节运行控制台”：世界观、角色、大纲被塞进章节页 Tab；势力、伏笔、章节指令、状态卡、版本、质量报告、连续性报告、人工审核记录和 Agent 产物缺少项目级入口；`/run` 仍容易被理解为日常创作主入口。v5.3.1 的目标是把 WebUI 改成真人作者能长期使用的项目级工作台。

## 产品原则

1. 项目资料是项目级资产，不属于某一章。
2. 章节页只处理章节正文、当前章指令、当前章产物和当前章工作流。
3. 日常创作从项目工作台发生，不从高级运行表单发生。
4. 缺上下文时，系统要告诉用户缺什么，并把用户带到对应项目模块补齐。
5. 所有模块必须有空状态、创建入口、编辑入口和删除/归档确认。
6. 真实模式下不营造“已经完成”的假象，待人工发布、阻塞、返修都要清楚展示。

## 信息架构

### 主导航

- 创作中心：`/`
- 项目：`/projects`
- 审核：`/review`
- 风格：`/style`
- 设置：`/settings`

`/run` 从主导航移除，仅保留为高级调试入口。可从项目工作台的次级菜单进入，文案为“高级运行调试”。

### 项目级页面

路径：`/projects/:projectId`

项目页顶部保留项目名称、类型、简介、生成模式、上下文完整度、下一步建议。

项目页二级导航：

- 总览
- 章节
- 世界观
- 角色
- 势力
- 大纲
- 伏笔
- 章节指令
- 风格指南
- 审核
- 运行记录
- 设置

### 章节级页面

路径仍可复用 `/projects/:projectId?chapter=N&view=...`，但语义必须收窄为当前章节。

章节级视图只包含：

- 正文
- 当前章指令
- Scene Beats
- 工作流
- 版本
- 审核意见

世界观、角色、大纲不再作为章节 Tab 出现。章节页可以显示“本章引用的世界观/角色/大纲摘要”，但编辑入口跳回项目级模块。

## 模块要求

| 模块 | 数据来源 | API 状态 | v5.3.1 交付 |
| --- | --- | --- | --- |
| 世界观 | `world_settings` | 已有 CRUD | 项目级列表、创建、编辑、删除、重要度/类别筛选 |
| 角色 | `characters` | 已有 CRUD | 项目级卡片/列表、创建、编辑、删除、主角/配角筛选 |
| 大纲 | `outlines` | 已有 CRUD | 项目级层级列表、创建、编辑、删除、章节覆盖范围展示 |
| 势力 | `factions` | 缺主 API | 新增 CRUD API + 项目级 UI |
| 伏笔 | `plot_holes` | repository 部分能力 | 新增 CRUD API + planted/resolved 状态 UI |
| 章节指令 | `instructions` | repository 有读写 | 新增 CRUD API + 按章节管理 UI |
| 状态卡 | `chapter_state` | repository 有只读/写入 | 新增只读历史入口 |
| 版本 | `chapter_versions` | repository 有写入/部分 diff | 新增版本列表，diff 可先做简版 |
| 质量报告 | `quality_reports` | repository 有能力 | 新增只读报告列表和详情 |
| 连续性报告 | `continuity_reports` | repository 有能力 | 新增只读报告列表和详情 |
| 人工审核 | `human_review_sessions` / `reviews` | 部分能力 | 融入审核中心和章节审核页 |
| Agent 产物 | `agent_artifacts` | repository 有能力 | 工作流/章节产物页展示 |

## API 设计

已有 API 保留：

- `GET/POST/PUT/DELETE /api/projects/{id}/world-settings`
- `GET/POST/PUT/DELETE /api/projects/{id}/characters`
- `GET/POST/PUT/DELETE /api/projects/{id}/outlines`

新增或补齐：

- `GET /api/projects/{id}/factions`
- `POST /api/projects/{id}/factions`
- `PUT /api/projects/{id}/factions/{faction_id}`
- `DELETE /api/projects/{id}/factions/{faction_id}`
- `GET /api/projects/{id}/plot-holes`
- `POST /api/projects/{id}/plot-holes`
- `PUT /api/projects/{id}/plot-holes/{plot_id}`
- `DELETE /api/projects/{id}/plot-holes/{plot_id}`
- `GET /api/projects/{id}/instructions`
- `POST /api/projects/{id}/instructions`
- `PUT /api/projects/{id}/instructions/{chapter_number}`
- `DELETE /api/projects/{id}/instructions/{chapter_number}`
- `GET /api/projects/{id}/chapters/{chapter_number}/state-history`
- `GET /api/projects/{id}/chapters/{chapter_number}/versions`
- `GET /api/projects/{id}/chapters/{chapter_number}/versions/{version_id}/diff`
- `GET /api/projects/{id}/quality-reports`
- `GET /api/projects/{id}/continuity-reports`
- `GET /api/projects/{id}/artifacts`
- `GET /api/projects/{id}/context-status`

`context-status` 返回项目生成准备度：

```json
{
  "ready": false,
  "score": 67,
  "missing": ["world_settings", "instructions"],
  "actions": [
    {"label": "补充世界观", "path": "/projects/demo?module=worldview"},
    {"label": "生成章节指令", "path": "/projects/demo?module=instructions"}
  ]
}
```

## 前端重构

### ProjectDetail 拆分

当前 `ProjectDetail.tsx` 已经过大，v5.3.1 必须拆分：

- `pages/ProjectDetail.tsx`：只负责路由、项目加载和布局
- `components/project/ProjectHeader.tsx`
- `components/project/ProjectModuleNav.tsx`
- `components/project/ProjectOverview.tsx`
- `components/project/ChaptersModule.tsx`
- `components/project/WorldSettingsModule.tsx`
- `components/project/CharactersModule.tsx`
- `components/project/OutlinesModule.tsx`
- `components/project/FactionsModule.tsx`
- `components/project/PlotHolesModule.tsx`
- `components/project/InstructionsModule.tsx`
- `components/project/StyleGuideModule.tsx`
- `components/project/ReviewModule.tsx`
- `components/project/RunsModule.tsx`
- `components/project/ProjectSettingsModule.tsx`
- `components/chapter/ChapterWorkspace.tsx`
- `components/chapter/ChapterContentPanel.tsx`
- `components/chapter/ChapterInstructionPanel.tsx`
- `components/chapter/ChapterWorkflowPanel.tsx`
- `components/chapter/ChapterVersionsPanel.tsx`
- `components/chapter/ChapterReviewPanel.tsx`

### URL 规范

项目模块：

- `/projects/:id?module=overview`
- `/projects/:id?module=chapters`
- `/projects/:id?module=worldview`
- `/projects/:id?module=characters`
- `/projects/:id?module=factions`
- `/projects/:id?module=outline`
- `/projects/:id?module=plots`
- `/projects/:id?module=instructions`
- `/projects/:id?module=style`
- `/projects/:id?module=review`
- `/projects/:id?module=runs`
- `/projects/:id?module=settings`

章节工作区：

- `/projects/:id?module=chapters&chapter=1&view=content`
- `/projects/:id?module=chapters&chapter=1&view=instruction`
- `/projects/:id?module=chapters&chapter=1&view=beats`
- `/projects/:id?module=chapters&chapter=1&view=workflow`
- `/projects/:id?module=chapters&chapter=1&view=versions`
- `/projects/:id?module=chapters&chapter=1&view=review`

旧参数兼容：

- `?chapter=1&view=content` 自动视为 `module=chapters`
- `/projects/:id/chapters/:num` 继续 redirect 到新参数形态

## 开发阶段

### Phase A：API 与 read model

目标：补齐项目级模块 API，让前端不再绕过 repository。

任务：

1. 新增 `factions.py`, `plot_holes.py`, `instructions.py`, `project_context.py` routes。
2. 在 `api_app.py` 注册新 router。
3. 对 `chapter_state`, `chapter_versions`, `quality_reports`, `continuity_reports`, `agent_artifacts` 增加只读端点。
4. 所有返回使用统一 envelope，不泄露 traceback。
5. 增加 API 集成测试。

验收：

- CRUD 端点能真实写 DB。
- 删除只做软删除或确认删除，不能静默破坏生成历史。
- `context-status` 与 v5.3.0 Context Readiness Gate 使用同一套判断，不复制规则。

### Phase B：项目级模块 UI

目标：世界观/角色/大纲/势力/伏笔/章节指令从章节 Tab 迁移到项目模块。

任务：

1. 拆分 `ProjectDetail.tsx`。
2. 新增项目二级导航。
3. 迁移世界观、角色、大纲 UI。
4. 新增势力、伏笔、章节指令 UI。
5. 每个模块提供列表、空状态、创建、编辑、删除/归档确认。
6. 缺上下文时，从错误详情跳转到对应模块。

验收：

- 世界观/角色/大纲不再出现在章节 Tab。
- 用户可在项目页完成生成前必要资料补齐。
- 表单中文化，不能出现 raw JSON 操作体验。

### Phase C：章节工作区收窄

目标：章节页变成真正的章节工作区，而不是项目资料混杂页。

任务：

1. 章节导航只保留正文、当前章指令、Scene Beats、工作流、版本、审核。
2. 当前章指令支持查看/编辑/生成。
3. 工作流面板显示当前 run，保留“查看详情”。
4. 版本面板显示章节版本列表和简版 diff。
5. 审核面板显示 AI 审核结果、人工发布、退回修改。

验收：

- 点击生成后留在章节工作区。
- 真实模式生成通过后显示“待人工发布”，主按钮是确认发布。
- 失败/阻塞时显示原因和可执行恢复动作。

### Phase D：导航与验收收口

目标：去掉 demo 感，确保主路径清楚。

任务：

1. `/run` 从 Layout 主导航移除。
2. 项目页提供“高级运行调试”次级入口。
3. Dashboard CTA 全部进入项目工作台。
4. Review / Style / Settings 与项目工作台入口互通。
5. 更新 README、roadmap、v5.3 spec。
6. 增加前端静态测试和 API 测试。

验收：

- 新用户从创建项目到补上下文、生成章节、人工发布，全程不需要进入 `/run`。
- `/run` 仍可手动访问，不破坏开发调试。
- 全量 pytest、frontend typecheck、frontend build 通过。

## 测试计划

新增测试文件建议：

- `tests/test_v531_project_workspace_api.py`
- `tests/test_v531_project_workspace_frontend.py`
- `tests/test_v531_context_navigation.py`

核心断言：

1. factions CRUD 真实写入、更新、删除。
2. plot_holes CRUD 真实写入、状态更新。
3. instructions CRUD 真实写入，并被 run/chapter 读取。
4. context-status 返回缺失项和跳转 action。
5. ProjectDetail 不再包含世界观/角色/大纲章节 Tab 文案。
6. Layout 不显示 `/run` 主导航。
7. 章节工作区显示当前章指令、版本、审核、工作流入口。
8. 缺上下文错误能显示“补充世界观/角色/大纲/章节指令”的入口。
9. 真实模式待发布章节在项目工作台有发布按钮。

## 非目标

- 不实现完整 Project Genesis 自动生成项目圣经。可保留为 v5.3.2 或 v5.4。
- 不实现完整 Fact Ledger。事实账本仍属于 v5.3.3。
- 不重构所有历史 CLI。
- 不彻底删除 `/run`。
- 不做复杂富文本编辑器，正文阅读/基础编辑即可。

## 完成定义

v5.3.1 完成时，用户应该能回答这几个问题：

1. 我的小说世界观在哪里管理？
2. 我的角色、势力、伏笔、大纲在哪里管理？
3. 第 1 章为什么不能生成，缺什么资料？
4. 第 1 章生成后每个环节产出了什么？
5. AI 审核通过后为什么还没发布，我在哪里确认发布？
6. `/run` 是高级调试入口，而不是日常创作入口。

如果这些问题仍需要用户猜，v5.3.1 就不能算完成。
