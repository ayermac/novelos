"""Creative contracts API endpoints for v6.9.0.

Provides endpoints for managing project launch profiles and genre contracts.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse
from ...models.creative_contracts import (
    ProjectLaunchProfile,
    GenreContract,
    GenreProfile,
)
from ...quality.genesis_quality_gate import (
    generate_launch_profile,
    generate_genre_contract,
    check_project_ready_for_production,
)
from ...config.genre_profile_loader import (
    load_genre_profile,
    get_all_profile_ids,
    get_default_genre_profile,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Request/Response Models ──────────────────────────────────────────────


class GenerateContractRequest(BaseModel):
    """Request body for generating creative contracts."""

    project_id: str
    user_idea: str
    genre_profile_id: str = "generic"


class ApproveContractRequest(BaseModel):
    """Request body for approving a genre contract."""

    project_id: str


class CreativeContractResponse(BaseModel):
    """Response for creative contract data."""

    project_id: str
    launch_profile: dict | None = None
    genre_contract: dict | None = None
    is_approved: bool = False
    is_ready_for_production: bool = False


# ── Helper Functions ─────────────────────────────────────────────────────


def _get_repo(request: Request) -> Any:
    """Get repository from request state."""
    from ..deps import get_repo
    return get_repo(request)


def _get_settings(request: Request) -> Any:
    """Get settings from request state."""
    from ..deps import get_settings
    return get_settings(request)


def _get_llm_mode(request: Request) -> str:
    """Get LLM mode from request state."""
    from ..deps import get_llm_mode
    return get_llm_mode(request)


def _serialize_model(model: Any) -> dict:
    """Serialize a Pydantic model to dict."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    elif hasattr(model, "dict"):
        return model.dict()
    else:
        return vars(model)


def _parse_contract_data(row: dict | None) -> dict | None:
    """Parse contract_data JSON string from a DB row into a dict."""
    if not row:
        return None
    contract_data = row.get("contract_data", "{}")
    if isinstance(contract_data, str):
        try:
            return json.loads(contract_data)
        except json.JSONDecodeError:
            return None
    return contract_data


# ── API Endpoints ────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/creative-contracts")
async def get_creative_contracts(
    project_id: str,
    request: Request,
) -> EnvelopeResponse:
    """Get creative contracts for a project.

    Returns the launch profile and genre contract if they exist.
    """
    repo = _get_repo(request)

    # Check if project exists
    project = repo.get_project(project_id)
    if not project:
        return error_response(
            message=f"项目不存在: {project_id}",
            domain_status="not_found",
        )

    # Get launch profile
    launch_profile_row = repo.get_creative_contract(project_id, "launch_profile")
    launch_profile = None
    if launch_profile_row:
        parsed = _parse_contract_data(launch_profile_row)
        if parsed:
            try:
                launch_profile = ProjectLaunchProfile(**parsed)
            except Exception as e:
                logger.warning(f"Failed to parse launch profile: {e}")

    # Get genre contract
    genre_contract_row = repo.get_creative_contract(project_id, "genre_contract")
    genre_contract = None
    is_approved = False
    if genre_contract_row:
        parsed = _parse_contract_data(genre_contract_row)
        if parsed:
            try:
                # Remove approved field before parsing (it's stored in contract_data JSON)
                is_approved = parsed.pop("approved", False)
                genre_contract = GenreContract(**parsed)
            except Exception as e:
                logger.warning(f"Failed to parse genre contract: {e}")

    # Check if project is ready for production
    is_ready = check_project_ready_for_production(project_id, repo)

    return envelope_response(
        CreativeContractResponse(
            project_id=project_id,
            launch_profile=_serialize_model(launch_profile) if launch_profile else None,
            genre_contract=_serialize_model(genre_contract) if genre_contract else None,
            is_approved=is_approved,
            is_ready_for_production=is_ready,
        ).model_dump()
    )


@router.post("/projects/{project_id}/creative-contracts/generate")
async def generate_creative_contracts(
    project_id: str,
    request: Request,
    body: GenerateContractRequest,
) -> EnvelopeResponse:
    """Generate creative contracts for a project.

    Creates a launch profile and genre contract based on user idea and genre profile.
    """
    repo = _get_repo(request)
    settings = _get_settings(request)
    llm_mode = _get_llm_mode(request)

    # Check if project exists
    project = repo.get_project(project_id)
    if not project:
        return error_response(
            message=f"项目不存在: {project_id}",
            domain_status="not_found",
        )

    # Check if contracts already exist
    existing_launch = repo.get_creative_contract(project_id, "launch_profile")
    existing_contract = repo.get_creative_contract(project_id, "genre_contract")
    if existing_launch or existing_contract:
        return error_response(
            message="项目已有创作合同，请先删除现有合同再重新生成",
            domain_status="conflict",
        )

    # Load genre profile
    try:
        genre_profile = load_genre_profile(body.genre_profile_id)
    except FileNotFoundError:
        # Fallback to generic profile
        genre_profile = get_default_genre_profile()

    # Get LLM caller if in real mode
    llm_caller = None
    if llm_mode == "real":
        from ...llm.provider import get_llm_provider
        llm_provider = get_llm_provider(settings)
        if llm_provider:
            llm_caller = llm_provider.complete

    # Generate launch profile
    try:
        launch_profile = generate_launch_profile(
            user_idea=body.user_idea,
            genre_profile=genre_profile,
            llm_caller=llm_caller,
        )
    except Exception as e:
        logger.error(f"Failed to generate launch profile: {e}")
        return error_response(
            message=f"生成启动配置失败: {str(e)}",
            domain_status="error",
        )

    # Generate genre contract
    try:
        genre_contract = generate_genre_contract(
            launch_profile=launch_profile,
            genre_profile=genre_profile,
            llm_caller=llm_caller,
        )
    except Exception as e:
        logger.error(f"Failed to generate genre contract: {e}")
        return error_response(
            message=f"生成类型合同失败: {str(e)}",
            domain_status="error",
        )

    # Save to database
    try:
        repo.upsert_creative_contract(
            project_id=project_id,
            contract_type="launch_profile",
            data=_serialize_model(launch_profile),
        )
        repo.upsert_creative_contract(
            project_id=project_id,
            contract_type="genre_contract",
            data=_serialize_model(genre_contract),
        )
    except Exception as e:
        logger.error(f"Failed to save creative contracts: {e}")
        return error_response(
            message=f"保存创作合同失败: {str(e)}",
            domain_status="error",
        )

    return envelope_response({
        "project_id": project_id,
        "launch_profile": _serialize_model(launch_profile),
        "genre_contract": _serialize_model(genre_contract),
        "is_approved": False,
        "is_ready_for_production": False,
        "message": "创作合同生成成功",
    })


@router.post("/projects/{project_id}/creative-contracts/approve")
async def approve_creative_contracts(
    project_id: str,
    request: Request,
    body: ApproveContractRequest,
) -> EnvelopeResponse:
    """Approve the genre contract for a project.

    Sets the genre contract as approved, allowing chapter production to begin.
    """
    repo = _get_repo(request)

    # Check if project exists
    project = repo.get_project(project_id)
    if not project:
        return error_response(
            message=f"项目不存在: {project_id}",
            domain_status="not_found",
        )

    # Check if genre contract exists
    genre_contract_row = repo.get_creative_contract(project_id, "genre_contract")
    if not genre_contract_row:
        return error_response(
            message="项目尚未生成类型合同，请先生成合同",
            domain_status="not_found",
        )

    # Parse contract_data JSON
    contract_data = _parse_contract_data(genre_contract_row)
    if not contract_data:
        return error_response(
            message="类型合同数据格式错误",
            domain_status="error",
        )

    # Check if already approved
    if contract_data.get("approved", False):
        return envelope_response({
            "project_id": project_id,
            "is_approved": True,
            "message": "类型合同已审批",
        })

    # Update approval status
    try:
        contract_data["approved"] = True
        repo.upsert_creative_contract(
            project_id=project_id,
            contract_type="genre_contract",
            data=contract_data,
        )
    except Exception as e:
        logger.error(f"Failed to approve genre contract: {e}")
        return error_response(
            message=f"审批类型合同失败: {str(e)}",
            domain_status="error",
        )

    return envelope_response({
        "project_id": project_id,
        "is_approved": True,
        "message": "类型合同审批成功，项目已准备就绪",
    })


@router.get("/projects/{project_id}/production-readiness")
async def check_production_readiness(
    project_id: str,
    request: Request,
) -> EnvelopeResponse:
    """Check if a project is ready for chapter production.

    Returns readiness status and any missing requirements.
    """
    repo = _get_repo(request)

    # Check if project exists
    project = repo.get_project(project_id)
    if not project:
        return error_response(
            message=f"项目不存在: {project_id}",
            domain_status="not_found",
        )

    # Check creative contracts
    launch_profile_row = repo.get_creative_contract(project_id, "launch_profile")
    genre_contract_row = repo.get_creative_contract(project_id, "genre_contract")

    # Parse genre contract data
    genre_contract_data = _parse_contract_data(genre_contract_row)
    is_approved = genre_contract_data.get("approved", False) if genre_contract_data else False

    # Determine readiness
    is_ready = bool(launch_profile_row and genre_contract_row and is_approved)

    # Build requirements list
    requirements = []
    if not launch_profile_row:
        requirements.append("missing_launch_profile")
    if not genre_contract_row:
        requirements.append("missing_genre_contract")
    if not is_approved:
        requirements.append("contract_not_approved")

    return envelope_response({
        "project_id": project_id,
        "is_ready": is_ready,
        "requirements": requirements,
        "has_launch_profile": bool(launch_profile_row),
        "has_genre_contract": bool(genre_contract_row),
        "is_approved": is_approved,
    })


@router.get("/genre-profiles")
async def list_genre_profiles(request: Request) -> EnvelopeResponse:
    """List all available genre profile IDs.

    Returns a list of genre profile identifiers that can be used when generating contracts.
    """
    profile_ids = get_all_profile_ids()

    return envelope_response({
        "profiles": profile_ids,
        "count": len(profile_ids),
    })
