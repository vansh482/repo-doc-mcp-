"""
Watcher CLI — command-line interface for the auto-update system.

This provides three subcommands:

    python -m src.watcher.cli check      — Single-shot: check for changes and update
    python -m src.watcher.cli watch      — Start polling daemon (runs continuously)
    python -m src.watcher.cli install    — Install git hooks for automatic triggering
    python -m src.watcher.cli generate   — Generate CI/CD workflow files

Usage examples:

    # Check for changes and update docs if needed (great for CI/CD)
    python -m src.watcher.cli check --repo-path /path/to/repo

    # Start watching in the background (polls every 5 minutes)
    python -m src.watcher.cli watch --repo-path /path/to/repo --interval 5

    # Install a git post-merge hook
    python -m src.watcher.cli install --repo-path /path/to/repo --hook post-merge

    # Generate a GitHub Actions workflow file
    python -m src.watcher.cli generate --repo-path /path/to/repo --type github-actions
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from src.config.settings import LLMProvider, ServerConfig
from src.watcher.branch_docs import BranchDocGenerator
from src.watcher.watcher import BranchWatcher, GitHookInstaller


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Auto-update documentation when the main branch changes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── check: single-shot check and update ──
    check_parser = subparsers.add_parser(
        "check",
        help="Check for changes and update docs if needed (single-shot)",
    )
    _add_common_args(check_parser)

    # ── watch: polling daemon ──
    watch_parser = subparsers.add_parser(
        "watch",
        help="Start polling daemon that watches for branch changes",
    )
    _add_common_args(watch_parser)
    watch_parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Polling interval in minutes (default: 5)",
    )

    # ── install: git hook installer ──
    install_parser = subparsers.add_parser(
        "install",
        help="Install git hooks for automatic doc updates",
    )
    install_parser.add_argument(
        "--repo-path",
        default=".",
        help="Path to the repository",
    )
    install_parser.add_argument(
        "--hook",
        choices=["post-merge", "post-receive", "both"],
        default="post-merge",
        help="Which hook to install (default: post-merge)",
    )
    install_parser.add_argument(
        "--branch",
        default=None,
        help="Branch to watch (auto-detected if not specified)",
    )
    install_parser.add_argument(
        "--output",
        default="./docs/generated",
        help="Output directory for docs",
    )
    install_parser.add_argument(
        "--python-path",
        default="python3",
        help="Path to Python interpreter",
    )
    install_parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove previously installed hooks",
    )

    # ── branch-docs: generate docs for a working branch ──
    branch_parser = subparsers.add_parser(
        "branch-docs",
        help="Generate documentation for a specific working branch (with diff vs main)",
    )
    branch_parser.add_argument(
        "branch",
        help="Branch to document (e.g., 'feature/add-oauth')",
    )
    branch_parser.add_argument(
        "--base",
        default=None,
        help="Base branch to compare against (auto-detected if not specified)",
    )
    branch_parser.add_argument(
        "--repo-path",
        default=".",
        help="Path to the repository",
    )
    branch_parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish branch docs to Confluence/Google Docs",
    )
    branch_parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config file",
    )
    branch_parser.add_argument(
        "--provider",
        choices=["anthropic", "openai", "ollama", "bedrock"],
        default=None,
        help="LLM provider override",
    )
    branch_parser.add_argument(
        "--model",
        default=None,
        help="LLM model override",
    )

    # ── cleanup: remove branch docs after merge ──
    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help="Remove branch-specific documentation after merge/deletion",
    )
    cleanup_parser.add_argument(
        "branch",
        help="Branch whose docs to remove",
    )
    cleanup_parser.add_argument(
        "--repo-path",
        default=".",
        help="Path to the repository",
    )
    cleanup_parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config file",
    )

    # ── generate: CI/CD workflow generator ──
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate CI/CD workflow files",
    )
    gen_parser.add_argument(
        "--repo-path",
        default=".",
        help="Path to the repository",
    )
    gen_parser.add_argument(
        "--type",
        choices=["github-actions", "gitlab-ci"],
        default="github-actions",
        help="CI/CD platform (default: github-actions)",
    )
    gen_parser.add_argument(
        "--branch",
        default=None,
        help="Branch to watch",
    )
    gen_parser.add_argument(
        "--output",
        default="./docs/generated",
        help="Output directory for docs",
    )

    return parser


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments common to check and watch commands."""
    parser.add_argument(
        "--repo-path",
        default=".",
        help="Path to the repository (default: current directory)",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Branch to watch (auto-detected if not specified)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory for generated docs",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Auto-publish to Confluence/Google Docs after update",
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "openai", "ollama", "bedrock"],
        default=None,
        help="LLM provider override",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model override",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config file",
    )


async def run_check(args: argparse.Namespace) -> None:
    """Execute a single-shot check and update."""
    config = _build_config(args)

    print(f"\n🔍 Checking for changes on branch '{args.branch or 'auto-detect'}'...")
    print(f"   Repository: {Path(args.repo_path).resolve()}")

    watcher = BranchWatcher(
        config=config,
        repo_path=args.repo_path,
        branch=args.branch,
        output_dir=args.output,
    )

    result = await watcher.check_and_update()

    # Print result with appropriate formatting
    if result.strategy == "skip":
        print(f"\n✅ {result.message}")
    elif result.strategy == "error":
        print(f"\n❌ {result.message}")
        sys.exit(1)
    elif result.strategy == "cosmetic_update":
        print(f"\n📝 {result.message}")
    elif result.strategy == "targeted_update":
        print(f"\n🎯 {result.message}")
        print(f"   Files re-analyzed: {result.files_reanalyzed}")
        print(f"   Sections updated: {result.sections_updated}")
    elif result.strategy == "full_regeneration":
        print(f"\n📄 {result.message}")
        print(f"   Files analyzed: {result.files_reanalyzed}")

    if result.commit_messages:
        print(f"\n   Recent commits:")
        for msg in result.commit_messages[:5]:
            print(f"     • {msg}")


async def run_watch(args: argparse.Namespace) -> None:
    """Start the polling daemon."""
    config = _build_config(args)

    watcher = BranchWatcher(
        config=config,
        repo_path=args.repo_path,
        branch=args.branch,
        output_dir=args.output,
    )

    # Handle graceful shutdown on Ctrl+C
    loop = asyncio.get_event_loop()

    def shutdown_handler():
        print("\n🛑 Shutting down watcher...")
        watcher.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)

    print(f"👁️  Starting doc watcher (Ctrl+C to stop)")
    await watcher.start_polling(interval_minutes=args.interval)


def run_install(args: argparse.Namespace) -> None:
    """Install or uninstall git hooks."""
    installer = GitHookInstaller(
        repo_path=args.repo_path,
        python_path=args.python_path,
        branch=args.branch or "main",
        output_dir=args.output,
    )

    if args.uninstall:
        removed = installer.uninstall_hooks()
        if removed:
            print(f"🗑️  Removed hooks: {', '.join(removed)}")
        else:
            print("No repo-doc hooks found to remove.")
        return

    if args.hook in ("post-merge", "both"):
        path = installer.install_post_merge_hook()
        print(f"✅ Installed post-merge hook: {path}")

    if args.hook in ("post-receive", "both"):
        path = installer.install_post_receive_hook()
        print(f"✅ Installed post-receive hook: {path}")

    print(f"\nDocs will auto-update when you merge into '{args.branch or 'main'}'")


def run_generate(args: argparse.Namespace) -> None:
    """Generate CI/CD workflow files."""
    installer = GitHookInstaller(
        repo_path=args.repo_path,
        branch=args.branch or "main",
        output_dir=args.output,
    )

    if args.type == "github-actions":
        workflow = installer.generate_github_action()
        output_path = Path(args.repo_path) / ".github" / "workflows" / "update-docs.yml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(workflow)
        print(f"✅ Generated GitHub Actions workflow: {output_path}")
        print(f"\n⚠️  Don't forget to add ANTHROPIC_API_KEY to your repo secrets!")
    else:
        print(f"❌ GitLab CI support coming soon. Use 'github-actions' for now.")


async def run_branch_docs(args: argparse.Namespace) -> None:
    """Generate documentation for a specific working branch."""
    config = _build_config(args)

    if getattr(args, "publish", False):
        config.watcher.branch_docs.publish_branch_docs = True

    print(f"\n🌿 Generating branch docs: {args.branch}")
    print(f"   Base: {args.base or 'auto-detect'}")
    print(f"   Repository: {Path(args.repo_path).resolve()}")

    generator = BranchDocGenerator(config, args.repo_path)
    result = await generator.generate_branch_docs(args.branch, args.base)

    if result.success:
        print(f"\n✅ {result.message}")
        print(f"   Output: {result.output_dir}")
        print(f"   Change scope: {result.change_scope}")
        if result.confluence_url:
            print(f"   Confluence: {result.confluence_url}")
        if result.google_docs_url:
            print(f"   Google Docs: {result.google_docs_url}")
    else:
        print(f"\n❌ {result.message}")
        sys.exit(1)


async def run_cleanup(args: argparse.Namespace) -> None:
    """Remove branch-specific documentation."""
    config = ServerConfig.load(getattr(args, "config", None))
    generator = BranchDocGenerator(config, args.repo_path)
    removed = await generator.cleanup_branch_docs(args.branch)

    if removed:
        print(f"🗑️  Removed docs for branch: {args.branch}")
    else:
        print(f"No docs found for branch: {args.branch}")


def _build_config(args: argparse.Namespace) -> ServerConfig:
    """Build a ServerConfig from CLI arguments."""
    config = ServerConfig.load(getattr(args, "config", None))

    if getattr(args, "provider", None):
        config.llm.provider = LLMProvider(args.provider)
    if getattr(args, "model", None):
        config.llm.model = args.model
    if getattr(args, "publish", False):
        config.watcher.publish_after_update = True

    return config


def main():
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "check":
        asyncio.run(run_check(args))
    elif args.command == "watch":
        asyncio.run(run_watch(args))
    elif args.command == "install":
        run_install(args)
    elif args.command == "generate":
        run_generate(args)
    elif args.command == "branch-docs":
        asyncio.run(run_branch_docs(args))
    elif args.command == "cleanup":
        asyncio.run(run_cleanup(args))


if __name__ == "__main__":
    main()
