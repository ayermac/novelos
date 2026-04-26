"""Style Bible, Gate, and Sample routes."""

from __future__ import annotations

import json
import hashlib
from fastapi import APIRouter, Request, Form, UploadFile, File

from ..deps import get_repo, render, safe_error_message, build_dispatcher_for_web

router = APIRouter()

# File size limit for sample upload
MAX_FILE_SIZE = 200 * 1024  # 200KB


def _build_style_context(repo, extra: dict | None = None) -> dict:
    """Build shared Style page context from the current Web database."""
    projects = repo.list_projects()

    bibles = {}
    pending_proposals = {}
    gate_configs = {}
    samples_by_project = {}
    
    for project in projects:
        project_id = project["project_id"]

        bible = repo.get_style_bible(project_id)
        if bible:
            bibles[project_id] = bible

        proposals = repo.list_style_evolution_proposals(project_id, status="pending")
        if proposals:
            pending_proposals[project_id] = proposals

        # Get gate config
        gate_config = repo.get_style_gate_config(project_id)
        if gate_config:
            gate_configs[project_id] = gate_config

        # Get samples
        samples = repo.list_style_samples(project_id)
        if samples:
            samples_by_project[project_id] = samples

    context = {
        "projects": projects,
        "bibles": bibles,
        "pending_proposals": pending_proposals,
        "gate_configs": gate_configs,
        "samples_by_project": samples_by_project,
    }
    if extra:
        context.update(extra)
    return context


@router.get("")
async def style_overview(request: Request):
    """Show style overview with projects."""
    try:
        repo = get_repo(request)
        return render(request, "style.html", _build_style_context(repo))
    except Exception as e:
        return render(request, "style.html", {"error": safe_error_message(e)})


@router.post("/init")
async def style_init(
    request: Request,
    project_id: str = Form(...),
    template: str = Form("default_web_serial"),
):
    """Initialize Style Bible from template."""
    try:
        repo = get_repo(request)
        
        # Use the template helper directly
        from ...style_bible.templates import create_style_bible_from_template, validate_style_bible
        
        # Create StyleBible from template
        bible = create_style_bible_from_template(
            project_id=project_id,
            template_id=template,
        )
        
        # Validate
        validation = validate_style_bible(bible)
        if not validation.get("ok"):
            return render(request, "style.html", {"error": validation.get("error", "Validation failed")})
        
        # Save to current Web DB
        success = repo.save_style_bible(project_id, bible.model_dump())
        
        result = {
            "ok": success,
            "project_id": project_id,
            "template": template,
            "message": "Style Bible initialized successfully" if success else "Failed to save Style Bible",
        }
        
        return render(request, "style.html", _build_style_context(repo, {"result": result}))
    except Exception as e:
        return render(request, "style.html", {"error": safe_error_message(e)})


@router.post("/gate-set")
async def style_gate_set(
    request: Request,
    project_id: str = Form(...),
    mode: str = Form(None),
    threshold: int = Form(None),
    enabled: bool = Form(None),
):
    """Configure Style Gate."""
    try:
        repo = get_repo(request)
        
        # Load existing config or create new
        from ...models.style_gate import StyleGateConfig, StyleGateMode
        
        existing = repo.get_style_gate_config(project_id)
        if existing:
            config = StyleGateConfig.from_storage_dict(existing)
        else:
            config = StyleGateConfig()
        
        # Apply form values
        if mode is not None:
            try:
                config.mode = StyleGateMode(mode)
            except ValueError:
                pass
        
        if threshold is not None:
            config.blocking_threshold = threshold  # ✅ Correct field name
        
        if enabled is not None:
            config.enabled = enabled
        
        # Save via repository
        gate_dict = config.to_storage_dict()
        success = repo.set_style_gate_config(project_id, gate_dict)
        
        result = {
            "ok": success,
            "project_id": project_id,
            "gate_config": gate_dict,
        }
        
        return render(request, "style.html", _build_style_context(repo, {"result": result}))
    except Exception as e:
        return render(request, "style.html", {"error": safe_error_message(e)})


@router.post("/proposal-decide")
async def style_proposal_decide(
    request: Request,
    proposal_id: str = Form(...),
    decision: str = Form(...),
    notes: str = Form(""),
):
    """Approve or reject a style proposal."""
    try:
        repo = get_repo(request)
        
        # Map form values to repository status values
        # Form: approve/reject -> Repository: approved/rejected
        decision_map = {
            "approve": "approved",
            "reject": "rejected",
        }
        
        status_value = decision_map.get(decision.lower())
        if not status_value:
            return render(
                request,
                "style.html",
                {"error": f"Invalid decision '{decision}'. Must be 'approve' or 'reject'."},
            )
        
        # Use repository method with correct status value
        success = repo.decide_style_evolution_proposal(
            proposal_id=proposal_id,
            decision=status_value,
            notes=notes,
        )
        
        result = {
            "ok": success,
            "proposal_id": proposal_id,
            "decision": decision,
            "status": status_value,
        }
        
        return render(request, "style.html", _build_style_context(repo, {"result": result}))
    except Exception as e:
        return render(request, "style.html", {"error": safe_error_message(e)})


@router.post("/sample-import")
async def style_sample_import(
    request: Request,
    project_id: str = Form(...),
    name: str = Form(""),
    file: UploadFile = File(...),
):
    """Import a style sample from uploaded file."""
    try:
        # Check file size
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            return render(
                request,
                "style.html",
                {"error": f"File too large ({len(content)} bytes). Maximum: {MAX_FILE_SIZE} bytes"},
            )

        # Decode UTF-8
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return render(request, "style.html", {"error": "File is not valid UTF-8 text"})

        if not text.strip():
            return render(request, "style.html", {"error": "File is empty"})

        # Compute hash and preview
        content_hash = hashlib.sha256(content).hexdigest()
        content_preview = text[:500]

        # Use filename if name not provided
        if not name:
            name = file.filename or "uploaded_sample"

        # Analyze sample
        from ...style_bible.sample_analyzer import analyze_style_sample_text

        analysis_result = analyze_style_sample_text(text)
        if not analysis_result.get("ok"):
            return render(request, "style.html", {"error": analysis_result.get("error", "Analysis failed")})

        metrics_data = analysis_result["data"]["metrics"]
        analysis_data = analysis_result["data"]["analysis"]

        # Save sample
        repo = get_repo(request)
        sample_id = repo.save_style_sample(
            project_id=project_id,
            name=name,
            source_type="local_text",
            content_hash=content_hash,
            content_preview=content_preview,
            metrics_json=json.dumps(metrics_data, ensure_ascii=False),
            analysis_json=json.dumps(analysis_data, ensure_ascii=False),
            status="analyzed",
        )

        return render(
            request,
            "style.html",
            _build_style_context(repo, {
                "result": {
                    "ok": True,
                    "sample_id": sample_id,
                    "name": name,
                    "status": "analyzed",
                }
            }),
        )
    except Exception as e:
        return render(request, "style.html", {"error": safe_error_message(e)})


@router.post("/sample-propose")
async def style_sample_propose(
    request: Request,
    project_id: str = Form(...),
    sample_ids: str = Form(...),
):
    """Generate proposals from style samples."""
    try:
        repo = get_repo(request)
        
        # Parse comma-separated sample IDs
        ids = [s.strip() for s in sample_ids.split(",") if s.strip()]
        
        # Use the helper function directly
        from ...style_bible.sample_proposal import propose_style_from_samples
        
        result = propose_style_from_samples(
            project_id=project_id,
            sample_ids=ids,
            repo=repo,
        )
        
        return render(request, "style.html", _build_style_context(repo, {"result": result}))
    except Exception as e:
        return render(request, "style.html", {"error": safe_error_message(e)})
