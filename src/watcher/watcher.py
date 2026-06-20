"""
Branch Watcher — monitors the main branch for changes and auto-updates docs.

This module provides two modes of watching for changes:

MODE 1: POLLING (simpler, works everywhere)
    The watcher runs as a background process that periodically checks
    if the main branch has new commits. If it detects changes, it runs
    the incremental updater.

    ┌─────────────┐       ┌──────────┐       ┌──────────────┐
    │  Timer Loop │ ────> │  git     │ ────> │  Incremental │
    │  (every 5m) │       │  fetch   │       │  Updater     │
    └─────────────┘       │  + diff  │       └──────────────┘
                          └──────────┘

MODE 2: GIT HOOKS (more efficient, requires setup)
    A post-merge or post-receive hook triggers the update immediately
    when new commits land on main. This is more efficient (no polling)
    but requires adding a hook to the repo's .git/hooks/ directory.

    ┌──────────────┐       ┌──────────────┐
    │  git merge   │ ────> │  Incremental │
    │  (hook fires)│       │  Updater     │
    └──────────────┘       └──────────────┘

MODE 3: CI/CD INTEGRATION (production-grade)
    The update runs as a CI/CD step after merges to main. This is
    the most reliable approach for teams. The watcher provides a
    single-shot "check and update" command for this use case.

In all modes, the watcher uses the DocState file to know the last documented
commit and the GitDiffEngine to figure out what changed since then.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from src.config.settings import ServerConfig
from src.llm.providers import create_llm_provider
from src.publishers.confluence import ConfluencePublisher
from src.publishers.google_docs import GoogleDocsPublisher
from src.watcher.git_diff import GitDiffEngine, ChangeScope
from src.watcher.incremental import DocState, IncrementalUpdater, UpdateResult


class BranchWatcher:
    """Watches a branch for changes and triggers doc updates.

    Usage (polling mode):
        watcher = BranchWatcher(config, repo_path="/path/to/repo")
        await watcher.start_polling(interval_minutes=5)

    Usage (single-shot for CI/CD):
        watcher = BranchWatcher(config, repo_path="/path/to/repo")
        result = await watcher.check_and_update()
    """

    def __init__(
        self,
        config: ServerConfig,
        repo_path: str,
        branch: str | None = None,
        output_dir: str | None = None,
        on_update: Callable[[UpdateResult], None] | None = None,
    ):
        """Initialize the watcher.

        Args:
            config: Server configuration (LLM settings, doc settings, etc.)
            repo_path: Path to the repository to watch
            branch: Branch to watch (auto-detected if not specified)
            output_dir: Where docs are saved (from config if not specified)
            on_update: Optional callback fired when an update completes
        """
        self.config = config
        self.repo_path = Path(repo_path).resolve()
        self.output_dir = Path(
            output_dir or config.doc.output_dir
        )
        if not self.output_dir.is_absolute():
            self.output_dir = self.repo_path / self.output_dir

        self.on_update = on_update
        self._running = False
        self._git = GitDiffEngine(str(self.repo_path))

        # Auto-detect the main branch if not specified
        self.branch = branch or self._git.detect_main_branch()

    async def check_and_update(self) -> UpdateResult:
        """Single-shot: check for changes and update if needed.

        This is the core method. It:
        1. Loads the last documented state (which commit was last documented)
        2. Fetches the latest state of the watched branch
        3. Computes the diff between last documented and current
        4. If there are changes, runs the incremental updater
        5. Returns the result

        This is idempotent — calling it multiple times without new commits
        will return a "no changes" result.
        """
        # Step 1: Load previous state
        state = DocState.load(self.output_dir)

        # Step 2: Fetch latest from remote (best effort — works without network too)
        self._fetch_remote()

        # Step 3: Get current commit on the watched branch
        current_commit = self._git.get_head_commit(self.branch)
        if not current_commit:
            # Try the remote version
            current_commit = self._git.get_head_commit(f"origin/{self.branch}")

        if not current_commit:
            return UpdateResult(
                strategy="error",
                message=f"Could not determine current commit for branch '{self.branch}'",
            )

        # Step 4: Determine if anything changed
        if state and state.commit_hash == current_commit:
            return UpdateResult(
                strategy="skip",
                message="No new commits — docs are up to date.",
            )

        # Step 5: Compute the diff
        if state and state.commit_hash:
            diff = self._git.diff(state.commit_hash, current_commit)
        else:
            # No previous state — this is the first run, do a full generation.
            # We create a "fake" diff that triggers full regeneration.
            diff = self._git.diff_from_last(current_commit)
            # Force structural scope to trigger full regen
            diff.scope = ChangeScope.STRUCTURAL

        self._log(
            f"Changes detected: {diff.total_files_changed} files changed "
            f"(scope: {diff.scope.value})"
        )
        self._log(diff.summary())

        # Step 6: Run the incremental updater
        llm = create_llm_provider(self.config.llm)
        updater = IncrementalUpdater(llm, self.config)
        result = await updater.update(
            str(self.repo_path),
            diff,
            str(self.output_dir),
        )

        self._log(f"Update complete: {result.message}")

        # Auto-publish if configured and update actually changed docs
        if (
            self.config.watcher.publish_after_update
            and result.strategy not in ("skip", "error")
        ):
            await self._publish_updated_docs()

        # Fire the callback if registered
        if self.on_update:
            self.on_update(result)

        return result

    async def start_polling(
        self,
        interval_minutes: float = 5.0,
    ) -> None:
        """Start the polling loop — checks for changes every N minutes.

        This runs indefinitely until stop() is called or the process is killed.
        It's designed to run as a background process or daemon.

        The polling approach is simple and reliable:
        - Every interval, it runs check_and_update()
        - If there are changes, docs get updated
        - If not, it goes back to sleep
        - If an error occurs, it logs it and tries again next interval

        For production use, you'd typically run this via systemd, supervisor,
        or as a Docker container.
        """
        self._running = True
        interval_seconds = interval_minutes * 60

        self._log(
            f"Starting branch watcher for '{self.branch}' "
            f"(polling every {interval_minutes} minutes)"
        )
        self._log(f"Repository: {self.repo_path}")
        self._log(f"Output: {self.output_dir}")

        while self._running:
            try:
                result = await self.check_and_update()
                self._log(f"[{datetime.utcnow().isoformat()}] {result.message}")
            except Exception as e:
                self._log(f"Error during update check: {e}")

            # Sleep until next check (but wake up if stop() is called)
            for _ in range(int(interval_seconds)):
                if not self._running:
                    break
                await asyncio.sleep(1)

        self._log("Watcher stopped.")

    def stop(self) -> None:
        """Stop the polling loop gracefully."""
        self._running = False

    async def _publish_updated_docs(self) -> None:
        """Publish updated docs to configured destinations after a watcher update."""
        tech_path = self.output_dir / "TECHNICAL_DOC.md"
        simple_path = self.output_dir / "NON_TECHNICAL_GUIDE.md"

        tech_content = tech_path.read_text(encoding="utf-8") if tech_path.exists() else ""
        simple_content = simple_path.read_text(encoding="utf-8") if simple_path.exists() else ""

        if not tech_content and not simple_content:
            self._log("No docs found to publish.")
            return

        repo_name = self.repo_path.name

        if self.config.publish.confluence.enabled:
            try:
                publisher = ConfluencePublisher(self.config.publish.confluence)
                result = await publisher.publish(tech_content, simple_content, repo_name)
                self._log(f"Confluence: {result.summary()}")
            except Exception as e:
                self._log(f"Confluence publish failed: {e}")

        if self.config.publish.google_docs.enabled:
            try:
                publisher = GoogleDocsPublisher(self.config.publish.google_docs)
                result = await publisher.publish(tech_content, simple_content, repo_name)
                self._log(f"Google Docs: {result.summary()}")
            except Exception as e:
                self._log(f"Google Docs publish failed: {e}")

    def _fetch_remote(self) -> None:
        """Fetch latest changes from the remote.

        This ensures we detect commits pushed by other developers,
        not just local changes. It's a best-effort operation — if
        there's no network connectivity, we'll still check local state.
        """
        try:
            import subprocess
            subprocess.run(
                ["git", "fetch", "origin", self.branch],
                cwd=self.repo_path,
                capture_output=True,
                timeout=30,
            )
        except Exception:
            pass  # Network fetch is best-effort

    def _log(self, message: str) -> None:
        """Simple logging — prints to stdout with a timestamp.
        In production, this would use Python's logging module."""
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        print(f"[repo-doc-watcher {timestamp}] {message}")


# ──────────────────────────────────────────────────────────────────────
# Git Hook Generator — creates git hooks for event-driven updates
# ──────────────────────────────────────────────────────────────────────

class GitHookInstaller:
    """Installs git hooks that trigger doc updates on branch changes.

    Instead of polling, git hooks fire IMMEDIATELY when relevant events happen.
    This is more efficient but requires modifying the repo's .git/hooks/.

    We install a post-merge hook that fires after `git merge` or `git pull`
    completes on the watched branch. The hook spawns the updater as a
    background process so it doesn't block the git operation.
    """

    HOOK_TEMPLATE = '''#!/bin/bash
# Auto-generated by repo-doc-mcp — do not edit manually
# This hook triggers documentation updates after merges to {branch}

# Get the current branch name
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Only run for the watched branch
if [ "$CURRENT_BRANCH" = "{branch}" ]; then
    echo "[repo-doc] Merge detected on {branch} — triggering doc update..."

    # Run the updater in the background so it doesn't block git
    nohup {python_path} -m src.watcher.cli check \\
        --repo-path "{repo_path}" \\
        --output "{output_dir}" \\
        > "{output_dir}/.repo-doc-update.log" 2>&1 &

    echo "[repo-doc] Doc update started in background (PID: $!)"
    echo "[repo-doc] Check {output_dir}/.repo-doc-update.log for progress"
fi
'''

    POST_RECEIVE_TEMPLATE = '''#!/bin/bash
# Auto-generated by repo-doc-mcp
# Server-side hook for bare repositories (e.g., on GitHub/GitLab self-hosted)

while read oldrev newrev refname; do
    BRANCH=$(echo "$refname" | sed 's|refs/heads/||')
    if [ "$BRANCH" = "{branch}" ]; then
        echo "[repo-doc] Push to {branch} detected — triggering doc update..."
        nohup {python_path} -m src.watcher.cli check \\
            --repo-path "{repo_path}" \\
            --output "{output_dir}" \\
            > "{output_dir}/.repo-doc-update.log" 2>&1 &
    fi
done
'''

    def __init__(
        self,
        repo_path: str,
        python_path: str = "python3",
        branch: str = "main",
        output_dir: str = "./docs/generated",
        mcp_server_path: str = ".",
    ):
        self.repo_path = Path(repo_path).resolve()
        self.python_path = python_path
        self.branch = branch
        self.output_dir = output_dir
        self.mcp_server_path = Path(mcp_server_path).resolve()

    def install_post_merge_hook(self) -> str:
        """Install a post-merge hook in the repo.

        Returns the path to the installed hook file.
        Backs up any existing hook before overwriting.
        """
        hooks_dir = self.repo_path / ".git" / "hooks"
        hook_path = hooks_dir / "post-merge"

        # Backup existing hook if present
        if hook_path.exists():
            backup_path = hook_path.with_suffix(".backup")
            hook_path.rename(backup_path)

        # Generate and write the hook script
        hook_content = self.HOOK_TEMPLATE.format(
            branch=self.branch,
            python_path=self.python_path,
            repo_path=str(self.repo_path),
            output_dir=self.output_dir,
        )

        hook_path.write_text(hook_content)
        hook_path.chmod(0o755)  # Make executable

        return str(hook_path)

    def install_post_receive_hook(self) -> str:
        """Install a post-receive hook (for bare/server repos).

        This is used in self-hosted Git servers where pushes to main
        should trigger doc generation.
        """
        hooks_dir = self.repo_path / "hooks"  # Bare repos use /hooks directly
        if not hooks_dir.exists():
            hooks_dir = self.repo_path / ".git" / "hooks"

        hook_path = hooks_dir / "post-receive"

        if hook_path.exists():
            backup_path = hook_path.with_suffix(".backup")
            hook_path.rename(backup_path)

        hook_content = self.POST_RECEIVE_TEMPLATE.format(
            branch=self.branch,
            python_path=self.python_path,
            repo_path=str(self.repo_path),
            output_dir=self.output_dir,
        )

        hook_path.write_text(hook_content)
        hook_path.chmod(0o755)

        return str(hook_path)

    def uninstall_hooks(self) -> list[str]:
        """Remove all repo-doc hooks and restore backups if they exist."""
        hooks_dir = self.repo_path / ".git" / "hooks"
        removed = []

        for hook_name in ["post-merge", "post-receive"]:
            hook_path = hooks_dir / hook_name
            backup_path = hook_path.with_suffix(".backup")

            if hook_path.exists():
                content = hook_path.read_text()
                if "repo-doc-mcp" in content:
                    hook_path.unlink()
                    removed.append(hook_name)

                    # Restore backup if it exists
                    if backup_path.exists():
                        backup_path.rename(hook_path)

        return removed

    def generate_github_action(self) -> str:
        """Generate a GitHub Actions workflow YAML for CI/CD integration.

        This is the production-grade approach: run doc updates as a CI step
        after merges to main. The workflow commits the updated docs back
        to the repo automatically.
        """
        return f"""# .github/workflows/update-docs.yml
# Auto-generated by repo-doc-mcp
# This workflow updates documentation when changes are pushed to {self.branch}

name: Update Documentation

on:
  push:
    branches:
      - {self.branch}

jobs:
  update-docs:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history needed for git diff

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install repo-doc-mcp
        run: |
          cd {self.mcp_server_path}
          pip install -e .

      - name: Check for changes and update docs
        env:
          ANTHROPIC_API_KEY: ${{{{ secrets.ANTHROPIC_API_KEY }}}}
        run: |
          python -m src.watcher.cli check \\
            --repo-path . \\
            --output {self.output_dir}

      - name: Commit updated docs
        run: |
          git config user.name "repo-doc-bot"
          git config user.email "bot@repo-doc-mcp"
          git add {self.output_dir}/
          if git diff --staged --quiet; then
            echo "No doc changes to commit"
          else
            git commit -m "docs: auto-update documentation [skip ci]"
            git push
          fi
"""
