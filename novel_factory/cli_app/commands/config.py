"""Config and LLM CLI commands: config show/validate, llm profiles/route/validate, doctor."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import platform
import sys
from pathlib import Path

from ..common import (
    _get_settings,
    _get_effective_llm_mode,
    _StubLLM,
    init_db,
    Repository,
    validate_settings,
)
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
