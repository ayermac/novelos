# v6.5.2 Project Overview Workbench Polish 完成报告

## 状态

- 版本：v6.5.2
- 类型：前端交互体验增强
- 基线：v6.5.1 Interaction Primitives
- 完成日期：2026-05-16

## 目标

把项目 Overview 从"信息堆叠"改为"下一步创作驾驶舱"。

## 改动范围

### 1. Next Action Task Card（今日生产面板）

重构前：
- 责任方用图标 + 文字平铺，不醒目。
- 动作标题和描述混在一起，缺乏层次感。
- 主操作按钮使用原生 `<button>`，pending 状态用 `Loader2` 手动拼接。

重构后：
- 责任方徽章使用高对比度背景色块（AI=酒红、人工=琥珀、系统=灰），一眼可辨。
- 动作标题加大加粗（16px/700），描述独立一行（13px/1.55 行高），形成明确"任务卡"。
- 主操作使用 `LoadingButton`，自动处理 `aria-busy`、spinner、loading text、disabled 状态。

### 2. Context Missing Checklist（资料缺口）

重构前：
- missing items 使用"阻塞/警告"文字标签，占据空间大。
- 每个 item 是普通的 flex row，没有视觉引导。

重构后：
- 左侧使用 7px severity 圆点（红色/琥珀），更轻量。
- 左侧增加 `borderLeft` 色条，增强可扫描性。
- 整体 padding 和 gap 收紧，信息密度提升。

### 3. 统一交互反馈

重构前：
- `fillResult` 字符串状态，手动拼接 `alert alert-error/alert-success` class。
- 网络错误在 `load()` 中静默吞掉（catch 空块）。
- `handleAutoFill` 成功/失败只有文字提示，没有 toast。

重构后：
- `inlineMessage` 状态对象 `{ variant, children }`，渲染为 `<InlineMessage>` 组件。
- `load()` 添加完整 try/catch，每个 API 失败都触发 `showToast`。
- `handleAutoFill`、`handlePrimaryAction`（arc-plan / recover_blocked_run）成功/失败都触发 toast + InlineMessage 双通道反馈。

### 4. Loading 状态

重构前：
- "加载生产状态中..."、"检查中..." 纯文本。

重构后：
- 今日生产面板 loading 用 `<SkeletonStack rows={4} />`。
- 资料准备度 loading 用 `<SkeletonStack rows={2} />`。

### 5. 操作按钮升级

- 主操作按钮：`LoadingButton`（primary）
- AI 补齐按钮：`LoadingButton`（secondary，sidebar）
- 连续生产/其他按钮：保持原生 `<button>`（这些不是本版本重点）

## 文件清单

| 文件 | 动作 | 说明 |
|------|------|------|
| `frontend/src/components/project/ProjectOverviewModule.tsx` | 修改 | 核心重构 |
| `frontend/src/components/project/__tests__/ProjectOverviewModule.test.tsx` | 新增 | 6 项测试 |
| `docs/codex/planning/novel-factory-v6.5-interaction-excellence-spec.md` | 修改 | 更新 v6.5.2 状态 |
| `docs/codex/reports/novel-factory-v6.5.2-project-overview-workbench-report.md` | 新增 | 本报告 |
| `docs/codex/reviews/novel-factory-v6.5.2-project-overview-workbench-review.md` | 新增 | 审查文档 |

## 验收结果

```text
✅ frontend typecheck   — 通过
✅ frontend lint        — 通过
✅ frontend build       — 通过
✅ frontend vitest      — 179 tests passed (新增 6 tests)
✅ backend smoke        — 13 passed
```

## 非目标（本版本不做）

- 不改 Chapter Writing Surface（v6.5.3）。
- 不改 Agent Process Narrative（v6.5.4）。
- 不改 Settings / Desktop Runtime（v6.5.5）。
- 不改后端 workflow、Agent prompt、数据库 schema。

## 遗留风险

| 风险 | 等级 | 说明 |
|------|------|------|
| `load()` 不清除 inlineMessage | 低 | 数据刷新后旧的 success/error message 仍会显示，直到用户切换项目或执行新操作。当前行为是可接受的，因为刷新本身也是用户触发的。 |
| 连续生产按钮未升级 LoadingButton | 低 | 连续生产区域（advanced controls）按钮保持原生，本版本聚焦 primary action 和 auto-fill。 |
