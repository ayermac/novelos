#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调度器 (Dispatcher) - 任务调度与状态监控

注意：此文件导入共享的 db_common 模块
路径：../../shared/tools/db_common.py
"""
import sys, os

# 添加共享工具目录到路径
_shared_tools = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared', 'tools'))
if _shared_tools not in sys.path:
    sys.path.insert(0, _shared_tools)

from db_common import *

COMMANDS = {
    'health_check': cmd_health_check,
    'projects': cmd_projects,
    'current_project': cmd_current_project,
    'chapters': cmd_chapters,
    # ❌ 移除 add_chapter - 由 Planner 创建，Dispatcher 禁止调用
    'next_chapter': cmd_next_chapter,
    'reviews': cmd_reviews,
    'sync_plots': cmd_sync_plots,
    'instruction': cmd_instruction,
    'task_start': cmd_task_start,
    'task_complete': cmd_task_complete,
    'task_list': cmd_task_list,
    'task_reset': cmd_task_reset,
    'task_timeout': cmd_task_timeout,
    'stats': cmd_stats,
    'pending_plots': cmd_pending_plots,
    # Agent 消息队列
    'send_message': cmd_send_message,
    'get_messages': cmd_get_messages,
    'resolve_message': cmd_resolve_message,
}

HELP = """用法: db.py <command> [args...]

调度器可用命令:
  health_check [project]       - 健康检查
  projects                     - 列出所有项目
  current_project              - 获取当前项目
  chapters <project>           - 列出章节
  next_chapter [project]       - 下一章信息
  reviews <project>            - 质检报告列表
  sync_plots <project>         - 同步伏笔数据
  stats <project>              - 项目统计
  pending_plots <project>      - 待兑现伏笔
  instruction <p> <n>          - 读取写作指令
  task_start <p> <type> <n> <agent> - 任务开始
  task_complete <id> [success] - 任务完成
  task_list <p> [status] [limit] - 列出任务
  task_reset <id>              - 重置任务回 pending
  task_timeout <p> <minutes>   - 超时检查

Agent 消息队列:
  send_message <project> <from> <to> <type> <chapter> '<json>' [priority]
    - 发送异步消息
    - type: FLAG_ISSUE/ESCALATE/SUGGEST/NOTIFY
    - priority: normal/high/urgent (默认 normal)
    - chapter: 章节号，传 - 表示不关联
  get_messages <project> <agent> [status] [limit]
    - 获取待处理消息 (status: pending/processing/resolved/all)
  resolve_message <id> [result]
    - 标记消息为已处理

⚠️ 禁止命令（Dispatcher 无权调用）:
  add_chapter, create_instruction, save_draft, add_review
  这些命令由 Planner/Author/Editor 调用，Dispatcher 只负责调度
"""

if __name__ == "__main__":
    run(COMMANDS, HELP)
