# 网文工厂 OpenClaw 适配报告

## 更新日期：2026-04-06

---

## 一、适配完成内容

### ✅ 已适配到 OpenClaw 框架

| 组件 | 原位置 | 新位置 | 状态 |
|------|--------|--------|------|
| 上下文构建 | `shared/context/context_builder.py` | `db_common.py` 命令 | ✅ |
| 健康报告 | `shared/monitoring/system_monitor.py` | `db_common.py` 命令 | ✅ |
| 写作模板 | `shared/templates/writing_templates.py` | `author/.../references/writing_templates.md` | ✅ |
| Agent Prompt | `shared/prompts/agent_prompts.py` | 各 Agent 的 `SOUL.md`、`SKILL.md` | ✅ |

### ✅ 新增数据库命令

```bash
# 构建上下文（供 Agent 使用）
python3 tools/db.py build_context <project> <chapter> <agent_type>
# agent_type: author, editor, planner

# 健康报告（供 Dispatcher 和 Architect 使用）
python3 tools/db.py health_report <project>
```

### ✅ 更新的 Agent 文件

| Agent | 更新内容 |
|-------|----------|
| Planner | `TOOLS.md` - 添加 `build_context`、`health_report` 命令 |
| Author | `TOOLS.md` - 添加完整命令列表；`references/writing_templates.md` - 写作模板 |
| Editor | `TOOLS.md` - 添加完整命令列表 |
| Dispatcher | `TOOLS.md` - 添加 `health_report` 命令 |
| Architect | `TOOLS.md` - 添加 `health_report` 命令 |

---

## 二、使用方式

### 1. 上下文构建

Agent 在创作/质检前，可以一步获取所有上下文：

```bash
# Author 获取完整上下文（死刑红线 + 指令 + 状态卡 + 伏笔 + 问题模式 + 角色）
python3 tools/db.py build_context <project> <chapter> author

# Editor 获取完整上下文（同上 + 章节内容）
python3 tools/db.py build_context <project> <chapter> editor

# Planner 获取规划上下文
python3 tools/db.py build_context <project> <chapter> planner
```

返回 JSON 包含：
- `context`: 完整上下文字符串
- `estimated_tokens`: 估算 token 数
- `token_limit`: token 限制

### 2. 健康报告

Dispatcher 和 Architect 可以监控系统健康：

```bash
python3 tools/db.py health_report <project>
```

返回：
- `status`: healthy/warning/error
- `metrics`: 10项指标（失败率、平均分、伏笔兑现率等）
- `alerts`: 告警列表
- `chapter_stats`: 章节统计

### 3. 写作模板

Author 在创作前应阅读：
```
skills/novel-writing/references/writing_templates.md
```

包含：
- 死刑红线（AI 烂词列表）
- 场景描写模板
- 对话模板
- 节奏控制模板
- 情绪模板
- 动作描写模板

---

## 三、架构说明

### OpenClaw 框架下的组件关系

```
OpenClaw Agent 运行时
    │
    ├── SOUL.md          # Agent 身份定义
    ├── IDENTITY.md      # Agent 角色定位
    ├── TOOLS.md         # 可用工具列表
    │
    └── skills/
        └── <skill-name>/
            ├── SKILL.md           # 工作流程
            └── references/
                └── *.md           # 参考文档

调用方式：
    Agent → 读取 SKILL.md → 执行 python3 tools/db.py <命令>
```

### 数据库命令层

所有 Agent 共享 `shared/tools/db_common.py`，通过 `tools/db.py` 调用：

```python
# 各 Agent 的 tools/db.py 导入共享模块
from db_common import *

COMMANDS = {
    # 子集命令...
}

if __name__ == "__main__":
    run(COMMANDS, HELP)
```

---

## 四、剩余优化项

### Phase 2：稳定性提升

| 任务 | 优先级 | 状态 |
|------|--------|------|
| 数据备份机制 | P1 | ⏳ 待实现 |
| 配置管理（YAML） | P1 | ⏳ 待实现 |

### Phase 3：能力增强

| 任务 | 优先级 | 状态 |
|------|--------|------|
| 激活 learned_patterns 自动记录 | P2 | ⏳ 待实现 |
| Editor 自动记录问题模式 | P2 | ⏳ 待实现 |

---

## 五、测试建议

### 测试新命令

```bash
# 测试上下文构建
cd /Users/jason/.openclaw/agents/planner/workspace
python3 tools/db.py build_context <project> 1 author

# 测试健康报告
python3 tools/db.py health_report <project>
```

### 测试 Agent 工作流

1. Dispatcher 分配任务
2. Planner 创建写作指令
3. Author 读取 `build_context` → 创作章节
4. Editor 读取 `build_context` → 质检
5. Architect 运行 `health_report` 检查系统状态

---

## 六、结论

之前创建的 Python 模块（prompts、context、monitoring、templates、tests）**不符合 OpenClaw 框架**，已删除。

正确做法：
1. **功能通过 `db_common.py` 命令暴露** → Agent 通过 `python3 tools/db.py xxx` 调用
2. **模板和参考文档放入 `references/` 目录** → Agent 在 SKILL 中引用
3. **Agent 身份定义在 `SOUL.md` 和 `IDENTITY.md`** → 不是 Python 代码

系统现在完全适配 OpenClaw 框架。
