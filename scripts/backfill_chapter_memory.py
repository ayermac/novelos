#!/usr/bin/env python3
"""Backfill MemoryCurator extraction for an already reviewed/published chapter.

This is a recovery tool for chapters that reached reviewed/awaiting_publish/
published without a visible memory_curator run or memory update batch.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _has_memory_batch_for_chapter(repo, project_id: str, chapter_number: int) -> bool:
    """Return True only when the memory inbox already has a visible batch."""
    try:
        for batch in repo.list_memory_batches(project_id):
            if int(batch.get("chapter_number") or 0) == int(chapter_number):
                return True
    except Exception:
        pass
    return False


def _build_llm(settings, llm_mode: str):
    if llm_mode == "stub":
        from novel_factory.llm.stub_provider import StubLLM

        return StubLLM()

    from novel_factory.workflow.runner import _build_llm_router

    return _build_llm_router(settings, llm_mode).for_agent("memory_curator")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill MemoryCurator extraction for a chapter."
    )
    parser.add_argument("--db-path", required=True, help="Path to SQLite database.")
    parser.add_argument("--project-id", required=True, help="Project id.")
    parser.add_argument("--chapter", required=True, type=int, help="Chapter number.")
    parser.add_argument("--config", default=None, help="Optional config YAML path.")
    parser.add_argument("--llm-mode", default="real", choices=("real", "stub"))
    parser.add_argument("--force", action="store_true", help="Run even if memory evidence already exists.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    from novel_factory.agents.memory_curator import MemoryCuratorAgent
    from novel_factory.config.loader import load_settings_with_cli
    from novel_factory.db.repository import Repository
    from novel_factory.skills.registry import SkillRegistry

    repo = Repository(args.db_path)
    chapter = repo.get_chapter(args.project_id, args.chapter)
    if not chapter:
        payload = {"ok": False, "error": "CHAPTER_NOT_FOUND"}
        print(json.dumps(payload, ensure_ascii=False) if args.json else payload["error"])
        return 1

    status = chapter.get("status")
    if status not in {"reviewed", "awaiting_publish", "published"} and not args.force:
        payload = {
            "ok": False,
            "error": "INVALID_STATUS",
            "message": f"章节状态为 {status!r}，默认只补 reviewed/awaiting_publish/published；如确认要跑请加 --force。",
        }
        print(json.dumps(payload, ensure_ascii=False) if args.json else payload["message"])
        return 1

    if _has_memory_batch_for_chapter(repo, args.project_id, args.chapter) and not args.force:
        payload = {
            "ok": True,
            "skipped": True,
            "message": "该章节已有记忆收件箱批次，未重复补跑。",
        }
        print(json.dumps(payload, ensure_ascii=False) if args.json else payload["message"])
        return 0

    settings = load_settings_with_cli(
        config_path=args.config,
        db_path=args.db_path,
        llm_mode=args.llm_mode,
    )
    llm = _build_llm(settings, args.llm_mode)
    run_id = repo.create_workflow_run(
        args.project_id,
        args.chapter,
        graph_name="memory_backfill",
    )
    repo.update_workflow_run(run_id, status="running", current_node="memory_curator")
    repo.create_workflow_node_event(
        run_id=run_id,
        project_id=args.project_id,
        chapter_number=args.chapter,
        node_name="memory_curator",
        event_type="started",
        status="running",
        message="手动补跑记忆提取",
    )

    agent = MemoryCuratorAgent(repo, llm, skill_registry=SkillRegistry())
    result = agent.run(
        {
            "project_id": args.project_id,
            "chapter_number": args.chapter,
            "chapter_status": status,
            "workflow_run_id": run_id,
            "llm_mode": args.llm_mode,
        }
    )

    if result.get("error"):
        repo.create_workflow_node_event(
            run_id=run_id,
            project_id=args.project_id,
            chapter_number=args.chapter,
            node_name="memory_curator",
            event_type="failed",
            status="failed",
            error_message=str(result["error"]),
        )
        repo.update_workflow_run(
            run_id,
            status="failed",
            current_node="memory_curator",
            error_message=str(result["error"]),
        )
        payload = {"ok": False, "run_id": run_id, **result}
        print(json.dumps(payload, ensure_ascii=False) if args.json else result["error"])
        return 1

    repo.create_workflow_node_event(
        run_id=run_id,
        project_id=args.project_id,
        chapter_number=args.chapter,
        node_name="memory_curator",
        event_type="completed",
        status="completed",
        message="手动补跑记忆提取完成",
        output_summary=f"{result.get('memory_items_count', 0)} 条候选记忆",
    )
    repo.update_workflow_run(run_id, status="completed", current_node="memory_curator", clear_error=True)

    payload = {
        "ok": True,
        "run_id": run_id,
        "project_id": args.project_id,
        "chapter": args.chapter,
        "chapter_status": status,
        **result,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
