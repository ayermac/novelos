# 日报命令速查

## 数据获取命令

| 命令 | 用途 | 关键字段 |
|------|------|---------|
| `projects` | 获取所有项目 | project_id, name |
| `stats <project>` | 项目统计 | 章节数、字数、均分 |
| `chapters <project>` | 章节列表 | 状态、得分 |
| `task_list <project>` | 任务列表 | status, retry_count |
| `pending_plots <project>` | 待兑现伏笔 | 伏笔代码、计划兑现章节 |

---

## 完整流程

```bash
# 步骤1：获取所有项目
python3 tools/db.py projects

# 步骤2：遍历项目获取产能统计
python3 tools/db.py stats novel_002

# 步骤3：获取章节详情，锁定卡点
python3 tools/db.py chapters novel_002

# 步骤4：扫描任务异常
python3 tools/db.py task_list novel_002

# 步骤5：获取伏笔债务
python3 tools/db.py pending_plots novel_002

# 步骤6：装填模板呈现
```

---

## 重点关注的字段

### chapters 状态

| 状态 | 含义 | 关注度 |
|------|------|--------|
| `planned` | 待创作 | 正常 |
| `draft` | 创作中 | 正常 |
| `review` | 待审核 | 正常 |
| `reviewed` | 已通过 | 正常 |
| `revision` | **退回修改** | ⚠️ 高关注 |
| `published` | 已发布 | 正常 |

### task_list 状态

| 状态 | 含义 | 关注度 |
|------|------|--------|
| `pending` | 待执行 | 正常 |
| `running` | 执行中 | 正常 |
| `completed` | 已完成 | 正常 |
| `failed` | **执行失败** | ❌ 报警 |

### pending_plots 伏笔

| 类型 | 时限 | 逾期标准 |
|------|------|---------|
| `long` | 50-100章 | 当前章节 > 计划章节 + 20 |
| `mid` | 20-50章 | 当前章节 > 计划章节 + 10 |
| `short` | 5-20章 | 当前章节 > 计划章节 + 5 |
