# v5.5.11 Author-Centric Workspace Reset / 作者中心工作台重置

## 目标

把当前“能力很多但不好理解”的项目工作台，重置为作者能直接使用的生产界面：

1. 用户只需要理解三件事：今天该做什么、AI 正在做什么、哪里需要我判断。
2. 自动生产从技术概念降级为作者语言，不暴露 session、stream、SSE、dry-run 等内部词。
3. 项目菜单按作者任务重新组织，而不是按数据库对象和系统模块堆叠。
4. 生产指挥台必须解释“为什么阻塞、系统会怎么修、什么时候必须人工处理”。
5. 从工作台点击生成章节后，章节页必须立即看到对应工作流，而不是让用户怀疑没有启动。

## 背景

v5.5.3 到 v5.5.10 已经连续补齐了自动生产的后端能力：

- 下一步动作判断
- AI 自动补齐项目资料
- 弧线规划
- 自动运行器
- 实时监控
- session 持久化、暂停、恢复、取消、重试
- 刷新恢复与断线重连
- 有界自动化护栏，避免看不见的 token 空转

但产品体验仍然有明显断裂：

- 用户不理解“生产指挥台”到底该怎么用。
- 每个版本都在增加自动化能力，但 WebUI 感知不明显。
- 菜单层级像系统后台，不像作者工作台。
- 自动生产里的技术词太多，用户无法判断哪些是自己该处理的。
- 每章都阻塞时，用户会质疑“这还算自动生产吗”。

v5.5.11 的核心不是继续加自动动作，而是把已存在能力重新组织成一个清晰的作者产品。

## 产品原则

### 1. 作者任务优先

页面导航应该回答“我要做什么”，而不是“系统有哪些表”。

推荐一级任务：

- 工作台：今天要做什么、AI 能做什么、哪里卡住了
- 写章节：章节正文、生成进度、工作流
- 审稿发布：待审核内容、发布闸门、返修原因
- 记忆收件箱：待应用的记忆更新、事实变更、冲突
- 小说设定：世界观、角色、大纲、伏笔、章节指令
- 系统状态：运行记录、失败诊断、配置

### 2. 自动化透明但不暴露实现

用户应看到：

- AI 正在补资料 / 写第几章 / 等待审核
- 这次最多执行几步
- 已执行几步
- 为什么停下
- 下一步谁来处理

用户不应被迫理解：

- SSE
- EventSource
- session id
- generator
- dry-run
- max_steps
- stream

### 3. 自动生产不是无限修复

自动生产可以处理机械工作，但遇到以下情况必须清晰停机：

- 同一红线多次失败
- 题材偏离书名或创世契约
- 需要人工确认方向
- 没有新增有效内容
- 已达到预算上限

停机后必须给出“复盘卡片”：这次失败了什么、系统已尝试什么、建议怎么处理。

## 范围

### 本期要做

#### A. 项目导航重组

重构项目内导航文案与分组，但尽量复用已有页面：

| 新导航 | 目标 | 可能映射到现有模块 |
| --- | --- | --- |
| 工作台 | 项目首页、下一步动作、生产控制 | overview |
| 写章节 | 章节正文与工作流 | chapters |
| 审稿发布 | 待审核、发布、返修 | review / chapters review view |
| 记忆收件箱 | 待应用记忆、事实冲突 | memory / facts |
| 小说设定 | 世界观、角色、大纲、伏笔、指令 | genesis / world / characters / outlines / plot-holes / instructions |
| 系统状态 | 运行记录、配置、诊断 | runs / settings / health |

要求：

- 同一能力不要在多个入口重复出现。
- 高级/诊断入口可以折叠，不占用日常主路径。
- 移动端导航必须能收起，不能横向溢出。

#### B. 工作台改成“今日生产”

把 Production Command Center 改成作者能理解的今日面板：

1. 顶部只显示一个主要建议：
   - “现在建议：让 AI 补齐第 2 章资料”
   - “现在建议：生成第 2 章”
   - “现在建议：审核第 1 章”
2. 明确区分责任方：
   - AI 可自动处理
   - 需要你确认
   - 系统已停机
3. 自动生产入口改名：
   - “连续生产”
   - “只预览，不消耗生成”
   - “最多执行几步”
   - “生产记录”
4. 隐藏技术字段：
   - 不显示 session / stream / SSE。
   - session id 只在诊断详情或复制调试信息中出现。

#### C. 阻塞复盘卡片

当出现 blocking / failed / repeated_failure / consecutive_no_progress 时，显示一张复盘卡：

- 卡在哪个角色：编剧 / 执笔 / 润色 / 审核 / 发布
- 错误类型：红线违规 / 状态过期 / 记忆应用失败 / LLM 输出无效 / 预算耗尽
- 系统已尝试：重试次数、最近失败原因
- 建议动作：
  - 让 AI 按复盘修复
  - 打开章节工作流
  - 手动编辑资料
  - 终止本次生产记录

重点场景：

- `Author 输出包含 CRITICAL 死刑红线`
- `stale state, status advance failed`
- `memory apply failed`
- `NO_CONTENT_CREATED`

#### D. 工作流启动可见性

从工作台点击“生成第 N 章”后：

- 必须导航到 `module=chapters&chapter=N&view=workflow`。
- 章节页顶部必须显示“第 N 章正在生成”或“最近一次运行”。
- 如果工作流尚未拉到 run id，应显示启动中状态，而不是空白。
- 如果启动失败，应保留在章节页并显示失败原因。

#### E. 书名契约提示

针对“书名是《绝世仙帝在都市》，内容却不像这个题材”的问题，在工作台和创世/设定页增加轻量提示：

- 展示书名、题材、主角身份、核心爽点的契约摘要。
- 如果生成内容偏离契约，阻塞复盘卡应提示“题材契约偏离”。
- 本期只做展示与入口，不新增复杂题材评分模型。

### 本期不做

- 不重写整个前端架构。
- 不新增自动发布。
- 不新增新的 LLM agent。
- 不做复杂 token 成本精算。
- 不做云端队列或多用户权限。
- 不把所有阻塞都变成自动修复。

## 交互文案规范

| 技术词 | 作者侧文案 |
| --- | --- |
| auto-run | 连续生产 |
| dry-run | 只预览，不执行 |
| session | 生产记录 |
| stream / SSE | 实时进度 |
| max_steps | 最多执行几步 |
| stop_reason | 停止原因 |
| failed step | 失败步骤 |
| retry-step | 重试这一步 |
| active session | 正在进行的生产 |

## 前端实现建议

重点文件：

- `frontend/src/pages/ProjectDetail.tsx`
- `frontend/src/components/project/ProjectShell.tsx`
- `frontend/src/components/project/ProjectSideNav.tsx`
- `frontend/src/components/project/ProjectModuleNav.tsx`
- `frontend/src/components/project/ProjectOverviewModule.tsx`
- `frontend/src/components/project/ChapterWorkspace.tsx`

建议拆分：

1. 新增 `ProjectTaskNav` 或重构现有导航配置，统一从一份 task-based config 渲染。
2. 在 `ProjectOverviewModule` 内抽取：
   - `TodayProductionPanel`
   - `AutomationBudgetPanel`
   - `ProductionPostmortemCard`
   - `ProductionHistoryPanel`
3. 在 `ChapterWorkspace` 增加从工作台启动后的显式 loading / run visibility。
4. 把自动生产相关技术字段放入折叠的“调试信息”。

## 后端实现建议

本期优先复用已有 API，只有确实必要时补轻量字段：

- `production-next` 可增加更面向 UI 的字段：
  - `responsible_party: "ai" | "human" | "system"`
  - `reason`
  - `blocked_summary`
  - `target_chapter`
  - `user_facing_label`
- 自动生产 session 详情可增加：
  - `last_failure_action`
  - `last_failure_target_chapter`
  - `last_failure_message`
  - `progress_summary`

不要为了 UI 重命名破坏已有 API；可在前端映射中文文案。

## 验收标准

### 产品验收

- 新用户进入项目后，能在 10 秒内知道下一步该点哪里。
- 用户不需要理解 session / SSE / dry-run 等词，也能完成连续生产。
- 章节生成从工作台启动后，章节页能看到正在运行的工作流。
- 阻塞时不只显示错误，而是显示原因、系统尝试、下一步建议。
- 菜单分组符合作者任务，不再像数据库模块列表。
- 自动化边界清楚：AI 做机械推进，人做审核和方向判断。

### 工程验收

- 不破坏 v5.5.10 API 与测试。
- 前端 typecheck / lint / build 通过。
- 新增前端源码测试或组件测试覆盖：
  - 导航文案与分组
  - 技术词隐藏
  - 工作台单一主动作
  - 工作流启动后可见
  - 阻塞复盘卡渲染
- 如新增 API 字段，补对应 pytest。

### 浏览器验收

至少检查：

- 桌面端项目 overview
- 移动端项目 overview
- 章节 workflow view
- 记忆/事实入口
- 阻塞状态样例
- 连续生产运行中样例

要求：

- 无文字溢出
- 无按钮重复
- 无入口歧义
- 无嵌套卡片堆叠
- 圆角不超过 8px
- 不使用装饰性 orb/blob/大渐变

## 建议执行顺序

1. 先重构导航信息架构和文案。
2. 再重构工作台“今日生产”首屏。
3. 补阻塞复盘卡片。
4. 修复工作台到章节工作流的启动可见性。
5. 最后做移动端和浏览器视觉验收。

## 交付物

- 更新后的项目导航与工作台 UI。
- 阻塞复盘卡片。
- 工作流启动可见性修复。
- 必要的 API 轻量字段。
- v5.5.11 专项测试。
- 文档更新：
  - `docs/codex/planning/novel-factory-v5.5.11-author-centric-workspace-reset-spec.md`
  - `docs/codex/README.md`
  - `README.md`
  - `README.zh-CN.md`
  - `AGENTS.md`
  - `CLAUDE.md`
