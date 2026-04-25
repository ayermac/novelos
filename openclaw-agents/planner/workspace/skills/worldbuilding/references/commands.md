# 世界观命令速查

## 项目管理

```bash
# 创建新项目
python3 tools/db.py add_project <project_id> <name> <genre> [description] [total_chapters]

# 获取当前项目
python3 tools/db.py current_project

# 列出所有项目
python3 tools/db.py projects
```

---

## 世界观设定

```bash
python3 tools/db.py add_world_setting <project> <category> "<title>" "<content>"
```

**category 取值**：
- `world_overview` - 世界观总纲
- `power_system` - 力量体系
- `geography` - 地理设定
- `history` - 历史背景
- `rules` - 世界规则
- `other` - 其他

---

## 角色管理

```bash
# 创建角色
python3 tools/db.py add_character <project> <name> <role> <description> [alias] [first_chapter]

# 更新角色
python3 tools/db.py update_character <project> <name_or_id> \
  --name <新名字> --alias <别名> --role <角色> \
  --description <新描述> --status <状态>

# 删除角色（软删除）
python3 tools/db.py delete_character <project> <name_or_id>

# 硬删除
python3 tools/db.py delete_character <project> <name_or_id> --hard
```

**role 取值**：`protagonist` / `antagonist` / `supporting` / `minor`

---

## 势力管理

```bash
python3 tools/db.py add_faction <project> <name> <type> <description> <relationship>
```

**type 取值**：`government` / `corporation` / `guild` / `gang` / `religious` / `other`
**relationship 取值**：`ally` / `neutral` / `enemy` / `complex`

---

## 大纲管理

```bash
# 创建大纲
python3 tools/db.py create_outline <project> <level> <sequence> "<title>" --chapters_range "<range>" --file <content_file>

# 更新大纲（相同 project_id, level, sequence 会替换）
python3 tools/db.py create_outline <project> <level> <sequence> ...

# 删除大纲
python3 tools/db.py delete_outline <project> <level> <sequence>
```

**level 取值**：`book` / `volume` / `arc`
