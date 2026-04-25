#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
星探 (Scout) - 市场分析工具

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
    'add_market_report': cmd_add_market_report,
    'market_reports': cmd_market_reports,
    'stats': cmd_stats,
    'chapters': cmd_chapters,
    'projects': cmd_projects,
    'current_project': cmd_current_project,
}

HELP = """用法: db.py <command> [args...]

星探可用命令:
  add_market_report ...        - 添加市场报告
  market_reports [count]        - 市场报告列表
  stats <project>              - 项目统计
  chapters <project>           - 列出章节
  projects                     - 列出所有项目
  current_project              - 获取当前项目
"""

if __name__ == "__main__":
    run(COMMANDS, HELP)
