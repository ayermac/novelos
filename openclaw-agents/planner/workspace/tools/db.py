#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
总编 (Planner) - 完全访问权限

注意：此文件导入共享的 db_common 模块
路径：../../shared/tools/db_common.py
"""
import sys, os

# 添加共享工具目录到路径
_shared_tools = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared', 'tools'))
if _shared_tools not in sys.path:
    sys.path.insert(0, _shared_tools)

from db_common import *

COMMANDS = dict(ALL_COMMANDS)
COMMANDS['build_context'] = cmd_build_context

HELP = """用法: db.py <command> [args...]

总编可用命令（完全访问）:
  项目管理:  projects / add_project / update_project / current_project / set_current_project
  世界观:    add_world_setting / update_world_setting / delete_world_setting / world_settings
  角色:      characters / add_character / update_character / delete_character
  势力:      factions / add_faction / update_faction / delete_faction
  大纲:      create_outline / update_outline / delete_outline / outlines
  章节:      chapters / add_chapter / next_chapter / update_chapter / chapter_content / save_draft / publish_chapter
  指令:      instruction / instructions / create_instruction / update_instruction
  伏笔:      add_plot / resolve_plot / pending_plots / sync_plots / verify_plots
  质检:      add_review / reviews / check_chapter
  状态:      chapter_state
  版本:      list_versions / get_version / rollback_version
  统计:      stats
  任务:      task_start / task_complete / task_reset / task_timeout / task_list / increment_retry
  问题模式:  anti_patterns / context_rules / record_pattern_hit / pattern_stats
  消息队列:  get_messages / resolve_message
  系统:      health_check / validate_data
  市场:      add_market_report / market_reports
"""

if __name__ == "__main__":
    run(COMMANDS, HELP)
