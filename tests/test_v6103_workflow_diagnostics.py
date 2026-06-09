"""v6.10.3 workflow diagnostics and stability tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from novel_factory.db.connection import init_db
from novel_factory.db.repository import Repository


def _repo(tmp_path: Path) -> Repository:
    db_path = tmp_path / "v6103.db"
    init_db(db_path)
    repo = Repository(str(db_path))
    repo.create_project("v6103-proj", "v6.10.3", "urban")
    repo.add_chapter("v6103-proj", 1, title="帝豪血衣令", status="reviewed")
    repo.save_chapter_content(
        "v6103-proj",
        1,
        "帝豪血衣令在掌心亮起，林辰借它反制赵天朗。",
        title="帝豪血衣令",
    )
    return repo


def test_title_guard_blocks_truncated_title_before_manual_publish(tmp_path):
    repo = _repo(tmp_path)
    repo.save_chapter_content(
        "v6103-proj",
        1,
        "帝豪血衣令在掌心亮起，林辰借它反制赵天朗。",
        title="第5章 三家世界五百强企业宣布无",
    )
    batch = repo.create_memory_batch("v6103-proj", chapter_number=1, run_id="mem", summary="trusted")
    repo.create_memory_item(
        batch_id=batch["id"],
        project_id="v6103-proj",
        target_table="story_facts",
        operation="create",
        after_json='{"fact_key":"title_guard.memory"}',
        confidence=0.9,
        evidence_text="可信记忆",
        rationale="MemoryCurator LLM 正文复核提取",
    )

    from fastapi.testclient import TestClient
    from novel_factory.api_app import create_api_app

    with TestClient(create_api_app(db_path=repo.db_path, llm_mode="stub")) as client:
        resp = client.post("/api/publish/chapter", json={"project_id": "v6103-proj", "chapter": 1})

    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "TITLE_GUARD_BLOCKED"
    assert body["error"]["details"]["domain_result"]["flags"]["title_blocking"] is True
    assert repo.get_chapter("v6103-proj", 1)["status"] == "reviewed"


def test_quality_gate_blocks_when_mandatory_checker_errors(tmp_path, monkeypatch):
    from novel_factory.workflow import nodes

    repo = _repo(tmp_path)
    repo.update_chapter_status("v6103-proj", 1, "polished")

    def broken_word_count(*args, **kwargs):
        raise RuntimeError("word count checker crashed")

    monkeypatch.setattr(nodes, "_check_word_count", broken_word_count)
    result = nodes.quality_gate_node(
        {
            "project_id": "v6103-proj",
            "chapter_number": 1,
            "chapter_status": "polished",
            "llm_mode": "stub",
        },
        repo,
    )

    gate = result["quality_gate"]
    assert gate["passed"] is False
    assert any("必需检查器 word_count_gate" in issue for issue in gate["blocking_issues"])
    assert gate["diagnostics"]["checker_health"]["policy"] == "mandatory_checker_failure_blocks_quality_gate"


def test_run_doctor_classifies_quality_gate_failure(tmp_path):
    from novel_factory.workflow.run_doctor import diagnose_run

    repo = _repo(tmp_path)
    run_id = repo.create_workflow_run("v6103-proj", 1)
    repo.update_workflow_run(
        run_id,
        status="blocked",
        current_node="quality_gate",
        error_message="Quality gate failed: 2 blocking issues",
    )
    repo.create_workflow_node_event(
        run_id=run_id,
        project_id="v6103-proj",
        chapter_number=1,
        node_name="quality_gate",
        event_type="failed",
        status="warning",
        message="Quality gate failed: 2 blocking issues",
    )
    run_data = repo.get_workflow_runs_for_project("v6103-proj", chapter_number=1, limit=1)[0]

    doctor = diagnose_run(repo, run_data, repo.get_chapter("v6103-proj", 1))

    assert doctor["category"] == "deterministic_quality_failure"
    assert doctor["next_action"] == "revise_by_gate"


def test_run_detail_includes_run_doctor(tmp_path):
    repo = _repo(tmp_path)
    run_id = repo.create_workflow_run("v6103-proj", 1)
    repo.update_workflow_run(
        run_id,
        status="failed",
        current_node="author",
        error_message="Author 纯正文生成空内容",
    )

    from fastapi.testclient import TestClient
    from novel_factory.api_app import create_api_app

    with TestClient(create_api_app(db_path=repo.db_path, llm_mode="stub")) as client:
        resp = client.get(f"/api/runs/{run_id}")

    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["run_doctor"]["category"] == "model_output_failure"
    assert body["data"]["run_doctor"]["next_action"] == "retry_node_or_switch_model"


def test_title_guard_accepts_matching_good_title():
    from novel_factory.quality.title_guard import validate_publish_title

    result = validate_publish_title("帝豪血衣令", "帝豪血衣令在掌心亮起，林辰借它反制赵天朗。")

    assert result.passed is True
    assert result.issues == []


def test_title_guard_accepts_chapter_prefixed_split_keyword_title():
    from novel_factory.quality.title_guard import validate_publish_title

    content = """第6章 喂养倒计时

林辰收到一条加密短信：利息需要“喂养”，坐标是“饲料”。
拍卖倒计时在走，江城的坐标也开始呼唤。"""

    result = validate_publish_title("第6章 喂养倒计时", content)

    assert result.passed is True
    assert result.evidence["semantic_title"] == "喂养倒计时"
    assert result.evidence["keyword_evidence"][0]["match_type"] == "bigram_coverage"


def test_title_guard_still_blocks_unrepresented_title():
    from novel_factory.quality.title_guard import validate_publish_title

    result = validate_publish_title("第6章 帝豪血衣令", "林辰收到短信，拍卖倒计时正在逼近。")

    assert result.passed is False
    assert any("标题与正文脱节" in issue for issue in result.issues)


def test_continuity_title_check_uses_split_keyword_coverage(tmp_path):
    from novel_factory.quality.continuity_gate import evaluate_chapter_continuity

    repo = _repo(tmp_path)
    content = """第6章 喂养倒计时

林辰收到一条加密短信：利息需要“喂养”，坐标是“饲料”。
拍卖倒计时在走，江城的坐标也开始呼唤。"""

    result = evaluate_chapter_continuity(
        repo,
        "v6103-proj",
        1,
        content,
        title="第6章 喂养倒计时",
    )

    assert not any("标题与正文脱节" in issue for issue in result.issues)
    assert result.evidence["title"]["keyword_evidence"][0]["match_type"] == "bigram_coverage"
