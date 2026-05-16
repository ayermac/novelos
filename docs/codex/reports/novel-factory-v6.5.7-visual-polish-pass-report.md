# v6.5.7 Visual Polish Pass 完成报告

## 总体结论

**PASS**

v6.5.7 完成一次可感知的视觉层升级：新增日间/夜间主题切换，并将主布局、项目工作台、章节写作台和质量诊断面板接入主题 token。

## 改动范围

| 文件 | 改动 |
| --- | --- |
| `frontend/src/components/Layout.tsx` | 新增日/夜主题切换按钮，持久化主题，侧边栏/顶栏改为 token 驱动 |
| `frontend/src/index.css` | 新增 light/dark 主题 token、状态 badge 暗色适配；新增 ChapterVersionPanel 样式体系与深色覆盖；新增 app-dialog 各变体 icon 背景深色覆盖 |
| `frontend/src/components/ui/ui.css` | 控件 hover、表格 hover、Skeleton 改为主题变量 |
| `frontend/src/components/project/AuthorWorkbench.css` | 章节写作台与项目 shell 暗色适配 |
| `frontend/src/components/project/ProjectOverviewModule.tsx` | 主任务卡、健康卡、资料缺口卡改为主题变量 |
| `frontend/src/components/project/ProjectSideNav.tsx` | 项目内侧栏改为主题变量 |
| `frontend/src/components/project/QualityDiagnosisPanel.tsx` | 质量诊断面板视觉重做，支持暗色模式 |
| `frontend/src/components/settings/SkillVisibilityPanel.css` | 添加完整的 `html[data-theme='dark']` 覆盖，修复深色模式下导航、卡片、矩阵、chip、消息、测试摘要等硬编码浅色样式 |
| `frontend/src/components/project/ChapterVersionPanel.tsx` | 将内联硬编码颜色（`#e8f0fe`、`#fff`、`#f5f5f5`、`#1a73e8` 等）全部提取为 className，由 CSS 统一管理并支持深色模式 |
| `frontend/src/components/project/RunsModule.tsx` | 将 `<a href="/runs/xxx">` 改为 `<Link to="/runs/xxx">`，修复桌面端 HashRouter 下导航到错误路径导致的空白页面 |
| `frontend/src/components/__tests__/Layout.test.tsx` | 新增主题切换与持久化测试 |

## 产品变化

- 用户可以在侧边栏品牌区切换日间 / 夜间模式。
- 主题选择保存到 `localStorage`，下次打开保持一致。
- 夜间模式不是简单反色，而是使用深色纸面、暖金强调色、低对比边框和暗色写作台。
- 质量诊断面板从普通折叠块升级为更明确的文字体检仪表盘。
- Overview 和章节工作台的主要表面不再被硬编码浅色块卡住。
- Skill 管理面板在深色模式下所有表面（导航、卡片、矩阵、chip、消息、测试摘要）均有正确的暗色覆盖，不再出现浅色突兀块。
- 章节版本历史面板在深色模式下当前版本高亮、普通版本背景、详情面板背景均使用主题变量，不再显示硬编码浅色。
- 运行记录详情链接在桌面端正确跳转，不再出现点击后空白的问题。

## 非目标确认

- 未改后端 API。
- 未改 workflow 拓扑。
- 未改 Agent prompt。
- 未改数据库 schema。
- 未引入新 UI 框架。

## 验证结果

| 命令 | 结果 |
| --- | --- |
| `cd frontend && npm run typecheck` | 通过 |
| `cd frontend && npm run lint` | 通过 |
| `cd frontend && npm run build` | 通过（保留既有 chunk size warning） |
| `cd frontend && npm run test -- --run src/components/__tests__/Layout.test.tsx src/components/project/__tests__/ProjectOverviewModule.test.tsx src/components/project/__tests__/AuthorWorkbench.test.tsx` | 63 passed |
| `cd frontend && npm run test -- --run` | 15 files, 199 passed |
| `cd desktop && npm run typecheck` | 通过 |
| `cd desktop && npm run build` | 通过 |
| `python3 scripts/verify.py smoke` | 28 passed |

## 已知限制

- 除已修复的 SkillVisibilityPanel 和 ChapterVersionPanel 外，仍有少量旧组件存在 inline hard-coded 色值，后续在 v6.6 前端证据 UX 中顺手清理。
- 浏览器截图验证在当前 sandbox 下被 Chromium headless 权限阻止，改由编译、单测和构建验证。
