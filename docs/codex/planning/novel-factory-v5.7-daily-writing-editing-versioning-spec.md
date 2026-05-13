# Novelos v5.7 日常写作编辑与版本管理规格

## 状态

- 类型：可执行规划规格
- 状态：planned
- 基线：v5.6.1 Workbench Stabilization
- 产品目标：把 Author Workbench 从“AI 章节生产控制台”推进到“作者每天可写、可改、可追溯的创作闭环”
- 技术目标：建立正文编辑、版本管理、对比回滚、局部返修的最小闭环，为后续记忆一致性、RAG 和 AgentOps 复盘打基础

## 背景

v5.5.15 解决了生产防护、重复生成、终态 guard、真实项目验收和运行恢复基线。v5.6/v5.6.1 把项目页稳定成个人创作工作台，补齐了菜单、路由、卡住恢复、工作流刷新、站内弹窗、加载态和产物可读性。

当前系统已经能比较稳定地“生成章节”，但作者还不能自然地在系统里完成日常写作动作：

- 手动修改正文；
- 保存自己的修改；
- 看见 AI 版、人工版、返修版之间的关系；
- 对比版本差异；
- 回滚误改；
- 只让 AI 改一小段，而不是重跑整章。

v5.7 的目标是补上这条创作者闭环。

## 产品定位

v5.7 不是新的 Agent 大脑，也不是新的视觉重构。它是 Author Workbench 的核心写作能力升级：

```text
AI 生成章节 -> 作者编辑 -> 保存版本 -> 对比/回滚 -> 局部 AI 返修 -> 人工确认 -> 发布前保护
```

这条链路属于 AI Agent 产品能力，但需要后端版本能力、Agent 局部返修 API 和前端写作交互共同支撑。

## 非目标

- 不做多租户、组织、RBAC、计费、企业后台。
- 不做 Creator Knowledge Base / RAG。
- 不做完整长篇记忆治理。
- 不重写 LangGraph 主生产链路。
- 不改变 v5.5.15 / v5.6.1 已稳定的生成 guard 和恢复语义。
- 不引入大型富文本编辑器，除非原生 textarea/contenteditable 无法满足基础验收。
- 不做复杂协同编辑。
- 不做 DOCX/EPUB 导出。
- 不做审稿系统大改版。

## 核心原则

1. 作者的人工修改是一等产物，不能被下一次 AI 运行静默覆盖。
2. 所有正文变化都必须可追溯：谁改的、什么时候改的、为什么改的。
3. AI 局部返修必须默认可撤销，不能直接覆盖正文。
4. 发布章节默认只读，修改已发布内容必须显式创建修订版。
5. 版本功能应该服务写作判断，而不是变成工程日志。
6. UI 要把“当前正文”和“过程稿/历史版本”分清楚。

## 数据模型范围

现有系统已经有 `chapter_versions` 相关能力。v5.7 应优先复用既有表和 repository，不轻易新增平行版本表。

需要确认并补齐的版本字段：

- `project_id`
- `chapter_number`
- `version_id`
- `content`
- `word_count`
- `created_by`
- `created_at`
- `source`
  - `ai_generation`
  - `manual_edit`
  - `local_revision`
  - `rollback`
  - `publish_snapshot`
- `base_version_id`
- `summary`
- `metadata`

如果现有 schema 不完整，优先用向后兼容 migration 补字段。

## 后端 API 范围

### 1. 获取章节正文编辑状态

新增或补齐：

```text
GET /api/projects/{project_id}/chapters/{chapter_number}/editor
```

返回：

- 当前正文；
- 当前章节状态；
- 当前可编辑性；
- 当前版本 id；
- 最近版本列表摘要；
- 是否有未保存草稿；
- published / awaiting_publish / reviewed 状态下的编辑限制说明。

验收：

- planned 空章节返回可理解空状态；
- drafted/polished/revision 章节可编辑；
- reviewed 在 real mode 下默认可编辑但保存后应回到非发布态或提示需要重新审核；
- published 默认只读。

### 2. 保存人工正文

新增或补齐：

```text
POST /api/projects/{project_id}/chapters/{chapter_number}/content
```

请求：

- `content`
- `summary`
- `base_version_id`
- `confirm`

行为：

- 更新章节当前正文；
- 更新 word_count；
- 创建 `manual_edit` 版本；
- 记录 base_version_id；
- 如果章节是 `published`，必须拒绝并要求显式创建修订版；
- 如果 base_version_id 已过期，返回冲突信息。

验收：

- 保存后重新打开章节能看到新正文；
- 保存生成一个新版本；
- 空正文或过短正文要有明确错误；
- 过期 base version 不能静默覆盖。

### 3. 版本列表与详情

新增或补齐：

```text
GET /api/projects/{project_id}/chapters/{chapter_number}/versions
GET /api/projects/{project_id}/chapters/{chapter_number}/versions/{version_id}
```

列表返回：

- version_id；
- source；
- created_by；
- created_at；
- word_count；
- summary；
- 是否为当前版本。

详情返回：

- 完整正文；
- metadata；
- base_version_id。

验收：

- AI 生成、人工保存、局部返修、回滚都能在版本列表看到；
- 版本标签必须是作者可读文案，不暴露内部 key 作为主文案。

### 4. 版本对比

新增：

```text
GET /api/projects/{project_id}/chapters/{chapter_number}/versions/{left_version_id}/diff/{right_version_id}
```

返回结构化 diff：

- added；
- removed；
- unchanged；
- changed block；
- word count delta。

实现建议：

- MVP 可用 Python 标准库 `difflib`；
- 前端按段落/行展示；
- 不需要复杂语义 diff。

验收：

- 能对比当前正文和上一版本；
- 能对比任意两个版本；
- 中文文本展示稳定；
- 大段文本不会让 UI 卡死。

### 5. 回滚版本

新增：

```text
POST /api/projects/{project_id}/chapters/{chapter_number}/versions/{version_id}/restore
```

行为：

- 用目标版本内容更新当前正文；
- 创建 `rollback` 新版本，而不是删除历史；
- published 章节默认拒绝，除非先创建修订版；
- 返回新 current_version_id。

验收：

- 回滚后当前正文等于目标版本；
- 历史版本不丢；
- 回滚动作有站内确认；
- 回滚后版本列表能看出来源。

### 6. 创建已发布章节修订版

新增：

```text
POST /api/projects/{project_id}/chapters/{chapter_number}/revision-draft
```

行为：

- 仅对 `published` 或 `awaiting_publish` 章节开放；
- 创建当前发布内容的修订草稿版本；
- 将章节状态调整到明确的可编辑状态，建议使用 `revision`；
- 保留发布版本快照。

验收：

- published 章节正文区域默认只读；
- 点击“创建修订版”后才能编辑；
- 不能误改已发布正文而不留版本。

### 7. 局部 AI 返修

新增：

```text
POST /api/projects/{project_id}/chapters/{chapter_number}/local-revision
```

请求：

- `selected_text`
- `selection_start`
- `selection_end`
- `instruction`
- `base_version_id`
- `mode`
  - `rewrite`
  - `polish`
  - `shorten`
  - `expand`
  - `tone`

行为：

- 调用适合的 Agent 或 LLM profile；
- 只返回候选替换结果，不直接覆盖当前正文；
- 记录 local revision artifact；
- 前端确认接受后，再调用保存接口创建 `local_revision` 版本。

验收：

- 未选择文本时不能提交；
- 选择文本过长时提示缩小范围；
- AI 返回失败不改变正文；
- 接受返修后创建新版本；
- 放弃返修后正文不变。

## 前端范围

主要文件范围：

- `frontend/src/pages/ProjectDetail.tsx`
- `frontend/src/components/project/AuthorWorkbench.tsx`
- `frontend/src/components/project/AuthorWritingSurface.tsx`
- `frontend/src/components/project/AuthorAgentPanel.tsx`
- `frontend/src/components/project/AuthorWorkbench.css`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/state-labels.ts`
- `frontend/src/components/project/__tests__/AuthorWorkbench.test.tsx`

建议新增组件：

- `ChapterEditorSurface.tsx`
- `ChapterVersionPanel.tsx`
- `ChapterDiffViewer.tsx`
- `LocalRevisionPanel.tsx`

### 1. 正文编辑模式

在“正文”视图中增加：

- 阅读模式；
- 编辑模式；
- 保存；
- 放弃修改；
- 保存中状态；
- 未保存变更提示。

验收：

- 有正文时默认阅读模式；
- 点击编辑进入编辑模式；
- 修改后保存按钮可用；
- 保存中按钮 disabled；
- 保存失败显示站内错误；
- 切换章节或视图时，如果有未保存修改，用站内确认。

### 2. 发布章节保护

published 章节：

- 默认只读；
- 展示“已发布，创建修订版后可编辑”；
- 主按钮是“创建修订版”，不是直接编辑。

验收：

- 不允许直接保存 published 正文；
- 创建修订版后进入可编辑状态；
- 修订版保存会形成新版本。

### 3. 版本面板

在“历史”或新增“版本”区域展示：

- 当前版本；
- 最近版本列表；
- 来源标签；
- 字数；
- 时间；
- 查看；
- 对比；
- 回滚。

验收：

- 版本列表不显示内部 source key；
- 当前版本高亮；
- 回滚要站内确认；
- 回滚后刷新正文。

### 4. Diff 视图

提供：

- 当前 vs 上一版；
- 任意版本对比；
- added/removed/change 的可读样式；
- 字数变化。

验收：

- 中文段落不乱码；
- 删除和新增视觉明确；
- diff 面板可关闭返回正文。

### 5. 局部返修交互

在编辑模式中支持：

- 选中文本；
- 输入返修要求；
- 选择返修模式；
- 提交 AI 返修；
- 预览候选结果；
- 接受 / 放弃 / 再改一次。

MVP 可先用 textarea selection API，不必上复杂富文本。

验收：

- 未选择文本时禁用返修；
- 有 selection 时显示返修面板；
- 返修中有加载态；
- AI 结果不会直接覆盖正文；
- 接受后替换选区并标记为未保存；
- 保存后创建 `local_revision` 版本。

## Agent 范围

v5.7 的局部返修可以优先复用现有 Author/Polisher 能力，不必新增完整 Agent。

建议策略：

- `rewrite` / `expand`：走 Author 风格；
- `polish` / `tone` / `shorten`：走 Polisher 风格；
- 输入上下文包含：
  - 当前章节标题；
  - 当前章节摘要或前后 500 字；
  - selected_text；
  - 用户 instruction；
  - 风格规范摘要；
  - 不能改动选区以外内容的硬约束。

输出必须结构化：

```json
{
  "replacement_text": "...",
  "change_summary": "...",
  "risk_notes": []
}
```

验收：

- 输出为空时返回错误；
- replacement_text 不应包含未请求的整章内容；
- risk_notes 可展示给作者；
- stub mode 有确定性返回，便于测试。

## 状态与 guard

必须保留：

- running workflow 时不能同时整体生成本章；
- reviewed/awaiting_publish/published 终态 guard 不被破坏；
- reviewed + real mode 仍等待人工发布；
- published 不允许直接覆盖；
- reset/recovery 行为不变。

新增规则：

- manual edit 保存后，如果章节原状态是 `reviewed`，应标记为需要重新审核或回到 `polished`，避免改后直接发布；
- manual edit 保存后，如果章节原状态是 `published`，必须拒绝；
- local revision 接受后也应触发同样的状态回退逻辑；
- 回滚到旧版本不代表自动通过审核。

## 测试计划

### 后端测试

建议新增：

- `tests/test_v57_chapter_editing_versions.py`

覆盖：

1. 保存正文创建 manual_edit 版本；
2. published 章节不能直接保存；
3. 创建 published 修订版；
4. version list / detail；
5. diff API；
6. restore 创建 rollback 版本；
7. stale base_version 拒绝覆盖；
8. local revision 只返回候选不覆盖正文；
9. 接受 local revision 后保存为新版本；
10. reviewed 保存后不能保持可直接发布状态。

### 前端测试

扩展：

- `frontend/src/components/project/__tests__/AuthorWorkbench.test.tsx`

或新增：

- `frontend/src/components/project/__tests__/ChapterEditorSurface.test.tsx`

覆盖：

1. 阅读/编辑模式切换；
2. 保存按钮 pending 和错误态；
3. 未保存变更切换确认；
4. published 只读；
5. 创建修订版入口；
6. 版本列表展示；
7. diff 展示；
8. 回滚确认；
9. selection local revision；
10. 接受返修后正文替换但未保存；
11. 保存 local revision 后刷新版本列表。

## 真实项目验收

使用 `novel_3v2o`：

1. 打开第 4 章正文；
2. 进入编辑模式；
3. 修改一段文字并保存；
4. 确认版本列表出现人工编辑版本；
5. 对比人工编辑版本和上一版；
6. 回滚到上一版；
7. 选择一段正文进行局部返修；
8. 接受返修并保存；
9. 确认新版本 source 为 local revision；
10. 对 published 章节验证默认只读和创建修订版流程；
11. 确认 v5.6.1 的工作流、卡住恢复、菜单路由不回归。

## 实施顺序

1. 盘点现有 `chapter_versions` schema 和 repository 能力。
2. 先补后端版本 API 和测试。
3. 再做前端编辑模式和保存。
4. 增加版本列表、详情、diff、回滚。
5. 增加 published 修订版保护。
6. 最后接入局部 AI 返修。
7. 跑 `novel_3v2o` 真实路径验收。
8. 创建 v5.7 completion report 和 review。

## 验证命令

```bash
python3 -m pytest tests/test_v57_chapter_editing_versions.py tests/test_v5515_production_readiness.py tests/test_v55_run_recovery.py -q
```

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
npm run test -- --run
```

声明新稳定基线前运行：

```bash
python3 -m pytest -q
```

## 完成标准

v5.7 完成必须满足：

1. 作者能在工作台里编辑正文并保存。
2. 每次保存都产生版本记录。
3. 可以查看版本、对比版本、回滚版本。
4. published 章节默认只读，修改必须先创建修订版。
5. 局部 AI 返修支持选区、指令、候选预览、接受/放弃。
6. AI 返修不会直接覆盖正文。
7. v5.5.15 / v5.6.1 guard 和恢复语义不回归。
8. `novel_3v2o` 真实验收通过。
9. 前端 typecheck/lint/build/vitest 通过。
10. 后端定向测试与全量 pytest 通过。
11. 完成报告写入 `docs/codex/reports/`。
12. Review 记录写入 `docs/codex/reviews/`。

## 给实现 Agent 的开发 Prompt

按以下规格实现 `v5.7 Daily Writing Editing and Versioning`：

```text
docs/codex/planning/novel-factory-v5.7-daily-writing-editing-versioning-spec.md
```

目标是完成个人创作工作台的第一段创作者闭环：正文编辑、保存、版本列表、版本详情、diff、回滚、published 修订版保护、局部 AI 返修。

不要做多租户、权限、企业后台、RAG、长篇记忆治理、导出发布，也不要重写 v5.5.15/v5.6.1 的工作流 guard。

优先复用现有 `chapter_versions` 和 repository 能力；若 schema 不足，用向后兼容 migration 补齐。前端优先使用简单稳定的 textarea 选区能力完成局部返修 MVP，不引入大型编辑器。

必须覆盖测试，并用 `novel_3v2o` 做真实路径验收。完成前运行：

```bash
python3 -m pytest tests/test_v57_chapter_editing_versions.py tests/test_v5515_production_readiness.py tests/test_v55_run_recovery.py -q
cd frontend
npm run typecheck
npm run lint
npm run build
npm run test -- --run
```

更新稳定基线前运行：

```bash
python3 -m pytest -q
```
