"""
Branch-Aware Documentation — generates separate docs per working branch.

This module enables the vision of:
    Mainline (main/master):
        → docs/generated/main/TECHNICAL_DOC.md          (always up-to-date)
        → Published to Confluence: "MyApp — Technical Documentation"

    Working branch (feature/xyz):
        → docs/generated/feature-xyz/TECHNICAL_DOC.md    (shows what's different)
        → Published to Confluence: "MyApp — feature/xyz Documentation"
        → Includes a "What Changed vs Main" section

The branch doc generator:
1. Uses GitDiffEngine to compute branch diff vs main
2. Generates full docs for the branch via the standard pipeline
3. Prepends a "What Changed" section summarizing the branch's changes
4. Saves to a branch-namespaced output directory
5. Optionally publishes to a separate Confluence page
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config.settings import ServerConfig
from src.generators.doc_generator import DocGenerator
from src.llm.providers import BaseLLMProvider, create_llm_provider
from src.parsers.analyzer import CodeAnalyzer
from src.parsers.scanner import RepoScanner
from src.publishers.confluence import ConfluencePublisher
from src.publishers.google_docs import GoogleDocsPublisher
from src.watcher.git_diff import GitDiffEngine, DiffResult, ChangeScope
from src.watcher.incremental import DocState


def sanitize_branch_name(branch: str) -> str:
    """Convert a branch name to a safe directory/file name."""
    return re.sub(r'[^\w\-.]', '-', branch.replace('/', '-'))


class BranchDocGenerator:
    """Generates documentation for a specific branch with a diff-vs-main section.

    Usage:
        generator = BranchDocGenerator(config, repo_path="/path/to/repo")
        result = await generator.generate_branch_docs("feature/add-oauth")
    """

    def __init__(self, config: ServerConfig, repo_path: str):
        self.config = config
        self.repo_path = Path(repo_path).resolve()
        self._git = GitDiffEngine(str(self.repo_path))

    async def generate_branch_docs(
        self,
        branch: str,
        base_branch: str | None = None,
    ) -> BranchDocResult:
        """Generate docs for a working branch, including a diff vs main.

        Args:
            branch: The working branch to document (e.g., "feature/add-oauth")
            base_branch: The base branch to compare against (auto-detected if None)

        Returns:
            BranchDocResult with paths and publish status
        """
        base = base_branch or self._git.detect_main_branch()
        safe_name = sanitize_branch_name(branch)

        # Compute the branch output directory
        base_output = Path(self.config.doc.output_dir)
        if not base_output.is_absolute():
            base_output = self.repo_path / base_output
        branch_output = base_output / safe_name
        branch_output.mkdir(parents=True, exist_ok=True)

        # Step 1: Compute diff between base and branch
        base_commit = self._git.get_head_commit(base)
        branch_commit = self._git.get_head_commit(branch)

        if not base_commit or not branch_commit:
            return BranchDocResult(
                branch=branch,
                base_branch=base,
                success=False,
                message=f"Could not resolve commits for {base} or {branch}",
            )

        diff = self._git.diff(base_commit, branch_commit)

        # Step 2: Generate full docs for the branch state
        llm = create_llm_provider(self.config.llm)
        scanner = RepoScanner(self.config.repo)
        repo_tree = scanner.scan(str(self.repo_path))

        analyzer = CodeAnalyzer(llm)
        analysis = await analyzer.analyze(repo_tree)

        generator = DocGenerator(llm, self.config.doc)
        tech_doc, simple_doc = await generator.generate(analysis)

        tech_content = tech_doc.to_markdown()
        simple_content = simple_doc.to_markdown()

        # Step 3: Prepend the "What Changed" section
        change_section = self._build_change_section(diff, branch, base)
        tech_content = change_section + "\n\n---\n\n" + tech_content
        simple_content = self._build_simple_change_section(diff, branch, base) + "\n\n---\n\n" + simple_content

        # Step 4: Save to branch-namespaced directory
        (branch_output / "TECHNICAL_DOC.md").write_text(tech_content, encoding="utf-8")
        (branch_output / "NON_TECHNICAL_GUIDE.md").write_text(simple_content, encoding="utf-8")

        # Save state for incremental updates
        state = DocState(
            commit_hash=branch_commit,
            branch=branch,
            repo_name=repo_tree.name,
            documented_files={f.path: str(f.size_bytes) for f in repo_tree.files},
        )
        state.save(branch_output)

        result = BranchDocResult(
            branch=branch,
            base_branch=base,
            success=True,
            output_dir=str(branch_output),
            files_changed=diff.total_files_changed,
            change_scope=diff.scope.value,
            message=f"Branch docs generated: {diff.total_files_changed} files differ from {base}",
        )

        # Step 5: Publish if configured
        if self.config.watcher.branch_docs.publish_branch_docs:
            await self._publish_branch_docs(
                tech_content, simple_content, branch, result,
            )

        return result

    async def cleanup_branch_docs(self, branch: str) -> bool:
        """Remove branch-specific docs after merge/deletion.

        Returns True if docs were found and cleaned up.
        """
        safe_name = sanitize_branch_name(branch)
        base_output = Path(self.config.doc.output_dir)
        if not base_output.is_absolute():
            base_output = self.repo_path / base_output
        branch_output = base_output / safe_name

        if not branch_output.exists():
            return False

        # Remove all files in the branch directory
        import shutil
        shutil.rmtree(branch_output)
        return True

    def _build_change_section(
        self, diff: DiffResult, branch: str, base: str,
    ) -> str:
        """Build a Markdown section showing what changed vs main (technical)."""
        lines = [
            f"# Branch: `{branch}` — Changes vs `{base}`",
            "",
            f"*Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*",
            f"*Comparing: `{diff.from_commit[:8]}` ({base}) → `{diff.to_commit[:8]}` ({branch})*",
            f"*Change scope: **{diff.scope.value}***",
            "",
            f"## Summary of Changes",
            "",
            f"**{diff.total_files_changed}** files changed:",
            "",
        ]

        if diff.added_files:
            lines.append(f"### Added ({len(diff.added_files)} files)")
            for f in diff.added_files[:20]:
                stats = f""
                if f.diff_stats:
                    stats = f" (+{f.diff_stats.lines_added})"
                lines.append(f"- `{f.path}`{stats}")
            lines.append("")

        if diff.modified_files:
            lines.append(f"### Modified ({len(diff.modified_files)} files)")
            for f in diff.modified_files[:20]:
                stats = ""
                if f.diff_stats:
                    stats = f" (+{f.diff_stats.lines_added}/-{f.diff_stats.lines_removed})"
                lines.append(f"- `{f.path}`{stats}")
            lines.append("")

        if diff.deleted_files:
            lines.append(f"### Deleted ({len(diff.deleted_files)} files)")
            for f in diff.deleted_files[:20]:
                lines.append(f"- `{f.path}`")
            lines.append("")

        if diff.commit_messages:
            lines.append("### Commit History")
            lines.append("")
            for msg in diff.commit_messages[:15]:
                lines.append(f"- {msg}")
            lines.append("")

        return "\n".join(lines)

    def _build_simple_change_section(
        self, diff: DiffResult, branch: str, base: str,
    ) -> str:
        """Build a plain-English summary of branch changes (non-technical)."""
        lines = [
            f"# What's New on `{branch}`",
            "",
            f"This document describes the version of the project on the **{branch}** branch, "
            f"which has **{diff.total_files_changed}** changes compared to the main version ({base}).",
            "",
        ]

        if diff.added_files:
            names = [Path(f.path).stem for f in diff.added_files[:5]]
            lines.append(f"**New features/components added:** {', '.join(names)}")
            lines.append("")

        if diff.modified_files:
            names = [Path(f.path).stem for f in diff.modified_files[:5]]
            lines.append(f"**Updated parts:** {', '.join(names)}")
            lines.append("")

        if diff.deleted_files:
            names = [Path(f.path).stem for f in diff.deleted_files[:5]]
            lines.append(f"**Removed:** {', '.join(names)}")
            lines.append("")

        if diff.commit_messages:
            lines.append("**Recent changes described as:**")
            for msg in diff.commit_messages[:5]:
                # Strip commit hash prefix if present
                clean = msg.split(" ", 1)[-1] if " " in msg else msg
                lines.append(f"- {clean}")
            lines.append("")

        return "\n".join(lines)

    async def _publish_branch_docs(
        self,
        tech_content: str,
        simple_content: str,
        branch: str,
        result: "BranchDocResult",
    ) -> None:
        """Publish branch docs to separate Confluence/Google Docs pages."""
        repo_name = self.repo_path.name
        branch_label = f"{repo_name} [{branch}]"

        if self.config.publish.confluence.enabled:
            try:
                publisher = ConfluencePublisher(self.config.publish.confluence)
                pub_result = await publisher.publish(
                    tech_content, simple_content, branch_label,
                )
                result.confluence_url = pub_result.technical_url
            except Exception as e:
                result.publish_error = f"Confluence: {e}"

        if self.config.publish.google_docs.enabled:
            try:
                publisher = GoogleDocsPublisher(self.config.publish.google_docs)
                pub_result = await publisher.publish(
                    tech_content, simple_content, branch_label,
                )
                result.google_docs_url = pub_result.technical_url
            except Exception as e:
                result.publish_error = f"Google Docs: {e}"


class BranchDocResult:
    """Result of a branch documentation generation."""

    def __init__(
        self,
        branch: str = "",
        base_branch: str = "",
        success: bool = False,
        output_dir: str = "",
        files_changed: int = 0,
        change_scope: str = "",
        message: str = "",
        confluence_url: str = "",
        google_docs_url: str = "",
        publish_error: str = "",
    ):
        self.branch = branch
        self.base_branch = base_branch
        self.success = success
        self.output_dir = output_dir
        self.files_changed = files_changed
        self.change_scope = change_scope
        self.message = message
        self.confluence_url = confluence_url
        self.google_docs_url = google_docs_url
        self.publish_error = publish_error
        self.timestamp = datetime.utcnow().isoformat()

    def summary(self) -> str:
        lines = [f"Branch docs: {self.branch} vs {self.base_branch}"]
        lines.append(f"  {self.message}")
        if self.output_dir:
            lines.append(f"  Output: {self.output_dir}")
        if self.confluence_url:
            lines.append(f"  Confluence: {self.confluence_url}")
        if self.google_docs_url:
            lines.append(f"  Google Docs: {self.google_docs_url}")
        if self.publish_error:
            lines.append(f"  Publish error: {self.publish_error}")
        return "\n".join(lines)
