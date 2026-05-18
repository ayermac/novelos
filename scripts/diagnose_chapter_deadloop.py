#!/usr/bin/env python3
"""
诊断章节死循环脚本（v6.6.0）

用法:
    python scripts/diagnose_chapter_deadloop.py --db-path xxx.db --project-id demo --chapter 2
"""

from __future__ import annotations

import argparse
import json
import sqlite3


def _short_json_list(value: str | None, limit: int = 5) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return [str(value)[:160]]
    if not isinstance(parsed, list):
        return [str(parsed)[:160]]
    return [str(item)[:160] for item in parsed[:limit]]


def diagnose(db_path: str, project_id: str, chapter_number: int):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    print(f"=== 章节死循环诊断 ===")
    print(f"项目: {project_id}  章节: {chapter_number}")
    print()

    # 当前状态
    cur = conn.execute(
        "SELECT status, word_count, updated_at FROM chapters WHERE project_id=? AND chapter_number=?",
        (project_id, chapter_number)
    )
    row = cur.fetchone()
    if row:
        print(f"当前状态: {row['status']}")
        print(f"当前字数: {row['word_count']}")
    else:
        print("章节不存在")
        return

    # 版本数量
    cur = conn.execute(
        "SELECT COUNT(*) as cnt FROM chapter_versions WHERE project_id=? AND chapter=?",
        (project_id, chapter_number),
    )
    version_count = cur.fetchone()["cnt"]
    print(f"历史版本数: {version_count}")

    cur = conn.execute(
        "SELECT COUNT(*) as cnt FROM workflow_runs "
        "WHERE project_id=? AND chapter_number=? AND status='failed'",
        (project_id, chapter_number),
    )
    failed_count = cur.fetchone()["cnt"]
    print(f"失败工作流数: {failed_count}")

    cur = conn.execute(
        "SELECT COUNT(*) as cnt FROM task_status "
        "WHERE project_id=? AND chapter_number=? AND task_type='reset'",
        (project_id, chapter_number),
    )
    reset_count = cur.fetchone()["cnt"]
    print(f"人工 reset 数: {reset_count}")

    # 最近 review
    cur = conn.execute(
        "SELECT r.score, r.pass, r.revision_target, r.issues, r.suggestions, r.reviewed_at "
        "FROM reviews r JOIN chapters c ON c.id=r.chapter_id "
        "WHERE r.project_id=? AND c.chapter_number=? "
        "ORDER BY r.reviewed_at DESC LIMIT 1",
        (project_id, chapter_number),
    )
    review = cur.fetchone()
    if review:
        print(f"最新评分: {review['score']}")
        print(f"最新审核: {'通过' if review['pass'] else '退回'} → {review['revision_target']}")
        issues = _short_json_list(review["issues"])
        if issues:
            print("最近问题:")
            for issue in issues:
                print(f"  - {issue}")

    # 最佳候选
    cur = conn.execute(
        "SELECT id, version, word_count, created_by, created_at "
        "FROM chapter_versions WHERE project_id=? AND chapter=? "
        "AND word_count >= 100 ORDER BY word_count DESC, version DESC LIMIT 5",
        (project_id, chapter_number),
    )
    candidates = cur.fetchall()
    if candidates:
        print("\n候选历史版本:")
        for item in candidates:
            print(
                f"  - v{item['version']} #{item['id']} "
                f"{item['word_count']}字 by {item['created_by']} at {item['created_at']}"
            )

    print("\n疑似系统原因:")
    if version_count > 20:
        print("  - 版本数过高，可能存在返修循环")
    if failed_count > 5:
        print("  - 失败工作流过多，建议停止自动重跑")
    if reset_count > 2:
        print("  - 多次人工 reset 后仍失败，建议恢复最佳历史版本或调整章节指令")
    print("  - 建议使用 restore-best-version API 恢复历史最佳版本")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    args = parser.parse_args()

    diagnose(args.db_path, args.project_id, args.chapter)
