"""
Git Diff Engine — detects changes between two git states.

This module is the foundation of the incremental update system. Instead of
re-analyzing the entire repository every time main branch changes, we ask git
"what exactly changed since the last time we generated docs?" and only re-process
those files.

HOW IT WORKS:

    Last documented state          Current state
    (stored commit hash)           (latest commit on main)
           │                              │
           └──────── git diff ────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │   ChangedFiles  │
              │  - added files  │
              │  - modified     │
              │  - deleted      │
              │  - renamed      │
              └─────────────────┘
                        │
                        ▼
              Only re-analyze these files,
              then merge into existing docs

The key insight: if 500 files exist but only 3 changed, we run LLM analysis
on just those 3 files and surgically update the docs. This saves both time
and money (LLM API costs).

We also support detecting the SCOPE of changes — did the change affect the
architecture (new module added)? Or just a bug fix in an existing function?
This determines whether we need a full doc regen or a targeted update.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ChangeType(str, Enum):
    """Types of changes a file can undergo between two commits."""
    ADDED = "added"           # New file that didn't exist before
    MODIFIED = "modified"     # Existing file with content changes
    DELETED = "deleted"       # File was removed
    RENAMED = "renamed"       # File was moved/renamed (possibly with changes)


class ChangeScope(str, Enum):
    """How significant is this set of changes for documentation purposes?

    STRUCTURAL changes mean the architecture might have changed — new modules,
    deleted components, renamed entry points. These require a broader doc update.

    CONTENT changes mean existing files were modified but the overall structure
    is the same. These only require updating the affected file summaries and
    possibly some cross-references.

    COSMETIC changes are things like formatting, comments, or config tweaks
    that probably don't need doc updates at all.
    """
    STRUCTURAL = "structural"   # New/deleted modules, renamed components
    CONTENT = "content"         # Modified logic within existing files
    COSMETIC = "cosmetic"       # Formatting, comments, minor config changes


@dataclass
class FileChange:
    """Represents a single file that changed between two git states."""
    path: str                                # Relative path from repo root
    change_type: ChangeType                  # Added, modified, deleted, renamed
    old_path: Optional[str] = None           # For renames: the previous path
    diff_stats: Optional[DiffStats] = None   # Lines added/removed
    diff_content: Optional[str] = None       # The actual diff (for context)


@dataclass
class DiffStats:
    """Statistics about a file's changes — how many lines were added/removed."""
    lines_added: int = 0
    lines_removed: int = 0

    @property
    def total_changes(self) -> int:
        return self.lines_added + self.lines_removed

    @property
    def is_minor(self) -> bool:
        """A change of fewer than 5 lines is usually cosmetic or a small fix."""
        return self.total_changes < 5


@dataclass
class DiffResult:
    """Complete diff result between two git states.

    This is what the watcher uses to decide what needs re-documenting.
    It contains not just the list of changed files, but also a classification
    of how impactful the changes are (the 'scope').
    """
    from_commit: str                              # The commit we documented last
    to_commit: str                                # The current commit
    changes: list[FileChange] = field(default_factory=list)
    scope: ChangeScope = ChangeScope.COSMETIC     # Overall change significance
    commit_messages: list[str] = field(default_factory=list)  # Commit messages in range

    @property
    def total_files_changed(self) -> int:
        return len(self.changes)

    @property
    def added_files(self) -> list[FileChange]:
        return [c for c in self.changes if c.change_type == ChangeType.ADDED]

    @property
    def modified_files(self) -> list[FileChange]:
        return [c for c in self.changes if c.change_type == ChangeType.MODIFIED]

    @property
    def deleted_files(self) -> list[FileChange]:
        return [c for c in self.changes if c.change_type == ChangeType.DELETED]

    @property
    def renamed_files(self) -> list[FileChange]:
        return [c for c in self.changes if c.change_type == ChangeType.RENAMED]

    @property
    def has_changes(self) -> bool:
        return len(self.changes) > 0

    def summary(self) -> str:
        """Human-readable summary of the changes."""
        parts = [f"Changes from {self.from_commit[:8]} → {self.to_commit[:8]}:"]
        if self.added_files:
            parts.append(f"  + {len(self.added_files)} files added")
        if self.modified_files:
            parts.append(f"  ~ {len(self.modified_files)} files modified")
        if self.deleted_files:
            parts.append(f"  - {len(self.deleted_files)} files deleted")
        if self.renamed_files:
            parts.append(f"  → {len(self.renamed_files)} files renamed")
        parts.append(f"  Scope: {self.scope.value}")
        return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────
# Patterns for classifying change significance
# ──────────────────────────────────────────────────────────────────────

# Files/paths that indicate STRUCTURAL changes when added or deleted
STRUCTURAL_PATTERNS = {
    # New modules/packages
    "__init__.py",
    # Entry points
    "main.py", "app.py", "index.ts", "index.js", "server.py",
    "manage.py", "wsgi.py", "asgi.py",
    # Build/deploy config changes
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Makefile", "CMakeLists.txt",
    # Package definitions
    "pyproject.toml", "setup.py", "package.json", "Cargo.toml",
    "go.mod", "pom.xml", "build.gradle",
}

# Directories that indicate structural changes when they appear/disappear
STRUCTURAL_DIRS = {
    "src", "lib", "pkg", "cmd", "internal", "api",
    "services", "models", "controllers", "routes",
    "components", "modules", "core",
}

# File patterns that are cosmetic / non-doc-worthy
COSMETIC_PATTERNS = {
    ".gitignore", ".editorconfig", ".prettierrc",
    ".eslintrc", ".flake8", "mypy.ini",
    "LICENSE", "CHANGELOG.md",
}


class GitDiffEngine:
    """Computes the diff between two git states and classifies the changes.

    Usage:
        engine = GitDiffEngine(repo_path="/path/to/repo")

        # Diff between two commits
        result = engine.diff("abc1234", "def5678")

        # Diff between last documented state and current HEAD
        result = engine.diff_from_last(last_commit="abc1234")

        # Get the current branch's HEAD commit
        head = engine.get_head_commit()

        # Get the main/mainline branch name
        main_branch = engine.detect_main_branch()
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {self.repo_path}")

    def diff(self, from_commit: str, to_commit: str) -> DiffResult:
        """Compute the full diff between two commits.

        This is the main method. It:
        1. Runs git diff to find changed files
        2. Parses the diff output into FileChange objects
        3. Collects commit messages in the range
        4. Classifies the overall scope of changes

        Returns a DiffResult with all the information needed for
        incremental doc updates.
        """
        changes = self._get_changed_files(from_commit, to_commit)
        commit_messages = self._get_commit_messages(from_commit, to_commit)
        scope = self._classify_scope(changes)

        return DiffResult(
            from_commit=from_commit,
            to_commit=to_commit,
            changes=changes,
            scope=scope,
            commit_messages=commit_messages,
        )

    def diff_from_last(self, last_commit: str) -> DiffResult:
        """Diff from a previous commit to the current HEAD.

        This is the convenience method used during auto-updates:
        "what changed since we last generated docs?"
        """
        head = self.get_head_commit()
        if not head:
            raise RuntimeError("Could not determine HEAD commit")

        if last_commit == head:
            return DiffResult(
                from_commit=last_commit,
                to_commit=head,
                scope=ChangeScope.COSMETIC,
            )

        return self.diff(last_commit, head)

    def get_head_commit(self, branch: str | None = None) -> Optional[str]:
        """Get the HEAD commit hash, optionally for a specific branch."""
        ref = branch or "HEAD"
        result = self._run_git(["rev-parse", ref])
        return result.strip() if result else None

    def detect_main_branch(self) -> str:
        """Detect the main/mainline branch name.

        Different repos use different conventions:
        - "main" (modern default)
        - "master" (legacy default)
        - "mainline" (some enterprises)
        - "develop" / "dev" (some workflows)

        We check which of these actually exist as remote branches
        and return the first match.
        """
        candidates = ["main", "master", "mainline", "develop"]

        # Check remote branches first
        remote_branches = self._run_git(
            ["branch", "-r", "--list"]
        )
        if remote_branches:
            for candidate in candidates:
                if f"origin/{candidate}" in remote_branches:
                    return candidate

        # Fall back to local branches
        local_branches = self._run_git(["branch", "--list"])
        if local_branches:
            for candidate in candidates:
                if candidate in local_branches:
                    return candidate

        # Last resort: just use HEAD
        return "HEAD"

    def get_latest_main_commit(self) -> Optional[str]:
        """Get the latest commit hash on the main branch.

        First tries to fetch from remote (to get the absolute latest),
        then falls back to the local tracking branch.
        """
        main_branch = self.detect_main_branch()

        # Try to get the remote version first (might be ahead of local)
        remote_commit = self.get_head_commit(f"origin/{main_branch}")
        if remote_commit:
            return remote_commit

        # Fall back to local
        return self.get_head_commit(main_branch)

    # ──────────────────────────────────────────────────────────────────
    # Private helpers — git command execution and output parsing
    # ──────────────────────────────────────────────────────────────────

    def _get_changed_files(
        self, from_commit: str, to_commit: str,
    ) -> list[FileChange]:
        """Run git diff and parse the output into FileChange objects.

        We use --name-status for the file list (shows A/M/D/R status)
        and --numstat for line counts (lines added/removed per file).
        """
        # Get file changes with their status (Added/Modified/Deleted/Renamed)
        name_status = self._run_git([
            "diff", "--name-status", "--find-renames", from_commit, to_commit,
        ])

        # Get line-level stats
        numstat = self._run_git([
            "diff", "--numstat", from_commit, to_commit,
        ])

        if not name_status:
            return []

        # Parse numstat into a dict: {filepath: DiffStats}
        stats_map: dict[str, DiffStats] = {}
        if numstat:
            for line in numstat.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 3:
                    added = int(parts[0]) if parts[0] != "-" else 0
                    removed = int(parts[1]) if parts[1] != "-" else 0
                    filepath = parts[2]
                    stats_map[filepath] = DiffStats(
                        lines_added=added,
                        lines_removed=removed,
                    )

        # Parse name-status into FileChange objects
        changes: list[FileChange] = []
        for line in name_status.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue

            status = parts[0]
            filepath = parts[1] if len(parts) >= 2 else ""

            if status == "A":
                changes.append(FileChange(
                    path=filepath,
                    change_type=ChangeType.ADDED,
                    diff_stats=stats_map.get(filepath),
                ))
            elif status == "M":
                changes.append(FileChange(
                    path=filepath,
                    change_type=ChangeType.MODIFIED,
                    diff_stats=stats_map.get(filepath),
                ))
            elif status == "D":
                changes.append(FileChange(
                    path=filepath,
                    change_type=ChangeType.DELETED,
                    diff_stats=stats_map.get(filepath),
                ))
            elif status.startswith("R"):
                # Rename: status is like "R095" (95% similarity)
                old_path = filepath
                new_path = parts[2] if len(parts) >= 3 else filepath
                changes.append(FileChange(
                    path=new_path,
                    change_type=ChangeType.RENAMED,
                    old_path=old_path,
                    diff_stats=stats_map.get(new_path),
                ))

        return changes

    def _get_commit_messages(
        self, from_commit: str, to_commit: str,
    ) -> list[str]:
        """Get all commit messages between two commits.

        These messages are useful for generating a changelog-style
        summary of what changed and why.
        """
        output = self._run_git([
            "log", "--oneline", "--no-merges",
            f"{from_commit}..{to_commit}",
        ])
        if not output:
            return []
        return [line.strip() for line in output.strip().splitlines()]

    def _classify_scope(self, changes: list[FileChange]) -> ChangeScope:
        """Classify the overall significance of a set of changes.

        The rules are (checked in order, first match wins):

        1. STRUCTURAL if:
           - Any new __init__.py (new Python package)
           - Any new/deleted entry point file (main.py, index.ts, etc.)
           - Any new/deleted directory that looks like a module
           - Any change to package definitions (pyproject.toml, package.json)
           - More than 10 files changed (probably a big feature)

        2. CONTENT if:
           - Source code files (.py, .ts, .js, etc.) were modified
           - More than 20 total lines changed

        3. COSMETIC if:
           - Only config/formatting/docs changed
           - Very few lines changed (< 5 per file)
        """
        if not changes:
            return ChangeScope.COSMETIC

        # Check for structural changes
        for change in changes:
            filename = Path(change.path).name
            parent_dir = Path(change.path).parent.name

            # New or deleted package/module indicators
            if change.change_type in {ChangeType.ADDED, ChangeType.DELETED}:
                if filename in STRUCTURAL_PATTERNS:
                    return ChangeScope.STRUCTURAL
                if parent_dir in STRUCTURAL_DIRS and filename == "__init__.py":
                    return ChangeScope.STRUCTURAL

            # Renamed structural files
            if change.change_type == ChangeType.RENAMED:
                if filename in STRUCTURAL_PATTERNS:
                    return ChangeScope.STRUCTURAL

        # Large number of files = probably structural
        if len(changes) > 10:
            return ChangeScope.STRUCTURAL

        # Check for content changes (meaningful code modifications)
        total_lines_changed = 0
        has_source_changes = False

        source_extensions = {
            "py", "ts", "js", "tsx", "jsx", "go", "rs", "java",
            "kt", "rb", "cs", "swift", "c", "cpp", "h",
        }

        for change in changes:
            ext = Path(change.path).suffix.lstrip(".")
            if ext in source_extensions:
                has_source_changes = True

            if change.diff_stats:
                total_lines_changed += change.diff_stats.total_changes

        if has_source_changes and total_lines_changed > 20:
            return ChangeScope.CONTENT

        if has_source_changes:
            return ChangeScope.CONTENT

        return ChangeScope.COSMETIC

    def _run_git(self, args: list[str]) -> Optional[str]:
        """Execute a git command and return its stdout.

        Returns None if the command fails (rather than raising),
        because many git queries are best-effort (e.g., checking
        for a remote branch that might not exist).
        """
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
