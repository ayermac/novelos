#!/usr/bin/env python3
"""
调度器一致性检查脚本

检查章节状态一致性，返回调度决策。
使用方式：python consistency_check.py <project> <chapter_number>
"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

# 添加共享工具目录到路径
# 脚本在 dispatcher/workspace/skills/dispatcher/scripts/ 下
# db_common.py 在 agents/shared/tools/ 下，需要向上 6 级
_shared_tools = Path(__file__).parent.parent.parent.parent.parent.parent / "shared" / "tools"
sys.path.insert(0, str(_shared_tools))

from db_common import get_connection, row_to_dict

# 熔断阈值
MAX_REVISE_RETRIES = 3
TASK_TIMEOUT_MINUTES = 30


def query_task_status(project: str, chapter_number: int = None, status: str = None):
    """
    查询任务状态

    Args:
        project: 项目ID
        chapter_number: 章节号（可选）
        status: 任务状态（可选）

    Returns:
        任务列表
    """
    conn = get_connection()
    try:
        if chapter_number is not None and status:
            cursor = conn.execute(
                "SELECT * FROM task_status WHERE project_id=? AND chapter_number=? AND status=? ORDER BY created_at DESC",
                (project, chapter_number, status)
            )
        elif chapter_number is not None:
            # 只按章节过滤
            cursor = conn.execute(
                "SELECT * FROM task_status WHERE project_id=? AND chapter_number=? ORDER BY created_at DESC",
                (project, chapter_number)
            )
        elif status:
            cursor = conn.execute(
                "SELECT * FROM task_status WHERE project_id=? AND status=? ORDER BY created_at DESC",
                (project, status)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM task_status WHERE project_id=? ORDER BY created_at DESC",
                (project,)
            )
        tasks = [row_to_dict(row) for row in cursor.fetchall()]
        return tasks
    finally:
        conn.close()


def get_chapter(project: str, chapter_number: int):
    """
    获取章节数据

    Args:
        project: 项目ID
        chapter_number: 章节号

    Returns:
        章节数据字典或 None
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM chapters WHERE project_id=? AND chapter_number=?",
            (project, chapter_number)
        )
        chapter = row_to_dict(cursor.fetchone())
        return chapter
    finally:
        conn.close()


def check_consistency(project: str, chapter_number: int) -> dict:
    """
    检查章节状态一致性，返回决策

    Returns:
        {
            'action': 'trigger' | 'retry' | 'skip' | 'timeout' | 'abandon',
            'reason': str,
            'task_id': str | None  # 仅 timeout 时需要
        }
    """
    # 先检查章节当前状态
    chapter = get_chapter(project, chapter_number)
    if not chapter:
        return {'action': 'trigger', 'reason': '章节不存在，首次创建'}
    
    # 已发布的章节不需要调度
    if chapter['status'] == 'published':
        return {'action': 'skip', 'reason': f"第 {chapter_number} 章已发布，无需调度"}
    
    # 获取该章节的所有任务记录
    tasks = query_task_status(project, chapter_number)
    
    # 【熔断机制】防死循环
    # 如果同一章被质检退回 (revise 任务) 超过阈值，说明执笔 Agent 陷入逻辑死角
    # 只检查未完成章节的熔断
    revise_tasks = [t for t in tasks if t['task_type'] == 'revise']
    if len(revise_tasks) >= MAX_REVISE_RETRIES:
        return {
            'action': 'abandon',
            'reason': f"第 {chapter_number} 章已被质检退回 {len(revise_tasks)} 次，触发防死循环熔断，需人类介入修改。"
        }

    # 情况 1: 没有任何任务记录
    if not tasks:
        return {'action': 'trigger', 'reason': '无任务记录，首次触发'}

    # 情况 2: 有 running 任务
    running_tasks = [t for t in tasks if t['status'] == 'running']
    if running_tasks:
        for task in running_tasks:
            started_at = datetime.fromisoformat(task['started_at'])
            duration = datetime.now() - started_at
            if duration > timedelta(minutes=TASK_TIMEOUT_MINUTES):
                return {
                    'action': 'timeout',
                    'reason': f"任务运行超时 ({duration.total_seconds()/60:.1f}分钟)",
                    'task_id': task['id']
                }
        return {'action': 'skip', 'reason': '前置任务正在执行中，跳过本轮调度'}

    # 情况 3: 有 failed 任务
    failed_tasks = [t for t in tasks if t['status'] == 'failed']
    if failed_tasks:
        last_failed = failed_tasks[-1]
        retry_count = last_failed.get('retry_count', 0)
        if retry_count < 3:
            return {'action': 'retry', 'reason': f"任务失败，第 {retry_count + 1} 次重试"}
        else:
            return {'action': 'abandon', 'reason': "任务底层错误重试 3 次均失败，需人工干预"}

    # 情况 4: 只有 completed 任务（检查状态对齐）
    return {'action': 'trigger', 'reason': '前置节点已完成，触发下一节点'}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python consistency_check.py <project> <chapter_number>")
        sys.exit(1)

    project = sys.argv[1]
    chapter_number = int(sys.argv[2])

    result = check_consistency(project, chapter_number)
    print(json.dumps(result, ensure_ascii=False, indent=2))
