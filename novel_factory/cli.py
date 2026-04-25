"""Novel Factory CLI — command-line interface for v3.6.

Provides the ``novelos`` console script and preserves ``python -m novel_factory.cli``
compatibility.

Commands:
    init-db          Initialize the database
    run-chapter      Drive a chapter through the production pipeline
    status           Show chapter status
    runs             Show workflow runs for a project
    artifacts        Show artifacts for a chapter
    human-resume     Resume a blocked chapter to a new status
    config show      Show current configuration
    config validate  Validate configuration
    seed-demo        Seed demo project data
    smoke-run        Run a smoke test on demo project
    doctor           Run system diagnostics
    batch run        Run batch production for multiple chapters
    batch status     Get batch production run status
    batch enqueue    Enqueue a batch production request (v3.4)
    batch queue-run  Execute next pending queue item (v3.4)
    batch queue-status  Get production queue status (v3.4)
    batch queue-pause   Pause a queue item (v3.4)
    batch queue-resume  Resume a paused queue item (v3.4)
    batch queue-retry   Retry a failed/timed-out queue item (v3.4)
    batch queue-timeouts  Mark timed-out queue items (v3.4)
    batch queue-events   View queue item audit events (v3.5)
    batch queue-cancel   Cancel a queue item (v3.5)
    batch queue-recover  Recover a stuck running item (v3.5)
    batch queue-doctor   Diagnose queue item (v3.5)
    serial create    Create a serial plan (v3.6)
    serial status    Get serial plan status (v3.6)
    serial enqueue-next  Enqueue next batch for serial plan (v3.6)
    serial advance   Advance serial plan with decision (v3.6)
    serial pause     Pause a serial plan (v3.6)
    serial resume    Resume a paused serial plan (v3.6)
    serial cancel    Cancel a serial plan (v3.6)
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .config.loader import load_settings_with_cli, validate_settings
from .config.settings import Settings
from .db.connection import init_db
from .db.repository import Repository
from .dispatcher import Dispatcher
from .llm.provider import LLMProvider


# ── Helpers ──────────────────────────────────────────────────────


def _get_settings(args) -> Settings:
    """Load settings with explicit priority."""
    llm_mode = getattr(args, "llm_mode", "real")
    return load_settings_with_cli(
        config_path=getattr(args, "config", None),
        db_path=getattr(args, "db_path", None),
        llm_mode=llm_mode,
        llm_api_key=getattr(args, "llm_api_key", None),
        llm_base_url=getattr(args, "llm_base_url", None),
        llm_model=getattr(args, "llm_model", None),
    )


def _get_llm(settings: Settings, llm_mode: str = "real") -> LLMProvider:
    """Create LLM provider from settings and llm_mode.
    
    DEPRECATED: This function is kept for backward compatibility.
    Prefer _build_dispatcher() for v3.1+ agent-level routing.
    """
    if llm_mode == "stub":
        return _StubLLM()
    # real mode
    if not settings.llm.api_key:
        raise ValueError("LLM API key is required for real mode")
    from .llm.openai_compatible import OpenAICompatibleProvider
    return OpenAICompatibleProvider(settings.llm)


def _build_dispatcher(repo, settings: Settings, llm_mode: str = "real"):
    """Build Dispatcher with LLMRouter support (v3.1).
    
    This function implements the priority:
    1. Stub mode: uses _StubLLM (backward compatible)
    2. Real mode with llm_profiles: builds LLMRouter and passes to Dispatcher
    3. Real mode without llm_profiles: falls back to old _get_llm() for backward compatibility
    
    Args:
        repo: Repository instance
        settings: Settings instance
        llm_mode: "stub" or "real"
        
    Returns:
        Dispatcher instance with appropriate LLM configuration
    """
    # Stub mode: always use stub LLM, regardless of llm_profiles
    if llm_mode == "stub":
        stub_llm = _StubLLM()
        # If llm_profiles is configured, use LLMRouter with stub
        if settings.llm_profiles and len(settings.llm_profiles) > 0:
            from .llm.profiles import LLMProfilesConfig
            from .llm.router import LLMRouter
            
            config = LLMProfilesConfig(
                default_llm=settings.default_llm,
                llm_profiles=settings.llm_profiles,
                agent_llm=settings.agent_llm,
            )
            
            router = LLMRouter(config, stub_provider=stub_llm, llm_mode="stub")
            return Dispatcher(repo, llm_router=router, max_retries=settings.quality_gate.max_retries)
        else:
            # No llm_profiles, use single stub LLM
            return Dispatcher(repo, llm=stub_llm, max_retries=settings.quality_gate.max_retries)
    
    # Real mode: check if llm_profiles is configured
    if settings.llm_profiles and len(settings.llm_profiles) > 0:
        # Use LLMRouter for agent-level routing
        from .llm.profiles import LLMProfilesConfig
        from .llm.router import LLMRouter
        from .config.env_loader import load_dotenv, create_env_getter
        
        # Load .env for API keys (non-polluting)
        dotenv_vars = load_dotenv()
        
        # Create env getter with priority: OS env > .env > default
        env_getter = create_env_getter(dotenv_vars)
        
        # Build LLMProfilesConfig
        config = LLMProfilesConfig(
            default_llm=settings.default_llm,
            llm_profiles=settings.llm_profiles,
            agent_llm=settings.agent_llm,
        )
        
        # Create LLMRouter with custom env_getter
        router = LLMRouter(config, llm_mode=llm_mode, env_getter=env_getter)
        
        # Create Dispatcher with router
        return Dispatcher(repo, llm_router=router, max_retries=settings.quality_gate.max_retries)
    else:
        # Fallback to old single LLM for backward compatibility
        llm = _get_llm(settings, llm_mode)
        return Dispatcher(repo, llm=llm, max_retries=settings.quality_gate.max_retries)


class _StubLLM(LLMProvider):
    """Stub LLM that returns minimal valid outputs for each agent."""

    def invoke_json(self, messages, schema=None, temperature=None) -> dict:
        schema_name = getattr(schema, "__name__", "") if schema else ""
        if "Planner" in schema_name:
            return {
                "chapter_brief": {
                    "objective": "推进剧情",
                    "required_events": ["事件1"],
                    "plots_to_plant": [],
                    "plots_to_resolve": [],
                    "ending_hook": "悬念",
                    "constraints": [],
                }
            }
        if "Screenwriter" in schema_name:
            return {"scene_beats": [{"sequence": 1, "scene_goal": "场景目标", "conflict": "冲突", "hook": "钩子"}]}
        if "Author" in schema_name:
            # Generate content with conflict, dialogue, and hook to pass final_gate
            # Must be >= 500 characters, avoid death penalty words
            content = """林默推开房门，屋内弥漫着淡淡的茶香。他缓步走到窗前，凝望着外面的雨幕。
"你来了。"身后传来一个低沉的声音。林默转身，看到一个黑衣男子站在阴影中。
"你是谁？"林默警觉地问道，手已经摸向腰间的短剑。
"我是谁不重要，"黑衣男子缓缓走近，"重要的是，你正在寻找的东西，也在寻找你。"
林默心中一凛。这件事他从未告诉过任何人，这个人是怎么知道的？
"别紧张，"黑衣男子停下脚步，"我是来帮你的。但你必须做出选择。"
"什么选择？"林默紧盯着对方，随时准备出手。
"是继续寻找真相，还是保全你现在的平静生活。"黑衣男子的目光变得复杂。
林默沉默了片刻。窗外的雨越下越大，雷声隐隐传来。
"我已经没有退路了，"他终于说道，"不管前面是什么，我都必须走下去。"
黑衣男子点了点头。"很好。那么，从现在开始，你要小心身边的每一个人。"
说完，他的身影渐渐消失在阴影中，仿佛从未出现过。
林默站在原地，心中涌起一股不安。窗外的雨声似乎变得更加急促，仿佛在预示着什么。
他走到书桌前，翻开那本泛黄的笔记本。纸页上密密麻麻的字迹记录着这些年来的调查。
他拿起笔，在空白处写下今天的日期，然后停住了。笔尖悬在纸面上，迟迟没有落下。
最后，他只写了一句话：今天，一切都将改变。
就在这时，门外传来急促的敲门声。林默迅速合上笔记本，藏好短剑，然后走去开门。
门外站着一个陌生的年轻人，浑身湿透，目光中带着惊恐。
"救救我，"年轻人喘着气说，"他们...他们要杀我。"
林默还没来得及反应，远处就传来了脚步声。不止一个人，而且正在快速接近。
他一把将年轻人拉进屋内，关上门，然后吹灭了桌上的蜡烛。
黑暗中，他听到了自己的心跳声。这一刻，他知道，平静的日子已经结束了。"""
            return {
                "title": "测试章节",
                "content": content,
                "word_count": len(content),
                "implemented_events": ["事件1"],
                "used_plot_refs": [],
            }
        if "Polisher" in schema_name:
            # Return polished content (same as author for simplicity)
            content = """林默推开房门，屋内弥漫着淡淡的茶香。他缓步走到窗前，凝望着外面的雨幕。
"你来了。"身后传来一个低沉的声音。林默转身，看到一个黑衣男子站在阴影中。
"你是谁？"林默警觉地问道，手已经摸向腰间的短剑。
"我是谁不重要，"黑衣男子缓缓走近，"重要的是，你正在寻找的东西，也在寻找你。"
林默心中一凛。这件事他从未告诉过任何人，这个人是怎么知道的？
"别紧张，"黑衣男子停下脚步，"我是来帮你的。但你必须做出选择。"
"什么选择？"林默紧盯着对方，随时准备出手。
"是继续寻找真相，还是保全你现在的平静生活。"黑衣男子的目光变得复杂。
林默沉默了片刻。窗外的雨越下越大，雷声隐隐传来。
"我已经没有退路了，"他终于说道，"不管前面是什么，我都必须走下去。"
黑衣男子点了点头。"很好。那么，从现在开始，你要小心身边的每一个人。"
说完，他的身影渐渐消失在阴影中，仿佛从未出现过。
林默站在原地，心中涌起一股不安。窗外的雨声似乎变得更加急促，仿佛在预示着什么。
他走到书桌前，翻开那本泛黄的笔记本。纸页上密密麻麻的字迹记录着这些年来的调查。
他拿起笔，在空白处写下今天的日期，然后停住了。笔尖悬在纸面上，迟迟没有落下。
最后，他只写了一句话：今天，一切都将改变。
就在这时，门外传来急促的敲门声。林默迅速合上笔记本，藏好短剑，然后走去开门。
门外站着一个陌生的年轻人，浑身湿透，目光中带着惊恐。
"救救我，"年轻人喘着气说，"他们...他们要杀我。"
林默还没来得及反应，远处就传来了脚步声。不止一个人，而且正在快速接近。
他一把将年轻人拉进屋内，关上门，然后吹灭了桌上的蜡烛。
黑暗中，他听到了自己的心跳声。这一刻，他知道，平静的日子已经结束了。"""
            return {
                "content": content,
                "fact_change_risk": "none",
                "changed_scope": ["sentence", "rhythm"],
                "summary": "微调表达",
            }
        if "Editor" in schema_name:
            return {
                "pass": True,
                "score": 92,
                "scores": {"setting": 20, "logic": 20, "poison": 18, "text": 17, "pacing": 17},
                "issues": [],
                "suggestions": [],
                "revision_target": None,
                "state_card": {},
            }
        # v2 sidecar agents
        if "ScoutOutput" in schema_name:
            return {
                "market_report": {
                    "genre": "玄幻",
                    "platform": "起点",
                    "audience": "男性读者",
                    "trends": ["趋势1", "趋势2"],
                    "opportunities": ["机会1", "机会2"],
                    "reader_preferences": ["偏好1", "偏好2"],
                    "competitor_notes": ["竞品1", "竞品2"],
                    "summary": "市场分析摘要",
                    "recommendations": ["建议1", "建议2"]
                },
                "topic": "都市异能",
                "keywords": ["关键词1", "关键词2"]
            }
        if "ContinuityCheckerOutput" in schema_name:
            return {
                "report": {
                    "project_id": "demo",
                    "from_chapter": 1,
                    "to_chapter": 5,
                    "issues": [{
                        "issue_type": "character",
                        "severity": "warning",
                        "chapter_range": "1-5",
                        "description": "角色不一致",
                        "recommendation": "检查角色设定"
                    }],
                    "warnings": ["警告1"],
                    "state_card_consistency": True,
                    "character_consistency": True,
                    "plot_consistency": True,
                    "summary": "连续性检查摘要"
                },
                "agent_messages": []
            }
        if "ArchitectOutput" in schema_name:
            return {
                "proposals": [{
                    "proposal_type": "quality_rule",
                    "scope": "quality",
                    "title": "改进提案",
                    "description": "描述",
                    "risk_level": "medium",
                    "affected_area": ["editor"],
                    "recommendation": "建议",
                    "rationale": "理由",
                    "implementation_notes": "实施说明"
                }],
                "summary": "架构改进提案摘要",
                "total_proposals": 1
            }
        return {}

    def invoke_text(self, messages, temperature=None, max_tokens=None) -> str:
        return "{}"


def _print_output(data: Any, use_json: bool = False) -> None:
    """Print output in human-readable or JSON format."""
    if use_json:
        print(json.dumps(data, ensure_ascii=False, default=str, indent=2))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list):
                    print(f"{k}:")
                    for item in v:
                        print(f"  - {item}")
                else:
                    print(f"{k}: {v}")
        elif isinstance(data, list):
            for item in data:
                print(item)
        else:
            print(data)


# ── Command handlers ─────────────────────────────────────────────


def cmd_init_db(args) -> None:
    """Initialize the database."""
    settings = _get_settings(args)
    # Ensure parent directory exists
    from pathlib import Path
    db_dir = Path(settings.db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)
    print(f"Database initialized at: {settings.db_path}")


def cmd_run_chapter(args) -> dict:
    """Run a chapter through the production pipeline.
    
    Returns:
        Dict with chapter_status, steps, error, requires_human.
    """
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    llm_mode = getattr(args, "llm_mode", "real")
    
    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)

    result = dispatcher.run_chapter(
        project_id=args.project_id,
        chapter_number=args.chapter,
        max_steps=args.max_steps,
    )

    use_json = getattr(args, "json", False)
    
    # v3.1: Check for LLM configuration errors (distinguished by specific error messages)
    # Business logic errors (max_steps exceeded, requires_human) should NOT cause exit(1)
    error_msg = result.get("error", "")
    is_llm_config_error = "LLM configuration error" in error_msg or "API key" in error_msg or "base_url" in error_msg
    
    if is_llm_config_error:
        if use_json:
            # LLM config error: return error envelope
            envelope = {"ok": False, "error": error_msg, "data": result}
            print(json.dumps(envelope, ensure_ascii=False))
        else:
            _print_output(result, use_json)
        sys.exit(1)
    else:
        # Normal result (may include business errors like max_steps exceeded)
        if use_json:
            envelope = {"ok": True, "error": error_msg or None, "data": result}
            print(json.dumps(envelope, ensure_ascii=False))
        else:
            _print_output(result, use_json)
    
    return result


def cmd_status(args) -> None:
    """Show chapter status."""
    settings = _get_settings(args)
    repo = Repository(settings.db_path)

    chapter = repo.get_chapter(args.project_id, args.chapter)
    use_json = getattr(args, "json", False)

    if not chapter:
        if use_json:
            print(json.dumps({"error": "Chapter not found"}, ensure_ascii=False))
        else:
            print(f"No chapter found: project={args.project_id}, chapter={args.chapter}")
        sys.exit(1)

    # Get latest workflow run for this specific chapter
    runs = repo.get_workflow_runs_for_project(args.project_id, chapter_number=args.chapter, limit=1)
    latest_run = runs[0] if runs else None

    result = {
        "project_id": args.project_id,
        "chapter_number": args.chapter,
        "status": chapter["status"],
        "word_count": chapter.get("word_count", 0),
        "latest_run": latest_run,
    }

    # Add recent error if any
    if latest_run and latest_run.get("error_message"):
        result["recent_error"] = latest_run["error_message"]

    _print_output(result, use_json)


def cmd_runs(args) -> None:
    """Show workflow runs for a project."""
    settings = _get_settings(args)
    repo = Repository(settings.db_path)

    runs = repo.get_workflow_runs_for_project(args.project_id)
    use_json = getattr(args, "json", False)

    if use_json:
        _print_output(runs, use_json)
    else:
        if not runs:
            print(f"No workflow runs found for project={args.project_id}")
            return
        for run in runs:
            print(
                f"  [{run.get('status', '?')}] "
                f"run={run['id'][:8]}... "
                f"ch={run.get('chapter_number', '?')} "
                f"node={run.get('current_node', '-')} "
                f"started={run.get('started_at', '?')}"
            )
            if run.get("error_message"):
                print(f"    error: {run['error_message']}")


def cmd_artifacts(args) -> None:
    """Show artifacts for a chapter."""
    settings = _get_settings(args)
    repo = Repository(settings.db_path)

    artifacts = repo.get_artifacts_for_chapter(args.project_id, args.chapter)
    use_json = getattr(args, "json", False)

    if use_json:
        _print_output(artifacts, use_json)
    else:
        if not artifacts:
            print(f"No artifacts found: project={args.project_id}, chapter={args.chapter}")
            return
        for art in artifacts:
            print(
                f"  [{art.get('agent_id', '?')}] "
                f"type={art.get('artifact_type', '?')} "
                f"id={art.get('id', '?')[:8]}... "
                f"created={art.get('created_at', '?')}"
            )


def cmd_human_resume(args) -> None:
    """Resume a blocked chapter to a new status.
    
    Note: This command does NOT run Agents, so it does NOT require LLM validation.
    """
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    # human-resume does NOT run Agents, so we use a stub LLM to satisfy Dispatcher requirement
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, llm=stub_llm, max_retries=settings.quality_gate.max_retries)

    result = dispatcher.resume_blocked(
        project_id=args.project_id,
        chapter_number=args.chapter,
        status=args.status,
    )

    use_json = getattr(args, "json", False)
    if not result.get("ok"):
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)

    _print_output(result, use_json)


def cmd_config_show(args) -> None:
    """Show current configuration."""
    settings = _get_settings(args)
    use_json = getattr(args, "json", False)
    
    # Prepare data for output
    data = {
        "db_path": settings.db_path,
        "llm": {
            "provider": settings.llm.provider,
            "base_url": settings.llm.base_url,
            "api_key": "***" if settings.llm.api_key else "",
            "model": settings.llm.model,
            "temperature": settings.llm.temperature,
            "max_tokens": settings.llm.max_tokens,
        },
        "quality_gate": {
            "pass_score": settings.quality_gate.pass_score,
            "max_retries": settings.quality_gate.max_retries,
            "death_penalty_words": settings.quality_gate.death_penalty_words,
        },
        "workflow": {
            "task_timeout_minutes": settings.workflow.task_timeout_minutes,
            "checkpoint_enabled": settings.workflow.checkpoint_enabled,
        },
        "llm_mode": getattr(args, "llm_mode", "real"),
    }
    
    if use_json:
        print(json.dumps({"ok": True, "error": None, "data": data}, ensure_ascii=False))
    else:
        print("Configuration:")
        print(f"  DB path: {data['db_path']}")
        print(f"  LLM mode: {data['llm_mode']}")
        print(f"  LLM provider: {data['llm']['provider']}")
        print(f"  LLM base URL: {data['llm']['base_url']}")
        print(f"  LLM API key: {data['llm']['api_key']}")
        print(f"  LLM model: {data['llm']['model']}")
        print(f"  LLM temperature: {data['llm']['temperature']}")
        print(f"  Quality pass score: {data['quality_gate']['pass_score']}")
        print(f"  Max retries: {data['quality_gate']['max_retries']}")
        print(f"  Task timeout (minutes): {data['workflow']['task_timeout_minutes']}")
        print(f"  Checkpoint enabled: {data['workflow']['checkpoint_enabled']}")


def cmd_config_validate(args) -> None:
    """Validate configuration."""
    settings = _get_settings(args)
    llm_mode = getattr(args, "llm_mode", "real")
    issues = validate_settings(settings, llm_mode)
    use_json = getattr(args, "json", False)
    
    if use_json:
        if issues:
            print(json.dumps({"ok": False, "error": "; ".join(issues), "data": {"issues": issues}}, ensure_ascii=False))
        else:
            print(json.dumps({"ok": True, "error": None, "data": {"issues": []}}, ensure_ascii=False))
    else:
        if issues:
            print("Configuration validation failed:")
            for issue in issues:
                print(f"  - {issue}")
            sys.exit(1)
        else:
            print("Configuration validation passed.")


# ── v3.1: LLM Profile Commands ───────────────────────────────────

def cmd_llm_profiles(args) -> None:
    """List all LLM profiles."""
    from .llm.profiles import LLMProfilesConfig
    from .llm.router import LLMRouter
    from .config.env_loader import load_dotenv, create_env_getter
    
    # Load .env (non-polluting)
    dotenv_vars = load_dotenv()
    env_getter = create_env_getter(dotenv_vars)
    
    settings = _get_settings(args)
    llm_mode = getattr(args, "llm_mode", "real")
    use_json = getattr(args, "json", False)
    
    # Build LLMProfilesConfig from settings
    config = LLMProfilesConfig(
        default_llm=settings.default_llm,
        llm_profiles=settings.llm_profiles,
        agent_llm=settings.agent_llm,
    )
    
    # Create router (stub mode doesn't need real keys)
    stub_llm = _StubLLM() if llm_mode == "stub" else None
    router = LLMRouter(config, stub_provider=stub_llm, llm_mode=llm_mode, env_getter=env_getter)
    
    # Get profiles
    profiles = router.list_profiles()
    
    if use_json:
        print(json.dumps({"ok": True, "error": None, "data": {"profiles": profiles}}, ensure_ascii=False, indent=2))
    else:
        print("LLM Profiles:")
        for name, info in profiles.items():
            print(f"\n  [{name}]")
            print(f"    provider: {info['provider']}")
            print(f"    base_url: {info['base_url']}")
            print(f"    api_key: {info['api_key']}")
            print(f"    model: {info['model']}")
            print(f"    temperature: {info['temperature']}")
            print(f"    max_tokens: {info['max_tokens']}")


def cmd_llm_route(args) -> None:
    """Show LLM route for an agent."""
    from .llm.profiles import LLMProfilesConfig
    from .llm.router import LLMRouter
    from .config.env_loader import load_dotenv, create_env_getter
    
    # Load .env (non-polluting)
    dotenv_vars = load_dotenv()
    env_getter = create_env_getter(dotenv_vars)
    
    settings = _get_settings(args)
    llm_mode = getattr(args, "llm_mode", "real")
    use_json = getattr(args, "json", False)
    agent_id = args.agent
    
    # Build LLMProfilesConfig from settings
    config = LLMProfilesConfig(
        default_llm=settings.default_llm,
        llm_profiles=settings.llm_profiles,
        agent_llm=settings.agent_llm,
    )
    
    # Create router (stub mode doesn't need real keys)
    stub_llm = _StubLLM() if llm_mode == "stub" else None
    router = LLMRouter(config, stub_provider=stub_llm, llm_mode=llm_mode, env_getter=env_getter)
    
    try:
        route_info = router.get_route_info(agent_id)
        
        if use_json:
            print(json.dumps({"ok": True, "error": None, "data": route_info}, ensure_ascii=False, indent=2))
        else:
            print(f"LLM Route for agent '{agent_id}':")
            print(f"  profile: {route_info['profile']}")
            print(f"  provider: {route_info['provider']}")
            print(f"  base_url: {route_info['base_url']}")
            print(f"  api_key: {route_info['api_key']}")
            print(f"  model: {route_info['model']}")
            print(f"  temperature: {route_info['temperature']}")
            print(f"  max_tokens: {route_info['max_tokens']}")
    except ValueError as e:
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)


def cmd_llm_validate(args) -> None:
    """Validate LLM configuration."""
    from .llm.profiles import LLMProfilesConfig
    from .llm.router import LLMRouter
    from .config.env_loader import load_dotenv, create_env_getter
    
    # Load .env (non-polluting)
    dotenv_vars = load_dotenv()
    env_getter = create_env_getter(dotenv_vars)
    
    settings = _get_settings(args)
    llm_mode = getattr(args, "llm_mode", "real")
    use_json = getattr(args, "json", False)
    
    # Build LLMProfilesConfig from settings
    config = LLMProfilesConfig(
        default_llm=settings.default_llm,
        llm_profiles=settings.llm_profiles,
        agent_llm=settings.agent_llm,
    )
    
    # Create router (stub mode doesn't need real keys)
    stub_llm = _StubLLM() if llm_mode == "stub" else None
    router = LLMRouter(config, stub_provider=stub_llm, llm_mode=llm_mode, env_getter=env_getter)
    
    # Validate
    result = router.validate()
    
    if use_json:
        if result["errors"]:
            print(json.dumps({"ok": False, "error": "; ".join(result["errors"]), "data": result}, ensure_ascii=False))
        else:
            print(json.dumps({"ok": True, "error": None, "data": result}, ensure_ascii=False, indent=2))
    else:
        if result["errors"]:
            print("LLM configuration validation failed:")
            for error in result["errors"]:
                print(f"  - {error}")
            sys.exit(1)
        else:
            print("LLM configuration validation passed.")
            if result["warnings"]:
                print("\nWarnings:")
                for warning in result["warnings"]:
                    print(f"  - {warning}")


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
        "INSERT INTO projects (project_id, name, genre, is_current) VALUES (?, ?, ?, 1)",
        (project_id, f"{project_id.title()} Novel", "fantasy"),
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
    llm_mode = getattr(args, "llm_mode", "stub")
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
            import io
            import sys
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
    
    result = dispatcher.run_chapter(
        project_id=project_id,
        chapter_number=chapter,
        max_steps=max_steps,
    )
    
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


def cmd_doctor(args) -> None:
    """Run system diagnostics."""
    import importlib.metadata
    import importlib.util
    import platform
    from pathlib import Path
    
    checks = []
    
    # Python version
    py_version = platform.python_version()
    checks.append({"check": "Python version", "status": "ok", "details": py_version})
    
    # Package version
    try:
        pkg_version = importlib.metadata.version("novel-factory")
        checks.append({"check": "Package version", "status": "ok", "details": pkg_version})
    except importlib.metadata.PackageNotFoundError:
        checks.append({"check": "Package version", "status": "warning", "details": "Not installed as package (running from source)"})
    
    # Schema files
    schema_path = Path(__file__).resolve().parent / "db" / "schema" / "000_base_schema.sql"
    if schema_path.exists():
        checks.append({"check": "Base schema file", "status": "ok", "details": str(schema_path)})
    else:
        checks.append({"check": "Base schema file", "status": "error", "details": "Not found"})
    
    # Config files
    config_path = Path(__file__).resolve().parent / "config" / "llm.yaml"
    if config_path.exists():
        checks.append({"check": "Config file (llm.yaml)", "status": "ok", "details": str(config_path)})
    else:
        checks.append({"check": "Config file (llm.yaml)", "status": "warning", "details": "Not found"})
    
    # DB path writable
    settings = _get_settings(args)
    db_path = Path(settings.db_path)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        checks.append({"check": "DB directory writable", "status": "ok", "details": str(db_path.parent)})
    except Exception as e:
        checks.append({"check": "DB directory writable", "status": "error", "details": f"Cannot create: {e}"})
    
    # LLM config
    if settings.llm.api_key:
        checks.append({"check": "LLM API key", "status": "ok", "details": "Configured (hidden)"})
    else:
        checks.append({"check": "LLM API key", "status": "warning", "details": "Not configured (real mode will fail)"})
    
    # CLI entry point
    checks.append({"check": "CLI entry point", "status": "ok", "details": "novelos command available"})
    
    use_json = getattr(args, "json", False)
    if use_json:
        result = {
            "ok": all(c["status"] in ("ok", "warning") for c in checks),
            "error": None if all(c["status"] in ("ok", "warning") for c in checks) else "Some checks failed",
            "data": {"checks": checks}
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("System Diagnostics:")
        for check in checks:
            icon = "✓" if check["status"] == "ok" else "⚠" if check["status"] == "warning" else "✗"
            print(f"  {icon} {check['check']}: {check['details']}")
        
        if any(c["status"] == "error" for c in checks):
            print("\nSome checks failed. Please fix errors before proceeding.")
            sys.exit(1)
        elif any(c["status"] == "warning" for c in checks):
            print("\nSome warnings present. System may have limited functionality.")
        else:
            print("\nAll checks passed.")


def cmd_scout(args) -> None:
    """Generate market report using Scout agent."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    llm_mode = getattr(args, "llm_mode", "real")
    
    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)
    
    result = dispatcher.run_scout(
        project_id=args.project_id,
        topic=getattr(args, "topic", None),
        genre=getattr(args, "genre", None),
        platform=getattr(args, "platform", None),
        audience=getattr(args, "audience", None),
    )
    
    use_json = getattr(args, "json", False)
    if not result.get("ok"):
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)
    
    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report = result.get("market_report", {})
        print(f"Market Report (ID: {result.get('report_id')})")
        print(f"Genre: {report.get('genre', 'N/A')}")
        print(f"\nSummary: {report.get('summary', 'N/A')}")
        print(f"\nTrends:")
        for trend in report.get("trends", []):
            print(f"  - {trend}")
        print(f"\nOpportunities:")
        for opp in report.get("opportunities", []):
            print(f"  - {opp}")
        print(f"\nRecommendations:")
        for rec in report.get("recommendations", []):
            print(f"  - {rec}")


def cmd_report_daily(args) -> None:
    """Generate daily report using Secretary agent."""
    from .agents.secretary import SecretaryAgent
    
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    secretary = SecretaryAgent(repo)
    
    result = secretary.generate_daily_report(
        project_id=args.project_id,
        date=getattr(args, "date", None),
    )
    
    use_json = getattr(args, "json", False)
    if not result.get("ok"):
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)
    
    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report = result.get("report", {})
        print(f"Daily Report - {report.get('date', 'N/A')}")
        print(f"Project: {report.get('project_id', 'N/A')}")
        print(f"\nTotal runs: {report.get('total_runs', 0)}")
        print(f"Successful: {report.get('successful_runs', 0)}")
        print(f"Failed: {report.get('failed_runs', 0)}")
        print(f"\nChapter Status Distribution:")
        for status, count in sorted(report.get("chapter_status_distribution", {}).items()):
            print(f"  - {status}: {count}")
        if report.get("recent_errors"):
            print(f"\nRecent Errors:")
            for error in report["recent_errors"][:5]:
                print(f"  - {error[:100]}")


def cmd_export_chapter(args) -> None:
    """Export chapter using Secretary agent."""
    from .agents.secretary import SecretaryAgent
    
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    secretary = SecretaryAgent(repo)
    
    result = secretary.export_chapter(
        project_id=args.project_id,
        chapter_number=args.chapter,
        export_format=getattr(args, "format", "markdown"),
    )
    
    use_json = getattr(args, "json", False)
    if not result.get("ok"):
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)
    
    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # Print the formatted output
        data = result.get("data", {})
        output = data.get("output", "")
        print(output)


def cmd_continuity_check(args) -> None:
    """Check cross-chapter continuity using ContinuityChecker agent."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    llm_mode = getattr(args, "llm_mode", "real")
    
    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)
    
    result = dispatcher.run_continuity_check(
        project_id=args.project_id,
        from_chapter=args.from_chapter,
        to_chapter=args.to_chapter,
    )
    
    use_json = getattr(args, "json", False)
    if not result.get("ok"):
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)
    
    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report = result.get("report", {})
        print(f"Continuity Report (ID: {result.get('report_id')})")
        print(f"Chapters: {report.get('from_chapter')}-{report.get('to_chapter')}")
        print(f"\nSummary: {report.get('summary', 'N/A')}")
        print(f"\nConsistency Checks:")
        print(f"  State Card: {'✓' if report.get('state_card_consistency') else '✗'}")
        print(f"  Character: {'✓' if report.get('character_consistency') else '✗'}")
        print(f"  Plot: {'✓' if report.get('plot_consistency') else '✗'}")
        
        issues = report.get("issues", [])
        if issues:
            print(f"\nIssues ({len(issues)}):")
            for issue in issues[:10]:
                print(f"  [{issue.get('severity', 'info').upper()}] {issue.get('issue_type')}: {issue.get('description')}")


def cmd_architect_suggest(args) -> None:
    """Generate architecture improvement proposals."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    llm_mode = getattr(args, "llm_mode", "real")
    
    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)
    
    result = dispatcher.run_architect_suggest(
        project_id=args.project_id,
        scope=getattr(args, "scope", "quality"),
    )
    
    use_json = getattr(args, "json", False)
    
    # v3.1: run_architect_suggest already returns {ok, error, data} format
    # Check for LLM configuration errors (distinguished by ok=false and specific error messages)
    error_msg = result.get("error", "")
    is_llm_config_error = not result.get("ok") and (
        "LLM configuration error" in error_msg or 
        "API key" in error_msg or 
        "base_url" in error_msg
    )
    
    if is_llm_config_error:
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Error: {error_msg}")
        sys.exit(1)
    else:
        # Normal result
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            data = result.get("data", {})
            print(f"Architecture Proposals for {args.project_id}:")
            print(f"  Scope: {data.get('scope', 'N/A')}")
            print(f"  Proposals: {len(data.get('proposals', []))}")
            for i, proposal in enumerate(data.get("proposals", [])[:5], 1):
                print(f"\n  Proposal {i}:")
                print(f"    Title: {proposal.get('title', 'N/A')}")
                print(f"    Risk: {proposal.get('risk_level', 'N/A')}")
                print(f"    Recommendation: {proposal.get('recommendation', 'N/A')[:100]}...")


def cmd_skill_list(args) -> None:
    """List available skills."""
    from .skills.registry import SkillRegistry
    
    settings = _get_settings(args)
    
    try:
        registry = SkillRegistry()  # Use default config path
        skills = registry.list_skills()
        
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": True, "error": None, "data": {"skills": skills}}, ensure_ascii=False, indent=2))
        else:
            print("Available Skills:")
            for skill in skills:
                status = "enabled" if skill.get("enabled") else "disabled"
                print(f"  - {skill.get('id')}: {skill.get('type')} ({status})")
                print(f"      Class: {skill.get('class')}")
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)


def cmd_skill_run(args) -> None:
    """Run a skill."""
    from .skills.registry import SkillRegistry
    
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    skill_id = getattr(args, "skill_id", "")
    text = getattr(args, "text", None)
    project_id = getattr(args, "project_id", None)
    chapter = getattr(args, "chapter", None)
    input_json_str = getattr(args, "input_json", None)
    
    # Build payload
    payload = {}
    
    # Priority: --input-json > --text
    if input_json_str:
        try:
            payload = json.loads(input_json_str)
        except json.JSONDecodeError as e:
            if getattr(args, "json", False):
                print(json.dumps({"ok": False, "error": f"Invalid JSON input: {e}", "data": {}}, ensure_ascii=False))
            else:
                print(f"Error: Invalid JSON input: {e}")
            sys.exit(1)
    elif text:
        payload["text"] = text
    
    # Add project_id and chapter to payload if provided
    if project_id:
        payload["project_id"] = project_id
    if chapter:
        payload["chapter_number"] = chapter
    
    try:
        registry = SkillRegistry()  # Use default config path
        # v2.2: Use run_skill with agent="manual" and stage="manual"
        result = registry.run_skill(skill_id, payload, agent="manual", stage="manual")
        
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result.get("ok"):
                print(f"Skill '{skill_id}' executed successfully.")
                data = result.get("data", {})
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print(f"Error: {result.get('error')}")
                sys.exit(1)
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)


def cmd_skill_show(args) -> None:
    """Show skill manifest details (v2.2)."""
    from .skills.registry import SkillRegistry
    
    settings = _get_settings(args)
    
    skill_id = getattr(args, "skill_id", "")
    
    try:
        registry = SkillRegistry()
        manifest = registry.get_manifest(skill_id)
        
        if not manifest:
            # No manifest, show v2.1 compatibility info
            skill_config = registry.skills_config.get(skill_id)
            if not skill_config:
                use_json = getattr(args, "json", False)
                if use_json:
                    print(json.dumps({"ok": False, "error": f"Skill not found: {skill_id}", "data": {}}, ensure_ascii=False))
                else:
                    print(f"Error: Skill not found: {skill_id}")
                sys.exit(1)
            
            # Show v2.1 info
            use_json = getattr(args, "json", False)
            if use_json:
                print(json.dumps({
                    "ok": True,
                    "error": None,
                    "data": {
                        "id": skill_id,
                        "type": skill_config.get("type"),
                        "enabled": skill_config.get("enabled", True),
                        "class": skill_config.get("class"),
                        "description": skill_config.get("description", ""),
                        "manifest": None,
                    }
                }, ensure_ascii=False, indent=2))
            else:
                print(f"Skill: {skill_id}")
                print(f"  Type: {skill_config.get('type')}")
                print(f"  Enabled: {skill_config.get('enabled', True)}")
                print(f"  Class: {skill_config.get('class')}")
                print(f"  Description: {skill_config.get('description', '')}")
                print("  Manifest: None (v2.1 compatibility)")
            return
        
        # Show manifest info
        use_json = getattr(args, "json", False)
        if use_json:
            # Get skill config for package info
            skill_config = registry.skills_config.get(skill_id, {})
            manifest_dict = manifest.model_dump()
            
            # Add package field from skills.yaml
            if skill_config.get("package"):
                manifest_dict["package"] = skill_config["package"]
            
            print(json.dumps({
                "ok": True,
                "error": None,
                "data": manifest_dict
            }, ensure_ascii=False, indent=2))
        else:
            print(f"Skill: {manifest.id}")
            print(f"  Name: {manifest.name}")
            print(f"  Version: {manifest.version}")
            print(f"  Kind: {manifest.kind}")
            print(f"  Description: {manifest.description}")
            print(f"  Enabled: {manifest.enabled}")
            print(f"  Builtin: {manifest.builtin}")
            print(f"  Class: {manifest.class_name}")
            print(f"  Allowed Agents: {', '.join(manifest.allowed_agents)}")
            print(f"  Allowed Stages: {', '.join(manifest.allowed_stages)}")
            print(f"  Permissions:")
            print(f"    transform_text: {manifest.permissions.transform_text}")
            print(f"    validate_text: {manifest.permissions.validate_text}")
            print(f"    write_skill_run: {manifest.permissions.write_skill_run}")
            print(f"  Failure Policy:")
            print(f"    on_error: {manifest.failure_policy.on_error}")
            print(f"    max_retries: {manifest.failure_policy.max_retries}")
            if manifest.package:
                print(f"  Package:")
                print(f"    name: {manifest.package.name}")
                print(f"    handler: {manifest.package.handler}")
                print(f"    entry_class: {manifest.package.entry_class}")
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)


def cmd_skill_validate(args) -> None:
    """Validate all skill manifests (v2.2)."""
    from .skills.registry import SkillRegistry
    
    settings = _get_settings(args)
    
    try:
        registry = SkillRegistry()
        result = registry.validate_all()
        
        use_json = getattr(args, "json", False)
        if use_json:
            # Wrap in envelope format
            envelope = {
                "ok": result.get("ok", False),
                "error": None if result.get("ok") else "; ".join(result.get("errors", [])),
                "data": {
                    "errors": result.get("errors", []),
                    "warnings": result.get("warnings", [])
                }
            }
            print(json.dumps(envelope, ensure_ascii=False, indent=2))
        else:
            if result["ok"]:
                print("All skill manifests are valid.")
                if result["warnings"]:
                    print("\nWarnings:")
                    for warning in result["warnings"]:
                        print(f"  - {warning}")
            else:
                print("Skill manifest validation failed.")
                print("\nErrors:")
                for error in result["errors"]:
                    print(f"  - {error}")
                if result["warnings"]:
                    print("\nWarnings:")
                    for warning in result["warnings"]:
                        print(f"  - {warning}")
                sys.exit(1)
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)


def cmd_skill_test(args) -> None:
    """Run skill fixtures test (v2.3)."""
    from .skills.registry import SkillRegistry
    
    settings = _get_settings(args)
    
    skill_id = getattr(args, "skill_id", None)
    test_all = getattr(args, "all", False)
    
    try:
        registry = SkillRegistry()
        
        if test_all:
            # Test all skills with packages
            skills = registry.list_skills()
            package_skills = [s for s in skills if s.get("package")]
            
            if not package_skills:
                print("No skills with packages found.")
                return
            
            all_results = {}
            total_passed = 0
            total_failed = 0
            
            for skill_info in package_skills:
                skill_id = skill_info["id"]
                result = registry.test_skill(skill_id)
                all_results[skill_id] = result
                
                if result.get("ok"):
                    total_passed += 1
                else:
                    total_failed += 1
            
            use_json = getattr(args, "json", False)
            if use_json:
                print(json.dumps({
                    "ok": total_failed == 0,
                    "error": None if total_failed == 0 else f"{total_failed}/{len(package_skills)} skills failed",
                    "data": {
                        "passed": total_passed,
                        "failed": total_failed,
                        "total": len(package_skills),
                        "results": all_results,
                    }
                }, ensure_ascii=False, indent=2))
            else:
                print(f"Test Results: {total_passed}/{len(package_skills)} passed")
                print()
                for skill_id, result in all_results.items():
                    data = result.get("data", {})
                    passed = data.get("passed", 0)
                    total = data.get("total", 0)
                    status = "✓" if result.get("ok") else "✗"
                    print(f"  {status} {skill_id}: {passed}/{total} cases passed")
                
                if total_failed > 0:
                    sys.exit(1)
        else:
            # Test single skill
            if not skill_id:
                use_json = getattr(args, "json", False)
                if use_json:
                    print(json.dumps({
                        "ok": False,
                        "error": "skill_id is required (or use --all)",
                        "data": {}
                    }, ensure_ascii=False))
                else:
                    print("Error: skill_id is required (or use --all)")
                sys.exit(1)
            
            result = registry.test_skill(skill_id)
            
            use_json = getattr(args, "json", False)
            if use_json:
                # Ensure envelope format: {ok, error, data}
                # Ensure data is always a dict, never null
                data = result.get("data")
                if data is None:
                    data = {}
                
                envelope = {
                    "ok": result.get("ok", False),
                    "error": result.get("error") if not result.get("ok") else None,
                    "data": data
                }
                print(json.dumps(envelope, ensure_ascii=False, indent=2))
            else:
                data = result.get("data", {})
                passed = data.get("passed", 0)
                failed = data.get("failed", 0)
                total = data.get("total", 0)
                
                if result.get("ok"):
                    print(f"✓ All {total} test cases passed for skill '{skill_id}'")
                else:
                    print(f"✗ {failed}/{total} test cases failed for skill '{skill_id}'")
                    print()
                    print("Failed cases:")
                    for case in data.get("cases", []):
                        if not case.get("passed"):
                            print(f"  - {case.get('name')}")
                            if case.get("result", {}).get("error"):
                                print(f"    Error: {case['result']['error']}")
                    sys.exit(1)
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)


def cmd_quality_check(args) -> None:
    """Run quality check on a chapter."""
    from .quality.hub import QualityHub
    from .skills.registry import SkillRegistry
    
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    project_id = getattr(args, "project_id", "")
    chapter = getattr(args, "chapter", 1)
    stage = getattr(args, "stage", "draft")
    
    try:
        repo = Repository(settings.db_path)
        skill_registry = SkillRegistry()  # Use default config path
        hub = QualityHub(repo, skill_registry)
        
        # Get chapter content
        chapter_data = repo.get_chapter(project_id, chapter)
        if not chapter_data:
            if getattr(args, "json", False):
                print(json.dumps({"ok": False, "error": f"Chapter not found: {project_id}/{chapter}", "data": {}}, ensure_ascii=False))
            else:
                print(f"Error: Chapter not found: {project_id}/{chapter}")
            sys.exit(1)
        
        content = chapter_data.get("content")
        
        # R1: Handle empty content or planned chapters
        if content is None:
            content = ""
        
        # Run quality check based on stage
        if stage == "draft":
            result = hub.check_draft(project_id, chapter, content)
        elif stage == "polished":
            # Get original draft for comparison
            versions = repo.get_chapter_versions(project_id, chapter)
            original = versions[0].get("content") if versions else content
            if original is None:
                original = ""
            result = hub.check_polished(project_id, chapter, original, content)
        else:  # final
            result = hub.final_gate(project_id, chapter)
        
        # Save quality report
        if result.get("ok"):
            data = result.get("data", {})
            repo.save_quality_report(
                project_id=project_id,
                chapter_number=chapter,
                stage=stage,
                overall_score=data.get("overall_score", 0),
                pass_=data.get("pass", False),
                revision_target=data.get("revision_target"),
                blocking_issues=data.get("blocking_issues", []),
                warnings=data.get("warnings", []),
                skill_results=data.get("skill_results", []),
                quality_dimensions=data.get("quality_dimensions", {}),
            )
        
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result.get("ok"):
                data = result.get("data", {})
                status = "PASSED" if data.get("pass") else "FAILED"
                print(f"Quality Check ({stage}): {status}")
                print(f"  Overall Score: {data.get('overall_score', 0):.2f}")
                print(f"  Revision Target: {data.get('revision_target', 'N/A')}")
                
                if data.get("blocking_issues"):
                    print("\n  Blocking Issues:")
                    for issue in data.get("blocking_issues", []):
                        print(f"    - {issue.get('type')}: {issue.get('message')}")
                
                if data.get("warnings"):
                    print("\n  Warnings:")
                    for warning in data.get("warnings", []):
                        print(f"    - {warning}")
            else:
                print(f"Error: {result.get('error')}")
                sys.exit(1)
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)


def cmd_quality_report(args) -> None:
    """Show quality reports for a chapter."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    project_id = getattr(args, "project_id", "")
    chapter = getattr(args, "chapter", 1)
    limit = getattr(args, "limit", 5)
    
    try:
        repo = Repository(settings.db_path)
        reports = repo.get_quality_reports(project_id, chapter, limit=limit)
        
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": True, "error": None, "data": {"reports": reports}}, ensure_ascii=False, indent=2))
        else:
            print(f"Quality Reports for {project_id}/{chapter}:")
            if not reports:
                print("  No reports found.")
            else:
                for i, report in enumerate(reports, 1):
                    status = "PASSED" if report.get("pass") else "FAILED"
                    print(f"\n  Report {i}:")
                    print(f"    Stage: {report.get('stage', 'N/A')}")
                    print(f"    Status: {status}")
                    print(f"    Score: {report.get('overall_score', 0):.2f}")
                    print(f"    Created: {report.get('created_at', 'N/A')}")
                    
                    if report.get("blocking_issues"):
                        print(f"    Blocking Issues: {len(report.get('blocking_issues', []))}")
                    if report.get("warnings"):
                        print(f"    Warnings: {len(report.get('warnings', []))}")
    except Exception as e:
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
            sys.exit(1)


# ── Batch Production commands (v3.0) ───────────────────────────────


def cmd_batch_run(args) -> None:
    """Run batch production for multiple chapters."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    llm_mode = getattr(args, "llm_mode", "real")
    
    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)
    
    result = dispatcher.run_batch(
        project_id=args.project_id,
        from_chapter=args.from_chapter,
        to_chapter=args.to_chapter,
    )
    
    use_json = getattr(args, "json", False)
    
    # v3.1: run_batch already returns {ok, error, data} format
    # Check for LLM configuration errors (distinguished by ok=false and specific error messages)
    # Business logic errors (blocked chapter) should NOT cause exit(1)
    error_msg = result.get("error", "")
    is_llm_config_error = not result.get("ok") and (
        "LLM configuration error" in error_msg or 
        "API key" in error_msg or 
        "base_url" in error_msg
    )
    
    if is_llm_config_error:
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            _print_output(result, use_json)
        sys.exit(1)
    else:
        # Normal result (may include business errors like blocked chapter)
        if use_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            _print_output(result, use_json)


def cmd_batch_status(args) -> None:
    """Get batch production run status."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    # batch-status does NOT run Agents, so we use a stub LLM
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.get_batch_status(args.run_id)
    
    use_json = getattr(args, "json", False)
    _print_output(result, use_json)


def cmd_batch_review(args) -> None:
    """Record human review decision for a batch production run."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    # batch-review does NOT run Agents, so we use a stub LLM
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.review_batch(
        run_id=args.run_id,
        decision=args.decision,
        notes=getattr(args, "notes", None),
    )
    
    use_json = getattr(args, "json", False)
    _print_output(result, use_json)


def cmd_batch_revise(args) -> None:
    """Create and execute a batch revision plan (v3.2)."""
    import json as json_module
    
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    llm_mode = getattr(args, "llm_mode", "real")
    
    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)
    
    # Create revision plan
    plan_result = dispatcher.create_batch_revision_plan(
        run_id=args.run_id,
        plan_json=args.plan_json,
    )
    
    if not plan_result.get("ok"):
        use_json = getattr(args, "json", False)
        if use_json:
            print(json.dumps(plan_result, ensure_ascii=False))
        else:
            print(f"Error: {plan_result.get('error')}")
        sys.exit(1)
    
    # Execute revision
    revision_run_id = plan_result["data"]["revision_run_id"]
    run_result = dispatcher.run_batch_revision(revision_run_id)
    
    use_json = getattr(args, "json", False)
    if use_json:
        # Merge results
        result = {
            "ok": run_result.get("ok", True),
            "error": run_result.get("error"),
            "data": {
                "run_id": args.run_id,
                "revision_run_id": revision_run_id,
                "affected_chapters": plan_result["data"]["affected_chapters"],
                "status": run_result["data"]["status"],
            }
        }
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"Revision Run ID: {revision_run_id}")
        print(f"Affected Chapters: {plan_result['data']['affected_chapters']}")
        print(f"Status: {run_result['data']['status']}")
        if run_result.get("error"):
            print(f"Error: {run_result['error']}")


def cmd_batch_revision_status(args) -> None:
    """Get batch revision run status (v3.2)."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    # revision-status does NOT run Agents, so we use a stub LLM
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.get_batch_revision_status(args.revision_run_id)
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Revision Run ID: {data['revision_run_id']}")
            print(f"Source Run ID: {data['source_run_id']}")
            print(f"Status: {data['status']}")
            print(f"Affected Chapters: {data['affected_chapters']}")
            print("\nItems:")
            for item in data["items"]:
                status_str = f"  Chapter {item['chapter_number']}: {item['status']}"
                if item.get("error"):
                    status_str += f" (Error: {item['error']})"
                print(status_str)
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_continuity(args) -> None:
    """Run batch continuity gate for a production run (v3.3)."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    llm_mode = getattr(args, "llm_mode", "real")
    
    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)
    
    result = dispatcher.run_batch_continuity_gate(args.run_id)
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Continuity Gate (ID: {data['gate_id']})")
            print(f"  Status: {data['status']}")
            print(f"  Issue Count: {data['issue_count']}")
            print(f"  Summary: {data['summary']}")
            if data.get("blocking_issues"):
                print(f"  Blocking Issues:")
                for issue in data["blocking_issues"]:
                    print(f"    [{issue.get('severity', '').upper()}] {issue.get('issue_type')}: {issue.get('description')}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_continuity_status(args) -> None:
    """Get batch continuity gate status (v3.3)."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.get_batch_continuity_gate_status(args.run_id)
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            gate = data.get("gate")
            if gate:
                print(f"Continuity Gate (ID: {gate['id']})")
                print(f"  Status: {gate['status']}")
                print(f"  Issue Count: {gate.get('issue_count', 0)}")
                print(f"  Summary: {gate.get('summary', 'N/A')}")
                if gate.get("blocking_issues"):
                    print(f"  Blocking Issues:")
                    for issue in gate["blocking_issues"]:
                        print(f"    [{issue.get('severity', '').upper()}] {issue.get('issue_type')}: {issue.get('description')}")
            else:
                print(f"Continuity Gate: not_run")
        else:
            print(f"Error: {result.get('error')}")


# ── v3.4 Production Queue commands ────────────────────────────────


def cmd_batch_enqueue(args) -> None:
    """Enqueue a batch production request."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    max_chapters = getattr(args, "max_chapters", 50)
    
    result = dispatcher.enqueue_batch(
        project_id=args.project_id,
        from_chapter=args.from_chapter,
        to_chapter=args.to_chapter,
        priority=getattr(args, "priority", 100),
        max_attempts=getattr(args, "max_attempts", 3),
        timeout_minutes=getattr(args, "timeout_minutes", 120),
        max_chapters=max_chapters,
    )
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Queue item created: {data['queue_id']} (status: {data['status']})")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_run(args) -> None:
    """Execute the next pending queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    llm_mode = getattr(args, "llm_mode", "real")
    
    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)
    
    result = dispatcher.run_queue_once()
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            if data.get("status") == "idle":
                print(data.get("message", "No pending queue items"))
            else:
                print(f"Queue item completed: {data.get('queue_id')}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_status(args) -> None:
    """Get production queue status."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.get_queue_status(
        project_id=getattr(args, "project_id", None),
        status=getattr(args, "status", None),
    )
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            items = result["data"].get("items", [])
            if not items:
                print("No queue items found.")
            else:
                for item in items:
                    print(
                        f"  [{item['status']}] {item['queue_id']} "
                        f"project={item['project_id']} "
                        f"ch={item['from_chapter']}-{item['to_chapter']} "
                        f"priority={item['priority']} "
                        f"attempts={item['attempt_count']}/{item['max_attempts']}"
                    )
                    if item.get("last_error"):
                        print(f"    error: {item['last_error']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_pause(args) -> None:
    """Pause a production queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.pause_queue_item(args.queue_id)
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Queue item paused: {result['data']['queue_id']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_resume(args) -> None:
    """Resume a paused queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.resume_queue_item(args.queue_id)
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Queue item resumed: {result['data']['queue_id']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_retry(args) -> None:
    """Retry a failed or timed-out queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.retry_queue_item(args.queue_id)
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Queue item retried: {data['queue_id']} (attempt {data['attempt_count']})")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_timeouts(args) -> None:
    """Mark timed-out queue items."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.mark_queue_timeouts()
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            count = result["data"].get("timed_out_count", 0)
            print(f"Timed-out items marked: {count}")
        else:
            print(f"Error: {result.get('error')}")


# ── v3.5 Queue Runtime Hardening commands ───────────────────────────


def cmd_batch_queue_events(args) -> None:
    """View queue item audit events."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.get_queue_events(args.queue_id)
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Queue item: {data['queue_id']}")
            print(f"Events ({len(data['events'])}):")
            for event in data["events"]:
                print(f"  [{event['event_type']}] {event['from_status'] or '-'} → {event['to_status'] or '-'}")
                if event.get("message"):
                    print(f"    {event['message']}")
                print(f"    at {event['created_at']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_cancel(args) -> None:
    """Cancel a queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.cancel_queue_item(
        queue_id=args.queue_id,
        reason=getattr(args, "reason", None),
    )
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Queue item cancelled: {result['data']['queue_id']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_recover(args) -> None:
    """Recover a stuck running queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.recover_queue_item(
        queue_id=args.queue_id,
        force=getattr(args, "force", False),
    )
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Queue item recovered: {result['data']['queue_id']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_doctor(args) -> None:
    """Diagnose a queue item."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)
    
    result = dispatcher.doctor_queue_item(args.queue_id)
    
    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Queue item: {data['queue_id']}")
            print(f"Status: {data['status']}")
            print(f"Production run: {data.get('production_run_id') or 'N/A'}")
            print(f"\nChecks:")
            for check in data["checks"]:
                status = "✓" if check["pass"] else "✗"
                msg = check.get("message", "")
                print(f"  {status} {check['name']}: {msg or ('pass' if check['pass'] else 'fail')}")
            if data.get("recent_error"):
                print(f"\nRecent error: {data['recent_error']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_batch_queue_run_limit(args) -> None:
    """Execute multiple queue items."""
    settings = _get_settings(args)
    init_db(settings.db_path)
    
    repo = Repository(settings.db_path)
    llm_mode = getattr(args, "llm_mode", "real")
    
    try:
        dispatcher = _build_dispatcher(repo, settings, llm_mode)
    except ValueError as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e), "data": {}}, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)
    
    # Handle --once as --limit 1
    limit = getattr(args, "limit", 1)
    if getattr(args, "once", False):
        limit = 1
    
    result = dispatcher.run_queue(limit=limit)
    
    use_json = getattr(args, "json", False)
    
    # v3.4 backward compatibility: when limit=1 and stopped_reason=idle,
    # return the old format {"status": "idle"} instead of the new format
    is_v34_compat = (
        limit == 1
        and result.get("ok")
        and result.get("data", {}).get("stopped_reason") == "idle"
    )
    if is_v34_compat:
        runs = result.get("data", {}).get("runs", [])
        if runs and runs[0].get("ok"):
            v34_result = runs[0]  # The original run_queue_once result
        else:
            v34_result = result
    
    if use_json:
        if is_v34_compat:
            print(json.dumps(v34_result, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            if data.get("stopped_reason") == "idle" and data.get("executed", 0) == 0:
                print("No pending queue items")
            else:
                print(f"Executed {data['executed']}/{data['limit']} queue items")
                if data.get("stopped_reason"):
                    print(f"Stopped: {data['stopped_reason']}")
                for i, run in enumerate(data.get("runs", []), 1):
                    if run.get("ok"):
                        run_data = run.get("data", {})
                        if run_data.get("status") == "idle":
                            print(f"  Run {i}: idle")
                        else:
                            print(f"  Run {i}: {run_data.get('queue_id')} → {run_data.get('status')}")
                    else:
                        print(f"  Run {i}: failed - {run.get('error')}")
        else:
            print(f"Error: {result.get('error')}")


# ── Serial commands (v3.6) ──────────────────────────────────────────────


def cmd_serial_create(args) -> None:
    """Create a new serial plan."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.create_serial_plan(
        project_id=args.project_id,
        name=args.name,
        start_chapter=args.start_chapter,
        target_chapter=args.target_chapter,
        batch_size=args.batch_size,
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Serial plan created: {data['serial_plan_id']}")
            print(f"Status: {data['status']}")
            print(f"Current chapter: {data['current_chapter']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_serial_status(args) -> None:
    """Get serial plan status."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.get_serial_status(args.serial_plan_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Serial plan: {data['serial_plan_id']}")
            print(f"Project: {data['project_id']}")
            print(f"Name: {data['name']}")
            print(f"Status: {data['status']}")
            print(f"Progress: {data['current_chapter']}/{data['target_chapter']}")
            print(f"Batch size: {data['batch_size']}")
            print(f"Completed chapters: {data['completed_chapters']}")
            if data.get("current_queue_id"):
                print(f"Current queue: {data['current_queue_id']}")
            if data.get("current_production_run_id"):
                print(f"Current production run: {data['current_production_run_id']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_serial_enqueue_next(args) -> None:
    """Enqueue next batch for serial plan."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.enqueue_serial_next(args.serial_plan_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Enqueued chapters {data['from_chapter']}-{data['to_chapter']}")
            print(f"Queue ID: {data['queue_id']}")
            print(f"Status: {data['status']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_serial_advance(args) -> None:
    """Advance serial plan with decision."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.advance_serial_plan(
        serial_plan_id=args.serial_plan_id,
        decision=args.decision,
        notes=getattr(args, "notes", None),
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            data = result["data"]
            print(f"Decision: {args.decision}")
            print(f"Status: {data['status']}")
            if "current_chapter" in data:
                print(f"Current chapter: {data['current_chapter']}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_serial_pause(args) -> None:
    """Pause a serial plan."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.pause_serial_plan(args.serial_plan_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Serial plan paused: {args.serial_plan_id}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_serial_resume(args) -> None:
    """Resume a paused serial plan."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.resume_serial_plan(args.serial_plan_id)

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Serial plan resumed: {args.serial_plan_id}")
        else:
            print(f"Error: {result.get('error')}")


def cmd_serial_cancel(args) -> None:
    """Cancel a serial plan."""
    settings = _get_settings(args)
    init_db(settings.db_path)

    repo = Repository(settings.db_path)
    stub_llm = _StubLLM()
    dispatcher = Dispatcher(repo, stub_llm, max_retries=3)

    result = dispatcher.cancel_serial_plan(
        serial_plan_id=args.serial_plan_id,
        reason=getattr(args, "reason", None),
    )

    use_json = getattr(args, "json", False)
    if use_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result.get("ok"):
            print(f"Serial plan cancelled: {args.serial_plan_id}")
        else:
            print(f"Error: {result.get('error')}")


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


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for novelos CLI."""
    parser = JSONArgumentParser(
        prog="novelos",
        description="Novel Factory — AI-powered novel chapter production",
    )
    parser.add_argument("--config", help="Path to config YAML file")
    parser.add_argument("--db-path", help="Path to SQLite database file")
    parser.add_argument("--llm-mode", choices=["stub", "real"], default="real", help="LLM mode: stub for demo, real for actual LLM (global default)")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init-db
    init_parser = subparsers.add_parser("init-db", help="Initialize the database")
    init_parser.set_defaults(func=cmd_init_db)

    # run-chapter
    run_parser = subparsers.add_parser("run-chapter", help="Run chapter production pipeline")
    run_parser.add_argument("--project-id", required=True, help="Project ID")
    run_parser.add_argument("--chapter", type=int, required=True, help="Chapter number")
    run_parser.add_argument("--max-steps", type=int, default=20, help="Maximum dispatch steps (default: 20)")
    run_parser.add_argument("--llm-mode", choices=["stub", "real"], default="real", help="LLM mode: stub for demo, real for actual LLM (default: real)")
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
    resume_parser.add_argument("--llm-mode", choices=["stub", "real"], default="real", help="LLM mode: stub for demo, real for actual LLM (default: real)")
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

    # seed-demo
    seed_parser = subparsers.add_parser("seed-demo", help="Seed demo project data")
    seed_parser.add_argument("--project-id", default="demo", help="Project ID to seed (default: demo)")
    seed_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    seed_parser.set_defaults(func=cmd_seed_demo)

    # smoke-run
    smoke_parser = subparsers.add_parser("smoke-run", help="Run a smoke test on demo project")
    smoke_parser.add_argument("--project-id", default="demo", help="Project ID to test (default: demo)")
    smoke_parser.add_argument("--chapter", type=int, default=1, help="Chapter number to test (default: 1)")
    smoke_parser.add_argument("--llm-mode", choices=["stub", "real"], default="stub", help="LLM mode: stub for demo, real for actual LLM (default: stub)")
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
    scout_parser.add_argument("--llm-mode", choices=["stub", "real"], default="real", help="LLM mode: stub for demo, real for actual LLM (default: real)")
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
    continuity_parser.add_argument("--llm-mode", choices=["stub", "real"], default="real", help="LLM mode: stub for demo, real for actual LLM (default: real)")
    continuity_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    continuity_parser.set_defaults(func=cmd_continuity_check)

    # architect
    architect_parser = subparsers.add_parser("architect", help="Generate architecture proposals")
    architect_subparsers = architect_parser.add_subparsers(dest="architect_command", help="Architect subcommands")
    
    architect_suggest = architect_subparsers.add_parser("suggest", help="Generate improvement proposals")
    architect_suggest.add_argument("--project-id", required=True, help="Project ID")
    architect_suggest.add_argument("--scope", choices=["quality", "workflow", "agent", "system"], default="quality", help="Analysis scope (default: quality)")
    architect_suggest.add_argument("--llm-mode", choices=["stub", "real"], default="real", help="LLM mode: stub for demo, real for actual LLM (default: real)")
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
    batch_run.add_argument("--llm-mode", choices=["stub", "real"], default="real", help="LLM mode: stub for demo, real for actual LLM (default: real)")
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
    batch_revise.add_argument("--llm-mode", choices=["stub", "real"], default="real", help="LLM mode: stub for demo, real for actual LLM (default: real)")
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
    batch_continuity.add_argument("--llm-mode", choices=["stub", "real"], default="real", help="LLM mode: stub for demo, real for actual LLM (default: real)")
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
    batch_queue_run.add_argument("--llm-mode", choices=["stub", "real"], default="real", help="LLM mode: stub for demo, real for actual LLM (default: real)")
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

    # serial create
    serial_create = serial_subparsers.add_parser("create", help="Create a serial plan")
    serial_create.add_argument("--project-id", required=True, help="Project ID")
    serial_create.add_argument("--name", required=True, help="Serial plan name")
    serial_create.add_argument("--start-chapter", type=int, required=True, help="Starting chapter number")
    serial_create.add_argument("--target-chapter", type=int, required=True, help="Target chapter number")
    serial_create.add_argument("--batch-size", type=int, required=True, help="Chapters per batch")
    serial_create.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_create.set_defaults(func=cmd_serial_create)

    # serial status
    serial_status = serial_subparsers.add_parser("status", help="Get serial plan status")
    serial_status.add_argument("--serial-plan-id", required=True, help="Serial plan ID")
    serial_status.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_status.set_defaults(func=cmd_serial_status)

    # serial enqueue-next
    serial_enqueue_next = serial_subparsers.add_parser("enqueue-next", help="Enqueue next batch")
    serial_enqueue_next.add_argument("--serial-plan-id", required=True, help="Serial plan ID")
    serial_enqueue_next.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_enqueue_next.set_defaults(func=cmd_serial_enqueue_next)

    # serial advance
    serial_advance = serial_subparsers.add_parser("advance", help="Advance serial plan with decision")
    serial_advance.add_argument("--serial-plan-id", required=True, help="Serial plan ID")
    serial_advance.add_argument("--decision", required=True, choices=["approve", "request_changes", "pause", "cancel"], help="Decision")
    serial_advance.add_argument("--notes", help="Optional notes")
    serial_advance.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_advance.set_defaults(func=cmd_serial_advance)

    # serial pause
    serial_pause = serial_subparsers.add_parser("pause", help="Pause a serial plan")
    serial_pause.add_argument("--serial-plan-id", required=True, help="Serial plan ID")
    serial_pause.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_pause.set_defaults(func=cmd_serial_pause)

    # serial resume
    serial_resume = serial_subparsers.add_parser("resume", help="Resume a paused serial plan")
    serial_resume.add_argument("--serial-plan-id", required=True, help="Serial plan ID")
    serial_resume.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_resume.set_defaults(func=cmd_serial_resume)

    # serial cancel
    serial_cancel = serial_subparsers.add_parser("cancel", help="Cancel a serial plan")
    serial_cancel.add_argument("--serial-plan-id", required=True, help="Serial plan ID")
    serial_cancel.add_argument("--reason", help="Cancellation reason")
    serial_cancel.add_argument("--json", action="store_true", help="Output in JSON format")
    serial_cancel.set_defaults(func=cmd_serial_cancel)

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


if __name__ == "__main__":
    main()