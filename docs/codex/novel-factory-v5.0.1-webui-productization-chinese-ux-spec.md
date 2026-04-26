# v5.0.1 WebUI Productization & Chinese UX 规格

## 目标

将 Novel Factory WebUI 从"验收控制台"升级为"中文作者工作台"。重点不是增加功能，而是让现有功能看起来统一、清晰、可日常使用。

## 设计方向

- 中文优先
- 作者工作台 / 生产控制台风格
- 安静、专业、信息密度适中
- 不要营销页，不要大 hero，不要花哨渐变
- 不要像后台 demo，也不要像默认 Bootstrap
- 页面要像一个真正给网文作者长期使用的 SaaS 工具

## 整体视觉风格

- 背景：浅灰白工作区 `#f3f4f6`
- 主内容：白色面板 + 细边框
- 强调色：
  - 青绿色 `#059669` 用于成功/可执行
  - 蓝色 `#2563eb` 用于信息
  - 琥珀色 `#d97706` 用于警告
  - 红色 `#dc2626` 用于阻塞
- 字体：系统中文字体栈
- 卡片圆角不超过 8px
- 表格紧凑、可扫描
- 状态必须用中文 badge
- 主按钮必须明显，次级按钮要克制
- 页面首屏必须告诉用户"现在是什么状态、下一步做什么"

## 布局

- 左侧固定导航栏（220px），深色背景 `#111827`
- 顶部状态栏（56px），显示 LLM 模式、数据库路径、当前项目
- 主内容区自适应，最大宽度 1400px
- 移动端：v5.0.1 只验收桌面端

## 导航（中文）

| 路由 | 中文标签 |
|------|---------|
| `/` | 总览 |
| `/projects` | 项目 |
| `/onboarding` | 创建项目 |
| `/run` | 生成章节 |
| `/batch` | 批量生产 |
| `/queue` | 队列 |
| `/serial` | 连载计划 |
| `/review` | 审核 |
| `/style` | 风格 |
| `/config` | 诊断 |
| `/settings` | 配置 |
| `/acceptance` | 验收 |

## 核心页面

### 1. 总览 Dashboard

首屏结构：
- 页面标题：创作控制台
- 摘要卡片：项目数、待审核章节、队列中任务、最近运行
- 主操作：创建新项目、生成章节、进入审核
- 最近项目列表、最近运行列表
- 异常/阻塞提示

### 2. 项目工作台 /projects/{project_id}

模块：
- 项目概览
- 下一步建议（NBA）
- 章节进度
- 最近运行
- 待审核
- 生产队列
- 连载计划
- 风格健康
- 快捷操作

### 3. 审核工作台 /review

- 项目选择器 + 状态筛选标签
- 摘要卡片：待审核、阻塞、可批准、需返修
- 主区域：审核队列表格
- 高级工具区折叠在下方（Run ID、Chapter Range 等）
- 不突出"批量批准"

### 4. 生成章节 /run

- 项目选择器 + 章节选择
- LLM 模式
- 主按钮：生成章节
- 当前章节状态
- 运行结果摘要 + 下一步动作

### 5. 风格 /style

- 风格健康摘要
- 风格圣经状态
- 风格门禁状态
- 样本数量
- 待处理提案
- 主操作：初始化风格圣经、上传样本、查看提案

### 6. 配置中心 /settings

- 运行模式
- LLM Profiles
- Agent 路由
- 模型推荐
- 配置诊断
- 配置向导（Provider、Base URL、Model、API Key、Default LLM、Agent Routing）
- 默认只生成配置草案，不直接写入真实配置

## 状态 Badge 中文映射

| 英文 | 中文 |
|------|------|
| planned | 已规划 |
| scripted | 已出剧本 |
| drafted | 已起草 |
| polished | 已润色 |
| review | 待审核 |
| reviewed | 已审核 |
| published | 已发布 |
| blocked / blocking | 已阻塞 |
| failed | 失败 |
| pending | 待处理 |
| approved | 已通过 |
| rejected | 已拒绝 |

## 安全要求

- API Key 输入后不回显
- 页面只显示"已配置 / 未配置"
- 默认生成配置草案，不直接写入 `.env` 或真实 config
- 如果支持保存，必须是单独 POST 操作
- 不能把 API Key 写入 HTML、日志、测试输出

## 禁止

- 不新增真实 LLM 调用
- 不自动 approve/publish
- 不引入登录、多用户、权限
- 不引入 WebSocket/Redis/Celery
- 不泄露 API key/secret/traceback/raw JSON
- 不提交 config/acceptance.yaml、stderr.txt、真实密钥

## 测试

新增 `tests/test_v501_webui_productization_chinese_ux.py`，覆盖：
- 导航中文化
- Review 页面中文化
- Config/Settings 页面中文化
- 配置向导存在
- API key 不泄露
- 生成配置草案不写真实文件
- 空状态可读
- 页面无 traceback/raw JSON

## 验收标准

- v5.0 专项测试通过
- WebUI 组合测试通过
- 全量测试通过
- 新增 v5.0.1 测试通过
