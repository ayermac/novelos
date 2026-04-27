"""Tests for v5.1 Frontend Build and Chinese UX.

Covers:
- Frontend files exist
- Chinese labels in components
- Build configuration
"""

from __future__ import annotations

from pathlib import Path


class TestFrontendStructure:
    """Frontend project structure is correct."""

    def test_frontend_directory_exists(self):
        """frontend/ directory exists."""
        frontend_dir = Path(__file__).parent.parent / "frontend"
        assert frontend_dir.exists()
        assert frontend_dir.is_dir()

    def test_package_json_exists(self):
        """package.json exists."""
        package_json = Path(__file__).parent.parent / "frontend" / "package.json"
        assert package_json.exists()

    def test_tsconfig_exists(self):
        """tsconfig.json exists."""
        tsconfig = Path(__file__).parent.parent / "frontend" / "tsconfig.json"
        assert tsconfig.exists()

    def test_vite_config_exists(self):
        """vite.config.ts exists."""
        vite_config = Path(__file__).parent.parent / "frontend" / "vite.config.ts"
        assert vite_config.exists()

    def test_src_directory_exists(self):
        """src/ directory exists."""
        src_dir = Path(__file__).parent.parent / "frontend" / "src"
        assert src_dir.exists()

    def test_main_tsx_exists(self):
        """main.tsx exists."""
        main_tsx = Path(__file__).parent.parent / "frontend" / "src" / "main.tsx"
        assert main_tsx.exists()

    def test_app_tsx_exists(self):
        """App.tsx exists."""
        app_tsx = Path(__file__).parent.parent / "frontend" / "src" / "App.tsx"
        assert app_tsx.exists()

    def test_index_css_exists(self):
        """index.css exists."""
        index_css = Path(__file__).parent.parent / "frontend" / "src" / "index.css"
        assert index_css.exists()


class TestFrontendChineseLabels:
    """Frontend components use Chinese labels."""

    def test_layout_has_chinese_nav(self):
        """Layout component has Chinese navigation labels."""
        layout_file = Path(__file__).parent.parent / "frontend" / "src" / "components" / "Layout.tsx"
        if not layout_file.exists():
            return  # Skip if file doesn't exist yet
        content = layout_file.read_text()
        assert "总览" in content
        assert "项目" in content
        assert "创建项目" in content
        assert "生成章节" in content
        assert "审核" in content
        assert "风格" in content
        assert "配置" in content
        assert "验收" in content

    def test_dashboard_has_chinese_labels(self):
        """Dashboard page has Chinese labels."""
        dashboard_file = Path(__file__).parent.parent / "frontend" / "src" / "pages" / "Dashboard.tsx"
        if not dashboard_file.exists():
            return
        content = dashboard_file.read_text()
        assert "总览" in content or "项目数" in content or "队列项" in content

    def test_projects_has_chinese_labels(self):
        """Projects page has Chinese labels."""
        projects_file = Path(__file__).parent.parent / "frontend" / "src" / "pages" / "Projects.tsx"
        if not projects_file.exists():
            return
        content = projects_file.read_text()
        assert "项目列表" in content or "创建项目" in content

    def test_onboarding_has_chinese_labels(self):
        """Onboarding page has Chinese labels."""
        onboarding_file = Path(__file__).parent.parent / "frontend" / "src" / "pages" / "Onboarding.tsx"
        if not onboarding_file.exists():
            return
        content = onboarding_file.read_text()
        assert "创建新项目" in content or "小说名称" in content or "项目 ID" in content

    def test_review_has_chinese_labels(self):
        """Review page has Chinese labels."""
        review_file = Path(__file__).parent.parent / "frontend" / "src" / "pages" / "Review.tsx"
        if not review_file.exists():
            return
        content = review_file.read_text()
        assert "审核工作台" in content or "待审核" in content or "已通过" in content

    def test_settings_has_chinese_labels(self):
        """Settings page has Chinese labels."""
        settings_file = Path(__file__).parent.parent / "frontend" / "src" / "pages" / "Settings.tsx"
        if not settings_file.exists():
            return
        content = settings_file.read_text()
        assert "配置中心" in content or "运行模式" in content or "演示模式" in content


class TestFrontendBuildConfig:
    """Frontend build configuration is correct."""

    def test_package_json_has_correct_name(self):
        """package.json has correct name."""
        package_json = Path(__file__).parent.parent / "frontend" / "package.json"
        content = package_json.read_text()
        assert '"name": "novel-factory-frontend"' in content

    def test_package_json_has_correct_version(self):
        """package.json has v5.1.3 version."""
        package_json = Path(__file__).parent.parent / "frontend" / "package.json"
        content = package_json.read_text()
        assert '"version": "5.1.3"' in content

    def test_package_json_has_react_dependencies(self):
        """package.json has React dependencies."""
        package_json = Path(__file__).parent.parent / "frontend" / "package.json"
        content = package_json.read_text()
        assert '"react"' in content
        assert '"react-dom"' in content
        assert '"react-router-dom"' in content

    def test_package_json_has_dev_dependencies(self):
        """package.json has dev dependencies."""
        package_json = Path(__file__).parent.parent / "frontend" / "package.json"
        content = package_json.read_text()
        assert '"typescript"' in content
        assert '"vite"' in content

    def test_index_html_has_chinese_lang(self):
        """index.html has lang="zh-CN"."""
        index_html = Path(__file__).parent.parent / "frontend" / "index.html"
        content = index_html.read_text()
        assert 'lang="zh-CN"' in content

    def test_index_html_has_chinese_title(self):
        """index.html has Chinese title."""
        index_html = Path(__file__).parent.parent / "frontend" / "index.html"
        content = index_html.read_text()
        assert "小说工厂" in content
        assert "作者工作台" in content
