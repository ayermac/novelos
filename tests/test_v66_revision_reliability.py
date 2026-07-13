"""v6.6.0 Revision Reliability 完整系统级测试"""

import pytest
import tempfile
import os
from novel_factory.quality.hub import VersionRegressionGuard
from novel_factory.quality.hub import DeadloopDetector
from novel_factory.validators.word_count_policy import WordCountPolicy, DEFAULT_POLICY
from novel_factory.quality.editor_strategy import classify_editor_result, post_process_llm_decision
from novel_factory.db.best_version_recovery import find_best_chapter_version
from novel_factory.validators.chapter_checker import check_word_count_quality_gate, check_word_count_upper_gate


def test_version_regression_guard():
    guard = VersionRegressionGuard()
    current = "x" * 4200
    new_short = "y" * 3400
    reject, _ = guard.should_reject_new_draft(current, new_short, 4000)
    assert reject is True


def test_version_regression_guard_allows_system_compression():
    guard = VersionRegressionGuard()
    current = "x" * 4119
    compressed = "y" * 3255

    reject, reason = guard.should_reject_new_draft(
        current,
        compressed,
        3000,
        editor_suggestions=[],
        allow_system_compression=True,
    )

    assert reject is False
    assert reason == ""


def test_deadloop_detector():
    class FakeRepo:
        def get_chapter(self, *a): return {"status": "revision"}
        def get_chapter_version_count(self, *a): return 22
        def count_recent_failed_workflow_runs(self, *a): return 0

    result = DeadloopDetector.check_deadloop(FakeRepo(), "p", 1)
    assert result["triggered"]


def test_word_count_policy():
    policy = WordCountPolicy()
    assert policy.evaluate(3419, 4000)[1] == "warning"
    assert policy.evaluate(3300, 4000)[1] == "hard_fail"
    assert policy.evaluate(3800, 4000)[1] == "ok"


def test_canonical_word_count_gate_uses_policy_warning_band():
    passed, message = check_word_count_quality_gate("x" * 3419, 4000, "editor")
    assert passed is True
    assert "偏低" in message

    passed, message = check_word_count_quality_gate("x" * 3300, 4000, "editor")
    assert passed is False
    assert "字数未达标" in message


def test_word_count_upper_gate_rejects_extreme_overlength():
    passed, message = check_word_count_upper_gate("x" * 4926, 3000, "author")
    assert passed is False
    assert "字数超标" in message


def test_author_plain_text_context_contains_revision_feedback(monkeypatch):
    from novel_factory.agents.author import AuthorAgent
    from novel_factory.models.state import ChapterStatus

    agent = AuthorAgent.__new__(AuthorAgent)
    agent.repo = type("Repo", (), {"get_characters": lambda self, project_id: []})()
    monkeypatch.setattr(agent, "_get_instruction", lambda state: {"objective": "修复章节", "key_events": "[]"})
    monkeypatch.setattr(agent, "_get_scene_beats", lambda state: [])
    monkeypatch.setattr(agent, "_get_chapter_info", lambda state: {
        "id": 1,
        "project_id": "p",
        "status": ChapterStatus.REVISION.value,
    })

    context = agent._build_plain_text_context({
        "project_id": "p",
        "chapter_number": 1,
        "chapter_status": ChapterStatus.REVISION.value,
        "_revision_review": {
            "score": 83,
            "revision_target": "author",
            "issues": ["对白太书面"],
            "suggestions": ["增加打断和口语化反应"],
        },
    }, "fallback")

    assert "【退回问题】" in context
    assert "对白太书面" in context
    assert "增加打断和口语化反应" in context


def test_editor_strategy_high_score():
    decision = classify_editor_result(86, ["advisory only"])
    assert decision.pass_ is True
    assert decision.revision_needed is False


def test_editor_strategy_low_score():
    decision = classify_editor_result(76, ["logic issue"])
    assert decision.revision_needed is True


def test_editor_strategy_high_score_hard_logic_still_blocks():
    decision = classify_editor_result(86, ["逻辑漏洞：时间线矛盾"])
    assert decision.pass_ is False
    assert decision.category == "blocking"


def test_post_process_llm_over_strict():
    decision = post_process_llm_decision(False, 87, ["minor style"])
    assert decision.pass_ is True


def test_best_version_recovery_logic():
    class FakeRepo:
        def get_chapter_versions(self, pid, ch):
            return [
                {"id": 1, "content": "a" * 3000, "review_score": 70},
                {"id": 2, "content": "b" * 4100, "review_score": 88},
            ]
    best = find_best_chapter_version(FakeRepo(), "p", 1, 4000)
    assert best["review_score"] == 88


def test_best_version_recovery_uses_repository_version_api():
    class FakeRepo:
        def list_chapter_versions(self, pid, ch):
            return [
                {"id": 1, "version": 1, "word_count": 4100, "review_score": 70},
                {"id": 2, "version": 2, "word_count": 4050, "review_score": 88},
            ]

        def get_version_by_id(self, pid, version_id):
            return {
                "id": version_id,
                "content": ("a" if version_id == 1 else "b") * 4100,
                "review_score": 70 if version_id == 1 else 88,
            }

    best = find_best_chapter_version(FakeRepo(), "p", 1, 4000)
    assert best["id"] == 2


def test_deadloop_failed_runs_are_scoped_after_manual_reset():
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        init_db(db_path)
        repo = Repository(db_path)
        repo.create_project(project_id="deadloop-reset", name="Deadloop Reset", genre="科幻")
        repo.add_chapter(
            project_id="deadloop-reset",
            chapter_number=1,
            title="第一章",
            status="blocking",
        )

        run_ids = []
        for i in range(7):
            run_id = repo.create_workflow_run("deadloop-reset", 1)
            repo.update_workflow_run(run_id, status="failed", error_message=f"失败 {i}")
            run_ids.append(run_id)

        conn = repo._conn()
        try:
            for idx, run_id in enumerate(run_ids):
                conn.execute(
                    "UPDATE workflow_runs SET started_at=? WHERE id=?",
                    (f"2026-01-01 00:0{idx}:00", run_id),
                )
            conn.commit()
        finally:
            conn.close()

        before = DeadloopDetector.check_deadloop(repo, "deadloop-reset", 1)
        assert before["triggered"] is True
        assert "失败 workflow" in before["reason"]

        assert repo.reset_chapter("deadloop-reset", 1) is True
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE task_status SET completed_at='2026-01-02 00:00:00' "
                "WHERE project_id='deadloop-reset' AND chapter_number=1 AND task_type='reset'"
            )
            conn.commit()
        finally:
            conn.close()

        after = DeadloopDetector.check_deadloop(repo, "deadloop-reset", 1)
        assert after["triggered"] is False
        assert repo.count_recent_failed_workflow_runs(
            "deadloop-reset",
            1,
            since=repo.get_latest_chapter_reset_marker("deadloop-reset", 1),
        ) == 0
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_deadloop_version_count_is_scoped_after_manual_reset():
    from novel_factory.db.connection import init_db
    from novel_factory.db.repository import Repository

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        init_db(db_path)
        repo = Repository(db_path)
        repo.create_project(project_id="version-reset", name="Version Reset", genre="科幻")
        repo.add_chapter(
            project_id="version-reset",
            chapter_number=1,
            title="第一章",
            status="blocking",
        )
        for i in range(22):
            repo.save_version(
                "version-reset",
                1,
                f"第 {i} 个历史版本" + ("内容" * 120),
                created_by="author",
            )

        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE chapter_versions SET created_at='2026-01-01 00:00:00' "
                "WHERE project_id='version-reset' AND chapter=1"
            )
            conn.commit()
        finally:
            conn.close()

        before = DeadloopDetector.check_deadloop(repo, "version-reset", 1)
        assert before["triggered"] is True
        assert "版本数超过阈值" in before["reason"]

        assert repo.reset_chapter("version-reset", 1) is True
        conn = repo._conn()
        try:
            conn.execute(
                "UPDATE task_status SET completed_at='2026-01-02 00:00:00' "
                "WHERE project_id='version-reset' AND chapter_number=1 AND task_type='reset'"
            )
            conn.commit()
        finally:
            conn.close()

        after = DeadloopDetector.check_deadloop(repo, "version-reset", 1)
        assert after["triggered"] is False
        assert repo.get_chapter_version_count(
            "version-reset",
            1,
            since=repo.get_latest_chapter_reset_marker("version-reset", 1),
        ) == 0
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
