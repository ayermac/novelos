# 📚 OpenClaw Web Novel Factory - System Architecture & Refactoring Guide

## ⚠️ 致 Claude Code 的核心准则
你当前介入的是一个**工业级多智能体网文生成系统（Agentic Web Novel Factory）**。
大语言模型（LLM）在长篇创作中存在天然的缺陷：**记忆断层、空间逻辑崩塌、喜欢使用AI烂梗、护短（不愿给出差评）**。
因此，本次重构的核心理念是：**用代码的绝对理性，去压制 LLM 的语义幻觉。能用 Python 脚本（硬校验）卡死的规则，绝对不依赖 Prompt（软校验）。**

---

## 一、 系统核心架构 (System Architecture)

本系统基于 `OpenClaw` 框架，采用 **Actor-Critic（生成-对抗）** 加上 **Rule-Engine（规则引擎）** 的混合架构。

### 目录结构

```
/Users/jason/.openclaw/agents/
├── shared/                          # 共享资源
│   ├── data/                         # 公共数据
│   │   ├── novel_factory.db          # 数据库（所有 Agent 共享）
│   │   ├── init_db.sql               # 数据库初始化脚本
│   │   └── upgrade_db.sql            # 数据库升级脚本
│   └── tools/                        # 共享工具
│       ├── db_common.py              # 数据库公共模块
│       ├── check_chapter.py          # 章节检查工具
│       ├── clean_project.py          # 项目清理工具
│       ├── export_chapters.py        # 章节导出工具
│       └── feedback_system.py        # 反馈升级系统
├── dispatcher/workspace/             # 调度器
│   ├── skills/dispatcher/scripts/
│   │   ├── lock.py                   # 调度锁
│   │   └── consistency_check.py      # 一致性检查
│   └── tools/db.py                   # 调度器数据库工具
├── planner/workspace/                # 总编
├── author/workspace/                 # 执笔
├── editor/workspace/                 # 质检
├── scout/workspace/                  # 星探
├── secretary/workspace/              # 秘书
└── architect/workspace/              # 架构师
```

### 核心 Agent 角色池

| Agent | 职责 | 触发方式 |
|-------|------|----------|
| ⚙️ Dispatcher | 流水线总控，监听任务状态，流转状态机 | Cron 定时（每5分钟） |
| 🧠 Planner | 控制宏观剧情，生成写作指令，埋设伏笔 | Dispatcher 调度 |
| ✍️ Author | 将指令转化为正文 | Dispatcher 调度 |
| 🔪 Editor | 五层审校 + 死刑红线扫描 | Dispatcher 调度 |
| 🔭 Scout | 市场分析，题材推荐 | 用户触发 |
| 📊 Secretary | 日报生成，进度汇报 | 定时/触发 |
| 🏗️ Architect | 系统诊断与优化 | 用户触发 |

### 状态流转

```
planned (待创作) → drafting (创作中) → review (待质检) → revision (退回重写) / reviewed (通过)
                                                            ↑_______________|
```

---

## 二、 核心数据流转与状态管理

### 1. 状态卡系统 (`chapter_state`)
- 每章通过质检后提取数值快照（金钱、等级、位置等）
- Author 写第 N 章时必须读取第 N-1 章的 `chapter_state`
- **严禁 Author 脑补数值**

### 2. 伏笔追踪系统 (`plot_holes` + `chapter_plots`)
- Planner 在指令中声明需要兑现的伏笔
- `verify_plots` 验证正文是否触发伏笔条件

### 3. 反模式/错题本 (`anti_patterns` 表)
- 位置：数据库 `anti_patterns` 表和 `context_rules` 表
- 命令：`python3 tools/db.py anti_patterns [--enabled|--all]`
- 23 个问题模式 + 3 条上下文规则
- 支持：动态更新、发现频率统计、与 learned_patterns 联动

### 4. 版本管理 (`chapter_versions`)
- 每次保存草稿时自动保存版本
- 支持回滚和版本对比

### 5. 问题学习系统 (`learned_patterns`)
- 质检发现的问题自动记录
- 高频问题模式化，形成经验积累

---

## 三、 核心工作流 (SOP)

```
[Dispatcher] 轮询发现新章节需求
    │
    ├─> [Planner] 读取大纲 & 状态卡 -> 生成 Instruction
    │
    ├─> [Author] 读取 Instruction & 状态卡 & 错题本 -> 生成草稿
    │     └─> check_chapter.py 本地校验（字数、禁用词、数值）
    │     └─> 生成完成 -> 状态设为 review
    │
    ├─> [Editor] 执行五层审校 + 死刑红线扫描
    │     ├─> Pass (>=90分): 写入 chapter_state，状态设为 reviewed
    │     └─> Fail (<90分): 输出 issues & suggestions，状态设为 revision
    │
    └─> [Author] (revision) 读取 issues -> 局部修改 -> 返回 review
```

### 熔断机制
- 单章修改超过 3 次：`human_intervention`（人工介入）
- 任务运行超过 30 分钟：`timeout`（超时失败）
- 底层错误重试 3 次：`abandon`（放弃）

---

## 四、 重构指导原则

### 1. 软硬校验分离
- **LLM 擅长**：软校验（动机、情绪张力）
- **代码擅长**：硬校验（字数、禁用词、数值对比）
- 所有硬校验在 `check_chapter.py` 中用正则/逻辑拦截

### 2. 阻断无限循环
- `task_status.retry_count` 记录重试次数
- 超过阈值触发熔断，状态设为 `human_intervention`

### 3. 工具调用鲁棒性
- `db_common.py` 增强参数解析
- 所有异常返回友好 JSON 错误
- 数据库错误给出修复建议

### 4. 消除 LLM 记忆幻觉
- Context Builder 按优先级组装：**死刑红线 > 写作指令 > 错题本 > 角色设定**
- 强制清理过期对话历史

---

## 五、 数据库表结构概览

### 核心表
| 表名 | 用途 |
|------|------|
| `projects` | 项目管理 |
| `chapters` | 章节管理 |
| `instructions` | 写作指令 |
| `reviews` | 质检报告 |
| `plot_holes` | 伏笔管理 |
| `chapter_state` | 数值状态卡 |
| `task_status` | 任务状态 |

### 高级功能表
| 表名 | 用途 |
|------|------|
| `chapter_versions` | 版本管理 |
| `state_history` | 状态变更历史 |
| `agent_messages` | Agent 异步消息队列 |
| `learned_patterns` | 问题模式学习 |
| `best_practices` | 最佳实践 |

---

## 六、 给 Claude Code 的代码风格指南

### 数据库路径
- 所有工具导入 `from db_common import DB_PATH, get_connection`
- 数据库位于 `shared/data/novel_factory.db`

### 参数校验
- 使用 try-except 捕获所有数据库操作
- 返回 JSON 格式的错误信息

### 禁止事项
- ❌ Agent 间直接通信（`@agent`）
- ❌ 各 Agent 独立数据库副本
- ❌ 跳过 `chapter_state` 直接创作
- ❌ 启动时未查询 `anti_patterns` 表

---

**使命必达**：你的目标是构建一台冷酷无情、逻辑严密的小说压榨机。一切为了逻辑闭环，一切为了反降智！