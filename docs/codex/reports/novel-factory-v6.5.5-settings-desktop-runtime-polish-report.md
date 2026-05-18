# v6.5.5 Settings & Desktop Runtime Polish 完成报告

## 状态

- 版本：v6.5.5
- 类型：前端交互体验增强 / 桌面端设置打磨
- 基线：v6.5.1 Interaction Primitives + v6.5.4 Agent Process Narrative
- 完成日期：2026-05-16

## 目标

把 LLM 配置、API key、安全存储、sidecar 状态、诊断包导出整合为更自然的桌面设置体验。

## 改动范围

### 1. SettingsConsoleSections — 桌面运行时区域打磨

**DesktopRuntimeSection：**

- loading 态由文字 "加载中..." 改为 `<SkeletonStack rows={4} />`，避免布局跳动。
- 运行时信息使用 grid 布局（`minmax(240px, 1fr)`），字段包括运行模式、平台、LLM 模式、版本、配置文件、数据库、Sidecar 状态、API 地址、PID、日志路径。
- 健康状态使用顶部 badge（后端正常/后端异常 + 彩色圆点）。
- `handleRestart` / `handleExportDiagnostics` 的 `dialog.alert` 全部替换为 `showToast`，操作结果即时可感知。
- 重启与导出按钮改为 `LoadingButton`，支持 `loadingText="重启中..."` / `"导出中..."`。
- 浏览器模式下显示清晰降级提示："浏览器模式下无法打开本地目录。如需完整桌面功能，请使用 Novelos 桌面应用。"

**DesktopApiKeyCard：**

- 引入 `useToast`，`handleSave` / `handleDelete` 成功后弹出 toast（`tone: 'success'`），失败后弹出 `tone: 'danger'`。
- 保存按钮使用 `LoadingButton variant="primary"`，删除按钮使用 `LoadingButton variant="danger"`。
- 原生 message div 替换为 `<InlineMessage variant={...}>`，提供语义化颜色反馈。
- API Key 输入框保持 `type="password"`，不暴露明文；状态标签仅显示"已安全保存/未配置/来自环境变量"。

**ConfigDraftSection：**

- 新增 `useToast`，"复制草案"使用 `LoadingButton`，点击后弹出 `showToast({ tone: 'success', ... })`。
- 验证结果使用 `InlineMessage` 组件，替代原生 div。

### 2. DesktopFirstRunSetup — 首次运行与配置弹窗打磨

- `handleSaveConfig`、`handleSaveKey`、`handleTest`、`handleRestart` 均增加 `showToast` 反馈，覆盖成功、失败、需重启等场景。
- 所有操作按钮（保存配置、保存 API Key、测试连接、重启本地服务）替换为 `<LoadingButton>`，并正确设置 `loadingText`。
- 错误提示与连接测试结果由原生 div 改为 `<InlineMessage>` 包裹。
- 连接测试成功时 toast 显示延迟信息（如 "连接测试成功 (420ms)"）。

### 3. LoadingButton — 扩展 variant 类型

- `variant` 联合类型扩展为：`'primary' | 'secondary' | 'accent' | 'ghost' | 'warning' | 'danger'`
- 支持 Settings 与 DesktopFirstRunSetup 中 `warning`（重启按钮）和 `danger`（删除 Key 按钮）样式。

### 4. 测试覆盖

**DesktopFirstRunSetup.test.tsx：**

- 所有 render 使用 `Wrapper`（`<ToastProvider><AppDialogProvider>...</AppDialogProvider></ToastProvider>`）包裹。
- 因 Provider 使 `container.firstChild` 不再为 `null`，将相关断言改为 `screen.queryByText(/欢迎使用 Novelos 桌面版/).not.toBeInTheDocument()`。
- 新增 `save config button uses LoadingButton and is disabled while saving`：延迟 resolve PUT 请求，断言出现 "保存中" 且按钮 disabled。
- 新增 `save key button calls IPC and input is cleared on success`：验证 `mockSetApiKey` 被正确调用。

## 文件变更

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `frontend/src/components/settings/SettingsConsoleSections.tsx` | 修改 | DesktopRuntimeSection SkeletonStack + LoadingButton + toast；DesktopApiKeyCard LoadingButton + InlineMessage + toast；ConfigDraftSection 复制草案 toast |
| `frontend/src/components/desktop/DesktopFirstRunSetup.tsx` | 修改 | 全部 action button 替换为 LoadingButton，toast 反馈，InlineMessage 错误/测试结果 |
| `frontend/src/components/ui/LoadingButton.tsx` | 修改 | 扩展 variant 类型支持 warning/danger |
| `frontend/src/components/desktop/__tests__/DesktopFirstRunSetup.test.tsx` | 修改 | 新增 ToastProvider Wrapper，新增 v6.5.5 loading 态和 IPC 调用测试 |
| `docs/codex/planning/novel-factory-v6.5-interaction-excellence-spec.md` | 修改 | 更新 v6.5.5 为已实现 |
| `docs/codex/reports/novel-factory-v6.5.5-settings-desktop-runtime-polish-report.md` | 新增 | 本报告 |
| `docs/codex/reviews/novel-factory-v6.5.5-settings-desktop-runtime-polish-review.md` | 新增 | 评审文档 |

## 验证结果

| 检查项 | 结果 |
|--------|------|
| `cd frontend && npm run typecheck` | 通过 |
| `cd frontend && npm run lint` | 通过 |
| `cd frontend && npm run build` | 通过 |
| `cd frontend && npm run test -- --run` | 通过（含新增 v6.5.5 测试） |
| `cd desktop && npm run typecheck` | 通过 |
| `cd desktop && npm run build` | 通过 |
| `python3 scripts/verify.py smoke` | 通过 |

## 已知限制

- `DesktopRuntimeSection` 中的"打开数据目录/配置目录/日志目录"和"刷新"按钮保持原生 `<button>`，因为它们是即时操作，不需要异步 loading 状态。
- `DesktopFirstRunSetup` 的 prompt/modal 中的"开始配置"和"暂时跳过"按钮保持原生 `<button>`，因为它们是状态切换而非异步操作。
- 诊断包导出路径在 toast 中展示，较长路径可能被截断，但用户可通过"打开日志目录"查看完整文件系统。
