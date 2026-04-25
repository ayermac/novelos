#!/usr/bin/env python3
"""
导出已发布章节到 Markdown 文件

注意：此文件导入共享的 db_common 模块
数据库位置：shared/data/novel_factory.db

用法:
  python export_chapters.py <project_id>              # 导出指定项目所有已发布章节
  python export_chapters.py <project_id> <chapter>    # 导出指定项目的单个章节
  python export_chapters.py --all                     # 导出所有项目
  python export_chapters.py --list                    # 列出所有可导出的章节
"""

import os
import sys
from datetime import datetime

# 添加共享工具目录到路径
_shared_tools = os.path.abspath(os.path.dirname(__file__))
if _shared_tools not in sys.path:
    sys.path.insert(0, _shared_tools)

from db_common import get_connection, row_to_dict

# 默认输出目录为执行命令的当前目录下的 export 文件夹
OUTPUT_DIR = os.path.join(os.getcwd(), "export")


def get_project_info(project_id):
    """获取项目信息"""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT * FROM projects WHERE project_id = ?",
        (project_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row)


def get_published_chapters(project_id, chapter_number=None):
    """获取已发布的章节"""
    conn = get_connection()

    if chapter_number:
        cursor = conn.execute("""
            SELECT c.*, p.name as project_name
            FROM chapters c
            JOIN projects p ON c.project_id = p.project_id
            WHERE c.project_id = ? AND c.chapter_number = ? AND c.status = 'published'
        """, (project_id, chapter_number))
    else:
        cursor = conn.execute("""
            SELECT c.*, p.name as project_name
            FROM chapters c
            JOIN projects p ON c.project_id = p.project_id
            WHERE c.project_id = ? AND c.status = 'published'
            ORDER BY c.chapter_number
        """, (project_id,))

    chapters = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return chapters


def get_all_published_chapters():
    """获取所有已发布的章节"""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT c.*, p.name as project_name
        FROM chapters c
        JOIN projects p ON c.project_id = p.project_id
        WHERE c.status = 'published'
        ORDER BY c.project_id, c.chapter_number
    """)
    chapters = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return chapters


def list_exportable_chapters():
    """列出可导出的章节"""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT
            c.project_id,
            p.name as project_name,
            COUNT(*) as chapter_count,
            SUM(c.word_count) as total_words
        FROM chapters c
        JOIN projects p ON c.project_id = p.project_id
        WHERE c.status = 'published'
        GROUP BY c.project_id
        ORDER BY c.project_id
    """)

    print("\n📋 可导出的已发布章节：")
    print("-" * 60)
    print(f"{'项目ID':<30} {'项目名':<20} {'章节数':<8} {'字数':<10}")
    print("-" * 60)

    total_chapters = 0
    total_words = 0

    for row in cursor.fetchall():
        row = row_to_dict(row)
        print(f"{row['project_id']:<30} {row['project_name']:<20} {row['chapter_count']:<8} {row['total_words']:<10,}")
        total_chapters += row['chapter_count']
        total_words += row['total_words'] or 0

    print("-" * 60)
    print(f"{'合计':<30} {'':<20} {total_chapters:<8} {total_words:<10,}")
    print()

    conn.close()


def export_chapter_to_md(chapter, project_info, output_dir):
    """将单个章节导出为 Markdown"""
    # 创建项目目录
    project_dir = os.path.join(output_dir, chapter['project_id'])
    os.makedirs(project_dir, exist_ok=True)

    # 生成文件名
    filename = f"第{chapter['chapter_number']}章_{chapter['title'] or '未命名'}.md"
    # 清理文件名中的非法字符
    filename = filename.replace('/', '-').replace('\\', '-').replace(':', '-')
    filepath = os.path.join(project_dir, filename)

    # 生成 Markdown 内容
    md_content = f"""---
项目: {chapter['project_name']}
项目ID: {chapter['project_id']}
章节: 第{chapter['chapter_number']}章
标题: {chapter['title'] or '未命名'}
字数: {chapter['word_count']}
状态: 已发布
发布时间: {chapter['published_at'] or '未知'}
导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
---

# 第{chapter['chapter_number']}章 {chapter['title'] or '未命名'}

{chapter['content'] or ''}
"""

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(md_content)

    return filepath


def export_project(project_id, output_dir):
    """导出项目的所有已发布章节"""
    project_info = get_project_info(project_id)
    if not project_info:
        print(f"❌ 项目 {project_id} 不存在")
        return 0

    chapters = get_published_chapters(project_id)
    if not chapters:
        print(f"❌ 项目 {project_id} 没有已发布的章节")
        return 0

    print(f"\n📚 导出项目: {project_info['name']}")
    print(f"   已发布章节: {len(chapters)} 章")
    print()

    exported = 0
    for chapter in chapters:
        filepath = export_chapter_to_md(chapter, project_info, output_dir)
        print(f"   ✅ 第{chapter['chapter_number']}章: {filepath}")
        exported += 1

    return exported


def export_single_chapter(project_id, chapter_number, output_dir):
    """导出单个章节"""
    project_info = get_project_info(project_id)
    if not project_info:
        print(f"❌ 项目 {project_id} 不存在")
        return 0

    chapters = get_published_chapters(project_id, chapter_number)
    if not chapters:
        print(f"❌ 章节 {chapter_number} 不存在或未发布")
        return 0

    chapter = chapters[0]
    filepath = export_chapter_to_md(chapter, project_info, output_dir)
    print(f"✅ 已导出: {filepath}")
    return 1


def export_all(output_dir):
    """导出所有已发布章节"""
    chapters = get_all_published_chapters()
    if not chapters:
        print("❌ 没有已发布的章节")
        return 0

    # 按项目分组
    by_project = {}
    for chapter in chapters:
        pid = chapter['project_id']
        if pid not in by_project:
            by_project[pid] = []
        by_project[pid].append(chapter)

    print(f"\n📚 导出所有已发布章节")
    print(f"   项目数: {len(by_project)}")
    print(f"   总章节: {len(chapters)}")
    print()

    exported = 0
    for project_id, project_chapters in by_project.items():
        project_info = get_project_info(project_id)
        for chapter in project_chapters:
            filepath = export_chapter_to_md(chapter, project_info, output_dir)
            print(f"   ✅ {project_info['name']} - 第{chapter['chapter_number']}章")
            exported += 1

    return exported


def print_help():
    help_text = """
导出已发布章节到 Markdown 文件 v2.0

用法:
  python export_chapters.py <project_id>              导出项目所有已发布章节
  python export_chapters.py <project_id> <chapter>    导出指定章节
  python export_chapters.py --all                     导出所有项目
  python export_chapters.py --list                    列出可导出的章节
  python export_chapters.py --help                    显示帮助

示例:
  # 列出可导出的章节
  python export_chapters.py --list

  # 导出单个项目
  python export_chapters.py interstellar_farming_wasteland

  # 导出单个章节
  python export_chapters.py interstellar_farming_wasteland 1

  # 导出所有
  python export_chapters.py --all

输出目录: ./export/ (当前目录下)
"""
    print(help_text)


def main():
    if len(sys.argv) < 2:
        print_help()
        return

    arg = sys.argv[1]

    if arg in ('--help', '-h', 'help'):
        print_help()
    elif arg == '--list':
        list_exportable_chapters()
    elif arg == '--all':
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        exported = export_all(OUTPUT_DIR)
        print(f"\n✅ 完成！共导出 {exported} 章")
        print(f"📁 输出目录: {OUTPUT_DIR}")
    else:
        project_id = arg
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        if len(sys.argv) > 2:
            # 导出单个章节
            chapter_number = int(sys.argv[2])
            exported = export_single_chapter(project_id, chapter_number, OUTPUT_DIR)
        else:
            # 导出整个项目
            exported = export_project(project_id, OUTPUT_DIR)

        if exported > 0:
            print(f"\n✅ 完成！共导出 {exported} 章")
            print(f"📁 输出目录: {OUTPUT_DIR}/{project_id}/")


if __name__ == "__main__":
    main()
