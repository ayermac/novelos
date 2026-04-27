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


def _get_generation_stats(request: Request) -> dict:
    """Get generation capability statistics.

    Returns:
        - test_result: pending/success/failed (LLM connectivity test)
        - success_rate: percentage of successful runs in last 30
        - avg_duration_seconds: average duration of completed runs
    """
    from ..deps import get_repo, get_llm_mode

    llm_mode = get_llm_mode(request)
    is_stub = llm_mode == "stub"

    # Get actual stats from database (for both stub and real modes)
    try:
        repo = get_repo(request)
        conn = repo._conn()
        try:
            # Get last 30 runs
            rows = conn.execute(
                "SELECT status, started_at, completed_at FROM workflow_runs "
                "ORDER BY started_at DESC LIMIT 30"
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return {
                "test_result": "pending",
                "success_rate": 0,
                "avg_duration_seconds": 0,
                "total_runs": 0,
                "last_run_at": None,
            }

        # Calculate success rate
        completed = sum(1 for r in rows if r["status"] == "completed")
        total = len(rows)
        success_rate = round((completed / total) * 100) if total > 0 else 0

        # Calculate average duration for completed runs
        durations = []
        for r in rows:
            if r["status"] == "completed" and r["started_at"] and r["completed_at"]:
                try:
                    from datetime import datetime
                    start = datetime.fromisoformat(r["started_at"].replace("Z", "+00:00"))
                    end = datetime.fromisoformat(r["completed_at"].replace("Z", "+00:00"))
                    durations.append((end - start).total_seconds())
                except (ValueError, TypeError):
                    pass

        avg_duration = round(sum(durations) / len(durations)) if durations else 0

        # In stub mode, test_result is always "pending" (no real LLM test)
        # In real mode, determine based on success rate
        if is_stub:
            test_result = "pending"
        else:
            test_result = "success" if success_rate >= 50 else "failed"

        # Get last run time
        last_run_at = rows[0]["started_at"] if rows else None

        return {
            "test_result": test_result,
            "success_rate": success_rate,
            "avg_duration_seconds": avg_duration,
            "total_runs": total,
            "last_run_at": last_run_at,
        }

    except Exception:
        return {
            "test_result": "pending",
            "success_rate": 0,
            "avg_duration_seconds": 0,
            "total_runs": 0,
            "last_run_at": None,
        }


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

        # Generation capability diagnostics
        generation_stats = _get_generation_stats(request)

        return envelope_response({
            "llm_mode": llm_mode,
            "llm_profiles": llm_profiles,
            "agent_routes": agent_routes,
            "default_llm": getattr(settings, "default_llm", None),
            "diagnostics": diagnostics,
            "generation_stats": generation_stats,
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


class ValidateConfigRequest(BaseModel):
    """Validate config request."""

    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4"
    api_key_env: str = "OPENAI_API_KEY"


@router.post("/settings/validate")
async def validate_config(request: Request, body: ValidateConfigRequest) -> EnvelopeResponse:
    """Validate LLM configuration by testing connectivity.

    Tests that the API key is valid and the endpoint is reachable.
    Does NOT save any configuration.
    """
    import os

    try:
        # Get API key from environment
        api_key = os.getenv(body.api_key_env)
        if not api_key:
            return envelope_response({
                "valid": False,
                "error_code": "MISSING_API_KEY",
                "message": f"环境变量 {body.api_key_env} 未设置",
                "details": {
                    "api_key_env": body.api_key_env,
                    "has_key": False,
                },
            })

        # Check for placeholder keys
        if api_key.startswith("sk-place") or api_key == "your-api-key-here":
            return envelope_response({
                "valid": False,
                "error_code": "PLACEHOLDER_API_KEY",
                "message": "API key 看起来是占位符，请设置真实的 API key",
                "details": {
                    "api_key_env": body.api_key_env,
                    "has_key": True,
                    "key_prefix": api_key[:10] + "...",
                },
            })

        # Test connectivity with a minimal LLM call
        try:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model=body.model,
                api_key=api_key,
                base_url=body.base_url,
                timeout=10,
                max_retries=1,
            )

            # Minimal test call
            response = llm.invoke([{"role": "user", "content": "Say 'ok'"}])

            return envelope_response({
                "valid": True,
                "message": "配置验证成功",
                "details": {
                    "provider": body.provider,
                    "model": body.model,
                    "base_url": body.base_url,
                    "api_key_env": body.api_key_env,
                    "response_preview": response.content[:50] if response.content else None,
                },
            })

        except Exception as e:
            error_msg = str(e)

            # Parse common error types
            error_code = "CONNECTION_FAILED"
            if "401" in error_msg or "authentication" in error_msg.lower():
                error_code = "INVALID_API_KEY"
            elif "404" in error_msg or "not found" in error_msg.lower():
                error_code = "MODEL_NOT_FOUND"
            elif "timeout" in error_msg.lower():
                error_code = "TIMEOUT"
            elif "connection" in error_msg.lower():
                error_code = "CONNECTION_FAILED"

            return envelope_response({
                "valid": False,
                "error_code": error_code,
                "message": f"连接失败: {error_msg[:200]}",
                "details": {
                    "provider": body.provider,
                    "model": body.model,
                    "base_url": body.base_url,
                    "api_key_env": body.api_key_env,
                    "error": error_msg[:500],
                },
            })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"验证配置失败: {str(e)}")
