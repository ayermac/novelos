"""CLI main entry point: parser construction and main() function."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys

from .common import _StubLLM
from .output import _print_output

# Command imports — grouped by module
from .commands.core import (
    cmd_init_db,
    cmd_run_chapter,
    cmd_status,
    cmd_runs,
    cmd_artifacts,
    cmd_human_resume,
)
from .commands.config import (
    cmd_config_show,
    cmd_config_validate,
    cmd_llm_profiles,
    cmd_llm_route,
    cmd_llm_validate,
    cmd_doctor,
)
from .commands.demo import (
    cmd_seed_demo,
    cmd_smoke_run,
)
from .commands.sidecar import (
    cmd_scout,
    cmd_report_daily,
    cmd_export_chapter,
    cmd_continuity_check,
    cmd_architect_suggest,
)
from .commands.skills import (
    cmd_skill_list,
    cmd_skill_run,
    cmd_skill_show,
    cmd_skill_validate,
    cmd_skill_test,
)
from .commands.skill_import import (
    cmd_skill_import_plan,
    cmd_skill_import_apply,
    cmd_skill_import_validate,
)
from .commands.quality import (
    cmd_quality_check,
    cmd_quality_report,
)
from .commands.batch import (
    cmd_batch_run,
    cmd_batch_status,
    cmd_batch_review,
    cmd_batch_revise,
    cmd_batch_revision_status,
    cmd_batch_continuity,
    cmd_batch_continuity_status,
    cmd_batch_enqueue,
    cmd_batch_queue_run,
    cmd_batch_queue_status,
    cmd_batch_queue_pause,
    cmd_batch_queue_resume,
    cmd_batch_queue_retry,
    cmd_batch_queue_timeouts,
    cmd_batch_queue_events,
    cmd_batch_queue_cancel,
    cmd_batch_queue_recover,
    cmd_batch_queue_doctor,
    cmd_batch_queue_run_limit,
)
from .commands.serial import (
    cmd_serial_create,
    cmd_serial_status,
    cmd_serial_enqueue_next,
    cmd_serial_advance,
    cmd_serial_pause,
    cmd_serial_resume,
    cmd_serial_cancel,
)
from .commands.review import (
    cmd_review_pack,
    cmd_review_chapter,
    cmd_review_timeline,
    cmd_review_diff,
    cmd_review_export,
)
from .commands.llm_catalog import (
    cmd_llm_catalog,
    cmd_llm_recommend,
    cmd_llm_config_plan,
)
from .commands.style_bible import (
    cmd_style_templates,
    cmd_style_init,
    cmd_style_show,
    cmd_style_update,
    cmd_style_check,
    cmd_style_delete,
)


# ── Argument parser ──────────────────────────────────────────────


class JSONArgumentParser(argparse.ArgumentParser):
    """Custom ArgumentParser that outputs JSON errors when --json is present."""

    def error(self, message: str) -> None:
        """Override error to output JSON format when --json is present."""
        # Check if --json is in sys.argv
        if "--json" in sys.argv:
            print(json.dumps({"ok": False, "error": message, "data": {}}, ensure_ascii=False))
            sys.exit(2)
        else:
            # Default behavior
            super().error(message)


def _get_version() -> str:
    """Get package version from importlib.metadata, with fallback for source mode."""
    try:
        return importlib.metadata.version("novel-factory")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for novelos CLI."""
    parser = JSONArgumentParser(
        prog="novelos",
        description="Novel Factory — AI-powered novel chapter production",
    )
    parser.add_argument("--config", help="Path to config YAML file")
    parser.add_argument("--db-path", help="Path to SQLite database file")
    parser.add_argument("--llm-mode", dest="global_llm_mode", choices=["stub", "real"], default=None, help="LLM mode: stub for demo, real for actual LLM (global default)")
    parser.add_argument("--version", action="version", version=f"novelos {_get_version()}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init-db
    init_parser = subparsers.add_parser("init-db", help="Initialize the database")
    init_parser.set_defaults(func=cmd_init_db)

    # run-chapter
    run_parser = subparsers.add_parser("run-chapter", help="Run chapter production pipeline")
    run_parser.add_argument("--project-id", required=True, help="Project ID")
    run_parser.add_argument("--chapter", type=int, required=True, help="Chapter number")
    run_parser.add_argument("--max-steps", type=int, default=20, help="Maximum dispatch steps (default: 20)")
    run_parser.add_argument("--llm-mode", choices=["stub", "real"], default=None, help="LLM mode: stub for demo, real for actual LLM (default: real)")
    run_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    run_parser.set_defaults(func=cmd_run_chapter)

    # status
    status_parser = subparsers.add_parser("status", help="Show chapter status")
    status_parser.add_argument("--project-id", required=True, help="Project ID")
    status_parser.add_argument("--chapter", type=int, required=True, help="Chapter number")
    status_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    status_parser.set_defaults(func=cmd_status)

    # runs
    runs_parser = subparsers.add_parser("runs", help="Show workflow runs for a project")
    runs_parser.add_argument("--project-id", required=True, help="Project ID")
    runs_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    runs_parser.set_defaults(func=cmd_runs)

    # artifacts
    artifacts_parser = subparsers.add_parser("artifacts", help="Show artifacts for a chapter")
    artifacts_parser.add_argument("--project-id", required=True, help="Project ID")
    artifacts_parser.add_argument("--chapter", type=int, required=True, help="Chapter number")
    artifacts_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    artifacts_parser.set_defaults(func=cmd_artifacts)

    # human-resume
    resume_parser = subparsers.add_parser("human-resume", help="Resume a blocked chapter")
    resume_parser.add_argument("--project-id", required=True, help="Project ID")
    resume_parser.add_argument("--chapter", type=int, required=True, help="Chapter number")
    resume_parser.add_argument("--status", required=True, help="Target status to resume to")
    resume_parser.add_argument("--llm-mode", choices=["stub", "real"], default=None, help="LLM mode: stub for demo, real for actual LLM (default: real)")
    resume_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    resume_parser.set_defaults(func=cmd_human_resume)

    # config show
    config_show_parser = subparsers.add_parser("config", help="Configuration commands")
    config_subparsers = config_show_parser.add_subparsers(dest="config_command", help="Config subcommands")

    config_show = config_subparsers.add_parser("show", help="Show current configuration")
    config_show.add_argument("--json", action="store_true", help="Output in JSON format")
    config_show.set_defaults(func=cmd_config_show)

    config_validate = config_subparsers.add_parser("validate", help="Validate configuration")
    config_validate.add_argument("--json", action="store_true", help="Output in JSON format")
    config_validate.set_defaults(func=cmd_config_validate)

    # v3.1: llm commands
    llm_parser = subparsers.add_parser("llm", help="LLM profile and routing commands")
    llm_subparsers = llm_parser.add_subparsers(dest="llm_command", help="LLM subcommands")

    llm_profiles = llm_subparsers.add_parser("profiles", help="List all LLM profiles")
    llm_profiles.add_argument("--json", action="store_true", help="Output in JSON format")
    llm_profiles.set_defaults(func=cmd_llm_profiles)

    llm_route = llm_subparsers.add_parser("route", help="Show LLM route for an agent")
    llm_route.add_argument("--agent", required=True, help="Agent ID (e.g., author, editor)")
    llm_route.add_argument("--json", action="store_true", help="Output in JSON format")
    llm_route.set_defaults(func=cmd_llm_route)

    llm_validate = llm_subparsers.add_parser("validate", help="Validate LLM configuration")
    llm_validate.add_argument("--json", action="store_true", help="Output in JSON format")
    llm_validate.set_defaults(func=cmd_llm_validate)

    # v3.9: llm catalog / recommend / config-plan
    llm_catalog = llm_subparsers.add_parser("catalog", help="List LLM model catalog")
    llm_catalog.add_argument("--json", action="store_true", help="Output in JSON format")
    llm_catalog.set_defaults(func=cmd_llm_catalog)

    llm_recommend = llm_subparsers.add_parser("recommend", help="Recommend LLM models for agents")
    llm_recommend.add_argument("--agent", help="Agent ID (e.g., author, editor)")
    llm_recommend.add_argument("--all", action="store_true", help="Recommend for all agents")
    llm_recommend.add_argument("--cost-tier", choices=["low", "medium", "high"], help="Maximum cost tier")
    llm_recommend.add_argument("--quality-tier", choices=["draft", "standard", "premium"], help="Minimum quality tier")
    llm_recommend.add_argument("--provider", help="Comma-separated provider whitelist (e.g., openai,deepseek)")
    llm_recommend.add_argument("--require-strengths", dest="require_strengths", help="Comma-separated required strengths (e.g., reasoning,json)")
    llm_recommend.add_argument("--prefer-low-latency", dest="prefer_low_latency", action="store_true", help="Prefer low-latency models")
    llm_recommend.add_argument("--json", action="store_true", help="Output in JSON format")
    llm_recommend.set_defaults(func=cmd_llm_recommend)

    llm_config_plan = llm_subparsers.add_parser("config-plan", help="Generate LLM configuration plan draft")
    llm_config_plan.add_argument("--all", action="store_true", help="Generate plan for all agents (default behavior)")
    llm_config_plan.add_argument("--cost-tier", choices=["low", "medium", "high"], help="Maximum cost tier")
    llm_config_plan.add_argument("--quality-tier", choices=["draft", "standard", "premium"], help="Minimum quality tier")
    llm_config_plan.add_argument("--provider", help="Comma-separated provider whitelist")
    llm_config_plan.add_argument("--prefer-low-latency", dest="prefer_low_latency", action="store_true", help="Prefer low-latency models")
    llm_config_plan.add_argument("--json", action="store_true", help="Output in JSON format")
    llm_config_plan.set_defaults(func=cmd_llm_config_plan)

    # seed-demo
    seed_parser = subparsers.add_parser("seed-demo", help="Seed demo project data")
    seed_parser.add_argument("--project-id", default="demo", help="Project ID to seed (default: demo)")
    seed_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    seed_parser.set_defaults(func=cmd_seed_demo)

    # smoke-run
    smoke_parser = subparsers.add_parser("smoke-run", help="Run a smoke test on demo project")
    smoke_parser.add_argument("--project-id", default="demo", help="Project ID to test (default: demo)")
    smoke_parser.add_argument("--chapter", type=int, default=1, help="Chapter number to test (default: 1)")
    smoke_parser.add_argument("--llm-mode", choices=["stub", "real"], default=None, help="LLM mode: stub for demo, real for actual LLM (default: stub)")
    smoke_parser.add_argument("--max-steps", type=int, default=20, help="Maximum dispatch steps (default: 20)")
    smoke_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    smoke_parser.set_defaults(func=cmd_smoke_run)

    # doctor
    doctor_parser = subparsers.add_parser("doctor", help="Run system diagnostics")
    doctor_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    doctor_parser.set_defaults(func=cmd_doctor)

    # scout
    scout_parser = subparsers.add_parser("scout", help="Generate market report")
    scout_parser.add_argument("--project-id", required=True, help="Project ID")
    scout_parser.add_argument("--topic", help="Topic to analyze")
    scout_parser.add_argument("--genre", help="Target genre")
    scout_parser.add_argument("--platform", help="Target platform")
    scout_parser.add_argument("--audience", help="Target audience")
    scout_parser.add_argument("--llm-mode", choices=["stub", "real"], default=None, help="LLM mode: stub for demo, real for actual LLM (default: real)")
    scout_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    scout_parser.set_defaults(func=cmd_scout)

    # report
    report_parser = subparsers.add_parser("report", help="Generate reports")
    report_subparsers = report_parser.add_subparsers(dest="report_command", help="Report subcommands")

    report_daily = report_subparsers.add_parser("daily", help="Generate daily report")
    report_daily.add_argument("--project-id", required=True, help="Project ID")
    report_daily.add_argument("--date", help="Report date (YYYY-MM-DD, default: today)")
    report_daily.add_argument("--json", action="store_true", help="Output in JSON format")
    report_daily.set_defaults(func=cmd_report_daily)

    # export
    export_parser = subparsers.add_parser("export", help="Export data")
    export_subparsers = export_parser.add_subparsers(dest="export_command", help="Export subcommands")

    export_chapter = export_subparsers.add_parser("chapter", help="Export chapter")
    export_chapter.add_argument("--project-id", required=True, help="Project ID")
    export_chapter.add_argument("--chapter", type=int, required=True, help="Chapter number")
    export_chapter.add_argument("--format", choices=["json", "markdown"], default="markdown", help="Export format (default: markdown)")
    export_chapter.add_argument("--json", action="store_true", help="Output in JSON format")
    export_chapter.set_defaults(func=cmd_export_chapter)

    # continuity-check
    continuity_parser = subparsers.add_parser("continuity-check", help="Check cross-chapter continuity")
    continuity_parser.add_argument("--project-id", required=True, help="Project ID")
    continuity_parser.add_argument("--from-chapter", type=int, required=True, help="Start chapter")
    continuity_parser.add_argument("--to-chapter", type=int, required=True, help="End chapter")
    continuity_parser.add_argument("--llm-mode", choices=["stub", "real"], default=None, help="LLM mode: stub for demo, real for actual LLM (default: real)")
    continuity_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    continuity_parser.set_defaults(func=cmd_continuity_check)

    # architect
    architect_parser = subparsers.add_parser("architect", help="Generate architecture proposals")
    architect_subparsers = architect_parser.add_subparsers(dest="architect_command", help="Architect subcommands")

    architect_suggest = architect_subparsers.add_parser("suggest", help="Generate improvement proposals")
    architect_suggest.add_argument("--project-id", required=True, help="Project ID")
    architect_suggest.add_argument("--scope", choices=["quality", "workflow", "agent", "system"], default="quality", help="Analysis scope (default: quality)")
    architect_suggest.add_argument("--llm-mode", choices=["stub", "real"], default=None, help="LLM mode: stub for demo, real for actual LLM (default: real)")
    architect_suggest.add_argument("--json", action="store_true", help="Output in JSON format")
    architect_suggest.set_defaults(func=cmd_architect_suggest)

    # skills (plural, matching spec)
    skills_parser = subparsers.add_parser("skills", help="Manage and run skills")
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command", help="Skills subcommands")

    skills_list = skills_subparsers.add_parser("list", help="List available skills")
    skills_list.add_argument("--json", action="store_true", help="Output in JSON format")
    skills_list.set_defaults(func=cmd_skill_list)

    skills_run = skills_subparsers.add_parser("run", help="Run a skill")
    skills_run.add_argument("skill_id", help="Skill ID to run (e.g., humanizer-zh, ai-style-detector)")
    skills_run.add_argument("--text", help="Text input for the skill")
    skills_run.add_argument("--project-id", help="Project ID (optional)")
    skills_run.add_argument("--chapter", type=int, help="Chapter number (optional)")
    skills_run.add_argument("--input-json", help="JSON input payload (optional, overrides --text)")
    skills_run.add_argument("--json", action="store_true", help="Output in JSON format")
    skills_run.set_defaults(func=cmd_skill_run)

    # v2.2: skills show command
    skills_show = skills_subparsers.add_parser("show", help="Show skill manifest details")
    skills_show.add_argument("skill_id", help="Skill ID to show (e.g., humanizer-zh, ai-style-detector)")
    skills_show.add_argument("--json", action="store_true", help="Output in JSON format")
    skills_show.set_defaults(func=cmd_skill_show)

    # v2.2: skills validate command
    skills_validate = skills_subparsers.add_parser("validate", help="Validate all skill manifests")
    skills_validate.add_argument("--json", action="store_true", help="Output in JSON format")
    skills_validate.set_defaults(func=cmd_skill_validate)

    # v2.3: skills test command
    skills_test = skills_subparsers.add_parser("test", help="Run skill fixtures test")
    skills_test.add_argument("skill_id", nargs="?", help="Skill ID to test (e.g., humanizer-zh)")
    skills_test.add_argument("--all", action="store_true", help="Test all skills with packages")
    skills_test.add_argument("--json", action="store_true", help="Output in JSON format")
    skills_test.set_defaults(func=cmd_skill_test)

    # v3.8: skills import subcommands
    skills_import_plan = skills_subparsers.add_parser("import-plan", help="Generate import plan for external skill")
    skills_import_plan.add_argument("--source", required=True, help="Path to external skill directory")
    skills_import_plan.add_argument("--json", action="store_true", help="Output in JSON format")
    skills_import_plan.set_defaults(func=cmd_skill_import_plan)

    skills_import_apply = skills_subparsers.add_parser("import-apply", help="Apply import plan and generate skill package")
    skills_import_apply.add_argument("--source", required=True, help="Path to external skill directory")
    skills_import_apply.add_argument("--skill-id", required=True, help="Target skill ID (e.g., imported-demo)")
    skills_import_apply.add_argument("--force", action="store_true", help="Overwrite existing package directory")
    skills_import_apply.add_argument("--json", action="store_true", help="Output in JSON format")
    skills_import_apply.set_defaults(func=cmd_skill_import_apply)

    skills_import_validate = skills_subparsers.add_parser("import-validate", help="Validate imported skill package")
    skills_import_validate.add_argument("--skill-id", required=True, help="Skill ID to validate")
    skills_import_validate.add_argument("--json", action="store_true", help="Output in JSON format")
    skills_import_validate.set_defaults(func=cmd_skill_import_validate)

    # quality
    quality_parser = subparsers.add_parser("quality", help="Quality hub operations")
    quality_subparsers = quality_parser.add_subparsers(dest="quality_command", help="Quality subcommands")

    quality_check = quality_subparsers.add_parser("check", help="Run quality check on a chapter")
    quality_check.add_argument("--project-id", required=True, help="Project ID")
    quality_check.add_argument("--chapter", type=int, required=True, help="Chapter number")
    quality_check.add_argument("--stage", choices=["draft", "polished", "final"], default="draft", help="Quality check stage (default: draft)")
    quality_check.add_argument("--json", action="store_true", help="Output in JSON format")
    quality_check.set_defaults(func=cmd_quality_check)

    quality_report = quality_subparsers.add_parser("report", help="Show quality reports for a chapter")
    quality_report.add_argument("--project-id", required=True, help="Project ID")
    quality_report.add_argument("--chapter", type=int, required=True, help="Chapter number")
    quality_report.add_argument("--limit", type=int, default=5, help="Maximum number of reports to show (default: 5)")
    quality_report.add_argument("--json", action="store_true", help="Output in JSON format")
    quality_report.set_defaults(func=cmd_quality_report)

    # batch (v3.0)
    batch_parser = subparsers.add_parser("batch", help="Batch production operations")
    batch_subparsers = batch_parser.add_subparsers(dest="batch_command", help="Batch subcommands")

    batch_run = batch_subparsers.add_parser("run", help="Run batch production for multiple chapters")
    batch_run.add_argument("--project-id", required=True, help="Project ID")
    batch_run.add_argument("--from-chapter", type=int, required=True, help="Starting chapter number (inclusive)")
    batch_run.add_argument("--to-chapter", type=int, required=True, help="Ending chapter number (inclusive)")
    batch_run.add_argument("--llm-mode", choices=["stub", "real"], default=None, help="LLM mode: stub for demo, real for actual LLM (default: real)")
    batch_run.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_run.set_defaults(func=cmd_batch_run)

    batch_status = batch_subparsers.add_parser("status", help="Get batch production run status")
    batch_status.add_argument("--run-id", required=True, help="Production run ID")
    batch_status.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_status.set_defaults(func=cmd_batch_status)

    batch_review = batch_subparsers.add_parser("review", help="Record human review decision")
    batch_review.add_argument("--run-id", required=True, help="Production run ID")
    batch_review.add_argument("--decision", required=True, choices=["approve", "request_changes", "reject"], help="Review decision")
    batch_review.add_argument("--notes", help="Optional review notes")
    batch_review.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_review.set_defaults(func=cmd_batch_review)

    # batch revise (v3.2)
    batch_revise = batch_subparsers.add_parser("revise", help="Create and execute batch revision plan")
    batch_revise.add_argument("--run-id", required=True, help="Production run ID")
    batch_revise.add_argument("--plan-json", required=True, help="Revision plan JSON string")
    batch_revise.add_argument("--llm-mode", choices=["stub", "real"], default=None, help="LLM mode: stub for demo, real for actual LLM (default: real)")
    batch_revise.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_revise.set_defaults(func=cmd_batch_revise)

    # batch revision-status (v3.2)
    batch_revision_status = batch_subparsers.add_parser("revision-status", help="Get batch revision run status")
    batch_revision_status.add_argument("--revision-run-id", required=True, help="Revision run ID")
    batch_revision_status.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_revision_status.set_defaults(func=cmd_batch_revision_status)

    # batch continuity (v3.3)
    batch_continuity = batch_subparsers.add_parser("continuity", help="Run batch continuity gate")
    batch_continuity.add_argument("--run-id", required=True, help="Production run ID")
    batch_continuity.add_argument("--llm-mode", choices=["stub", "real"], default=None, help="LLM mode: stub for demo, real for actual LLM (default: real)")
    batch_continuity.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_continuity.set_defaults(func=cmd_batch_continuity)

    # batch continuity-status (v3.3)
    batch_continuity_status = batch_subparsers.add_parser("continuity-status", help="Get batch continuity gate status")
    batch_continuity_status.add_argument("--run-id", required=True, help="Production run ID")
    batch_continuity_status.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_continuity_status.set_defaults(func=cmd_batch_continuity_status)

    # batch enqueue (v3.4)
    batch_enqueue = batch_subparsers.add_parser("enqueue", help="Enqueue a batch production request")
    batch_enqueue.add_argument("--project-id", required=True, help="Project ID")
    batch_enqueue.add_argument("--from-chapter", type=int, required=True, help="Starting chapter number (inclusive)")
    batch_enqueue.add_argument("--to-chapter", type=int, required=True, help="Ending chapter number (inclusive)")
    batch_enqueue.add_argument("--priority", type=int, default=100, help="Queue priority (lower = higher, default: 100)")
    batch_enqueue.add_argument("--max-chapters", type=int, default=50, help="Maximum chapters per batch (default: 50)")
    batch_enqueue.add_argument("--max-attempts", type=int, default=3, help="Maximum retry attempts (default: 3)")
    batch_enqueue.add_argument("--timeout-minutes", type=int, default=120, help="Timeout for running items in minutes (default: 120)")
    batch_enqueue.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_enqueue.set_defaults(func=cmd_batch_enqueue)

    # batch queue-run (v3.4)
    batch_queue_run = batch_subparsers.add_parser("queue-run", help="Execute next pending queue item")
    batch_queue_run.add_argument("--once", action="store_true", help="Run once (equivalent to --limit 1)")
    batch_queue_run.add_argument("--limit", type=int, default=1, help="Maximum number of queue items to execute (default: 1)")
    batch_queue_run.add_argument("--llm-mode", choices=["stub", "real"], default=None, help="LLM mode: stub for demo, real for actual LLM (default: real)")
    batch_queue_run.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_queue_run.set_defaults(func=cmd_batch_queue_run_limit)

    # batch queue-status (v3.4)
    batch_queue_status = batch_subparsers.add_parser("queue-status", help="Get production queue status")
    batch_queue_status.add_argument("--project-id", help="Filter by project ID")
    batch_queue_status.add_argument("--status", choices=["pending", "running", "paused", "completed", "failed", "timeout", "cancelled"], help="Filter by status")
    batch_queue_status.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_queue_status.set_defaults(func=cmd_batch_queue_status)

    # batch queue-pause (v3.4)
    batch_queue_pause = batch_subparsers.add_parser("queue-pause", help="Pause a queue item")
    batch_queue_pause.add_argument("--queue-id", required=True, help="Queue item ID")
    batch_queue_pause.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_queue_pause.set_defaults(func=cmd_batch_queue_pause)

    # batch queue-resume (v3.4)
    batch_queue_resume = batch_subparsers.add_parser("queue-resume", help="Resume a paused queue item")
    batch_queue_resume.add_argument("--queue-id", required=True, help="Queue item ID")
    batch_queue_resume.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_queue_resume.set_defaults(func=cmd_batch_queue_resume)

    # batch queue-retry (v3.4)
    batch_queue_retry = batch_subparsers.add_parser("queue-retry", help="Retry a failed or timed-out queue item")
    batch_queue_retry.add_argument("--queue-id", required=True, help="Queue item ID")
    batch_queue_retry.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_queue_retry.set_defaults(func=cmd_batch_queue_retry)

    # batch queue-timeouts (v3.4)
    batch_queue_timeouts = batch_subparsers.add_parser("queue-timeouts", help="Mark timed-out queue items")
    batch_queue_timeouts.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_queue_timeouts.set_defaults(func=cmd_batch_queue_timeouts)

    # batch queue-events (v3.5)
    batch_queue_events = batch_subparsers.add_parser("queue-events", help="View queue item audit events")
    batch_queue_events.add_argument("--queue-id", required=True, help="Queue item ID")
    batch_queue_events.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_queue_events.set_defaults(func=cmd_batch_queue_events)

    # batch queue-cancel (v3.5)
    batch_queue_cancel = batch_subparsers.add_parser("queue-cancel", help="Cancel a queue item")
    batch_queue_cancel.add_argument("--queue-id", required=True, help="Queue item ID")
    batch_queue_cancel.add_argument("--reason", help="Cancellation reason")
    batch_queue_cancel.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_queue_cancel.set_defaults(func=cmd_batch_queue_cancel)

    # batch queue-recover (v3.5)
    batch_queue_recover = batch_subparsers.add_parser("queue-recover", help="Recover a stuck running queue item")
    batch_queue_recover.add_argument("--queue-id", required=True, help="Queue item ID")
    batch_queue_recover.add_argument("--force", action="store_true", help="Force recovery even if not stuck")
    batch_queue_recover.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_queue_recover.set_defaults(func=cmd_batch_queue_recover)

    # batch queue-doctor (v3.5)
    batch_queue_doctor = batch_subparsers.add_parser("queue-doctor", help="Diagnose a queue item")
    batch_queue_doctor.add_argument("--queue-id", required=True, help="Queue item ID")
    batch_queue_doctor.add_argument("--json", action="store_true", help="Output in JSON format")
    batch_queue_doctor.set_defaults(func=cmd_batch_queue_doctor)

    # serial (v3.6)
    serial_parser = subparsers.add_parser("serial", help="Serial plan operations")
    serial_subparsers = serial_parser.add_subparsers(dest="serial_command", help="Serial subcommands")

    serial_create = serial_subparsers.add_parser("create", help="Create a serial plan")
    serial_create.add_argument("--project-id", required=True, help="Project ID")
    serial_create.add_argument("--name", required=True, help="Serial plan name")
    serial_create.add_argument("--start-chapter", type=int, required=True, help="Starting chapter number")
    serial_create.add_argument("--target-chapter", type=int, required=True, help="Target chapter number")
    serial_create.add_argument("--batch-size", type=int, required=True, help="Chapters per batch")
    serial_create.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_create.set_defaults(func=cmd_serial_create)

    serial_status = serial_subparsers.add_parser("status", help="Get serial plan status")
    serial_status.add_argument("--serial-plan-id", required=True, help="Serial plan ID")
    serial_status.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_status.set_defaults(func=cmd_serial_status)

    serial_enqueue_next = serial_subparsers.add_parser("enqueue-next", help="Enqueue next batch")
    serial_enqueue_next.add_argument("--serial-plan-id", required=True, help="Serial plan ID")
    serial_enqueue_next.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_enqueue_next.set_defaults(func=cmd_serial_enqueue_next)

    serial_advance = serial_subparsers.add_parser("advance", help="Advance serial plan with decision")
    serial_advance.add_argument("--serial-plan-id", required=True, help="Serial plan ID")
    serial_advance.add_argument("--decision", required=True, choices=["approve", "request_changes", "pause", "cancel"], help="Decision")
    serial_advance.add_argument("--notes", help="Optional notes")
    serial_advance.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_advance.set_defaults(func=cmd_serial_advance)

    serial_pause = serial_subparsers.add_parser("pause", help="Pause a serial plan")
    serial_pause.add_argument("--serial-plan-id", required=True, help="Serial plan ID")
    serial_pause.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_pause.set_defaults(func=cmd_serial_pause)

    serial_resume = serial_subparsers.add_parser("resume", help="Resume a paused serial plan")
    serial_resume.add_argument("--serial-plan-id", required=True, help="Serial plan ID")
    serial_resume.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_resume.set_defaults(func=cmd_serial_resume)

    serial_cancel = serial_subparsers.add_parser("cancel", help="Cancel a serial plan")
    serial_cancel.add_argument("--serial-plan-id", required=True, help="Serial plan ID")
    serial_cancel.add_argument("--reason", help="Cancellation reason")
    serial_cancel.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_cancel.set_defaults(func=cmd_serial_cancel)

    # review (v3.7)
    review_parser = subparsers.add_parser("review", help="Review workbench operations")
    review_subparsers = review_parser.add_subparsers(dest="review_command", help="Review subcommands")

    review_pack = review_subparsers.add_parser("pack", help="Build a review pack")
    review_pack.add_argument("--run-id", help="Production run ID")
    review_pack.add_argument("--serial-plan-id", help="Serial plan ID")
    review_pack.add_argument("--project-id", help="Project ID (for range)")
    review_pack.add_argument("--from-chapter", type=int, help="Starting chapter (for range)")
    review_pack.add_argument("--to-chapter", type=int, help="Ending chapter (for range)")
    review_pack.add_argument("--json", action="store_true", help="Output in JSON format")
    review_pack.set_defaults(func=cmd_review_pack)

    review_chapter = review_subparsers.add_parser("chapter", help="Get review view for a chapter")
    review_chapter.add_argument("--project-id", required=True, help="Project ID")
    review_chapter.add_argument("--chapter", type=int, required=True, help="Chapter number")
    review_chapter.add_argument("--json", action="store_true", help="Output in JSON format")
    review_chapter.set_defaults(func=cmd_review_chapter)

    review_timeline = review_subparsers.add_parser("timeline", help="Get timeline events")
    review_timeline.add_argument("--run-id", help="Production run ID")
    review_timeline.add_argument("--serial-plan-id", help="Serial plan ID")
    review_timeline.add_argument("--queue-id", help="Queue item ID")
    review_timeline.add_argument("--project-id", help="Project ID (for chapter)")
    review_timeline.add_argument("--chapter", type=int, help="Chapter number")
    review_timeline.add_argument("--json", action="store_true", help="Output in JSON format")
    review_timeline.set_defaults(func=cmd_review_timeline)

    review_diff = review_subparsers.add_parser("diff", help="Get diff between chapter versions")
    review_diff.add_argument("--project-id", required=True, help="Project ID")
    review_diff.add_argument("--chapter", type=int, required=True, help="Chapter number")
    review_diff.add_argument("--from-version", help="From version ID")
    review_diff.add_argument("--to-version", help="To version ID")
    review_diff.add_argument("--json", action="store_true", help="Output in JSON format")
    review_diff.set_defaults(func=cmd_review_diff)

    review_export = review_subparsers.add_parser("export", help="Export review pack")
    review_export.add_argument("--run-id", help="Production run ID")
    review_export.add_argument("--serial-plan-id", help="Serial plan ID")
    review_export.add_argument("--project-id", help="Project ID (for range)")
    review_export.add_argument("--from-chapter", type=int, help="Starting chapter (for range)")
    review_export.add_argument("--to-chapter", type=int, help="Ending chapter (for range)")
    review_export.add_argument("--format", choices=["json", "markdown"], default="json", help="Export format")
    review_export.add_argument("--output", required=True, help="Output file path")
    review_export.add_argument("--force", action="store_true", help="Force overwrite")
    review_export.add_argument("--json", action="store_true", help="Output in JSON format")
    review_export.set_defaults(func=cmd_review_export)

    # v4.0: style commands
    style_parser = subparsers.add_parser("style", help="Style Bible operations")
    style_subparsers = style_parser.add_subparsers(dest="style_command", help="Style subcommands")

    style_templates = style_subparsers.add_parser("templates", help="List available Style Bible templates")
    style_templates.add_argument("--json", action="store_true", help="Output in JSON format")
    style_templates.set_defaults(func=cmd_style_templates)

    style_init = style_subparsers.add_parser("init", help="Initialize Style Bible from template")
    style_init.add_argument("--project-id", required=True, help="Project ID")
    style_init.add_argument("--template", default="default_web_serial", help="Template ID (default: default_web_serial)")
    style_init.add_argument("--create-project", action="store_true", help="Auto-create project row if it does not exist")
    style_init.add_argument("--set", action="append", help="Override field (key=value, can repeat)")
    style_init.add_argument("--json", action="store_true", help="Output in JSON format")
    style_init.set_defaults(func=cmd_style_init)

    style_show = style_subparsers.add_parser("show", help="Show Style Bible for a project")
    style_show.add_argument("--project-id", required=True, help="Project ID")
    style_show.add_argument("--json", action="store_true", help="Output in JSON format")
    style_show.set_defaults(func=cmd_style_show)

    style_update = style_subparsers.add_parser("update", help="Update Style Bible fields")
    style_update.add_argument("--project-id", required=True, help="Project ID")
    style_update.add_argument("--set", action="append", help="Set field (key=value, can repeat)")
    style_update.add_argument("--json", action="store_true", help="Output in JSON format")
    style_update.set_defaults(func=cmd_style_update)

    style_check = style_subparsers.add_parser("check", help="Check chapter against Style Bible")
    style_check.add_argument("--project-id", required=True, help="Project ID")
    style_check.add_argument("--chapter", type=int, required=True, help="Chapter number")
    style_check.add_argument("--json", action="store_true", help="Output in JSON format")
    style_check.set_defaults(func=cmd_style_check)

    style_delete = style_subparsers.add_parser("delete", help="Delete Style Bible for a project")
    style_delete.add_argument("--project-id", required=True, help="Project ID")
    style_delete.add_argument("--json", action="store_true", help="Output in JSON format")
    style_delete.set_defaults(func=cmd_style_delete)

    # Legacy aliases: 'init' → 'init-db', 'run' → 'run-chapter'
    init_compat = subparsers.add_parser("init", help="Initialize the database (legacy alias for init-db)")
    init_compat.set_defaults(func=cmd_init_db)

    run_compat = subparsers.add_parser("run", help="Run chapter production (legacy alias for run-chapter)")
    run_compat.add_argument("--project-id", required=True, help="Project ID")
    run_compat.add_argument("--chapter", type=int, required=True, help="Chapter number")
    run_compat.add_argument("--status", default="planned", help="Initial chapter status (ignored in v1.3)")
    run_compat.add_argument("--stream", action="store_true", help="Stream output (ignored in v1.3)")
    run_compat.set_defaults(func=cmd_run_chapter)

    return parser


def main() -> None:
    """Entry point for novelos command."""
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)
