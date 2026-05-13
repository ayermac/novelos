# v5.5.13 Wide-Screen Author Workspace IA Fix

## 背景

用户在 2560px+ 宽屏下反馈 WebUI 不适应。此前的 CSS-only 全宽修复未能解决根本原因——问题是信息架构和状态语义，不仅仅是布局宽度。

## 问题清单

1. **Overview 卡片水平拉伸**：宽屏下单卡片拉伸导致信息密度低
2. **ChapterWorkspace 右侧空**：ws-right 区域没有运行详情面板
3. **状态矛盾**：Overview 显示"已暂停"但章节工作流显示"执行中"
4. **CTA 冲突**："继续生成第 3 章"和"重新接入"同时出现
5. **技术状态暴露**：`paused`、`client_disconnected` 等技术状态直接展示给作者
6. **进度误导**："2/10 章"在全书 500 章目标下具有误导性

## 解决方案

### 1. 统一状态映射 (`state-labels.ts`)

新建 `frontend/src/lib/state-labels.ts`，集中管理：

- `tSessionStopLabel(status, stopReason)` — 自动运行 session 状态 → 中文标签
- `tWorkflowNodeLabel(node)` — 工作流节点 → 中文标签
- `tActionKey(key)` — 生产动作键 → 中文标签
- `tStepResult(result)` — 步骤结果 → 中文标签

关键设计：`tSessionStopLabel` 同时接收 `status` 和 `stopReason` 两个参数，因为相同的 `stopReason` 在不同 `status` 下含义不同（如 `paused` + `client_disconnected` vs `paused` + 手动暂停）。

### 2. Overview 双栏布局 (`ProjectOverviewModule.tsx`)

- ≥1440px 时启用 CSS Grid 双栏：左侧主内容 + 右侧 340px 侧栏
- 1920px → 400px 侧栏，2560px → 440px 侧栏
- 主内容区：BookTitleContractCard + 今日生产面板
- 侧栏区：章节进度、创作目标、资料准备度、资料缺口

### 3. 进度拆分

原：`{published}/{total} 章已发布`

新：
- `全书 {published}/{project.total_chapters_planned} 章` — 全书目标（如 500 章）
- `批次 {published}/{stats.total_chapters} 章` — 当前规划批次（如 10 章）

### 4. CTA 消歧

派生 `hasRunningWorkflow` 变量：
- `streamStatus === 'running'` 或 autoResult 有 running 步骤

CTA 逻辑：
- `disconnected && hasRunningWorkflow` → "查看第 N 章实时进度"（链接到章节工作流）
- `disconnected && !hasRunningWorkflow` → "重新接入"
- `!disconnected && paused` → "继续生产"
- `!disconnected` → "连续生产" toggle（始终显示）

### 5. ChapterWorkspace 右侧面板

替换 `ContextSidebar` 为 `RunDetailSidebar`：

- 当前运行：workflow status badge + 当前节点中文名
- 流式指示器：SSE 步骤进度（`isStreaming` 时）
- 错误/停止原因
- 操作按钮：查看运行详情、查看正文、生成本章
- 近期运行列表

### 6. 技术状态隐藏

所有 raw `streamStatus`/`stop_reason` 显示替换为 `tSessionStopLabel`：

- 预算状态面板的"当前状态"和"停止原因"
- 步骤时间线的状态栏
- 阻塞复盘卡片的停止原因
- session 历史记录的状态和停止原因

## 文件变更

| 文件 | 动作 |
|------|------|
| `frontend/src/lib/state-labels.ts` | 新建 |
| `frontend/src/components/project/ProjectOverviewModule.tsx` | 修改 |
| `frontend/src/components/project/ChapterWorkspace.tsx` | 修改 |
| `frontend/src/pages/ProjectDetail.tsx` | 修改（CSS + 移除未使用 props） |
| `frontend/src/components/project/__tests__/v5513-wide-screen-ia.test.tsx` | 新建 |
| `frontend/src/components/project/__tests__/v5511-author-centric.test.tsx` | 修改（适配新标签） |

## 验证

```bash
cd frontend && npm run typecheck   # TypeScript 编译通过
cd frontend && npm run build       # 生产构建通过
cd frontend && npx vitest run      # 46/46 测试通过
```
