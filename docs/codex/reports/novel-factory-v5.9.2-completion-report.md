# Novelos v5.9.2 UI Controls Standardization 完成报告

## 结论

v5.9.2 已完成。该版本新增统一前端 UI 控件层，并迁移主要产品路径中的原生浏览器表单/表格观感。

本版本为前端体验稳定化版本，不涉及后端 API、数据库、工作流、Agent 或 LLM 行为变更。

## 核心交付

新增统一控件目录：

```text
frontend/src/components/ui/
```

新增控件：

- `FormField`
- `TextInput`
- `NumberInput`
- `TextArea`
- `Select`
- `Checkbox`
- `Switch`
- `SegmentedControl`
- `DataTable`
- `EmptyState`
- `InlineMessage`
- `Spinner`
- `ui.css`
- `index.ts`

## 迁移范围

已迁移主要页面/模块：

- `frontend/src/components/settings/SkillVisibilityPanel.tsx`
- `frontend/src/components/settings/SettingsConsoleSections.tsx`
- `frontend/src/components/settings/RunHealthPanel.tsx`
- `frontend/src/pages/Onboarding.tsx`
- `frontend/src/pages/Run.tsx`
- `frontend/src/pages/Review.tsx`
- `frontend/src/pages/Style.tsx`
- `frontend/src/components/project/ChapterEditorSurface.tsx`
- `frontend/src/components/project/ProjectOverviewModule.tsx`
- `frontend/src/components/project/RunsModule.tsx`
- `frontend/src/components/project/CharactersModule.tsx`
- `frontend/src/components/project/WorldSettingsModule.tsx`
- `frontend/src/components/project/FactionsModule.tsx`
- `frontend/src/components/project/OutlinesModule.tsx`
- `frontend/src/components/project/InstructionsModule.tsx`
- `frontend/src/components/project/PlotHolesModule.tsx`
- `frontend/src/components/project/ProjectSettingsModule.tsx`
- `frontend/src/components/project/FactLedgerModule.tsx`
- `frontend/src/components/project/ProjectSkillOverridesModule.tsx`
- `frontend/src/components/project/GenesisModule.tsx`

## Review 后补充修复

Review 发现并修复：

1. `FormField` 在未显式传入 `htmlFor/id` 时，label 与控件没有语义关联。
   - 修复：`FormField` 自动为单个子控件注入 `id`、`aria-describedby`、`aria-invalid` 和 `invalid`。
   - 测试：新增自动关联和错误描述测试。
2. `RunsModule` 仍保留手写原生 table。
   - 修复：迁移为统一 `DataTable`。
3. `Checkbox/Switch` 的隐藏 input 没有相对定位容器。
   - 修复：为 `.ui-check` / `.ui-switch` 增加 `position: relative`。

## 验证结果

前端：

```text
npm run typecheck     passed
npm run lint          passed
npm run build         passed
npm run test -- --run 146 passed
```

后端 smoke：

```text
python3 scripts/verify.py smoke
13 passed + 12 passed
```

说明：`npm run build` 仍保留既有 Vite chunk-size warning，不影响构建完成。

## 原生控件扫描

扫描命令：

```bash
rg "<input|<select|<textarea|<table|data-table|form-control|window\\.alert|window\\.confirm|window\\.prompt|alert\\(|confirm\\(|prompt\\(" frontend/src -n
```

剩余命中说明：

- `frontend/src/components/ui/*`：统一控件内部保留原生 input/select/textarea/table，以保留语义和键盘可访问性。
- `frontend/src/components/AppDialog.tsx`：弹窗内部 prompt input，属于对话框实现细节。
- `frontend/src/index.css`：保留 legacy `.form-control` / `.data-table` 兼容样式，迁移页面不再依赖。
- `dialog.alert/confirm/prompt`：均为 `useAppDialog` 站内弹窗调用，不是浏览器原生弹窗。
- 测试文件中的命中为断言或测试描述。

## 残留风险

- `index.css` 仍保留 legacy 表单/表格样式，后续可以在确认无引用后删除。
- UI 控件层当前是轻量组件库，未引入 storybook 或视觉回归截图。
- 部分页面仍保留 inline layout style，但原生控件观感已收口。

