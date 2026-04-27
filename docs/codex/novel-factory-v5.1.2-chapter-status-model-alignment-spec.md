# v5.1.2 Chapter & Status Model Alignment 规格

## 目标

统一章节状态模型，修复因 `chapter.status`、`workflow_run.status`、`production_queue.status` 混用导致的 WebUI 无法正确生成章节问题。

## 背景问题

v5.1.1 及之前版本存在三套状态混用：

1. **`chapter.status`**（章节生产状态）：`pending` / `planned` / `scripted` / `drafted` / `polished` / `reviewed` / `published` / `blocking` / `revision`
2. **`workflow_run.status`**（单次运行状态）：`running` / `completed` / `blocked` / `failed`
3. **`production_queue.status`**（队列状态）：`pending` / `running` / `completed` / `failed`
4. **`acceptance.status`**（验收状态）：`pass` / `partial` / `missing`

### 冲突根源

- API `onboarding` 创建初始章节时使用 `status="pending"`
- Dispatcher `STATUS_ROUTE` 不认识 `pending`，导致 `pending` 章节运行时走 `__stop__`
- `/api/run/chapter` 使用 `result.get("status", "completed")`，但 dispatcher 返回的是 `chapter_status` / `requires_human` / `error`
- 前端 Run 页面默认章节号用 `chapter_count + 1`，导致选择不存在的章节

### 影响

- 用户在 WebUI 创建项目后，点击“生成第 1 章”，`workflow_run.status` 被标记为 `blocked`
- 前端可能显示“章节生成完成”，但实际 workflow_run 是 `blocked`
- 对已有 10 章的项目，Run 页面默认填 11，但第 11 章不存在

## 状态模型定义

### 章节生产状态（`chapter.status`）

| 状态 | 含义 | 中文 |
|------|------|------|
| `planned` | 已规划，等待编剧/大纲 | 已规划 |
| `scripted` | 已编剧，等待正文作者 | 已编剧 |
| `drafted` | 已起草，等待润色 | 已起草 |
| `polished` | 已润色，等待编辑 | 已润色 |
| `reviewed` | 已审核，等待发布 | 待审核 |
| `published` | 已发布，终态 | 已发布 |
| `blocking` | 已阻塞，需要人工处理 | 已阻塞 |
| `revision` | 返修中 | 返修中 |
| `pending` | **旧 API/队列残留状态，兼容为 planned** | 等待中 |

### 工作流运行状态（`workflow_run.status`）

| 状态 | 含义 | 中文 |
|------|------|------|
| `running` | 正在运行 | 运行中 |
| `completed` | 正常结束 | 已完成 |
| `blocked` | 被阻塞（需人工） | 已阻塞 |
| `failed` | 失败 | 失败 |

### 队列状态（`production_queue.status`）

| 状态 | 含义 |
|------|------|
| `pending` | 等待执行 |
| `running` | 正在执行 |
| `completed` | 已完成 |
| `failed` | 失败 |

**重要区分**：
- `chapter.status` 用 `blocking`（已阻塞）
- `workflow_run.status` 用 `blocked`（已阻塞）
- `production_queue.status` 用 `pending`（等待中）
- 三者**不得混用**

## 修复内容

### 一、API onboarding 初始章节状态

文件：`novel_factory/api/routes/onboarding.py`

- 创建初始章节时，`status` 从 `"pending"` 改为 `"planned"`
- 新建项目后 `/api/projects/{project_id}/workspace` 返回的 chapters 显示 `planned`
- 不影响 `production_queue` 的 `pending` 状态

### 二、兼容旧 pending 章节

文件：`novel_factory/dispatch/base.py`

在 `STATUS_ROUTE` 中添加：
```python
"pending": "screenwriter",  # Compatibility: old Web API initial status
```

底层兼容方案，使已有数据库中 `pending` 状态的章节可以继续运行。

### 三、修复 /api/run/chapter 响应结构

文件：`novel_factory/api/routes/run.py`

返回结构改为：
```json
{
  "run_id": "uuid",
  "project_id": "my-novel",
  "chapter": 1,
  "workflow_status": "completed",
  "chapter_status": "published",
  "status": "completed",
  "requires_human": false,
  "error": null,
  "llm_mode": "stub",
  "message": "章节生成完成"
}
```

规则：
- `error` 存在 → `workflow_status = "failed"`, `message = "章节生成失败"`
- `requires_human` 或 `chapter_status == "blocking"` → `workflow_status = "blocked"`, `message = "章节生成被阻塞，需要人工处理"`
- `chapter_status == "published"` 或正常结束 → `workflow_status = "completed"`
- `status` 字段保留，等于 `workflow_status`，兼容旧前端

### 四、修复 ProjectDetail recent_runs 展示

文件：`frontend/src/pages/ProjectDetail.tsx`

- `recent_runs` 显示 `workflow_run.status`，通过 `StatusBadge` 中文化
- `blocked` 且 `error_message` 为空时，显示兜底说明：
  > “工作流被阻塞，请检查章节状态或重新运行。”

### 五、修复 Run 页面章节选择逻辑

文件：`frontend/src/pages/Run.tsx`

1. 加载项目后调用 `/api/projects/{project_id}/workspace` 获取 `chapters`
2. 章节选择改为 `<select>` 下拉，选项来自已有 chapters
3. 默认选择第一个可生成章节（状态优先级：`planned` > `pending` > `scripted` > `drafted` > `polished` > `revision`）
4. 没有可生成章节时显示“暂无可生成章节”，提供“返回项目工作台”和“创建新项目”入口
5. 项目信息区显示：当前章节数、可生成章节数、下一可生成章节
6. 生成成功后刷新 workspace 数据
7. 结果面板显示 `workflow_status` / `chapter_status` / `requires_human` / `error` 中文

### 六、统一前端状态中文映射

文件：`frontend/src/lib/i18n.ts`

新增：
- `tWorkflowStatus(status)` — 翻译 workflow_run 状态
- `tChapterStatus(status)` — 翻译 chapter 生产状态

避免 `workflow blocked` 和 `chapter blocking` 混淆。

## 测试覆盖

新增测试文件：`tests/test_v512_chapter_status_alignment.py`

后端：
1. `test_new_project_chapters_are_planned` — onboarding 新建项目后章节状态为 planned
2. `test_pending_in_status_route` — STATUS_ROUTE 包含 pending 映射
3. `test_run_chapter_returns_workflow_status` — API 返回 workflow_status、chapter_status、requires_human、error
4. `test_run_chapter_blocked_not_completed_message` — blocked/failed 时 message 不会是“章节生成完成”
5. `test_workflow_run_status_matches_api_status` — DB workflow_run.status 与 API workflow_status 一致

前端/源码质量：
6. `test_run_uses_workspace_not_chapter_count_plus_one` — Run.tsx 使用 workspace，不用 chapter_count + 1
7. `test_run_chapter_selector_is_select` — 章节号使用 select 元素
8. `test_run_result_shows_workflow_and_chapter_status` — 结果面板显示 workflow_status/chapter_status
9. `test_project_detail_blocked_fallback` — ProjectDetail blocked 有中文兜底说明

## 验收命令

```bash
./scripts/v51_smoke_acceptance.sh
python3 -m pytest -q
cd frontend && npm run typecheck
cd frontend && npm run build
```

## 禁止范围

- 不恢复 Jinja WebUI
- 不引入登录/权限
- 不引入 Redis/Celery/WebSocket
- 不做真实 LLM 调用测试
- 不提交真实 API key
- 不提交 frontend/node_modules、frontend/dist、config/acceptance.yaml、stderr.txt

## 测试基线

- v5.1.1 基线：1255/1255 passed
- v5.1.2 新增测试：9 个
- 预期新基线：1264/1264 passed
