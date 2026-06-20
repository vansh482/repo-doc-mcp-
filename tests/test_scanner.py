"""
Tests for the Repository Scanner.

These tests validate that the scanner correctly:
- Detects programming languages from file extensions
- Categorizes files into the right types
- Respects ignore patterns
- Reads and structures file content properly
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.config.settings import RepoConfig
from src.core.models import FileType
from src.parsers.scanner import (
    RepoScanner,
    detect_file_type,
    detect_language,
)


# ──────────────────────────────────────────────────────────────────────
# Language Detection Tests
# ──────────────────────────────────────────────────────────────────────

class TestDetectLanguage:
    """Tests for the detect_language function."""

    def test_common_extensions(self):
        assert detect_language("main.py") == "python"
        assert detect_language("app.ts") == "typescript"
        assert detect_language("index.js") == "javascript"
        assert detect_language("Main.java") == "java"
        assert detect_language("server.go") == "go"
        assert detect_language("lib.rs") == "rust"

    def test_nested_paths(self):
        assert detect_language("src/core/models.py") == "python"
        assert detect_language("packages/api/src/index.ts") == "typescript"

    def test_special_filenames(self):
        assert detect_language("Makefile") == "makefile"
        assert detect_language("Dockerfile") == "dockerfile"
        assert detect_language("Jenkinsfile") == "groovy"

    def test_config_files(self):
        assert detect_language("config.yaml") == "yaml"
        assert detect_language("settings.json") == "json"
        assert detect_language("pyproject.toml") == "toml"

    def test_unknown_extension(self):
        assert detect_language("file.xyz") is None
        assert detect_language("binary.bin") is None


# ──────────────────────────────────────────────────────────────────────
# File Type Detection Tests
# ──────────────────────────────────────────────────────────────────────

class TestDetectFileType:
    """Tests for the detect_file_type function."""

    def test_source_code(self):
        assert detect_file_type("main.py") == FileType.SOURCE_CODE
        assert detect_file_type("app.ts") == FileType.SOURCE_CODE
        assert detect_file_type("server.go") == FileType.SOURCE_CODE

    def test_config_files(self):
        assert detect_file_type("config.yaml") == FileType.CONFIG
        assert detect_file_type("settings.json") == FileType.CONFIG
        assert detect_file_type("app.toml") == FileType.CONFIG

    def test_documentation(self):
        assert detect_file_type("README.md") == FileType.DOCUMENTATION
        assert detect_file_type("docs/guide.rst") == FileType.DOCUMENTATION

    def test_test_files(self):
        assert detect_file_type("test_main.py") == FileType.TEST
        assert detect_file_type("app.test.ts") == FileType.TEST
        assert detect_file_type("LoginSpec.java") == FileType.TEST

    def test_build_files(self):
        assert detect_file_type("Dockerfile") == FileType.BUILD
        assert detect_file_type("Makefile") == FileType.BUILD


# ──────────────────────────────────────────────────────────────────────
# Scanner Integration Tests
# ──────────────────────────────────────────────────────────────────────

class TestRepoScanner:
    """Integration tests using a temporary directory as a fake repo."""

    def _create_test_repo(self, tmp_path: Path) -> Path:
        """Create a small fake repository for testing."""
        # Create directory structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "core").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg").mkdir()

        # Create source files
        (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')\n")
        (tmp_path / "src" / "core" / "models.py").write_text("class User:\n    pass\n")
        (tmp_path / "src" / "utils.ts").write_text("export function helper() {}\n")

        # Create config file
        (tmp_path / "config.yaml").write_text("key: value\n")

        # Create test file
        (tmp_path / "tests" / "test_main.py").write_text("def test_main():\n    assert True\n")

        # Create README
        (tmp_path / "README.md").write_text("# Test Project\n")

        # Create a file in node_modules (should be ignored)
        (tmp_path / "node_modules" / "pkg" / "index.js").write_text("module.exports = {}\n")

        return tmp_path

    def test_scan_finds_files(self, tmp_path: Path):
        repo = self._create_test_repo(tmp_path)
        scanner = RepoScanner()
        result = scanner.scan(str(repo))

        # Should find source files but NOT node_modules
        paths = {f.path for f in result.files}
        assert "src/main.py" in paths
        assert "src/core/models.py" in paths
        assert "README.md" in paths
        # node_modules should be ignored
        assert not any("node_modules" in p for p in paths)

    def test_scan_detects_languages(self, tmp_path: Path):
        repo = self._create_test_repo(tmp_path)
        scanner = RepoScanner()
        result = scanner.scan(str(repo))

        # Check languages are detected
        languages = result.languages
        assert "python" in languages
        assert "typescript" in languages

    def test_scan_categorizes_files(self, tmp_path: Path):
        repo = self._create_test_repo(tmp_path)
        scanner = RepoScanner()
        result = scanner.scan(str(repo))

        file_types = {f.path: f.file_type for f in result.files}
        assert file_types.get("src/main.py") == FileType.SOURCE_CODE
        assert file_types.get("config.yaml") == FileType.CONFIG
        assert file_types.get("README.md") == FileType.DOCUMENTATION
        assert file_types.get("tests/test_main.py") == FileType.TEST

    def test_scan_reads_content(self, tmp_path: Path):
        repo = self._create_test_repo(tmp_path)
        scanner = RepoScanner()
        result = scanner.scan(str(repo))

        main_file = next(f for f in result.files if f.path == "src/main.py")
        assert "def main():" in main_file.content

    def test_scan_respects_max_files(self, tmp_path: Path):
        repo = self._create_test_repo(tmp_path)
        config = RepoConfig(max_files=2)
        scanner = RepoScanner(config)
        result = scanner.scan(str(repo))

        assert len(result.files) <= 2

    def test_scan_nonexistent_path_raises(self):
        scanner = RepoScanner()
        with pytest.raises(ValueError, match="does not exist"):
            scanner.scan("/nonexistent/path/xyz123")

    def test_repo_tree_properties(self, tmp_path: Path):
        repo = self._create_test_repo(tmp_path)
        scanner = RepoScanner()
        result = scanner.scan(str(repo))

        assert result.total_files > 0
        assert result.total_lines > 0
        assert result.name == tmp_path.name
