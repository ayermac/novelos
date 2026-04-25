---
name: daily-report
description: |
  生成网文工厂运营日报，汇总各 Agent 产出、质量打分与系统运转瓶颈。
  
  TRIGGER when:
  - 数据秘书汇总数据
  - 用户询问运营状况、生产进度、质量报告
  - 需要生成日报、周报、项目汇报
  - 任务消息包含"日报"、"汇报"、"统计"、"瓶颈"
  
  DO NOT trigger when:
  - 简单的数据查询
  - 与运营统计无关的创作任务
---

# 运营日报与质量洞察 Skill

## 汇报规约

作为数据秘书，你直接向老板汇报。日报不仅是计件表，更是**工厂健康状况的体检单**。

**三大原则**：
1. **突出质量瓶颈**：高亮被质检退回的章节和低分项
2. **暴露系统卡点**：超时、重试失败任务列入红色预警
3. **追踪资产负债**：未兑现伏笔是项目"债务"，长期不填必须警告

---

## 工作流程

```
1. 获取所有项目
   python3 tools/db.py projects

2. 遍历每个项目获取统计
   python3 tools/db.py stats <project_id>

3. 获取章节状态（重点关注 revision）
   python3 tools/db.py chapters <project_id>

4. 扫描任务异常
   python3 tools/db.py task_list <project_id>

5. 获取伏笔债务
   python3 tools/db.py pending_plots <project_id>

6. 汇总生成格式化日报
```

---

## 命令速查

详见 `skills/daily-report/references/commands.md`

| 命令 | 用途 |
|------|------|
| `projects` | 获取所有项目 |
| `stats <project>` | 项目统计 |
| `chapters <project>` | 章节列表（关注 revision） |
| `task_list <project>` | 任务异常（关注 failed） |
| `pending_plots <project>` | 伏笔债务 |

---

## 输出模板

详见 `skills/daily-report/references/template.md`

使用 Markdown 格式，包含：
- **产能与质量大盘**：项目数、产出、均分、退回次数
- **项目运转详情**：进度、卡点、伏笔债务
- **异常与熔断预警**：重写死锁、任务失败、伏笔烂尾

---

## 自检清单

```
□ 报喜也报忧：是否如实提取了 revision 状态和低分数据？
□ 预警准确性：异常预警是否基于真实数据库状态？
□ 格式对齐：是否严格使用了 Markdown 模板？
```
