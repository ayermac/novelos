#!/bin/bash
# 网文工厂数据备份脚本
# 用法: ./backup.sh [project_id]

set -e

# 配置
BACKUP_DIR="${BACKUP_DIR:-/backups/novel_factory}"
DB_PATH="${DB_PATH:-$(dirname "$0")/../data/novel_factory.db}"
DATE=$(date +%Y%m%d_%H%M%S)
PROJECT_ID="${1:-}"

# 创建备份目录
mkdir -p "$BACKUP_DIR"

echo "=========================================="
echo "网文工厂数据备份"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 1. 完整数据库备份
echo "[1/4] 备份完整数据库..."
BACKUP_FILE="${BACKUP_DIR}/novel_factory_${DATE}.db"
sqlite3 "$DB_PATH" ".backup '${BACKUP_FILE}'"
echo "  ✅ 已保存: $BACKUP_FILE"

# 2. 导出关键数据为 JSON（用于版本控制）
echo "[2/4] 导出关键数据..."
EXPORT_FILE="${BACKUP_DIR}/export_${DATE}.json"
python3 -c "
import sqlite3
import json
from pathlib import Path

db_path = '${DB_PATH}'
export_file = '${EXPORT_FILE}'
project_id = '${PROJECT_ID}'

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

data = {
    'timestamp': '${DATE}',
    'project_id': project_id if project_id else 'all'
}

# 导出项目
if project_id:
    projects = [dict(r) for r in conn.execute('SELECT * FROM projects WHERE project_id=?', (project_id,)).fetchall()]
else:
    projects = [dict(r) for r in conn.execute('SELECT * FROM projects').fetchall()]
data['projects'] = projects

# 导出章节
if project_id:
    chapters = [dict(r) for r in conn.execute('SELECT * FROM chapters WHERE project_id=?', (project_id,)).fetchall()]
else:
    chapters = [dict(r) for r in conn.execute('SELECT * FROM chapters').fetchall()]
data['chapters'] = chapters

# 导出角色
if project_id:
    characters = [dict(r) for r in conn.execute('SELECT * FROM characters WHERE project_id=?', (project_id,)).fetchall()]
else:
    characters = [dict(r) for r in conn.execute('SELECT * FROM characters').fetchall()]
data['characters'] = characters

# 导出伏笔
if project_id:
    plots = [dict(r) for r in conn.execute('SELECT * FROM plot_holes WHERE project_id=?', (project_id,)).fetchall()]
else:
    plots = [dict(r) for r in conn.execute('SELECT * FROM plot_holes').fetchall()]
data['plot_holes'] = plots

# 导出指令
if project_id:
    instructions = [dict(r) for r in conn.execute('SELECT * FROM instructions WHERE project_id=?', (project_id,)).fetchall()]
else:
    instructions = [dict(r) for r in conn.execute('SELECT * FROM instructions').fetchall()]
data['instructions'] = instructions

# 导出世界观
if project_id:
    world = [dict(r) for r in conn.execute('SELECT * FROM world_settings WHERE project_id=?', (project_id,)).fetchall()]
else:
    world = [dict(r) for r in conn.execute('SELECT * FROM world_settings').fetchall()]
data['world_settings'] = world

# 导出质检报告
if project_id:
    reviews = [dict(r) for r in conn.execute('SELECT * FROM reviews WHERE project_id=?', (project_id,)).fetchall()]
else:
    reviews = [dict(r) for r in conn.execute('SELECT * FROM reviews').fetchall()]
data['reviews'] = reviews

# 导出状态卡
if project_id:
    states = [dict(r) for r in conn.execute('SELECT * FROM chapter_state WHERE project_id=?', (project_id,)).fetchall()]
else:
    states = [dict(r) for r in conn.execute('SELECT * FROM chapter_state').fetchall()]
data['chapter_state'] = states

conn.close()

with open(export_file, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f'  已导出 {len(projects)} 个项目, {len(chapters)} 个章节, {len(characters)} 个角色')
"
echo "  ✅ 已保存: $EXPORT_FILE"

# 3. 压缩备份
echo "[3/4] 压缩备份文件..."
COMPRESSED_FILE="${BACKUP_DIR}/backup_${DATE}.tar.gz"
tar -czf "$COMPRESSED_FILE" -C "$BACKUP_DIR" "novel_factory_${DATE}.db" "export_${DATE}.json"
echo "  ✅ 已压缩: $COMPRESSED_FILE"

# 4. 清理旧备份（保留最近 7 天）
echo "[4/4] 清理旧备份..."
find "$BACKUP_DIR" -name "backup_*.tar.gz" -mtime +7 -delete
find "$BACKUP_DIR" -name "novel_factory_*.db" -mtime +7 -delete
find "$BACKUP_DIR" -name "export_*.json" -mtime +7 -delete
echo "  ✅ 已清理 7 天前的备份"

echo ""
echo "=========================================="
echo "备份完成！"
echo "压缩文件: $COMPRESSED_FILE"
echo "大小: $(du -h "$COMPRESSED_FILE" | cut -f1)"
echo "=========================================="
