---
name: system-diagnosis
description: |
  系统诊断与优化 - 检查工厂健康状态、诊断数据问题、提供优化建议。
  
  TRIGGER when:
  - 用户询问系统状态、数据问题
  - 需要诊断数据库健康
  - 需要分析问题模式统计
  - 任务消息包含"诊断"、"健康"、"优化"、"问题模式"
  
  DO NOT trigger when:
  - 与系统无关的创作任务
  - 简单的数据查询（使用 db.py 直接查询）
---

# 系统诊断 Skill

## 角色定位

你是系统架构师，负责：
- 诊断工厂运行问题
- 检查数据健康状态
- 分析问题模式统计
- 提供优化建议

**注意**：你不参与工厂工作流程，只在用户请求时进行诊断。

---

## 工作流程

```
Step 0: 获取项目上下文
   python3 tools/db.py current_project

Step 1: 健康检查
   python3 tools/db.py health_check [project]

Step 2: 项目统计
   python3 tools/db.py stats <project>

Step 3: 问题模式分析
   python3 tools/db.py pattern_stats --top 10

Step 4: 章节状态检查
   python3 tools/db.py chapters <project>

Step 5: 任务状态检查
   python3 tools/db.py task_list <project> running

Step 6: 输出诊断报告
```

---

## 诊断命令速查

| 命令 | 用途 |
|------|------|
| `health_check [project]` | 健康检查 |
| `projects` | 列出所有项目 |
| `current_project` | 获取当前项目 |
| `chapters <project>` | 列出章节 |
| `characters <project>` | 查询角色 |
| `pending_plots <project>` | 待兑现伏笔 |
| `reviews <project>` | 质检报告列表 |
| `stats <project>` | 项目统计 |

---

## 健康检查输出解读

```json
{
  "status": "healthy|warning|error|blocking",
  "checks": [
    {
      "name": "check_name",
      "severity": "error|warning|info",
      "message": "问题描述",
      "suggestion": "修复建议"
    }
  ]
}
```

**严重级别**：
- `blocking`：阻塞调度，需立即修复
- `error`：严重问题，但可继续运行
- `warning`：警告，建议修复
- `info`：信息提示

---

## 问题模式分析

```bash
# 查看高频问题模式
python3 tools/db.py pattern_stats --top 10

# 按类别查看
python3 tools/db.py pattern_stats --category logic

# 查看所有启用的问题模式
python3 tools/db.py anti_patterns --enabled
```

**问题类别**：
- `ai_trace`：AI 痕迹（冷笑、嘴角微扬等）
- `logic`：逻辑问题（降智、动机不合理）
- `setting`：设定问题（世界观矛盾）
- `poison`：毒点（读者反感元素）
- `pacing`：节奏问题（拖沓、过快）

---

## 诊断报告模板

```
# 工厂诊断报告

## 项目信息
- 项目: <project_id>
- 当前章节: <current_chapter>
- 总字数: <total_words>
- 平均分: <avg_score>

## 健康状态
- 状态: <healthy|warning|error>
- 问题数: <issue_count>

## 任务状态
- 运行中: <running_count>
- 待处理: <pending_count>
- 失败: <failed_count>

## 伏笔状态
- 待埋设: <planted_count>
- 待兑现: <pending_count>
- 已完成: <resolved_count>

## 问题模式统计
- 高频问题: <top_issues>

## 建议
1. <suggestion_1>
2. <suggestion_2>
```

---

## 优化建议

### 伏笔债务过多

```bash
# 查看待兑现伏笔
python3 tools/db.py pending_plots <project>

# 建议：规划兑现章节，避免长期不填坑
```

### 质量分数偏低

```bash
# 查看质检报告
python3 tools/db.py reviews <project>

# 建议：分析低分章节问题模式，针对性改进
```

### 任务堆积

```bash
# 查看运行中任务
python3 tools/db.py task_list <project> running

# 建议：检查是否有任务卡住，必要时 reset 或 timeout
```

---

## 禁止事项

- ❌ 禁止修改任何创作数据
- ❌ 禁止修改任何规划数据
- ❌ 禁止 @其他 Agent
- ✅ 只读诊断，提供建议
