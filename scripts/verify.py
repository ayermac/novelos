#!/usr/bin/env python3
"""
分层验证入口脚本

降低每轮开发都跑全量测试的成本，支持按场景选择验证层级：
  smoke     - 快速后端关键回归
  v57       - v5.7 编辑/版本相关测试
  frontend  - 前端 typecheck + lint + vitest
  full      - 全量后端 + 前端（稳定基线/提交前闸门）
  release   - 发布预检 + 全量后端/前端/桌面 + release smoke
  durations - 查看最慢的 30 个 pytest 用例耗时

用法:
  python3 scripts/verify.py smoke
  python3 scripts/verify.py v57
  python3 scripts/verify.py frontend
  python3 scripts/verify.py full
  python3 scripts/verify.py release
  python3 scripts/verify.py durations
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


# ─── helpers ───────────────────────────────────────────────────────────────

def repo_root() -> Path:
    """返回仓库根目录，不依赖当前 shell 所在目录。"""
    script_dir = Path(__file__).resolve().parent
    return script_dir.parent


def banner(text: str) -> None:
    print(f"\n{'=' * 60}", flush=True)
    print(f"  {text}", flush=True)
    print(f"{'=' * 60}\n", flush=True)


def run(cmd: list[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    """运行命令，失败时立即退出。"""
    result = subprocess.run(cmd, cwd=cwd, check=False, capture_output=False, text=True)
    if check and result.returncode != 0:
        print(f"\n[ERROR] Command failed with exit code {result.returncode}: {' '.join(cmd)}", flush=True)
        sys.exit(result.returncode)
    return result


def run_optional_pytest(test_file: str) -> bool:
    """运行单个 pytest 文件，文件不存在时提示并跳过，返回是否执行。"""
    path = repo_root() / "tests" / test_file
    if not path.exists():
        print(f"  ⚠  可选测试文件不存在，跳过: tests/{test_file}", flush=True)
        return False
    run([sys.executable, "-m", "pytest", f"tests/{test_file}", "-q"])
    return True


# ─── commands ──────────────────────────────────────────────────────────────

def cmd_smoke() -> None:
    banner("SMOKE: 快速后端关键回归")

    run_optional_pytest("test_v5515_production_readiness.py")
    run_optional_pytest("test_v57_chapter_editing_versions.py")

    print("\n✓ smoke 完成\n", flush=True)


def cmd_v57() -> None:
    banner("V57: v5.7 编辑/版本相关测试")

    root = repo_root()

    run_optional_pytest("test_v57_chapter_editing_versions.py")

    banner("V57: frontend typecheck")
    run(["npm", "run", "typecheck"], cwd=root / "frontend")

    banner("V57: frontend ChapterEditorSurface tests")
    run(["npm", "run", "test", "--", "--run", "ChapterEditorSurface"], cwd=root / "frontend")

    print("\n✓ v57 完成\n", flush=True)


def cmd_frontend() -> None:
    banner("FRONTEND: 前端 typecheck + lint + vitest")

    root = repo_root()

    banner("FRONTEND: typecheck")
    run(["npm", "run", "typecheck"], cwd=root / "frontend")

    banner("FRONTEND: lint")
    run(["npm", "run", "lint"], cwd=root / "frontend")

    banner("FRONTEND: vitest")
    run(["npm", "run", "test", "--", "--run"], cwd=root / "frontend")

    print("\n✓ frontend 完成\n", flush=True)


def cmd_full() -> None:
    banner("FULL: 全量后端 + 前端（稳定基线/提交前闸门）")

    root = repo_root()

    banner("FULL: pytest")
    # Bound xdist concurrency for deterministic subprocess/SQLite timing on
    # developer machines and release runners. Project addopts uses ``-n auto``.
    run([sys.executable, "-m", "pytest", "-q", "-n", "4"], cwd=root)

    banner("FULL: frontend typecheck")
    run(["npm", "run", "typecheck"], cwd=root / "frontend")

    banner("FULL: frontend lint")
    run(["npm", "run", "lint"], cwd=root / "frontend")

    banner("FULL: frontend build")
    run(["npm", "run", "build"], cwd=root / "frontend")

    banner("FULL: frontend vitest")
    run(["npm", "run", "test", "--", "--run"], cwd=root / "frontend")

    print("\n✓ full 完成\n", flush=True)


def cmd_release() -> None:
    """Run the canonical, ordered release-evidence gate."""
    banner("RELEASE: 发布完整性与全栈验证")

    root = repo_root()

    banner("RELEASE 1/5: read-only preflight")
    run([sys.executable, "scripts/release_preflight.py"], cwd=root)

    banner("RELEASE 2/5: full pytest (4 workers)")
    run([sys.executable, "-m", "pytest", "-q", "-n", "4"], cwd=root)

    banner("RELEASE 3/5: frontend typecheck + lint + build + vitest")
    run(["npm", "run", "typecheck"], cwd=root / "frontend")
    run(["npm", "run", "lint"], cwd=root / "frontend")
    run(["npm", "run", "build"], cwd=root / "frontend")
    run(["npm", "run", "test", "--", "--run"], cwd=root / "frontend")

    banner("RELEASE 4/5: desktop typecheck + build")
    run(["npm", "run", "typecheck"], cwd=root / "desktop")
    run(["npm", "run", "build"], cwd=root / "desktop")

    banner("RELEASE 5/5: release smoke (stub mode, local API skipped)")
    run([sys.executable, "scripts/release_smoke.py", "--skip-api"], cwd=root)

    print("\n✓ release 完成；该结果可作为 completion report 发布证据\n", flush=True)


def cmd_durations() -> None:
    banner("DURATIONS: 查看最慢的 30 个 pytest 用例")

    run([sys.executable, "-m", "pytest", "-q", "--durations=30"], cwd=repo_root())

    print("\n✓ durations 完成\n", flush=True)


# ─── main ──────────────────────────────────────────────────────────────────

COMMANDS = {
    "smoke": cmd_smoke,
    "v57": cmd_v57,
    "frontend": cmd_frontend,
    "full": cmd_full,
    "release": cmd_release,
    "durations": cmd_durations,
}


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python3 scripts/verify.py <command>")
        print("")
        print("可用命令:")
        for name in COMMANDS:
            print(f"  {name}")
        print("")
        print("说明:")
        print("  smoke     - 快速后端关键回归（日常小改动后）")
        print("  v57       - v5.7 编辑/版本相关测试（编辑器改动后）")
        print("  frontend  - 前端 typecheck + lint + vitest（前端改动后）")
        print("  full      - 全量后端 + 前端（稳定基线声明或提交前）")
        print("  release   - 发布预检 + 全量后端/前端/桌面 + release smoke")
        print("  durations - 查看 pytest 最慢用例耗时")
        sys.exit(1)

    name = sys.argv[1]
    cmd = COMMANDS.get(name)
    if cmd is None:
        print(f"[ERROR] 未知命令: {name}")
        print(f"可用命令: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    # 确保在仓库根目录执行
    os.chdir(repo_root())
    cmd()


if __name__ == "__main__":
    main()
