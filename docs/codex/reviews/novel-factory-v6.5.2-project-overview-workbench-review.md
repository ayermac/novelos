# v6.5.2 Project Overview Workbench Polish 审查

## 审查日期

2026-05-16

## 范围

`frontend/src/components/project/ProjectOverviewModule.tsx` 重构审查。

## 审查项

### 1. v6.5.1 Primitives 使用

| 组件 | 使用位置 | 状态 |
|------|----------|------|
| `LoadingButton` | primary action、AI 补齐按钮 | ✅ 正确 |
| `SkeletonStack` | 今日生产面板 loading、资料准备度 loading | ✅ 正确 |
| `InlineMessage` | auto-fill / arc-plan / recover 反馈 | ✅ 正确 |
| `useToast` | load 错误、操作成功/失败 | ✅ 正确 |

### 2. 交互反馈完整性

| 操作 | pending | success | error | 状态 |
|------|---------|---------|-------|------|
| 初始数据加载 | SkeletonStack | — | toast | ✅ |
| auto-fill | LoadingButton loading | InlineMessage + toast | InlineMessage + toast | ✅ |
| arc-plan | LoadingButton loading (primary) | InlineMessage + toast | InlineMessage + toast | ✅ |
| recover_blocked_run | LoadingButton loading (primary) | InlineMessage + toast | InlineMessage + toast | ✅ |
| generate_chapter (导航) | LoadingButton loading | — | — | ✅ (导航类无需反馈) |

### 3. production-next 行为兼容

- `next_action.key` 映射逻辑未改动。
- `generate_chapter` / `continue_next_chapter` 仍然导航到章节页，不自动触发生成（v6.3 约束保留）。
- `hasRunningWorkflow` 禁用逻辑保留。
- `disconnected` / `isSessionObsolete` / `recovering` 状态处理保留。

### 4. 代码质量

- 未引入新的 `useEffect` 依赖问题。
- `load()` 的 `showToast` 已加入 dependency array。
- `primaryActionLoading` 与 `filling` 状态分离清晰：前者用于 primary action，后者用于 auto-fill。
- `inlineMessage` 替代 `fillResult` 后，类型安全提升（从 `string` 变为 `{ variant, children }`）。

### 5. 测试覆盖

| 测试项 | 覆盖 | 说明 |
|--------|------|------|
| Skeleton loading | ✅ | 验证 `.ui-skeleton-stack` 存在 |
| Next action card | ✅ | 责任方徽章、描述、LoadingButton |
| Context checklist | ✅ | severity 圆点、item label、计数 |
| Primary action success | ✅ | auto-fill 成功 InlineMessage |
| Primary action failure | ✅ | auto-fill 失败 InlineMessage |
| Ready context state | ✅ | 100% 准备度不显示资料缺口 |

### 6. 待改进项（不阻塞本版本）

1. **连续生产按钮未使用 LoadingButton**：advanced controls 区域的"开始连续生产"/"暂停"/"取消"仍使用原生 button，建议 v6.5.3 或 v6.5.5 统一。
2. **Dashboard N+1 问题未解决**：v6.5.2 只改了 Overview，Dashboard 的 N+1 API 调用仍保留。
3. **health-summary 加载错误**：当前 toast 提示较通用，后续可考虑在 UI 中内嵌健康检查失败状态。

## 结论

**通过审查。** v6.5.2 达成"下一步创作驾驶舱"目标，交互基件使用规范，测试覆盖充分，无后端改动，无行为回归。
