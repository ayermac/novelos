from __future__ import annotations

import tempfile

from novel_factory.config.settings import load_settings
from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository
from novel_factory.workflow.runner import run_with_graph


def test_run_auto_creates_next_arc_plan_when_chapter_exceeds_existing_outline():
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = temp_file.name
    temp_file.close()
    try:
        init_db(db_path)
        repo = Repository(db_path)
        project_id = "auto-arc-test"
        repo.create_project(
            project_id=project_id,
            name="潮汐档案",
            genre="科幻悬疑",
            description="近未来海洋城邦中的潮汐能源系统、失联案与记忆篡改谜团。",
            target_words=60000,
            total_chapters_planned=20,
            current_chapter=13,
        )
        repo.create_world_setting(
            project_id=project_id,
            category="城市系统",
            title="潮汐能源城邦",
            content="城市依赖潮汐能源系统运行，旧档案与联网审计互相牵制。",
        )
        repo.create_character(
            project_id=project_id,
            name="陆澈",
            role="protagonist",
            description="调查局人员，追查潮汐档案中的身份补录谜团。",
        )
        repo.create_outline(
            project_id=project_id,
            level="arc",
            sequence=1,
            title="第一阶段",
            content="陆澈从机房线索追到外环旧库。",
            chapters_range="1-10",
        )
        conn = repo._conn()
        try:
            conn.execute(
                """INSERT INTO chapters
                (project_id, chapter_number, title, status, word_count)
                VALUES (?, ?, ?, ?, ?)""",
                (project_id, 13, "第13章", "planned", 0),
            )
            conn.commit()
        finally:
            conn.close()

        settings = load_settings()
        settings.db_path = db_path

        result = run_with_graph(project_id, 13, settings, repo, "stub")

        assert result.get("context_incomplete") is not True
        assert "第13章大纲" not in result.get("missing", [])
        outlines = repo.list_outlines(project_id)
        assert any(o.get("chapters_range") == "11-20" for o in outlines)
        instruction = repo.get_instruction_by_chapter(project_id, 13)
        assert instruction is not None
        assert instruction["objective"]
    finally:
        import os

        os.unlink(db_path)


def test_run_guard_auto_creates_continuation_instruction_for_next_arc():
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = temp_file.name
    temp_file.close()
    try:
        init_db(db_path)
        repo = Repository(db_path)
        project_id = "auto-arc-guard-test"
        repo.create_project(
            project_id=project_id,
            name="潮汐档案",
            genre="科幻悬疑",
            description="近未来海洋城邦中的潮汐能源系统、失联案与记忆篡改谜团。",
            target_words=60000,
            total_chapters_planned=20,
            current_chapter=13,
        )
        repo.create_genesis_run(project_id, input_json='{"title":"潮汐档案"}', status="approved")
        repo.create_world_setting(
            project_id=project_id,
            category="城市系统",
            title="潮汐能源城邦",
            content="城市依赖潮汐能源系统运行。",
        )
        repo.create_character(
            project_id=project_id,
            name="陆澈",
            role="protagonist",
            description="调查局人员。",
        )
        repo.create_outline(
            project_id=project_id,
            level="arc",
            sequence=1,
            title="第一阶段",
            content="陆澈从机房线索追到外环旧库。",
            chapters_range="1-10",
        )
        repo.add_chapter(project_id, 13, "第 13 章", status="planned")

        from novel_factory.api.routes._run_guards import check_chapter_run_guard

        err, _preflight = check_chapter_run_guard(repo, project_id, 13)
        assert err is None
        assert repo.get_instruction_by_chapter(project_id, 13) is not None
        assert any(o.get("chapters_range") == "11-20" for o in repo.list_outlines(project_id))
    finally:
        import os

        os.unlink(db_path)


def test_run_guard_auto_creates_missing_instruction_when_arc_outline_exists():
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = temp_file.name
    temp_file.close()
    try:
        init_db(db_path)
        repo = Repository(db_path)
        project_id = "auto-instruction-guard-test"
        repo.create_project(
            project_id=project_id,
            name="潮汐档案",
            genre="科幻悬疑",
            description="近未来海洋城邦中的潮汐能源系统、失联案与记忆篡改谜团。",
            target_words=60000,
            total_chapters_planned=20,
            current_chapter=13,
        )
        repo.create_genesis_run(project_id, input_json='{"title":"潮汐档案"}', status="approved")
        repo.create_world_setting(
            project_id=project_id,
            category="城市系统",
            title="潮汐能源城邦",
            content="城市依赖潮汐能源系统运行。",
        )
        repo.create_character(
            project_id=project_id,
            name="陆澈",
            role="protagonist",
            description="调查局人员。",
        )
        repo.create_outline(
            project_id=project_id,
            level="arc",
            sequence=2,
            title="第二阶段",
            content="陆澈进入外环暂存点。",
            chapters_range="11-20",
        )
        repo.add_chapter(project_id, 13, "第 13 章", status="planned")

        from novel_factory.api.routes._run_guards import check_chapter_run_guard

        err, _preflight = check_chapter_run_guard(repo, project_id, 13)
        assert err is None
        instruction = repo.get_instruction_by_chapter(project_id, 13)
        assert instruction is not None
        assert instruction["objective"]
    finally:
        import os

        os.unlink(db_path)


def test_continuation_plan_only_creates_instruction_for_requested_chapter():
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = temp_file.name
    temp_file.close()
    try:
        init_db(db_path)
        repo = Repository(db_path)
        project_id = "auto-instruction-current-only-test"
        repo.create_project(
            project_id=project_id,
            name="潮汐档案",
            genre="科幻悬疑",
            description="近未来海洋城邦中的潮汐能源系统、失联案与记忆篡改谜团。",
            target_words=60000,
            total_chapters_planned=20,
            current_chapter=13,
        )
        repo.create_outline(
            project_id=project_id,
            level="arc",
            sequence=2,
            title="第二阶段",
            content="陆澈进入外环暂存点。",
            chapters_range="11-20",
        )

        from novel_factory.workflow.continuation_plan import ensure_continuation_plan_for_chapter

        result = ensure_continuation_plan_for_chapter(repo, project_id, 13)

        assert result["created_instructions"] == 1
        assert repo.get_instruction_by_chapter(project_id, 13) is not None
        assert repo.get_instruction_by_chapter(project_id, 14) is None
        assert repo.get_instruction_by_chapter(project_id, 20) is None
    finally:
        import os

        os.unlink(db_path)
