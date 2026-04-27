"""v5.1 Frontend Quality Checks.

Tests for frontend code quality:
- All pages import API client or are static
- No English-dominated navigation
- No href="#" links
- No undefined/null/[object Object] visible fallbacks
- No hardcoded localhost
- API client handles envelope correctly
"""

from __future__ import annotations

from pathlib import Path


def test_all_pages_import_api_or_static():
    """Test all 10 pages import API client or are static."""
    frontend_src = Path(__file__).parent.parent / "frontend" / "src"
    pages_dir = frontend_src / "pages"

    assert pages_dir.exists(), "pages directory should exist"

    page_files = list(pages_dir.glob("*.tsx"))
    assert len(page_files) == 9, f"Should have 9 page files (Acceptance removed in v5.1.6), found {len(page_files)}"

    # Check each page
    for page_file in page_files:
        content = page_file.read_text()

        # Should import from lib/api or be static (no API calls)
        has_api_import = "from '../lib/api'" in content
        has_fetch = "fetch(" in content
        is_static = not has_fetch

        assert has_api_import or is_static, (
            f"{page_file.name} should import from lib/api or be static"
        )


def test_no_english_navigation():
    """Test navigation is in Chinese."""
    frontend_src = Path(__file__).parent.parent / "frontend" / "src"
    layout_file = frontend_src / "components" / "Layout.tsx"

    assert layout_file.exists(), "Layout.tsx should exist"

    content = layout_file.read_text()

    # Navigation labels should be Chinese (v5.1.6: "总览" renamed to "创作中心")
    chinese_labels = [
        "创作中心",
        "项目",
        "创建项目",
        "高级运行",
        "审核",
        "风格",
        "配置",
    ]

    for label in chinese_labels:
        assert label in content, f"Navigation should include '{label}'"


def test_no_href_hash():
    """Test no href='#' in frontend code."""
    frontend_src = Path(__file__).parent.parent / "frontend" / "src"

    for tsx_file in frontend_src.rglob("*.tsx"):
        content = tsx_file.read_text()
        assert 'href="#"' not in content, f"{tsx_file.name} should not have href='#'"


def test_no_hardcoded_localhost():
    """Test no hardcoded localhost in frontend code."""
    frontend_src = Path(__file__).parent.parent / "frontend" / "src"

    for tsx_file in frontend_src.rglob("*.tsx"):
        content = tsx_file.read_text()
        # Allow localhost in comments
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "//" in line:
                # Skip comment lines
                continue
            assert "localhost:" not in line, (
                f"{tsx_file.name}:{i+1} should not have hardcoded localhost"
            )


def test_api_client_envelope_handling():
    """Test API client handles envelope correctly."""
    frontend_src = Path(__file__).parent.parent / "frontend" / "src"
    api_file = frontend_src / "lib" / "api.ts"

    assert api_file.exists(), "lib/api.ts should exist"

    content = api_file.read_text()

    # Should define EnvelopeResponse interface
    assert "interface EnvelopeResponse" in content or "type EnvelopeResponse" in content

    # Should handle ok/error/data
    assert "ok" in content
    assert "error" in content
    assert "data" in content

    # Should use /api base
    assert "API_BASE" in content or '"/api"' in content


def test_no_visible_undefined_null():
    """Test no visible undefined/null/[object Object] fallbacks."""
    frontend_src = Path(__file__).parent.parent / "frontend" / "src"

    # Patterns that indicate bad fallback
    bad_patterns = [
        ">{undefined}<",
        ">{null}<",
        ">[object Object]<",
        ">undefined<",
        ">null<",
    ]

    for tsx_file in frontend_src.rglob("*.tsx"):
        content = tsx_file.read_text()
        for pattern in bad_patterns:
            assert pattern not in content, (
                f"{tsx_file.name} should not have visible '{pattern}'"
            )


def test_pages_have_error_states():
    """Test pages have error/loading states."""
    frontend_src = Path(__file__).parent.parent / "frontend" / "src"
    pages_dir = frontend_src / "pages"

    # Pages that should have error states (not static)
    dynamic_pages = [
        "Dashboard.tsx",
        "Projects.tsx",
        "ProjectDetail.tsx",
        "Run.tsx",
        "Review.tsx",
        "Style.tsx",
        "Settings.tsx",
        "Acceptance.tsx",
    ]

    for page_name in dynamic_pages:
        page_file = pages_dir / page_name
        if not page_file.exists():
            continue

        content = page_file.read_text()

        # Should have loading or error handling
        has_loading = "loading" in content.lower() or "加载" in content
        has_error = "error" in content.lower() or "失败" in content

        assert has_loading or has_error, (
            f"{page_name} should have loading or error state"
        )


def test_pages_have_chinese_titles():
    """Test pages have Chinese titles."""
    frontend_src = Path(__file__).parent.parent / "frontend" / "src"
    pages_dir = frontend_src / "pages"

    # Check a few key pages
    key_pages = {
        "Dashboard.tsx": "创作中心",
        "Projects.tsx": "项目",
        "Onboarding.tsx": "创建",
        "Run.tsx": "生成",
        "Review.tsx": "审核",
    }

    for page_name, expected_text in key_pages.items():
        page_file = pages_dir / page_name
        if not page_file.exists():
            continue

        content = page_file.read_text()
        assert expected_text in content, (
            f"{page_name} should contain Chinese text '{expected_text}'"
        )
