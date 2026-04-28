"""Demo CLI commands: seed-demo, smoke-run."""

from __future__ import annotations

import argparse
import io
import json
import sys

from ..common import (
    _get_settings,
    _get_effective_llm_mode,
    _build_dispatcher,
    init_db,
    Repository,
)
from ..output import _print_output, print_llm_runtime_error


def cmd_seed_demo(args) -> None:
    """Seed demo project data."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    project_id = getattr(args, "project_id", "demo")
    use_json = getattr(args, "json", False)

    repo = Repository(settings.db_path)

    # Check if project already exists
    conn = repo._conn()
    existing = conn.execute(
        "SELECT project_id FROM projects WHERE project_id=?", (project_id,)
    ).fetchone()

    if existing:
        conn.close()
        if use_json:
            print(json.dumps({"ok": True, "error": None, "data": {"project_id": project_id, "message": "Project already exists, skipping seed"}}, ensure_ascii=False))
        else:
            print(f"Project '{project_id}' already exists, skipping seed.")
        return

    # Create demo project
    conn.execute(
        "INSERT INTO projects (project_id, name, genre, is_current, description, "
        "target_words, total_chapters_planned) VALUES (?, ?, ?, 1, ?, ?, ?)",
        (project_id, f"{project_id.title()} Novel", "fantasy",
         "平凡青年林默意外获得神秘力量，踏上一段充满危险与未知的冒险之旅。",
         150000, 50),
    )

    # Create chapter 1
    conn.execute(
        "INSERT INTO chapters (project_id, chapter_number, title, status) VALUES (?, ?, ?, ?)",
        (project_id, 1, "第一章：开端", "planned"),
    )

    # Create instruction
    conn.execute(
        "INSERT INTO instructions (project_id, chapter_number, objective, key_events, "
        "plots_to_plant, plots_to_resolve, ending_hook, word_target, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        (project_id, 1, "主角获得神秘力量，开始冒险", '["获得力量", "遭遇敌人"]', '["神秘力量来源"]', '[]', "敌人是谁？", 2500),
    )

    # Create character
    conn.execute(
        "INSERT INTO characters (project_id, name, role, description, status) "
        "VALUES (?, ?, ?, ?, 'active')",
        (project_id, "林默", "protagonist", "平凡青年，意外获得神秘力量"),
    )

    # Create plot hole
    conn.execute(
        "INSERT INTO plot_holes (project_id, code, title, status, planted_chapter, planned_resolve_chapter) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, "P001", "神秘力量来源", "planted", 1, 5),
    )

    # v5.3.0: Seed world setting (required by Context Readiness Gate)
    conn.execute(
        "INSERT INTO world_settings (project_id, category, title, content) "
        "VALUES (?, ?, ?, ?)",
        (project_id, "力量体系", "灵力觉醒",
         "天地间存在一种被称为'灵力'的神秘力量。少数人天生拥有觉醒灵力的潜能，"
         "觉醒后可感知超自然现象，掌握不可思议的能力。灵力分为金木水火土五行，"
         "修炼者需循五行相生之道方可精进。"),
    )

    # v5.3.0: Seed chapter outline (required by Context Readiness Gate)
    conn.execute(
        "INSERT INTO outlines (project_id, level, sequence, title, content, chapters_range) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, "chapter", 1, "第一章：开端",
         "平凡青年林默在一场意外中觉醒灵力，发现身边隐藏着不为人知的秘密力量。"
         "初次遭遇敌人后，他被迫踏上修行之路。",
         "1"),
    )

    conn.commit()
    conn.close()

    if use_json:
        print(json.dumps({"ok": True, "error": None, "data": {"project_id": project_id, "chapter": 1, "message": "Project seeded successfully"}}, ensure_ascii=False))
    else:
        print(f"Demo project seeded: project_id='{project_id}', chapter=1")


def cmd_smoke_run(args) -> None:
    """Run a smoke test on demo project."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    project_id = getattr(args, "project_id", "demo")
    chapter = getattr(args, "chapter", 1)
    # smoke-run defaults to stub mode if no explicit --llm-mode is given
    llm_mode = _get_effective_llm_mode(args)
    if llm_mode == "real" and getattr(args, "llm_mode", None) is None and getattr(args, "global_llm_mode", None) is None:
        llm_mode = "stub"
    max_steps = getattr(args, "max_steps", 20)
    use_json = getattr(args, "json", False)

    # Seed demo if not exists
    repo = Repository(settings.db_path)
    conn = repo._conn()
    existing = conn.execute(
        "SELECT project_id FROM projects WHERE project_id=?", (project_id,)
    ).fetchone()
    conn.close()

    if not existing:
        # Call seed-demo internally, suppress output in json mode
        seed_args = argparse.Namespace()
        seed_args.config = getattr(args, "config", None)
        seed_args.db_path = getattr(args, "db_path", None)
        seed_args.llm_mode = llm_mode
        seed_args.project_id = project_id
        seed_args.json = False  # Always suppress JSON for internal call
        # Temporarily redirect stdout if json mode
        if use_json:
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                cmd_seed_demo(seed_args)
            finally:
                sys.stdout = old_stdout
        else:
            cmd_seed_demo(seed_args)

    # Run chapter directly with dispatcher (bypass cmd_run_chapter to avoid double output)
    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)

    try:
        result = dispatcher.run_chapter(
            project_id=project_id,
            chapter_number=chapter,
            max_steps=max_steps,
        )
    except Exception as e:
        print_llm_runtime_error(e, use_json)

    # Wrap in envelope
    if use_json:
        # Check if run was successful (chapter_status == "published" and no error)
        is_ok = result.get("chapter_status") == "published" and not result.get("error")
        envelope = {
            "ok": is_ok,
            "error": None if is_ok else result.get("error", "Smoke run failed"),
            "data": result
        }
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    else:
        _print_output(result, False)
