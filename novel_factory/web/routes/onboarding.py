"""Onboarding route - create new novel project via Web UI."""

from __future__ import annotations

import json
import sqlite3
from fastapi import APIRouter, Request, Form

from ..deps import get_repo, render, safe_error_message
from ...style_bible.templates import list_templates, load_style_bible_template

router = APIRouter()


@router.get("")
async def onboarding_form(request: Request):
    """Show onboarding form for creating a new project."""
    # Load templates from v4.0 Style Bible template system
    templates = list_templates()
    template_ids = sorted(templates.keys())
    
    return render(
        request,
        "onboarding.html",
        {
            "style_templates": template_ids,
        },
    )


@router.post("/project")
async def create_project(
    request: Request,
    project_id: str = Form(...),
    name: str = Form(...),
    genre: str = Form(""),
    description: str = Form(""),
    total_chapters_planned: int = Form(500),
    target_words: int = Form(1500000),
    start_chapter: int = Form(1),
    initial_chapter_count: int = Form(10),
    style_template: str = Form("default_web_serial"),
    opening_objective: str = Form(""),
    world_setting: str = Form(""),
    main_character_name: str = Form(""),
    main_character_role: str = Form("protagonist"),
    main_character_description: str = Form(""),
    create_serial_plan: str = Form(""),
    serial_batch_size: int = Form(5),
):
    """Create a new project with initial chapters and Style Bible."""
    try:
        repo = get_repo(request)
        
        # Load templates for error responses
        templates = list_templates()
        template_ids = sorted(templates.keys())

        # Validate project_id doesn't already exist
        existing = repo.get_project(project_id)
        if existing:
            return render(
                request,
                "onboarding.html",
                {
                    "error": f"项目 ID '{project_id}' 已存在，请使用其他 ID",
                    "style_templates": template_ids,
                    "form_data": {
                        "project_id": project_id,
                        "name": name,
                        "genre": genre,
                        "description": description,
                        "total_chapters_planned": total_chapters_planned,
                        "target_words": target_words,
                        "start_chapter": start_chapter,
                        "initial_chapter_count": initial_chapter_count,
                        "style_template": style_template,
                        "opening_objective": opening_objective,
                        "world_setting": world_setting,
                        "main_character_name": main_character_name,
                        "main_character_role": main_character_role,
                        "main_character_description": main_character_description,
                        "create_serial_plan": create_serial_plan,
                        "serial_batch_size": serial_batch_size,
                    },
                },
                status_code=400,
            )

        # Validate chapter counts
        if initial_chapter_count < 1:
            return render(
                request,
                "onboarding.html",
                {
                    "error": "初始章节数必须至少为 1",
                    "style_templates": template_ids,
                },
                status_code=400,
            )

        if start_chapter < 1:
            return render(
                request,
                "onboarding.html",
                {
                    "error": "起始章节号必须至少为 1",
                    "style_templates": template_ids,
                },
                status_code=400,
            )

        # Validate total_chapters_planned covers initial chapters
        end_chapter = start_chapter + initial_chapter_count - 1
        if total_chapters_planned < end_chapter:
            return render(
                request,
                "onboarding.html",
                {
                    "error": f"计划总章节数 ({total_chapters_planned}) 不能小于初始章节范围 ({start_chapter}-{end_chapter})",
                    "style_templates": template_ids,
                },
                status_code=400,
            )

        # Validate style template
        if style_template not in templates:
            return render(
                request,
                "onboarding.html",
                {
                    "error": f"无效的风格模板: {style_template}",
                    "style_templates": template_ids,
                },
                status_code=400,
            )

        # Load Style Bible template
        style_bible_template = load_style_bible_template(style_template)
        
        # Use atomic transaction for all database writes
        conn = repo._conn()
        try:
            # 1. Create project
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "INSERT INTO projects "
                "(project_id, name, genre, description, total_chapters_planned, "
                "target_words, current_chapter, status, is_current, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?)",
                (
                    project_id,
                    name,
                    genre,
                    description,
                    total_chapters_planned,
                    target_words,
                    start_chapter,
                    now,
                    now,
                ),
            )

            # 2. Create initial chapters with planned status
            for chapter_num in range(start_chapter, end_chapter + 1):
                conn.execute(
                    "INSERT INTO chapters (project_id, chapter_number, title, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'planned', ?, ?)",
                    (project_id, chapter_num, f"第 {chapter_num} 章", now, now),
                )

            # 3. Create first chapter instruction
            if opening_objective:
                conn.execute(
                    "INSERT OR REPLACE INTO instructions "
                    "(project_id, chapter_number, objective, key_events, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, '', 'active', ?, ?)",
                    (project_id, start_chapter, opening_objective, now, now),
                )

            # 4. Optionally create world setting
            if world_setting:
                conn.execute(
                    "INSERT INTO world_settings (project_id, category, title, content, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (project_id, "世界观", "基础世界观", world_setting, now),
                )

            # 5. Optionally create main character
            if main_character_name:
                conn.execute(
                    "INSERT INTO characters "
                    "(project_id, name, alias, role, description, first_appearance, status, created_at) "
                    "VALUES (?, ?, '', ?, ?, ?, 'active', ?)",
                    (project_id, main_character_name, main_character_role, 
                     main_character_description, start_chapter, now),
                )

            # 6. Initialize Style Bible
            import uuid
            bible_id = str(uuid.uuid4())
            style_bible_dict = style_bible_template.copy()
            style_bible_dict["genre"] = genre or style_bible_dict.get("genre", "")
            style_bible_dict.pop("description", None)  # Remove metadata field
            
            conn.execute(
                "INSERT INTO style_bibles "
                "(id, project_id, name, genre, target_platform, target_audience, "
                "bible_json, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, '1.0.0', ?, ?)",
                (
                    bible_id,
                    project_id,
                    style_bible_dict.get("name", "Default Style Bible"),
                    style_bible_dict.get("genre", ""),
                    style_bible_dict.get("target_platform", ""),
                    style_bible_dict.get("target_audience", ""),
                    json.dumps(style_bible_dict, ensure_ascii=False),
                    now,
                    now,
                ),
            )

            # 7. Optionally create Serial Plan
            serial_plan_id = None
            if create_serial_plan == "on":
                serial_plan_id = f"serial_{uuid.uuid4().hex[:12]}"
                total_planned = end_chapter - start_chapter + 1
                conn.execute(
                    "INSERT INTO serial_plans "
                    "(id, project_id, name, start_chapter, target_chapter, batch_size, "
                    "current_chapter, status, total_planned_chapters, completed_chapters, "
                    "created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, 0, ?, ?)",
                    (
                        serial_plan_id,
                        project_id,
                        f"{name} - Serial Plan",
                        start_chapter,
                        end_chapter,
                        serial_batch_size,
                        start_chapter,
                        total_planned,
                        now,
                        now,
                    ),
                )

            # Commit all changes atomically
            conn.commit()
            
        except Exception as e:
            # Rollback on any error - no partial state left
            conn.rollback()
            raise
        finally:
            conn.close()

        # Success - show success page
        return render(
            request,
            "onboarding_success.html",
            {
                "project_id": project_id,
                "name": name,
                "initial_chapter_count": initial_chapter_count,
                "start_chapter": start_chapter,
                "end_chapter": end_chapter,
                "serial_plan_id": serial_plan_id,
            },
        )

    except sqlite3.IntegrityError as e:
        templates = list_templates()
        return render(
            request,
            "onboarding.html",
            {
                "error": f"数据库冲突: {safe_error_message(e)}",
                "style_templates": sorted(templates.keys()),
            },
            status_code=400,
        )
    except Exception as e:
        templates = list_templates()
        return render(
            request,
            "onboarding.html",
            {
                "error": safe_error_message(e),
                "style_templates": sorted(templates.keys()),
            },
            status_code=500,
        )
