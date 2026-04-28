"""v5.2 Phase A Tests - Data CRUD + Project/Chapter Management.

Tests for:
1. Repository Mixins (WorldSetting, Character, Outline)
2. API Routes (CRUD endpoints)
3. Project cascade delete
4. Chapter reset (blocking → planned, revision → planned)
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


class TestRepositoryMixins:
    """Test new Repository Mixin methods."""

    def test_world_setting_crud(self):
        """WorldSettingRepositoryMixin provides full CRUD."""
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            repo = Repository(db_path)

            # Create project first
            repo.create_project(
                project_id="test_ws",
                name="Test Project",
                genre="玄幻",
            )

            # Create
            ws = repo.create_world_setting(
                project_id="test_ws",
                category="力量体系",
                title="修仙等级",
                content="练气、筑基、金丹...",
            )
            assert ws["id"] is not None
            assert ws["category"] == "力量体系"

            # Read
            fetched = repo.get_world_setting("test_ws", ws["id"])
            assert fetched["title"] == "修仙等级"

            # List
            all_ws = repo.list_world_settings("test_ws")
            assert len(all_ws) == 1

            # Update
            updated = repo.update_world_setting("test_ws", ws["id"], {"content": "更新后的内容"})
            assert updated["content"] == "更新后的内容"

            # Delete
            assert repo.delete_world_setting("test_ws", ws["id"]) is True
            assert repo.get_world_setting("test_ws", ws["id"]) is None

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_character_crud(self):
        """CharacterRepositoryMixin provides full CRUD."""
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            repo = Repository(db_path)

            repo.create_project(
                project_id="test_char",
                name="Test Project",
                genre="玄幻",
            )

            # Create
            char = repo.create_character(
                project_id="test_char",
                name="张三",
                role="protagonist",
                description="主角",
            )
            assert char["id"] is not None
            assert char["role"] == "protagonist"

            # Read
            fetched = repo.get_character("test_char", char["id"])
            assert fetched["name"] == "张三"

            # List (active only by default)
            repo.create_character(
                project_id="test_char",
                name="李四",
                role="supporting",
            )
            active = repo.list_characters("test_char")
            assert len(active) == 2

            # Update status to inactive
            repo.update_character("test_char", char["id"], {"status": "inactive"})
            active_after = repo.list_characters("test_char", include_inactive=False)
            assert len(active_after) == 1

            # Delete
            assert repo.delete_character("test_char", char["id"]) is True

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_outline_crud(self):
        """OutlineRepositoryMixin provides full CRUD."""
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            repo = Repository(db_path)

            repo.create_project(
                project_id="test_outline",
                name="Test Project",
                genre="玄幻",
            )

            # Create
            outline = repo.create_outline(
                project_id="test_outline",
                level="volume",
                sequence=1,
                title="第一卷",
                content="开篇",
                chapters_range="1-10",
            )
            assert outline["id"] is not None
            assert outline["level"] == "volume"

            # Read
            fetched = repo.get_outline("test_outline", outline["id"])
            assert fetched["title"] == "第一卷"

            # Get by level
            repo.create_outline(
                project_id="test_outline",
                level="arc",
                sequence=1,
                title="第一篇章",
            )
            volumes = repo.get_outlines_by_level("test_outline", "volume")
            assert len(volumes) == 1

            arcs = repo.get_outlines_by_level("test_outline", "arc")
            assert len(arcs) == 1

            # Delete
            assert repo.delete_outline("test_outline", outline["id"]) is True

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestProjectCascadeDelete:
    """Test project cascade delete functionality."""

    def test_delete_project_cascades_to_characters(self):
        """Deleting a project should delete all its characters."""
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            repo = Repository(db_path)

            # Create project with characters
            repo.create_project(project_id="cascade_test", name="Cascade Test")
            repo.create_character(project_id="cascade_test", name="角色1", role="protagonist")
            repo.create_character(project_id="cascade_test", name="角色2", role="supporting")

            # Verify characters exist
            chars = repo.list_characters("cascade_test", include_inactive=True)
            assert len(chars) == 2

            # Delete project
            assert repo.delete_project("cascade_test") is True

            # Verify characters are gone
            chars_after = repo.list_characters("cascade_test", include_inactive=True)
            assert len(chars_after) == 0

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_delete_project_cascades_to_outlines(self):
        """Deleting a project should delete all its outlines."""
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            repo = Repository(db_path)

            repo.create_project(project_id="cascade_outline", name="Test")
            repo.create_outline(project_id="cascade_outline", level="volume", sequence=1, title="第一卷")

            assert len(repo.list_outlines("cascade_outline")) == 1

            repo.delete_project("cascade_outline")

            assert len(repo.list_outlines("cascade_outline")) == 0

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_delete_project_cascades_to_world_settings(self):
        """Deleting a project should delete all its world settings."""
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            repo = Repository(db_path)

            repo.create_project(project_id="cascade_ws", name="Test")
            repo.create_world_setting(project_id="cascade_ws", category="设定", title="世界观")

            assert len(repo.list_world_settings("cascade_ws")) == 1

            repo.delete_project("cascade_ws")

            assert len(repo.list_world_settings("cascade_ws")) == 0

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestChapterReset:
    """Test chapter reset functionality."""

    def test_reset_blocking_chapter(self):
        """Resetting a blocking chapter should change status to planned."""
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            repo = Repository(db_path)

            repo.create_project(project_id="reset_test", name="Test")
            repo.add_chapter(project_id="reset_test", chapter_number=1, title="第一章", status="blocking")

            # Reset
            assert repo.reset_chapter("reset_test", 1) is True

            # Verify status changed
            chapter = repo.get_chapter("reset_test", 1)
            assert chapter["status"] == "planned"

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_reset_revision_chapter(self):
        """Resetting a revision chapter should change status to planned."""
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            repo = Repository(db_path)

            repo.create_project(project_id="reset_rev", name="Test")
            repo.add_chapter(project_id="reset_rev", chapter_number=1, title="第一章", status="revision")

            assert repo.reset_chapter("reset_rev", 1) is True

            chapter = repo.get_chapter("reset_rev", 1)
            assert chapter["status"] == "planned"

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_cannot_reset_other_statuses(self):
        """Resetting other statuses should return False."""
        from novel_factory.db.repository import Repository
        from novel_factory.db.connection import init_db

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            repo = Repository(db_path)

            repo.create_project(project_id="reset_other", name="Test")
            repo.add_chapter(project_id="reset_other", chapter_number=1, title="第一章", status="published")

            # Should not reset published chapter
            assert repo.reset_chapter("reset_other", 1) is False

            chapter = repo.get_chapter("reset_other", 1)
            assert chapter["status"] == "published"

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestAPIRoutes:
    """Test new API routes."""

    def test_characters_crud_api(self):
        """Characters API provides CRUD operations."""
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            app = create_api_app(db_path=db_path, llm_mode="stub")
            client = TestClient(app)

            # Create project first
            client.post("/api/onboarding/projects", json={
                "project_id": "api_char_test",
                "name": "API Test",
                "genre": "玄幻",
                "initial_chapter_count": 1,
            })

            # Create character
            resp = client.post("/api/projects/api_char_test/characters", json={
                "name": "API角色",
                "role": "protagonist",
                "description": "测试角色",
            })
            assert resp.json()["ok"] is True
            char_id = resp.json()["data"]["id"]

            # List characters
            resp = client.get("/api/projects/api_char_test/characters")
            assert len(resp.json()["data"]) == 1

            # Get character
            resp = client.get(f"/api/projects/api_char_test/characters/{char_id}")
            assert resp.json()["data"]["name"] == "API角色"

            # Update character
            resp = client.put(f"/api/projects/api_char_test/characters/{char_id}", json={
                "description": "更新后的描述",
            })
            assert resp.json()["data"]["description"] == "更新后的描述"

            # Delete character
            resp = client.delete(f"/api/projects/api_char_test/characters/{char_id}")
            assert resp.json()["data"]["deleted"] is True

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_outlines_crud_api(self):
        """Outlines API provides CRUD operations."""
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            app = create_api_app(db_path=db_path, llm_mode="stub")
            client = TestClient(app)

            client.post("/api/onboarding/projects", json={
                "project_id": "api_outline_test",
                "name": "API Test",
                "initial_chapter_count": 1,
            })

            # Onboarding creates one outline, so we should have 1 already
            resp = client.get("/api/projects/api_outline_test/outlines")
            initial_count = len(resp.json()["data"])

            # Create another outline
            resp = client.post("/api/projects/api_outline_test/outlines", json={
                "level": "arc",
                "sequence": 1,
                "title": "第一篇章",
            })
            assert resp.json()["ok"] is True
            outline_id = resp.json()["data"]["id"]

            # Get by level
            resp = client.get("/api/projects/api_outline_test/outlines?level=arc")
            assert len(resp.json()["data"]) == 1

            # Delete
            resp = client.delete(f"/api/projects/api_outline_test/outlines/{outline_id}")
            assert resp.json()["data"]["deleted"] is True

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_world_settings_crud_api(self):
        """World Settings API provides CRUD operations."""
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            app = create_api_app(db_path=db_path, llm_mode="stub")
            client = TestClient(app)

            client.post("/api/onboarding/projects", json={
                "project_id": "api_ws_test",
                "name": "API Test",
                "initial_chapter_count": 1,
            })

            # Create world setting
            resp = client.post("/api/projects/api_ws_test/world-settings", json={
                "category": "世界观",
                "title": "设定一",
                "content": "内容",
            })
            assert resp.json()["ok"] is True
            ws_id = resp.json()["data"]["id"]

            # List
            resp = client.get("/api/projects/api_ws_test/world-settings")
            assert len(resp.json()["data"]) == 1

            # Delete
            resp = client.delete(f"/api/projects/api_ws_test/world-settings/{ws_id}")
            assert resp.json()["data"]["deleted"] is True

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_delete_project_api(self):
        """DELETE /api/projects/{id} should cascade delete."""
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            app = create_api_app(db_path=db_path, llm_mode="stub")
            client = TestClient(app)

            # Create project with characters
            client.post("/api/onboarding/projects", json={
                "project_id": "delete_api_test",
                "name": "To Delete",
                "initial_chapter_count": 1,
                "main_character_name": "主角",
            })

            # Delete project
            resp = client.delete("/api/projects/delete_api_test")
            assert resp.json()["ok"] is True

            # Verify project is gone
            resp = client.get("/api/projects/delete_api_test")
            assert resp.json()["ok"] is False

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_reset_chapter_api(self):
        """POST /api/projects/{id}/chapters/{n}/reset should reset chapter."""
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            app = create_api_app(db_path=db_path, llm_mode="stub")
            client = TestClient(app)

            client.post("/api/onboarding/projects", json={
                "project_id": "reset_api_test",
                "name": "Reset Test",
                "initial_chapter_count": 1,
            })

            # Manually set chapter to blocking
            from novel_factory.db.repository import Repository
            repo = Repository(db_path)
            repo.update_chapter_status("reset_api_test", 1, "blocking")

            # Reset via API
            resp = client.post("/api/projects/reset_api_test/chapters/1/reset")
            assert resp.json()["ok"] is True
            assert resp.json()["data"]["new_status"] == "planned"

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestOnboardingSeedData:
    """Test onboarding creates seed data for characters, outlines, world_settings."""

    def test_onboarding_creates_character(self):
        """Onboarding with main_character_name should create a character."""
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            app = create_api_app(db_path=db_path, llm_mode="stub")
            client = TestClient(app)

            resp = client.post("/api/onboarding/projects", json={
                "project_id": "seed_char_test",
                "name": "Seed Test",
                "initial_chapter_count": 5,
                "main_character_name": "张三",
                "main_character_role": "protagonist",
                "main_character_description": "主角描述",
            })

            assert resp.json()["ok"] is True
            data = resp.json()["data"]
            assert len(data["characters"]) == 1
            assert data["characters"][0]["name"] == "张三"

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_onboarding_creates_outline(self):
        """Onboarding should create initial volume outline."""
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            app = create_api_app(db_path=db_path, llm_mode="stub")
            client = TestClient(app)

            resp = client.post("/api/onboarding/projects", json={
                "project_id": "seed_outline_test",
                "name": "Seed Outline Test",
                "initial_chapter_count": 10,
            })

            data = resp.json()["data"]
            assert len(data["outlines"]) == 1
            assert data["outlines"][0]["level"] == "volume"

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_onboarding_creates_world_setting(self):
        """Onboarding with world_setting should create world setting."""
        from novel_factory.db.connection import init_db
        from novel_factory.api_app import create_api_app

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            init_db(db_path)
            app = create_api_app(db_path=db_path, llm_mode="stub")
            client = TestClient(app)

            resp = client.post("/api/onboarding/projects", json={
                "project_id": "seed_ws_test",
                "name": "Seed WS Test",
                "initial_chapter_count": 5,
                "world_setting": "修仙世界，灵气复苏",
            })

            data = resp.json()["data"]
            assert len(data["world_settings"]) == 1
            assert "修仙" in data["world_settings"][0]["content"]

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
