"""
MR Documentation CLI — command-line interface for per-MR doc generation.

Usage examples:

    # Generate docs for a feature branch (compared to main)
    python -m src.mr_docs.cli feature/add-oauth

    # Specify the target branch explicitly
    python -m src.mr_docs.cli feature/add-oauth --target develop

    # Add MR metadata for richer docs
    python -m src.mr_docs.cli feature/add-oauth \\
        --title "Add OAuth2 Authentication" \\
        --description "Implements Google and GitHub OAuth login" \\
        --author "Jane Smith"

    # Generate from commit hashes (for already-merged MRs)
    python -m src.mr_docs.cli --from-commit abc1234 --to-commit def5678

    # Only generate the technical review
    python -m src.mr_docs.cli feature/add-oauth --type technical

    # Custom output directory
    python -m src.mr_docs.cli feature/add-oauth --output ./reviews
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from src.config.settings import LLMProvider, ServerConfig
from src.llm.providers import create_llm_provider
from src.mr_docs.mr_analyzer import MRDiffAnalyzer, RiskLevel
from src.mr_docs.mr_generator import MRDocGenerator, save_mr_docs


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate documentation for a Merge Request / Pull Request",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Document a feature branch vs main
  python -m src.mr_docs.cli feature/add-oauth

  # Document with full metadata
  python -m src.mr_docs.cli feature/add-oauth \\
      --title "Add OAuth2 Authentication" \\
      --author "Jane Smith"

  # Document using commit hashes
  python -m src.mr_docs.cli --from-commit abc1234 --to-commit def5678

  # Quick analysis without generating full docs
  python -m src.mr_docs.cli feature/add-oauth --analyze-only
        """,
    )

    # Branch-based mode (default)
    parser.add_argument(
        "source_branch",
        nargs="?",
        default=None,
        help="Source branch (the MR/PR branch, e.g., 'feature/add-oauth')",
    )
    parser.add_argument(
        "--target", "-t",
        default="main",
        help="Target branch to compare against (default: main)",
    )

    # Commit-based mode
    parser.add_argument(
        "--from-commit",
        default=None,
        help="Start commit hash (alternative to branch mode)",
    )
    parser.add_argument(
        "--to-commit",
        default=None,
        help="End commit hash (alternative to branch mode)",
    )

    # MR metadata
    parser.add_argument(
        "--title",
        default="",
        help="MR/PR title (auto-generated from branch name if omitted)",
    )
    parser.add_argument(
        "--description", "-d",
        default="",
        help="MR/PR description text",
    )
    parser.add_argument(
        "--author", "-a",
        default="",
        help="MR/PR author name",
    )

    # Output options
    parser.add_argument(
        "--repo-path",
        default=".",
        help="Repository path (default: current directory)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory for generated docs",
    )
    parser.add_argument(
        "--type",
        choices=["both", "technical", "non-technical"],
        default="both",
        help="Which doc type to generate (default: both)",
    )

    # LLM options
    parser.add_argument(
        "--provider", "-p",
        choices=["anthropic", "openai", "ollama"],
        default=None,
        help="LLM provider override",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        help="LLM model override",
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to config file",
    )

    # Analysis-only mode
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Only analyze the MR diff, don't generate docs (no LLM calls)",
    )

    return parser


async def run(args: argparse.Namespace) -> None:
    """Execute MR documentation generation."""
    
    # Validate arguments
    if not args.source_branch and not (args.from_commit and args.to_commit):
        print("Error: Provide either a source_branch or both --from-commit and --to-commit")
        sys.exit(1)

    repo_path = Path(args.repo_path).resolve()
    if not repo_path.is_dir():
        print(f"Error: '{repo_path}' is not a valid directory")
        sys.exit(1)

    # Load config
    config = ServerConfig.load(args.config)
    if args.provider:
        config.llm.provider = LLMProvider(args.provider)
    if args.model:
        config.llm.model = args.model

    # ── Step 1: Analyze the MR diff ──
    print(f"\n🔍 Analyzing merge request...")
    start = time.time()

    analyzer = MRDiffAnalyzer(str(repo_path))

    if args.source_branch:
        print(f"   Branch: {args.source_branch} → {args.target}")
        analysis = analyzer.analyze(
            source_branch=args.source_branch,
            target_branch=args.target,
            mr_title=args.title,
            mr_description=args.description,
            author=args.author,
        )
    else:
        print(f"   Commits: {args.from_commit[:8]} → {args.to_commit[:8]}")
        analysis = analyzer.analyze_from_diff(
            from_commit=args.from_commit,
            to_commit=args.to_commit,
            mr_title=args.title,
            mr_description=args.description,
        )

    analyze_time = time.time() - start

    # Print analysis summary
    risk_icon = {
        RiskLevel.LOW: "🟢", RiskLevel.MEDIUM: "🟡",
        RiskLevel.HIGH: "🟠", RiskLevel.CRITICAL: "🔴",
    }.get(analysis.risk_level, "")

    print(f"\n   MR: {analysis.mr_title}")
    print(f"   Nature: {analysis.change_nature.value.replace('_', ' ').title()}")
    print(f"   Risk: {risk_icon} {analysis.risk_level.value.upper()}")
    print(f"   Files changed: {analysis.total_files_changed}")
    print(f"   Change areas:")
    for group in analysis.change_groups:
        print(f"     • {group.name}: {len(group.files)} files")

    # Print flags
    if analysis.has_breaking_changes:
        print(f"   ⚠️  BREAKING CHANGES DETECTED")
    if analysis.has_migration:
        print(f"   🗄️  Database migration included")
    if analysis.has_new_dependencies:
        print(f"   📦 New dependencies added")
    if analysis.has_config_changes:
        print(f"   ⚙️  Configuration changes")

    print(f"   Analysis time: {analyze_time:.1f}s")

    # If analyze-only, stop here
    if args.analyze_only:
        if analysis.commit_messages:
            print(f"\n   Commits:")
            for msg in analysis.commit_messages[:10]:
                print(f"     • {msg}")
        return

    # ── Step 2: Generate documents ──
    print(f"\n📝 Generating MR documentation with {config.llm.provider.value} ({config.llm.model})...")
    start = time.time()

    llm = create_llm_provider(config.llm)
    generator = MRDocGenerator(llm)

    tech_doc, simple_doc = await generator.generate(analysis)

    gen_time = time.time() - start
    print(f"   Generation time: {gen_time:.1f}s")

    # ── Step 3: Save documents ──
    output_dir = Path(args.output) if args.output else repo_path / config.doc.output_dir / "mr_docs"
    branch_label = args.source_branch or f"{args.from_commit[:8]}_to_{args.to_commit[:8]}"

    if args.type == "both":
        tech_path, simple_path = save_mr_docs(
            tech_doc, simple_doc, output_dir, branch_label,
        )
        print(f"\n   ✅ Technical Review: {tech_path}")
        print(f"   ✅ Stakeholder Summary: {simple_path}")
    elif args.type == "technical":
        tech_path, _ = save_mr_docs(
            tech_doc, simple_doc, output_dir, branch_label,
        )
        print(f"\n   ✅ Technical Review: {tech_path}")
    else:
        _, simple_path = save_mr_docs(
            tech_doc, simple_doc, output_dir, branch_label,
        )
        print(f"\n   ✅ Stakeholder Summary: {simple_path}")

    total_time = analyze_time + gen_time
    print(f"\n🎉 Done! Total time: {total_time:.1f}s")


def main():
    parser = create_parser()
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
