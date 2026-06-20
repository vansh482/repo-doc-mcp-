"""
MCP Server for Repository Documentation Generation.

This is the main entry point — it exposes our documentation pipeline as MCP tools
that can be called by any MCP client (VS Code extensions, IntelliJ plugins,
Claude Desktop, etc.)

The server exposes these tools:

    ┌─────────────────────────────────────────────────────────────────┐
    │  MCP Tools                                                       │
    │                                                                  │
    │  generate_docs(repo_path)                                        │
    │    → Scans repo, analyzes code, generates both doc types         │
    │    → Returns paths to generated markdown files                   │
    │                                                                  │
    │  generate_technical_doc(repo_path)                                │
    │    → Generates only the technical documentation                   │
    │                                                                  │
    │  generate_non_technical_doc(repo_path)                           │
    │    → Generates only the non-technical documentation              │
    │                                                                  │
    │  get_repo_summary(repo_path)                                     │
    │    → Quick scan + summary without full doc generation            │
    │                                                                  │
    │  list_configs()                                                  │
    │    → Shows current configuration                                 │
    │                                                                  │
    │  update_config(key, value)                                       │
    │    → Dynamically update configuration                            │
    └─────────────────────────────────────────────────────────────────┘

How MCP works (simplified):
- The server runs as a subprocess, communicating over stdin/stdout using JSON-RPC
- The IDE extension (or Claude Desktop) is the MCP "client"
- The client discovers available tools, then calls them as needed
- The server processes the request and streams back results
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.config.settings import DocConfig, LLMConfig, LLMProvider, ServerConfig
from src.generators.doc_generator import DocGenerator
from src.llm.providers import BaseLLMProvider, create_llm_provider
from src.parsers.analyzer import CodeAnalyzer
from src.parsers.scanner import RepoScanner
from src.watcher.git_diff import GitDiffEngine
from src.watcher.incremental import IncrementalUpdater
from src.watcher.branch_docs import BranchDocGenerator
from src.watcher.watcher import BranchWatcher, GitHookInstaller
from src.mr_docs.mr_analyzer import MRDiffAnalyzer
from src.mr_docs.mr_generator import MRDocGenerator, save_mr_docs


# ──────────────────────────────────────────────────────────────────────
# Server Setup
# ──────────────────────────────────────────────────────────────────────

# Load configuration at startup
config = ServerConfig.load()

# Create the MCP server instance
server = Server(config.server_name)


def get_llm_provider() -> BaseLLMProvider:
    """Create an LLM provider from current config.
    We recreate this each time to pick up config changes."""
    return create_llm_provider(config.llm)


# ──────────────────────────────────────────────────────────────────────
# Tool Definitions — these tell MCP clients what tools are available
# ──────────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Declare all available tools to the MCP client.

    Each tool has:
    - A name (used to call it)
    - A description (shown to users in the IDE)
    - An input schema (JSON Schema defining the parameters)
    """
    return [
        Tool(
            name="generate_docs",
            description=(
                "Generate comprehensive documentation for a code repository. "
                "Produces TWO documents: a detailed technical doc for engineers "
                "and a simplified guide for non-technical team members. "
                "Both documents are saved as Markdown files."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": (
                            "Absolute path to the repository root directory. "
                            "If not provided, uses the current working directory."
                        ),
                    },
                    "output_dir": {
                        "type": "string",
                        "description": (
                            "Directory where generated docs will be saved. "
                            "Defaults to ./docs/generated in the repo."
                        ),
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="generate_technical_doc",
            description=(
                "Generate ONLY the technical documentation for engineers. "
                "Includes architecture details, API references, data flow, "
                "and setup instructions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="generate_non_technical_doc",
            description=(
                "Generate ONLY the non-technical guide for PMs, designers, "
                "and stakeholders. Uses plain language, analogies, and no jargon."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_repo_summary",
            description=(
                "Quick repository scan — returns a summary of the codebase structure, "
                "languages, file count, and detected tech stack WITHOUT generating "
                "full documentation. Useful for a quick overview."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="list_config",
            description="Show the current server configuration including LLM provider and doc settings.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="update_config",
            description=(
                "Update a configuration setting. Supports changing the LLM provider, "
                "model, output format, and other settings."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": (
                            "Config key to update. Use dot notation for nested keys. "
                            "Examples: 'llm.provider', 'llm.model', 'llm.api_key', "
                            "'doc.output_format', 'repo.max_files'"
                        ),
                    },
                    "value": {
                        "type": "string",
                        "description": "New value for the config key.",
                    },
                },
                "required": ["key", "value"],
            },
        ),
        Tool(
            name="check_and_update_docs",
            description=(
                "Check if the main branch has new commits since docs were last generated. "
                "If changes are detected, incrementally updates the documentation — "
                "only re-analyzing changed files instead of regenerating everything. "
                "Uses three strategies: full regeneration for structural changes, "
                "targeted updates for content changes, and metadata-only updates for cosmetic changes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                    "branch": {
                        "type": "string",
                        "description": "Branch to check for updates (auto-detected if omitted).",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="install_git_hooks",
            description=(
                "Install git hooks that automatically update documentation when "
                "changes are merged into the main branch. Supports post-merge hooks "
                "(for local development) and post-receive hooks (for git servers)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                    "hook_type": {
                        "type": "string",
                        "enum": ["post-merge", "post-receive", "both"],
                        "description": "Which hook to install (default: post-merge).",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="generate_ci_workflow",
            description=(
                "Generate a CI/CD workflow file (e.g., GitHub Actions) that "
                "automatically updates documentation when commits are pushed to main. "
                "This is the production-grade approach for teams."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["github-actions"],
                        "description": "CI/CD platform (default: github-actions).",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="generate_mr_docs",
            description=(
                "Generate documentation for a specific Merge Request (MR) or Pull Request (PR). "
                "Produces TWO documents: a technical review doc for engineers (with diffs, risk "
                "assessment, and deployment notes) and a non-technical summary for stakeholders "
                "(plain English explanation of what changed and why it matters). "
                "Specify the source branch (the MR branch) and target branch (usually main)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                    "source_branch": {
                        "type": "string",
                        "description": (
                            "The MR/PR source branch (e.g., 'feature/add-oauth'). "
                            "This is the branch with the new changes."
                        ),
                    },
                    "target_branch": {
                        "type": "string",
                        "description": (
                            "The branch being merged into (default: 'main'). "
                            "Usually 'main', 'master', or 'develop'."
                        ),
                    },
                    "mr_title": {
                        "type": "string",
                        "description": "Title of the MR/PR (auto-generated from branch name if omitted).",
                    },
                    "mr_description": {
                        "type": "string",
                        "description": "Description of the MR/PR (from the MR body text).",
                    },
                    "author": {
                        "type": "string",
                        "description": "Author of the MR/PR.",
                    },
                },
                "required": ["source_branch"],
            },
        ),
        Tool(
            name="generate_branch_docs",
            description=(
                "Generate documentation for a specific working branch, including a "
                "'What Changed vs Main' section showing the diff. Saves to a branch-namespaced "
                "directory (e.g., docs/generated/feature-add-oauth/). Optionally publishes "
                "to a separate Confluence page."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                    "branch": {
                        "type": "string",
                        "description": "The working branch to document (e.g., 'feature/add-oauth').",
                    },
                    "base_branch": {
                        "type": "string",
                        "description": "Base branch to compare against (default: auto-detected main).",
                    },
                },
                "required": ["branch"],
            },
        ),
        Tool(
            name="generate_mr_docs_from_commits",
            description=(
                "Generate MR documentation using specific commit hashes instead of branch names. "
                "Useful for documenting already-merged MRs or comparing any two points in history."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                    "from_commit": {
                        "type": "string",
                        "description": "The starting commit hash (before the MR changes).",
                    },
                    "to_commit": {
                        "type": "string",
                        "description": "The ending commit hash (after the MR changes).",
                    },
                    "mr_title": {
                        "type": "string",
                        "description": "Title for the MR document.",
                    },
                    "mr_description": {
                        "type": "string",
                        "description": "Description of what this MR does.",
                    },
                },
                "required": ["from_commit", "to_commit"],
            },
        ),
    ]


# ──────────────────────────────────────────────────────────────────────
# Tool Implementations — the actual logic behind each tool
# ──────────────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route tool calls to their implementations.

    This is the MCP dispatcher — when a client calls a tool by name,
    this function routes it to the correct handler.
    """
    handlers = {
        "generate_docs": handle_generate_docs,
        "generate_technical_doc": handle_generate_technical_doc,
        "generate_non_technical_doc": handle_generate_non_technical_doc,
        "get_repo_summary": handle_get_repo_summary,
        "list_config": handle_list_config,
        "update_config": handle_update_config,
        "check_and_update_docs": handle_check_and_update,
        "install_git_hooks": handle_install_git_hooks,
        "generate_ci_workflow": handle_generate_ci_workflow,
        "generate_branch_docs": handle_generate_branch_docs,
        "generate_mr_docs": handle_generate_mr_docs,
        "generate_mr_docs_from_commits": handle_generate_mr_docs_from_commits,
    }

    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    try:
        result = await handler(arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        error_msg = f"Error executing {name}: {type(e).__name__}: {str(e)}"
        return [TextContent(type="text", text=error_msg)]


async def handle_generate_docs(args: dict) -> str:
    """Generate both technical and non-technical documentation.

    This is the primary tool — it runs the full pipeline:
    scan → analyze → generate docs → save files
    """
    repo_path = args.get("repo_path", os.getcwd())
    output_dir = args.get("output_dir", None)

    # Step 1: Scan the repository
    scanner = RepoScanner(config.repo)
    repo_tree = scanner.scan(repo_path)

    # Step 2: Analyze the codebase
    llm = get_llm_provider()
    analyzer = CodeAnalyzer(llm)
    analysis = await analyzer.analyze(repo_tree)

    # Step 3: Generate documentation
    doc_config = config.doc
    if output_dir:
        doc_config = DocConfig(**{**doc_config.model_dump(), "output_dir": output_dir})

    generator = DocGenerator(llm, doc_config)
    tech_doc, simple_doc = await generator.generate(analysis)

    # Step 4: Save the generated docs
    out_dir = Path(output_dir or doc_config.output_dir)
    if not out_dir.is_absolute():
        out_dir = Path(repo_path) / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    tech_path = out_dir / "TECHNICAL_DOC.md"
    simple_path = out_dir / "NON_TECHNICAL_GUIDE.md"

    tech_path.write_text(tech_doc.to_markdown(), encoding="utf-8")
    simple_path.write_text(simple_doc.to_markdown(), encoding="utf-8")

    return (
        f"Documentation generated successfully!\n\n"
        f"Repository: {repo_tree.name}\n"
        f"Branch: {repo_tree.branch or 'N/A'}\n"
        f"Files analyzed: {repo_tree.total_files}\n"
        f"Lines of code: {repo_tree.total_lines}\n"
        f"Languages: {', '.join(repo_tree.languages.keys())}\n\n"
        f"Generated files:\n"
        f"  📄 Technical Doc: {tech_path}\n"
        f"  📄 Non-Technical Guide: {simple_path}\n"
    )


async def handle_generate_technical_doc(args: dict) -> str:
    """Generate only the technical documentation."""
    repo_path = args.get("repo_path", os.getcwd())

    scanner = RepoScanner(config.repo)
    repo_tree = scanner.scan(repo_path)

    llm = get_llm_provider()
    analyzer = CodeAnalyzer(llm)
    analysis = await analyzer.analyze(repo_tree)

    generator = DocGenerator(llm, config.doc)
    tech_doc, _ = await generator.generate(analysis)

    out_dir = Path(repo_path) / config.doc.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    tech_path = out_dir / "TECHNICAL_DOC.md"
    tech_path.write_text(tech_doc.to_markdown(), encoding="utf-8")

    return f"Technical documentation saved to: {tech_path}"


async def handle_generate_non_technical_doc(args: dict) -> str:
    """Generate only the non-technical documentation."""
    repo_path = args.get("repo_path", os.getcwd())

    scanner = RepoScanner(config.repo)
    repo_tree = scanner.scan(repo_path)

    llm = get_llm_provider()
    analyzer = CodeAnalyzer(llm)
    analysis = await analyzer.analyze(repo_tree)

    generator = DocGenerator(llm, config.doc)
    _, simple_doc = await generator.generate(analysis)

    out_dir = Path(repo_path) / config.doc.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    simple_path = out_dir / "NON_TECHNICAL_GUIDE.md"
    simple_path.write_text(simple_doc.to_markdown(), encoding="utf-8")

    return f"Non-technical guide saved to: {simple_path}"


async def handle_get_repo_summary(args: dict) -> str:
    """Quick repo scan — returns structure overview without full doc generation."""
    repo_path = args.get("repo_path", os.getcwd())

    scanner = RepoScanner(config.repo)
    repo_tree = scanner.scan(repo_path)

    # Build a quick summary without LLM calls
    lang_info = "\n".join(
        f"  - {lang}: {count} files"
        for lang, count in repo_tree.languages.items()
    )

    # Count files by type
    type_counts: dict[str, int] = {}
    for f in repo_tree.files:
        type_counts[f.file_type.value] = type_counts.get(f.file_type.value, 0) + 1

    type_info = "\n".join(
        f"  - {ftype}: {count} files"
        for ftype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
    )

    return (
        f"Repository Summary: {repo_tree.name}\n"
        f"{'=' * 50}\n\n"
        f"Branch: {repo_tree.branch or 'N/A'}\n"
        f"Commit: {(repo_tree.commit_hash or 'N/A')[:8]}\n"
        f"Total Files: {repo_tree.total_files}\n"
        f"Total Lines: {repo_tree.total_lines}\n\n"
        f"Languages:\n{lang_info}\n\n"
        f"File Types:\n{type_info}\n"
    )


async def handle_list_config(args: dict) -> str:
    """Show current configuration."""
    return (
        f"Current Configuration\n"
        f"{'=' * 50}\n\n"
        f"LLM Provider: {config.llm.provider.value}\n"
        f"LLM Model: {config.llm.model}\n"
        f"LLM Base URL: {config.llm.base_url or 'default'}\n"
        f"Max Tokens: {config.llm.max_tokens}\n"
        f"Temperature: {config.llm.temperature}\n\n"
        f"Output Dir: {config.doc.output_dir}\n"
        f"Output Format: {config.doc.output_format}\n"
        f"Include Diagrams: {config.doc.include_architecture_diagram}\n"
        f"Include Glossary: {config.doc.include_glossary}\n\n"
        f"Max Files: {config.repo.max_files}\n"
        f"Max File Size: {config.repo.max_file_size_kb}KB\n"
        f"Ignore Patterns: {len(config.repo.ignore_patterns)} patterns\n"
    )


async def handle_update_config(args: dict) -> str:
    """Update a configuration value dynamically."""
    global config
    key = args["key"]
    value = args["value"]

    try:
        parts = key.split(".")
        if len(parts) == 2:
            section, field = parts

            if section == "llm":
                current = config.llm.model_dump()
                if field == "provider":
                    current[field] = LLMProvider(value)
                elif field in {"max_tokens"}:
                    current[field] = int(value)
                elif field in {"temperature"}:
                    current[field] = float(value)
                else:
                    current[field] = value
                config.llm = LLMConfig(**current)

            elif section == "doc":
                current = config.doc.model_dump()
                if field in {"include_architecture_diagram", "include_glossary"}:
                    current[field] = value.lower() in {"true", "1", "yes"}
                elif field == "tree_depth":
                    current[field] = int(value)
                else:
                    current[field] = value
                config.doc = DocConfig(**current)

            elif section == "repo":
                current = config.repo.model_dump()
                if field in {"max_file_size_kb", "max_files"}:
                    current[field] = int(value)
                else:
                    current[field] = value
                config.repo = config.repo.__class__(**current)

            else:
                return f"Unknown config section: {section}"

            return f"Updated {key} = {value}"
        else:
            return f"Invalid key format. Use 'section.field' (e.g., 'llm.model')"

    except Exception as e:
        return f"Failed to update config: {e}"


# ──────────────────────────────────────────────────────────────────────
# Phase 3: Auto-Update Tool Handlers
# ──────────────────────────────────────────────────────────────────────

async def handle_check_and_update(args: dict) -> str:
    """Check for changes on the main branch and incrementally update docs.

    This is the key Phase 3 tool. It:
    1. Checks if new commits exist on main since the last doc generation
    2. Classifies the changes (structural, content, or cosmetic)
    3. Applies the appropriate update strategy (full regen, targeted, or metadata-only)
    4. Returns a summary of what was done
    """
    repo_path = args.get("repo_path", os.getcwd())
    branch = args.get("branch", None)

    watcher = BranchWatcher(
        config=config,
        repo_path=repo_path,
        branch=branch,
    )

    result = await watcher.check_and_update()

    # Format the result as a readable string
    lines = [
        f"Auto-Update Result",
        f"{'=' * 50}",
        f"Strategy: {result.strategy}",
        f"Message: {result.message}",
    ]

    if result.files_reanalyzed > 0:
        lines.append(f"Files re-analyzed: {result.files_reanalyzed}")
    if result.sections_updated > 0:
        lines.append(f"Doc sections updated: {result.sections_updated}")
    if result.commit_messages:
        lines.append(f"\nRecent commits:")
        for msg in result.commit_messages[:10]:
            lines.append(f"  • {msg}")

    return "\n".join(lines)


async def handle_install_git_hooks(args: dict) -> str:
    """Install git hooks for automatic doc updates on merge."""
    repo_path = args.get("repo_path", os.getcwd())
    hook_type = args.get("hook_type", "post-merge")

    installer = GitHookInstaller(
        repo_path=repo_path,
        branch=config.llm.provider.value,  # Will be overridden by auto-detect
    )

    # Detect the main branch for the hook
    try:
        git = GitDiffEngine(repo_path)
        branch = git.detect_main_branch()
    except Exception:
        branch = "main"

    installer = GitHookInstaller(
        repo_path=repo_path,
        branch=branch,
        output_dir=config.doc.output_dir,
    )

    results = []
    if hook_type in ("post-merge", "both"):
        path = installer.install_post_merge_hook()
        results.append(f"✅ Installed post-merge hook: {path}")

    if hook_type in ("post-receive", "both"):
        path = installer.install_post_receive_hook()
        results.append(f"✅ Installed post-receive hook: {path}")

    results.append(
        f"\nDocs will auto-update when changes are merged into '{branch}'."
    )
    results.append(
        "The hook runs in the background so it won't slow down your git operations."
    )

    return "\n".join(results)


async def handle_generate_ci_workflow(args: dict) -> str:
    """Generate a CI/CD workflow file for automatic doc updates."""
    repo_path = args.get("repo_path", os.getcwd())
    platform = args.get("platform", "github-actions")

    try:
        git = GitDiffEngine(repo_path)
        branch = git.detect_main_branch()
    except Exception:
        branch = "main"

    installer = GitHookInstaller(
        repo_path=repo_path,
        branch=branch,
        output_dir=config.doc.output_dir,
    )

    if platform == "github-actions":
        workflow = installer.generate_github_action()
        output_path = Path(repo_path) / ".github" / "workflows" / "update-docs.yml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(workflow)

        return (
            f"Generated GitHub Actions workflow: {output_path}\n\n"
            f"This workflow will automatically update docs when commits "
            f"are pushed to '{branch}'.\n\n"
            f"⚠️  Add your LLM API key as a repository secret:\n"
            f"  Settings → Secrets → ANTHROPIC_API_KEY"
        )
    else:
        return f"Platform '{platform}' is not yet supported. Use 'github-actions'."


async def handle_generate_branch_docs(args: dict) -> str:
    """Generate docs for a working branch with diff vs main."""
    repo_path = args.get("repo_path", os.getcwd())
    branch = args["branch"]
    base_branch = args.get("base_branch", None)

    generator = BranchDocGenerator(config, repo_path)
    result = await generator.generate_branch_docs(branch, base_branch)

    if result.success:
        lines = [
            f"Branch Documentation Generated!",
            f"{'=' * 50}",
            f"",
            f"Branch: {result.branch} (vs {result.base_branch})",
            f"Files changed: {result.files_changed}",
            f"Change scope: {result.change_scope}",
            f"Output: {result.output_dir}",
        ]
        if result.confluence_url:
            lines.append(f"Confluence: {result.confluence_url}")
        if result.google_docs_url:
            lines.append(f"Google Docs: {result.google_docs_url}")
        return "\n".join(lines)
    else:
        return f"Branch docs failed: {result.message}"


# ──────────────────────────────────────────────────────────────────────
# Phase 4: Per-MR Documentation Tool Handlers
# ──────────────────────────────────────────────────────────────────────

async def handle_generate_mr_docs(args: dict) -> str:
    """Generate documentation for a merge request using branch names.

    This analyzes the diff between a source branch (the MR branch) and a
    target branch (usually main), then generates both technical review
    and non-technical summary documents.
    """
    repo_path = args.get("repo_path", os.getcwd())
    source_branch = args["source_branch"]
    target_branch = args.get("target_branch", "main")
    mr_title = args.get("mr_title", "")
    mr_description = args.get("mr_description", "")
    author = args.get("author", "")

    # Step 1: Analyze the MR diff
    analyzer = MRDiffAnalyzer(repo_path)
    analysis = analyzer.analyze(
        source_branch=source_branch,
        target_branch=target_branch,
        mr_title=mr_title,
        mr_description=mr_description,
        author=author,
    )

    # Step 2: Generate both documents
    llm = get_llm_provider()
    generator = MRDocGenerator(llm)
    tech_doc, simple_doc = await generator.generate(analysis)

    # Step 3: Save to disk
    output_dir = Path(repo_path) / config.doc.output_dir / "mr_docs"
    tech_path, simple_path = save_mr_docs(
        tech_doc, simple_doc, output_dir, source_branch,
    )

    # Build response with analysis summary
    flags = []
    if analysis.has_breaking_changes:
        flags.append("⚠️  BREAKING CHANGES DETECTED")
    if analysis.has_migration:
        flags.append("🗄️  Database migration included")
    if analysis.has_new_dependencies:
        flags.append("📦 New dependencies added")
    if analysis.has_config_changes:
        flags.append("⚙️  Configuration changes")

    groups_summary = "\n".join(
        f"  • {g.name}: {len(g.files)} files"
        for g in analysis.change_groups
    )

    return (
        f"MR Documentation Generated!\n"
        f"{'=' * 50}\n\n"
        f"MR: {analysis.mr_title}\n"
        f"Branch: {source_branch} → {target_branch}\n"
        f"Nature: {analysis.change_nature.value.replace('_', ' ').title()}\n"
        f"Risk: {analysis.risk_level.value.upper()}\n"
        f"Files changed: {analysis.total_files_changed}\n\n"
        f"Change Areas:\n{groups_summary}\n\n"
        + ("\n".join(flags) + "\n\n" if flags else "")
        + f"Generated Files:\n"
        f"  📄 Technical Review: {tech_path}\n"
        f"  📄 Stakeholder Summary: {simple_path}\n"
    )


async def handle_generate_mr_docs_from_commits(args: dict) -> str:
    """Generate MR documentation using explicit commit hashes.

    Useful for documenting already-merged MRs or comparing any two
    points in the git history.
    """
    repo_path = args.get("repo_path", os.getcwd())
    from_commit = args["from_commit"]
    to_commit = args["to_commit"]
    mr_title = args.get("mr_title", "")
    mr_description = args.get("mr_description", "")

    # Analyze the diff between commits
    analyzer = MRDiffAnalyzer(repo_path)
    analysis = analyzer.analyze_from_diff(
        from_commit=from_commit,
        to_commit=to_commit,
        mr_title=mr_title,
        mr_description=mr_description,
    )

    # Generate documents
    llm = get_llm_provider()
    generator = MRDocGenerator(llm)
    tech_doc, simple_doc = await generator.generate(analysis)

    # Save to disk
    output_dir = Path(repo_path) / config.doc.output_dir / "mr_docs"
    commit_label = f"{from_commit[:8]}_to_{to_commit[:8]}"
    tech_path, simple_path = save_mr_docs(
        tech_doc, simple_doc, output_dir, commit_label,
    )

    return (
        f"MR Documentation Generated (from commits)!\n"
        f"{'=' * 50}\n\n"
        f"Range: {from_commit[:8]} → {to_commit[:8]}\n"
        f"Title: {analysis.mr_title}\n"
        f"Nature: {analysis.change_nature.value.replace('_', ' ').title()}\n"
        f"Risk: {analysis.risk_level.value.upper()}\n"
        f"Files changed: {analysis.total_files_changed}\n\n"
        f"Generated Files:\n"
        f"  📄 Technical Review: {tech_path}\n"
        f"  📄 Stakeholder Summary: {simple_path}\n"
    )


# ──────────────────────────────────────────────────────────────────────
# Server Entry Point
# ──────────────────────────────────────────────────────────────────────

def main():
    """Start the MCP server.

    The server communicates over stdin/stdout using the MCP protocol (JSON-RPC).
    This is the standard way MCP servers work — the IDE extension spawns this
    process and talks to it via stdin/stdout.
    """
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
