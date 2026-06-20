"""
MR Diff Analyzer — understands merge request changes at a semantic level.

While the git_diff engine from Phase 3 answers "what files changed?", this module
goes deeper and answers questions specific to merge requests:

    - What FEATURE areas were affected? (auth, payments, UI, etc.)
    - What is the NATURE of each change? (new feature, bug fix, refactor, etc.)
    - Are there BREAKING changes? (API signature changes, removed endpoints, etc.)
    - What is the RISK LEVEL? (low = docs change, high = core auth logic changed)
    - What TESTS were added or modified?
    - What CONFIGURATION changes might affect deployments?

HOW IT WORKS:
                                                          
    MR source branch ──── git diff ──── MR target branch  
                              │                            
                              ▼                            
                    ┌────────────────────┐                 
                    │   Raw DiffResult   │  (from Phase 3) 
                    └────────┬───────────┘                 
                             │                             
                    ┌────────▼───────────┐                 
                    │  MR Diff Analyzer  │  (this module)  
                    │  - groups changes  │                 
                    │  - detects intent  │                 
                    │  - assesses risk   │                 
                    └────────┬───────────┘                 
                             │                             
                    ┌────────▼───────────┐                 
                    │   MRAnalysis       │  (rich context) 
                    └────────────────────┘                 

The MRAnalysis object contains everything the doc generator needs to
write a meaningful MR document — not just a list of changed files, but
a narrative understanding of what the MR does and why it matters.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from src.watcher.git_diff import (
    ChangeType,
    DiffResult,
    FileChange,
    GitDiffEngine,
)


class ChangeNature(str, Enum):
    """What KIND of work does this MR represent?
    This is inferred from commit messages, file patterns, and the diff itself."""
    NEW_FEATURE = "new_feature"
    BUG_FIX = "bug_fix"
    REFACTOR = "refactor"
    PERFORMANCE = "performance"
    SECURITY = "security"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    DEPENDENCY_UPDATE = "dependency_update"
    CONFIGURATION = "configuration"
    INFRASTRUCTURE = "infrastructure"
    MIXED = "mixed"


class RiskLevel(str, Enum):
    """How risky is this MR from a deployment perspective?"""
    LOW = "low"           # Docs, tests, comments only
    MEDIUM = "medium"     # Non-critical source changes
    HIGH = "high"         # Core logic, auth, payments, DB migrations
    CRITICAL = "critical" # Breaking API changes, security-sensitive areas


@dataclass
class ChangeGroup:
    """A logical grouping of related changes within an MR.
    
    For example, an MR might touch both "authentication" and "user profile" areas.
    Each group gets its own section in the generated MR document, making it easier
    to understand what the MR does at a glance.
    """
    name: str                                          # e.g., "Authentication", "User API"
    description: str = ""                              # Brief explanation of this group
    files: list[FileChange] = field(default_factory=list)
    nature: ChangeNature = ChangeNature.MIXED


@dataclass
class MRAnalysis:
    """Complete analysis of a Merge Request — the rich context for doc generation.
    
    This is the 'input' to the MR doc generator. It contains everything needed
    to write a meaningful MR document: what changed, why, the risk level, 
    affected areas, test coverage, and the raw diff for technical details.
    """
    # MR metadata
    mr_title: str = ""
    mr_description: str = ""
    source_branch: str = ""
    target_branch: str = ""
    author: str = ""
    
    # The underlying diff
    diff: Optional[DiffResult] = None
    
    # Semantic analysis
    change_nature: ChangeNature = ChangeNature.MIXED
    risk_level: RiskLevel = RiskLevel.MEDIUM
    change_groups: list[ChangeGroup] = field(default_factory=list)
    
    # Detected properties
    has_breaking_changes: bool = False
    has_migration: bool = False
    has_new_dependencies: bool = False
    has_config_changes: bool = False
    has_test_changes: bool = False
    
    # Commit messages (the developer's own description of what they did)
    commit_messages: list[str] = field(default_factory=list)
    
    # File-level diffs (for including in the technical doc)
    file_diffs: dict[str, str] = field(default_factory=dict)  # {path: diff_content}
    
    @property
    def total_files_changed(self) -> int:
        return self.diff.total_files_changed if self.diff else 0
    
    @property
    def summary_line(self) -> str:
        """One-line summary for headers and notifications."""
        nature = self.change_nature.value.replace("_", " ").title()
        risk = self.risk_level.value.upper()
        return f"[{nature}] [{risk} Risk] {self.total_files_changed} files changed"


# ──────────────────────────────────────────────────────────────────────
# Feature Area Detection — maps file paths to logical feature areas
# ──────────────────────────────────────────────────────────────────────

# Common directory-to-feature-area mappings. These are heuristics —
# they work for most conventional project structures.
DIRECTORY_FEATURE_MAP: dict[str, str] = {
    "auth": "Authentication",
    "authentication": "Authentication",
    "login": "Authentication",
    "user": "User Management",
    "users": "User Management",
    "account": "User Management",
    "profile": "User Management",
    "api": "API Layer",
    "routes": "API Layer",
    "controllers": "API Layer",
    "endpoints": "API Layer",
    "handlers": "API Layer",
    "models": "Data Models",
    "schemas": "Data Models",
    "entities": "Data Models",
    "db": "Database",
    "database": "Database",
    "migrations": "Database Migrations",
    "payment": "Payments",
    "billing": "Payments",
    "stripe": "Payments",
    "ui": "User Interface",
    "components": "User Interface",
    "views": "User Interface",
    "pages": "User Interface",
    "templates": "User Interface",
    "frontend": "User Interface",
    "styles": "Styling",
    "css": "Styling",
    "config": "Configuration",
    "settings": "Configuration",
    "test": "Tests",
    "tests": "Tests",
    "spec": "Tests",
    "__tests__": "Tests",
    "utils": "Utilities",
    "helpers": "Utilities",
    "lib": "Core Library",
    "core": "Core Library",
    "services": "Business Logic",
    "middleware": "Middleware",
    "hooks": "Hooks & Plugins",
    "plugins": "Hooks & Plugins",
    "docs": "Documentation",
    "ci": "CI/CD",
    "deploy": "Infrastructure",
    "infra": "Infrastructure",
    "docker": "Infrastructure",
    "k8s": "Infrastructure",
    "kubernetes": "Infrastructure",
}

# Files that indicate breaking changes when modified
BREAKING_CHANGE_PATTERNS = [
    r"api/.*\.(py|ts|js|go|rs)$",       # API route definitions
    r"proto/.*\.proto$",                   # Protobuf definitions
    r"graphql/.*\.(graphql|gql)$",        # GraphQL schemas
    r".*schema.*\.(py|ts|sql)$",          # Database schemas
    r".*migration.*\.(py|sql)$",          # Database migrations
    r"openapi.*\.(yaml|yml|json)$",       # OpenAPI specs
]

# Files that indicate high risk when modified
HIGH_RISK_PATTERNS = [
    r"auth.*\.(py|ts|js|go|rs)$",
    r"security.*\.(py|ts|js|go|rs)$",
    r"crypto.*\.(py|ts|js|go|rs)$",
    r"payment.*\.(py|ts|js|go|rs)$",
    r"billing.*\.(py|ts|js|go|rs)$",
    r".*middleware.*\.(py|ts|js|go|rs)$",
]


class MRDiffAnalyzer:
    """Analyzes a merge request diff and produces a rich MRAnalysis.
    
    This is the main class for Phase 4's diff understanding. It takes a
    DiffResult (from Phase 3's git_diff engine) and enriches it with
    MR-specific semantic understanding.
    
    Usage:
        analyzer = MRDiffAnalyzer(repo_path)
        analysis = analyzer.analyze(
            source_branch="feature/add-oauth",
            target_branch="main",
            mr_title="Add OAuth2 authentication",
            mr_description="Implements OAuth2 login with Google and GitHub providers",
        )
    """
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.git = GitDiffEngine(str(self.repo_path))
    
    def analyze(
        self,
        source_branch: str,
        target_branch: str = "main",
        mr_title: str = "",
        mr_description: str = "",
        author: str = "",
    ) -> MRAnalysis:
        """Perform complete MR analysis.
        
        This is the main entry point. It runs the git diff, then layers
        on semantic understanding: grouping files by feature area, detecting
        the nature of changes, assessing risk, and extracting per-file diffs.
        """
        # Step 1: Get the base diff between branches
        source_commit = self.git.get_head_commit(source_branch)
        target_commit = self.git.get_head_commit(target_branch)
        
        if not source_commit or not target_commit:
            # Try with origin/ prefix for remote branches
            source_commit = source_commit or self.git.get_head_commit(f"origin/{source_branch}")
            target_commit = target_commit or self.git.get_head_commit(f"origin/{target_branch}")
        
        if not source_commit or not target_commit:
            raise ValueError(
                f"Could not resolve branches: {source_branch} → {target_branch}. "
                f"Make sure both branches exist."
            )
        
        # Get the merge base (where the branch diverged from target)
        merge_base = self._get_merge_base(target_commit, source_commit)
        
        # Diff from merge base to source branch tip (shows only the MR's changes)
        diff = self.git.diff(merge_base or target_commit, source_commit)
        
        # Step 2: Infer MR title from branch name if not provided
        if not mr_title:
            mr_title = self._title_from_branch(source_branch)
        
        # Step 3: Group files by feature area
        change_groups = self._group_by_feature(diff.changes)
        
        # Step 4: Detect the nature of changes
        change_nature = self._detect_nature(diff, mr_title, mr_description)
        
        # Step 5: Assess risk level
        risk_level = self._assess_risk(diff.changes)
        
        # Step 6: Detect special properties
        has_breaking = self._detect_breaking_changes(diff.changes)
        has_migration = any("migration" in c.path.lower() for c in diff.changes)
        has_new_deps = any(
            c.path in {"requirements.txt", "package.json", "Cargo.toml", "go.mod", "pyproject.toml"}
            and c.change_type in {ChangeType.MODIFIED, ChangeType.ADDED}
            for c in diff.changes
        )
        has_config = any(
            c.path.endswith((".yaml", ".yml", ".toml", ".ini", ".env"))
            and "test" not in c.path.lower()
            for c in diff.changes
        )
        has_tests = any(
            "test" in c.path.lower() or "spec" in c.path.lower()
            for c in diff.changes
        )
        
        # Step 7: Extract per-file diffs (for the technical doc)
        file_diffs = self._extract_file_diffs(merge_base or target_commit, source_commit)
        
        return MRAnalysis(
            mr_title=mr_title,
            mr_description=mr_description,
            source_branch=source_branch,
            target_branch=target_branch,
            author=author,
            diff=diff,
            change_nature=change_nature,
            risk_level=risk_level,
            change_groups=change_groups,
            has_breaking_changes=has_breaking,
            has_migration=has_migration,
            has_new_dependencies=has_new_deps,
            has_config_changes=has_config,
            has_test_changes=has_tests,
            commit_messages=diff.commit_messages,
            file_diffs=file_diffs,
        )
    
    def analyze_from_diff(
        self,
        from_commit: str,
        to_commit: str,
        mr_title: str = "",
        mr_description: str = "",
    ) -> MRAnalysis:
        """Analyze an MR using explicit commit hashes instead of branch names.
        
        Useful for analyzing already-merged MRs or when you have the
        exact commits rather than branch references.
        """
        diff = self.git.diff(from_commit, to_commit)
        
        change_groups = self._group_by_feature(diff.changes)
        change_nature = self._detect_nature(diff, mr_title, mr_description)
        risk_level = self._assess_risk(diff.changes)
        has_breaking = self._detect_breaking_changes(diff.changes)
        file_diffs = self._extract_file_diffs(from_commit, to_commit)
        
        return MRAnalysis(
            mr_title=mr_title or "Merge Request",
            mr_description=mr_description,
            source_branch=to_commit[:8],
            target_branch=from_commit[:8],
            diff=diff,
            change_nature=change_nature,
            risk_level=risk_level,
            change_groups=change_groups,
            has_breaking_changes=has_breaking,
            has_migration=any("migration" in c.path.lower() for c in diff.changes),
            has_new_dependencies=any(
                c.path in {"requirements.txt", "package.json", "Cargo.toml", "go.mod"}
                for c in diff.changes
            ),
            has_test_changes=any("test" in c.path.lower() for c in diff.changes),
            commit_messages=diff.commit_messages,
            file_diffs=file_diffs,
        )
    
    # ──────────────────────────────────────────────────────────────────
    # Private analysis methods
    # ──────────────────────────────────────────────────────────────────
    
    def _group_by_feature(self, changes: list[FileChange]) -> list[ChangeGroup]:
        """Group changed files by logical feature area.
        
        This looks at the directory structure of each changed file and maps
        it to a human-readable feature area using the DIRECTORY_FEATURE_MAP.
        Files that don't match any known area go into "Other Changes".
        """
        groups: dict[str, list[FileChange]] = {}
        
        for change in changes:
            area = self._detect_feature_area(change.path)
            groups.setdefault(area, []).append(change)
        
        # Convert to ChangeGroup objects, sorted by number of files (most files first)
        result = []
        for name, files in sorted(groups.items(), key=lambda x: -len(x[1])):
            # Determine the nature of changes in this group
            natures = set()
            for f in files:
                if "test" in f.path.lower():
                    natures.add(ChangeNature.TESTING)
                elif f.change_type == ChangeType.ADDED:
                    natures.add(ChangeNature.NEW_FEATURE)
                else:
                    natures.add(ChangeNature.MIXED)
            
            nature = natures.pop() if len(natures) == 1 else ChangeNature.MIXED
            
            result.append(ChangeGroup(
                name=name,
                files=files,
                nature=nature,
            ))
        
        return result
    
    def _detect_feature_area(self, filepath: str) -> str:
        """Map a file path to its logical feature area."""
        parts = Path(filepath).parts
        
        # Check each directory component against our feature map
        for part in parts:
            part_lower = part.lower()
            if part_lower in DIRECTORY_FEATURE_MAP:
                return DIRECTORY_FEATURE_MAP[part_lower]
        
        # Fall back to the immediate parent directory name
        if len(parts) > 1:
            return parts[-2].replace("_", " ").replace("-", " ").title()
        
        # Root-level files
        return "Project Root"
    
    def _detect_nature(
        self, diff: DiffResult, title: str, description: str,
    ) -> ChangeNature:
        """Infer the nature of the MR from commit messages, title, and file patterns.
        
        We use keyword matching on the MR title and commit messages to determine
        if this is a feature, fix, refactor, etc. This aligns with conventional
        commit conventions (feat:, fix:, refactor:, etc.)
        """
        text = f"{title} {description} {' '.join(diff.commit_messages)}".lower()
        
        # Check for conventional commit prefixes and common keywords
        nature_keywords = {
            ChangeNature.BUG_FIX: ["fix", "bug", "patch", "hotfix", "issue", "resolve"],
            ChangeNature.NEW_FEATURE: ["feat", "feature", "add", "implement", "introduce", "new"],
            ChangeNature.REFACTOR: ["refactor", "restructure", "reorganize", "clean", "simplify"],
            ChangeNature.PERFORMANCE: ["perf", "performance", "optimize", "speed", "cache", "fast"],
            ChangeNature.SECURITY: ["security", "vulnerability", "cve", "auth", "encrypt"],
            ChangeNature.DOCUMENTATION: ["docs", "documentation", "readme", "guide"],
            ChangeNature.TESTING: ["test", "coverage", "spec", "e2e"],
            ChangeNature.DEPENDENCY_UPDATE: ["deps", "dependency", "upgrade", "bump", "update"],
            ChangeNature.CONFIGURATION: ["config", "env", "settings", "ci/cd", "pipeline"],
            ChangeNature.INFRASTRUCTURE: ["infra", "docker", "k8s", "deploy", "terraform"],
        }
        
        scores: dict[ChangeNature, int] = {}
        for nature, keywords in nature_keywords.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[nature] = score
        
        if scores:
            return max(scores, key=lambda k: scores[k])
        
        # Fall back to file-based detection
        if all("test" in c.path.lower() for c in diff.changes):
            return ChangeNature.TESTING
        if all(c.path.endswith((".md", ".rst", ".txt")) for c in diff.changes):
            return ChangeNature.DOCUMENTATION
        
        return ChangeNature.MIXED
    
    def _assess_risk(self, changes: list[FileChange]) -> RiskLevel:
        """Assess the deployment risk level of an MR based on what was changed.
        
        Risk assessment is based on which parts of the codebase were touched.
        Changes to authentication, payment, or database migration files are
        inherently higher risk than changes to documentation or tests.
        """
        max_risk = RiskLevel.LOW
        
        for change in changes:
            path = change.path
            
            # Check for breaking change patterns (critical risk)
            for pattern in BREAKING_CHANGE_PATTERNS:
                if re.match(pattern, path):
                    if change.change_type == ChangeType.DELETED:
                        return RiskLevel.CRITICAL  # Deleted API = breaking change
                    max_risk = max(max_risk, RiskLevel.HIGH, key=lambda r: list(RiskLevel).index(r))
            
            # Check for high-risk patterns
            for pattern in HIGH_RISK_PATTERNS:
                if re.match(pattern, path):
                    max_risk = max(max_risk, RiskLevel.HIGH, key=lambda r: list(RiskLevel).index(r))
            
            # Source code changes are at least medium risk
            source_exts = {".py", ".ts", ".js", ".go", ".rs", ".java", ".kt", ".rb"}
            if Path(path).suffix in source_exts and "test" not in path.lower():
                max_risk = max(max_risk, RiskLevel.MEDIUM, key=lambda r: list(RiskLevel).index(r))
        
        return max_risk
    
    def _detect_breaking_changes(self, changes: list[FileChange]) -> bool:
        """Check if the MR likely contains breaking changes."""
        for change in changes:
            # Deleted files that look like API definitions
            if change.change_type == ChangeType.DELETED:
                for pattern in BREAKING_CHANGE_PATTERNS:
                    if re.match(pattern, change.path):
                        return True
            
            # Renamed API files (could break imports/endpoints)
            if change.change_type == ChangeType.RENAMED:
                for pattern in BREAKING_CHANGE_PATTERNS:
                    if re.match(pattern, change.path):
                        return True
        
        return False
    
    def _extract_file_diffs(
        self, from_commit: str, to_commit: str,
    ) -> dict[str, str]:
        """Get the actual diff content for each changed file.
        
        This is used in the technical MR doc to show exactly what changed.
        We truncate large diffs to keep the document readable.
        """
        result: dict[str, str] = {}
        
        try:
            output = subprocess.run(
                ["git", "diff", "--unified=3", from_commit, to_commit],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if output.returncode != 0:
                return result
            
            # Parse the unified diff output into per-file sections
            current_file = None
            current_diff: list[str] = []
            
            for line in output.stdout.splitlines():
                if line.startswith("diff --git"):
                    # Save previous file's diff
                    if current_file and current_diff:
                        diff_text = "\n".join(current_diff)
                        # Truncate very large diffs
                        if len(diff_text) > 3000:
                            diff_text = diff_text[:3000] + "\n... [diff truncated]"
                        result[current_file] = diff_text
                    
                    # Extract filename from "diff --git a/path b/path"
                    parts = line.split(" b/")
                    current_file = parts[-1] if len(parts) > 1 else None
                    current_diff = [line]
                elif current_file:
                    current_diff.append(line)
            
            # Don't forget the last file
            if current_file and current_diff:
                diff_text = "\n".join(current_diff)
                if len(diff_text) > 3000:
                    diff_text = diff_text[:3000] + "\n... [diff truncated]"
                result[current_file] = diff_text
                
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return result
    
    def _get_merge_base(self, commit_a: str, commit_b: str) -> Optional[str]:
        """Find the merge base (common ancestor) of two commits.
        
        This is important for MR analysis: we want to diff only the changes
        introduced by the MR, not everything that differs between the branches.
        The merge base is where the feature branch diverged from main.
        """
        try:
            result = subprocess.run(
                ["git", "merge-base", commit_a, commit_b],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None
    
    def _title_from_branch(self, branch_name: str) -> str:
        """Generate a human-readable title from a branch name.
        
        Converts "feature/add-oauth-login" to "Add OAuth Login"
        or "fix/user-profile-crash" to "User Profile Crash Fix"
        """
        # Remove common prefixes
        name = branch_name
        for prefix in ["feature/", "feat/", "fix/", "bugfix/", "hotfix/",
                        "refactor/", "chore/", "docs/", "perf/"]:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        
        # Convert separators to spaces and title-case
        name = name.replace("-", " ").replace("_", " ").replace("/", " - ")
        return name.title()
