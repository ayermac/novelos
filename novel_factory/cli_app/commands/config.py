"""Config and LLM CLI commands: config show/validate, llm profiles/route/validate, doctor."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import platform
import sys
import time
from pathlib import Path

from ..common import (
    _get_settings,
    _get_effective_llm_mode,
    _StubLLM,
    init_db,
    Repository,
    validate_settings,
)
from ...llm.provider import is_configured_live_provider
from ..output import _print_output


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
        "llm_mode": _get_effective_llm_mode(args),
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
    llm_mode = _get_effective_llm_mode(args)
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


def cmd_llm_profiles(args) -> None:
    """List all LLM profiles."""
    from ...llm.profiles import LLMProfilesConfig
    from ...llm.router import LLMRouter
    from ...config.env_loader import load_dotenv, create_env_getter

    # Load .env (non-polluting)
    dotenv_vars = load_dotenv()
    env_getter = create_env_getter(dotenv_vars)

    settings = _get_settings(args)
    llm_mode = _get_effective_llm_mode(args)
    use_json = getattr(args, "json", False)

    # Build LLMProfilesConfig from settings
    config = LLMProfilesConfig(
        default_llm=settings.default_llm,
        llm_profiles=settings.llm_profiles,
        agent_llm=settings.agent_llm,
        agent_llm_fallback=settings.agent_llm_fallback,
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
    from ...llm.profiles import LLMProfilesConfig
    from ...llm.router import LLMRouter
    from ...config.env_loader import load_dotenv, create_env_getter

    # Load .env (non-polluting)
    dotenv_vars = load_dotenv()
    env_getter = create_env_getter(dotenv_vars)

    settings = _get_settings(args)
    llm_mode = _get_effective_llm_mode(args)
    use_json = getattr(args, "json", False)
    agent_id = args.agent

    # Build LLMProfilesConfig from settings
    config = LLMProfilesConfig(
        default_llm=settings.default_llm,
        llm_profiles=settings.llm_profiles,
        agent_llm=settings.agent_llm,
        agent_llm_fallback=settings.agent_llm_fallback,
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
    from ...llm.profiles import LLMProfilesConfig
    from ...llm.router import LLMRouter
    from ...config.env_loader import load_dotenv, create_env_getter

    # Load .env (non-polluting)
    dotenv_vars = load_dotenv()
    env_getter = create_env_getter(dotenv_vars)

    settings = _get_settings(args)
    llm_mode = _get_effective_llm_mode(args)
    use_json = getattr(args, "json", False)

    # Build LLMProfilesConfig from settings
    config = LLMProfilesConfig(
        default_llm=settings.default_llm,
        llm_profiles=settings.llm_profiles,
        agent_llm=settings.agent_llm,
        agent_llm_fallback=settings.agent_llm_fallback,
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


def _classify_llm_smoke_error(error: Exception) -> str:
    """Classify live LLM smoke errors into stable diagnostic buckets."""
    name = error.__class__.__name__
    text = str(error).lower()
    if name == "InvalidAPIKeyError" or "unauthorized" in text or "401" in text or "api key" in text:
        return "auth"
    if name == "InsufficientBalanceError" or "quota" in text or "balance" in text or "insufficient" in text:
        return "billing"
    if name == "RateLimitError" or "rate" in text or "429" in text or "limit" in text:
        return "rate_limit"
    if name == "LLMTimeoutError" or "timeout" in text or "timed out" in text:
        return "timeout"
    if "empty response" in text or "空响应" in text:
        return "empty_response"
    if isinstance(error, ValueError):
        return "configuration"
    return "provider_error"


def _build_llm_smoke_router(settings, llm_mode: str):
    """Build the same router used by production, with dotenv-aware env resolution."""
    from ...config.env_loader import load_dotenv, create_env_getter
    from ...llm.profiles import LLMProfilesConfig
    from ...llm.router import LLMRouter

    dotenv_vars = load_dotenv()
    env_getter = create_env_getter(dotenv_vars)
    config = LLMProfilesConfig(
        default_llm=settings.default_llm,
        llm_profiles=settings.llm_profiles,
        agent_llm=settings.agent_llm,
        agent_llm_fallback=settings.agent_llm_fallback,
    )
    stub_llm = _StubLLM() if llm_mode == "stub" else None
    return LLMRouter(config, stub_provider=stub_llm, llm_mode=llm_mode, env_getter=env_getter)


def _legacy_llm_smoke_provider(settings, llm_mode: str):
    """Fallback provider for projects without llm_profiles."""
    if llm_mode == "stub":
        return _StubLLM(), {
            "agent": "legacy",
            "profile": "legacy",
            "provider": "stub",
            "base_url": "",
            "api_key": "",
            "model": "stub",
            "temperature": 0,
            "max_tokens": 0,
        }

    from ...config.env_loader import load_dotenv, create_env_getter, mask_api_key
    from ...llm.openai_compatible import OpenAICompatibleProvider

    dotenv_vars = load_dotenv()
    env_getter = create_env_getter(dotenv_vars)
    api_key = settings.llm.api_key or env_getter("OPENAI_API_KEY")
    base_url = settings.llm.base_url or env_getter("OPENAI_BASE_URL")
    if api_key:
        settings.llm.api_key = api_key
    if base_url:
        settings.llm.base_url = base_url
    provider = OpenAICompatibleProvider(settings.llm)
    return provider, {
        "agent": "legacy",
        "profile": "legacy",
        "provider": settings.llm.provider,
        "base_url": settings.llm.base_url,
        "api_key": mask_api_key(settings.llm.api_key),
        "model": settings.llm.model,
        "temperature": settings.llm.temperature,
        "max_tokens": settings.llm.max_tokens,
    }


def cmd_llm_smoke(args) -> None:
    """Run a tiny live LLM completion and report latency/error classification."""
    settings = _get_settings(args)
    llm_mode = _get_effective_llm_mode(args)
    use_json = getattr(args, "json", False)
    agent = getattr(args, "agent", "planner")
    timeout_seconds = max(1, int(getattr(args, "timeout_seconds", 8)))
    max_tokens = max(1, int(getattr(args, "max_tokens", 32)))
    prompt = getattr(args, "prompt", None) or "请只回复 OK"

    started = time.perf_counter()
    route_info = {}
    data = {
        "llm_mode": llm_mode,
        "agent": agent,
        "timeout_seconds": timeout_seconds,
        "max_tokens": max_tokens,
    }

    try:
        if settings.llm_profiles:
            router = _build_llm_smoke_router(settings, llm_mode)
            route_info = router.get_route_info(agent)
            provider = router.for_agent(agent)
        else:
            provider, route_info = _legacy_llm_smoke_provider(settings, llm_mode)

        if is_configured_live_provider(provider):
            provider.config.request_timeout_seconds = timeout_seconds
            provider.config.retry_attempts = 1

        text = provider.invoke_text(
            [
                {"role": "system", "content": "你是 LLM 连通性测试助手。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=max_tokens,
        )
        if not (text or "").strip():
            raise RuntimeError("LLM returned empty response")
        duration_ms = int((time.perf_counter() - started) * 1000)
        usage = getattr(getattr(provider, "last_token_usage", None), "to_dict", lambda: None)()
        data.update({
            "ok": True,
            "profile": route_info.get("profile"),
            "provider": route_info.get("provider"),
            "base_url": route_info.get("base_url"),
            "model": route_info.get("model"),
            "duration_ms": duration_ms,
            "usage": usage,
            "response_preview": (text or "")[:120],
        })

        if use_json:
            print(json.dumps({"ok": True, "error": None, "data": data}, ensure_ascii=False, indent=2))
        else:
            print("LLM live smoke passed:")
            print(f"  agent: {agent}")
            print(f"  profile: {data['profile']}")
            print(f"  model: {data['model']}")
            print(f"  duration_ms: {duration_ms}")
            print(f"  response: {data['response_preview']}")

    except Exception as e:
        duration_ms = int((time.perf_counter() - started) * 1000)
        error_type = _classify_llm_smoke_error(e)
        data.update({
            "ok": False,
            "profile": route_info.get("profile"),
            "provider": route_info.get("provider"),
            "base_url": route_info.get("base_url"),
            "model": route_info.get("model"),
            "duration_ms": duration_ms,
            "error_type": error_type,
            "error_message": str(e),
        })
        if use_json:
            print(json.dumps({"ok": False, "error": str(e), "data": data}, ensure_ascii=False, indent=2))
        else:
            print("LLM live smoke failed:")
            print(f"  error_type: {error_type}")
            print(f"  error: {e}")
            print(f"  duration_ms: {duration_ms}")
        sys.exit(1)


def cmd_doctor(args) -> None:
    """Run system diagnostics."""
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
    schema_path = Path(__file__).resolve().parent.parent / "db" / "schema" / "000_base_schema.sql"
    if schema_path.exists():
        checks.append({"check": "Base schema file", "status": "ok", "details": str(schema_path)})
    else:
        checks.append({"check": "Base schema file", "status": "error", "details": "Not found"})

    # Config files
    config_path = Path(__file__).resolve().parent.parent / "config" / "llm.yaml"
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
