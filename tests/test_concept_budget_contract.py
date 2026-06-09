"""Concept budget prompt contract tests."""


def test_planner_and_screenwriter_include_concept_budget_contract():
    from novel_factory.agents.planner import PLANNER_SYSTEM_PROMPT
    from novel_factory.agents.screenwriter import SCREENWRITER_SYSTEM_PROMPT

    assert "单章概念预算" in PLANNER_SYSTEM_PROMPT
    assert "1 个核心新概念" in PLANNER_SYSTEM_PROMPT
    assert "单章概念预算" in SCREENWRITER_SYSTEM_PROMPT
    assert "scene beat 必须围绕同一个核心新概念" in SCREENWRITER_SYSTEM_PROMPT
