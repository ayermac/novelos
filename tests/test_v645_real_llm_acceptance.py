"""v6.4.5 real LLM quality acceptance harness tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys


def _run_script(args: list[str], env: dict[str, str] | None = None) -> dict:
    result = subprocess.run(
        [sys.executable, "scripts/verify_v64_real_llm.py", *args],
        cwd=os.getcwd(),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return json.loads(result.stdout[result.stdout.index("{"):])


def test_real_mode_skips_cleanly_without_api_key(tmp_path):
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY"}
    }
    report_path = tmp_path / "real-skip.json"

    data = _run_script(["--mode", "real", "--output", str(report_path)], env=env)

    assert data["status"] == "skipped"
    assert data["mode"] == "real"
    assert data["version"] == "v6.4.5"
    assert "API key" in data["reason"]
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "skipped"


def test_stub_mode_runs_acceptance_harness(tmp_path):
    report_path = tmp_path / "stub-report.json"

    data = _run_script(["--mode", "stub", "--output", str(report_path)])

    assert data["status"] == "passed"
    assert data["mode"] == "stub"
    assert data["chapter"]["has_content"] is True
    assert data["diagnosis"]["overall_score"] >= 0
    assert "dimensions" in data["diagnosis"]
    assert "death_penalty" in data["diagnosis"]["dimensions"]
    assert "info_dump" in data["diagnosis"]["dimensions"]
    assert data["acceptance"]["checks"]["death_penalty_clean"] is True
