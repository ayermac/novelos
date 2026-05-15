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
            if "api_key" in lower or "apikey" in lower or "secret" in lower or "token" in lower:
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
            "version": "6.6.0-m4",
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
            return envelope_response({
                "exists": False,
                "llm_mode": getattr(request.app.state, "llm_mode", "stub"),
                "profiles": {},
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
            "llm_mode": getattr(request.app.state, "llm_mode", "stub"),
            "default_llm": raw.get("default_llm"),
            "profiles": safe_profiles,
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

        # Update llm_mode in app state and file
        if body.llm_mode is not None:
            request.app.state.llm_mode = body.llm_mode
            raw["llm_mode"] = body.llm_mode

        # Update default_llm profile fields if a default_llm is set
        default_llm = raw.get("default_llm", "default")
        if default_llm and "llm_profiles" in raw and isinstance(raw["llm_profiles"], dict):
            if default_llm in raw["llm_profiles"] and isinstance(raw["llm_profiles"][default_llm], dict):
                profile = raw["llm_profiles"][default_llm]
                if body.base_url is not None:
                    profile["base_url"] = body.base_url
                if body.model is not None:
                    profile["model"] = body.model
                if body.temperature is not None:
                    profile["temperature"] = body.temperature
                if body.timeout is not None:
                    profile["timeout"] = body.timeout
        elif body.base_url is not None or body.model is not None:
            # No profiles exist; create a minimal default profile
            if "llm_profiles" not in raw:
                raw["llm_profiles"] = {}
            if not isinstance(raw["llm_profiles"], dict):
                raw["llm_profiles"] = {}
            raw["llm_profiles"][default_llm or "default"] = {
                "provider": "openai_compatible",
                "model": body.model or "gpt-4",
                "base_url": body.base_url or "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
            }
            if body.temperature is not None:
                raw["llm_profiles"][default_llm or "default"]["temperature"] = body.temperature
            if body.timeout is not None:
                raw["llm_profiles"][default_llm or "default"]["timeout"] = body.timeout
            if default_llm:
                raw["default_llm"] = default_llm
            else:
                raw["default_llm"] = "default"

        # Write back
        import yaml

        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

        return envelope_response({
            "saved": True,
            "config_path": str(config_file),
            "message": "配置已保存（未包含 API key）",
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
