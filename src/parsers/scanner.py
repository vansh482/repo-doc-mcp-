"""
Repository Scanner — reads a repo's file tree and produces a RepoTree.

This module is the very first step in the pipeline. Given a repo path, it:
1. Walks the directory tree, respecting ignore patterns (like .gitignore)
2. Reads file contents (text files only)
3. Detects the programming language of each file
4. Categorizes files (source code, config, test, docs, etc.)
5. Extracts git metadata (branch, commit hash)

The result is a RepoTree object — a structured snapshot of the entire repository.

Design decisions:
- We use fnmatch for pattern matching (same as .gitignore) for familiarity
- Binary files are detected and skipped (we can't meaningfully document them)
- Large files are read but flagged — the LLM layer decides how to handle them
- Git operations use subprocess for simplicity (no GitPython dependency here)
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path
from typing import Optional

from src.config.settings import RepoConfig
from src.core.models import FileType, RepoFile, RepoTree


# ──────────────────────────────────────────────────────────────────────
# Language Detection — maps file extensions to language names
# ──────────────────────────────────────────────────────────────────────

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    # Web
    "js": "javascript", "jsx": "javascript", "ts": "typescript", "tsx": "typescript",
    "html": "html", "htm": "html", "css": "css", "scss": "scss", "less": "less",
    "vue": "vue", "svelte": "svelte",
    # Backend
    "py": "python", "rb": "ruby", "go": "go", "rs": "rust",
    "java": "java", "kt": "kotlin", "kts": "kotlin",
    "scala": "scala", "clj": "clojure",
    "cs": "csharp", "fs": "fsharp", "vb": "vb.net",
    "php": "php", "swift": "swift", "m": "objective-c",
    # Systems
    "c": "c", "h": "c", "cpp": "cpp", "hpp": "cpp", "cc": "cpp",
    "zig": "zig", "nim": "nim", "hs": "haskell", "erl": "erlang", "ex": "elixir",
    # Scripting / Data
    "sh": "bash", "bash": "bash", "zsh": "zsh", "fish": "fish",
    "pl": "perl", "lua": "lua", "r": "r", "jl": "julia",
    "sql": "sql",
    # Config
    "json": "json", "yaml": "yaml", "yml": "yaml", "toml": "toml",
    "xml": "xml", "ini": "ini", "cfg": "ini",
    # Docs
    "md": "markdown", "rst": "restructuredtext", "tex": "latex", "txt": "text",
    # Build / Infra
    "dockerfile": "dockerfile", "tf": "terraform", "hcl": "terraform",
    "gradle": "gradle", "cmake": "cmake",
    # Misc
    "proto": "protobuf", "graphql": "graphql", "gql": "graphql",
}

# Files without extensions that we can still identify by their name
FILENAME_TO_LANGUAGE: dict[str, str] = {
    "Makefile": "makefile", "Dockerfile": "dockerfile", "Jenkinsfile": "groovy",
    "Vagrantfile": "ruby", "Rakefile": "ruby", "Gemfile": "ruby",
    "Procfile": "procfile", "Brewfile": "ruby",
    ".gitignore": "gitignore", ".dockerignore": "dockerignore",
    ".env": "dotenv", ".env.example": "dotenv",
    "CMakeLists.txt": "cmake",
}


# ──────────────────────────────────────────────────────────────────────
# File Type Detection — categorizes files for documentation strategy
# ──────────────────────────────────────────────────────────────────────

# Patterns that indicate a file is a test file
TEST_PATTERNS = [
    "test_*", "*_test.*", "*.test.*", "*.spec.*",
    "tests/*", "test/*", "__tests__/*", "spec/*",
    "*Test.*", "*Spec.*",
]

# Extensions that are configuration files
CONFIG_EXTENSIONS = {
    "json", "yaml", "yml", "toml", "ini", "cfg", "xml",
    "env", "properties", "conf",
}

# Extensions that are documentation files
DOC_EXTENSIONS = {"md", "rst", "txt", "adoc", "tex"}

# Filenames that are build/infra files
BUILD_FILENAMES = {
    "Makefile", "Dockerfile", "Jenkinsfile", "Vagrantfile",
    "docker-compose.yml", "docker-compose.yaml",
    ".github", "Procfile", "Brewfile",
    "webpack.config.js", "vite.config.ts", "rollup.config.js",
    "tsconfig.json", "babel.config.js", ".eslintrc.js",
    "setup.py", "setup.cfg", "pyproject.toml",
}

DATA_EXTENSIONS = {"csv", "tsv", "parquet", "avro", "json"}


def detect_language(filepath: str) -> Optional[str]:
    """Detect programming language from file extension or name."""
    name = Path(filepath).name
    ext = Path(filepath).suffix.lstrip(".")

    # Check exact filename matches first (Makefile, Dockerfile, etc.)
    if name in FILENAME_TO_LANGUAGE:
        return FILENAME_TO_LANGUAGE[name]

    # Then check extension
    return EXTENSION_TO_LANGUAGE.get(ext.lower())


def detect_file_type(filepath: str) -> FileType:
    """Categorize a file based on its path, name, and extension.

    The order of checks matters — test files in a 'tests/' directory
    should be categorized as TEST, not SOURCE_CODE, even if they're .py files.
    """
    path = Path(filepath)
    name = path.name
    ext = path.suffix.lstrip(".").lower()
    path_str = str(filepath)

    # Check if it's a test file (check this BEFORE source code)
    for pattern in TEST_PATTERNS:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(path_str, pattern):
            return FileType.TEST

    # Check for build/infra files
    if name in BUILD_FILENAMES:
        return FileType.BUILD

    # Documentation files
    if ext in DOC_EXTENSIONS:
        return FileType.DOCUMENTATION

    # Config files
    if ext in CONFIG_EXTENSIONS:
        return FileType.CONFIG

    # Data files
    if ext in DATA_EXTENSIONS:
        return FileType.DATA

    # If it has a recognized programming language, it's source code
    if detect_language(filepath):
        return FileType.SOURCE_CODE

    return FileType.OTHER


# ──────────────────────────────────────────────────────────────────────
# The Scanner — orchestrates the repo reading process
# ──────────────────────────────────────────────────────────────────────

class RepoScanner:
    """Scans a repository directory and produces a RepoTree.

    Usage:
        scanner = RepoScanner(config)
        repo_tree = scanner.scan("/path/to/repo")

    The scanner is intentionally synchronous — file I/O on local disk is fast
    enough that async would add complexity without meaningful benefit.
    """

    def __init__(self, config: RepoConfig | None = None):
        self.config = config or RepoConfig()

    def scan(self, repo_path: str) -> RepoTree:
        """Scan the repository and return a structured RepoTree.

        This is the main entry point. It:
        1. Resolves the repo path and extracts git info
        2. Walks the file tree, filtering by ignore patterns
        3. Reads each file's content
        4. Returns a RepoTree with all files categorized
        """
        root = Path(repo_path).resolve()
        if not root.is_dir():
            raise ValueError(f"Repository path does not exist or is not a directory: {root}")

        # Extract git metadata (best effort — works even without git)
        branch = self._get_git_branch(root)
        commit = self._get_git_commit(root)
        repo_name = root.name

        # Walk and collect files
        files: list[RepoFile] = []
        file_count = 0

        for file_path in self._walk_repo(root):
            if file_count >= self.config.max_files:
                break

            repo_file = self._read_file(root, file_path)
            if repo_file is not None:
                files.append(repo_file)
                file_count += 1

        return RepoTree(
            name=repo_name,
            root_path=str(root),
            branch=branch,
            commit_hash=commit,
            files=files,
        )

    def _walk_repo(self, root: Path):
        """Walk the repository, yielding file paths that pass our filters.

        This is where ignore patterns are applied. We check directories too,
        so we can skip entire subtrees (like node_modules) efficiently.
        """
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = os.path.relpath(dirpath, root)

            # Filter out ignored directories IN PLACE — this tells os.walk to skip them
            # This is the efficient way to prune the walk (modifying dirnames in-place)
            dirnames[:] = [
                d for d in dirnames
                if not self._should_ignore(d, is_dir=True)
            ]

            for filename in filenames:
                if not self._should_ignore(filename, is_dir=False):
                    full_path = Path(dirpath) / filename
                    yield full_path

    def _should_ignore(self, name: str, is_dir: bool = False) -> bool:
        """Check if a file or directory should be ignored based on config patterns.

        We match against both the name itself and the configured patterns.
        Hidden files/directories (starting with .) are also ignored by default.
        """
        # Always ignore hidden files/dirs (except .env.example-like files)
        if name.startswith(".") and name not in {".env.example", ".env.sample"}:
            return True

        for pattern in self.config.ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True

        return False

    def _read_file(self, root: Path, file_path: Path) -> Optional[RepoFile]:
        """Read a single file and create a RepoFile model.

        Returns None if:
        - The file is binary (we detect this by trying UTF-8 decode)
        - The file exceeds size limits
        - The file can't be read for any reason
        """
        try:
            size = file_path.stat().st_size

            # Skip files that are too large
            if size > self.config.max_file_size_kb * 1024:
                # Still include the file but with a truncation notice
                content = self._read_truncated(file_path)
            else:
                content = file_path.read_text(encoding="utf-8", errors="strict")

        except UnicodeDecodeError:
            # Binary file — skip it
            return None
        except (OSError, PermissionError):
            return None

        rel_path = str(file_path.relative_to(root))
        ext = file_path.suffix.lstrip(".")

        # Apply extension filter if configured
        if self.config.include_extensions and ext.lower() not in {
            e.lower().lstrip(".") for e in self.config.include_extensions
        }:
            return None

        return RepoFile(
            path=rel_path,
            absolute_path=str(file_path),
            content=content,
            extension=ext,
            size_bytes=size,
            file_type=detect_file_type(rel_path),
            language=detect_language(rel_path),
        )

    def _read_truncated(self, file_path: Path) -> str:
        """Read a large file but truncate it, adding a notice.

        For very large files, we read the first chunk (to understand the file)
        and append a note explaining the truncation.
        """
        max_bytes = self.config.max_file_size_kb * 1024
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_bytes)
            return content + f"\n\n# ... [FILE TRUNCATED — original size exceeds {self.config.max_file_size_kb}KB] ..."
        except Exception:
            return "# [Could not read file]"

    def _get_git_branch(self, root: Path) -> Optional[str]:
        """Get the current git branch name (returns None if not a git repo)."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=root, capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def _get_git_commit(self, root: Path) -> Optional[str]:
        """Get the current HEAD commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root, capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None
