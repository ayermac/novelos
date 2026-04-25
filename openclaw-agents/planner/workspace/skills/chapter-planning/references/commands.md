# 章节规划命令速查

## 数据读取命令

| 命令 | 用途 |
|------|------|
| `current_project` | 获取当前项目ID |
| `next_chapter <project>` | 获取下一章信息 |
| `chapter_state <project> <chapter>` | 读取状态卡 |
| `outlines <project> [level]` | 查询大纲 |
| `characters <project>` | 读取角色 |
| `factions <project>` | 读取势力 |
| `world_settings <project>` | 读取世界观 |
| `task_list <project> running` | 获取运行中任务 |

## 数据写入命令

| 命令 | 用途 |
|------|------|
| `add_chapter` | 创建章节记录 |
| `create_instruction` | 创建写作指令 |
| `create_outline` | 创建大纲 |
| `update_outline` | 更新大纲 |
| `delete_outline` | 删除大纲 |
| `task_complete` | 标记任务完成 |
| `validate_data` | 数据校对 |

---

## 创建章节记录

```bash
python3 tools/db.py add_chapter <project> <chapter_number> "<title>" 0 planned
```

## 创建写作指令

```bash
python3 tools/db.py create_instruction \
  <project> \           # 1. 项目ID
  <chapter> \           # 2. 章节号
  "<objective>" \       # 3. 本章目标（必须以状态卡开头）
  "<key_events>" \      # 4. 关键事件（分号分隔）
  "<ending_hook>" \     # 5. 结尾钩子
  '<plots_to_resolve>' \ # 6. 要兑现的伏笔 JSON
  '<plots_to_plant>' \   # 7. 要埋设的伏笔 JSON
  "<emotion_tone>" \    # 8. 情绪基调
  '<new_characters>'    # 9. 新角色 JSON
```

**参数顺序必须严格遵守！空值用 `''` 或 `'[]'`**

---

## 大纲命令

```bash
# 创建卷级大纲
python3 tools/db.py create_outline <project> volume 1 "卷名" "1-50" --content "内容"

# 创建篇章级大纲
python3 tools/db.py create_outline <project> part 1 "篇章名" "1-10" --content "内容"

# 创建章节级大纲
python3 tools/db.py create_outline <project> chapter 1 "章节名" "1" --content "内容"

# 查询大纲
python3 tools/db.py outlines <project> [volume|part|chapter]

# 更新大纲
python3 tools/db.py update_outline <project> <level> <sequence> --content "新内容"

# 删除大纲
python3 tools/db.py delete_outline <project> <level> <sequence>
```

---

## 设定更新命令

```bash
# 更新角色状态
python3 tools/db.py update_character <project> <name> --status deceased
python3 tools/db.py update_character <project> <name> --description "新描述"

# 更新势力
python3 tools/db.py update_faction <project> <name> --relationship ally

# 新增世界观设定
python3 tools/db.py add_world_setting <project> <category> "<title>" "<content>"
```

---

## 数据校对

```bash
# 校对指定章节
python3 tools/db.py validate_data <project> <chapter>

# 校对所有待规划章节
python3 tools/db.py validate_data <project>
```

---

## 任务状态

```bash
# 成功完成
python3 tools/db.py task_complete <task_id> true

# 任务失败
python3 tools/db.py task_complete <task_id> false
```

**参数只能是 `true` 或 `false`，禁止其他内容！**

✅ 正确：`task_complete 174 true`
❌ 错误：`task_complete 174 "任务完成"`
