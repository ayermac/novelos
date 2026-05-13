# v5.6 Author Workbench Review

## 范围

本次 Review 验证 v5.6 Author Workbench 是否达成 Phase 1 目标：

```text
在保留 v5.5.15 工作流安全防护的前提下，把项目页改造成个人 AI 辅助创作工作台。
```

## Review 检查项

| # | 检查项 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | `/projects/:id` 默认进入工作台 | 通过 | 项目页无需 `module=chapters` 即可渲染 Author Workbench |
| 2 | 当前章节是主要视觉对象 | 通过 | 中央写作区承载正文、工作流、产物、历史视图 |
| 3 | 项目模块仍然可达 | 通过 | 缺失菜单已恢复到项目导航 |
| 4 | 每章菜单作用于正确章节 | 通过 | 菜单动作不再依赖过期的当前选中章节状态 |
| 5 | running workflow guard 按章节判断 | 通过 | 一个章节运行中不会错误隐藏所有章节动作 |
| 6 | 终态章节继续受保护 | 通过 | reviewed/awaiting_publish/published 不暴露危险生成入口 |
| 7 | 卡住工作流有恢复入口 | 通过 | 工作台展示阻塞、重置、恢复详情动作 |
| 8 | 工作流节点文案可理解 | 通过 | 规划、编剧、执笔、润色、审核、发布与实际步骤对齐 |
| 9 | 前端验证通过 | 通过 | typecheck/lint/build/vitest passed |
| 10 | 后端回归风险已覆盖 | 通过 | v5.5.15 production-readiness smoke tests 与全量 pytest 基线通过 |

## 发现与修复

### P1：项目资料模块过于隐藏

初版工作台让章节生产链路更清楚了，但大纲、伏笔、事实账本、风格规范等项目资料模块变得不够明显。

修复：

- 恢复完整项目模块菜单，作为紧凑但可达的二级导航。
- 保留工作台为默认入口，没有退回旧的 dashboard-first 结构。

### P1：章节菜单可能作用于错误章节

部分菜单回调通过当前选中章节状态传递。若当前选中第 4 章，但点击第 5 章的菜单，动作可能错误作用到第 4 章。

修复：

- 重构章节菜单动作，显式传入被点击章节。
- 增加菜单动作和章节目标相关的前端测试。

### P1：running workflow 状态判断范围过大

UI 可能把某个运行中的 workflow 当成整个项目的阻塞，而不是判断它是否阻塞当前章节。

修复：

- 工作台内按章节计算 guard 状态。
- published 和 planned 章节继续只暴露各自合法动作。

### P2：卡住工作流可见但不够可处理

UI 可以提示 workflow 疑似卡住，但用户仍然需要自己推断如何恢复。

修复：

- 增加可见恢复动作：
  - `标记为阻塞`
  - `清除阻塞并重置`
  - `打开恢复详情`

### P2：工作流标签 `策划` 造成理解偏差

工作流展示可能显示 `策划`，但实际运行节点更接近 `screenwriter`。这会让用户不信任当前运行状态。

修复：

- 统一时间线标签：
  - `planner` -> `规划`
  - `screenwriter` -> `编剧`
  - `publisher` / `awaiting_publish` -> `发布`
- 时间线只在实际涉及 planning step 时展示规划节点。

### P3：视觉设计可用，但不是最终定稿

第一版视觉过重，后续修复已经往更安静的写作工作台方向调整。但 v5.6 仍应被视为功能性 UI 里程碑，而不是最终视觉身份。

建议：

- 不要继续在同一套 CSS 上反复“刷颜色”。
- 下一阶段 UX 工作应先形成小型设计契约：字体层级、密度、色彩角色、交互状态，以及改造前后截图。

## 验证结果

前端：

- `npm run typecheck`: passed
- `npm run lint`: passed
- `npm run build`: passed
- `npm run test -- --run`: 95/95 passed

后端：

- `python3 -m pytest tests/test_v514_workflow_visibility.py tests/test_v5515_production_readiness.py -q`: 29 passed
- v5.6 修复集完成后的全量 pytest 基线：1844/1844 passed

## 结论

Review 通过。v5.6 可以作为当前 WebUI 工作台基线。后续不建议继续做大范围导航重构，而应进入更聚焦的“日常写作可用性”增强阶段。
