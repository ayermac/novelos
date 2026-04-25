#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
秘书 (Secretary) - 只读数据汇总

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
    'projects': cmd_projects,
    'current_project': cmd_current_project,
    'chapters': cmd_chapters,
    'stats': cmd_stats,
    'reviews': cmd_reviews,
    'market_reports': cmd_market_reports,
    'task_timeout': cmd_task_timeout,
    'health_check': cmd_health_check,
    'characters': cmd_characters,
    'pending_plots': cmd_pending_plots,
}

HELP = """用法: db.py <command> [args...]

秘书可用命令（只读）:
  projects                     - 列出所有项目
  current_project              - 获取当前项目
  chapters <project>           - 列出章节
  stats <project>              - 项目统计
  reviews <project>            - 质检报告列表
  market_reports [count]       - 市场报告列表
  pending_plots <project>      - 待兑现伏笔
  task_timeout <p> <minutes>   - 超时检查
  health_check [project]       - 健康检查
  characters <project>         - 查询角色
"""

if __name__ == "__main__":
    run(COMMANDS, HELP)
