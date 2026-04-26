"""Settings API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class ConfigPlanRequest(BaseModel):
    """Config plan request."""

    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4"
    api_key_env: str = "OPENAI_API_KEY"
    default_llm: str = "default"
    agent_llm: str | None = None


@router.get("/settings")
async def get_settings(request: Request) -> EnvelopeResponse:
    """Get current settings.

    Never returns API keys or secrets.
    """
    from ..deps import get_settings, get_llm_mode

    try:
        settings = get_settings(request)
        llm_mode = get_llm_mode(request)

        # Build LLM profiles (without API keys)
        llm_profiles = []
        if hasattr(settings, "llm_profiles") and settings.llm_profiles:
            import os
            for name, profile in settings.llm_profiles.items():
                # Check if API key is configured (via env or direct)
                has_key = False
                api_key_env = getattr(profile, "api_key_env", None)
                if api_key_env:
                    has_key = bool(os.getenv(api_key_env))
                elif getattr(profile, "api_key", None):
                    has_key = True

                # Check if base_url is configured (via env or direct)
                has_base_url = False
                base_url_env = getattr(profile, "base_url_env", None)
                if base_url_env:
                    has_base_url = bool(os.getenv(base_url_env))
                elif getattr(profile, "base_url", None):
                    has_base_url = True

                llm_profiles.append({
                    "name": name,
                    "provider": getattr(profile, "provider", "unknown"),
                    "model": getattr(profile, "model", "unknown"),
                    "has_key": has_key,
                    "has_base_url": has_base_url,
                    "api_key_env": api_key_env,  # Show env var name, not value
                    "base_url_env": base_url_env,  # Show env var name, not value
                })

        # Build agent routes
        agent_routes = []
        if hasattr(settings, "agent_llm") and settings.agent_llm:
            for agent, route in settings.agent_llm.items():
                agent_routes.append({
                    "agent": agent,
                    "route": route,
                })

        # Diagnostics
        diagnostics = {
            "llm_mode": llm_mode,
            "has_profiles": len(llm_profiles) > 0,
            "has_default_llm": hasattr(settings, "default_llm") and settings.default_llm,
        }

        return envelope_response({
            "llm_mode": llm_mode,
            "llm_profiles": llm_profiles,
            "agent_routes": agent_routes,
            "default_llm": getattr(settings, "default_llm", None),
            "diagnostics": diagnostics,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"获取设置失败: {str(e)}")


@router.post("/config/plan")
async def create_config_plan(request: Request, body: ConfigPlanRequest) -> EnvelopeResponse:
    """Generate a configuration plan (draft).

    This does NOT write to any config file.
    Returns a YAML draft for user review.
    """
    from datetime import datetime

    try:
        # Generate draft YAML
        draft_lines = [
            "# 配置草案 (Config Draft)",
            f"# 生成时间: {datetime.utcnow().isoformat()}",
            "",
            "# 使用方式：",
            "# 1. 将以下 YAML 保存到项目配置目录（如 config/local.yaml）",
            f"# 2. 在启动前设置环境变量：export {body.api_key_env}=<your-api-key>",
            "# 3. 启动 API 服务：novelos api --config config/local.yaml --llm-mode real",
            "# 4. 启动前端开发服务器：cd frontend && npm run dev",
            "",
            "llm_profiles:",
            f"  {body.default_llm}:",
            f"    provider: {body.provider}",
            f"    model: {body.model}",
            f'    base_url: "{body.base_url}"',
            f'    api_key_env: "{body.api_key_env}"',
            "",
            f"default_llm: {body.default_llm}",
            "",
        ]

        if body.agent_llm:
            draft_lines.append("agent_llm:")
            pairs = [p.strip() for p in body.agent_llm.split(",")]
            for pair in pairs:
                if "=" in pair:
                    agent, profile = pair.split("=", 1)
                    draft_lines.append(f"  {agent.strip()}: {profile.strip()}")

        draft = "\n".join(draft_lines)

        return envelope_response({
            "draft": draft,
            "format": "yaml",
            "message": "配置草案已生成，请复制并保存到配置文件",
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"生成配置草案失败: {str(e)}")
