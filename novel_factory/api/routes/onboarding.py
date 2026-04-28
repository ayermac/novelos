"""Onboarding API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..envelope import envelope_response, error_response, EnvelopeResponse

router = APIRouter()


class CreateProjectRequest(BaseModel):
    """Create project request."""

    project_id: str
    name: str
    genre: str | None = None
    description: str | None = None
    total_chapters_planned: int = 500
    target_words: int = 1500000
    style_template: str = "default_web_serial"
    start_chapter: int = 1
    initial_chapter_count: int = 10
    opening_objective: str | None = None
    world_setting: str | None = None
    main_character_name: str | None = None
    main_character_role: str = "protagonist"
    main_character_description: str | None = None
    main_character_traits: str | None = None
    create_serial_plan: bool = False
    serial_batch_size: int = 5


@router.post("/onboarding/projects")
async def create_project(request: Request, body: CreateProjectRequest) -> EnvelopeResponse:
    """Create a new project with initial chapters.

    This is the API equivalent of the onboarding form.
    In stub mode, does not trigger real LLM calls.
    """
    from ..deps import get_repo, get_dispatcher, get_llm_mode

    try:
        repo = get_repo(request)
        llm_mode = get_llm_mode(request)

        # Check if project already exists
        existing = repo.get_project(body.project_id)
        if existing:
            return error_response("VALIDATION_ERROR", f"项目 '{body.project_id}' 已存在")

        # Create project
        repo.create_project(
            project_id=body.project_id,
            name=body.name,
            genre=body.genre or "",
            description=body.description or "",
            total_chapters_planned=body.total_chapters_planned,
            target_words=body.target_words,
        )
        project = repo.get_project(body.project_id)

        # Create initial chapters
        chapters = []
        for i in range(body.initial_chapter_count):
            chapter_num = body.start_chapter + i
            ch_id = repo.add_chapter(
                project_id=body.project_id,
                chapter_number=chapter_num,
                title=f"第 {chapter_num} 章",
                status="planned",
            )
            chapters.append({"chapter_number": chapter_num, "id": ch_id})

        # Create serial plan if requested
        serial_plan = None
        if body.create_serial_plan:
            from ..deps import get_settings
            settings = get_settings(request)
            dispatcher = get_dispatcher(request)
            serial_plan = repo.create_serial_plan(
                project_id=body.project_id,
                batch_size=body.serial_batch_size,
                total_chapters=body.total_chapters_planned,
            )

        # Add seed data for stub mode demonstration
        characters = []
        outlines = []
        world_settings = []

        # Add main character if provided
        if body.main_character_name:
            char = repo.create_character(
                project_id=body.project_id,
                name=body.main_character_name,
                role=body.main_character_role,
                description=body.main_character_description or "",
                traits=body.main_character_traits or "",
                first_appearance=1,
            )
            characters.append(char)

        # Add world setting if provided
        if body.world_setting:
            ws = repo.create_world_setting(
                project_id=body.project_id,
                category="世界观",
                title="背景设定",
                content=body.world_setting,
            )
            world_settings.append(ws)

        # Add sample outline structure (volume 1)
        outline = repo.create_outline(
            project_id=body.project_id,
            level="volume",
            sequence=1,
            title="第一卷",
            content=f"{body.name} 第一卷：开局",
            chapters_range=f"{body.start_chapter}-{body.start_chapter + 9}",
        )
        outlines.append(outline)

        return envelope_response({
            "project": project,
            "chapters": chapters,
            "characters": characters,
            "outlines": outlines,
            "world_settings": world_settings,
            "serial_plan": serial_plan,
            "llm_mode": llm_mode,
        })

    except Exception as e:
        return error_response("INTERNAL_ERROR", f"创建项目失败: {str(e)}")
