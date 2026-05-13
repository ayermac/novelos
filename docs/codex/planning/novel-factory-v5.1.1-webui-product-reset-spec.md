# v5.1.1 WebUI Product Reset 规格

## 目标

将 v5.1 React WebUI 从"API demo"升级为真正的"中文作者工作台"，让个人作者进入系统后能清楚完成：
- 创建小说项目
- 查看项目进展
- 生成章节
- 查看运行结果
- 进入审核
- 查看风格状态
- 配置 LLM 草案
- 查看开发验收状态

## 产品原则

- 桌面端优先，保证 1280x800 可用
- 左侧导航 + 顶部状态栏保留
- 不要大面积空白
- 不要 API 字段直出
- 不要 raw JSON
- 不要英文内部状态
- 每个空状态都要告诉用户下一步
- 每个错误状态都要告诉用户发生了什么、可以怎么恢复
- 页面要像工具，不像 landing page，不要营销式大 hero

## 状态映射表

| 内部状态 | 中文显示 |
|---------|---------|
| completed | 已完成 |
| pending | 等待中 |
| running | 运行中 |
| failed | 失败 |
| partial | 迁移中 |
| pass | 通过 |
| error | 错误 |
| review | 待审核 |
| approved | 已通过 |
| rejected | 需返修 |
| blocking | 已阻塞 |
| fantasy | 奇幻 |
| urban | 都市 |
| sci-fi / scifi | 科幻 |
| xianxia | 仙侠 |
| romance | 言情 |
| mystery | 悬疑 |
| unknown | 未知 |

## 共享组件

### StatusBadge
- 接收 status 属性
- 内部调用 `tStatus()` 获取中文标签
- CSS class 使用内部状态（供样式使用）

### EmptyState
- 标题 + 提示 + 可选操作按钮
- 用于列表为空状态

### ErrorState
- 标题 + 错误消息 + 重试按钮
- 用于加载失败状态

### PageHeader
- 页面标题 + 可选返回按钮 + 可选操作插槽

## 页面改造清单

### Dashboard / 总览页
- [x] NextAction 卡片（无项目→创建、待审核→审核、失败→查看、继续创作）
- [x] 关键统计（项目数、待审核、队列项、运行模式）
- [x] 最近运行列表（状态中文、项目名可点击）
- [x] 快捷操作（创建项目、生成章节、审核、配置）
- [x] StatusBadge 中文显示

### Projects / 项目列表
- [x] PageHeader 带"创建项目"按钮
- [x] 类型列中文（fantasy→奇幻）
- [x] 操作按钮改为"查看工作台"
- [x] EmptyState 带创建引导

### ProjectDetail / 项目详情
- [x] NextAction 组件（blocking→review→failed→no chapters→continue）
- [x] 项目概览（类型中文、总章节、总字数、待审核）
- [x] 章节进度状态统计条
- [x] 最近运行列表
- [x] PageHeader 带返回按钮

### Onboarding / 创建项目
- [x] Wizard 表单（基础信息 → 规模设置 → 初始章节）
- [x] 类型改为下拉选择（中文选项）
- [x] 成功结果面板（绿色勾选、进入项目、生成第一章）
- [x] PageHeader 带返回

### Run / 生成章节
- [x] 项目信息卡片（名称、当前章节数）
- [x] 章节号自动建议（chapter_count + 1）
- [x] 结构化结果面板（StatusBadge、下一步操作）
- [x] 失败时 ErrorState 显示

### Review / 审核工作台
- [x] 统计卡片（待审核、阻塞、已通过、需返修）
- [x] StatusBadge 中文状态
- [x] EmptyState 带"去生成章节"操作

### Style / 风格管理
- [x] API 优雅降级（缺表时返回 ok=true + 空数组）
- [x] 健康摘要卡片
- [x] 空状态说明（生成章节后会出现数据）
- [x] Style Gate、Style Samples 列表

### Settings / 配置中心
- [x] 演示模式警告横幅
- [x] LLM 档案表格（API Key 状态、Base URL 状态）
- [x] 配置诊断（已配置/未配置状态）
- [x] 配置向导启动命令示例
- [x] Agent 路由列表

### Acceptance / 验收矩阵
- [x] 卡片列表布局（防溢出）
- [x] partial 状态显示"迁移中"
- [x] 中文化 label 和 notes
- [x] 统计包含 partial 计数

## API 修复

### /api/style/console
- 捕获 "no such table" 错误
- 返回 ok=true + 空数据结构
- 前端显示优雅空状态

### /api/acceptance
- summary 包含 partial 字段
- v50_acceptance 状态为 partial

## 测试覆盖

### 新增/更新测试
1. `test_style_console_graceful_with_missing_table` - Style console 缺表时返回 200
2. `test_settings_returns_diagnostics` - Settings API 返回诊断信息
3. `test_acceptance_returns_partial_status` - v50_acceptance 状态为 partial
4. `test_acceptance_summary_has_partial` - Acceptance summary 包含 partial 计数
5. `test_frontend_build_succeeds` - 前端构建通过
6. `test_frontend_typecheck_succeeds` - TypeScript 类型检查通过

### 验收命令
```bash
./scripts/v51_smoke_acceptance.sh
python3 -m pytest -q
cd frontend && npm run typecheck
cd frontend && npm run build
```

## 禁止事项

- 不恢复 Jinja WebUI
- 不开发登录/注册/权限
- 不引入 Redis/Celery/WebSocket
- 不做真实 LLM 调用测试
- 不提交真实 API key
- 不提交 frontend/node_modules
- 不提交 frontend/dist
- 不提交 config/acceptance.yaml
- 不提交 stderr.txt
- 不做 v5.2 新功能

## 文件清单

### 新增文件
- `frontend/src/lib/i18n.ts` - 状态映射函数
- `frontend/src/components/StatusBadge.tsx` - 状态徽章组件
- `frontend/src/components/EmptyState.tsx` - 空状态组件
- `frontend/src/components/ErrorState.tsx` - 错误状态组件
- `frontend/src/components/PageHeader.tsx` - 页面头部组件

### 修改文件
- `frontend/src/index.css` - 新增组件样式
- `frontend/src/pages/Dashboard.tsx` - NextAction、统计、最近运行
- `frontend/src/pages/Projects.tsx` - 中文类型、工作台入口
- `frontend/src/pages/ProjectDetail.tsx` - NextAction、进度统计
- `frontend/src/pages/Onboarding.tsx` - Wizard、成功面板
- `frontend/src/pages/Run.tsx` - 项目信息、结果面板
- `frontend/src/pages/Review.tsx` - 统计、StatusBadge
- `frontend/src/pages/Style.tsx` - 优雅空状态
- `frontend/src/pages/Settings.tsx` - 诊断信息、配置向导
- `frontend/src/pages/Acceptance.tsx` - 卡片列表、partial 状态
- `novel_factory/api/routes/style.py` - 优雅降级
- `novel_factory/api/routes/acceptance.py` - partial 计数
- `tests/test_v51_p2_fixes.py` - 新增测试

## 测试基线

- 当前测试基线: 1255/1255 passed
