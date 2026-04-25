# 数据库命令详解

执笔 Agent 可用的 `db.py` 命令完整列表。

## 核心命令（创作流程必用）

### 获取项目上下文
```bash
python3 tools/db.py current_project
```
返回当前激活项目的信息。

### 读取状态卡
```bash
python3 tools/db.py chapter_state <project> <上一章号>
```
返回上一章结束时的数值状态，是创作的基准。

**返回格式（有数据时）：**
```json
{
  "chapter": 1,
  "summary": "系统Lv1，建造点数剩余5/10，有水源，无食物，辐射18%",
  "state": {
    "system": { "level": 1, "xp": 0, "max_xp": 100 },
    "build_points": { "current": 5, "daily_max": 10 }
  }
}
```

**返回格式（无数据时）：**
```json
{ "message": "没有第0章的数值状态" }
```

### 读取写作指令
```bash
python3 tools/db.py instruction <project> <chapter>
```

### 读取参考资料
```bash
python3 tools/db.py characters <project>      # 角色设定
python3 tools/db.py world_settings <project>  # 世界观
python3 tools/db.py pending_plots <project>   # 待处理伏笔
python3 tools/db.py outlines <project>        # 大纲
```

### 保存草稿
```bash
# 方式1：--content 参数（推荐，支持长文本）
python3 tools/db.py save_draft <project> <chapter> --content "章节内容..."

# 方式2：--file 参数
python3 tools/db.py save_draft <project> <chapter> --file /path/to/file.txt
```

### 更新章节状态
```bash
python3 tools/db.py update_chapter <project> <chapter> <status>
# status: planned | drafting | review | published
```

### 任务状态管理
```bash
# 查询 running 状态的任务
python3 tools/db.py task_list <project> running

# 标记任务完成（必须执行！）
python3 tools/db.py task_complete <task_id> true

# 标记任务失败
python3 tools/db.py task_complete <task_id> false
```

**参数格式：**
- `task_id` 是数字
- 第二个参数只能是 `true` 或 `false`（字符串）

```bash
# 正确
python3 tools/db.py task_complete 174 true

# 错误
python3 tools/db.py task_complete 174 "任务完成"
python3 tools/db.py task_complete 174 成功
```

---

## 验证命令

### 伏笔验证
```bash
python3 tools/db.py verify_plots <project> <chapter>
```
检测章节中伏笔是否正确处理，从三个维度检测：
1. 伏笔代码（如 S004）
2. 标题关键词（从标题提取 2-4 字词组）
3. 描述实体（从描述提取 2-6 字词组）

### 章节自动检查
```bash
python3 tools/db.py check_chapter <project> <chapter>
```
不依赖 LLM 的自动检查项：
- 字数统计（实际 vs 目标，超标50% → issue）
- 状态卡对比（状态卡说"X"，内容有"非X" → issue）
- 指令对齐（关键事件是否包含 → warning）
- 伏笔触发对象（直接 vs 间接 → issue）

**返回格式：**
```json
{
  "issues": ["状态卡矛盾：状态卡说'短期不会有大动作'，但内容有'明天反击'"],
  "warnings": ["关键事件可能缺失..."],
  "passed": false
}
```

---

## 读取质检报告
```bash
python3 tools/db.py reviews <project>
```
修改模式下读取质检的 issues 和 suggestions。

---

## 细节设定更新

创作过程中自然产生的新设定可以更新：

```bash
# 补充角色背景
python3 tools/db.py update_character <project> <name> --background "新增背景..."

# 补充角色性格
python3 tools/db.py update_character <project> <name> --description "性格描述..."

# 补充角色能力
python3 tools/db.py update_character <project> <name> --abilities "新能力..."

# 添加世界观设定
python3 tools/db.py add_world_setting <project> <category> "<title>" "<content>"
```

---

## 命令速查表

| 场景 | 命令 |
|------|------|
| 获取当前项目 | `current_project` |
| 读取上一章状态 | `chapter_state <p> <n-1>` |
| 读取写作指令 | `instruction <p> <n>` |
| 读取角色设定 | `characters <p>` |
| 读取世界观 | `world_settings <p>` |
| 读取待处理伏笔 | `pending_plots <p>` |
| 验证伏笔处理 | `verify_plots <p> <n>` |
| 自动检查章节 | `check_chapter <p> <n>` |
| 保存草稿 | `save_draft <p> <n> --content "..."` |
| 更新章节状态 | `update_chapter <p> <n> review` |
| 标记任务完成 | `task_complete <id> true` |
| 读取质检报告 | `reviews <p>` |
