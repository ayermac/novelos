#!/usr/bin/env python3
"""
清空项目数据脚本
用法: python tools/clean_project.py <project_id> [--delete-project]

注意：此文件导入共享的 db_common 模块
数据库位置：shared/data/novel_factory.db

参数:
  project_id      要清空的项目ID
  --delete-project 同时删除项目记录本身（可选）

示例:
  # 清空 novel_002 的所有数据，保留项目记录
  python clean_project.py novel_002

  # 清空 novel_002 的所有数据，包括项目记录
  python clean_project.py novel_002 --delete-project
"""

import sys
import os

# 添加共享工具目录到路径
_shared_tools = os.path.abspath(os.path.dirname(__file__))
if _shared_tools not in sys.path:
    sys.path.insert(0, _shared_tools)

from db_common import get_connection, row_to_dict


def clean_project(project_id, delete_project=False):
    """清空指定项目的所有数据"""
    conn = get_connection()
    cursor = conn.cursor()

    # 检查项目是否存在
    cursor.execute("SELECT name FROM projects WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    if not row:
        print(f"❌ 项目 {project_id} 不存在")
        conn.close()
        return False

    project_name = row[0]

    # 禁用外键约束以便删除
    conn.execute("PRAGMA foreign_keys = OFF")

    # 统计各表删除数量
    stats = {}

    # 按依赖顺序删除（先删除依赖表）
    # 注意：需要包含所有高级功能表
    tables = [
        ('reviews', "DELETE FROM reviews WHERE project_id = ?"),
        ('chapter_plots', "DELETE FROM chapter_plots WHERE project_id = ?"),
        ('chapter_versions', "DELETE FROM chapter_versions WHERE project_id = ?"),
        ('chapter_state', "DELETE FROM chapter_state WHERE project_id = ?"),
        ('state_history', "DELETE FROM state_history WHERE project_id = ?"),
        ('chapters', "DELETE FROM chapters WHERE project_id = ?"),
        ('instructions', "DELETE FROM instructions WHERE project_id = ?"),
        ('plot_holes', "DELETE FROM plot_holes WHERE project_id = ?"),
        ('outlines', "DELETE FROM outlines WHERE project_id = ?"),
        ('factions', "DELETE FROM factions WHERE project_id = ?"),
        ('characters', "DELETE FROM characters WHERE project_id = ?"),
        ('world_settings', "DELETE FROM world_settings WHERE project_id = ?"),
        ('task_status', "DELETE FROM task_status WHERE project_id = ?"),
        ('agent_messages', "DELETE FROM agent_messages WHERE chapter_number IN (SELECT chapter_number FROM chapters WHERE project_id = ?)"),
        ('learned_patterns', "DELETE FROM learned_patterns WHERE project_id = ?"),
        ('best_practices', "DELETE FROM best_practices WHERE project_id = ?"),
    ]

    print(f"\n🗑️  清空项目: {project_id} ({project_name})")
    print("=" * 50)

    for table, sql in tables:
        cursor.execute("SELECT COUNT(*) FROM {}".format(table))
        before = cursor.fetchone()[0]
        try:
            if 'agent_messages' in sql:
                cursor.execute(sql, (project_id,))
            else:
                cursor.execute(sql, (project_id,))
            deleted = cursor.rowcount
            if deleted > 0:
                stats[table] = deleted
                print(f"  ✓ {table}: 删除 {deleted} 条记录")
        except Exception as e:
            # 表可能不存在或没有相关数据
            pass

    # 是否删除项目本身
    if delete_project:
        cursor.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
        stats['projects'] = 1
        print(f"  ✓ projects: 删除项目记录")
    else:
        stats['projects'] = 0
        print(f"  ○ projects: 保留项目记录")

    conn.commit()
    conn.close()

    print("=" * 50)
    total = sum(stats.values())
    print(f"✅ 完成！共删除 {total} 条记录")

    if not delete_project:
        print(f"💡 提示: 项目 {project_id} 记录已保留，可重新添加数据")

    return True


def list_projects():
    """列出所有项目"""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT p.project_id, p.name, p.genre, p.is_current,
               (SELECT COUNT(*) FROM chapters WHERE project_id = p.project_id) as chapters,
               (SELECT COUNT(*) FROM plot_holes WHERE project_id = p.project_id) as plots
        FROM projects p
        ORDER BY p.created_at DESC
    """)
    projects = cursor.fetchall()
    conn.close()

    if not projects:
        print("📋 当前没有项目")
        return

    print("\n📋 项目列表:")
    print("-" * 70)
    print(f"{'项目ID':<15} {'名称':<15} {'章节':<8} {'伏笔':<8} {'当前':<6}")
    print("-" * 70)
    for p in projects:
        current = "✓" if p[3] else ""
        print(f"{p[0]:<15} {p[1]:<15} {p[4]:<8} {p[5]:<8} {current:<6}")
    print("-" * 70)


def print_help():
    """打印帮助信息"""
    help_text = """
清空项目数据脚本 v2.0
用法: python clean_project.py <project_id> [--delete-project]

参数:
  project_id        要清空的项目ID
  --delete-project  同时删除项目记录本身（可选）
  --list            列出所有项目

示例:
  # 查看所有项目
  python clean_project.py --list

  # 清空 novel_002 的所有数据，保留项目记录
  python clean_project.py novel_002

  # 清空 novel_002 的所有数据，包括项目记录
  python clean_project.py novel_002 --delete-project

删除范围:
  - reviews (质检记录)
  - chapter_plots (章节-伏笔关联)
  - chapter_versions (版本历史)
  - chapter_state (状态卡)
  - state_history (状态历史)
  - chapters (章节)
  - instructions (写作指令)
  - plot_holes (伏笔)
  - outlines (大纲)
  - factions (势力)
  - characters (角色)
  - world_settings (世界观设定)
  - task_status (任务状态)
  - agent_messages (Agent消息)
  - learned_patterns (学习模式)
  - best_practices (最佳实践)
  - projects (项目记录，仅当指定 --delete-project)
"""
    print(help_text)


def main():
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    arg = sys.argv[1]

    if arg in ('-h', '--help', 'help'):
        print_help()
    elif arg == '--list':
        list_projects()
    else:
        project_id = arg
        delete_project = '--delete-project' in sys.argv
        clean_project(project_id, delete_project)


if __name__ == "__main__":
    main()
