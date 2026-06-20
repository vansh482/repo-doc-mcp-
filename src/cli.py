"""
CLI Tool for Repo Doc MCP Server — standalone testing without an MCP client.

This lets you test the full documentation pipeline from the command line:

    python -m src.cli /path/to/your/repo

It runs the exact same pipeline as the MCP server tools, just triggered
from the terminal instead of from an IDE extension.

This is useful for:
- Testing during development of this tool
- One-off doc generation without setting up MCP
- CI/CD pipelines that auto-generate docs on merge
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from src.config.settings import LLMConfig, LLMProvider, ServerConfig
from src.generators.doc_generator import DocGenerator
from src.llm.providers import create_llm_provider
from src.parsers.analyzer import CodeAnalyzer
from src.parsers.scanner import RepoScanner


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate documentation for a code repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate both docs using default config (Anthropic Claude)
  python -m src.cli /path/to/repo

  # Generate using OpenAI GPT-4o
  python -m src.cli /path/to/repo --provider openai --model gpt-4o

  # Generate using local Ollama
  python -m src.cli /path/to/repo --provider ollama --model llama3.1

  # Only generate non-technical doc
  python -m src.cli /path/to/repo --type non-technical

  # Quick repo summary (no LLM calls)
  python -m src.cli /path/to/repo --summary-only

  # Custom output directory
  python -m src.cli /path/to/repo --output ./my-docs
        """,
    )

    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Path to the repository root (default: current directory)",
    )
    parser.add_argument(
        "--provider", "-p",
        choices=["anthropic", "openai", "ollama", "bedrock"],
        default=None,
        help="LLM provider to use (overrides config file)",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        help="LLM model name (overrides config file)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key for the LLM provider (overrides env var)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base URL for Ollama or custom endpoints",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory for generated docs",
    )
    parser.add_argument(
        "--type", "-t",
        choices=["both", "technical", "non-technical"],
        default="both",
        help="Which documentation to generate (default: both)",
    )
    parser.add_argument(
        "--summary-only", "-s",
        action="store_true",
        help="Only show repo summary, skip doc generation (no LLM calls)",
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to YAML config file",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress output",
    )

    return parser


async def run_pipeline(args: argparse.Namespace) -> None:
    """Execute the documentation pipeline based on CLI arguments."""

    # ── Load config ──
    config = ServerConfig.load(args.config)

    # Override config with CLI arguments if provided
    if args.provider:
        config.llm.provider = LLMProvider(args.provider)
    if args.model:
        config.llm.model = args.model
    if args.api_key:
        config.llm.api_key = args.api_key
    if args.base_url:
        config.llm.base_url = args.base_url

    repo_path = Path(args.repo_path).resolve()
    if not repo_path.is_dir():
        print(f"Error: '{repo_path}' is not a valid directory")
        sys.exit(1)

    # ── Step 1: Scan ──
    print(f"\n📂 Scanning repository: {repo_path}")
    start = time.time()

    scanner = RepoScanner(config.repo)
    repo_tree = scanner.scan(str(repo_path))

    scan_time = time.time() - start
    print(f"   Found {repo_tree.total_files} files, {repo_tree.total_lines} lines")
    print(f"   Languages: {', '.join(repo_tree.languages.keys())}")
    print(f"   Branch: {repo_tree.branch or 'N/A'}")
    print(f"   Scan time: {scan_time:.1f}s")

    # If summary-only, print and exit
    if args.summary_only:
        print(f"\n{'=' * 60}")
        print(f"Repository Summary: {repo_tree.name}")
        print(f"{'=' * 60}")
        print(f"Branch: {repo_tree.branch or 'N/A'}")
        print(f"Commit: {(repo_tree.commit_hash or 'N/A')[:8]}")
        print(f"Total Files: {repo_tree.total_files}")
        print(f"Total Lines: {repo_tree.total_lines}")
        print(f"\nLanguages:")
        for lang, count in repo_tree.languages.items():
            print(f"  {lang}: {count} files")
        print(f"\nFile Types:")
        type_counts: dict[str, int] = {}
        for f in repo_tree.files:
            type_counts[f.file_type.value] = type_counts.get(f.file_type.value, 0) + 1
        for ftype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {ftype}: {count} files")
        return

    # ── Step 2: Analyze ──
    print(f"\n🔍 Analyzing codebase with {config.llm.provider.value} ({config.llm.model})...")
    start = time.time()

    llm = create_llm_provider(config.llm)
    analyzer = CodeAnalyzer(llm)
    analysis = await analyzer.analyze(repo_tree)

    analyze_time = time.time() - start
    print(f"   Project purpose: {(analysis.project_purpose or 'N/A')[:100]}...")
    print(f"   Key components: {', '.join(analysis.key_components[:5])}")
    print(f"   Analysis time: {analyze_time:.1f}s")

    # ── Step 3: Generate Docs ──
    print(f"\n📝 Generating documentation...")
    start = time.time()

    generator = DocGenerator(llm, config.doc)

    # Determine output directory
    output_dir = Path(args.output) if args.output else Path(str(repo_path)) / config.doc.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.type in ("both", "technical"):
        tech_doc, simple_doc = await generator.generate(analysis)

        if args.type == "both" or args.type == "technical":
            tech_path = output_dir / "TECHNICAL_DOC.md"
            tech_path.write_text(tech_doc.to_markdown(), encoding="utf-8")
            print(f"   ✅ Technical doc: {tech_path}")

        if args.type == "both" or args.type == "non-technical":
            simple_path = output_dir / "NON_TECHNICAL_GUIDE.md"
            simple_path.write_text(simple_doc.to_markdown(), encoding="utf-8")
            print(f"   ✅ Non-technical guide: {simple_path}")

    elif args.type == "non-technical":
        _, simple_doc = await generator.generate(analysis)
        simple_path = output_dir / "NON_TECHNICAL_GUIDE.md"
        simple_path.write_text(simple_doc.to_markdown(), encoding="utf-8")
        print(f"   ✅ Non-technical guide: {simple_path}")

    gen_time = time.time() - start
    print(f"   Generation time: {gen_time:.1f}s")

    total_time = scan_time + analyze_time + gen_time
    print(f"\n🎉 Done! Total time: {total_time:.1f}s")


def main():
    parser = create_parser()
    args = parser.parse_args()
    asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    main()
