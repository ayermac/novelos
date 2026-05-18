# v6.5.5 Settings & Desktop Runtime Polish 评审

## 评审日期

2026-05-16

## 评审范围

- `frontend/src/components/settings/SettingsConsoleSections.tsx`
- `frontend/src/components/desktop/DesktopFirstRunSetup.tsx`
- `frontend/src/components/ui/LoadingButton.tsx`
- `frontend/src/components/desktop/__tests__/DesktopFirstRunSetup.test.tsx`

## 检查清单

### 功能正确性

- [x] 桌面模式与 WebUI 模式明确区分（`isDesktop` 检测 + 浏览器模式降级提示）
- [x] 未配置 real LLM 时，SettingsOverviewSection 显示演示模式 badge 和配置引导
- [x] DesktopRuntimeSection loading 态使用 SkeletonStack（4 行）
- [x] DesktopRuntimeSection 重启 sidecar 使用 LoadingButton + toast 反馈
- [x] DesktopRuntimeSection 导出诊断包使用 LoadingButton + toast 反馈
- [x] DesktopApiKeyCard 保存 API Key 使用 LoadingButton + InlineMessage + toast 双通道
- [x] DesktopApiKeyCard 删除 API Key 使用 LoadingButton variant="danger" + 确认对话框
- [x] DesktopApiKeyCard 输入框使用 `type="password"`，不暴露明文
- [x] ConfigDraftSection "复制草案"使用 LoadingButton + toast 反馈
- [x] ConfigDraftSection 验证结果使用 InlineMessage
- [x] DesktopFirstRunSetup 保存配置按钮使用 LoadingButton，有 loading 态
- [x] DesktopFirstRunSetup 保存 API Key 按钮使用 LoadingButton，成功清空输入
- [x] DesktopFirstRunSetup 测试连接按钮使用 LoadingButton，结果使用 InlineMessage + toast
- [x] DesktopFirstRunSetup 重启服务按钮使用 LoadingButton variant="warning"

### 向后兼容

- [x] `LoadingButton` props 接口扩展（新增 variant），原有调用不受影响
- [x] `SettingsConsoleSections` 各 section 的 props 接口未变更
- [x] `DesktopFirstRunSetup` props 接口未变更
- [x] 现有测试全部通过（原 184+ 个测试）

### 代码质量

- [x] 未引入新的 TypeScript 类型错误
- [x] 未引入新的 ESLint 警告
- [x] toast 反馈文案使用中文，符合产品语言
- [x] safeStorage 安全模型未改变（配置文件中仍仅保留环境变量名）

### 可访问性

- [x] LoadingButton 自动处理 `aria-busy` 和 `disabled`
- [x] InlineMessage 使用语义化颜色（success/danger/warning）
- [x] API Key 输入框使用 `type="password"`，屏幕阅读器不会读出明文

### 测试覆盖

| 测试用例 | 状态 |
|----------|------|
| DesktopFirstRunSetup browser 模式不渲染 | 已有，通过 |
| DesktopFirstRunSetup 配置不完整时显示引导 | 已有，通过 |
| DesktopFirstRunSetup 配置就绪时不显示引导 | 已有，通过 |
| DesktopFirstRunSetup 从引导进入编辑 | 已有，通过 |
| DesktopFirstRunSetup 选择服务商填充预设 | 已有，通过 |
| DesktopFirstRunSetup 保存配置调用 PUT API | 已有，通过 |
| DesktopFirstRunSetup 保存 Key 调用 IPC | 已有，通过 |
| DesktopFirstRunSetup 跳过引导 | 已有，通过 |
| DesktopFirstRunSetup compact 模式直接渲染表单 | 已有，通过 |
| save config button uses LoadingButton and is disabled while saving | 新增，通过 |
| save key button calls IPC and input is cleared on success | 新增，通过 |

## 发现的问题

### 已处理

1. **LoadingButton variant 类型未包含 warning/danger**
   - `SettingsConsoleSections.tsx` 与 `DesktopFirstRunSetup.tsx` 中使用 `variant="warning"` 和 `variant="danger"` 时，`LoadingButton.tsx` 的 TS 类型未包含这两个值，导致 `npm run typecheck` 报错。
   - 已在 `LoadingButton.tsx` 中将 `variant` 联合类型扩展为包含 `'warning' | 'danger'`。

2. **测试中 container.firstChild 断言失败**
   - 引入 `ToastProvider` 后，即使组件返回 `null`，容器内仍有 Toast 的 portal 节点，导致 `expect(container.firstChild).toBeNull()` 失败。
   - 已将判断组件未渲染的断言改为基于文本查询：`screen.queryByText(/欢迎使用 Novelos 桌面版/).not.toBeInTheDocument()`。

3. **PUT 请求测试需要捕获 loading 状态**
   - 新增测试需要验证按钮在请求 pending 时的 loading 状态。
   - 已手动构造延迟 resolve 的 Promise 作为 `fetchMock` 的 PUT 返回值，在 resolve 前断言按钮处于 "保存中..." 且 disabled。

### 未处理（建议后续跟进）

1. **DesktopRuntimeSection 中部分按钮保持原生 `<button>`**
   - "打开数据目录/配置目录/日志目录"和"刷新"是即时操作，无需异步 loading，保持原生按钮合理。如需视觉统一，可后续给这些按钮也套一层 LoadingButton（loading 永远为 false）。

2. **DesktopFirstRunSetup prompt 按钮未 LoadingButton 化**
   - "开始配置"和"暂时跳过"是状态切换，无异步操作，保持原生按钮合理。

## 结论

**通过评审。** v6.5.5 按 spec 完成了 Settings & Desktop Runtime 的交互体验打磨，桌面与浏览器模式区分清晰，API Key 安全存储交互反馈即时可感知，未引入回归，测试覆盖充分，safeStorage 安全模型保持不变。
