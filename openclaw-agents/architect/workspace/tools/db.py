#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
架构师 (Architect) - 系统诊断工具（只读）

注意：此文件导入共享的 db_common 模块
路径：../../shared/tools/db_common.py

架构师职责：
- 诊断工厂运行问题
- 检查数据健康状态
- 分析问题模式统计
- 提供优化建议

架构师不参与工厂工作流程，只在用户请求时进行诊断。
"""
import sys, os

# 添加共享工具目录到路径
_shared_tools = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared', 'tools'))
if _shared_tools not in sys.path:
    sys.path.insert(0, _shared_tools)

from db_common import *

COMMANDS = {
    # 项目信息
    'projects': cmd_projects,
    'current_project': cmd_current_project,
    # 章节与内容
    'chapters': cmd_chapters,
    # 设定数据
    'characters': cmd_characters,
    'pending_plots': cmd_pending_plots,
    # 质检报告
    'reviews': cmd_reviews,
    # 统计
    'stats': cmd_stats,
    # 健康检查
    'health_check': cmd_health_check,
    # 问题模式
    'anti_patterns': cmd_anti_patterns,
    'pattern_stats': cmd_pattern_stats,
    'context_rules': cmd_context_rules,
}

HELP = """用法: db.py <command> [args...]

架构师可用命令（只读诊断）:
  项目信息:
    projects                    - 列出所有项目
    current_project             - 获取当前项目
    stats <project>             - 项目统计

  章节与内容:
    chapters <project>          - 列出章节

  设定数据:
    characters <project>        - 查询角色
    pending_plots <project>     - 待兑现伏笔

  质检报告:
    reviews <project>           - 质检报告列表

  问题分析:
    anti_patterns [--all] [--enabled] - 问题模式库
    pattern_stats [--top N] [--category <cat>] - 问题模式统计
    context_rules               - 上下文规则

  系统健康:
    health_check [project]      - 健康检查
"""

if __name__ == "__main__":
    run(COMMANDS, HELP)
