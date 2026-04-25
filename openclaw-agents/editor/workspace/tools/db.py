#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
质检 (Editor) - 五层审校工具

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
    # 章节
    'chapters': cmd_chapters,
    'chapter_content': cmd_chapter_content,
    'update_chapter': cmd_update_chapter,
    # 质检
    'add_review': cmd_add_review,
    'reviews': cmd_reviews,
    'check_chapter': cmd_check_chapter,
    'verify_plots': cmd_verify_plots,
    # 参考信息
    'characters': cmd_characters,
    'instructions': cmd_instructions,
    'instruction': cmd_instruction,
    'pending_plots': cmd_pending_plots,
    'world_settings': cmd_world_settings,
    'factions': cmd_factions,
    'outlines': cmd_outlines,
    # 上下文组装（推荐）
    'build_context': cmd_build_context,
    # 问题模式
    'anti_patterns': cmd_anti_patterns,
    'context_rules': cmd_context_rules,
    'record_pattern_hit': cmd_record_pattern_hit,
    'add_context_rule': cmd_add_context_rule,
    'add_best_practice': cmd_add_best_practice,
    'best_practices': cmd_best_practices,
    'extract_best_practices': cmd_extract_best_practices,
    'batch_extract_practices': cmd_batch_extract_practices,
    'promote_pattern': cmd_promote_pattern,
    # 统计/项目
    'stats': cmd_stats,
    'projects': cmd_projects,
    'chapter_state': cmd_chapter_state,
    'current_project': cmd_current_project,
    # 任务管理
    'task_start': cmd_task_start,
    'task_complete': cmd_task_complete,
    'task_list': cmd_task_list,
    # Agent 消息队列（向 Planner 提异议）
    'send_message': cmd_send_message,
    'get_messages': cmd_get_messages,
    'resolve_message': cmd_resolve_message,
}

HELP = """用法: db.py <command> [args...]

质检可用命令:
  章节:
    chapters <project>           - 列出章节
    chapter_content <p> <n> <v>  - 读取章节内容
    update_chapter <p> <n> <status> [words] - 更新章节状态

  质检核心:
    add_review ...              - 添加质检报告
    reviews <project>           - 质检报告列表
    check_chapter <p> <n>       - 自动检查章节（禁用词、数值）
    verify_plots <p> <n> [--verbose] - 伏笔验证（强制！）

  参考信息:
    instructions <project> [s]  - 列出指令
    instruction <p> <n>         - 读取写作指令
    characters <project>        - 查询角色
    world_settings <project>    - 世界观设定
    factions <project>          - 势力关系
    outlines <project>          - 大纲
    pending_plots <project>     - 待兑现伏笔

  问题模式（学习与记录）:
    anti_patterns [--all] [--enabled] - 查看问题模式库
    context_rules               - 查看上下文规则
    record_pattern_hit <code> [project] [chapter] - 记录问题命中
    add_context_rule <rule> <category> <severity> - 添加上下文规则
    best_practices [category] [--project <p>] - 查看高分范例
    add_best_practice <p> <cat> "<practice>" [chapters] [score] [evidence] - 记录最佳实践
    extract_best_practices <p> <n> --score <s> - 从高分章节提取最佳实践
    batch_extract_practices <p> [--min-score 90] - 批量提取高分章节
    promote_pattern <id> [--severity medium] - 提升高频问题到 anti_patterns

  统计与任务:
    stats <project>             - 项目统计
    chapter_state <p> <n> [--set '<JSON>'] - 读写状态卡
    projects                    - 列出项目
    current_project             - 获取当前项目
    task_start/complete/list    - 任务管理

  消息队列（向 Planner 提异议）:
    send_message <project> <from> <to> <type> <chapter> '<json>' [priority]
      - type: FLAG_ISSUE/ESCALATE/SUGGEST/NOTIFY
      - priority: normal/high/urgent
      - chapter: 章节号，传 - 表示不关联
    get_messages <project> <agent> [status] [limit]
    resolve_message <id> [result]
"""

if __name__ == "__main__":
    run(COMMANDS, HELP)
