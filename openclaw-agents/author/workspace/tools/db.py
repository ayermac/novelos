#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
执笔 (Author) - 章节创作工具

注意：此文件导入共享的 db_common 模块
路径：../../shared/tools/db_common.py

权限说明：
- Author 只能读取规划数据（伏笔、角色、世界观），不能修改
- 伏笔管理（add_plot/resolve_plot）由 Planner 负责
- 新角色添加需由 Planner 规划，Author 只能查询
"""
import sys, os

# 添加共享工具目录到路径
_shared_tools = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared', 'tools'))
if _shared_tools not in sys.path:
    sys.path.insert(0, _shared_tools)

from db_common import *

COMMANDS = {
    'chapters': cmd_chapters,
    'next_chapter': cmd_next_chapter,
    'chapter_content': cmd_chapter_content,
    'save_draft': cmd_save_draft,
    'update_chapter': cmd_update_chapter,
    'instruction': cmd_instruction,
    'reviews': cmd_reviews,
    'characters': cmd_characters,
    'world_settings': cmd_world_settings,
    'pending_plots': cmd_pending_plots,
    'chapter_state': cmd_chapter_state,
    'current_project': cmd_current_project,
    'verify_plots': cmd_verify_plots,
    'check_chapter': cmd_check_chapter,
    'anti_patterns': cmd_anti_patterns,
    'best_practices': cmd_best_practices,
    'build_context': cmd_build_context,
    'task_complete': cmd_task_complete,
    'task_list': cmd_task_list,
}

HELP = """用法: db.py <command> [args...]

执笔可用命令（只读权限为主）:
  章节操作:
    chapters <project>           - 列出章节
    next_chapter [project]       - 下一章信息
    chapter_content <p> <n> <v>  - 读取章节内容
    save_draft <p> <n> --content|--file <path> - 保存草稿
    update_chapter <p> <n> <status> [words]    - 更新章节状态

  参考资料:
    instruction <p> <n>         - 读取写作指令
    characters <project>        - 查询角色（只读）
    world_settings <project>    - 查询世界观设定（只读）
    pending_plots <project>     - 待兑现伏笔（只读）
    chapter_state <p> <n>       - 读取上一章结束时数值状态

  质量自查:
    verify_plots <p> <n>        - 验证伏笔处理
    check_chapter <p> <n>       - 自查章节（禁用词、数值）
    anti_patterns [--all]       - 问题模式库（避坑指南）
    best_practices [category]   - 高分范例参考

  任务管理:
    current_project             - 获取当前项目
    task_complete <id> [true|false] - 标记任务完成/失败
    task_list <project> [status] [limit] - 列出任务

注意：
- 伏笔管理（add_plot/resolve_plot）由 Planner 负责
- 新角色添加由 Planner 规划
- Editor 通过 agent_messages 向 Planner 提出异议
"""

if __name__ == "__main__":
    run(COMMANDS, HELP)
