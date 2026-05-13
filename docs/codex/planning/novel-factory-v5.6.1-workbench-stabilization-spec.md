# Novelos v5.6.1 工作台稳定化规格

## 状态

- 类型：可执行规划规格
- 状态：planned
- 基线：v5.6 Author Workbench Phase 1，以及截至 `4f1e05b` 的后续修复
- 产品目标：在继续开发更大的写作功能前，先把个人创作工作台稳定下来
- 工程目标：把真实使用路径写成可验收清单，停止继续零散修 UI

## 基线提交

当前 WebUI 基线包含：

- `b725bde`：引入 Author Workbench WebUI
- `4d59b04`：打磨工作台导航和恢复 UI
- `d8482c0`：改进弹窗和工作流反馈
- `b787cfa`：将运行产物和任务标签改成人可读文案
- `57cb0fc`：改进工作台导航和工作流刷新
- `aba9d16`：协调终态章节和遗留 workflow run
- `990860c`：增加可收起的全局侧边栏
- `c76ac75`：修复侧边栏品牌区压缩
- `0bd1950`：把 workflow artifacts 改成作者可理解的产物
- `5b1464a`：切换项目菜单时保留章节上下文
- `4f1e05b`：将“工作台”菜单路由到项目 overview，而不是章节工作台

本规格创建前的最新已验证基线：

- backend pytest：`1844/1844 passed`
- frontend typecheck：passed
- frontend lint：passed
- frontend build：passed
- frontend vitest：`108/108 passed`

## 目标

v5.6.1 是现有工作台的稳定化版本。它不追求新增大功能，而是让当前 UI 足够可信，可以作为后续 v5.7 正文编辑、保存、版本对比、局部返修的基础。

作者打开项目后，应该不需要猜就能回答：

1. 我现在在哪个项目页面？
2. 我正在看第几章？
3. 当前章节是什么状态？
4. AI 工作流是在运行、卡住、完成，还是已经过期？
5. 现在做什么操作是安全的？
6. 如果状态不对，应该在哪里恢复？

## 非目标

- 不再整体重构产品 UI。
- 不重新设计一套全新的视觉风格。
- 不加入多租户、组织、RBAC、计费或企业管理后台。
- 不在本阶段启动 v5.7 的正文编辑和版本管理能力。
- 不重写 LangGraph 工作流。
- 不改变 v5.5.15 已经稳定下来的生成 guard。
- 不引入大型新前端框架或组件库。
- 除非 UI 标签明显错误，不做 prompt 或模型供应商行为调整。

## 产品原则

1. 作者可理解的语言优先，内部 key 只能作为次要信息或折叠信息。
2. 当前章节上下文在切换项目模块时必须保持稳定。
3. 异步操作必须有加载态、防重复提交和明确结果。
4. 恢复动作必须说明目标章节和目标 run。
5. 工作流状态在页面停留时必须刷新，或者明确告诉用户数据已经过期。
6. 项目工作台内不允许使用原生浏览器 `confirm`、`alert`、`prompt`。
7. UI 应该像安静的写作软件，同时保留可检查的 AI 助手面板，而不是运维控制台。

## 范围

### 1. 导航稳定性

验收路径：

1. 打开 `/projects/novel_3v2o`，默认进入作者工作台。
2. 打开 `/projects/novel_3v2o?chapter=4&view=workflow`，选中的章节仍然是第 4 章。
3. 点击项目菜单里的“工作台”，进入项目 overview 模块，而不是章节工作台。
4. 点击“写章节”，回到当前章节的作者工作台。
5. 从第 4 章切到“大纲篇章”、“伏笔”、“事实账本”、“风格规范”，URL 仍保留 `chapter=4`。
6. 再回到“写章节”，仍展示第 4 章，除非用户主动切换过章节。
7. 收起和展开全局侧边栏时，项目标题、顶部区域和内容不能被压缩或裁切。
8. 收起和展开项目菜单时，所有二级模块仍然可达。

### 2. 章节菜单正确性

验收路径：

1. 每个章节行都有可发现的 overflow 操作菜单。
2. 打开菜单不会意外切换章节。
3. 菜单动作必须作用于被点击菜单所属章节，而不是当前选中章节。
4. `planned`、`scripted`、`drafted`、`polished`、`revision` 章节显示合法生成动作。
5. `reviewed + real mode` 显示发布动作，不显示生成当前章。
6. `published` 显示继续或生成下一章，不显示重新生成当前章。
7. `awaiting_publish` 明确说明章节正在等待发布。
8. 有 running workflow 的章节明确说明“已有工作流运行中”。

### 3. 写作区清晰度

验收路径：

1. “正文”视图只展示章节文本、空状态、写作指令或审稿上下文这些写作材料。
2. “正文”视图不展示工作流时间线。
3. “工作流”视图承载节点进度、run 状态、恢复动作和日志。
4. “产物”视图显示作者能看懂的标签，例如“过程稿”、“分场稿”、“正文草稿”、“润色稿”、“审稿意见”。
5. `scene_plan (screenwriter)` 这类原始标签不能作为主标签直接暴露。
6. 技术元数据可以放在折叠详情里，但不能成为作者第一眼看到的内容。

### 4. 工作流刷新与恢复

验收路径：

1. 工作流运行时，用户停留在页面上也能看到状态自动刷新，不需要手动刷新浏览器。
2. 当前运行中的节点有加载态。
3. 已完成节点展示稳定的完成态。
4. 每个节点在有数据时可以展示最近日志或事件摘要。
5. 超过卡住阈值的 run 展示明确的疑似卡住状态。
6. 卡住 run 提供恢复动作，并使用站内确认弹窗。
7. 如果终态章节存在遗留 running workflow，UI 应协调章节状态并推荐清理。
8. 如果第 5 章已发布但第 4 章仍显示 running workflow，UI 应解释这是状态矛盾，并引导恢复，而不是继续显示普通进行中。

### 5. 弹窗、加载态和错误状态

验收路径：

1. 项目工作台流程中不使用 `window.confirm`、`window.alert`、`window.prompt`。
2. 重置、清理、发布、恢复动作全部使用站内确认弹窗。
3. 每个 POST 动作都在按钮或邻近区域展示 pending 状态。
4. 请求进行中时禁用重复点击。
5. 成功和失败结果在 UI 中可见，不需要看浏览器 console。
6. 错误信息能说明失败动作以及目标章节或目标 run。

### 6. 视觉稳定化

验收路径：

1. 不继续做单纯“换颜色”的补丁。
2. 保持三层视觉层级：
   - 全局 / 项目导航
   - 中央写作区
   - AI / workflow 助手面板
3. 颜色只用于状态、当前选中项和主操作。
4. 卡片保持浅层级，避免卡片套卡片。
5. 常见桌面和笔记本宽度下，文字不能被裁切。
6. 当前章节标题和当前视图标题必须始终清楚可读。

## 建议实施顺序

1. 先为已经修好的路径补测试，尤其是项目菜单路由、章节上下文保留和章节菜单目标。
2. 用 `novel_3v2o` 按验收路径重新走一遍当前 UI。
3. 修复剩余的路由、刷新、弹窗、加载态和原始标签泄漏问题。
4. 如果怀疑视觉回归，用浏览器截图验证关键路径。
5. 实现验证通过后，再更新完成报告和 Review。

## 回归重点

后端：

- v5.5.15 production readiness tests 必须继续通过。
- workflow terminal / recovery 相关测试必须继续通过。
- 生成 guard 必须继续集中且跨入口一致。

前端：

- 项目菜单路由。
- 章节上下文保留。
- 全局侧边栏收起 / 展开。
- 项目菜单收起 / 展开。
- 章节 overflow 菜单目标。
- “正文”视图不显示工作流时间线。
- 工作流运行时自动刷新。
- 卡住 workflow 的恢复动作。
- 产物标签可读。
- 不使用原生浏览器弹窗。
- 异步动作有加载态。

## 验证命令

```bash
python3 -m pytest tests/test_v5515_production_readiness.py tests/test_v514_workflow_visibility.py -q
```

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
npm run test -- --run
```

声明新的稳定基线前，需要跑全量后端测试：

```bash
python3 -m pytest -q
```

## 完成标准

v5.6.1 只有在以下条件全部满足时才能算完成：

1. 上面的验收路径在 `novel_3v2o` 上通过。
2. 前端 typecheck、lint、build、vitest 通过。
3. 后端定向 workflow / production 测试通过。
4. 更新稳定基线前已跑全量 backend pytest。
5. 在 `docs/codex/reports/` 下创建完成报告。
6. 在 `docs/codex/reviews/` 下创建 Review 记录。

## 给实现 Agent 的开发 Prompt

按以下规格实现 `v5.6.1 Workbench Stabilization`：

```text
docs/codex/planning/novel-factory-v5.6.1-workbench-stabilization-spec.md
```

本阶段只稳定现有 v5.6 个人创作工作台。不要启动 v5.7 正文编辑 / 版本管理，不要引入多租户能力，也不要再次做大范围视觉重构。

使用 `novel_3v2o` 做真实路径验收。保留 v5.5.15 generation guard。重点覆盖项目菜单路由、章节上下文保留、章节 overflow 菜单目标、工作流刷新与恢复、产物标签人类可读、站内确认弹窗、异步加载态。

能加测试的地方要加测试。完成前运行：

```bash
python3 -m pytest tests/test_v5515_production_readiness.py tests/test_v514_workflow_visibility.py -q
cd frontend
npm run typecheck
npm run lint
npm run build
npm run test -- --run
```

更新稳定基线文档前，再运行：

```bash
python3 -m pytest -q
```
