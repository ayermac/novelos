# v6.5 Interaction Excellence Spec

## 状态

**v6.5.6 已封版。**

本版本回应桌面客户端当前"像后台系统"的问题。目标不是重做视觉品牌，而是把创作者工作台的操作反馈、等待状态、错误恢复、过程感和页面节奏提升到可持续迭代的标准。

## 设计原则

1. **动作必须有反馈**：任何异步操作都要有 pending 状态、成功/失败反馈，避免用户反复点击或猜测是否生效。
2. **等待不能是空白**：超过瞬时反馈的等待需要 skeleton、进度语义或清晰的状态文案。
3. **失败要可恢复**：错误提示需要说明发生了什么、下一步能做什么，不应只显示原始异常。
4. **桌面体验优先**：客户端是第一使用场景，交互密度可以高，但操作路径必须清楚。
5. **动效克制**：使用 150-300ms 的状态动效和焦点反馈；遵守 `prefers-reduced-motion`。
6. **底座先行**：先补统一组件，再按页面逐步替换，不做一次性大爆改。

## v6.5.0：Interaction Audit & UX Spec

状态：**已实现**

交付：

- 明确 v6.5 目标从 Agent Evidence UX 前置调整为 Interaction Excellence。
- 记录当前主要问题：
  - 异步按钮 pending 表达不统一。
  - 页面级等待状态偏静态。
  - 操作成功/失败缺少统一 toast。
  - 章节工作台、项目 Overview、设置页仍有后台感。
  - 视觉组件已有基础，但缺少跨页面交互协议。
- 规划 v6.5 后续拆分：
  - v6.5.1：交互基础组件与样板接入。
  - v6.5.2：项目 Overview 工作台体验。
  - v6.5.3：章节写作面板体验。
  - v6.5.4：Agent 过程叙事与执行反馈。
  - v6.5.5：Settings / Desktop runtime polish。

## v6.5.1：Interaction Primitives

状态：**已实现**

目标：建立后续页面重构共用的交互底座。

新增组件：

- `ToastProvider` / `useToast`
  - 支持 success / info / warning / danger。
  - 支持自动关闭和手动关闭。
  - 在孤立组件测试中安全 no-op，避免破坏既有测试。
- `LoadingButton`
  - 统一按钮 pending、disabled、`aria-busy`、spinner 和 loading text。
  - 复用现有 `.btn` 视觉系统。
- `Skeleton` / `SkeletonStack`
  - 用于页面片段加载，避免"空白等待"。
  - 遵守 reduced-motion。

样板接入：

- `App.tsx` 全局挂载 `ToastProvider`。
- `Onboarding.tsx`
  - 创建项目按钮改用 `LoadingButton`。
  - 创建成功/失败使用 toast。
  - 错误提示改用 `InlineMessage`。
- `QualityDiagnosisPanel.tsx`
  - 首次诊断加载改用 `SkeletonStack`。
  - 重新诊断按钮改用 `LoadingButton`。
  - 诊断失败/刷新成功使用 toast。

CSS 交互协议：

- 控件 active/focus/pending 状态统一。
- Toast 固定在右下角，适配窄屏宽度。
- Skeleton 使用轻量 shimmer，reduced-motion 下关闭动画。
- loading button 在 primary/secondary 场景中保持可读 spinner。

## 页面级体验升级

### v6.5.2：Project Overview Workbench Polish

状态：**已实现**

目标：把项目 Overview 从"信息堆叠"改为"下一步创作驾驶舱"。

重点：

- 顶部 next action 变成明确任务卡：责任方徽章（AI/人工/系统）+ 动作标题 + 原因描述 + LoadingButton 主操作。
- context 缺失项展示为可扫描 checklist：左侧 severity 圆点 + label + 手动编辑按钮，侧边栏补齐按钮使用 LoadingButton。
- auto-fill / genesis / chapter generation 的操作路径收敛，primary action 统一使用 LoadingButton 并带有 loading 状态。
- loading、empty、error 状态全部使用 v6.5.1 primitives：SkeletonStack 替换文本 loading、InlineMessage 替换字符串结果、toast 统一异步反馈。

已实现文件：

- `frontend/src/components/project/ProjectOverviewModule.tsx`
- `frontend/src/components/project/__tests__/ProjectOverviewModule.test.tsx`

验收标准：

- 前端 typecheck / lint / build / vitest 全通过。
- 新 ProjectOverviewModule 测试覆盖 skeleton loading、next action card、context checklist、操作反馈。
- load() 错误使用 toast 反馈，不再静默失败。
- auto-fill、arc-plan、recover_blocked_run 操作使用 InlineMessage + toast 双通道反馈。
- production-next 行为完全兼容，不改后端。

### v6.5.3：Chapter Writing Surface Polish

状态：**已实现**

目标：让章节正文页更像作者写作台，而不是运行详情页。

重点：

- 生成、发布、返修、恢复按钮统一使用 `LoadingButton`，提供一致的 pending 体验（`aria-busy`、spinner、loading text、disabled）。
- 章节内容 loading 使用 `SkeletonStack` 替代纯文本"加载中..."，避免布局跳动。
- 空章节状态给出明确下一步：标题 + 图标 + 可执行步骤列表（编剧规划 → 执笔撰写 → 润色审核）+ `LoadingButton` 生成入口。
- workflow running 状态保持现有区分（启动中 / 生成中 / 等待刷新 / 疑似卡住），恢复按钮统一使用 `LoadingButton`。
- auto-fill 操作接入 `InlineMessage` 内联反馈 + `toast` 全局通知。

已实现文件：

- `frontend/src/components/project/AuthorWritingSurface.tsx`
- `frontend/src/components/project/__tests__/AuthorWorkbench.test.tsx`

验收标准：

- 前端 typecheck / lint / build / vitest 全通过。
- AuthorWorkbench 测试兼容，新增测试覆盖 skeleton loading、空状态引导、LoadingButton pending 状态。
- 不改后端 workflow，不改章节生成逻辑。

### v6.5.4：Agent Process Narrative

状态：**已实现**

目标：把 Agent 执行过程从日志变成用户能理解的创作过程。

重点：

- 节点运行时显示节点专属叙事文案：
  - planner → "正在规划章节结构..."
  - screenwriter → "正在编排场景与情节..."
  - author → "正在撰写章节正文..."
  - polisher → "正在润色文字表达..."
  - editor → "正在审核内容质量..."
  - memory_curator → "正在整理章节记忆..."
  - 其他节点也有对应叙事。
- AuthorAgentPanel 右侧面板根据 currentNode 显示叙事 action-label 和详细 action-desc（如"AI 正在分析章节目标、角色关系和伏笔，规划本章结构。"）。
- WorkflowTimeline running 状态且没有日志时，显示节点专属叙事而非通用"节点运行中..."。
- streaming SSE 步骤在 AuthorAgentPanel 中 running 时显示叙事文案。
- AuthorAgentPanel 按钮统一替换为 `LoadingButton`，错误显示使用 `InlineMessage`。
- fallback、跳过、guard 等事件类型通过 `EVENT_NARRATIVE` 映射提供人类可读标签。

已实现文件：

- `frontend/src/lib/state-labels.ts` — 新增 `WORKFLOW_NODE_NARRATIVE`、`EVENT_NARRATIVE` 及对应翻译函数
- `frontend/src/components/project/AuthorAgentPanel.tsx` — 叙事文案 + LoadingButton + InlineMessage
- `frontend/src/components/project/AuthorWritingSurface.tsx` — WorkflowBody running 描述叙事化
- `frontend/src/components/WorkflowTimeline.tsx` — running 空日志时显示节点叙事
- `frontend/src/components/__tests__/WorkflowTimeline.test.tsx` — 新增叙事测试
- `frontend/src/components/project/__tests__/AuthorWorkbench.test.tsx` — 新增 Agent 面板叙事测试

验收标准：

- 前端 typecheck / lint / build / vitest 全通过。
- WorkflowTimeline 测试覆盖 running 节点叙事、fallback 事件标签。
- AuthorWorkbench 测试覆盖 AuthorAgentPanel 节点叙事（author/planner/streaming）。
- 不改后端 workflow 拓扑，不改 Agent prompt。

### v6.5.5：Settings & Desktop Runtime Polish

状态：**已实现**

目标：把 LLM 配置、API key、安全存储、sidecar 状态、诊断包导出做成更自然的桌面设置体验。

重点：

- 桌面模式与 WebUI 模式明确区分，浏览器模式下桌面独占功能给出清晰降级提示。
- 未配置 real LLM 时，设置页给出清晰状态和下一步引导（演示模式 badge、配置草案提示）。
- API Key 保存/删除/连接测试/重启 sidecar 全部接入 `LoadingButton + toast`，操作反馈即时可感知。
- runtime info、日志路径、数据目录、诊断包导出更可读（grid 布局、状态徽章、路径断行）。
- 不暴露明文 API Key，输入框使用 `type="password"`，状态仅显示"已配置/未配置"。
- 不改变 `safeStorage` 安全模型，配置文件中仅保留环境变量名。

已实现文件：

- `frontend/src/components/settings/SettingsConsoleSections.tsx` — DesktopRuntimeSection 骨架屏 + LoadingButton + toast + InlineMessage；DesktopApiKeyCard 安全存储交互；ConfigDraftSection 复制草案 toast
- `frontend/src/components/desktop/DesktopFirstRunSetup.tsx` — 全部 action button 替换为 LoadingButton，操作结果使用 toast，错误与测试结果使用 InlineMessage
- `frontend/src/components/ui/LoadingButton.tsx` — 扩展 variant 类型支持 `warning` / `danger`
- `frontend/src/components/desktop/__tests__/DesktopFirstRunSetup.test.tsx` — 新增 v6.5.5 LoadingButton loading 态、IPC 调用测试

验收标准：

- 前端 typecheck / lint / build / vitest 全通过。
- SettingsConsoleSections 中桌面运行时加载态使用 SkeletonStack，重启/导出诊断使用 LoadingButton + toast。
- DesktopApiKeyCard 保存/删除使用 LoadingButton，成功/失败使用 InlineMessage + toast 双通道反馈。
- DesktopFirstRunSetup 所有异步操作（保存配置、保存 Key、测试连接、重启服务）均有 loading 态和 toast 反馈。
- 浏览器模式下 DesktopRuntimeSection、DesktopConfigSection 明确提示"仅桌面应用可用"。
- 不改动后端 desktop.py API 行为，safeStorage 安全模型保持不变。

### v6.5.6：Interaction Excellence Closure

状态：**已实现，v6.5 已封版**

目标：对 v6.5.0～v6.5.5 的交互体验升级做最终收口，确认交互底座使用一致、文档真相源同步、回归验证通过。

交付：

- 补齐 v6.5.5 未提交改动并修复 review 中发现的 `.btn-warning` 样式缺失。
- 修复 `DesktopFirstRunSetup.test.tsx` 中 v6.5.5 新增测试未初始化 desktop bridge 的问题。
- 新增 v6.5.6 完成报告与最终 review。
- 更新 `docs/codex/README.md` 当前基线。
- 更新桌面客户端规划中的 v6.5 状态。

最终结论：

- v6.5 不改变后端 workflow、Agent prompt、数据库 schema 或 safeStorage 安全模型。
- v6.5 的主要价值是将已有能力产品化为可理解、可恢复、可反馈的创作者工作台体验。
- 后续 Agent Evidence UX 和 Structured Memory Canonicalization 顺延为下一阶段。

## 非目标

- 不做全新设计系统重写。
- 不做营销 landing page。
- 不改后端 workflow 拓扑。
- 不改 Agent prompt / quality gate。
- 不做 Agent Evidence 深度溯源，后续单独规划。

## 验收标准

- 新 primitives 有组件测试覆盖。
- 前端 typecheck / lint / build / vitest 全通过。
- 样板页面不破坏既有流程。
- 用户执行项目创建或质量诊断时能看到明确 pending / success / error。
- reduced-motion 下不会强制播放 skeleton/toast 动画。
- v6.5.6 封版时 frontend、desktop、backend smoke 验证通过。
