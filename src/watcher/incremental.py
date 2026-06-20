"""
Incremental Update Engine — smart doc updates based on what changed.

This is the brain of the auto-update system. Instead of regenerating the
entire documentation on every commit (expensive and slow), this module:

1. Takes the DiffResult (what files changed)
2. Maps those changes to documentation sections
3. Regenerates ONLY the affected sections
4. Merges the new sections into the existing document

STRATEGY BY CHANGE SCOPE:

    ┌─────────────┐     ┌────────────────────────────────────────┐
    │  STRUCTURAL  │ ──> │ Full regeneration (new module = new    │
    │  (new module,│     │ architecture diagram, new sections,    │
    │   deleted pkg│     │ updated component list, etc.)          │
    │   10+ files) │     └────────────────────────────────────────┘
    └─────────────┘
    ┌─────────────┐     ┌────────────────────────────────────────┐
    │   CONTENT    │ ──> │ Targeted update — re-analyze only the  │
    │  (modified   │     │ changed files, update their summaries, │
    │   source code│     │ regenerate affected doc sections.      │
    │   20+ lines) │     └────────────────────────────────────────┘
    └─────────────┘
    ┌─────────────┐     ┌────────────────────────────────────────┐
    │  COSMETIC    │ ──> │ Skip — formatting/comment changes      │
    │  (few lines, │     │ don't warrant doc regeneration.        │
    │   config only│     │ Just update the commit hash metadata.  │
    └─────────────┘     └────────────────────────────────────────┘

The targeted update (CONTENT scope) is the most interesting case. It works
by asking the LLM: "Here is the existing doc section for module X. The code
in X has changed as follows: [diff]. Please update ONLY the affected parts
of this documentation section."

This is dramatically cheaper and faster than regenerating from scratch.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config.settings import ServerConfig
from src.core.models import (
    DocType,
    DocumentSection,
    FileType,
    GeneratedDoc,
    RepoAnalysis,
)
from src.generators.doc_generator import DocGenerator
from src.llm.providers import BaseLLMProvider
from src.parsers.analyzer import CodeAnalyzer
from src.parsers.scanner import RepoScanner
from src.watcher.git_diff import (
    ChangeScope,
    ChangeType,
    DiffResult,
    FileChange,
)


# ──────────────────────────────────────────────────────────────────────
# State Tracking — remembers what was documented and when
# ──────────────────────────────────────────────────────────────────────

class DocState:
    """Persists the state of the last documentation generation.

    We save this to a JSON file alongside the generated docs so the
    auto-updater knows:
    - Which commit was last documented
    - When the docs were last generated
    - Which files were included in the docs
    - File hashes to detect changes even without git

    This file is the "memory" of the auto-update system.
    """

    STATE_FILENAME = ".repo-doc-state.json"

    def __init__(
        self,
        commit_hash: str = "",
        branch: str = "",
        generated_at: str = "",
        documented_files: dict[str, str] | None = None,
        repo_name: str = "",
    ):
        self.commit_hash = commit_hash
        self.branch = branch
        self.generated_at = generated_at or datetime.utcnow().isoformat()
        self.documented_files = documented_files or {}  # {path: content_hash}
        self.repo_name = repo_name

    def save(self, output_dir: str | Path) -> None:
        """Save state to disk alongside the generated docs."""
        state_path = Path(output_dir) / self.STATE_FILENAME
        state_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "commit_hash": self.commit_hash,
            "branch": self.branch,
            "generated_at": self.generated_at,
            "documented_files": self.documented_files,
            "repo_name": self.repo_name,
            "version": "1.0",
        }

        state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, output_dir: str | Path) -> Optional["DocState"]:
        """Load the last saved state. Returns None if no state exists."""
        state_path = Path(output_dir) / cls.STATE_FILENAME
        if not state_path.exists():
            return None

        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return cls(
                commit_hash=data.get("commit_hash", ""),
                branch=data.get("branch", ""),
                generated_at=data.get("generated_at", ""),
                documented_files=data.get("documented_files", {}),
                repo_name=data.get("repo_name", ""),
            )
        except (json.JSONDecodeError, KeyError):
            return None


# ──────────────────────────────────────────────────────────────────────
# The Incremental Update Engine
# ──────────────────────────────────────────────────────────────────────

# Prompt template for targeted section updates
SECTION_UPDATE_PROMPT = """You are updating existing documentation based on code changes.

## Current Documentation Section
{existing_section}

## Changes Made (git diff summary)
Files changed: {changed_files}
Commit messages: {commit_messages}

## Updated Code for Changed Files
{updated_code}

## Instructions
Update the documentation section above to reflect the code changes. Rules:
1. Keep the same heading level and structure
2. Only change parts that are affected by the code changes
3. Keep everything else exactly as-is
4. If the changes don't affect this section at all, respond with "NO_CHANGES_NEEDED"
5. Maintain the same writing style and tone as the existing content
6. Update any function signatures, class names, or file references that changed

Respond with the COMPLETE updated section (even unchanged parts), or "NO_CHANGES_NEEDED".
"""

NON_TECH_SECTION_UPDATE_PROMPT = """You are updating a non-technical guide based on code changes.

## Current Guide Section
{existing_section}

## What Changed (in simple terms)
{change_summary}

## Instructions
Update this guide section to reflect the changes. Rules:
1. Keep the same friendly, jargon-free tone
2. Only change parts that are affected
3. If the changes don't affect this section, respond with "NO_CHANGES_NEEDED"
4. Use plain language and analogies
5. Don't add any technical details

Respond with the COMPLETE updated section, or "NO_CHANGES_NEEDED".
"""


class IncrementalUpdater:
    """Orchestrates incremental documentation updates.

    This is the main class for Phase 3. It decides the update strategy
    based on the diff scope, executes the appropriate update path, and
    saves the results.

    Usage:
        updater = IncrementalUpdater(config)
        result = await updater.update(repo_path, diff_result)
    """

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        config: ServerConfig,
    ):
        self.llm = llm_provider
        self.config = config

    async def update(
        self,
        repo_path: str,
        diff: DiffResult,
        output_dir: str | None = None,
    ) -> UpdateResult:
        """Execute an incremental documentation update.

        This is the main entry point. It examines the diff, decides
        on a strategy, and performs the minimum work needed.

        Returns an UpdateResult describing what was done.
        """
        out_dir = Path(
            output_dir or self.config.doc.output_dir
        )
        if not out_dir.is_absolute():
            out_dir = Path(repo_path) / out_dir

        # If there are no changes, just update the commit hash in state
        if not diff.has_changes:
            return UpdateResult(
                strategy="skip",
                message="No changes detected — docs are up to date.",
                files_reanalyzed=0,
                sections_updated=0,
            )

        # Route to the appropriate strategy based on change scope
        if diff.scope == ChangeScope.STRUCTURAL:
            return await self._full_regeneration(repo_path, diff, out_dir)
        elif diff.scope == ChangeScope.CONTENT:
            return await self._targeted_update(repo_path, diff, out_dir)
        else:
            return await self._cosmetic_update(repo_path, diff, out_dir)

    async def _full_regeneration(
        self,
        repo_path: str,
        diff: DiffResult,
        output_dir: Path,
    ) -> UpdateResult:
        """STRUCTURAL changes → full doc regeneration.

        When the architecture changes (new modules, deleted packages, etc.),
        it's safer and more reliable to regenerate everything from scratch.
        The incremental approach could miss cross-module impacts.
        """
        # Use the standard full pipeline from Phase 1
        scanner = RepoScanner(self.config.repo)
        repo_tree = scanner.scan(repo_path)

        analyzer = CodeAnalyzer(self.llm)
        analysis = await analyzer.analyze(repo_tree)

        generator = DocGenerator(self.llm, self.config.doc)
        tech_doc, simple_doc = await generator.generate(analysis)

        # Save docs
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "TECHNICAL_DOC.md").write_text(
            tech_doc.to_markdown(), encoding="utf-8"
        )
        (output_dir / "NON_TECHNICAL_GUIDE.md").write_text(
            simple_doc.to_markdown(), encoding="utf-8"
        )

        # Save state for next incremental update
        state = DocState(
            commit_hash=diff.to_commit,
            branch=repo_tree.branch or "",
            repo_name=repo_tree.name,
            documented_files={
                f.path: str(f.size_bytes) for f in repo_tree.files
            },
        )
        state.save(output_dir)

        return UpdateResult(
            strategy="full_regeneration",
            message=(
                f"Full regeneration triggered by structural changes "
                f"({diff.total_files_changed} files changed). "
                f"Both documents fully regenerated."
            ),
            files_reanalyzed=repo_tree.total_files,
            sections_updated=-1,  # -1 = all sections
            commit_messages=diff.commit_messages,
        )

    async def _targeted_update(
        self,
        repo_path: str,
        diff: DiffResult,
        output_dir: Path,
    ) -> UpdateResult:
        """CONTENT changes → update only affected sections.

        This is the "smart" path. We:
        1. Identify which doc sections are affected by the changed files
        2. Re-analyze ONLY the changed files
        3. Ask the LLM to update ONLY those sections
        4. Merge the updated sections back into the full document
        """
        # Load existing docs
        tech_path = output_dir / "TECHNICAL_DOC.md"
        simple_path = output_dir / "NON_TECHNICAL_GUIDE.md"

        if not tech_path.exists():
            # No existing docs to update — fall back to full gen
            return await self._full_regeneration(repo_path, diff, output_dir)

        tech_content = tech_path.read_text(encoding="utf-8")
        simple_content = simple_path.read_text(encoding="utf-8") if simple_path.exists() else ""

        # Re-analyze only the changed files
        changed_paths = [
            c.path for c in diff.changes
            if c.change_type != ChangeType.DELETED
        ]

        # Scan only the changed files (quick — just a few files)
        scanner = RepoScanner(self.config.repo)
        repo_tree = scanner.scan(repo_path)

        # Filter to only changed files
        changed_files = [
            f for f in repo_tree.files
            if f.path in changed_paths
        ]

        # Build a change context for the LLM
        change_summary = self._build_change_summary(diff)
        changed_files_str = ", ".join(changed_paths[:20])
        commit_msgs = "\n".join(diff.commit_messages[:10])

        # Build updated code snippets for changed files
        updated_code_parts = []
        for f in changed_files:
            content = f.content
            if len(content) > 4000:
                content = content[:4000] + "\n... [truncated]"
            updated_code_parts.append(
                f"### {f.path} ({f.language or 'unknown'})\n```\n{content}\n```"
            )
        updated_code = "\n\n".join(updated_code_parts) or "No updated code available."

        # Update technical doc sections
        sections_updated = 0
        updated_tech = await self._update_doc_sections(
            tech_content,
            changed_files_str=changed_files_str,
            commit_messages=commit_msgs,
            updated_code=updated_code,
            is_technical=True,
        )
        if updated_tech != tech_content:
            sections_updated += 1

        # Update non-technical doc sections
        updated_simple = simple_content
        if simple_content:
            updated_simple = await self._update_doc_sections(
                simple_content,
                changed_files_str=changed_files_str,
                commit_messages=commit_msgs,
                updated_code="",  # Don't include code in non-tech updates
                is_technical=False,
                change_summary=change_summary,
            )
            if updated_simple != simple_content:
                sections_updated += 1

        # Update metadata (commit hash, timestamp) in the docs
        updated_tech = self._update_metadata(
            updated_tech, diff.to_commit, repo_tree.branch
        )
        updated_simple = self._update_metadata(
            updated_simple, diff.to_commit, repo_tree.branch
        )

        # Save updated docs
        tech_path.write_text(updated_tech, encoding="utf-8")
        if simple_content:
            simple_path.write_text(updated_simple, encoding="utf-8")

        # Update state
        state = DocState(
            commit_hash=diff.to_commit,
            branch=repo_tree.branch or "",
            repo_name=repo_tree.name,
            documented_files={
                f.path: str(f.size_bytes) for f in repo_tree.files
            },
        )
        state.save(output_dir)

        return UpdateResult(
            strategy="targeted_update",
            message=(
                f"Targeted update: re-analyzed {len(changed_files)} changed files, "
                f"updated {sections_updated} doc section(s)."
            ),
            files_reanalyzed=len(changed_files),
            sections_updated=sections_updated,
            commit_messages=diff.commit_messages,
        )

    async def _cosmetic_update(
        self,
        repo_path: str,
        diff: DiffResult,
        output_dir: Path,
    ) -> UpdateResult:
        """COSMETIC changes → just update metadata, don't regenerate content.

        When only formatting, comments, or config files changed, the actual
        documentation content doesn't need updating. We just bump the commit
        hash and timestamp so the docs show they're current.
        """
        tech_path = output_dir / "TECHNICAL_DOC.md"
        simple_path = output_dir / "NON_TECHNICAL_GUIDE.md"

        if tech_path.exists():
            content = tech_path.read_text(encoding="utf-8")
            content = self._update_metadata(content, diff.to_commit, None)
            tech_path.write_text(content, encoding="utf-8")

        if simple_path.exists():
            content = simple_path.read_text(encoding="utf-8")
            content = self._update_metadata(content, diff.to_commit, None)
            simple_path.write_text(content, encoding="utf-8")

        # Update state
        state = DocState.load(output_dir)
        if state:
            state.commit_hash = diff.to_commit
            state.generated_at = datetime.utcnow().isoformat()
            state.save(output_dir)

        return UpdateResult(
            strategy="cosmetic_update",
            message=(
                f"Cosmetic changes only ({diff.total_files_changed} files). "
                f"Updated metadata — doc content unchanged."
            ),
            files_reanalyzed=0,
            sections_updated=0,
            commit_messages=diff.commit_messages,
        )

    async def _update_doc_sections(
        self,
        doc_content: str,
        changed_files_str: str,
        commit_messages: str,
        updated_code: str,
        is_technical: bool,
        change_summary: str = "",
    ) -> str:
        """Ask the LLM to update specific sections of a document.

        Rather than sending the entire doc to the LLM (expensive),
        we identify sections that mention the changed files and only
        send those sections for update.
        """
        # Split the document into sections at ## headings
        sections = re.split(r'(^## .+$)', doc_content, flags=re.MULTILINE)

        updated_sections = []
        i = 0
        while i < len(sections):
            section = sections[i]

            # Check if this section mentions any of the changed files
            is_affected = any(
                changed_file in section
                for changed_file in changed_files_str.split(", ")
                if changed_file.strip()
            )

            # Also check if this is a high-level section that should be updated
            # when code changes (like "Core Components" or "Architecture")
            high_level_keywords = [
                "architecture", "overview", "component", "summary",
                "tech stack", "data flow", "building block",
                "how it works", "what can it do",
            ]
            is_high_level = any(
                kw in section.lower() for kw in high_level_keywords
            )

            if (is_affected or is_high_level) and len(section.strip()) > 50:
                # This section needs updating — send it to the LLM
                if is_technical:
                    prompt = SECTION_UPDATE_PROMPT.format(
                        existing_section=section[:3000],
                        changed_files=changed_files_str,
                        commit_messages=commit_messages,
                        updated_code=updated_code[:6000],
                    )
                else:
                    prompt = NON_TECH_SECTION_UPDATE_PROMPT.format(
                        existing_section=section[:3000],
                        change_summary=change_summary or commit_messages,
                    )

                try:
                    response = await self.llm.generate(prompt)
                    if "NO_CHANGES_NEEDED" not in response:
                        updated_sections.append(response)
                    else:
                        updated_sections.append(section)
                except Exception:
                    # If LLM fails for a section, keep the original
                    updated_sections.append(section)
            else:
                updated_sections.append(section)

            i += 1

        return "".join(updated_sections)

    def _build_change_summary(self, diff: DiffResult) -> str:
        """Build a plain-English summary of the changes for non-tech docs."""
        parts = []
        if diff.added_files:
            names = [Path(f.path).stem for f in diff.added_files[:5]]
            parts.append(f"New features/components added: {', '.join(names)}")
        if diff.modified_files:
            names = [Path(f.path).stem for f in diff.modified_files[:5]]
            parts.append(f"Existing parts updated: {', '.join(names)}")
        if diff.deleted_files:
            names = [Path(f.path).stem for f in diff.deleted_files[:5]]
            parts.append(f"Parts removed: {', '.join(names)}")
        if diff.commit_messages:
            parts.append(f"Changes described as: {'; '.join(diff.commit_messages[:5])}")
        return "\n".join(parts) or "Minor updates to the codebase."

    def _update_metadata(
        self,
        doc_content: str,
        new_commit: str,
        branch: str | None,
    ) -> str:
        """Update the commit hash and timestamp in the document header."""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        # Update the "Generated:" line
        doc_content = re.sub(
            r'\*Generated: .+?\*',
            f'*Generated: {now}*',
            doc_content,
        )

        # Update the "Commit:" line
        doc_content = re.sub(
            r'\*Commit: `.+?`\*',
            f'*Commit: `{new_commit[:8]}`*',
            doc_content,
        )

        return doc_content


# ──────────────────────────────────────────────────────────────────────
# Result model
# ──────────────────────────────────────────────────────────────────────

class UpdateResult:
    """Describes the outcome of an incremental update."""

    def __init__(
        self,
        strategy: str,
        message: str,
        files_reanalyzed: int = 0,
        sections_updated: int = 0,
        commit_messages: list[str] | None = None,
    ):
        self.strategy = strategy
        self.message = message
        self.files_reanalyzed = files_reanalyzed
        self.sections_updated = sections_updated
        self.commit_messages = commit_messages or []
        self.timestamp = datetime.utcnow().isoformat()

    def __repr__(self) -> str:
        return (
            f"UpdateResult(strategy={self.strategy!r}, "
            f"files={self.files_reanalyzed}, "
            f"sections={self.sections_updated})"
        )
