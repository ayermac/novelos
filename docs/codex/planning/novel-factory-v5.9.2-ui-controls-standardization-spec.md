# Novelos v5.9.2 UI Controls Standardization 规格

## 状态

- 类型：可执行规划规格
- 状态：planned
- 基线：v5.9.1 Skill Console UX
- 产品目标：清理系统中原生浏览器控件观感，建立统一、专业、可复用的表单/选择/开关/表格/弹窗交互层
- 技术目标：在不改业务行为的前提下，新增前端基础 UI 控件并分批替换散落的原生 input/select/textarea/checkbox/table 样式
- 版本性质：小版本，前端体验稳定化，不做视觉大重构

## 背景

v5.6 到 v5.9.1 已经把作者工作台、工作流可观测、编辑版本、Skill Console 等核心界面逐步拉起来。但目前页面里仍有不少浏览器默认控件和旧式散落样式：

- 原生 `<select>`、`<textarea>`、`<input>` 在不同页面观感不一致；
- 数字输入、checkbox、筛选下拉、表单 label/helper/error 的布局没有统一规范；
- `form-control`、`data-table`、inline style 混用，导致页面质感有时回到“工程表单”；
- 某些页面已经使用 `AppDialog`，但表单和表格还没有对应的统一组件层；
- Skill Console 已经向控制台体验靠拢，其他设置页/项目资料页需要跟上。

这个版本不是重新设计整套 WebUI，而是把原生浏览器控件“收口”为项目自己的组件和样式规范。

## 产品原则

1. 保留 HTML 语义和键盘可访问性，但不暴露浏览器默认视觉。
2. 优先统一作者常用路径：项目资料、设置、Skill、运行恢复、章节编辑。
3. 控件要像创作软件，不像后台 Demo 表单。
4. 小步替换，不改 API，不改数据结构，不引入大型 UI 框架。
5. 所有 loading、disabled、error、empty、focus 状态必须可见。
6. 不使用原生 `alert/confirm/prompt`；继续使用现有 `AppDialog`。

## 非目标

- 不重构整体信息架构。
- 不重做 Author Workbench 三栏布局。
- 不引入 shadcn、MUI、Ant Design 等重型组件库。
- 不替换为富文本编辑器。
- 不做暗色/亮色主题系统重构。
- 不处理后端工作流、Agent、LLM、数据库逻辑。
- 不把所有页面一次性改成全新视觉，只统一控件层和高频页面。

## 当前扫描结果

初步扫描命令：

```bash
rg "window\\.alert|window\\.confirm|alert\\(|confirm\\(|prompt\\(|<select|<textarea|<input|type=\"checkbox\"|type=\"radio\"|type=\"number\"|className=\"form-control\"|data-table" frontend/src -n
```

结论：

1. 原生浏览器弹窗基本已替换为 `useAppDialog()`，不是主要问题。
2. 主要问题集中在表单控件、checkbox、select、textarea、number input 和 table。
3. 涉及页面包括：
   - `frontend/src/pages/Onboarding.tsx`
   - `frontend/src/pages/Run.tsx`
   - `frontend/src/pages/Review.tsx`
   - `frontend/src/pages/Style.tsx`
   - `frontend/src/components/settings/*`
   - `frontend/src/components/project/*Module.tsx`
   - `frontend/src/components/project/ChapterEditorSurface.tsx`
   - `frontend/src/components/project/ProjectOverviewModule.tsx`
4. `SkillVisibilityPanel.tsx` 已有 v5.9.1 专属样式，但仍有 `select/textarea/form-control/data-table` 可纳入统一控件层。

## 核心交付

### 1. 新增统一 UI 控件层

新增目录建议：

```text
frontend/src/components/ui/
```

建议组件：

```text
FormField.tsx
TextInput.tsx
NumberInput.tsx
TextArea.tsx
Select.tsx
Checkbox.tsx
Switch.tsx
SegmentedControl.tsx
DataTable.tsx
EmptyState.tsx
InlineMessage.tsx
Spinner.tsx
ui.css
index.ts
```

最低要求：

1. 所有组件必须支持 `disabled`、`aria-*`、`className`、`id/name` 透传。
2. `FormField` 统一 label、helper、error、required、布局间距。
3. `Select` 要有统一外观、明确 focus、disabled、error 状态；不要求自绘下拉菜单，允许保留原生选择行为但隐藏默认粗糙样式。
4. `Checkbox/Switch` 必须替换默认 checkbox 视觉，同时保留原生 input 语义。
5. `DataTable` 统一表头、行 hover、空状态、横向滚动容器和紧凑密度。
6. `Spinner/InlineMessage` 用于处理请求中、错误、成功提示，避免按钮只变文案。

### 2. 替换高频页面原生控件

第一批必须替换：

```text
frontend/src/components/settings/SkillVisibilityPanel.tsx
frontend/src/components/settings/SettingsConsoleSections.tsx
frontend/src/components/settings/RunHealthPanel.tsx
frontend/src/pages/Onboarding.tsx
frontend/src/pages/Run.tsx
frontend/src/pages/Review.tsx
frontend/src/components/project/ChapterEditorSurface.tsx
frontend/src/components/project/ProjectOverviewModule.tsx
```

第二批建议替换：

```text
frontend/src/components/project/CharactersModule.tsx
frontend/src/components/project/WorldSettingsModule.tsx
frontend/src/components/project/FactionsModule.tsx
frontend/src/components/project/OutlinesModule.tsx
frontend/src/components/project/InstructionsModule.tsx
frontend/src/components/project/PlotHolesModule.tsx
frontend/src/components/project/ProjectSettingsModule.tsx
frontend/src/components/project/FactLedgerModule.tsx
frontend/src/components/project/ProjectSkillOverridesModule.tsx
frontend/src/pages/Style.tsx
```

替换要求：

1. 不改变表单字段、保存逻辑、API payload。
2. 不改变测试依赖的用户可见中文文案，除非当前文案本身是内部技术词。
3. 旧 `form-control` 允许短期保留，但新代码不能继续新增。
4. 旧 `data-table` 应逐步替换为 `DataTable` 或统一 `.ui-data-table`。
5. 页面内大量 inline style 的表单/表格样式应迁移到组件样式或局部 CSS。

### 3. 统一交互状态

所有替换后的控件必须满足：

1. `focus-visible` 有明显焦点环。
2. `disabled` 不仅颜色变淡，还不可点击，并有 cursor 反馈。
3. `loading` 按钮或区域显示 spinner/loading 状态。
4. 错误信息靠近对应字段或操作区域，不只显示在页面顶部。
5. 搜索框、筛选器、矩阵控件、数字输入在移动端不溢出。
6. checkbox/switch 不只靠颜色表达状态，要有位置/图形变化。

### 4. 原生浏览器弹窗兜底检查

虽然当前主要问题不是弹窗，但本版本必须加一条验收：

```bash
rg "window\\.alert|window\\.confirm|window\\.prompt|alert\\(|confirm\\(|prompt\\(" frontend/src -n
```

允许项：

- 测试文件中用于断言“不使用原生弹窗”的 mock；
- `AppDialog` 内部实现中的命名或测试描述。

不允许项：

- 产品代码中直接调用浏览器原生 `alert/confirm/prompt`。

### 5. 视觉规范

控件视觉要与当前作者工作台/Skill Console 方向一致：

```text
radius: 6-8px
border: 低对比细边
focus: 品牌青绿色或铜金色轻量 ring
background: 白色 / 暖纸 / 浅灰，不使用浏览器默认灰
font-size: 表单主体 13-14px，正文输入 15-16px
line-height: 1.5+
touch target: 移动端 44px+
```

禁止：

- 默认浏览器 select 箭头裸露在关键页面上；
- 默认 checkbox 小方块裸露；
- 输入框只靠 placeholder 当 label；
- 表单控件高度、圆角、边框颜色各写各的；
- 大面积蓝紫渐变、装饰性光斑；
- 继续新增无归属的 inline style。

## 推荐实施顺序

1. 建立 `frontend/src/components/ui/` 控件层与 `ui.css`。
2. 为控件层写基础测试：
   - label/helper/error 渲染；
   - input/select/textarea change；
   - checkbox/switch toggle；
   - disabled 和 aria；
   - DataTable 空状态。
3. 替换 `SkillVisibilityPanel.tsx` 中残留的 select/textarea/table。
4. 替换 `SettingsConsoleSections.tsx` 和 `RunHealthPanel.tsx`。
5. 替换 `ChapterEditorSurface.tsx`、`ProjectOverviewModule.tsx`。
6. 替换 Onboarding/Run/Review 这些高频页面。
7. 替换项目资料模块第二批页面。
8. 跑前端验证。
9. 扫描残留原生弹窗和未归一控件。
10. 写 completion report / review 后提交。

## 文件范围

允许修改：

```text
frontend/src/components/ui/*
frontend/src/components/settings/*
frontend/src/components/project/*
frontend/src/pages/Onboarding.tsx
frontend/src/pages/Run.tsx
frontend/src/pages/Review.tsx
frontend/src/pages/Style.tsx
frontend/src/index.css
frontend/src/components/**/__tests__/*
docs/codex/reports/*
docs/codex/reviews/*
```

谨慎修改：

```text
frontend/src/components/Layout.tsx
frontend/src/App.tsx
frontend/src/lib/api.ts
```

不应修改：

```text
novel_factory/**
tests/**
database migrations
LLM provider / workflow / agent backend
```

除非发现前端测试夹具必须补齐，不要改后端。

## 测试与验收

最低验证：

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
npm run test -- --run
```

建议补充：

```bash
python3 scripts/verify.py smoke
```

验收清单：

1. `settings?section=skills` 无浏览器默认 select/textarea/checkbox 观感。
2. 设置页 LLM/Agent/Skill/Run Health 表单控件风格一致。
3. Onboarding 输入体验统一，数字输入和 select 不突兀。
4. Project modules 的新增/编辑表单不再像原生 HTML 表单。
5. 章节编辑器 textarea 与工作台视觉一致。
6. 表格统一为同一套密度、边框、hover、空状态。
7. 键盘 Tab 可见焦点，回车/空格操作 checkbox/switch 正常。
8. 移动端 375px 宽度没有表单溢出和按钮挤压。
9. 产品代码无原生 `alert/confirm/prompt`。
10. 现有 API payload、保存行为、生成行为不变。

## Review 重点

Review 时优先看：

1. 是否真的减少了原生控件观感，而不是只换 class。
2. 是否引入过度抽象导致简单页面难维护。
3. 是否破坏现有测试或用户可见文案。
4. 是否把业务逻辑和 UI 组件混在一起。
5. 是否遗漏移动端触控尺寸。
6. 是否保留可访问性语义。

## Development Prompt for Implementation Agent

Task: Implement v5.9.2 UI Controls Standardization.

Context:

- Repo: Novelos, React + Vite frontend.
- Baseline: v5.9.1 Skill Console UX.
- Goal: replace native browser-looking controls across the WebUI with a consistent Novelos UI control layer.
- This is a frontend-only UX stabilization version. Do not change backend APIs, database, workflow, agents, or LLM logic.

Read first:

- `docs/codex/planning/novel-factory-v5.9.2-ui-controls-standardization-spec.md`
- `frontend/src/components/AppDialog.tsx`
- `frontend/src/index.css`
- `frontend/src/components/settings/SkillVisibilityPanel.tsx`
- `frontend/src/components/project/ChapterEditorSurface.tsx`

Implementation requirements:

1. Create `frontend/src/components/ui/` with reusable controls:
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
2. Controls must preserve native semantics and keyboard accessibility while removing default browser visuals.
3. Replace high-priority native controls in:
   - `frontend/src/components/settings/SkillVisibilityPanel.tsx`
   - `frontend/src/components/settings/SettingsConsoleSections.tsx`
   - `frontend/src/components/settings/RunHealthPanel.tsx`
   - `frontend/src/pages/Onboarding.tsx`
   - `frontend/src/pages/Run.tsx`
   - `frontend/src/pages/Review.tsx`
   - `frontend/src/components/project/ChapterEditorSurface.tsx`
   - `frontend/src/components/project/ProjectOverviewModule.tsx`
4. Replace second-priority project module controls where straightforward:
   - Characters, WorldSettings, Factions, Outlines, Instructions, PlotHoles, ProjectSettings, FactLedger, ProjectSkillOverrides, Style page.
5. Do not alter API payload shapes or save/generate/recovery behavior.
6. Do not use native `window.alert`, `window.confirm`, or `window.prompt`; keep using `useAppDialog`.
7. Add or update frontend tests for the new controls and at least one migrated page.
8. Run:
   - `npm run typecheck`
   - `npm run lint`
   - `npm run build`
   - `npm run test -- --run`
9. Run a grep check for native dialogs and summarize allowed test-only matches.
10. Produce a concise completion summary listing files changed, controls added, pages migrated, validation results, and known residual native controls if any remain.

Acceptance:

- The main WebUI no longer feels like raw browser forms.
- Forms have consistent label/helper/error/focus/disabled/loading states.
- Select, textarea, checkbox, switch, number input, and tables share the same visual system.
- Existing product behavior remains unchanged.

