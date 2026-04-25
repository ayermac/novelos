#!/bin/bash
# 网文工厂数据恢复脚本
# 用法: ./restore.sh <backup_file>

set -e

DB_PATH="${DB_PATH:-$(dirname "$0")/../data/novel_factory.db}"
BACKUP_FILE="${1:-}"

if [ -z "$BACKUP_FILE" ]; then
    echo "用法: ./restore.sh <backup_file>"
    echo ""
    echo "可用备份:"
    ls -lh /backups/novel_factory/backup_*.tar.gz 2>/dev/null || echo "  无备份文件"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "错误: 备份文件不存在: $BACKUP_FILE"
    exit 1
fi

echo "=========================================="
echo "网文工厂数据恢复"
echo "=========================================="
echo "备份文件: $BACKUP_FILE"
echo "目标数据库: $DB_PATH"
echo ""

read -p "确认恢复? 这将覆盖当前数据 [y/N]: " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "已取消"
    exit 0
fi

# 解压备份
TEMP_DIR=$(mktemp -d)
echo "[1/3] 解压备份文件..."
tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"
echo "  ✅ 已解压到临时目录"

# 备份当前数据库
echo "[2/3] 备份当前数据库..."
CURRENT_BACKUP="${DB_PATH}.before_restore_$(date +%Y%m%d_%H%M%S)"
if [ -f "$DB_PATH" ]; then
    cp "$DB_PATH" "$CURRENT_BACKUP"
    echo "  ✅ 已备份到: $CURRENT_BACKUP"
fi

# 恢复数据库
echo "[3/3] 恢复数据库..."
DB_BACKUP=$(find "$TEMP_DIR" -name "novel_factory_*.db" | head -1)
if [ -z "$DB_BACKUP" ]; then
    echo "  ❌ 备份文件中没有数据库"
    exit 1
fi
cp "$DB_BACKUP" "$DB_PATH"
echo "  ✅ 已恢复数据库"

# 清理
rm -rf "$TEMP_DIR"

echo ""
echo "=========================================="
echo "恢复完成！"
echo "原数据库备份: $CURRENT_BACKUP"
echo "=========================================="
