#!/usr/bin/env python3
"""v6.4.5 optional real-LLM chapter quality acceptance harness.

The script creates an isolated acceptance project, runs one chapter through the
workflow, and summarizes QualityHub.diagnose() output. Real mode is skipped
cleanly when no API key is configured; stub mode is available to verify the
harness without network or paid model access.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from novel_factory.config.settings import load_settings
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.quality.hub import QualityHub
from novel_factory.skills.registry import SkillRegistry
from novel_factory.workflow.runner import run_with_graph


DEFAULT_PROJECT_ID = "v64-real-acceptance"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v6.4.5 real LLM quality acceptance.")
    parser.add_argument("--mode", choices=["real", "stub"], default="real")
    parser.add_argument("--config", default=None, help="Optional config YAML path")
    parser.add_argument("--db-path", default=None, help="Optional SQLite DB path")
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--chapter", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--output", default=None, help="Optional JSON report path")
    parser.add_argument("--keep-db", action="store_true", help="Keep temporary DB after run")
    return parser.parse_args()


def _has_real_credentials(settings) -> bool:
    if settings.llm.api_key:
        return True
    for profile in settings.llm_profiles.values():
        if profile.api_key:
            return True
        if profile.api_key_env and os.getenv(profile.api_key_env):
            return True
    return any(
        os.getenv(name)
        for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY")
    )


def _seed_acceptance_project(repo: Repository, project_id: str, chapter: int) -> None:
    if repo.get_project(project_id) is None:
        repo.create_project(
            project_id=project_id,
            name="雨巷里的旧钟",
            genre="都市悬疑",
            description=(
                "一个修钟师在老城区接到匿名委托，发现失踪父亲留下的钟表暗号，"
                "必须在拆迁前夜找到被隐藏的证词。"
            ),
            total_chapters_planned=3,
            target_words=9000,
            current_chapter=chapter,
        )

    if repo.get_chapter(project_id, chapter) is None:
        repo.add_chapter(project_id, chapter, f"第 {chapter} 章（验收样章）", status="planned")

    latest_genesis = repo.get_latest_genesis_run(project_id)
    if latest_genesis is None or latest_genesis.get("status") != "approved":
        repo.create_genesis_run(
            project_id=project_id,
            input_json=json.dumps({"title": "雨巷里的旧钟", "genre": "都市悬疑"}, ensure_ascii=False),
            status="approved",
        )

    if not repo.list_world_settings(project_id):
        repo.create_world_setting(
            project_id=project_id,
            category="老城空间",
            title="即将拆迁的雨巷",
            content="雨巷里保留着旧钟表铺、废弃照相馆和地下排水道，拆迁公告让所有线索都有了倒计时。",
        )

    if not repo.list_characters(project_id, include_inactive=True):
        repo.create_character(
            project_id=project_id,
            name="沈砚",
            role="protagonist",
            description="沉默的修钟师，擅长从机械结构里读出人的习惯。",
            traits="克制,敏锐,不轻易相信别人",
            first_appearance=chapter,
        )
        repo.create_character(
            project_id=project_id,
            name="林澈",
            role="supporting",
            description="负责拆迁档案的社区工作人员，表面圆滑，实际在暗中保存旧案材料。",
            traits="谨慎,会试探,有隐情",
            first_appearance=chapter,
        )

    if not repo.list_outlines(project_id):
        repo.create_outline(
            project_id=project_id,
            level="chapter",
            sequence=chapter,
            title="匿名委托",
            content="沈砚收到一只停在凌晨三点十七分的旧钟，钟壳内藏着父亲笔迹和雨巷地址。",
            chapters_range=str(chapter),
        )

    instruction = repo.get_instruction_by_chapter(project_id, chapter)
    if instruction is None or not instruction.get("objective"):
        repo.create_instruction(
            project_id=project_id,
            chapter_number=chapter,
            objective="以旧钟委托开场，让沈砚发现父亲留下的第一条线索，并与林澈发生试探性对话。",
            key_events="沈砚收到旧钟;钟壳内发现雨巷地址;林澈试探沈砚是否知道旧案",
            emotion_tone="克制、潮湿、带有压迫感",
            ending_hook="旧钟在无人触碰时重新走动，指针停在拆迁日期。",
            word_target=2200,
        )


def _evaluate_acceptance(diagnosis: dict[str, Any]) -> dict[str, Any]:
    dimensions = diagnosis.get("dimensions", {})
    findings = diagnosis.get("findings", [])
    critical_count = sum(1 for item in findings if item.get("severity") == "critical")
    high_count = sum(1 for item in findings if item.get("severity") == "high")

    checks = {
        "overall_score_at_least_50": diagnosis.get("overall_score", 0) >= 50,
        "death_penalty_clean": dimensions.get("death_penalty", 0) == 100 and critical_count == 0,
        "ai_trace_acceptable": dimensions.get("ai_trace", 100) >= 40,
        "narrative_quality_acceptable": dimensions.get("narrative_quality", 100) >= 45,
        "no_more_than_three_high_findings": high_count <= 3,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "critical_findings": critical_count,
        "high_findings": high_count,
    }


def _write_report(report: dict[str, Any], output_path: str | None) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
    print(payload)


def main() -> int:
    args = _parse_args()
    settings = load_settings(args.config)

    if args.mode == "real" and not _has_real_credentials(settings):
        report = {
            "schema_version": 1,
            "version": "v6.4.5",
            "status": "skipped",
            "mode": "real",
            "reason": "No real LLM API key configured. Set OPENAI_API_KEY or a configured profile api_key_env.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_report(report, args.output)
        return 0

    temp_db = None
    db_path = args.db_path
    if not db_path:
        fd, temp_db = tempfile.mkstemp(prefix="novelos-v645-", suffix=".db")
        os.close(fd)
        db_path = temp_db

    settings = settings.model_copy(update={"db_path": str(db_path)})
    init_db(settings.db_path)
    repo = Repository(settings.db_path)
    _seed_acceptance_project(repo, args.project_id, args.chapter)

    report: dict[str, Any] = {
        "schema_version": 1,
        "version": "v6.4.5",
        "status": "running",
        "mode": args.mode,
        "project_id": args.project_id,
        "chapter": args.chapter,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": settings.db_path if args.keep_db or args.db_path else None,
    }

    try:
        run_result = run_with_graph(
            project_id=args.project_id,
            chapter_number=args.chapter,
            settings=settings,
            repo=repo,
            llm_mode=args.mode,
            max_steps=args.max_steps,
        )
        chapter = repo.get_chapter(args.project_id, args.chapter) or {}
        content = chapter.get("content") or ""
        diagnosis = QualityHub(repo, SkillRegistry()).diagnose(content)
        acceptance = _evaluate_acceptance(diagnosis)
        report.update({
            "status": acceptance["status"],
            "run": {
                "chapter_status": run_result.get("chapter_status"),
                "requires_human": run_result.get("requires_human"),
                "error": run_result.get("error"),
                "steps": run_result.get("steps", []),
            },
            "chapter": {
                "title": chapter.get("title"),
                "status": chapter.get("status"),
                "word_count": chapter.get("word_count") or 0,
                "has_content": bool(content.strip()),
            },
            "acceptance": acceptance,
            "diagnosis": {
                "overall_score": diagnosis.get("overall_score"),
                "dimensions": diagnosis.get("dimensions", {}),
                "metrics": diagnosis.get("metrics", {}),
                "finding_counts": {
                    "total": len(diagnosis.get("findings", [])),
                    "critical": acceptance["critical_findings"],
                    "high": acceptance["high_findings"],
                },
            },
        })
        return_code = 0 if report["status"] in {"passed", "skipped"} else 1
    except Exception as exc:  # pragma: no cover - defensive CLI envelope
        report.update({
            "status": "failed",
            "error": str(exc),
        })
        return_code = 1
    finally:
        if temp_db and not args.keep_db:
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(temp_db + suffix)
                if candidate.exists():
                    candidate.unlink()

    _write_report(report, args.output)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
