#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移 chapter_state 数据到新格式

旧格式：
{
  "数值类": {"金钱": 100, "生命力": 75, "等级": "Lv1"},
  "持有物品": {"物品": 数量},
  "位置类": {"当前位置": "地点"},
  "伏笔类": {"已埋设": [], "已兑现": []},
  "任务状态": {"当前任务": "...", "倒计时": "..."},
  "特殊状态": {...}
}

新格式：
{
  "assets": {
    "credits": {"value": 100, "change": 0, "reason": null},
    "hp": {"value": 75, "change": 0, "reason": null},
    "items": {"破损个人终端": 1, ...}
  },
  "character_states": {
    "主角": {
      "location": "地点",
      "level": "Lv1",
      "status": "active"
    }
  },
  "active_plots": ["P001", ...],
  "resolved_plots": ["L001", ...],
  "hidden_info": {
    "任务": "...",
    "倒计时": "..."
  }
}
"""

import sys
import os
import json

# 添加共享工具目录
_shared_tools = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared', 'tools'))
if _shared_tools not in sys.path:
    sys.path.insert(0, _shared_tools)

from db_common import get_connection, row_to_dict

# 主角名映射（需要根据项目调整）
PROTAGONIST_MAP = {
    'novel_003': '陈渊',
    'novel_001': '林默',
    'novel_002': '林默',
    # 默认值
    'default': '主角'
}

# 字段映射：旧格式 → 新格式
FIELD_MAPPINGS = {
    '数值类': {
        '金钱': 'credits',
        '金钱/信用点': 'credits',
        '信用点': 'credits',
        '生命力': 'hp',
        '生命值': 'hp',
        'HP': 'hp',
        '经验': 'exp',
        '经验值': 'exp',
        'XP': 'exp',
        '等级': 'level',  # 归 character_states
    },
    '持有物品': 'items',  # 整体映射到 assets.items
}


def get_protagonist_name(project_id):
    """获取主角名"""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT name FROM characters WHERE project_id = ? AND role = 'protagonist' LIMIT 1",
        (project_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return row[0]
    
    # 从映射表获取
    return PROTAGONIST_MAP.get(project_id, PROTAGONIST_MAP['default'])


def migrate_state(old_state, project_id):
    """
    将旧格式状态卡迁移到新格式
    
    Args:
        old_state: 旧格式状态卡 (dict)
        project_id: 项目ID
        
    Returns:
        新格式状态卡 (dict)
    """
    if not old_state:
        return old_state
    
    # 如果已经是新格式，直接返回
    if 'assets' in old_state or 'character_states' in old_state:
        print("  [INFO] 已是新格式，跳过迁移")
        return old_state
    
    protagonist = get_protagonist_name(project_id)
    new_state = {
        'assets': {},
        'character_states': {},
        'active_plots': [],
        'resolved_plots': [],
        'hidden_info': {}
    }
    
    # 1. 迁移数值类 → assets
    old_values = old_state.get('数值类', {})
    for old_key, value in old_values.items():
        new_key = FIELD_MAPPINGS['数值类'].get(old_key)
        
        if new_key == 'level':
            # 等级归 character_states
            if protagonist not in new_state['character_states']:
                new_state['character_states'][protagonist] = {'location': '', 'status': 'active'}
            new_state['character_states'][protagonist]['level'] = value
        elif new_key:
            # 数值资产
            new_state['assets'][new_key] = {
                'value': value,
                'change': 0,
                'reason': None
            }
        else:
            # 未知字段，保留原样到 assets
            new_state['assets'][old_key] = {
                'value': value,
                'change': 0,
                'reason': None
            }
    
    # 2. 迁移持有物品 → assets.items
    old_items = old_state.get('持有物品', {})
    if old_items:
        new_state['assets']['items'] = old_items
    
    # 3. 迁移位置类 → character_states
    old_location = old_state.get('位置类', {}).get('当前位置', '')
    if old_location:
        if protagonist not in new_state['character_states']:
            new_state['character_states'][protagonist] = {'status': 'active'}
        new_state['character_states'][protagonist]['location'] = old_location
    
    # 4. 迁移伏笔类
    old_plots = old_state.get('伏笔类', {})
    new_state['active_plots'] = old_plots.get('已埋设', [])
    new_state['resolved_plots'] = old_plots.get('已兑现', [])
    
    # 5. 迁移任务状态 → hidden_info
    old_tasks = old_state.get('任务状态', {})
    for key, value in old_tasks.items():
        new_state['hidden_info'][key] = value
    
    # 6. 迁移特殊状态 → hidden_info
    old_special = old_state.get('特殊状态', {})
    for key, value in old_special.items():
        new_state['hidden_info'][key] = value
    
    # 7. 迁移其他未分类字段 → hidden_info
    for old_key, old_value in old_state.items():
        if old_key in ['数值类', '持有物品', '位置类', '伏笔类', '任务状态', '特殊状态']:
            continue
        # 未分类字段，保留到 hidden_info
        if isinstance(old_value, dict):
            for k, v in old_value.items():
                new_state['hidden_info'][k] = v
        else:
            new_state['hidden_info'][old_key] = old_value
    
    return new_state


def dry_run(project_id=None):
    """
    预览迁移结果，不写入数据库
    """
    conn = get_connection()
    
    if project_id:
        cursor = conn.execute(
            "SELECT project_id, chapter_number, state_data, summary FROM chapter_state WHERE project_id = ?",
            (project_id,)
        )
    else:
        cursor = conn.execute(
            "SELECT project_id, chapter_number, state_data, summary FROM chapter_state"
        )
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("没有需要迁移的数据")
        return
    
    print(f"找到 {len(rows)} 条状态卡数据\n")
    
    for row in rows:
        pid = row[0]
        chapter = row[1]
        old_state_str = row[2]
        summary = row[3]
        
        print(f"项目: {pid}, 章节: {chapter}")
        print(f"摘要: {summary}")
        
        try:
            old_state = json.loads(old_state_str)
        except json.JSONDecodeError:
            print("  [ERROR] JSON 解析失败，跳过")
            continue
        
        print(f"旧格式: {json.dumps(old_state, ensure_ascii=False, indent=2)[:200]}...")
        
        new_state = migrate_state(old_state, pid)
        print(f"新格式: {json.dumps(new_state, ensure_ascii=False, indent=2)[:200]}...")
        print()


def migrate(project_id=None, force=False):
    """
    执行迁移，写入数据库
    
    Args:
        project_id: 指定项目ID，None 表示迁移所有项目
        force: 强制覆盖已迁移的数据
    """
    conn = get_connection()
    
    if project_id:
        cursor = conn.execute(
            "SELECT project_id, chapter_number, state_data, summary FROM chapter_state WHERE project_id = ?",
            (project_id,)
        )
    else:
        cursor = conn.execute(
            "SELECT project_id, chapter_number, state_data, summary FROM chapter_state"
        )
    
    rows = cursor.fetchall()
    
    if not rows:
        print("没有需要迁移的数据")
        conn.close()
        return
    
    print(f"找到 {len(rows)} 条状态卡数据")
    
    migrated = 0
    skipped = 0
    errors = 0
    
    for row in rows:
        pid = row[0]
        chapter = row[1]
        old_state_str = row[2]
        summary = row[3]
        
        try:
            old_state = json.loads(old_state_str)
        except json.JSONDecodeError as e:
            print(f"[ERROR] 项目 {pid} 章节 {chapter} JSON 解析失败: {e}")
            errors += 1
            continue
        
        # 检查是否已是新格式
        if not force and ('assets' in old_state or 'character_states' in old_state):
            print(f"[SKIP] 项目 {pid} 章节 {chapter} 已是新格式")
            skipped += 1
            continue
        
        # 迁移
        new_state = migrate_state(old_state, pid)
        new_state_str = json.dumps(new_state, ensure_ascii=False)
        
        # 更新数据库
        conn.execute(
            "UPDATE chapter_state SET state_data = ? WHERE project_id = ? AND chapter_number = ?",
            (new_state_str, pid, chapter)
        )
        
        print(f"[OK] 项目 {pid} 章节 {chapter} 迁移完成")
        migrated += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n迁移完成: 成功 {migrated}, 跳过 {skipped}, 错误 {errors}")


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 tools/migrate_state.py --dry-run [project_id]  # 预览迁移结果")
        print("  python3 tools/migrate_state.py --migrate [project_id]  # 执行迁移")
        print("  python3 tools/migrate_state.py --force [project_id]    # 强制覆盖已迁移数据")
        sys.exit(1)
    
    command = sys.argv[1]
    project_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    if command == '--dry-run':
        dry_run(project_id)
    elif command == '--migrate':
        migrate(project_id, force=False)
    elif command == '--force':
        migrate(project_id, force=True)
    else:
        print(f"未知命令: {command}")
        print("可用命令: --dry-run, --migrate, --force")
        sys.exit(1)


if __name__ == "__main__":
    main()
