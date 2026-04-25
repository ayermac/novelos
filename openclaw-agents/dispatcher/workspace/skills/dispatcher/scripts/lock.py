#!/usr/bin/env python3
"""
调度锁管理脚本

防止 Cron 重叠执行，确保调度原子性。
"""

import os
import sys
import time
from pathlib import Path

LOCK_FILE = "/tmp/novel_factory_dispatcher.lock"


def acquire_lock() -> bool:
    """
    尝试获取调度锁

    使用 noclobber 确保原子性，即使两个 Cron 同时执行，只有一个能成功创建文件。

    Returns:
        True 如果成功获取锁，False 如果锁已被占用
    """
    try:
        # 使用 os.O_EXCL | os.O_CREAT 确保原子性
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def release_lock():
    """释放调度锁"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            print("调度锁已释放")
    except Exception as e:
        print(f"释放锁时出错: {e}")


def get_lock_info() -> dict:
    """
    获取锁信息

    Returns:
        {'locked': bool, 'pid': int | None, 'age_seconds': float | None}
    """
    if not os.path.exists(LOCK_FILE):
        return {'locked': False, 'pid': None, 'age_seconds': None}

    try:
        with open(LOCK_FILE, 'r') as f:
            pid = int(f.read().strip())

        stat = os.stat(LOCK_FILE)
        age = time.time() - stat.st_mtime

        return {'locked': True, 'pid': pid, 'age_seconds': age}
    except Exception:
        return {'locked': True, 'pid': None, 'age_seconds': None}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python lock.py <acquire|release|info>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "acquire":
        if acquire_lock():
            print("调度锁获取成功，开始调度流程")
            sys.exit(0)
        else:
            print("调度锁获取失败，另一调度正在进行，跳过本轮")
            sys.exit(1)

    elif command == "release":
        release_lock()

    elif command == "info":
        info = get_lock_info()
        print(f"Lock status: {info}")
