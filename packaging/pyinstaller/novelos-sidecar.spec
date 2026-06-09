# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Novelos desktop sidecar.

Builds a one-directory bundle containing the Python backend and all
package data required to run independently of a source Python environment.

Usage:
    pyinstaller packaging/pyinstaller/novelos-sidecar.spec --clean

Output:
    dist/novelos-sidecar/novelos-sidecar
"""
from pathlib import Path
import os

repo_root = Path(SPECPATH).resolve().parent.parent
pkg_root = repo_root / "novel_factory"

block_cipher = None


# ── Collect all novel_factory Python modules as hidden imports ──
def collect_novel_factory_modules() -> list[str]:
    modules: list[str] = []
    for dirpath, dirnames, filenames in os.walk(pkg_root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        rel = Path(dirpath).relative_to(pkg_root)
        parts = list(rel.parts) if str(rel) != "." else []
        for f in filenames:
            if not f.endswith(".py"):
                continue
            if f == "__init__.py":
                if not parts:
                    continue
                mod = "novel_factory." + ".".join(parts)
            else:
                stem = f[:-3]
                if parts:
                    mod = "novel_factory." + ".".join(parts) + "." + stem
                else:
                    mod = "novel_factory." + stem
            modules.append(mod)
    return modules


novel_factory_hiddenimports = collect_novel_factory_modules()

a = Analysis(
    [str(pkg_root / "desktop_sidecar.py")],
    pathex=[str(repo_root)],
    binaries=[],
    datas=[
        (str(pkg_root / "db" / "schema" / "*.sql"), "novel_factory/db/schema"),
        (str(pkg_root / "db" / "migrations" / "*.sql"), "novel_factory/db/migrations"),
        (str(pkg_root / "config" / "*.yaml"), "novel_factory/config"),
        (str(pkg_root / "config" / "genre_strategies" / "*.yaml"), "novel_factory/config/genre_strategies"),
        (str(pkg_root / "config" / "skills" / "manifest" / "*.yaml"), "novel_factory/config/skills/manifest"),
        (str(pkg_root / "agent_runtime" / "roles" / "*.yaml"), "novel_factory/agent_runtime/roles"),
        # v6.10.0: Knowledge Skills (Markdown domain knowledge)
        (str(pkg_root / "skills" / "knowledge"), "novel_factory/skills/knowledge"),
    ],
    hiddenimports=[
        "uvicorn",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "fastapi",
        "starlette",
        "pydantic",
        "pydantic.deprecated.decorator",
        "langgraph",
        "langchain",
        "langchain_core",
        "langchain_community",
        "langchain_openai",
        "sqlite3",
        "yaml",
        "ruamel",
        "ruamel.yaml",
        "tenacity",
    ] + novel_factory_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── Additional third-party hidden imports via collect_submodules ──
try:
    from PyInstaller.utils.hooks import collect_submodules

    for pkg in (
        "langgraph",
        "langchain",
        "langchain_core",
        "langchain_openai",
        "fastapi",
        "starlette",
        "pydantic",
        "uvicorn",
        "ruamel",
        "ruamel.yaml",
    ):
        try:
            a.hiddenimports.extend(collect_submodules(pkg))
        except Exception:
            pass
except ImportError:
    pass

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="novelos-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="novelos-sidecar",
)
