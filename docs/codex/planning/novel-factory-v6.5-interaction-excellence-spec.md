# v6.5 Interaction Excellence Spec

## 状态

**v6.5.0 + v6.5.1 已实现。**

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

## 后续版本交给其他 Agent

### v6.5.2：Project Overview Workbench Polish

目标：把项目 Overview 从"信息堆叠"改为"下一步创作驾驶舱"。

重点：

- 顶部 next action 变成明确任务卡。
- context 缺失项展示为可完成 checklist。
- auto-fill / genesis / chapter generation 的操作路径收敛。
- loading、empty、error 状态全部使用 v6.5.1 primitives。

### v6.5.3：Chapter Writing Surface Polish

目标：让章节正文页更像作者写作台，而不是运行详情页。

重点：

- 生成、发布、返修、恢复按钮统一 pending。
- 正文、质量诊断、工作流过程稿之间的切换更顺滑。
- 空章节状态给出明确下一步。

### v6.5.4：Agent Process Narrative

目标：把 Agent 执行过程从日志变成用户能理解的创作过程。

重点：

- 节点运行时显示"正在规划/正在写作/正在润色/正在审核"。
- fallback、跳过、guard、quality warning 显示为人类可读事件。
- 复用 v6.1 execution events，不改后端拓扑。

### v6.5.5：Settings & Desktop Runtime Polish

目标：把 LLM 配置、API key、sidecar 状态、诊断包导出做成更自然的桌面设置体验。

重点：

- 未配置 real LLM 时给出清晰引导。
- 安全存储状态、重启 sidecar、连接测试统一反馈。
- 桌面独占功能在 WebUI 中降级清楚。

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
