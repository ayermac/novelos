"""Desktop client runtime API endpoints.

Provides runtime information and safe config management for the
Electron desktop client. Never exposes or writes API keys.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class DesktopConfigPayload(BaseModel):
    """Safe desktop config update payload.

    Only non-secret fields. API keys must be managed externally.
    """

    llm_mode: str | None = Field(default=None, pattern="^(stub|real)$")
    base_url: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    timeout: int | None = Field(default=None, ge=1, le=300)
    api_key_env: str | None = Field(default=None, pattern="^[A-Z0-9_]+$")
    agent_llm: dict[str, str] | None = None


class TestLlmRequest(BaseModel):
    """Request body for desktop LLM connection test."""

    provider: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"


class TestLlmResponse(BaseModel):
    """Response for desktop LLM connection test."""

    ok: bool
    mode: str = "unknown"
    provider: str = ""
    base_url: str = ""
    model: str = ""
    latency_ms: int | None = None
    message: str = ""
    error_code: str | None = None
    suggestion: str | None = None


def _is_desktop_runtime() -> bool:
    return os.environ.get("NOVELOS_DESKTOP") == "1"


def _desktop_config_path(request: Request) -> tuple[Path | None, str | None]:
    """Return desktop config path when this API is running inside desktop mode."""
    if not _is_desktop_runtime():
        return None, "DESKTOP_ONLY"

    from ..deps import get_config_path

    config_path = get_config_path(request) or os.environ.get("NOVELOS_CONFIG_PATH")
    config_dir = os.environ.get("NOVELOS_CONFIG_DIR")
    if not config_path or not config_dir:
        return None, "CONFIG_NOT_FOUND"

    try:
        resolved_config = Path(config_path).expanduser().resolve()
        resolved_dir = Path(config_dir).expanduser().resolve()
        if resolved_config != resolved_dir / resolved_config.name and resolved_dir not in resolved_config.parents:
            return None, "CONFIG_PATH_OUTSIDE_DESKTOP_DIR"
        return resolved_config, None
    except Exception:
        return None, "INVALID_CONFIG_PATH"


def _secret_key_envs() -> set[str]:
    """Return env names declared as desktop secure storage keys."""
    raw = os.environ.get("NOVELOS_DESKTOP_SECRET_KEYS", "")
    return {name.strip() for name in raw.split(",") if name.strip()}


def _api_key_source(env_name: str | None) -> str:
    """Determine the source of an API key for a given env name."""
    if not env_name:
        return "missing"
    secret_envs = _secret_key_envs()
    if env_name in secret_envs and os.environ.get(env_name):
        return "desktop_secure_storage"
    if os.environ.get(env_name):
        return "environment"
    return "missing"


def _api_key_configured(env_name: str | None) -> bool:
    """Check whether an API key is configured for a given env name."""
    if not env_name:
        return False
    return bool(os.environ.get(env_name))


def _contains_sensitive_key(value: Any) -> str | None:
    """Return the first sensitive key name found in nested JSON-like data."""
    if isinstance(value, dict):
        for key, nested in value.items():
            lower = str(key).lower()
            if (
                ("api_key" in lower and not lower.endswith("_env"))
                or "apikey" in lower
                or "secret" in lower
                or "token" in lower
            ):
                return str(key)
            found = _contains_sensitive_key(nested)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _contains_sensitive_key(item)
            if found:
                return found
    return None


@router.get("/desktop/runtime-info")
async def get_runtime_info(request: Request) -> EnvelopeResponse:
    """Return desktop runtime information.

    Includes paths, mode, and file existence checks.
    Never returns API keys.
    """
    from ..deps import get_config_path, get_db_path, get_llm_mode

    try:
        config_path = get_config_path(request)
        db_path = get_db_path(request)
        llm_mode = get_llm_mode(request)

        app_data_dir = os.environ.get("NOVELOS_APP_DATA_DIR", "")
        data_dir = os.environ.get("NOVELOS_DATA_DIR", "")
        config_dir = os.environ.get("NOVELOS_CONFIG_DIR", "")
        logs_dir = os.environ.get("NOVELOS_LOGS_DIR", "")
        backups_dir = os.environ.get("NOVELOS_BACKUPS_DIR", "")

        return envelope_response({
            "is_desktop": os.environ.get("NOVELOS_DESKTOP") == "1",
            "app_data_dir": app_data_dir,
            "data_dir": data_dir,
            "db_path": db_path,
            "config_path": config_path,
            "config_dir": config_dir,
            "logs_dir": logs_dir,
            "backups_dir": backups_dir,
            "llm_mode": llm_mode,
            "config_exists": bool(config_path and Path(config_path).exists()),
            "db_exists": bool(db_path and Path(db_path).exists()),
            "sidecar_pid": os.getpid(),
            "platform": os.environ.get("NOVELOS_PLATFORM", ""),
            "version": "6.8.0-m6",
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取运行时信息失败: {str(e)}")


@router.get("/desktop/config")
async def get_desktop_config(request: Request) -> EnvelopeResponse:
    """Read the current desktop config file safely.

    Returns only non-secret fields. API keys are redacted.
    """
    try:
        config_file, error_code = _desktop_config_path(request)
        if error_code == "DESKTOP_ONLY":
            return error_response("DESKTOP_ONLY", "桌面配置接口仅在 Novelos 桌面应用中可用")
        if error_code or not config_file:
            return error_response(error_code or "CONFIG_NOT_FOUND", "未找到桌面配置路径")
        if not config_file.exists():
            runtime_mode = getattr(request.app.state, "llm_mode", "stub")
            return envelope_response({
                "exists": False,
                "llm_mode": runtime_mode,
                "configured_llm_mode": runtime_mode,
                "runtime_llm_mode": runtime_mode,
                "profiles": {},
                "agent_llm": {},
            })

        import yaml

        with open(config_file, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        # Extract safe fields only
        safe_profiles: dict = {}
        profiles = raw.get("llm_profiles", {})
        if isinstance(profiles, dict):
            for name, profile in profiles.items():
                if not isinstance(profile, dict):
                    continue
                api_key_env = profile.get("api_key_env", "")
                safe_profiles[name] = {
                    "provider": profile.get("provider", "unknown"),
                    "model": profile.get("model", "unknown"),
                    "base_url": profile.get("base_url", ""),
                    "api_key_env": api_key_env,
                    "api_key_configured": _api_key_configured(api_key_env),
                    "api_key_source": _api_key_source(api_key_env),
                    "temperature": profile.get("temperature", 0.7),
                    "max_tokens": profile.get("max_tokens", 4096),
                }

        return envelope_response({
            "exists": True,
            "llm_mode": raw.get("llm_mode", getattr(request.app.state, "llm_mode", "stub")),
            "configured_llm_mode": raw.get("llm_mode", getattr(request.app.state, "llm_mode", "stub")),
            "runtime_llm_mode": getattr(request.app.state, "llm_mode", "stub"),
            "default_llm": raw.get("default_llm"),
            "profiles": safe_profiles,
            "agent_llm": raw.get("agent_llm", {}) if isinstance(raw.get("agent_llm", {}), dict) else {},
            "raw_preview": _redacted_yaml_preview(raw),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"读取配置失败: {str(e)}")


@router.put("/desktop/config")
async def update_desktop_config(request: Request) -> EnvelopeResponse:
    """Update safe desktop config fields.

    Only updates non-secret fields. Preserves unknown keys.
    Never writes API keys.
    """
    try:
        raw_body = await request.json()
        if not isinstance(raw_body, dict):
            return error_response("INVALID_BODY", "请求体必须是 JSON 对象")

        sensitive_key = _contains_sensitive_key(raw_body)
        if sensitive_key:
            return error_response("SECURITY_REJECTED", f"配置写入拒绝包含敏感字段: {sensitive_key}")

        # Validate manually to avoid silently ignoring extra fields
        try:
            body = DesktopConfigPayload(**raw_body)
        except Exception as ve:
            return error_response("VALIDATION_ERROR", f"字段校验失败: {str(ve)}")

        config_file, error_code = _desktop_config_path(request)
        if error_code == "DESKTOP_ONLY":
            return error_response("DESKTOP_ONLY", "桌面配置接口仅在 Novelos 桌面应用中可用")
        if error_code or not config_file:
            return error_response(error_code or "CONFIG_NOT_FOUND", "未找到桌面配置路径")

        raw: dict = {}
        if config_file.exists():
            import yaml

            with open(config_file, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}

        if not isinstance(raw, dict):
            raw = {}

        restart_required = False

        # Update llm_mode in app state and file
        if body.llm_mode is not None:
            current_llm_mode = getattr(request.app.state, "llm_mode", "stub")
            if current_llm_mode != body.llm_mode:
                restart_required = True
            raw["llm_mode"] = body.llm_mode

        # Update default_llm profile fields if a default_llm is set
        default_llm = raw.get("default_llm", "default")
        if default_llm and "llm_profiles" in raw and isinstance(raw["llm_profiles"], dict):
            if default_llm in raw["llm_profiles"] and isinstance(raw["llm_profiles"][default_llm], dict):
                profile = raw["llm_profiles"][default_llm]
                if body.base_url is not None and profile.get("base_url") != body.base_url:
                    profile["base_url"] = body.base_url
                    restart_required = True
                if body.model is not None and profile.get("model") != body.model:
                    profile["model"] = body.model
                    restart_required = True
                if body.temperature is not None and profile.get("temperature") != body.temperature:
                    profile["temperature"] = body.temperature
                    restart_required = True
                if body.timeout is not None and profile.get("timeout") != body.timeout:
                    profile["timeout"] = body.timeout
                    restart_required = True
                if body.api_key_env is not None and profile.get("api_key_env") != body.api_key_env:
                    profile["api_key_env"] = body.api_key_env
                    restart_required = True
        elif body.base_url is not None or body.model is not None or body.api_key_env is not None:
            # No profiles exist; create a minimal default profile
            restart_required = True
            if "llm_profiles" not in raw:
                raw["llm_profiles"] = {}
            if not isinstance(raw["llm_profiles"], dict):
                raw["llm_profiles"] = {}
            raw["llm_profiles"][default_llm or "default"] = {
                "provider": "openai_compatible",
                "model": body.model or "gpt-4o-mini",
                "base_url": body.base_url or "https://api.openai.com/v1",
                "api_key_env": body.api_key_env or "OPENAI_API_KEY",
            }
            if body.temperature is not None:
                raw["llm_profiles"][default_llm or "default"]["temperature"] = body.temperature
            if body.timeout is not None:
                raw["llm_profiles"][default_llm or "default"]["timeout"] = body.timeout
            if default_llm:
                raw["default_llm"] = default_llm
            else:
                raw["default_llm"] = "default"

        if body.agent_llm is not None:
            cleaned_routes = {
                str(agent).strip(): str(profile).strip()
                for agent, profile in body.agent_llm.items()
                if str(agent).strip() and str(profile).strip()
            }
            if raw.get("agent_llm", {}) != cleaned_routes:
                restart_required = True
            if cleaned_routes:
                raw["agent_llm"] = cleaned_routes
            else:
                raw.pop("agent_llm", None)

        # Write back
        import yaml

        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

        return envelope_response({
            "saved": True,
            "config_path": str(config_file),
            "restart_required": restart_required,
            "message": "配置已保存（未包含 API key）" + ("，重启后生效" if restart_required else ""),
        })
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"保存配置失败: {str(e)}")


def _redacted_yaml_preview(raw: dict) -> str:
    """Create a safe YAML preview with API keys redacted."""
    import copy

    safe = copy.deepcopy(raw)
    # Redact any field that looks like an API key
    _redact_dict(safe)
    import yaml

    return yaml.dump(safe, allow_unicode=True, default_flow_style=False)


def _redact_dict(d: dict[str, Any]) -> None:
    """Recursively redact sensitive keys in a dict."""
    for key in list(d.keys()):
        val = d[key]
        lower_key = str(key).lower()
        if (
            ("api_key" in lower_key and not lower_key.endswith("_env"))
            or "secret" in lower_key
            or "token" in lower_key
            or "authorization" in lower_key
            or lower_key == "password"
        ):
            d[key] = "***REDACTED***"
        elif isinstance(val, dict):
            _redact_dict(val)


@router.post("/desktop/test-llm")
async def test_llm_connection(request: Request, body: TestLlmRequest) -> EnvelopeResponse:
    """Test LLM connectivity from the desktop runtime.

    Uses the currently active config and environment (including safeStorage-injected keys).
    Only available when running inside the desktop app.
    """
    if not _is_desktop_runtime():
        return error_response("DESKTOP_ONLY", "LLM 连接测试仅在 Novelos 桌面应用中可用")

    # Reject if stub mode
    llm_mode = getattr(request.app.state, "llm_mode", "stub")
    if llm_mode == "stub":
        return envelope_response({
            "ok": False,
            "mode": "stub",
            "provider": body.provider,
            "base_url": body.base_url,
            "model": body.model,
            "message": "当前为演示模式 (stub)。请先切换为真实模式并保存配置，然后重启客户端。",
            "error_code": "STUB_MODE",
            "suggestion": "在桌面配置中将 LLM 模式设为 real，保存后重启本地服务。",
        })

    # Check API key presence
    api_key = os.environ.get(body.api_key_env)
    if not api_key:
        return envelope_response({
            "ok": False,
            "mode": "real",
            "provider": body.provider,
            "base_url": body.base_url,
            "model": body.model,
            "message": f"API Key 未配置 ({body.api_key_env})。请先通过桌面安全存储保存 API Key，然后重启客户端。",
            "error_code": "API_KEY_MISSING",
            "suggestion": "在桌面配置的「API Key 安全存储」中输入并保存密钥，然后重启本地服务使密钥注入环境变量。",
        })

    # Check for placeholder keys
    if api_key.startswith("sk-place") or api_key == "your-api-key-here":
        return envelope_response({
            "ok": False,
            "mode": "real",
            "provider": body.provider,
            "base_url": body.base_url,
            "model": body.model,
            "message": "API Key 看起来是占位符，请设置真实的 API key",
            "error_code": "API_KEY_MISSING",
            "suggestion": "替换为真实的服务商 API Key。",
        })

    import time

    start = time.time()
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=body.model,
            api_key=api_key,
            base_url=body.base_url,
            timeout=15,
            max_retries=1,
        )

        response = llm.invoke([{"role": "user", "content": "Say 'ok'"}])
        latency_ms = int((time.time() - start) * 1000)

        return envelope_response({
            "ok": True,
            "mode": "real",
            "provider": body.provider,
            "base_url": body.base_url,
            "model": body.model,
            "latency_ms": latency_ms,
            "message": f"连接成功 ({latency_ms}ms)",
        })

    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        error_msg = str(e)
        error_code = "UNKNOWN"
        suggestion = "请检查网络连接和配置参数。"

        if "401" in error_msg or "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
            error_code = "AUTH_FAILED"
            suggestion = "API Key 无效或无权限。请确认密钥属于当前服务商，并检查 Base URL 是否正确。"
        elif "404" in error_msg or "not found" in error_msg.lower():
            error_code = "MODEL_NOT_FOUND"
            suggestion = "模型 ID 在当前服务商不存在。请检查模型名称是否与服务商文档一致。"
        elif "timeout" in error_msg.lower():
            error_code = "TIMEOUT"
            suggestion = "连接超时。请检查网络状况，或尝试增加超时时间。"
        elif "connection" in error_msg.lower() or "network" in error_msg.lower() or "resolve" in error_msg.lower():
            error_code = "NETWORK_ERROR"
            suggestion = "网络连接失败。请检查 Base URL 是否正确，以及本地网络是否能访问该地址。"

        return envelope_response({
            "ok": False,
            "mode": "real",
            "provider": body.provider,
            "base_url": body.base_url,
            "model": body.model,
            "latency_ms": latency_ms,
            "message": f"连接失败: {error_msg[:200]}",
            "error_code": error_code,
            "suggestion": suggestion,
        })
