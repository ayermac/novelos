#!/usr/bin/env python3
"""Soak test for real-LLM long chapter generation with segmented agents.

Validates that Author, Polisher, and MemoryCurator handle long chapters via
segmented generation without failure. Can run in stub, dry-run, or real mode.

Usage:
    # Stub mode (fast, validates script structure)
    python3 scripts/soak_real_llm_long_chapter.py --llm-mode stub

    # Dry-run: set up project but skip actual generation
    python3 scripts/soak_real_llm_long_chapter.py --llm-mode stub --dry-run

    # Real mode (requires API key, incurs cost)
    python3 scripts/soak_real_llm_long_chapter.py --llm-mode real --config config/local.yaml

Exit codes:
    0 — soak passed
    1 — soak failed
    2 — skipped (missing API key or other prerequisite)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from novel_factory.api_app import create_api_app  # noqa: E402
from novel_factory.db.connection import init_db  # noqa: E402
from novel_factory.db.repository import Repository  # noqa: E402
from novel_factory.version import get_version  # noqa: E402
from novel_factory.workflow.execution_events import (  # noqa: E402
    EVENT_SEGMENT_STARTED,
    EVENT_SEGMENT_COMPLETED,
    EVENT_SEGMENT_FAILED,
)


# ── Project fixture ──────────────────────────────────────────────────

SOAK_PROJECT_ID = "soak-long-chapter"
LONG_CHAPTER_PREMISE = (
    "在一个古代修仙世界里，主角是一位天赋异禀但性格叛逆的年轻修士。"
    "他为了寻找失散多年的师父，踏上了一段充满危险与机遇的旅程。"
    "途中他结识了性格迥异的同伴，也遭遇了强大的敌人。"
)
LONG_SCENE_BEATS = [
    "开场：主角在山门测试大会上展示出惊人的天赋，却因拒绝拜师而与宗门长老发生冲突",
    "转折：师父留下的玉佩突然发光，指引主角前往神秘遗迹",
    "冒险：主角在遗迹中遭遇机关陷阱，运用智慧和修为逐一化解",
    "相遇：遗迹深处，主角遇到一位神秘女子，她似乎知道师父的下落",
    "揭秘：女子透露师父被关押在魔道圣地，主角决定前往营救",
    "伏击：离开遗迹后，主角被魔道追兵伏击，一场大战一触即发",
    "逃脱：主角在同伴帮助下成功突围，但身受重伤",
    "修养：在一处隐秘山谷中养伤，期间领悟到新的修炼法门",
    "集结：主角召集各路盟友，准备攻打魔道圣地",
    "决战：攻入圣地，面对魔道首领，主角展示出超越境界的实力",
    "营救：成功救出师父，但师父已被魔功侵蚀，神志不清",
    "尾声：主角带着师父踏上寻找解药的旅程，故事暂告段落",
]


def _seed_soak_project(db_path: str) -> None:
    """Create a soak project with long chapter context."""
    init_db(db_path)
    repo = Repository(db_path)

    # Create project
    repo.create_project(
        project_id=SOAK_PROJECT_ID,
        name="Soak Long Chapter",
        description=LONG_CHAPTER_PREMISE,
    )

    # Insert world settings
    repo.create_world_setting(
        project_id=SOAK_PROJECT_ID,
        category="world",
        title="修仙世界",
        content="古代修仙世界，灵气充沛，宗门林立",
    )

    # Insert characters
    repo.create_character(
        project_id=SOAK_PROJECT_ID,
        name="李青峰",
        role="protagonist",
        description="天赋异禀但性格叛逆的年轻修士",
    )
    repo.create_character(
        project_id=SOAK_PROJECT_ID,
        name="苏婉儿",
        role="supporting",
        description="神秘女子，知晓主角师父下落",
    )

    # Insert chapter 1 with long outline
    repo.add_chapter(
        project_id=SOAK_PROJECT_ID,
        chapter_number=1,
        title="第一章 天赋测试",
        status="planned",
    )
    repo.save_chapter_content(
        project_id=SOAK_PROJECT_ID,
        chapter_number=1,
        content="\n".join(f"{i+1}. {beat}" for i, beat in enumerate(LONG_SCENE_BEATS)),
        title="第一章 天赋测试",
    )

    # Set chapter instructions to trigger segmentation
    repo.create_instruction(
        project_id=SOAK_PROJECT_ID,
        chapter_number=1,
        objective=(
            "请根据以下大纲写一章长篇小说正文。"
            "要求：对话自然、场景描写细腻、情节紧凑、"
            "人物动机清晰、每一场景至少有800字。"
            "总字数不少于15000字。"
        ),
    )


def _check_api_key(config_path: str | None) -> bool:
    """Check if real LLM mode has a configured API key."""
    for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY"):
        if os.environ.get(key):
            return True
    # Try reading from .env
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        content = env_path.read_text()
        for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY"):
            if key in content:
                return True
    return False


def _run_chapter(
    db_path: str,
    llm_mode: str,
    config_path: str | None,
    dry_run: bool,
) -> dict:
    """Run chapter 1 generation and return results."""
    from fastapi.testclient import TestClient

    app = create_api_app(
        db_path=db_path,
        llm_mode=llm_mode,
        config_path=config_path,
    )
    client = TestClient(app)

    if dry_run:
        return {
            "dry_run": True,
            "status": "skipped",
            "message": "Dry run — project seeded, generation skipped",
        }

    # Trigger chapter generation
    start_time = time.time()
    resp = client.post(
        f"/api/projects/{SOAK_PROJECT_ID}/chapters/1/generate",
    )
    elapsed = time.time() - start_time

    body = resp.json()

    # Fetch run events for segment analysis
    events_resp = client.get(
        f"/api/projects/{SOAK_PROJECT_ID}/chapters/1/events",
    )
    events = events_resp.json().get("data", {}).get("events", [])

    segment_started = [e for e in events if e.get("event_type") == EVENT_SEGMENT_STARTED]
    segment_completed = [e for e in events if e.get("event_type") == EVENT_SEGMENT_COMPLETED]
    segment_failed = [e for e in events if e.get("event_type") == EVENT_SEGMENT_FAILED]

    # Fetch final chapter status
    chapter_resp = client.get(
        f"/api/projects/{SOAK_PROJECT_ID}/chapters/1",
    )
    chapter_data = chapter_resp.json().get("data", {})

    return {
        "status": "completed" if body.get("ok") else "failed",
        "http_status": resp.status_code,
        "elapsed_seconds": round(elapsed, 2),
        "chapter_status": chapter_data.get("status", "unknown"),
        "word_count": chapter_data.get("word_count", 0),
        "segment_events": {
            "started": len(segment_started),
            "completed": len(segment_completed),
            "failed": len(segment_failed),
        },
        "last_error": body.get("error"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Soak test for long chapter generation")
    parser.add_argument("--llm-mode", choices=["stub", "real"], default="stub")
    parser.add_argument("--config", help="Config YAML for real mode")
    parser.add_argument("--db-path", help="SQLite DB path (default: temp)")
    parser.add_argument("--dry-run", action="store_true", help="Seed project only, skip generation")
    parser.add_argument("--json", action="store_true", help="Output JSON summary")
    args = parser.parse_args()

    # Real mode key check
    if args.llm_mode == "real" and not args.dry_run:
        if not _check_api_key(args.config):
            msg = {
                "ok": False,
                "status": "skipped",
                "reason": "No API key found in environment or .env",
                "hint": "Set OPENAI_API_KEY, OPENROUTER_API_KEY, or DEEPSEEK_API_KEY",
            }
            if args.json:
                print(json.dumps(msg, ensure_ascii=False, indent=2))
            else:
                print("SKIPPED: No API key found.")
                print("Set OPENAI_API_KEY, OPENROUTER_API_KEY, or DEEPSEEK_API_KEY")
            return 2

    db_path = args.db_path or str(tempfile.mktemp(suffix="_soak.db"))

    try:
        _seed_soak_project(db_path)

        result = _run_chapter(
            db_path=db_path,
            llm_mode=args.llm_mode,
            config_path=args.config,
            dry_run=args.dry_run,
        )

        summary = {
            "ok": result.get("status") == "completed" or args.dry_run,
            "version": get_version(),
            "llm_mode": args.llm_mode,
            "dry_run": args.dry_run,
            "db_path": db_path,
            "result": result,
        }

        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print("=" * 60)
            print("Soak Test Result")
            print("=" * 60)
            print(f"Version:      {get_version()}")
            print(f"LLM mode:     {args.llm_mode}")
            print(f"Dry run:      {args.dry_run}")
            print(f"DB path:      {db_path}")
            print(f"Status:       {result.get('status', 'unknown')}")
            if not args.dry_run:
                print(f"Elapsed:      {result.get('elapsed_seconds', 0)}s")
                print(f"Word count:   {result.get('word_count', 0)}")
                se = result.get("segment_events", {})
                print(f"Segments:     {se.get('started', 0)} started, {se.get('completed', 0)} completed, {se.get('failed', 0)} failed")
                if result.get("last_error"):
                    print(f"Last error:   {result['last_error']}")
            print("-" * 60)
            if summary["ok"]:
                print("PASS")
            else:
                print("FAIL")

        return 0 if summary["ok"] else 1

    finally:
        if not args.db_path and os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    sys.exit(main())
