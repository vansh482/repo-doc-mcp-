"""
Publish Orchestrator — pushes generated documentation to Confluence and/or Google Docs.

This module is the "last mile" of the documentation pipeline. It takes the
generated Markdown content (from Phase 1's generator) and publishes it to
one or both of the configured destinations.

The publish step is ADDITIVE — local Markdown files are always saved regardless.
Publishing to Confluence/Google Docs happens after the local save, so you always
have a local backup even if publishing fails.

PIPELINE FLOW:
    Scanner → Analyzer → Generator → [Local Markdown files]
                                           │
                                           ├──→ Confluence Publisher
                                           │     (if configured)
                                           │
                                           └──→ Google Docs Publisher
                                                 (if configured)

USAGE FROM CLI:
    # Generate docs AND publish to configured destinations
    python -m src.publishers.cli /path/to/repo

    # Publish already-generated docs (skip regeneration)
    python -m src.publishers.cli /path/to/repo --publish-only

    # Publish to Confluence only
    python -m src.publishers.cli /path/to/repo --confluence-only

    # Publish to Google Docs only
    python -m src.publishers.cli /path/to/repo --google-docs-only
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from src.config.settings import ServerConfig, LLMProvider
from src.llm.providers import create_llm_provider
from src.parsers.scanner import RepoScanner
from src.parsers.analyzer import CodeAnalyzer
from src.generators.doc_generator import DocGenerator
from src.publishers.confluence import ConfluencePublisher
from src.publishers.google_docs import GoogleDocsPublisher


async def generate_and_publish(
    repo_path: str,
    config: ServerConfig,
    publish_only: bool = False,
    confluence_only: bool = False,
    google_docs_only: bool = False,
) -> None:
    """Run the full pipeline: generate docs → save locally → publish to configured destinations."""

    repo_path_resolved = Path(repo_path).resolve()
    out_dir = Path(config.doc.output_dir)
    if not out_dir.is_absolute():
        out_dir = repo_path_resolved / out_dir

    tech_content = ""
    simple_content = ""

    if publish_only:
        # ── Read existing docs from disk ──
        print(f"\n📂 Reading existing documentation from {out_dir}")
        tech_path = out_dir / "TECHNICAL_DOC.md"
        simple_path = out_dir / "NON_TECHNICAL_GUIDE.md"

        if not tech_path.exists() and not simple_path.exists():
            print(f"❌ No generated docs found at {out_dir}")
            print(f"   Run without --publish-only to generate docs first.")
            sys.exit(1)

        if tech_path.exists():
            tech_content = tech_path.read_text(encoding="utf-8")
            print(f"   Found technical doc ({len(tech_content)} chars)")
        if simple_path.exists():
            simple_content = simple_path.read_text(encoding="utf-8")
            print(f"   Found non-technical guide ({len(simple_content)} chars)")
    else:
        # ── Full generation pipeline ──
        print(f"\n📂 Scanning repository: {repo_path_resolved}")
        scanner = RepoScanner(config.repo)
        repo_tree = scanner.scan(str(repo_path_resolved))
        print(f"   Found {repo_tree.total_files} files, {repo_tree.total_lines} lines")

        print(f"\n🔍 Analyzing codebase with {config.llm.provider.value} ({config.llm.model})...")
        llm = create_llm_provider(config.llm)
        analyzer = CodeAnalyzer(llm)
        analysis = await analyzer.analyze(repo_tree)

        print(f"\n📝 Generating documentation...")
        generator = DocGenerator(llm, config.doc)
        tech_doc, simple_doc = await generator.generate(analysis)

        tech_content = tech_doc.to_markdown()
        simple_content = simple_doc.to_markdown()

        # Save locally
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "TECHNICAL_DOC.md").write_text(tech_content, encoding="utf-8")
        (out_dir / "NON_TECHNICAL_GUIDE.md").write_text(simple_content, encoding="utf-8")
        print(f"   ✅ Local Markdown files saved to {out_dir}")

    # ── Determine repo name ──
    repo_name = repo_path_resolved.name

    # ── Publish to Confluence ──
    if config.publish.confluence.enabled and not google_docs_only:
        print(f"\n☁️  Publishing to Confluence ({config.publish.confluence.url})...")
        start = time.time()
        try:
            publisher = ConfluencePublisher(config.publish.confluence)
            result = await publisher.publish(tech_content, simple_content, repo_name)
            elapsed = time.time() - start
            print(f"   {result.summary()}")
            print(f"   Publish time: {elapsed:.1f}s")
        except Exception as e:
            print(f"   ❌ Confluence publish failed: {e}")

    # ── Publish to Google Docs ──
    if config.publish.google_docs.enabled and not confluence_only:
        print(f"\n📄 Publishing to Google Docs...")
        start = time.time()
        try:
            publisher = GoogleDocsPublisher(config.publish.google_docs)
            result = await publisher.publish(tech_content, simple_content, repo_name)
            elapsed = time.time() - start
            print(f"   {result.summary()}")
            print(f"   Publish time: {elapsed:.1f}s")
        except Exception as e:
            print(f"   ❌ Google Docs publish failed: {e}")

    # ── Check if no publishers are configured ──
    if not config.publish.confluence.enabled and not config.publish.google_docs.enabled:
        print(f"\n⚠️  No publishers configured!")
        print(f"   Docs were saved locally to {out_dir}")
        print(f"   To publish, configure Confluence or Google Docs in repo-doc-mcp.yaml")
        print(f"   See the testing guide in TESTING.md for step-by-step setup instructions.")

    print(f"\n🎉 Done!")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate documentation and publish to Confluence / Google Docs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate docs and publish to all configured destinations
  python -m src.publishers.cli /path/to/repo

  # Publish existing docs (skip regeneration)
  python -m src.publishers.cli /path/to/repo --publish-only

  # Publish to Confluence only
  python -m src.publishers.cli /path/to/repo --confluence-only

  # Publish to Google Docs only
  python -m src.publishers.cli /path/to/repo --google-docs-only
        """,
    )

    parser.add_argument("repo_path", nargs="?", default=".", help="Repository path")
    parser.add_argument("--config", "-c", default=None, help="Config file path")
    parser.add_argument("--publish-only", action="store_true",
                       help="Publish existing docs without regenerating")
    parser.add_argument("--confluence-only", action="store_true",
                       help="Publish only to Confluence")
    parser.add_argument("--google-docs-only", action="store_true",
                       help="Publish only to Google Docs")
    parser.add_argument("--provider", choices=["anthropic", "openai", "ollama", "bedrock"], default=None)
    parser.add_argument("--model", default=None)

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    config = ServerConfig.load(args.config)
    if args.provider:
        config.llm.provider = LLMProvider(args.provider)
    if args.model:
        config.llm.model = args.model

    asyncio.run(generate_and_publish(
        repo_path=args.repo_path,
        config=config,
        publish_only=args.publish_only,
        confluence_only=args.confluence_only,
        google_docs_only=args.google_docs_only,
    ))


if __name__ == "__main__":
    main()
