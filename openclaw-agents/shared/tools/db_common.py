#!/usr/bin/env python3
"""
网文工厂 - 公共数据库模块
所有 Agent 的 db.py 共享此模块的函数和工具

数据库路径：
- 默认位置：shared/data/novel_factory.db
- 可通过环境变量 NOVEL_FACTORY_DB 覆盖

目录结构：
/Users/jason/.openclaw/agents/
├── shared/
│   ├── data/
│   │   └── novel_factory.db      <- 数据库位置
│   └── tools/
│       ├── db_common.py          <- 本文件
│       ├── check_chapter.py      <- 章节检查工具
│       └── feedback_system.py    <- 反馈升级系统
├── planner/workspace/tools/
│   └── db.py                     <- 导入 db_common
├── author/workspace/tools/
│   └── db.py                     <- 导入 db_common
└── ...
"""

import sqlite3
import json
import sys
from pathlib import Path
from datetime import datetime
import os

# 数据库路径计算
# shared/tools/db_common.py -> shared/data/novel_factory.db
_shared_tools_dir = Path(__file__).parent  # shared/tools/
_shared_dir = _shared_tools_dir.parent      # shared/
_data_dir = _shared_dir / "data"            # shared/data/

# 优先使用环境变量，否则使用标准位置
_db_env = os.environ.get('NOVEL_FACTORY_DB')
if _db_env:
    DB_PATH = Path(_db_env)
else:
    DB_PATH = _data_dir / "novel_factory.db"

# 确保数据目录存在
_data_dir.mkdir(parents=True, exist_ok=True)

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def row_to_dict(row):
    return dict(row) if row else None

# ============== 项目管理 ==============

def cmd_projects(args=None):
    conn = get_connection()
    cursor = conn.execute("""
        SELECT project_id, name, genre, status, is_current, current_chapter,
               total_chapters_planned, target_words, created_at, updated_at
        FROM projects ORDER BY created_at DESC
    """)
    projects = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    if not projects:
        print(json.dumps({"message": "没有项目"}, ensure_ascii=False))
    else:
        print(json.dumps(projects, ensure_ascii=False, indent=2))

def cmd_add_project(args):
    if len(args) < 3:
        print("Usage: db.py add_project <project_id> <name> <genre> [description] [total_chapters]")
        return
    project_id, name, genre = args[0], args[1], args[2]
    description = args[3] if len(args) > 3 else None
    total_chapters = int(args[4]) if len(args) > 4 else 500
    conn = get_connection()
    try:
        conn.execute("""INSERT INTO projects (project_id, name, genre, description, total_chapters_planned, status, is_current)
            VALUES (?, ?, ?, ?, ?, 'active', 1)""", (project_id, name, genre, description, total_chapters))
        conn.commit()
        print(json.dumps({"success": True, "project_id": project_id, "message": f"项目 '{name}' 创建成功"}, ensure_ascii=False))
    except sqlite3.IntegrityError:
        print(json.dumps({"success": False, "error": f"项目 ID '{project_id}' 已存在"}, ensure_ascii=False))
    finally:
        conn.close()

def cmd_current_project(args=None):
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM projects WHERE is_current = 1")
    project = row_to_dict(cursor.fetchone())
    conn.close()
    if project:
        print(json.dumps(project, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"message": "没有当前项目"}, ensure_ascii=False))

def cmd_set_current_project(args):
    if len(args) < 1:
        print("Usage: db.py set_current_project <project_id>")
        return
    conn = get_connection()
    conn.execute("UPDATE projects SET is_current = 0")
    conn.execute("UPDATE projects SET is_current = 1 WHERE project_id = ?", (args[0],))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "current_project": args[0]}, ensure_ascii=False))

def cmd_update_project(args):
    """
    更新项目信息。
    用法: db.py update_project <project_id> [--name <n>] [--genre <g>] [--description <d>] [--status <s>] [--total_chapters <n>] [--current_chapter <n>] [--target_words <n>]
    """
    if len(args) < 1:
        print("Usage: db.py update_project <project_id> [--name <n>] [--genre <g>] [--description <d>] [--status <s>] [--total_chapters <n>] [--current_chapter <n>] [--target_words <n>]")
        return
    project_id = args[0]
    conn = get_connection()
    existing = row_to_dict(conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone())
    if not existing:
        print(json.dumps({"success": False, "error": f"项目 '{project_id}' 不存在"}, ensure_ascii=False))
        conn.close()
        return
    fields = {}
    j = 1
    while j < len(args):
        if args[j] == '--name' and j+1 < len(args): fields['name'] = args[j+1]; j += 2
        elif args[j] == '--genre' and j+1 < len(args): fields['genre'] = args[j+1]; j += 2
        elif args[j] == '--description' and j+1 < len(args): fields['description'] = args[j+1]; j += 2
        elif args[j] == '--status' and j+1 < len(args): fields['status'] = args[j+1]; j += 2
        elif args[j] == '--total_chapters' and j+1 < len(args): fields['total_chapters_planned'] = int(args[j+1]); j += 2
        elif args[j] == '--current_chapter' and j+1 < len(args): fields['current_chapter'] = int(args[j+1]); j += 2
        elif args[j] == '--target_words' and j+1 < len(args): fields['target_words'] = int(args[j+1]); j += 2
        else: j += 1
    if not fields:
        print(json.dumps({"success": False, "error": "请提供至少一个 --flag"}, ensure_ascii=False))
        conn.close()
        return
    set_clause = ', '.join(f'{k}=?' for k in fields.keys())
    values = list(fields.values()) + [project_id]
    conn.execute(f"UPDATE projects SET {set_clause} WHERE project_id=?", values)
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "project_id": project_id, "updated_fields": list(fields.keys())}, ensure_ascii=False))

# ============== 世界观管理 ==============

def cmd_add_world_setting(args):
    if len(args) < 4:
        print("Usage: db.py add_world_setting <project> <category> <title> <content>")
        return
    conn = get_connection()
    conn.execute("INSERT INTO world_settings (project_id, category, title, content) VALUES (?, ?, ?, ?)",
        (args[0], args[1], args[2], ' '.join(args[3:])))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True}, ensure_ascii=False))

def cmd_world_settings(args):
    if len(args) < 1:
        print("Usage: db.py world_settings <project> [category]")
        return
    project_id = args[0]
    category = args[1] if len(args) > 1 else None
    conn = get_connection()
    if category:
        cursor = conn.execute("SELECT * FROM world_settings WHERE project_id=? AND category=? ORDER BY id",
            (project_id, category))
    else:
        cursor = conn.execute("SELECT * FROM world_settings WHERE project_id=? ORDER BY category, id",
            (project_id,))
    settings = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    print(json.dumps(settings, ensure_ascii=False, indent=2))

def cmd_update_world_setting(args):
    if len(args) < 4:
        print("Usage: db.py update_world_setting <project> <category> <title> <content>")
        return
    project_id, category, title = args[0], args[1], args[2]
    content = ' '.join(args[3:])
    conn = get_connection()
    conn.execute("UPDATE world_settings SET content=? WHERE project_id=? AND category=? AND title=?",
        (content, project_id, category, title))
    if not conn.total_changes:
        print(json.dumps({"success": False, "error": "设定不存在"}, ensure_ascii=False))
    else:
        conn.commit()
        print(json.dumps({"success": True}, ensure_ascii=False))
    conn.close()

def cmd_delete_world_setting(args):
    if len(args) < 4:
        print("Usage: db.py delete_world_setting <project> <category> <title>")
        return
    conn = get_connection()
    conn.execute("DELETE FROM world_settings WHERE project_id=? AND category=? AND title=?",
        (args[0], args[1], args[2]))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True}, ensure_ascii=False))

def cmd_update_world_setting(args):
    """
    更新世界观设定。
    用法: db.py update_world_setting <project> <setting_id> [--category <c>] [--title <t>] [--content <c>] [--notes <n>]
    也支持: db.py update_world_setting <project> <category> <title> --content <新内容>
    """
    if len(args) < 3:
        print("Usage: db.py update_world_setting <project> <id_or_category> <title_or_flag> [--title <t>] [--content <c>] [--category <c>] [--notes <n>]")
        return
    project_id = args[0]
    conn = get_connection()

    # 先尝试用 id 定位
    try:
        setting_id = int(args[1])
        existing = row_to_dict(conn.execute("SELECT * FROM world_settings WHERE id=? AND project_id=?",
            (setting_id, project_id)).fetchone())
    except ValueError:
        setting_id = None
        existing = row_to_dict(conn.execute("SELECT * FROM world_settings WHERE project_id=? AND category=? AND title=?",
            (project_id, args[1], args[2])).fetchone())

    if not existing:
        print(json.dumps({"success": False, "error": "设定不存在"}, ensure_ascii=False))
        conn.close()
        return

    # 解析 flag 参数
    fields = {}
    i = 1 if setting_id else 3  # 跳过已用的 id 或 category+title
    flag_list = args[i:]
    j = 0
    while j < len(flag_list):
        if flag_list[j] == '--title':
            fields['title'] = flag_list[j+1]; j += 2
        elif flag_list[j] == '--content':
            fields['content'] = flag_list[j+1]; j += 2
        elif flag_list[j] == '--category':
            fields['category'] = flag_list[j+1]; j += 2
        elif flag_list[j] == '--notes':
            fields['notes'] = flag_list[j+1]; j += 2
        else:
            j += 1

    if not fields:
        # 兼容旧版纯内容更新
        if i < len(args):
            fields['content'] = ' '.join(args[i:])
        else:
            print(json.dumps({"success": False, "error": "没有提供更新内容"}, ensure_ascii=False))
            conn.close()
            return

    set_clause = ', '.join(f'{k}=?' for k in fields.keys())
    values = list(fields.values()) + [existing['id']]
    conn.execute(f"UPDATE world_settings SET {set_clause} WHERE id=?", values)
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "id": existing['id'], "updated_fields": list(fields.keys())}, ensure_ascii=False))

def cmd_delete_world_setting(args):
    """删除世界观设定。用法: db.py delete_world_setting <project> <id_or_title>"""
    if len(args) < 2:
        print("Usage: db.py delete_world_setting <project> <id_or_title>")
        return
    project_id = args[0]
    conn = get_connection()
    try:
        setting_id = int(args[1])
        cursor = conn.execute("SELECT * FROM world_settings WHERE id=? AND project_id=?", (setting_id, project_id))
    except ValueError:
        cursor = conn.execute("SELECT * FROM world_settings WHERE project_id=? AND title=?", (project_id, args[1]))
    existing = row_to_dict(cursor.fetchone())
    if not existing:
        print(json.dumps({"success": False, "error": "设定不存在"}, ensure_ascii=False))
        conn.close()
        return
    conn.execute("DELETE FROM world_settings WHERE id=?", (existing['id'],))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "title": existing['title']}, ensure_ascii=False))

# ============== 角色管理 ==============

def cmd_add_character(args):
    if len(args) < 4:
        print("Usage: db.py add_character <project> <name> <role> <description> [alias] [first_chapter]")
        return
    project_id, name, role, description = args[0], args[1], args[2], args[3]
    alias = args[4] if len(args) > 4 else None
    first_chapter = int(args[5]) if len(args) > 5 else None
    conn = get_connection()
    conn.execute("""INSERT INTO characters (project_id, name, alias, role, description, first_appearance, status)
        VALUES (?, ?, ?, ?, ?, ?, 'active')""", (project_id, name, alias, role, description, first_chapter))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "name": name}, ensure_ascii=False))

def cmd_characters(args):
    if len(args) < 1:
        print("Usage: db.py characters <project>")
        return
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM characters WHERE project_id = ? ORDER BY role, first_appearance", (args[0],))
    characters = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    print(json.dumps(characters, ensure_ascii=False, indent=2))

def cmd_update_character(args):
    """
    更新已有角色信息。
    
    用法: db.py update_character <project> <name_or_id>
          [--name <new_name>] [--alias <alias>] [--role <role>]
          [--description <desc>] [--status <status>] [--first_chapter <n>]
    
    如果参数不带 --flag，则为旧版位置参数：
    db.py update_character <project> <name> <description> [role] [alias]
    """
    if len(args) < 2:
        print("Usage: db.py update_character <project> <name_or_id> [--name <n>] [--alias <a>] [--role <r>] [--description <d>] [--status <s>] [--first_chapter <n>]")
        return
    
    project_id = args[0]
    identifier = args[1]
    
    # 检测是否为新版 flag 模式
    flag_args = args[2:] if len(args) > 2 else []
    if any(a.startswith('--') for a in flag_args):
        # flag 模式：至少需要一个更新字段
        fields = {}
        i = 0
        while i < len(flag_args):
            flag = flag_args[i]
            if i + 1 >= len(flag_args):
                print(f"Error: {flag} 缺少值")
                return
            value = flag_args[i + 1]
            field_map = {
                '--name': 'name',
                '--alias': 'alias',
                '--role': 'role',
                '--description': 'description',
                '--status': 'status',
                '--first_chapter': 'first_appearance',
            }
            if flag not in field_map:
                print(f"Error: 未知参数 {flag}")
                return
            if flag == '--first_chapter':
                try:
                    value = int(value)
                except ValueError:
                    print(f"Error: --first_chapter 必须是整数")
                    return
            fields[field_map[flag]] = value
            i += 2
        if not fields:
            print("Error: 请提供至少一个 --flag 字段来更新")
            return
    else:
        # 旧版位置参数模式
        if len(flag_args) < 1:
            print("Usage (旧版): db.py update_character <project> <name> <description> [role] [alias]")
            return
        fields = {'description': ' '.join(flag_args[:1])}
        if len(flag_args) > 1:
            fields['role'] = flag_args[1]
        if len(flag_args) > 2:
            fields['alias'] = flag_args[2]
    
    conn = get_connection()
    # 按 name 或 id 查找
    try:
        char_id = int(identifier)
        cursor = conn.execute("SELECT * FROM characters WHERE project_id=? AND id=?", (project_id, char_id))
    except ValueError:
        cursor = conn.execute("SELECT * FROM characters WHERE project_id=? AND name=?", (project_id, identifier))
    
    existing = row_to_dict(cursor.fetchone())
    if not existing:
        print(json.dumps({"success": False, "error": f"角色 '{identifier}' 不存在于项目 '{project_id}' 中"}, ensure_ascii=False))
        conn.close()
        return
    
    # 如果更新了 name，检查新名字是否冲突
    if 'name' in fields:
        cursor = conn.execute("SELECT id FROM characters WHERE project_id=? AND name=? AND id!=?",
            (project_id, fields['name'], existing['id']))
        if cursor.fetchone():
            print(json.dumps({"success": False, "error": f"角色名 '{fields['name']}' 已存在"}, ensure_ascii=False))
            conn.close()
            return
    
    set_clause = ', '.join(f'{k}=?' for k in fields.keys())
    values = list(fields.values()) + [existing['id']]
    conn.execute(f"UPDATE characters SET {set_clause} WHERE id=?", values)
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "name": fields.get('name', identifier), "updated_fields": list(fields.keys())}, ensure_ascii=False))

def cmd_delete_character(args):
    """
    删除或停用角色（软删除，设置 status='inactive'）。
    
    用法: db.py delete_character <project> <name_or_id> [--hard]
    带 --hard 则物理删除，不带则软停用。
    """
    if len(args) < 2:
        print("Usage: db.py delete_character <project> <name_or_id> [--hard]")
        return
    
    project_id = args[0]
    identifier = args[1]
    hard = '--hard' in args
    
    conn = get_connection()
    try:
        char_id = int(identifier)
        cursor = conn.execute("SELECT * FROM characters WHERE project_id=? AND id=?", (project_id, char_id))
    except ValueError:
        cursor = conn.execute("SELECT * FROM characters WHERE project_id=? AND name=?", (project_id, identifier))
    
    existing = row_to_dict(cursor.fetchone())
    if not existing:
        print(json.dumps({"success": False, "error": f"角色 '{identifier}' 不存在"}, ensure_ascii=False))
        conn.close()
        return
    
    if hard:
        conn.execute("DELETE FROM characters WHERE id=?", (existing['id'],))
    else:
        conn.execute("UPDATE characters SET status='inactive' WHERE id=?", (existing['id'],))
    
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "name": existing['name'], "action": "hard_deleted" if hard else "soft_deleted(inactive)"}, ensure_ascii=False))

# ============== 势力管理 ==============

def cmd_factions(args):
    """列出项目中的势力。用法: db.py factions <project> [name]"""
    if len(args) < 1:
        print("Usage: db.py factions <project> [name]")
        return
    project_id = args[0]
    name = args[1] if len(args) > 1 else None
    conn = get_connection()
    if name:
        cursor = conn.execute("SELECT * FROM factions WHERE project_id=? AND name=?", (project_id, name))
        result = row_to_dict(cursor.fetchone())
        if not result: result = []
        else: result = [result]
    else:
        cursor = conn.execute("SELECT * FROM factions WHERE project_id=? ORDER BY type, name", (project_id,))
        result = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))

def cmd_update_faction(args):
    """
    更新势力。
    用法: db.py update_faction <project> <id_or_name> [--name <n>] [--type <t>] [--description <d>] [--relationship <r>] [--goals <g>]
    """
    if len(args) < 2:
        print("Usage: db.py update_faction <project> <id_or_name> [--name <n>] [--type <t>] [--description <d>] [--relationship <r>] [--goals <g>]")
        return
    project_id = args[0]
    conn = get_connection()
    try:
        faction_id = int(args[1])
        existing = row_to_dict(conn.execute("SELECT * FROM factions WHERE id=? AND project_id=?", (faction_id, project_id)).fetchone())
    except ValueError:
        existing = row_to_dict(conn.execute("SELECT * FROM factions WHERE project_id=? AND name=?", (project_id, args[1])).fetchone())
    if not existing:
        print(json.dumps({"success": False, "error": "势力不存在"}, ensure_ascii=False))
        conn.close()
        return
    fields = {}
    j = 2
    while j < len(args):
        if args[j] == '--name' and j+1 < len(args):
            fields['name'] = args[j+1]; j += 2
        elif args[j] == '--type' and j+1 < len(args):
            fields['type'] = args[j+1]; j += 2
        elif args[j] == '--description' and j+1 < len(args):
            fields['description'] = args[j+1]; j += 2
        elif args[j] == '--relationship' and j+1 < len(args):
            fields['relationship_with_protagonist'] = args[j+1]; j += 2
        elif args[j] == '--goals' and j+1 < len(args):
            fields['goals'] = args[j+1]; j += 2
        else:
            j += 1
    if not fields:
        print(json.dumps({"success": False, "error": "请提供至少一个 --flag"}, ensure_ascii=False))
        conn.close()
        return
    set_clause = ', '.join(f'{k}=?' for k in fields.keys())
    values = list(fields.values()) + [existing['id']]
    conn.execute(f"UPDATE factions SET {set_clause} WHERE id=?", values)
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "name": existing['name'], "updated_fields": list(fields.keys())}, ensure_ascii=False))

def cmd_delete_faction(args):
    """删除势力。用法: db.py delete_faction <project> <id_or_name>"""
    if len(args) < 2:
        print("Usage: db.py delete_faction <project> <id_or_name>")
        return
    project_id = args[0]
    conn = get_connection()
    try:
        faction_id = int(args[1])
        existing = row_to_dict(conn.execute("SELECT * FROM factions WHERE id=? AND project_id=?", (faction_id, project_id)).fetchone())
    except ValueError:
        existing = row_to_dict(conn.execute("SELECT * FROM factions WHERE project_id=? AND name=?", (project_id, args[1])).fetchone())
    if not existing:
        print(json.dumps({"success": False, "error": "势力不存在"}, ensure_ascii=False))
        conn.close()
        return
    conn.execute("DELETE FROM factions WHERE id=?", (existing['id'],))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "name": existing['name']}, ensure_ascii=False))

def cmd_add_faction(args):
    if len(args) < 5:
        print("Usage: db.py add_faction <project> <name> <type> <description> <relationship>")
        return
    conn = get_connection()
    conn.execute("""INSERT INTO factions (project_id, name, type, description, relationship_with_protagonist)
        VALUES (?, ?, ?, ?, ?)""", (args[0], args[1], args[2], args[3], args[4]))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "name": args[1]}, ensure_ascii=False))

# ============== 章节管理 ==============

def cmd_chapters(args):
    if len(args) < 1:
        print("Usage: db.py chapters <project>")
        return
    conn = get_connection()
    cursor = conn.execute("""
        SELECT c.*, i.objective as instruction_objective, i.key_events,
               r.score as review_score, r.pass as review_pass
        FROM chapters c
        LEFT JOIN instructions i ON c.instruction_id = i.id
        LEFT JOIN reviews r ON c.id = r.chapter_id
        WHERE c.project_id = ? ORDER BY c.chapter_number""", (args[0],))
    chapters = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    print(json.dumps(chapters, ensure_ascii=False, indent=2))

def cmd_add_chapter(args):
    if len(args) < 3:
        print("Usage: db.py add_chapter <project> <chapter_number> <title> [word_count] [status]")
        return
    project_id, chapter_number, title = args[0], int(args[1]), args[2]
    word_count = int(args[3]) if len(args) > 3 else 0
    status = args[4] if len(args) > 4 else 'planned'
    conn = get_connection()
    conn.execute("""INSERT OR REPLACE INTO chapters (project_id, chapter_number, title, word_count, status)
        VALUES (?, ?, ?, ?, ?)""", (project_id, chapter_number, title, word_count, status))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "chapter": chapter_number}, ensure_ascii=False))

def cmd_next_chapter(args):
    project_id = args[0] if args else None
    if not project_id:
        conn = get_connection()
        cursor = conn.execute("SELECT project_id FROM projects WHERE is_current = 1")
        row = cursor.fetchone()
        conn.close()
        if not row:
            print(json.dumps({"error": "没有当前项目"}, ensure_ascii=False))
            return
        project_id = row['project_id']
    conn = get_connection()
    cursor = conn.execute("""
        SELECT c.*, i.id as instruction_id, i.objective, i.key_events, i.ending_hook,
               i.plots_to_resolve, i.plots_to_plant, i.emotion_tone, i.status as instruction_status,
               CASE WHEN i.id IS NOT NULL THEN 1 ELSE 0 END as has_instruction
        FROM chapters c
        LEFT JOIN instructions i ON c.chapter_number = i.chapter_number AND c.project_id = i.project_id
        WHERE c.project_id = ? AND c.status = 'planned'
        ORDER BY c.chapter_number LIMIT 1""", (project_id,))
    chapter = row_to_dict(cursor.fetchone())
    conn.close()
    if chapter:
        print(json.dumps(chapter, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"message": "没有待创作的章节"}, ensure_ascii=False))

def cmd_update_chapter(args):
    if len(args) < 3:
        print("Usage: db.py update_chapter <project> <chapter> <status> [word_count] [score]")
        return
    project_id, chapter_number, status = args[0], int(args[1]), args[2]
    word_count = int(args[3]) if len(args) > 3 else None
    conn = get_connection()
    if status == 'published':
        conn.execute("""UPDATE chapters SET status=?, word_count=COALESCE(?,word_count),
            published_at=datetime('now','+8 hours') WHERE project_id=? AND chapter_number=?""",
            (status, word_count, project_id, chapter_number))
        conn.execute("UPDATE projects SET current_chapter=max(current_chapter,?) WHERE project_id=?",
            (chapter_number, project_id))
    else:
        conn.execute("""UPDATE chapters SET status=?, word_count=COALESCE(?,word_count)
            WHERE project_id=? AND chapter_number=?""", (status, word_count, project_id, chapter_number))
    conn.commit()
    conn.close()
    result = {"success": True, "chapter": chapter_number, "status": status}
    print(json.dumps(result, ensure_ascii=False))

def cmd_chapter_content(args):
    if len(args) < 3:
        print("Usage: db.py chapter_content <project> <chapter> <version>")
        return
    conn = get_connection()
    cursor = conn.execute("SELECT chapter_number, title, content, word_count FROM chapters WHERE project_id=? AND chapter_number=?",
        (args[0], int(args[1])))
    chapter = row_to_dict(cursor.fetchone())
    conn.close()
    if chapter:
        if args[2] in ('draft', 'published'):
            print(chapter.get('content', ''))
        else:
            print(json.dumps({"error": f"未知版本: {args[2]}"}, ensure_ascii=False))
    else:
        print(json.dumps({"error": "章节不存在"}, ensure_ascii=False))

def cmd_save_draft(args):
    """
    保存草稿（自动版本管理）。

    用法: db.py save_draft <project> <chapter> --content "..." | --file <path>
    """
    if len(args) < 3:
        print("Usage: db.py save_draft <project> <chapter> --content \"...\" | --file <path>")
        return
    project_id, chapter_number = args[0], int(args[1])
    if args[2] == '--content':
        content = args[3] if len(args) > 3 else ''
    elif args[2] == '--file':
        file_path = args[3]
        if not Path(file_path).exists():
            print(f"Error: File not found: {file_path}")
            return
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content_input = args[2]
        try:
            if Path(content_input).exists() and len(content_input) < 1000:
                with open(content_input, 'r', encoding='utf-8') as f:
                    content = f.read()
            else:
                content = content_input
        except OSError:
            content = content_input
    word_count = len(content)
    conn = get_connection()

    # 1. 自动保存版本（版本管理）
    cursor = conn.execute("""
        SELECT MAX(version) as max_version
        FROM chapter_versions
        WHERE project_id = ? AND chapter = ?
    """, (project_id, chapter_number))
    max_version = cursor.fetchone()['max_version'] or 0

    # 保存新版本（使用北京时间）
    conn.execute("""
        INSERT INTO chapter_versions (project_id, chapter, version, content, word_count, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, 'author', datetime('now', '+8 hours'))
    """, (project_id, chapter_number, max_version + 1, content, word_count))

    # 2. 更新章节表
    conn.execute("UPDATE chapters SET content=?, word_count=?, status='review' WHERE project_id=? AND chapter_number=?",
        (content, word_count, project_id, chapter_number))

    conn.commit()
    conn.close()
    print(json.dumps({
        "success": True,
        "chapter": chapter_number,
        "word_count": word_count,
        "version": max_version + 1
    }, ensure_ascii=False))

def cmd_publish_chapter(args):
    if len(args) < 2:
        print("Usage: db.py publish_chapter <project> <chapter>")
        return
    project_id, chapter_number = args[0], int(args[1])
    conn = get_connection()
    
    # 1. 更新章节状态
    conn.execute("UPDATE chapters SET status='published', published_at=datetime('now','+8 hours') WHERE project_id=? AND chapter_number=?",
        (project_id, chapter_number))
    
    # 2. 更新指令状态
    conn.execute("UPDATE instructions SET status='completed' WHERE project_id=? AND chapter_number=?",
        (project_id, chapter_number))
    
    # 3. 更新项目当前章节
    conn.execute("UPDATE projects SET current_chapter=? WHERE project_id=?", (chapter_number, project_id))
    
    # 4. 自动兑现伏笔
    cursor = conn.execute("SELECT plots_to_resolve FROM instructions WHERE project_id=? AND chapter_number=?", (project_id, chapter_number))
    instruction = cursor.fetchone()
    resolved_plots = []
    if instruction and instruction['plots_to_resolve']:
        try:
            plots_to_resolve = json.loads(instruction['plots_to_resolve'])
            for code in plots_to_resolve:
                # 提取伏笔代码（支持 "P001:描述" 格式）
                plot_code = code.split(':')[0] if ':' in code else code
                # 更新伏笔状态
                conn.execute("UPDATE plot_holes SET status='resolved', resolved_chapter=? WHERE project_id=? AND code=?",
                    (chapter_number, project_id, plot_code))
                # 记录到 chapter_plots
                cursor = conn.execute("SELECT id FROM plot_holes WHERE project_id=? AND code=?", (project_id, plot_code))
                plot_row = cursor.fetchone()
                if plot_row:
                    cursor = conn.execute("SELECT id FROM chapters WHERE project_id=? AND chapter_number=?", (project_id, chapter_number))
                    chapter_row = cursor.fetchone()
                    if chapter_row:
                        conn.execute("INSERT OR IGNORE INTO chapter_plots (project_id, chapter_id, plot_id, action, created_at) VALUES (?,?,?, 'resolved', datetime('now','+8 hours'))",
                            (project_id, chapter_row['id'], plot_row['id']))
                resolved_plots.append(plot_code)
        except json.JSONDecodeError:
            pass
    
    conn.commit()
    conn.close()
    result = {"success": True, "chapter": chapter_number, "status": "published"}
    if resolved_plots:
        result["resolved_plots"] = resolved_plots
    print(json.dumps(result, ensure_ascii=False))

# ============== 指令管理 ==============

def cmd_instruction(args):
    if len(args) < 2:
        print("Usage: db.py instruction <project> <chapter>")
        return
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM instructions WHERE project_id=? AND chapter_number=?", (args[0], int(args[1])))
    instruction = row_to_dict(cursor.fetchone())
    conn.close()
    if instruction:
        print(json.dumps(instruction, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"message": "没有找到指令"}, ensure_ascii=False))

def cmd_instructions(args):
    """列出指令。用法: db.py instructions <project> [status]"""
    if len(args) < 1:
        print("Usage: db.py instructions <project> [status]")
        return
    project_id = args[0]
    status = args[1] if len(args) > 1 else None
    conn = get_connection()
    if status:
        cursor = conn.execute("SELECT * FROM instructions WHERE project_id=? AND status=? ORDER BY chapter_number", (project_id, status))
    else:
        cursor = conn.execute("SELECT * FROM instructions WHERE project_id=? ORDER BY chapter_number", (project_id,))
    instructions = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    print(json.dumps(instructions, ensure_ascii=False, indent=2))

def cmd_update_instruction(args):
    """
    更新写作指令。
    用法: db.py update_instruction <project> <chapter> [--objective <o>] [--key_events <e>] [--plots_to_resolve <p>] [--plots_to_plant <p>] [--emotion_tone <t>] [--ending_hook <e>] [--status <s>] [--file <path>]
    """
    if len(args) < 3:
        print("Usage: db.py update_instruction <project> <chapter> [--objective <o>] [--key_events <e>] [--plots_to_resolve <p>] [--plots_to_plant <p>] [--emotion_tone <t>] [--ending_hook <e>] [--status <s>]")
        return
    project_id, chapter_num = args[0], int(args[1])
    conn = get_connection()
    existing = row_to_dict(conn.execute("SELECT * FROM instructions WHERE project_id=? AND chapter_number=?", (project_id, chapter_num)).fetchone())
    if not existing:
        print(json.dumps({"success": False, "error": "指令不存在"}, ensure_ascii=False))
        conn.close()
        return
    fields = {}
    j = 2
    while j < len(args):
        if args[j] in ('--objective', '--key_events', '--plots_to_resolve', '--plots_to_plant', '--emotion_tone', '--ending_hook', '--status') and j+1 < len(args):
            fields[args[j].lstrip('--')] = args[j+1]; j += 2
        else: j += 1
    if not fields:
        print(json.dumps({"success": False, "error": "请提供至少一个 --flag"}, ensure_ascii=False))
        conn.close()
        return
    set_clause = ', '.join(f'{k}=?' for k in fields.keys())
    values = list(fields.values()) + [project_id, chapter_num]
    conn.execute(f"UPDATE instructions SET {set_clause} WHERE project_id=? AND chapter_number=?", values)
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "chapter": chapter_num, "updated_fields": list(fields.keys())}, ensure_ascii=False))

def cmd_create_outline(args):
    if len(args) < 4:
        print("Usage: db.py create_outline <project> <level> <sequence> <title> [--chapters_range <range>] [--content <text>] [--file <path>]")
        return
    project_id, level, sequence, title = args[0], args[1], int(args[2]), args[3]
    content = None
    chapters_range = '0-0'
    j = 4
    while j < len(args):
        if args[j] == '--file' and j+1 < len(args):
            with open(args[j+1], 'r', encoding='utf-8') as f: content = f.read(); j += 2
        elif args[j] == '--content' and j+1 < len(args):
            content = args[j+1]; j += 2
        elif args[j] == '--chapters_range' and j+1 < len(args):
            chapters_range = args[j+1]; j += 2
        else: j += 1
    if content is None:
        print(json.dumps({"error": "请提供 --content 或 --file"}, ensure_ascii=False))
        return
    conn = get_connection()
    conn.execute("""INSERT OR REPLACE INTO outlines (project_id, level, sequence, title, content, chapters_range, created_at, updated_at)
        VALUES (?,?,?,?,?, ?, datetime('now','+8 hours'), datetime('now','+8 hours'))""",
        (project_id, level, sequence, title, content, chapters_range))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "id": project_id}, ensure_ascii=False))

def cmd_outlines(args):
    """列出大纲。用法: db.py outlines <project> [level]"""
    if len(args) < 1:
        print("Usage: db.py outlines <project> [level]")
        return
    project_id = args[0]
    level = args[1] if len(args) > 1 else None
    conn = get_connection()
    if level:
        cursor = conn.execute("SELECT * FROM outlines WHERE project_id=? AND level=? ORDER BY sequence", (project_id, level))
    else:
        cursor = conn.execute("SELECT * FROM outlines WHERE project_id=? ORDER BY level, sequence", (project_id,))
    outlines = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    print(json.dumps(outlines, ensure_ascii=False, indent=2))

def cmd_update_outline(args):
    """
    更新大纲。
    用法: db.py update_outline <project> <id_or_level> <sequence> [--title <t>] [--content <c>] [--file <f>] [--chapters_range <r>]
    """
    if len(args) < 3:
        print("Usage: db.py update_outline <project> <id_or_level> <seq> [--title <t>] [--content <c>] [--file <f>] [--chapters_range <r>]")
        return
    project_id = args[0]
    conn = get_connection()
    try:
        outline_id = int(args[1])
        existing = row_to_dict(conn.execute("SELECT * FROM outlines WHERE id=? AND project_id=?", (outline_id, project_id)).fetchone())
    except ValueError:
        level, seq = args[1], int(args[2])
        existing = row_to_dict(conn.execute("SELECT * FROM outlines WHERE project_id=? AND level=? AND sequence=?", (project_id, level, seq)).fetchone())
    if not existing:
        print(json.dumps({"success": False, "error": "大纲不存在"}, ensure_ascii=False))
        conn.close()
        return
    fields = {}
    j = 3 if existing.get('id') != int(args[1]) else 2
    # 如果用了 id 模式，跳过的参数不同
    try:
        int(args[1])
        j = 2
    except ValueError:
        j = 3
    while j < len(args):
        if args[j] == '--title' and j+1 < len(args): fields['title'] = args[j+1]; j += 2
        elif args[j] == '--content' and j+1 < len(args): fields['content'] = args[j+1]; j += 2
        elif args[j] == '--file' and j+1 < len(args):
            with open(args[j+1], 'r', encoding='utf-8') as f: fields['content'] = args[j+1] = f.read()
            j += 2
        elif args[j] == '--chapters_range' and j+1 < len(args): fields['chapters_range'] = args[j+1]; j += 2
        else: j += 1
    # updated_at 由 SQL 语句中的 datetime('now','+8 hours') 处理
    if not fields:
        print(json.dumps({"success": False, "error": "请提供更新内容"}, ensure_ascii=False))
        conn.close()
        return
    set_clause = ', '.join(f'{k}=?' for k in fields.keys())
    values = list(fields.values()) + [existing['id']]
    conn.execute(f"UPDATE outlines SET {set_clause}, updated_at=datetime('now','+8 hours') WHERE id=?", values)
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "title": existing['title'], "updated_fields": [k for k in fields.keys() if k != 'updated_at']}, ensure_ascii=False))

def cmd_delete_outline(args):
    """删除大纲。用法: db.py delete_outline <project> <id_or_level> [sequence]"""
    if len(args) < 2:
        print("Usage: db.py delete_outline <project> <id_or_level> [sequence]")
        return
    project_id = args[0]
    conn = get_connection()
    try:
        outline_id = int(args[1])
        existing = row_to_dict(conn.execute("SELECT * FROM outlines WHERE id=? AND project_id=?", (outline_id, project_id)).fetchone())
    except ValueError:
        level, seq = args[1], int(args[2]) if len(args) > 2 else 0
        existing = row_to_dict(conn.execute("SELECT * FROM outlines WHERE project_id=? AND level=? AND sequence=?", (project_id, level, seq)).fetchone())
    if not existing:
        print(json.dumps({"success": False, "error": "大纲不存在"}, ensure_ascii=False))
        conn.close()
        return
    conn.execute("DELETE FROM outlines WHERE id=?", (existing['id'],))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "title": existing['title']}, ensure_ascii=False))

def cmd_create_instruction(args):
    if len(args) < 5:
        print("Usage: db.py create_instruction <project> <chapter> <objective> <key_events> <ending_hook> [plots_to_resolve] [plots_to_plant] [emotion_tone] [new_characters]")
        return
    project_id = args[0]
    chapter_num = int(args[1])
    objective, key_events, ending_hook = args[2], args[3], args[4]
    plots_to_resolve = args[5] if len(args) > 5 else '[]'
    plots_to_plant = args[6] if len(args) > 6 else '[]'
    emotion_tone = args[7] if len(args) > 7 else None
    new_characters = args[8] if len(args) > 8 else '[]'
    
    # 🔒 数据校对：在创建指令前检查所有引用是否有效
    def extract_code(item):
        """提取伏笔代码（支持 'P001:描述' 格式）"""
        if isinstance(item, str):
            return item.split(':')[0] if ':' in item else item
        return item
    
    validation_issues = []
    validation_warnings = []
    
    # 1. 校对伏笔引用
    try:
        plots_plant_list = json.loads(plots_to_plant) if plots_to_plant else []
        plots_plant_codes = [extract_code(p) for p in plots_plant_list]
    except json.JSONDecodeError:
        validation_issues.append({"type": "invalid_json", "field": "plots_to_plant", "message": "plots_to_plant 不是有效 JSON"})
        plots_plant_codes = []
    
    try:
        plots_resolve_list = json.loads(plots_to_resolve) if plots_to_resolve else []
        plots_resolve_codes = [extract_code(p) for p in plots_resolve_list]
    except json.JSONDecodeError:
        validation_issues.append({"type": "invalid_json", "field": "plots_to_resolve", "message": "plots_to_resolve 不是有效 JSON"})
        plots_resolve_codes = []
    
    # 2. 校对新角色数据
    try:
        new_char_list = json.loads(new_characters) if new_characters else []
        for i, char in enumerate(new_char_list):
            if not isinstance(char, dict):
                validation_issues.append({"type": "invalid_character", "index": i, "message": f"角色 {i} 不是有效对象"})
            elif 'name' not in char:
                validation_issues.append({"type": "missing_field", "index": i, "field": "name", "message": f"角色 {i} 缺少 name 字段"})
    except json.JSONDecodeError:
        validation_issues.append({"type": "invalid_json", "field": "new_characters", "message": "new_characters 不是有效 JSON"})
        new_char_list = []
    
    # 连接数据库进行深度校对
    conn = get_connection()
    
    # 3. 校对 plots_to_plant 中的伏笔是否存在
    for code in plots_plant_codes:
        cursor = conn.execute("SELECT id FROM plot_holes WHERE project_id=? AND code=?", (project_id, code))
        if not cursor.fetchone():
            validation_issues.append({
                "type": "missing_plot",
                "field": "plots_to_plant",
                "code": code,
                "message": f"伏笔 {code} 不存在，请先执行 add_plot 创建",
                "action": f"python3 tools/db.py add_plot {project_id} {code} <type> '<title>' '<description>' {chapter_num} <resolve_chapter>"
            })
    
    # 4. 校对 plots_to_resolve 中的伏笔是否存在且已埋设
    for code in plots_resolve_codes:
        cursor = conn.execute("SELECT id, planted_chapter, status FROM plot_holes WHERE project_id=? AND code=?", (project_id, code))
        plot = cursor.fetchone()
        if not plot:
            validation_issues.append({
                "type": "missing_plot",
                "field": "plots_to_resolve",
                "code": code,
                "message": f"伏笔 {code} 不存在，无法兑现"
            })
        elif plot['planted_chapter'] and plot['planted_chapter'] > chapter_num:
            validation_issues.append({
                "type": "plot_not_planted",
                "field": "plots_to_resolve",
                "code": code,
                "message": f"伏笔 {code} 将在第{plot['planted_chapter']}章埋设，无法在第{chapter_num}章兑现"
            })
        elif plot['status'] == 'resolved':
            validation_warnings.append({
                "type": "plot_already_resolved",
                "code": code,
                "message": f"伏笔 {code} 已经被兑现，请确认是否需要重复兑现"
            })
    
    # 5. 校对上一章状态卡是否存在（warning）
    if chapter_num > 1:
        cursor = conn.execute("SELECT state_data FROM chapter_state WHERE project_id=? AND chapter_number=?", (project_id, chapter_num - 1))
        if not cursor.fetchone():
            validation_warnings.append({
                "type": "missing_state_card",
                "chapter": chapter_num - 1,
                "message": f"第{chapter_num-1}章没有状态卡，执笔可能缺乏数值基准",
                "action": f"建议质检通过后执行: python3 tools/db.py chapter_state {project_id} {chapter_num-1} --set '<JSON>'"
            })
    
    # 6. 校对章节是否存在
    cursor = conn.execute("SELECT id FROM chapters WHERE project_id=? AND chapter_number=?", (project_id, chapter_num))
    if not cursor.fetchone():
        validation_warnings.append({
            "type": "missing_chapter",
            "chapter": chapter_num,
            "message": f"第{chapter_num}章记录不存在，指令将创建但可能无法关联",
            "action": f"建议先执行: python3 tools/db.py add_chapter {project_id} {chapter_num} '<title>' 0 planned"
        })
    
    # 如果校对失败，返回错误
    if validation_issues:
        conn.close()
        print(json.dumps({
            "success": False,
            "error": "数据校对失败，指令未创建",
            "issues": validation_issues,
            "warnings": validation_warnings,
            "hint": "请修复上述问题后重新创建指令"
        }, ensure_ascii=False, indent=2))
        return
    
    # 校对通过，继续创建指令
    cursor = conn.cursor()
    conn.execute("""INSERT OR REPLACE INTO instructions 
        (project_id, chapter_number, objective, key_events, plots_to_resolve, plots_to_plant, emotion_tone, ending_hook, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (project_id, chapter_num, objective, key_events, plots_to_resolve, plots_to_plant, emotion_tone, ending_hook))
    
    cursor = conn.execute("SELECT id FROM instructions WHERE project_id=? AND chapter_number=?", (project_id, chapter_num))
    instruction_id = cursor.fetchone()[0]
    
    # 🔧 修复：关联 instruction 到 chapters 表
    cursor = conn.execute("SELECT id FROM chapters WHERE project_id=? AND chapter_number=?", (project_id, chapter_num))
    chapter_row = cursor.fetchone()
    if chapter_row:
        conn.execute("UPDATE chapters SET instruction_id=? WHERE id=?", (instruction_id, chapter_row[0]))
    chapter_id = chapter_row[0] if chapter_row else None
    
    characters_added = []
    if new_characters and chapter_id:
        try:
            for char in json.loads(new_characters):
                name = char.get('name')
                if not name: continue
                cursor.execute("SELECT id FROM characters WHERE project_id=? AND name=?", (project_id, name))
                if cursor.fetchone(): continue
                conn.execute("""INSERT INTO characters (project_id, name, alias, role, first_appearance, description, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'active')""",
                    (project_id, name, char.get('alias'), char.get('role','minor'), chapter_num, char.get('description','')))
                characters_added.append(name)
        except json.JSONDecodeError: pass
    
    for field, action in [('plots_to_resolve','resolved'), ('plots_to_plant','planted')]:
        val = locals().get(field)
        if val and chapter_id:
            try:
                for code in json.loads(val):
                    cursor = conn.execute("SELECT id FROM plot_holes WHERE project_id=? AND code=?", (project_id, code))
                    pr = cursor.fetchone()
                    if pr:
                        conn.execute("INSERT OR IGNORE INTO chapter_plots (project_id, chapter_id, plot_id, action) VALUES (?,?,?,?)",
                            (project_id, chapter_id, pr[0], action))
            except json.JSONDecodeError: pass
    
    conn.commit()
    conn.close()
    result = {"success": True, "chapter": chapter_num, "instruction_id": instruction_id, "validation": "passed"}
    if characters_added: result["characters_added"] = characters_added
    if validation_warnings: result["warnings"] = validation_warnings
    print(json.dumps(result, ensure_ascii=False))

# ============== 伏笔管理 ==============

def cmd_add_plot(args):
    """
    创建伏笔并自动关联到章节。
    用法: db.py add_plot <project> <code> <type> <title> <description> <planted_chapter> <planned_resolve_chapter>
    
    功能：
    1. 写入 plot_holes 表
    2. 如果 planted_chapter 对应的章节存在，自动写入 chapter_plots 关联表
    """
    if len(args) < 7:
        print("Usage: db.py add_plot <project> <code> <type> <title> <description> <planted_chapter> <planned_resolve_chapter>")
        return
    project_id, code, plot_type, title, description = args[0], args[1], args[2], args[3], args[4]
    planted_chapter = int(args[5])
    planned_resolve = int(args[6]) if len(args) > 6 and args[6] else None
    
    conn = get_connection()
    
    # 1. 写入 plot_holes 表
    conn.execute("""INSERT OR IGNORE INTO plot_holes (project_id, code, type, title, description, planted_chapter, planned_resolve_chapter, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'planted')""", (project_id, code, plot_type, title, description, planted_chapter, planned_resolve))
    
    # 2. 获取伏笔 ID
    cursor = conn.execute("SELECT id FROM plot_holes WHERE project_id=? AND code=?", (project_id, code))
    plot_row = cursor.fetchone()
    
    chapter_linked = False
    if plot_row:
        plot_id = plot_row[0]
        
        # 3. 自动关联到 chapter_plots（如果章节存在）
        cursor = conn.execute("SELECT id FROM chapters WHERE project_id=? AND chapter_number=?", (project_id, planted_chapter))
        chapter_row = cursor.fetchone()
        if chapter_row:
            conn.execute("""INSERT OR IGNORE INTO chapter_plots (project_id, chapter_id, plot_id, action, created_at)
                VALUES (?,?,?, 'planted', datetime('now','+8 hours'))""",
                (project_id, chapter_row[0], plot_id))
            chapter_linked = True
    
    conn.commit()
    conn.close()
    
    result = {"success": True, "code": code, "planted_chapter": planted_chapter}
    if chapter_linked:
        result["chapter_plots_linked"] = True
    else:
        result["chapter_plots_linked"] = False
        result["note"] = f"章节 {planted_chapter} 不存在，请稍后运行 sync_plots 或创建章节"
    
    print(json.dumps(result, ensure_ascii=False))

def cmd_resolve_plot(args):
    if len(args) < 3:
        print("Usage: db.py resolve_plot <project> <code> <resolved_chapter>")
        return
    project_id, code, resolved_chapter = args[0], args[1], int(args[2])
    conn = get_connection()
    conn.execute("UPDATE plot_holes SET status='resolved', resolved_chapter=? WHERE project_id=? AND code=?",
        (resolved_chapter, project_id, code))
    cursor = conn.execute("SELECT id FROM plot_holes WHERE project_id=? AND code=?", (project_id, code))
    pr = cursor.fetchone()
    if pr:
        cursor = conn.execute("SELECT id FROM chapters WHERE project_id=? AND chapter_number=?", (project_id, resolved_chapter))
        cr = cursor.fetchone()
        if cr:
            conn.execute("INSERT OR IGNORE INTO chapter_plots (project_id, chapter_id, plot_id, action) VALUES (?,?,?,?)",
                (project_id, cr[0], pr[0], 'resolved'))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "code": code}, ensure_ascii=False))

def cmd_pending_plots(args):
    if len(args) < 1:
        print("Usage: db.py pending_plots <project>")
        return
    conn = get_connection()
    cursor = conn.execute("""
        SELECT p.code, p.title, p.type, p.description, p.planted_chapter, p.planned_resolve_chapter, p.status, p.notes
        FROM plot_holes p WHERE p.project_id=? AND p.status NOT IN ('resolved','abandoned')
        ORDER BY CASE p.type WHEN 'long' THEN 1 WHEN 'mid' THEN 2 ELSE 3 END, p.planned_resolve_chapter""",
        (args[0],))
    plots = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    print(json.dumps(plots, ensure_ascii=False, indent=2))

def cmd_plots_by_chapter(args):
    """查询章节范围内的伏笔。用法: db.py plots_by_chapter <project> <start> <end>"""
    if len(args) < 3:
        print("Usage: db.py plots_by_chapter <project> <start> <end>")
        return
    project_id, start, end = args[0], int(args[1]), int(args[2])
    conn = get_connection()
    cursor = conn.execute("""
        SELECT code, title, type, description, planted_chapter, planned_resolve_chapter, resolved_chapter, status
        FROM plot_holes WHERE project_id=? AND (
            (planted_chapter BETWEEN ? AND ?) OR
            (planned_resolve_chapter BETWEEN ? AND ?) OR
            (resolved_chapter BETWEEN ? AND ?)
        ) ORDER BY planted_chapter""",
        (project_id, start, end, start, end, start, end))
    plots = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    print(json.dumps(plots, ensure_ascii=False, indent=2))

def cmd_sync_plots(args):
    if len(args) < 1:
        print("Usage: db.py sync_plots <project> [--dry-run]")
        return
    project_id = args[0]
    dry_run = '--dry-run' in args or '-n' in args
    conn = get_connection()
    chapter_map = {r['chapter_number']: r['id'] for r in conn.execute("SELECT chapter_number,id FROM chapters WHERE project_id=?", (project_id,)).fetchall()}
    plots = [row_to_dict(r) for r in conn.execute("SELECT id,code,planted_chapter,resolved_chapter FROM plot_holes WHERE project_id=?", (project_id,)).fetchall()]
    existing = {(r['chapter_id'], r['plot_id'], r['action']): True for r in conn.execute("SELECT chapter_id,plot_id,action FROM chapter_plots WHERE project_id=?", (project_id,)).fetchall()}
    missing_planted, missing_resolved = [], []
    for plot in plots:
        pid = plot['id']
        if plot['planted_chapter']:
            cid = chapter_map.get(plot['planted_chapter'])
            if cid and (cid, pid, 'planted') not in existing:
                missing_planted.append((cid, pid, plot['code']))
        if plot['resolved_chapter']:
            cid = chapter_map.get(plot['resolved_chapter'])
            if cid and (cid, pid, 'resolved') not in existing:
                missing_resolved.append((cid, pid, plot['code']))
    if not dry_run:
        for cid, pid, code in missing_planted:
            conn.execute("INSERT OR IGNORE INTO chapter_plots (project_id,chapter_id,plot_id,action,notes,created_at) VALUES (?,?,?,'planted',?,datetime('now','+8 hours'))",
                (project_id, cid, pid, f"伏笔埋设：{code}"))
        for cid, pid, code in missing_resolved:
            conn.execute("INSERT OR IGNORE INTO chapter_plots (project_id,chapter_id,plot_id,action,notes,created_at) VALUES (?,?,?,'resolved',?,datetime('now','+8 hours'))",
                (project_id, cid, pid, f"伏笔兑现：{code}"))
        conn.commit()
    conn.close()
    print(json.dumps({"missing_planted": len(missing_planted), "missing_resolved": len(missing_resolved), "dry_run": dry_run}, ensure_ascii=False, indent=2))

# ============== 质检管理 ==============

def cmd_verify_plots(args):
    """
    验证本章伏笔处理是否与指令一致。
    
    检测维度：
    1. 指令要求的伏笔是否在章节内容中出现（代码、标题、关键词）
    2. chapter_plots 表记录是否与指令一致
    3. plot_holes 表状态是否正确
    
    用法: db.py verify_plots <project> <chapter> [--verbose]
    """
    if len(args) < 2:
        print("Usage: db.py verify_plots <project> <chapter> [--verbose]")
        return
    project_id, chapter_num = args[0], int(args[1])
    verbose = '--verbose' in args
    conn = get_connection()
    
    # 1. 获取章节内容
    cursor = conn.execute("SELECT id, content FROM chapters WHERE project_id=? AND chapter_number=?", (project_id, chapter_num))
    chapter = row_to_dict(cursor.fetchone())
    if not chapter:
        print(json.dumps({"success": False, "error": f"章节 {chapter_num} 不存在"}, ensure_ascii=False))
        conn.close()
        return
    
    chapter_id = chapter['id']
    content = chapter.get('content', '')
    
    # 2. 获取指令
    cursor = conn.execute("SELECT plots_to_plant, plots_to_resolve FROM instructions WHERE project_id=? AND chapter_number=?", (project_id, chapter_num))
    instruction = row_to_dict(cursor.fetchone())
    if not instruction:
        print(json.dumps({"success": False, "error": f"章节 {chapter_num} 没有指令"}, ensure_ascii=False))
        conn.close()
        return
    
    try:
        plots_to_plant_raw = json.loads(instruction['plots_to_plant']) if instruction['plots_to_plant'] else []
        plots_to_resolve_raw = json.loads(instruction['plots_to_resolve']) if instruction['plots_to_resolve'] else []
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"指令伏笔参数不是有效 JSON: {e}"}, ensure_ascii=False))
        conn.close()
        return
    
    # 提取伏笔代码（支持 "P001:描述" 格式）
    def extract_code(item):
        if isinstance(item, str):
            return item.split(':')[0] if ':' in item else item
        return item
    
    plots_to_plant = [extract_code(p) for p in plots_to_plant_raw]
    plots_to_resolve = [extract_code(p) for p in plots_to_resolve_raw]
    
    # 3. 获取伏笔详情（用于关键词检测）
    all_codes = list(set(plots_to_plant + plots_to_resolve))
    plot_details = {}
    if all_codes:
        placeholders = ','.join('?' * len(all_codes))
        cursor = conn.execute(f"""SELECT code, title, description FROM plot_holes 
            WHERE project_id=? AND code IN ({placeholders})""", [project_id] + all_codes)
        for row in cursor.fetchall():
            plot_details[row[0]] = {"title": row[1], "description": row[2]}
    
    # 4. 获取 chapter_plots 记录
    cursor = conn.execute("SELECT action, p.code, p.title FROM chapter_plots cp JOIN plot_holes p ON cp.plot_id = p.id WHERE cp.chapter_id=?", (chapter_id,))
    existing = cursor.fetchall()
    recorded_planted = [r[1] for r in existing if r[0] == 'planted']
    recorded_resolved = [r[1] for r in existing if r[0] == 'resolved']
    
    # 5. 内容检测函数（多维度）
    def check_plot_in_content(code, content, details):
        """
        检测伏笔是否在内容中出现：
        1. 伏笔代码（如 P001）
        2. 伏笔标题关键词（提取核心词组）
        3. 描述中的关键实体名（人名、地名、关键短语）
        4. 扩展关键词（常见同义词、相关词）
        """
        import re
        matches = []
        
        # 检查代码
        if code in content:
            matches.append(f"代码:{code}")
        
        # 检查标题关键词
        if details and 'title' in details:
            title = details['title']
            # 提取2-4字的中文词组，但优先匹配有意义的组合
            title_keywords = re.findall(r'[\u4e00-\u9fa5]{2,4}', title)
            for kw in title_keywords:
                if kw in content:
                    matches.append(f"标题关键词:{kw}")
        
        # 检查描述中的关键实体
        if details and 'description' in details:
            desc = details['description']
            # 提取2-6字的中文词组（人名、地名、关键短语）
            entities = re.findall(r'[\u4e00-\u9fa5]{2,6}', desc)
            # 过滤掉常见的无意义词
            stopwords = {'这是', '那是', '就是', '可以', '没有', '不是', '什么', '这个', '那个', '已经', '还会', '如果', '因为', '所以', '但是', '而且', '或者', '以及', '对于', '通过', '进行', '可能', '应该', '需要', '必须', '一定', '一些', '这些', '那些', '他们的', '我们的', '你们的', '自己的', '其他', '其中', '以下', '以上', '之后', '之前', '当中', '里面', '外面', '这里', '那里', '现在', '当时', '一个', '每个', '各个', '某种', '某些', '任何', '所有', '全部', '部分', '大部分', '小部分', '很多', '多少', '几个', '怎样', '如何', '为何', '哪里', '何时', '多久', '多远', '多长', '多大', '多高', '多深', '多厚', '多重', '多快', '多慢', '多早', '多晚', '多好', '多坏', '多对', '多错', '多真', '多假', '多美', '多丑', '多善', '多恶', '多优', '多劣', '多强', '多弱', '多高', '多低', '多大', '多小', '多长', '多短', '多宽', '多窄', '多厚', '多薄', '多重', '多轻', '多快', '多慢', '多早', '多晚', '多新', '多旧', '多贵', '多便宜', '多重要', '多严重', '多紧急', '多困难', '多简单', '多复杂', '多明显', '多隐晦', '多清楚', '多模糊', '多准确', '多错误', '多完整', '多残缺', '多丰富', '多贫乏', '多精彩', '多无聊', '多有趣', '多无趣', '多有意义', '多无意义', '多有价值', '多无价值', '多有用的', '多无用的', '多有效的', '多无效的', '多有利的', '多不利的', '多有益的', '多有害的', '多积极的', '多消极的', '多正面的', '多负面的', '多好的', '多坏的', '多对的', '多错的', '多真的', '多假的', '多美的', '多丑的', '多善的', '多恶的', '多优的', '多劣的', '多强的', '多弱的', '多高的', '多低的', '多大的', '多小的', '多长的', '多短的', '多宽的', '多窄的', '多厚的', '多薄的', '多的', '少的', '大的', '小的', '高的', '低的', '长的', '短的', '宽的', '窄的', '厚的', '薄的', '重的', '轻的', '快的', '慢的', '早的', '晚的', '新的', '旧的', '贵的', '便宜的', '重要的', '严重的', '紧急的', '困难的', '简单的', '复杂的', '明显的', '隐晦的', '清楚的', '模糊的', '准确的', '错误的', '完整的', '残缺的', '丰富的', '贫乏的', '精彩的', '无聊的', '有趣的', '无趣的', '有意义的', '无意义的', '有价值的', '无价值的', '有用的', '无用的', '有效的', '无效的', '有利的', '不利的', '有益的', '有害的', '积极的', '消极的', '正面的', '负面的', '表象', '真相', '底牌'}
            filtered_entities = [e for e in entities if e not in stopwords and len(e) >= 2]
            # 去重并保留前10个
            seen = set()
            unique_entities = []
            for ent in filtered_entities:
                if ent not in seen:
                    seen.add(ent)
                    unique_entities.append(ent)
            for ent in unique_entities[:10]:
                if ent in content:
                    matches.append(f"实体:{ent}")
        
        return matches
    
    # 6. 执行检测
    planted_in_content = []
    missing_planted = []
    planted_details = {}
    for code in plots_to_plant:
        matches = check_plot_in_content(code, content, plot_details.get(code))
        if matches:
            planted_in_content.append(code)
            planted_details[code] = matches
        else:
            missing_planted.append(code)
    
    resolved_in_content = []
    missing_resolved = []
    resolved_details = {}
    for code in plots_to_resolve:
        matches = check_plot_in_content(code, content, plot_details.get(code))
        if matches:
            resolved_in_content.append(code)
            resolved_details[code] = matches
        else:
            missing_resolved.append(code)
    
    # 7. 计算伏笔偏差评分
    plot_deviation = {
        "missing_plant_count": len(missing_planted),
        "missing_resolve_count": len(missing_resolved),
        "extra_plant_count": len(set(recorded_planted) - set(plots_to_plant)),
        "extra_resolve_count": len(set(recorded_resolved) - set(plots_to_resolve)),
        "total_required": len(plots_to_plant) + len(plots_to_resolve),
        "total_found": len(planted_in_content) + len(resolved_in_content)
    }

    # 计算伏笔完成率
    if plot_deviation["total_required"] > 0:
        plot_deviation["completion_rate"] = plot_deviation["total_found"] / plot_deviation["total_required"]
    else:
        plot_deviation["completion_rate"] = 1.0  # 没有伏笔要求视为完成

    # 计算扣分
    plot_score_deduction = 0
    if plot_deviation["missing_resolve_count"] > 0:
        # 漏兑现是严重问题，每个扣 20 分
        plot_score_deduction += plot_deviation["missing_resolve_count"] * 20
    if plot_deviation["missing_plant_count"] > 0:
        # 漏埋是中等问题，每个扣 10 分
        plot_score_deduction += plot_deviation["missing_plant_count"] * 10
    if plot_deviation["extra_plant_count"] > 0 or plot_deviation["extra_resolve_count"] > 0:
        # 额外伏笔记录，扣 5 分
        plot_score_deduction += 5

    # 8. 构建结果
    result = {
        "success": True,
        "chapter": chapter_num,
        "instruction": {
            "plots_to_plant": plots_to_plant,
            "plots_to_resolve": plots_to_resolve
        },
        "content_check": {
            "planted_in_content": planted_in_content,
            "missing_planted": missing_planted,
            "resolved_in_content": resolved_in_content,
            "missing_resolved": missing_resolved
        },
        "chapter_plots_check": {
            "recorded_planted": recorded_planted,
            "recorded_resolved": recorded_resolved
        },
        "plot_deviation": plot_deviation,
        "plot_score_deduction": plot_score_deduction,
        "issues": []
    }
    
    # 8. 添加详细信息（verbose 模式）
    if verbose:
        result["content_check"]["planted_details"] = planted_details
        result["content_check"]["resolved_details"] = resolved_details
    
    # 9. 检测问题
    if missing_planted:
        result["issues"].append(f"指令要求埋设但内容中未找到: {missing_planted}")
    if missing_resolved:
        result["issues"].append(f"指令要求兑现但内容中未找到: {missing_resolved}")
    if set(plots_to_plant) != set(recorded_planted):
        missing_in_db = set(plots_to_plant) - set(recorded_planted)
        extra_in_db = set(recorded_planted) - set(plots_to_plant)
        if missing_in_db:
            result["issues"].append(f"chapter_plots 缺少埋设记录: {list(missing_in_db)}")
        if extra_in_db:
            result["issues"].append(f"chapter_plots 多余埋设记录: {list(extra_in_db)}")
    if set(plots_to_resolve) != set(recorded_resolved):
        missing_in_db = set(plots_to_resolve) - set(recorded_resolved)
        extra_in_db = set(recorded_resolved) - set(plots_to_resolve)
        if missing_in_db:
            result["issues"].append(f"chapter_plots 缺少兑现记录: {list(missing_in_db)}")
        if extra_in_db:
            result["issues"].append(f"chapter_plots 多余兑现记录: {list(extra_in_db)}")
    
    result["valid"] = len(result["issues"]) == 0
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_add_review(args):
    if len(args) < 11:
        print("Usage: db.py add_review <project> <chapter> <score> <pass> <summary> <setting_score> <logic_score> <poison_score> <text_score> <pacing_score> [issues] [suggestions]")
        return
    project_id = args[0]
    chapter_number = int(args[1])
    # 支持 true/false 字符串或 1/0 数字
    pass_arg = args[3].lower() if isinstance(args[3], str) else args[3]
    if pass_arg in ('true', '1'):
        pass_flag = 1
    elif pass_arg in ('false', '0'):
        pass_flag = 0
    else:
        pass_flag = int(args[3])
    score = int(args[2])
    summary = args[4]
    setting_score, logic_score, poison_score, text_score, pacing_score = int(args[5]), int(args[6]), int(args[7]), int(args[8]), int(args[9])
    issues = args[10] if len(args) > 10 else '[]'
    suggestions = args[11] if len(args) > 11 else '[]'
    if score == 0: score = setting_score + logic_score + poison_score + text_score + pacing_score

    # 🔒 强制: pass 必须与分数一致，≥90 才是 true
    auto_pass = 1 if score >= 90 else 0
    if pass_flag != auto_pass:
        print(json.dumps({
            "success": False,
            "error": "pass 参数与分数不匹配",
            "details": f"分数 {score} 分，{ '>=90 应传 1 (通过)' if auto_pass == 1 else '<90 应传 0 (退回)' }，实际传了 {pass_flag}"
        }, ensure_ascii=False))
        return
    # 支持文件路径
    for i, (var, name) in enumerate([(summary,'summary'),(issues,'issues'),(suggestions,'suggestions')]):
        if len(var) < 255 and Path(var).exists():
            with open(var, 'r', encoding='utf-8') as f:
                if name == 'summary': summary = f.read()
                elif name == 'issues': issues = f.read()
                else: suggestions = f.read()
    conn = get_connection()
    cursor = conn.execute("SELECT id FROM chapters WHERE project_id=? AND chapter_number=?", (project_id, chapter_number))
    cr = cursor.fetchone()
    if not cr:
        print(json.dumps({"error": "章节不存在"}, ensure_ascii=False)); conn.close(); return
    
    # 插入质检报告
    cursor = conn.execute("""INSERT OR REPLACE INTO reviews (project_id, chapter_id, pass, score, setting_score, logic_score, poison_score, text_score, pacing_score, issues, suggestions, summary)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (project_id, cr[0], pass_flag, score, setting_score, logic_score, poison_score, text_score, pacing_score, issues, suggestions, summary))
    review_id = cursor.lastrowid
    
    # 如果质检通过，更新最新版本的 review_id
    if pass_flag == 1:
        conn.execute("""
            UPDATE chapter_versions 
            SET review_id = ? 
            WHERE project_id = ? AND chapter = ? AND version = (
                SELECT MAX(version) FROM chapter_versions WHERE project_id = ? AND chapter = ?
            )
        """, (review_id, project_id, chapter_number, project_id, chapter_number))
    
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "chapter": chapter_number, "score": score, "pass": bool(pass_flag), "review_id": review_id}, ensure_ascii=False))

def cmd_reviews(args):
    if len(args) < 1:
        print("Usage: db.py reviews <project>")
        return
    conn = get_connection()
    cursor = conn.execute("""SELECT r.*, c.chapter_number, c.title FROM reviews r JOIN chapters c ON r.chapter_id=c.id
        WHERE r.project_id=? ORDER BY c.chapter_number""", (args[0],))
    reviews = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    print(json.dumps(reviews, ensure_ascii=False, indent=2))

# ============== 统计查询 ==============

def cmd_stats(args):
    if len(args) < 1:
        print("Usage: db.py stats <project>")
        return
    project_id = args[0]
    conn = get_connection()
    ch = row_to_dict(conn.execute("""SELECT COUNT(*) as total_chapters,
        SUM(CASE WHEN status='published' THEN 1 ELSE 0 END) as published_chapters,
        SUM(CASE WHEN status='drafting' THEN 1 ELSE 0 END) as drafting_chapters,
        SUM(CASE WHEN status='review' THEN 1 ELSE 0 END) as review_chapters,
        SUM(CASE WHEN status='planned' THEN 1 ELSE 0 END) as planned_chapters,
        SUM(word_count) as total_words FROM chapters WHERE project_id=?""", (project_id,)).fetchone())
    pl = row_to_dict(conn.execute("""SELECT COUNT(*) as total_plots,
        SUM(CASE WHEN type='long' THEN 1 ELSE 0 END) as long_plots,
        SUM(CASE WHEN type='mid' THEN 1 ELSE 0 END) as mid_plots,
        SUM(CASE WHEN type='short' THEN 1 ELSE 0 END) as short_plots,
        SUM(CASE WHEN status='planted' THEN 1 ELSE 0 END) as planted,
        SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) as resolved
        FROM plot_holes WHERE project_id=?""", (project_id,)).fetchone())
    rv = row_to_dict(conn.execute("""SELECT COUNT(*) as total_reviews, AVG(score) as avg_score,
        SUM(CASE WHEN pass=1 THEN 1 ELSE 0 END) as passed FROM reviews WHERE project_id=?""", (project_id,)).fetchone())
    conn.close()
    print(json.dumps({"project_id": project_id, "chapters": ch, "plots": pl, "reviews": rv}, ensure_ascii=False, indent=2))

# ============== 任务管理 ==============

def cmd_task_start(args):
    if len(args) < 4:
        print("Usage: db.py task_start <project> <task_type> <chapter> <agent>")
        return
    conn = get_connection()
    cursor = conn.execute("""INSERT INTO task_status (project_id, task_type, chapter_number, agent_id, status, started_at)
        VALUES (?,?,?,?, 'running', datetime('now','+8 hours'))""", (args[0], args[1], int(args[2]), args[3]))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "task_id": task_id}, ensure_ascii=False))

def cmd_task_complete(args):
    if len(args) < 1:
        print("Usage: db.py task_complete <task_id> [success]")
        return
    task_id = int(args[0])
    success = args[1] if len(args) > 1 else 'true'
    status = 'completed' if success == 'true' else 'failed'
    conn = get_connection()
    conn.execute("UPDATE task_status SET status=?, completed_at=datetime('now','+8 hours') WHERE id=?", (status, task_id))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "task_id": task_id}, ensure_ascii=False))

def cmd_task_list(args):
    """列出任务"""
    if len(args) < 1:
        print("Usage: db.py task_list <project> [status] [limit]")
        return
    project_id = args[0]
    status = args[1] if len(args) > 1 and args[1] != 'all' else None
    limit = int(args[2]) if len(args) > 2 else 20
    conn = get_connection()
    if status:
        cursor = conn.execute("""SELECT * FROM task_status WHERE project_id=? AND status=?
            ORDER BY created_at DESC LIMIT ?""", (project_id, status, limit))
    else:
        cursor = conn.execute("""SELECT * FROM task_status WHERE project_id=?
            ORDER BY created_at DESC LIMIT ?""", (project_id, limit))
    tasks = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    print(json.dumps(tasks, ensure_ascii=False, indent=2))

def cmd_task_reset(args):
    """重置任务回 pending 以重试"""
    if len(args) < 1:
        print("Usage: db.py task_reset <task_id>")
        return
    task_id = int(args[0])
    conn = get_connection()
    conn.execute("""UPDATE task_status SET status='pending', retry_count=retry_count+1,
        error_message=NULL, started_at=NULL, completed_at=NULL WHERE id=?""", (task_id,))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "task_id": task_id, "action": "reset_to_pending"}, ensure_ascii=False))

def cmd_task_timeout(args):
    if len(args) < 2:
        print("Usage: db.py task_timeout <project> <timeout_minutes>")
        return
    project_id, timeout_minutes = args[0], int(args[1])
    conn = get_connection()
    cursor = conn.execute("SELECT id, task_type, chapter_number, agent_id, started_at FROM task_status WHERE project_id=? AND status='running'", (project_id,))
    tasks = []
    for row in cursor.fetchall():
        started_at = datetime.fromisoformat(row['started_at'])
        elapsed = (datetime.now() - started_at).total_seconds() / 60
        if elapsed > timeout_minutes:
            tasks.append({"task_id": row['id'], "task_type": row['task_type'], "chapter": row['chapter_number'],
                "agent": row['agent_id'], "elapsed_minutes": round(elapsed, 1)})
    conn.close()
    print(json.dumps({"timeout_tasks": tasks, "count": len(tasks)}, ensure_ascii=False, indent=2))

def cmd_check_chapter(args):
    """
    检查章节的常见问题（不依赖 LLM 的理解能力）。
    用法: db.py check_chapter <project> <chapter>
    
    检查项：
    1. 字数统计（实际字数 vs 目标字数）
    2. 状态卡对比（是否有矛盾）
    3. 指令对齐（关键事件是否包含）
    4. 伏笔触发对象（是否正确）
    """
    if len(args) < 2:
        print("Usage: db.py check_chapter <project> <chapter>")
        return
    
    project_id = args[0]
    chapter_num = int(args[1])
    
    # 导入检查工具
    import sys
    import os
    tools_dir = Path(__file__).parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    
    from check_chapter import check_chapter
    
    result = check_chapter(project_id, chapter_num)
    print(json.dumps(result, ensure_ascii=False, indent=2))

# ============== 健康检查 ==============

def cmd_health_check(args):
    project_id = args[0] if args else None
    conn = get_connection()
    issues = []
    try: conn.execute("SELECT 1")
    except Exception as e: issues.append({"level": "error", "type": "database", "message": f"数据库连接失败: {e}"})
    cursor = conn.execute("SELECT COUNT(*) as count FROM projects")
    if cursor.fetchone()['count'] == 0:
        issues.append({"level": "blocking", "type": "projects", "message": "没有项目"})
    if project_id:
        if not conn.execute("SELECT 1 FROM projects WHERE project_id=?", (project_id,)).fetchone():
            issues.append({"level": "error", "type": "project_not_found", "message": f"项目 {project_id} 不存在"})
        oc = conn.execute("""SELECT COUNT(*) as count FROM chapters c LEFT JOIN projects p ON c.project_id=p.project_id
            WHERE c.project_id=? AND p.project_id IS NULL""", (project_id,)).fetchone()['count']
        if oc > 0:
            issues.append({"level": "warning", "type": "orphan_chapters", "message": f"发现 {oc} 个孤立章节"})
    conn.close()
    if issues:
        print(json.dumps({"status": "issues_found", "issues": issues}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"status": "healthy"}, ensure_ascii=False))

def cmd_validate_data(args):
    """
    校对项目数据一致性（规划前/后执行）。
    用法: db.py validate_data <project> [chapter]
    
    检查维度：
    1. 指令引用的伏笔是否存在
    2. 指令引用的角色是否存在
    3. 上一章状态卡是否存在
    4. 待兑现伏笔是否已在之前章节埋设
    5. 角色状态是否合理（死亡角色是否标记）
    
    返回：
    - valid: true/false
    - issues: 问题列表
    - warnings: 警告列表
    """
    if len(args) < 1:
        print("Usage: db.py validate_data <project> [chapter]")
        return
    project_id = args[0]
    chapter_num = int(args[1]) if len(args) > 1 else None
    
    conn = get_connection()
    issues = []
    warnings = []
    
    # 1. 检查指定章节或所有待规划章节
    if chapter_num:
        chapters_to_check = [chapter_num]
    else:
        # 检查所有 planned 状态的章节
        cursor = conn.execute("SELECT chapter_number FROM chapters WHERE project_id=? AND status='planned'", (project_id,))
        chapters_to_check = [row[0] for row in cursor.fetchall()]
        if not chapters_to_check:
            # 如果没有 planned 章节，检查下一章
            cursor = conn.execute("SELECT MAX(chapter_number) FROM chapters WHERE project_id=?", (project_id,))
            max_chapter = cursor.fetchone()[0] or 0
            chapters_to_check = [max_chapter + 1]
    
    for chapter in chapters_to_check:
        # 2. 检查指令是否存在
        cursor = conn.execute("SELECT * FROM instructions WHERE project_id=? AND chapter_number=?", (project_id, chapter))
        instruction = row_to_dict(cursor.fetchone())
        
        if not instruction:
            warnings.append({
                "chapter": chapter,
                "type": "no_instruction",
                "message": f"第{chapter}章没有指令"
            })
            continue
        
        # 3. 检查伏笔引用
        try:
            plots_to_plant = json.loads(instruction['plots_to_plant']) if instruction['plots_to_plant'] else []
            plots_to_resolve = json.loads(instruction['plots_to_resolve']) if instruction['plots_to_resolve'] else []
        except json.JSONDecodeError:
            issues.append({
                "chapter": chapter,
                "type": "invalid_json",
                "message": "指令的伏笔参数不是有效 JSON"
            })
            continue
        
        # 提取伏笔代码（支持 "P001:描述" 格式）
        def extract_code(item):
            if isinstance(item, str):
                return item.split(':')[0] if ':' in item else item
            return item
        
        plots_to_plant_codes = [extract_code(p) for p in plots_to_plant]
        plots_to_resolve_codes = [extract_code(p) for p in plots_to_resolve]
        
        # 检查 plots_to_plant 中的伏笔是否存在
        for code in plots_to_plant_codes:
            cursor = conn.execute("SELECT id FROM plot_holes WHERE project_id=? AND code=?", (project_id, code))
            if not cursor.fetchone():
                issues.append({
                    "chapter": chapter,
                    "type": "missing_plot",
                    "message": f"指令引用的伏笔 {code} 不存在（plots_to_plant）",
                    "action": f"先执行: python3 tools/db.py add_plot {project_id} {code} <type> '<title>' '<description>' {chapter} <resolve_chapter>"
                })
        
        # 检查 plots_to_resolve 中的伏笔是否存在且已埋设
        for code in plots_to_resolve_codes:
            cursor = conn.execute("SELECT id, planted_chapter, status FROM plot_holes WHERE project_id=? AND code=?", (project_id, code))
            plot = cursor.fetchone()
            if not plot:
                issues.append({
                    "chapter": chapter,
                    "type": "missing_plot",
                    "message": f"指令引用的伏笔 {code} 不存在（plots_to_resolve）"
                })
            elif plot['planted_chapter'] > chapter:
                issues.append({
                    "chapter": chapter,
                    "type": "plot_not_planted",
                    "message": f"伏笔 {code} 将在第{plot['planted_chapter']}章埋设，无法在第{chapter}章兑现"
                })
        
        # 4. 检查新角色引用
        try:
            new_characters = json.loads(instruction.get('new_characters', '[]') or '[]')
        except json.JSONDecodeError:
            new_characters = []
        
        for char in new_characters:
            if isinstance(char, dict) and 'name' in char:
                cursor = conn.execute("SELECT id FROM characters WHERE project_id=? AND name=?", (project_id, char['name']))
                # 新角色可以不存在，这里只是检查格式
                if not cursor.fetchone():
                    warnings.append({
                        "chapter": chapter,
                        "type": "new_character",
                        "message": f"指令将创建新角色: {char['name']}"
                    })
        
        # 5. 检查上一章状态卡
        if chapter > 1:
            cursor = conn.execute("SELECT state_data FROM chapter_state WHERE project_id=? AND chapter_number=?", (project_id, chapter - 1))
            if not cursor.fetchone():
                warnings.append({
                    "chapter": chapter,
                    "type": "missing_state_card",
                    "message": f"第{chapter-1}章没有状态卡，执笔可能缺乏数值基准"
                })
    
    # 6. 全局检查：死亡角色状态
    cursor = conn.execute("SELECT name, status, first_appearance FROM characters WHERE project_id=? AND status='deceased'", (project_id,))
    deceased_chars = cursor.fetchall()
    # 这里可以扩展检查章节内容是否引用了死亡角色
    
    conn.close()
    
    result = {
        "valid": len(issues) == 0,
        "chapters_checked": chapters_to_check,
        "issues": issues,
        "warnings": warnings,
        "summary": f"检查了 {len(chapters_to_check)} 个章节，发现 {len(issues)} 个错误，{len(warnings)} 个警告"
    }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))

# ============== 数值状态管理 ==============

def cmd_chapter_state(args):
    """
    查询/写入章节结束数值状态。
    用法: db.py chapter_state <project> <chapter>           → 查询状态
          db.py chapter_state <project> <chapter> --set '<JSON>' → 写入状态
    """
    if len(args) < 2:
        print("Usage: db.py chapter_state <project> <chapter> [--set '<JSON>']")
        return
    project_id, chapter_num = args[0], int(args[1])
    conn = get_connection()

    # 写模式
    set_idx = None
    for i, a in enumerate(args):
        if a == '--set' and i + 1 < len(args):
            set_idx = i; break
    if set_idx is not None:
        state_data = args[set_idx + 1]
        summary = args[set_idx + 2] if set_idx + 2 < len(args) else None
        try:
            json.loads(state_data)  # 验证 JSON 格式
        except json.JSONDecodeError:
            print(json.dumps({"success": False, "error": "state_data 不是有效 JSON"}, ensure_ascii=False))
            conn.close(); return
        
        # 获取旧状态（用于比较变更）
        old_cursor = conn.execute(
            "SELECT state_data FROM chapter_state WHERE project_id=? AND chapter_number=?",
            (project_id, chapter_num))
        old_row = old_cursor.fetchone()
        old_state = json.loads(old_row[0]) if old_row else {}
        
        # 解析新状态
        new_state = json.loads(state_data)
        
        # 计算变更字段
        changed_fields = []
        for key in set(list(old_state.keys()) + list(new_state.keys())):
            old_val = old_state.get(key)
            new_val = new_state.get(key)
            if old_val != new_val:
                changed_fields.append({
                    "field": key,
                    "old": old_val,
                    "new": new_val
                })
        
        # 写入 chapter_state（当前状态）
        conn.execute("""INSERT OR REPLACE INTO chapter_state (project_id, chapter_number, state_data, created_at, summary)
            VALUES (?,?,?, datetime('now','+8 hours'), ?)""",
            (project_id, chapter_num, state_data, summary))
        
        # 写入 state_history（历史记录）
        conn.execute("""INSERT INTO state_history (project_id, chapter, state_json, changed_fields, reason)
            VALUES (?,?,?,?,?)""",
            (project_id, chapter_num, state_data, json.dumps(changed_fields, ensure_ascii=False), summary))
        
        conn.commit()
        conn.close()
        print(json.dumps({"success": True, "chapter": chapter_num, "changed_fields": len(changed_fields)}, ensure_ascii=False))
        return

    # 读模式
    cursor = conn.execute("SELECT chapter_number, state_data, summary FROM chapter_state WHERE project_id=? AND chapter_number=?",
        (project_id, chapter_num))
    row = row_to_dict(cursor.fetchone())
    conn.close()
    if row:
        result = {"chapter": row['chapter_number'], "summary": row['summary']}
        try:
            result['state'] = json.loads(row['state_data'])
        except:
            result['state'] = row['state_data']
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"message": f"没有第{chapter_num}章的数值状态"}, ensure_ascii=False))


def cmd_validate_state(args):
    """
    校验章节状态卡的数值一致性。

    用法: db.py validate_state <project> <chapter> '<current_state_json>'
          db.py validate_state <project> <chapter> --from-content

    校验规则：
    1. 继承字段：上一章有、本章没提到的 → 必须继承（值不变）
    2. 变动字段：本章明确提到变动的 → 校验等式 前章值 + 变动 = 本章值
    3. 新增字段：本章新增的 → 直接记录
    4. 删除字段：上一章有、本章明确结束的 → 可删除（需说明原因）

    返回：
    - valid: true/false
    - inherited: 继承字段列表
    - changed: 变动字段列表（含校验结果）
    - added: 新增字段列表
    - removed: 删除字段列表
    - issues: 问题列表
    """
    if len(args) < 3:
        print(json.dumps({
            "error": "用法: db.py validate_state <project> <chapter> '<current_state_json>'",
            "example": "db.py validate_state novel_001 5 '{\"assets\":{\"credits\":{\"value\":300}}}'"
        }, ensure_ascii=False))
        return

    project_id = args[0]
    chapter_num = int(args[1])
    current_state_str = args[2]

    # 解析当前状态
    try:
        current_state = json.loads(current_state_str)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"JSON 解析失败: {e}"}, ensure_ascii=False))
        return

    conn = get_connection()

    # 获取上一章状态
    if chapter_num <= 1:
        conn.close()
        print(json.dumps({
            "valid": True,
            "message": "第1章无需校验（无上一章状态）",
            "current_state": current_state
        }, ensure_ascii=False, indent=2))
        return

    cursor = conn.execute(
        "SELECT state_data FROM chapter_state WHERE project_id=? AND chapter_number=?",
        (project_id, chapter_num - 1)
    )
    prev_row = cursor.fetchone()
    conn.close()

    if not prev_row or not prev_row['state_data']:
        print(json.dumps({
            "valid": True,
            "message": f"第{chapter_num-1}章无状态卡，跳过校验",
            "current_state": current_state
        }, ensure_ascii=False, indent=2))
        return

    try:
        prev_state = json.loads(prev_row['state_data'])
    except json.JSONDecodeError:
        print(json.dumps({
            "valid": False,
            "error": f"第{chapter_num-1}章状态卡 JSON 格式错误"
        }, ensure_ascii=False))
        return

    # 执行校验
    result = {
        "valid": True,
        "inherited": [],
        "changed": [],
        "added": [],
        "removed": [],
        "issues": []
    }

    def compare_values(path, prev_val, curr_val):
        """递归比较值"""
        if isinstance(prev_val, dict) and isinstance(curr_val, dict):
            # 检查变动
            if "value" in prev_val and "value" in curr_val:
                # 这是数值字段
                prev_value = prev_val.get("value")
                curr_value = curr_val.get("value")
                change = curr_val.get("change", 0)

                if prev_value is None or curr_value is None:
                    return  # 无法比较

                # 校验等式：前章值 + 变动 = 本章值
                expected = prev_value + change
                if curr_value != expected:
                    result["issues"].append({
                        "path": path,
                        "type": "value_mismatch",
                        "prev_value": prev_value,
                        "change": change,
                        "curr_value": curr_value,
                        "expected": expected,
                        "message": f"{path}: {prev_value} + ({change}) = {expected}，但章节显示 {curr_value}"
                    })
                    result["valid"] = False
                else:
                    result["changed"].append({
                        "path": path,
                        "prev_value": prev_value,
                        "change": change,
                        "curr_value": curr_value,
                        "valid": True
                    })
            else:
                # 递归比较字典
                all_keys = set(prev_val.keys()) | set(curr_val.keys())
                for key in all_keys:
                    new_path = f"{path}.{key}" if path else key
                    if key not in curr_val:
                        # 字段被删除
                        result["removed"].append({
                            "path": new_path,
                            "prev_value": prev_val[key]
                        })
                    elif key not in prev_val:
                        # 新增字段
                        result["added"].append({
                            "path": new_path,
                            "curr_value": curr_val[key]
                        })
                    else:
                        compare_values(new_path, prev_val[key], curr_val[key])
        elif isinstance(prev_val, dict) and "value" in prev_val:
            # 上一章是数值字段，本章变成普通值
            prev_value = prev_val.get("value")
            if prev_value != curr_val:
                result["issues"].append({
                    "path": path,
                    "type": "format_changed",
                    "prev_value": prev_value,
                    "curr_value": curr_val,
                    "message": f"{path}: 格式从数值字段变为普通值，且值从 {prev_value} 变为 {curr_val}"
                })
                result["valid"] = False
        else:
            # 普通值比较
            if prev_val != curr_val:
                result["changed"].append({
                    "path": path,
                    "prev_value": prev_val,
                    "curr_value": curr_val,
                    "valid": False,
                    "message": f"{path}: 值从 {prev_val} 变为 {curr_val}，但没有 change 字段"
                })

    # 比较主要桶
    buckets = ["assets", "character_states", "hidden_info"]

    for bucket in buckets:
        prev_bucket = prev_state.get(bucket, {})
        curr_bucket = current_state.get(bucket, {})

        if not prev_bucket and not curr_bucket:
            continue

        all_keys = set(prev_bucket.keys()) | set(curr_bucket.keys())

        for key in all_keys:
            path = f"{bucket}.{key}"

            if key not in curr_bucket:
                # 字段被删除
                result["removed"].append({
                    "path": path,
                    "prev_value": prev_bucket[key]
                })
            elif key not in prev_bucket:
                # 新增字段
                result["added"].append({
                    "path": path,
                    "curr_value": curr_bucket[key]
                })
            else:
                compare_values(path, prev_bucket[key], curr_bucket[key])

    # 特殊处理：active_plots 和 resolved_plots 是列表
    for list_bucket in ["active_plots", "resolved_plots"]:
        prev_list = prev_state.get(list_bucket, [])
        curr_list = current_state.get(list_bucket, [])

        if not isinstance(prev_list, list):
            prev_list = []
        if not isinstance(curr_list, list):
            curr_list = []

        prev_set = set(prev_list)
        curr_set = set(curr_list)

        # 新增的伏笔
        for item in curr_set - prev_set:
            result["added"].append({
                "path": list_bucket,
                "curr_value": item
            })

        # 删除的伏笔
        for item in prev_set - curr_set:
            result["removed"].append({
                "path": list_bucket,
                "prev_value": item
            })

    # 添加摘要
    result["summary"] = f"校验完成：继承 {len(result['inherited'])} 项，变动 {len(result['changed'])} 项，新增 {len(result['added'])} 项，删除 {len(result['removed'])} 项，问题 {len(result['issues'])} 项"

    print(json.dumps(result, ensure_ascii=False, indent=2))


# ============== 市场报告 ==============

def cmd_add_market_report(args):
    if len(args) < 7:
        print("Usage: db.py add_market_report <date> <summary> <hot_genres> <trending_tags> <opportunities> <risks> <advice>")
        return
    conn = get_connection()
    conn.execute("""INSERT INTO market_reports (report_date, summary, hot_genres, trending_tags, opportunities, risks, actionable_advice)
        VALUES (?,?,?,?,?,?,?)""", (args[0], args[1], args[2], args[3], args[4], args[5], args[6]))
    conn.commit()
    conn.close()
    print(json.dumps({"success": True}, ensure_ascii=False))

def cmd_market_reports(args):
    count = int(args[0]) if args else 5
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM market_reports ORDER BY report_date DESC LIMIT ?", (count,))
    reports = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    print(json.dumps(reports, ensure_ascii=False, indent=2))

# ============== 问题模式管理 ==============

def cmd_anti_patterns(args):
    """
    查询问题模式库。
    用法: db.py anti_patterns [category] [--severity high] [--all]

    参数:
      category: 问题类别 (ai_trace, logic, setting, poison, pacing)
      --severity <level>: 按严重程度过滤 (critical, high, medium, low)
      --all: 显示所有字段（包括 alternatives, check_rules, examples）
      --enabled: 只显示启用的模式
      --disabled: 只显示禁用的模式
    """
    conn = get_connection()

    # 解析参数
    category = None
    severity = None
    show_all = '--all' in args
    enabled_filter = None
    if '--enabled' in args:
        enabled_filter = 1
    elif '--disabled' in args:
        enabled_filter = 0

    # 过滤非 flag 参数
    filter_args = [a for a in args if not a.startswith('--')]
    if filter_args and filter_args[0] not in ('ai_trace', 'logic', 'setting', 'poison', 'pacing'):
        # 检查是否是 severity
        if filter_args[0] in ('critical', 'high', 'medium', 'low'):
            severity = filter_args[0]
        else:
            print(json.dumps({"error": f"未知类别: {filter_args[0]}", "valid_categories": ["ai_trace", "logic", "setting", "poison", "pacing"]}, ensure_ascii=False))
            conn.close()
            return
    elif filter_args:
        category = filter_args[0]

    # 继续解析 severity
    if '--severity' in args:
        idx = args.index('--severity')
        if idx + 1 < len(args):
            severity = args[idx + 1]

    # 构建查询
    query = "SELECT * FROM anti_patterns WHERE 1=1"
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)
    if severity:
        query += " AND severity = ?"
        params.append(severity)
    if enabled_filter is not None:
        query += " AND enabled = ?"
        params.append(enabled_filter)

    query += " ORDER BY severity DESC, category, code"

    cursor = conn.execute(query, params)
    patterns = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()

    # 简化输出（除非 --all）
    if not show_all:
        for p in patterns:
            p.pop('alternatives', None)
            p.pop('check_rules', None)
            p.pop('examples', None)

    print(json.dumps(patterns, ensure_ascii=False, indent=2))

def cmd_context_rules(args):
    """查询上下文规则。用法: db.py context_rules [category]"""
    conn = get_connection()

    category = args[0] if args else None
    if category:
        cursor = conn.execute("SELECT * FROM context_rules WHERE category = ? AND enabled = 1", (category,))
    else:
        cursor = conn.execute("SELECT * FROM context_rules WHERE enabled = 1")

    rules = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    print(json.dumps(rules, ensure_ascii=False, indent=2))

def cmd_add_anti_pattern(args):
    """
    添加问题模式。
    用法: db.py add_anti_pattern <category> <code> <pattern> <description> <severity> [alternatives_json] [check_rules_json] [examples_json]
    """
    if len(args) < 5:
        print(json.dumps({"error": "用法: db.py add_anti_pattern <category> <code> <pattern> <description> <severity> [alternatives_json] [check_rules_json] [examples_json]"}, ensure_ascii=False))
        return

    category, code, pattern, description, severity = args[0], args[1], args[2], args[3], args[4]
    alternatives = args[5] if len(args) > 5 else None
    check_rules = args[6] if len(args) > 6 else None
    examples = args[7] if len(args) > 7 else None

    # 验证 category
    valid_categories = ['ai_trace', 'logic', 'setting', 'poison', 'pacing']
    if category not in valid_categories:
        print(json.dumps({"error": f"无效类别: {category}", "valid_categories": valid_categories}, ensure_ascii=False))
        return

    # 验证 severity
    valid_severities = ['critical', 'high', 'medium', 'low']
    if severity not in valid_severities:
        print(json.dumps({"error": f"无效严重程度: {severity}", "valid_severities": valid_severities}, ensure_ascii=False))
        return

    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO anti_patterns (category, code, pattern, description, severity, alternatives, check_rules, examples)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (category, code, pattern, description, severity, alternatives, check_rules, examples))
        conn.commit()
        print(json.dumps({"success": True, "code": code, "category": category}, ensure_ascii=False))
    except sqlite3.IntegrityError:
        print(json.dumps({"error": f"模式代码 '{code}' 已存在"}, ensure_ascii=False))
    finally:
        conn.close()

def cmd_update_anti_pattern(args):
    """
    更新问题模式。
    用法: db.py update_anti_pattern <code> [--pattern <p>] [--description <d>] [--severity <s>] [--enabled <0|1>] [--alternatives <json>] [--check_rules <json>] [--examples <json>]
    """
    if len(args) < 1:
        print(json.dumps({"error": "用法: db.py update_anti_pattern <code> [--pattern <p>] [--description <d>] ..."}, ensure_ascii=False))
        return

    code = args[0]
    fields = {}
    i = 1
    while i < len(args):
        if args[i] == '--pattern' and i + 1 < len(args):
            fields['pattern'] = args[i + 1]; i += 2
        elif args[i] == '--description' and i + 1 < len(args):
            fields['description'] = args[i + 1]; i += 2
        elif args[i] == '--severity' and i + 1 < len(args):
            fields['severity'] = args[i + 1]; i += 2
        elif args[i] == '--enabled' and i + 1 < len(args):
            fields['enabled'] = int(args[i + 1]); i += 2
        elif args[i] == '--alternatives' and i + 1 < len(args):
            fields['alternatives'] = args[i + 1]; i += 2
        elif args[i] == '--check_rules' and i + 1 < len(args):
            fields['check_rules'] = args[i + 1]; i += 2
        elif args[i] == '--examples' and i + 1 < len(args):
            fields['examples'] = args[i + 1]; i += 2
        else:
            i += 1

    if not fields:
        print(json.dumps({"error": "请提供至少一个更新字段"}, ensure_ascii=False))
        return

    conn = get_connection()
    # 检查是否存在
    cursor = conn.execute("SELECT id FROM anti_patterns WHERE code = ?", (code,))
    if not cursor.fetchone():
        print(json.dumps({"error": f"模式代码 '{code}' 不存在"}, ensure_ascii=False))
        conn.close()
        return

    # updated_at 由 SQL 语句中的 datetime('now','+8 hours') 处理
    set_clause = ', '.join(f'{k}=?' for k in fields.keys())
    values = list(fields.values()) + [code]
    conn.execute(f"UPDATE anti_patterns SET {set_clause}, updated_at=datetime('now','+8 hours') WHERE code = ?", values)
    conn.commit()
    conn.close()
    print(json.dumps({"success": True, "code": code, "updated_fields": list(fields.keys())}, ensure_ascii=False))

def cmd_record_pattern_hit(args):
    """
    记录问题模式命中（增加发现次数）。
    用法: db.py record_pattern_hit <code> [project] [chapter]
    """
    if len(args) < 1:
        print(json.dumps({"error": "用法: db.py record_pattern_hit <code> [project] [chapter]"}, ensure_ascii=False))
        return

    code = args[0]
    project = args[1] if len(args) > 1 else None
    chapter = int(args[2]) if len(args) > 2 else None

    conn = get_connection()
    cursor = conn.execute("SELECT id FROM anti_patterns WHERE code = ?", (code,))
    if not cursor.fetchone():
        print(json.dumps({"error": f"模式代码 '{code}' 不存在"}, ensure_ascii=False))
        conn.close()
        return

    # 更新命中次数
    conn.execute("""
        UPDATE anti_patterns
        SET frequency = frequency + 1, last_seen = datetime('now','+8 hours')
        WHERE code = ?
    """, (code,))
    conn.commit()

    # 如果提供了项目和章节，同时记录到 learned_patterns
    if project and chapter:
        cursor = conn.execute("SELECT description FROM anti_patterns WHERE code = ?", (code,))
        pattern = row_to_dict(cursor.fetchone())
        if pattern:
            try:
                conn.execute("""
                    INSERT INTO learned_patterns (project_id, chapter_number, category, pattern)
                    VALUES (?, ?, (SELECT category FROM anti_patterns WHERE code = ?), ?)
                """, (project, chapter, code, pattern['description']))
                conn.commit()
            except:
                pass

    conn.close()
    print(json.dumps({"success": True, "code": code}, ensure_ascii=False))

def cmd_pattern_stats(args):
    """
    问题模式统计。
    用法: db.py pattern_stats [--top 10] [--category <cat>]
    """
    top = 10
    category = None

    if '--top' in args:
        idx = args.index('--top')
        if idx + 1 < len(args):
            top = int(args[idx + 1])
    if '--category' in args:
        idx = args.index('--category')
        if idx + 1 < len(args):
            category = args[idx + 1]

    conn = get_connection()

    # 按类别统计
    if category:
        cursor = conn.execute("""
            SELECT category, code, pattern, severity, frequency, last_seen
            FROM anti_patterns WHERE category = ? AND enabled = 1
            ORDER BY frequency DESC LIMIT ?
        """, (category, top))
    else:
        cursor = conn.execute("""
            SELECT category, code, pattern, severity, frequency, last_seen
            FROM anti_patterns WHERE enabled = 1
            ORDER BY frequency DESC LIMIT ?
        """, (top,))

    stats = [row_to_dict(row) for row in cursor.fetchall()]

    # 按类别汇总
    cursor = conn.execute("""
        SELECT category, COUNT(*) as total, SUM(frequency) as total_hits
        FROM anti_patterns WHERE enabled = 1
        GROUP BY category ORDER BY total_hits DESC
    """)
    by_category = [row_to_dict(row) for row in cursor.fetchall()]

    conn.close()

    print(json.dumps({
        "top_patterns": stats,
        "by_category": by_category,
        "total_patterns": sum(c['total'] for c in by_category),
        "total_hits": sum(c['total_hits'] or 0 for c in by_category)
    }, ensure_ascii=False, indent=2))


def cmd_add_context_rule(args):
    """
    添加上下文规则。
    用法: db.py add_context_rule <rule> <category> <severity>
    
    category: logic, setting, character, timeline
    severity: critical, high, medium
    """
    if len(args) < 3:
        print(json.dumps({"error": "用法: db.py add_context_rule <rule> <category> <severity>"}, ensure_ascii=False))
        return
    
    rule, category, severity = args[0], args[1], args[2]
    
    # 验证 category
    valid_categories = ['logic', 'setting', 'character', 'timeline']
    if category not in valid_categories:
        print(json.dumps({"error": f"无效类别: {category}", "valid_categories": valid_categories}, ensure_ascii=False))
        return
    
    # 验证 severity
    valid_severities = ['critical', 'high', 'medium']
    if severity not in valid_severities:
        print(json.dumps({"error": f"无效严重程度: {severity}", "valid_severities": valid_severities}, ensure_ascii=False))
        return
    
    conn = get_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO context_rules (rule, category, severity)
            VALUES (?, ?, ?)
        """, (rule, category, severity))
        conn.commit()
        print(json.dumps({"success": True, "id": cursor.lastrowid, "rule": rule[:50] + "..."}, ensure_ascii=False))
    except sqlite3.IntegrityError:
        print(json.dumps({"error": "规则已存在"}, ensure_ascii=False))
    finally:
        conn.close()


def cmd_add_best_practice(args):
    """
    添加最佳实践（高分章节经验）。
    用法: db.py add_best_practice <project> <category> <practice> [source_chapters_json] [avg_score] [evidence]
    
    category: pacing, dialogue, action, emotion, setting, hook
    """
    if len(args) < 3:
        print(json.dumps({"error": "用法: db.py add_best_practice <project> <category> <practice> [source_chapters_json] [avg_score] [evidence]"}, ensure_ascii=False))
        return
    
    project_id, category, practice = args[0], args[1], args[2]
    source_chapters = args[3] if len(args) > 3 else None
    avg_score = float(args[4]) if len(args) > 4 else None
    evidence = args[5] if len(args) > 5 else None
    
    # 验证 category
    valid_categories = ['pacing', 'dialogue', 'action', 'emotion', 'setting', 'hook']
    if category not in valid_categories:
        print(json.dumps({"error": f"无效类别: {category}", "valid_categories": valid_categories}, ensure_ascii=False))
        return
    
    conn = get_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO best_practices (project_id, source_chapters, avg_score, category, practice, evidence)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (project_id, source_chapters, avg_score, category, practice, evidence))
        conn.commit()
        print(json.dumps({"success": True, "id": cursor.lastrowid, "category": category}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
    finally:
        conn.close()


def cmd_best_practices(args):
    """
    查询最佳实践。
    用法: db.py best_practices [category] [--project <project>]
    """
    conn = get_connection()
    
    category = None
    project_id = None
    
    i = 0
    while i < len(args):
        if args[i] == '--project' and i + 1 < len(args):
            project_id = args[i + 1]
            i += 2
        elif not args[i].startswith('--'):
            category = args[i]
            i += 1
        else:
            i += 1
    
    query = "SELECT * FROM best_practices WHERE 1=1"
    params = []
    
    if category:
        query += " AND category = ?"
        params.append(category)
    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    
    query += " ORDER BY avg_score DESC, created_at DESC"
    
    cursor = conn.execute(query, params)
    practices = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    
    print(json.dumps(practices, ensure_ascii=False, indent=2))


def cmd_extract_best_practices(args):
    """
    从高分章节自动提取最佳实践。
    用法: db.py extract_best_practices <project> <chapter> --score <score>
    
    自动分析高分章节，提取写作亮点并记录到 best_practices。
    """
    if len(args) < 2:
        print(json.dumps({"error": "用法: db.py extract_best_practices <project> <chapter> --score <score>"}, ensure_ascii=False))
        return
    
    project_id = args[0]
    chapter = int(args[1])
    score = 85  # 默认分数
    
    i = 2
    while i < len(args):
        if args[i] == '--score' and i + 1 < len(args):
            score = int(args[i + 1])
            i += 2
        else:
            i += 1
    
    # 只有高分章节才提取
    if score < 85:
        print(json.dumps({"skipped": True, "reason": f"分数 {score} < 85，不提取最佳实践"}, ensure_ascii=False))
        return
    
    conn = get_connection()
    try:
        # 获取章节信息和质检报告
        cursor = conn.execute("""
            SELECT c.title, c.words, r.summary, r.set_score, r.logic_score, r.poison_score, r.text_score, r.pace_score
            FROM chapters c
            LEFT JOIN reviews r ON c.project_id = r.project_id AND c.chapter_number = r.chapter_number
            WHERE c.project_id = ? AND c.chapter_number = ?
        """, (project_id, chapter))
        row = cursor.fetchone()
        
        if not row:
            print(json.dumps({"error": "章节不存在"}, ensure_ascii=False))
            return
        
        chapter_data = row_to_dict(row)
        
        # 根据各维度分数自动提取
        extracted = []
        
        # Hook: 开篇类（通常是第1-3章）
        if chapter <= 3 and score >= 90:
            extracted.append({
                'category': 'hook',
                'practice': f"第{chapter}章开篇成功建立核心冲突",
                'evidence': chapter_data.get('title', ''),
                'source_score': score
            })
        
        # Pacing: 节奏分数高
        if chapter_data.get('pace_score', 0) >= 18:
            extracted.append({
                'category': 'pacing',
                'practice': f"第{chapter}章节奏张弛有度，得分{chapter_data['pace_score']}",
                'evidence': chapter_data.get('summary', '')[:100] if chapter_data.get('summary') else '',
                'source_score': score
            })
        
        # Text: 文字分数高
        if chapter_data.get('text_score', 0) >= 18:
            extracted.append({
                'category': 'dialogue',
                'practice': f"第{chapter}章对话/文字表达出色，得分{chapter_data['text_score']}",
                'evidence': None,
                'source_score': score
            })
        
        # Poison: 无毒点
        if chapter_data.get('poison_score', 0) >= 19:
            extracted.append({
                'category': 'setting',
                'practice': f"第{chapter}章设定严谨无崩塌，无毒点",
                'evidence': None,
                'source_score': score
            })
        
        # 写入数据库
        for item in extracted:
            try:
                conn.execute("""
                    INSERT INTO best_practices (project_id, category, practice, evidence, source_score, chapter_numbers)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (project_id, item['category'], item['practice'], item['evidence'], item['source_score'], str(chapter)))
            except:
                pass  # 忽略重复
        
        conn.commit()
        
        print(json.dumps({
            "success": True,
            "chapter": chapter,
            "score": score,
            "extracted_count": len(extracted),
            "practices": extracted
        }, ensure_ascii=False, indent=2))
        
    finally:
        conn.close()


def cmd_batch_extract_practices(args):
    """
    批量提取项目高分章节的最佳实践。
    用法: db.py batch_extract_practices <project> [--min-score 90]
    """
    if len(args) < 1:
        print(json.dumps({"error": "用法: db.py batch_extract_practices <project> [--min-score 90]"}, ensure_ascii=False))
        return
    
    project_id = args[0]
    min_score = 85
    
    i = 1
    while i < len(args):
        if args[i] == '--min-score' and i + 1 < len(args):
            min_score = int(args[i + 1])
            i += 2
        else:
            i += 1
    
    conn = get_connection()
    try:
        # 查找高分章节（reviews 表用 chapter_id，需要 JOIN chapters 获取 chapter_number）
        cursor = conn.execute("""
            SELECT c.chapter_number, AVG(r.setting_score + r.logic_score + r.poison_score + r.text_score + r.pacing_score) as avg_score
            FROM reviews r
            JOIN chapters c ON r.chapter_id = c.id
            WHERE r.project_id = ?
            GROUP BY c.chapter_number
            HAVING avg_score >= ?
            ORDER BY avg_score DESC
        """, (project_id, min_score))
        
        high_score_chapters = [row_to_dict(row) for row in cursor.fetchall()]
        
        if not high_score_chapters:
            print(json.dumps({"info": f"没有分数 >= {min_score} 的章节"}, ensure_ascii=False))
            return
        
        # 批量提取
        total_extracted = 0
        for ch in high_score_chapters:
            chapter = int(ch['chapter_number'])
            score = int(ch['avg_score'])
            
            # 调用单个提取逻辑
            cursor2 = conn.execute("""
                SELECT c.title, r.summary, r.setting_score, r.logic_score, r.poison_score, r.text_score, r.pacing_score
                FROM chapters c
                LEFT JOIN reviews r ON c.project_id = r.project_id AND c.chapter_number = ?
                WHERE c.project_id = ? AND c.chapter_number = ?
            """, (chapter, project_id, chapter))
            row = cursor2.fetchone()
            
            if not row:
                continue
            
            chapter_data = row_to_dict(row)
            extracted = []
            
            # Hook
            if chapter <= 3 and score >= 90:
                extracted.append(('hook', f"第{chapter}章开篇成功建立核心冲突", chapter_data.get('title', '')))
            
            # Pacing
            if chapter_data.get('pace_score', 0) >= 18:
                extracted.append(('pacing', f"第{chapter}章节奏张弛有度", str(chapter_data.get('pace_score', 0))))
            
            # Text
            if chapter_data.get('text_score', 0) >= 18:
                extracted.append(('dialogue', f"第{chapter}章文字表达出色", str(chapter_data.get('text_score', 0))))
            
            # Poison-free
            if chapter_data.get('poison_score', 0) >= 19:
                extracted.append(('setting', f"第{chapter}章设定严谨", "无毒点"))
            
            for cat, practice, evidence in extracted:
                try:
                    conn.execute("""
                        INSERT INTO best_practices (project_id, category, practice, evidence, source_score, chapter_numbers)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (project_id, cat, practice, evidence, score, str(chapter)))
                    total_extracted += 1
                except:
                    pass
        
        conn.commit()
        
        print(json.dumps({
            "success": True,
            "project": project_id,
            "min_score": min_score,
            "chapters_processed": len(high_score_chapters),
            "practices_extracted": total_extracted
        }, ensure_ascii=False, indent=2))
        
    finally:
        conn.close()


def cmd_promote_pattern(args):
    """
    将高频 learned_patterns 提升为 anti_patterns。
    用法: db.py promote_pattern <pattern_id> [--severity medium]
    """
    if len(args) < 1:
        print(json.dumps({"error": "用法: db.py promote_pattern <pattern_id> [--severity medium]"}, ensure_ascii=False))
        return
    
    pattern_id = int(args[0])
    severity = 'medium'
    
    i = 1
    while i < len(args):
        if args[i] == '--severity' and i + 1 < len(args):
            severity = args[i + 1]
            i += 2
        else:
            i += 1
    
    valid_severities = ['critical', 'high', 'medium', 'low']
    if severity not in valid_severities:
        print(json.dumps({"error": f"无效严重程度: {severity}", "valid_severities": valid_severities}, ensure_ascii=False))
        return
    
    conn = get_connection()
    try:
        # 获取 learned_pattern
        cursor = conn.execute("SELECT * FROM learned_patterns WHERE id = ?", (pattern_id,))
        pattern = cursor.fetchone()
        
        if not pattern:
            print(json.dumps({"error": f"learned_pattern {pattern_id} 不存在"}, ensure_ascii=False))
            return
        
        pattern_dict = row_to_dict(pattern)
        
        # 生成代码
        code = f"LP{pattern_id:03d}"
        
        # 检查是否已存在
        existing = conn.execute("SELECT id FROM anti_patterns WHERE code = ?", (code,)).fetchone()
        if existing:
            print(json.dumps({"error": f"anti_patterns 已存在 {code}", "existing_id": existing[0]}, ensure_ascii=False))
            return
        
        # 插入到 anti_patterns
        cursor = conn.execute("""
            INSERT INTO anti_patterns (code, category, pattern, description, severity, frequency)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, pattern_dict['category'], pattern_dict['pattern'], 
              f"从项目经验学习：{pattern_dict['pattern']}", severity, pattern_dict['frequency']))
        
        conn.commit()
        
        print(json.dumps({
            "success": True,
            "code": code,
            "category": pattern_dict['category'],
            "pattern": pattern_dict['pattern'],
            "severity": severity
        }, ensure_ascii=False, indent=2))
        
    finally:
        conn.close()


def cmd_learned_patterns(args):
    """
    查询学习到的问题模式。
    用法: db.py learned_patterns [category] [--project <project>] [--top 10]
    """
    conn = get_connection()
    
    category = None
    project_id = None
    limit = 20
    
    i = 0
    while i < len(args):
        if args[i] == '--project' and i + 1 < len(args):
            project_id = args[i + 1]
            i += 2
        elif args[i] == '--top' and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif not args[i].startswith('--'):
            category = args[i]
            i += 1
        else:
            i += 1
    
    query = "SELECT * FROM learned_patterns WHERE 1=1"
    params = []
    
    if category:
        query += " AND category = ?"
        params.append(category)
    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    
    query += " ORDER BY frequency DESC LIMIT ?"
    params.append(limit)
    
    cursor = conn.execute(query, params)
    patterns = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    
    print(json.dumps(patterns, ensure_ascii=False, indent=2))


def cmd_send_message(args):
    """
    发送异步消息给其他 Agent（通过 agent_messages 表）。

    用法: db.py send_message <project_id> <from_agent> <to_agent> <type> <chapter> '<json_content>' [priority]

    参数:
        project_id: 项目 ID
        from_agent: 发送方 Agent ID (dispatcher/planner/author/editor/scout/secretary/architect)
        to_agent: 接收方 Agent ID
        type: 消息类型 (FLAG_ISSUE/ESCALATE/SUGGEST/NOTIFY)
        chapter: 章节号 (可选，传 - 表示不关联)
        json_content: JSON 格式的消息内容
        priority: 优先级 (normal/high/urgent)，默认 normal

    示例:
        db.py send_message xuanhuan editor planner ESCALATE 10 '{"issue":"伏笔冲突","reason":"..."}' high
    """
    if len(args) < 6:
        print("Usage: db.py send_message <project_id> <from_agent> <to_agent> <type> <chapter> '<json_content>' [priority]")
        print("Types: FLAG_ISSUE, ESCALATE, SUGGEST, NOTIFY")
        print("Priority: normal, high, urgent (default: normal)")
        return

    project_id = args[0]
    from_agent = args[1]
    to_agent = args[2]
    msg_type = args[3].upper()
    chapter_num = args[4]
    content_json = args[5]
    priority = args[6].lower() if len(args) > 6 else 'normal'

    # 验证消息类型
    valid_types = ['FLAG_ISSUE', 'ESCALATE', 'SUGGEST', 'NOTIFY']
    if msg_type not in valid_types:
        print(json.dumps({
            "success": False,
            "error": f"无效消息类型: {msg_type}",
            "valid_types": valid_types
        }, ensure_ascii=False))
        return

    # 验证优先级
    valid_priorities = ['normal', 'high', 'urgent']
    if priority not in valid_priorities:
        print(json.dumps({
            "success": False,
            "error": f"无效优先级: {priority}",
            "valid_priorities": valid_priorities
        }, ensure_ascii=False))
        return

    # 解析章节号
    chapter_number = None
    if chapter_num != '-':
        try:
            chapter_number = int(chapter_num)
        except ValueError:
            print(json.dumps({
                "success": False,
                "error": f"章节号必须是数字或 '-': {chapter_num}"
            }, ensure_ascii=False))
            return

    # 解析 JSON 内容
    try:
        content = json.loads(content_json)
    except json.JSONDecodeError as e:
        print(json.dumps({
            "success": False,
            "error": f"JSON 解析失败: {e}"
        }, ensure_ascii=False))
        return

    conn = get_connection()

    try:
        cursor = conn.execute("""
            INSERT INTO agent_messages
            (project_id, from_agent, to_agent, type, priority, content, chapter_number, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (project_id, from_agent, to_agent, msg_type, priority, json.dumps(content, ensure_ascii=False), chapter_number))

        conn.commit()
        message_id = cursor.lastrowid

        print(json.dumps({
            "success": True,
            "message_id": message_id,
            "project_id": project_id,
            "from": from_agent,
            "to": to_agent,
            "type": msg_type,
            "priority": priority,
            "chapter": chapter_number,
            "status": "pending"
        }, ensure_ascii=False, indent=2))

    except sqlite3.Error as e:
        print(json.dumps({
            "success": False,
            "error": f"数据库错误: {e}"
        }, ensure_ascii=False))
    finally:
        conn.close()


def cmd_get_messages(args):
    """
    获取指定 Agent 的待处理消息。

    用法: db.py get_messages <project_id> <to_agent> [status] [limit]

    参数:
        project_id: 项目 ID
        to_agent: 接收方 Agent ID
        status: 消息状态 (pending/processing/resolved/all)，默认 pending
        limit: 返回数量限制，默认 10
    """
    if len(args) < 2:
        print("Usage: db.py get_messages <project_id> <to_agent> [status] [limit]")
        return

    project_id = args[0]
    to_agent = args[1]
    status = args[2] if len(args) > 2 else 'pending'
    limit = int(args[3]) if len(args) > 3 else 10

    conn = get_connection()

    if status == 'all':
        cursor = conn.execute("""
            SELECT id, from_agent, type, priority, content, chapter_number, status, created_at
            FROM agent_messages
            WHERE project_id = ? AND to_agent = ?
            ORDER BY
                CASE priority
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    ELSE 3
                END,
                created_at DESC
            LIMIT ?
        """, (project_id, to_agent, limit))
    else:
        cursor = conn.execute("""
            SELECT id, from_agent, type, priority, content, chapter_number, status, created_at
            FROM agent_messages
            WHERE project_id = ? AND to_agent = ? AND status = ?
            ORDER BY
                CASE priority
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    ELSE 3
                END,
                created_at DESC
            LIMIT ?
        """, (project_id, to_agent, status, limit))

    messages = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()

    print(json.dumps({
        "success": True,
        "project_id": project_id,
        "to_agent": to_agent,
        "status": status,
        "count": len(messages),
        "messages": messages
    }, ensure_ascii=False, indent=2))


def cmd_resolve_message(args):
    """
    标记消息为已处理。

    用法: db.py resolve_message <message_id> [result]

    参数:
        message_id: 消息 ID
        result: 处理结果说明（可选）
    """
    if len(args) < 1:
        print("Usage: db.py resolve_message <message_id> [result]")
        return

    message_id = int(args[0])
    result = args[1] if len(args) > 1 else None

    conn = get_connection()

    cursor = conn.execute("""
        UPDATE agent_messages
        SET status = 'resolved',
            processed_at = datetime('now', '+8 hours'),
            result = ?
        WHERE id = ?
    """, (result, message_id))

    if cursor.rowcount == 0:
        print(json.dumps({
            "success": False,
            "error": f"消息 {message_id} 不存在"
        }, ensure_ascii=False))
    else:
        conn.commit()
        print(json.dumps({
            "success": True,
            "message_id": message_id,
            "status": "resolved"
        }, ensure_ascii=False))

    conn.close()


# ============== 版本管理命令 ==============

def cmd_list_versions(args):
    """
    列出章节版本历史。

    用法: db.py list_versions <project> <chapter>
    """
    if len(args) < 2:
        print("Usage: db.py list_versions <project> <chapter>")
        return

    project_id = args[0]
    chapter = int(args[1])
    conn = get_connection()

    cursor = conn.execute("""
        SELECT id, version, word_count, created_at, created_by, notes
        FROM chapter_versions
        WHERE project_id = ? AND chapter = ?
        ORDER BY version DESC
    """, (project_id, chapter))

    versions = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()

    print(json.dumps({
        "success": True,
        "project": project_id,
        "chapter": chapter,
        "versions": versions,
        "count": len(versions)
    }, ensure_ascii=False, indent=2))


def cmd_get_version(args):
    """
    获取指定版本的章节内容。

    用法: db.py get_version <project> <chapter> <version>
    """
    if len(args) < 3:
        print("Usage: db.py get_version <project> <chapter> <version>")
        return

    project_id = args[0]
    chapter = int(args[1])
    version = int(args[2])
    conn = get_connection()

    cursor = conn.execute("""
        SELECT id, version, content, word_count, created_at, created_by, review_id, notes
        FROM chapter_versions
        WHERE project_id = ? AND chapter = ? AND version = ?
    """, (project_id, chapter, version))

    row = cursor.fetchone()
    conn.close()

    if row:
        print(json.dumps(row_to_dict(row), ensure_ascii=False, indent=2))
    else:
        print(json.dumps({
            "success": False,
            "error": f"版本 {version} 不存在"
        }, ensure_ascii=False))


def cmd_rollback_version(args):
    """
    回滚章节到指定版本。

    用法: db.py rollback_version <project> <chapter> <version>
    """
    if len(args) < 3:
        print("Usage: db.py rollback_version <project> <chapter> <version>")
        return

    project_id = args[0]
    chapter = int(args[1])
    target_version = int(args[2])
    conn = get_connection()

    # 获取目标版本
    cursor = conn.execute("""
        SELECT content, word_count
        FROM chapter_versions
        WHERE project_id = ? AND chapter = ? AND version = ?
    """, (project_id, chapter, target_version))

    version_data = cursor.fetchone()
    if not version_data:
        print(json.dumps({
            "success": False,
            "error": f"版本 {target_version} 不存在"
        }, ensure_ascii=False))
        conn.close()
        return

    content = version_data['content']
    word_count = version_data['word_count']

    # 获取当前最大版本号
    cursor = conn.execute("""
        SELECT MAX(version) as max_version
        FROM chapter_versions
        WHERE project_id = ? AND chapter = ?
    """, (project_id, chapter))
    max_version = cursor.fetchone()['max_version'] or 0

    # 保存回滚版本
    conn.execute("""
        INSERT INTO chapter_versions (project_id, chapter, version, content, word_count, created_by, notes)
        VALUES (?, ?, ?, ?, ?, 'rollback', ?)
    """, (project_id, chapter, max_version + 1, content, word_count, f"回滚到版本 {target_version}"))

    # 更新章节表
    conn.execute("""
        UPDATE chapters SET content = ?, word_count = ?, status = 'revision'
        WHERE project_id = ? AND chapter_number = ?
    """, (content, word_count, project_id, chapter))

    conn.commit()
    conn.close()

    print(json.dumps({
        "success": True,
        "project": project_id,
        "chapter": chapter,
        "rolled_back_to": target_version,
        "new_version": max_version + 1,
        "word_count": word_count
    }, ensure_ascii=False, indent=2))


# ============== 上下文构建命令 ==============

def cmd_build_context(args):
    """
    为 Agent 构建上下文。

    用法: db.py build_context <project> <chapter> <agent_type> [--tokens <limit>]

    agent_type: author, editor, planner
    """
    if len(args) < 3:
        print("Usage: db.py build_context <project> <chapter> <agent_type> [--tokens <limit>]")
        print("  agent_type: author, editor, planner")
        return

    project_id = args[0]
    chapter_num = int(args[1])
    agent_type = args[2]
    token_limit = 8000

    # 解析可选参数
    i = 3
    while i < len(args):
        if args[i] == '--tokens' and i + 1 < len(args):
            token_limit = int(args[i + 1])
            i += 2
        else:
            i += 1

    if agent_type not in ['author', 'editor', 'planner']:
        print(json.dumps({
            "success": False,
            "error": f"不支持的 agent_type: {agent_type}，请使用 author/editor/planner"
        }, ensure_ascii=False))
        return

    # 构建上下文
    context_parts = []

    # 1. 死刑红线（所有 Agent 共享）
    death_penalty = """## 死刑红线

### AI 烂词（出现即 50 分）
- 冷笑、嘴角微扬、嘴角勾起、眯起眼睛、眼中闪过一丝
- 眼神复杂、沉默片刻、气氛变得、一股、似乎、仿佛
- 深吸一口气、倒吸一口凉气、瞳孔骤缩、目光闪烁

### 降智场景（出现即退回）
- 反派明知主角身份还留手
- 主角获得关键信息后不思考直接行动
- 所有角色使用相同的说话方式"""
    context_parts.append(death_penalty)

    # 2. 写作指令
    conn = get_connection()
    cursor = conn.execute(
        "SELECT * FROM instructions WHERE project_id=? AND chapter_number=?",
        (project_id, chapter_num)
    )
    instruction = row_to_dict(cursor.fetchone())

    if instruction:
        instruction_text = f"""## 写作指令（第 {chapter_num} 章）

### 目标
{instruction.get('objective', '未设置')}

### 关键事件
{instruction.get('key_events', '未设置')}

### 要兑现的伏笔
{instruction.get('plots_to_resolve', '[]')}

### 要埋设的伏笔
{instruction.get('plots_to_plant', '[]')}

### 情绪基调
{instruction.get('emotion_tone', '未设置')}

### 结尾钩子
{instruction.get('ending_hook', '未设置')}

### 目标字数
{instruction.get('word_target', 2500)} 字"""
        context_parts.append(instruction_text)

    # 3. 状态卡（上一章）
    if chapter_num > 1:
        cursor = conn.execute(
            "SELECT state_data, summary FROM chapter_state WHERE project_id=? AND chapter_number=?",
            (project_id, chapter_num - 1)
        )
        state = row_to_dict(cursor.fetchone())
        if state:
            state_data = json.loads(state.get('state_data', '{}'))
            state_text = f"""## 状态卡（第 {chapter_num - 1} 章结束）

### 状态摘要
{state.get('summary', '')}

### 详细数值
```json
{json.dumps(state_data, ensure_ascii=False, indent=2)}
```

⚠️ 重要：所有数值必须从此状态卡复制，禁止自行编造！"""
            context_parts.append(state_text)
    else:
        context_parts.append("## 状态卡\n（第 1 章，无上一章状态卡，使用世界观初始数值）")

    # 4. 待处理伏笔
    cursor = conn.execute(
        """SELECT code, title, type, description, planted_chapter, planned_resolve_chapter
           FROM plot_holes
           WHERE project_id=? AND status IN ('planted', 'hinted')
           ORDER BY
             CASE type WHEN 'short' THEN 1 WHEN 'mid' THEN 2 ELSE 3 END,
             planned_resolve_chapter""",
        (project_id,)
    )
    plots = [row_to_dict(row) for row in cursor.fetchall()]

    if plots:
        plot_lines = ["| 代码 | 标题 | 类型 | 埋设章节 | 计划兑现 | 描述 |", "|------|------|------|----------|----------|------|"]
        for plot in plots[:10]:  # 限制数量
            plot_lines.append(
                f"| {plot['code']} | {plot['title'][:15]} | {plot['type']} | "
                f"{plot['planted_chapter']} | {plot.get('planned_resolve_chapter') or '未定'} | "
                f"{plot['description'][:20]}... |"
            )
        context_parts.append("## 待处理伏笔\n" + "\n".join(plot_lines))

    # 5. 问题模式库
    cursor = conn.execute(
        """SELECT code, pattern, description, severity
           FROM anti_patterns
           WHERE enabled = 1
           ORDER BY severity, frequency DESC
           LIMIT 15"""
    )
    patterns = [row_to_dict(row) for row in cursor.fetchall()]

    if patterns:
        pattern_lines = ["| 代码 | 模式 | 描述 | 严重度 |", "|------|------|------|--------|"]
        for p in patterns:
            pattern_lines.append(
                f"| {p['code']} | {p['pattern'][:15]} | {p['description'][:25]}... | {p['severity']} |"
            )
        context_parts.append("## 问题模式库（避坑指南）\n" + "\n".join(pattern_lines))

    # 5.5. 最佳实践（高分范例）
    cursor = conn.execute(
        """SELECT category, practice, evidence, source_score, chapter_numbers
           FROM best_practices
           WHERE (project_id = ? OR project_id IS NULL)
           AND source_score >= 85
           ORDER BY source_score DESC, category
           LIMIT 15""",
        (project_id,)
    )
    practices = [row_to_dict(row) for row in cursor.fetchall()]

    if practices:
        cat_names = {
            'hook': '开篇', 'pacing': '节奏', 'dialogue': '对话',
            'action': '动作', 'emotion': '情感', 'setting': '设定'
        }
        practice_lines = ["## 高分范例（最佳实践）"]
        for p in practices:
            cat_name = cat_names.get(p['category'], p['category'])
            practice_lines.append(f"- 【{cat_name}】{p['practice']}")
            if p.get('evidence'):
                practice_lines.append(f"  示例：{p['evidence'][:60]}")
            if p.get('chapter_numbers'):
                practice_lines.append(f"  来源：第{p['chapter_numbers']}章（{p['source_score']}分）")
        context_parts.append("\n".join(practice_lines))

    # 6. 角色设定（只取主要角色）
    cursor = conn.execute(
        """SELECT name, alias, role, description, status
           FROM characters
           WHERE project_id=? AND status = 'active'
           ORDER BY
             CASE role
               WHEN 'protagonist' THEN 1
               WHEN 'antagonist' THEN 2
               WHEN 'supporting' THEN 3
               ELSE 4
             END
           LIMIT 5""",
        (project_id,)
    )
    characters = [row_to_dict(row) for row in cursor.fetchall()]

    if characters:
        char_lines = ["## 角色设定"]
        for char in characters:
            role_emoji = {'protagonist': '👤', 'antagonist': '🎭', 'supporting': '👥'}.get(char['role'], '?')
            char_lines.append(f"\n### {role_emoji} {char['name']}" + (f"（{char['alias']}）" if char['alias'] else ''))
            char_lines.append(f"角色：{char['role']}")
            if char['description']:
                char_lines.append(f"描述：{char['description'][:100]}")
        context_parts.append("\n".join(char_lines))

    # 7. Editor 特有：章节内容
    if agent_type == 'editor':
        cursor = conn.execute(
            "SELECT content, word_count FROM chapters WHERE project_id=? AND chapter_number=?",
            (project_id, chapter_num)
        )
        chapter_data = row_to_dict(cursor.fetchone())
        if chapter_data:
            content = chapter_data.get('content', '')
            if len(content) > 8000:
                content = content[:8000] + "\n\n... (内容已截断)"
            context_parts.append(f"## 章节内容（字数：{chapter_data.get('word_count', 0)}）\n\n{content}")

    conn.close()

    # 组装最终上下文
    full_context = "\n\n---\n\n".join(context_parts)

    # Token 估算（中文约 1.5 字/token）
    estimated_tokens = int(len(full_context) / 1.5)

    print(json.dumps({
        "success": True,
        "agent_type": agent_type,
        "chapter": chapter_num,
        "estimated_tokens": estimated_tokens,
        "token_limit": token_limit,
        "context": full_context
    }, ensure_ascii=False, indent=2))


# ============== 健康报告命令 ==============

def cmd_health_report(args):
    """
    生成项目健康报告。

    用法: db.py health_report <project>
    """
    if len(args) < 1:
        print("Usage: db.py health_report <project>")
        return

    project_id = args[0]
    conn = get_connection()

    # 获取项目信息
    cursor = conn.execute(
        "SELECT name, genre, current_chapter FROM projects WHERE project_id=?",
        (project_id,)
    )
    project = row_to_dict(cursor.fetchone())

    if not project:
        print(json.dumps({"success": False, "error": f"项目 {project_id} 不存在"}, ensure_ascii=False))
        conn.close()
        return

    # 收集指标
    metrics = {}

    # 1. 任务失败率（过去 7 天）
    cursor = conn.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
        FROM task_status
        WHERE project_id = ? AND created_at > datetime('now', '-7 days')
    """, (project_id,))
    row = cursor.fetchone()
    metrics['task_failure_rate'] = round((row['failed'] / row['total'] * 100) if row and row['total'] > 0 else 0, 2)

    # 2. 平均质检分数
    cursor = conn.execute(
        "SELECT AVG(review_score) as avg_score FROM chapters WHERE project_id=? AND review_score > 0",
        (project_id,)
    )
    metrics['avg_review_score'] = round(cursor.fetchone()['avg_score'] or 0, 2)

    # 3. 伏笔兑现率
    cursor = conn.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) as resolved
        FROM plot_holes WHERE project_id = ?
    """, (project_id,))
    row = cursor.fetchone()
    metrics['plot_resolution_rate'] = round((row['resolved'] / row['total'] * 100) if row and row['total'] > 0 else 100, 2)

    # 4. 熔断触发次数
    cursor = conn.execute(
        "SELECT COUNT(*) as count FROM chapters WHERE project_id=? AND retry_count >= 3",
        (project_id,)
    )
    metrics['fuse_count'] = cursor.fetchone()['count']

    # 5. 消息队列积压
    cursor = conn.execute(
        "SELECT COUNT(*) as count FROM agent_messages WHERE project_id=? AND status='pending'",
        (project_id,)
    )
    metrics['message_backlog'] = cursor.fetchone()['count']

    # 6. 章节统计
    cursor = conn.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END) as published,
               SUM(CASE WHEN status = 'reviewed' THEN 1 ELSE 0 END) as reviewed,
               SUM(CASE WHEN status = 'review' THEN 1 ELSE 0 END) as in_review,
               SUM(CASE WHEN status = 'drafting' THEN 1 ELSE 0 END) as drafting,
               SUM(CASE WHEN status = 'revision' THEN 1 ELSE 0 END) as revision
        FROM chapters WHERE project_id = ?
    """, (project_id,))
    chapter_stats = row_to_dict(cursor.fetchone())

    # 生成告警
    alerts = []
    if metrics['task_failure_rate'] > 20:
        alerts.append({"level": "error", "message": f"任务失败率过高: {metrics['task_failure_rate']}%"})
    elif metrics['task_failure_rate'] > 10:
        alerts.append({"level": "warning", "message": f"任务失败率偏高: {metrics['task_failure_rate']}%"})

    if metrics['avg_review_score'] < 70:
        alerts.append({"level": "error", "message": f"平均质检分数过低: {metrics['avg_review_score']}"})
    elif metrics['avg_review_score'] < 80:
        alerts.append({"level": "warning", "message": f"平均质检分数偏低: {metrics['avg_review_score']}"})

    if metrics['fuse_count'] > 0:
        alerts.append({"level": "warning", "message": f"有 {metrics['fuse_count']} 个章节触发熔断"})

    if metrics['message_backlog'] > 10:
        alerts.append({"level": "error", "message": f"消息队列积压: {metrics['message_backlog']} 条"})
    elif metrics['message_backlog'] > 5:
        alerts.append({"level": "warning", "message": f"消息队列有积压: {metrics['message_backlog']} 条"})

    # 确定整体状态
    if any(a['level'] == 'error' for a in alerts):
        status = 'error'
    elif any(a['level'] == 'warning' for a in alerts):
        status = 'warning'
    else:
        status = 'healthy'

    conn.close()

    print(json.dumps({
        "success": True,
        "status": status,
        "project": {
            "id": project_id,
            "name": project['name'],
            "genre": project['genre'],
            "current_chapter": project['current_chapter']
        },
        "metrics": metrics,
        "chapter_stats": chapter_stats,
        "alerts": alerts
    }, ensure_ascii=False, indent=2))


# ============== 重试计数命令 ==============

def cmd_increment_retry(args):
    """
    递增任务重试计数。

    用法: db.py increment_retry <task_id>
    """
    if len(args) < 1:
        print("Usage: db.py increment_retry <task_id>")
        return

    task_id = int(args[0])
    conn = get_connection()

    cursor = conn.execute("""
        UPDATE task_status
        SET retry_count = retry_count + 1
        WHERE id = ?
    """, (task_id,))

    if cursor.rowcount == 0:
        print(json.dumps({
            "success": False,
            "error": f"任务 {task_id} 不存在"
        }, ensure_ascii=False))
    else:
        # 获取新的重试计数
        cursor = conn.execute("SELECT retry_count FROM task_status WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.commit()

        print(json.dumps({
            "success": True,
            "task_id": task_id,
            "retry_count": row['retry_count'] if row else 0
        }, ensure_ascii=False))

    conn.close()


# ============== 命令注册表 ==============

ALL_COMMANDS = {
    'projects': cmd_projects,
    'add_project': cmd_add_project,
    'update_project': cmd_update_project,
    'current_project': cmd_current_project,
    'set_current_project': cmd_set_current_project,
    'add_world_setting': cmd_add_world_setting,
    'world_settings': cmd_world_settings,
    'update_world_setting': cmd_update_world_setting,
    'delete_world_setting': cmd_delete_world_setting,
    'add_character': cmd_add_character,
    'characters': cmd_characters,
    'update_character': cmd_update_character,
    'delete_character': cmd_delete_character,
    'add_faction': cmd_add_faction,
    'factions': cmd_factions,
    'update_faction': cmd_update_faction,
    'delete_faction': cmd_delete_faction,
    'chapters': cmd_chapters,
    'add_chapter': cmd_add_chapter,
    'next_chapter': cmd_next_chapter,
    'update_chapter': cmd_update_chapter,
    'chapter_content': cmd_chapter_content,
    'save_draft': cmd_save_draft,
    'publish_chapter': cmd_publish_chapter,
    'instruction': cmd_instruction,
    'instructions': cmd_instructions,
    'create_instruction': cmd_create_instruction,
    'update_instruction': cmd_update_instruction,
    'add_plot': cmd_add_plot,
    'resolve_plot': cmd_resolve_plot,
    'pending_plots': cmd_pending_plots,
    'plots_by_chapter': cmd_plots_by_chapter,
    'sync_plots': cmd_sync_plots,
    'verify_plots': cmd_verify_plots,
    'add_review': cmd_add_review,
    'reviews': cmd_reviews,
    'chapter_state': cmd_chapter_state,
    'validate_state': cmd_validate_state,
    'stats': cmd_stats,
    'task_start': cmd_task_start,
    'task_complete': cmd_task_complete,
    'task_list': cmd_task_list,
    'task_reset': cmd_task_reset,
    'task_timeout': cmd_task_timeout,
    'health_check': cmd_health_check,
    'validate_data': cmd_validate_data,
    'check_chapter': cmd_check_chapter,
    'add_market_report': cmd_add_market_report,
    'market_reports': cmd_market_reports,
    'create_outline': cmd_create_outline,
    'outlines': cmd_outlines,
    'update_outline': cmd_update_outline,
    'delete_outline': cmd_delete_outline,
    # 问题模式管理
    'anti_patterns': cmd_anti_patterns,
    'context_rules': cmd_context_rules,
    'add_anti_pattern': cmd_add_anti_pattern,
    'update_anti_pattern': cmd_update_anti_pattern,
    'record_pattern_hit': cmd_record_pattern_hit,
    'pattern_stats': cmd_pattern_stats,
    # 上下文规则和最佳实践
    'add_context_rule': cmd_add_context_rule,
    'add_best_practice': cmd_add_best_practice,
    'best_practices': cmd_best_practices,
    'extract_best_practices': cmd_extract_best_practices,
    'batch_extract_practices': cmd_batch_extract_practices,
    'promote_pattern': cmd_promote_pattern,
    'learned_patterns': cmd_learned_patterns,
    # Agent 消息队列
    'send_message': cmd_send_message,
    'get_messages': cmd_get_messages,
    'resolve_message': cmd_resolve_message,
    # 版本管理
    'list_versions': cmd_list_versions,
    'get_version': cmd_get_version,
    'rollback_version': cmd_rollback_version,
    # 重试计数
    'increment_retry': cmd_increment_retry,
    # 上下文构建
    'build_context': cmd_build_context,
    # 健康报告
    'health_report': cmd_health_report,
}

def run(commands, help_text=""):
    """通用入口：用给定的命令子集运行

    增强参数校验和错误处理：
    - 捕获所有异常并返回友好错误信息
    - 参数类型错误时给出明确提示
    - 数据库错误时给出修复建议
    """
    if len(sys.argv) < 2:
        print(help_text or "用法: db.py <command> [args...]")
        return
    cmd = sys.argv[1]
    args = sys.argv[2:]
    if cmd in commands:
        try:
            commands[cmd](args)
        except sqlite3.Error as e:
            # 数据库错误
            error_msg = str(e)
            if "no such table" in error_msg.lower():
                suggestion = "数据库表不存在，请运行初始化脚本：sqlite3 shared/data/novel_factory.db < shared/data/init_db.sql"
            elif "database is locked" in error_msg.lower():
                suggestion = "数据库被锁定，请关闭其他进程或等待"
            elif "UNIQUE constraint" in error_msg:
                suggestion = "记录已存在，请检查是否有重复"
            else:
                suggestion = f"数据库错误: {error_msg}"
            print(json.dumps({
                "success": False,
                "error": "database_error",
                "message": error_msg,
                "suggestion": suggestion
            }, ensure_ascii=False, indent=2))
        except ValueError as e:
            # 参数类型错误
            print(json.dumps({
                "success": False,
                "error": "invalid_parameter",
                "message": str(e),
                "suggestion": "请检查参数类型是否正确（如：数字参数不要传字符串）"
            }, ensure_ascii=False, indent=2))
        except json.JSONDecodeError as e:
            # JSON 解析错误
            print(json.dumps({
                "success": False,
                "error": "invalid_json",
                "message": str(e),
                "suggestion": "JSON 参数格式错误，请检查引号和括号是否匹配"
            }, ensure_ascii=False, indent=2))
        except FileNotFoundError as e:
            # 文件不存在
            print(json.dumps({
                "success": False,
                "error": "file_not_found",
                "message": str(e),
                "suggestion": "指定的文件不存在，请检查路径"
            }, ensure_ascii=False, indent=2))
        except Exception as e:
            # 其他错误
            import traceback
            error_detail = traceback.format_exc()
            print(json.dumps({
                "success": False,
                "error": type(e).__name__,
                "message": str(e),
                "suggestion": "请检查命令参数是否正确"
            }, ensure_ascii=False, indent=2))
            # 调试模式下可以打印完整堆栈
            if os.environ.get('DEBUG'):
                traceback.print_exc()
    else:
        print(json.dumps({
            "success": False,
            "error": "unknown_command",
            "message": f"未知命令: {cmd}",
            "available_commands": list(commands.keys())
        }, ensure_ascii=False, indent=2))
