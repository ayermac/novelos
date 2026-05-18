# v6.5.7 Visual Polish Pass Review

## Review Verdict

**PASS WITH MINOR VISUAL FOLLOW-UP**

本次改动成功补齐 v6.5 交互迭代中"视觉感知不明显"的问题：新增主题切换，主布局和高频工作台页面有明确的日/夜模式差异，质量诊断面板也不再像后台表格。

## 核查项

| 检查项 | 结果 | 备注 |
| --- | --- | --- |
| 主题切换可访问性 | 通过 | 按钮 aria-label 随模式变化 |
| 主题持久化 | 通过 | `novelos.theme` 写入 localStorage |
| 全局 token | 通过 | light/dark 均定义主要背景、文本、边框、强调色 |
| 主布局适配 | 通过 | Sidebar / Topbar / tooltip / badge 使用变量 |
| 项目工作台适配 | 通过 | ProjectOverview 与 ProjectSideNav 关键表面使用变量 |
| 章节写作台适配 | 通过 | AuthorWorkbench 暗色变量覆盖 |
| 质量诊断 UI | 通过 | 评分环、指标条、finding 卡片均适配主题 |
| Skill 管理面板深色适配 | 通过 | SkillVisibilityPanel.css 添加完整 `html[data-theme='dark']` 覆盖，导航/卡片/矩阵/chip/消息/测试摘要均适配 |
| 章节版本历史深色适配 | 通过 | ChapterVersionPanel 内联颜色提取为 className，index.css 统一管理浅色/深色样式；当前版本高亮、详情面板背景均使用主题变量 |
| app-dialog 深色适配 | 通过 | index.css 为 danger/warning/success/info 变体添加深色模式下 icon 背景 `color-mix` 覆盖 |
| 运行记录路由修复 | 通过 | RunsModule `<a href>` 改为 `<Link to>`，桌面端 HashRouter 下正确生成 `/#/runs/xxx` |
| 后端影响 | 通过 | 无后端改动 |
| workflow 影响 | 通过 | 无拓扑改动 |

## Findings

### 已处理

1. **SkillVisibilityPanel 深色模式未适配**
   - Skill 管理面板使用独立 CSS 变量体系（`--skill-panel`、`--skill-soft`、`--skill-ink` 等），在深色模式下仍显示浅色硬编码背景，与整体暗色主题冲突。
   - 已在 `SkillVisibilityPanel.css` 中添加完整的 `html[data-theme='dark']` 覆盖，包含导航、卡片、矩阵、chip、消息、测试摘要、覆盖率标签等所有表面。

2. **ChapterVersionPanel 深色模式未适配**
   - 版本历史面板使用大量内联硬编码颜色（`#e8f0fe`、`#fff`、`#f5f5f5`、`#1a73e8` 等），在深色模式下显示为突兀的浅色块。
   - 已将所有内联样式提取为 className，在 `index.css` 中统一管理浅色/深色样式：当前版本高亮由淡蓝 `#e8f0fe` → 深蓝 `rgba(26, 115, 232, 0.15)`，普通版本背景由 `#fff` → `var(--paper-surface)`，详情面板由 `#f5f5f5` → `var(--bg-secondary)`。

3. **app-dialog icon 背景深色不协调**
   - 深色模式下 `app-dialog-danger`、`app-dialog-warning` 等变体的 icon 背景仍使用浅色值，与暗色主题不兼容。
   - 已在 `index.css` 中为各变体添加 `html[data-theme='dark']` 覆盖，使用 `color-mix(in srgb, var(--danger) 14%, var(--bg-primary))` 等语义化深色混合。

4. **运行记录详情跳转空白**
   - `RunsModule` 使用原生 `<a href="/runs/xxx">`，在桌面端 `HashRouter` 下导航到 `file:///runs/xxx` 导致空白页面。
   - 已改为 `<Link to="/runs/xxx">`，桌面端正确生成 `/#/runs/xxx`。

### P3 — 浏览器截图受 sandbox 限制

本地 Vite server 可启动，但 Chromium headless 截图在当前 sandbox 下触发 macOS MachPort 权限错误。已用 typecheck/lint/unit/build 作为替代验证。

## 结论

可以继续进入下一阶段。v6.5.7 没有改变业务逻辑，但显著提升了视觉差异、夜间可用性和工作台质感。
