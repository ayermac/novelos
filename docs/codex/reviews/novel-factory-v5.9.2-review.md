# Novelos v5.9.2 UI Controls Standardization Review

## Review 结论

通过。

v5.9.2 达成“小版本控件统一”的目标：新增 UI 控件层，迁移主要设置页、项目资料页、运行页、章节编辑器和 Skill Console 中的原生表单/表格观感，同时未改动后端行为。

## 检查项

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 统一控件层存在 | 通过 | `frontend/src/components/ui/` 已新增完整控件 |
| 表单控件不再裸露浏览器默认样式 | 通过 | 主路径迁移到 `TextInput/Select/TextArea/Checkbox/...` |
| 表格统一 | 通过 | 主要表格迁移到 `DataTable`，Review 后补迁移 `RunsModule` |
| 原生浏览器弹窗 | 通过 | 产品代码使用 `useAppDialog`，无 `window.alert/confirm/prompt` |
| 可访问性 | 通过，已修复 | `FormField` 自动关联 label/id/error 描述 |
| 移动触控/焦点态 | 通过 | 控件层具备 focus ring、disabled、44px 基础高度 |
| 业务行为不变 | 通过 | 未修改 API payload、工作流、Agent、数据库 |
| 测试验证 | 通过 | 前端 146 passed，smoke 后端通过 |

## Review 发现与修复

### P1: FormField 未自动关联 label 和控件

问题：

迁移中大量使用：

```tsx
<FormField label="模型">
  <Select ... />
</FormField>
```

但 `FormField` 原实现只有显式传 `htmlFor` 时才关联 label，导致无障碍语义不完整。

修复：

- `FormField` 使用 `useId()` 自动生成控件 id；
- 对单个有效 React 子元素自动注入：
  - `id`
  - `aria-describedby`
  - `aria-invalid`
  - `invalid`
- helper/error 自动生成描述 id。

验证：

- 新增 `auto-associates form field labels and error descriptions with a single child control` 测试。

### P2: RunsModule 仍使用手写原生 table

问题：

`frontend/src/components/project/RunsModule.tsx` 仍有手写 `<table>` 和大量 inline table style。

修复：

- 迁移为统一 `DataTable`。

### P3: Checkbox/Switch 隐藏 input 缺少定位容器

问题：

`.ui-check-input` / `.ui-switch-input` 使用 absolute visually-hidden 技法，但父容器没有 `position: relative`。

修复：

- `.ui-check` / `.ui-switch` 增加 `position: relative`。

### P4: Skill Console 左侧导航视觉过重，矩阵列过多

问题：

用户截图反馈 Agent 编排页左侧深色导航与右侧白色控制台割裂，矩阵使用全局 stage 导致列过多、右侧内容被挤压。

修复：

- 左侧导航改为浅色控制台样式，降低色块突兀感。
- 每个 Agent 分组只渲染该组实际涉及的 stage。
- 矩阵列宽和横向滚动提示优化。

验证：

- `SkillVisibilityPanel.test.tsx` 6 passed。
- `npm run typecheck/lint/build` passed。

## 验证结果

```text
npm run typecheck     passed
npm run lint          passed
npm run build         passed
npm run test -- --run 146 passed
python3 scripts/verify.py smoke passed
```

Build 仍有既有 Vite chunk-size warning。
