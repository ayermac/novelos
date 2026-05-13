# Novelos v5.7 日常写作编辑与版本管理完成报告

## 执行摘要

v5.7 成功将 Author Workbench 从"AI 章节生产控制台"推进到"作者每天可写、可改、可追溯的创作闭环"，建立了正文编辑、版本管理、对比回滚、局部返修的最小闭环。

**完成时间**: 2026-05-13
**基线版本**: v5.6.1 Workbench Stabilization
**测试状态**: 1859/1859 pytest 通过，前端 typecheck/lint/build/vitest 125/125 全部通过

## 核心交付

### 1. 后端版本管理 API

新增 8 个 API 端点：

- `GET /api/projects/{id}/chapters/{n}/editor` - 获取编辑器状态
- `POST /api/projects/{id}/chapters/{n}/content` - 保存人工编辑
- `GET /api/projects/{id}/chapters/{n}/versions` - 版本列表
- `GET /api/projects/{id}/chapters/{n}/versions/{id}` - 版本详情
- `GET /api/projects/{id}/chapters/{n}/versions/{left}/diff/{right}` - 版本对比
- `POST /api/projects/{id}/chapters/{n}/versions/{id}/restore` - 回滚版本
- `POST /api/projects/{id}/chapters/{n}/revision-draft` - 创建已发布章节修订版
- `POST /api/projects/{id}/chapters/{n}/local-revision` - 局部 AI 返修

### 2. 数据库迁移

新增 migration `029_v5_7_chapter_version_fields.sql`：

```sql
ALTER TABLE chapter_versions ADD COLUMN source TEXT DEFAULT 'ai_generation';
ALTER TABLE chapter_versions ADD COLUMN base_version_id INTEGER REFERENCES chapter_versions(id);
ALTER TABLE chapter_versions ADD COLUMN summary TEXT;
ALTER TABLE chapter_versions ADD COLUMN metadata TEXT;
```

### 3. 前端组件

新增 3 个核心组件：

- `ChapterEditorSurface.tsx` - 编辑器主界面（阅读/编辑模式切换、保存、未保存提示）
- `ChapterVersionPanel.tsx` - 版本列表面板（版本历史、查看、对比、回滚）
- `ChapterDiffViewer.tsx` - 版本对比视图（added/removed/changed 结构化展示）

局部返修能力已内置在 `ChapterEditorSurface.tsx`，不再保留独立未引用组件。

集成到现有组件：

- `AuthorWritingSurface.tsx` - 新增"版本"标签页
- `AuthorWorkbench.tsx` - 传递刷新回调
- `ProjectDetail.tsx` - 支持 versions 视图

### 4. LLM Provider 扩展

扩展 `stub_provider.py` 支持 `LocalRevisionOutput` schema：

```python
if "LocalRevisionOutput" in schema_name:
    return {
        "replacement_text": "（返修后）这是局部返修的候选替换文本。",
        "change_summary": "stub 模式：确定性局部返修结果",
        "risk_notes": [],
    }
```

## 完成标准验证

### 1. 作者能在工作台里编辑正文并保存 ✅

- 实现阅读/编辑模式切换
- 保存创建 `manual_edit` 版本
- 未保存变更提示

### 2. 每次保存都产生版本记录 ✅

- `save_version()` 扩展支持 `source`, `base_version_id`, `summary`, `metadata`
- 版本来源标签：AI 生成、人工编辑、局部返修、回滚、发布快照

### 3. 可以查看版本、对比版本、回滚版本 ✅

- 版本列表展示来源、字数、时间、摘要
- 版本对比使用 Python `difflib` 结构化展示
- 回滚创建 `rollback` 版本，保留历史

### 4. published 章节默认只读，修改必须先创建修订版 ✅

- `published`/`awaiting_publish` 章节返回 `editable: false`
- 前端展示"创建修订版"按钮
- 修订版创建后状态转为 `revision`

### 5. 局部 AI 返修支持选区、指令、候选预览、接受/放弃 ✅

- 文本选择触发返修面板
- 5 种返修模式：rewrite, polish, shorten, expand, tone
- AI 返回候选替换，不直接覆盖正文
- 接受后替换选区并标记为未保存

### 6. AI 返修不会直接覆盖正文 ✅

- `local-revision` 端点只返回候选
- 用户必须显式接受后才替换
- 接受后需要手动保存

### 7. v5.5.15 / v5.6.1 guard 和恢复语义不回归 ✅

- `published` 章节不能直接保存
- `reviewed` 保存后状态转为 `polished`，需重新审核
- `base_version_id` 过期检测防止覆盖
- v5.5.15 的运行 guard 与恢复语义保持不回归

### 8. 自动化回归通过 ✅

- 后端 v5.7 测试：12/12 通过
- 前端测试：125/125 通过
- 完整 pytest：1859/1859 通过

### 9. 前端 typecheck/lint/build/vitest 通过 ✅

- TypeScript 类型检查通过
- ESLint 无错误无警告
- Vite build 成功
- Vitest 125 测试通过

### 10. 后端定向测试与全量 pytest 通过 ✅

- `test_v57_chapter_editing_versions.py`: 12/12 通过
- `test_v5515_production_readiness.py`: 12/12 通过
- `test_v55_run_recovery.py`: 11/11 通过
- 全量 pytest: 1859/1859 通过

## 技术亮点

### 1. 向后兼容迁移

- 新增字段使用默认值，不影响现有数据
- `source` 默认 `ai_generation`，兼容历史版本
- Schema 检测避免重复执行

### 2. 冲突检测机制

- `base_version_id` 追踪版本依赖
- 过期版本保存返回 409 Conflict
- 防止多人协作场景的静默覆盖

### 3. 状态流转保护

- `reviewed` → `polished`：人工编辑后需重新审核
- `published` → `revision`：修订版保护已发布内容
- 终态 guard 不被破坏

### 4. 前端组件解耦

- 编辑器、版本面板、对比视图、返修面板独立组件
- 通过 props 和回调通信
- 易于测试和维护

### 5. Stub Provider 确定性

- 本地返修返回固定文本
- 测试不依赖真实 LLM
- 快速回归验证

## 文件清单

### 后端新增文件

```
novel_factory/db/migrations/029_v5_7_chapter_version_fields.sql
novel_factory/api/routes/versions.py
tests/test_v57_chapter_editing_versions.py
```

### 后端修改文件

```
novel_factory/db/connection.py
novel_factory/db/repositories/chapter.py
novel_factory/api/routes/__init__.py
novel_factory/api/routes/chapter_readonly.py
novel_factory/llm/stub_provider.py
```

### 前端新增文件

```
frontend/src/components/project/ChapterEditorSurface.tsx
frontend/src/components/project/ChapterVersionPanel.tsx
frontend/src/components/project/ChapterDiffViewer.tsx
frontend/src/components/project/__tests__/ChapterEditorSurface.test.tsx
```

### 前端修改文件

```
frontend/src/lib/api.ts
frontend/src/lib/state-labels.ts
frontend/src/components/project/AuthorWritingSurface.tsx
frontend/src/components/project/AuthorWorkbench.tsx
frontend/src/pages/ProjectDetail.tsx
```

## 测试覆盖

### 后端测试（10 个）

1. `test_save_content_creates_manual_edit_version` - 保存创建人工编辑版本
2. `test_published_chapter_cannot_save_directly` - published 章节不能直接保存
3. `test_create_revision_draft_for_published` - 创建 published 修订版
4. `test_version_list_and_detail` - 版本列表和详情
5. `test_version_diff` - 版本对比
6. `test_restore_creates_rollback_version` - 回滚创建 rollback 版本
7. `test_stale_base_version_rejects_overwrite` - 过期版本拒绝覆盖
8. `test_local_revision_returns_candidate` - 局部返修返回候选
9. `test_accept_local_revision_creates_version` - 接受返修创建版本
10. `test_reviewed_save_transitions_to_polished` - reviewed 保存后转为 polished

### 前端测试（6 个）

1. `renders in read mode by default` - 默认阅读模式
2. `switches to edit mode when edit button clicked` - 切换编辑模式
3. `shows published protection for published chapters` - published 保护
4. `shows unsaved indicator when content is modified` - 未保存提示
5. `renders version list` - 版本列表渲染
6. `shows empty state when no versions` - 空状态展示

## 遗留问题

### 1. 真实项目验收待执行

- 需要在 `novel_3v2o` 真实项目中执行 11 步验收流程
- 验证前端交互和后端 API 集成

### 2. 局部返修 Agent 能力复用

- 当前使用 stub provider 返回固定文本
- 未来可接入 Author/Polisher Agent
- 需要设计 prompt 和上下文传递

### 3. 版本元数据扩展

- `metadata` 字段当前为空
- 可扩展存储返修指令、风险提示等
- 为后续分析和复盘提供数据

### 4. 前端富文本编辑

- 当前使用原生 textarea
- 选区 API 功能有限
- 未来可考虑引入轻量级编辑器

## 下一步建议

### 短期（v5.7.x）

1. 完成 `novel_3v2o` 真实项目验收
2. 补充版本元数据字段使用
3. 优化版本对比 UI（段落级别 diff）
4. 增加版本搜索和过滤

### 中期（v5.8）

1. 接入真实 LLM 局部返修
2. 版本标签和分类管理
3. 版本导出和分享
4. 协作编辑冲突解决

### 长期（v6.0）

1. Creator Knowledge Base 集成
2. RAG 辅助写作
3. 长篇记忆一致性检查
4. AgentOps 复盘和优化

## 结论

v5.7 成功完成了个人创作工作台的第一段创作者闭环，建立了正文编辑、版本管理、对比回滚、局部返修的最小可行能力。所有测试通过，guard 和恢复语义保持稳定，为后续 AI 辅助写作能力扩展打下了坚实基础。

**推荐**: 声明 v5.7 为新的稳定基线。
