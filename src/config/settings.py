"""
Configuration management for the Repo Doc MCP Server.

This module defines ALL configurable settings using Pydantic models.
Users can configure via:
  1. A YAML config file (repo-doc-mcp.yaml)
  2. Environment variables (prefixed with REPO_DOC_)
  3. Defaults that work out of the box
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class LLMProvider(str, Enum):
    """Supported LLM providers. We use OpenAI-compatible API for Ollama,
    so only three adapters are needed to cover many models."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    BEDROCK = "bedrock"


class LLMConfig(BaseModel):
    """Configuration for a specific LLM provider.

    Each provider needs slightly different settings:
    - Anthropic: needs api_key, uses model like 'claude-sonnet-4-20250514'
    - OpenAI: needs api_key, uses model like 'gpt-4o'
    - Ollama: needs base_url (default localhost:11434), no api_key needed
    """
    provider: LLMProvider = LLMProvider.ANTHROPIC
    model: str = "claude-sonnet-4-20250514"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.3  # Low temp for consistent, factual docs
    aws_region: Optional[str] = None
    aws_profile: Optional[str] = None


class RepoConfig(BaseModel):
    """Controls how the server reads and parses the repository.

    The 'ignore_patterns' list works like .gitignore — any file or directory
    matching these patterns is skipped during scanning. This is critical for
    performance since repos can have thousands of files in node_modules, etc.
    """
    ignore_patterns: list[str] = Field(default_factory=lambda: [
        # Dependencies and build artifacts
        "node_modules", "__pycache__", ".git", ".svn",
        "venv", ".venv", "env", ".env",
        "dist", "build", "out", "target",
        ".next", ".nuxt", ".output",
        # Binary and media files (can't meaningfully document these)
        "*.pyc", "*.pyo", "*.so", "*.dll", "*.dylib",
        "*.jpg", "*.jpeg", "*.png", "*.gif", "*.svg", "*.ico",
        "*.mp3", "*.mp4", "*.wav", "*.avi",
        "*.zip", "*.tar", "*.gz", "*.rar",
        "*.woff", "*.woff2", "*.ttf", "*.eot",
        # IDE and OS files
        ".idea", ".vscode", ".DS_Store", "Thumbs.db",
        # Lock files (long, auto-generated, not useful for docs)
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "Pipfile.lock", "poetry.lock",
        # Coverage and test artifacts
        "coverage", ".coverage", "htmlcov",
        ".pytest_cache", ".mypy_cache",
    ])

    # Files larger than this are summarized rather than fully analyzed
    max_file_size_kb: int = 500

    # Maximum total files to process (safety limit for huge monorepos)
    max_files: int = 500

    # File extensions to include (empty = include all non-ignored)
    include_extensions: list[str] = Field(default_factory=list)


class DocConfig(BaseModel):
    """Controls the documentation generation output.

    Two document types are always generated:
    - technical: For engineers, includes architecture, API details, data flow
    - non_technical: For PMs/stakeholders, plain English, no jargon
    """
    output_dir: str = "./docs/generated"
    output_format: str = "markdown"  # "markdown" or "docx"

    # Whether to include a visual architecture diagram (mermaid syntax)
    include_architecture_diagram: bool = True

    # Whether to include a glossary in the non-technical doc
    include_glossary: bool = True

    # Max depth for directory tree in docs
    tree_depth: int = 4


class ConfluenceConfig(BaseModel):
    """Configuration for publishing documentation to Atlassian Confluence.

    You need three things to publish to Confluence:
    1. Your Confluence instance URL (e.g., https://yourcompany.atlassian.net)
    2. An API token (generated from id.atlassian.com/manage-profile/security/api-tokens)
    3. Your email address (the one linked to your Atlassian account)

    The space_key is the short identifier for the Confluence space where docs
    should be published (e.g., "ENG", "DOCS", "TEAM"). You can find it in the
    space's URL: https://yourcompany.atlassian.net/wiki/spaces/ENG/...
    """
    enabled: bool = False
    url: str = ""                          # e.g., "https://yourcompany.atlassian.net"
    email: str = ""                        # Atlassian account email
    api_token: str = ""                    # API token (NOT your password)
    space_key: str = ""                    # Space key like "ENG" or "DOCS"
    parent_page_id: Optional[str] = None   # Parent page ID to nest docs under (optional)
    # If True, update existing pages instead of creating new ones each time
    update_existing: bool = True


class GoogleDocsConfig(BaseModel):
    """Configuration for publishing documentation to Google Docs.

    You need a Google Cloud service account credentials JSON file to use this.
    Steps to set up:
    1. Go to console.cloud.google.com
    2. Create a project (or use an existing one)
    3. Enable the Google Docs API and Google Drive API
    4. Create a service account under IAM & Admin → Service Accounts
    5. Download the JSON key file
    6. Share the target Google Drive folder with the service account's email

    Alternatively, you can use OAuth2 credentials for personal use, but
    service accounts are better for automation/CI pipelines.
    """
    enabled: bool = False
    credentials_file: str = ""             # Path to service account JSON key file
    # The Google Drive folder ID where docs should be created.
    # Find it in the folder URL: https://drive.google.com/drive/folders/<FOLDER_ID>
    folder_id: str = ""
    # If set, update these specific doc IDs instead of creating new ones
    technical_doc_id: Optional[str] = None
    non_technical_doc_id: Optional[str] = None


class WatcherConfig(BaseModel):
    """Controls the auto-update watcher behavior.

    When enabled, the watcher monitors the main branch and can automatically
    publish updated docs to Confluence/Google Docs after each update.
    """
    enabled: bool = False
    branch: str = "main"
    interval_minutes: float = 5.0
    publish_after_update: bool = False
    branch_docs: BranchDocsConfig = Field(default_factory=lambda: BranchDocsConfig())


class BranchDocsConfig(BaseModel):
    """Controls per-branch documentation generation."""
    enabled: bool = False
    auto_cleanup: bool = True
    publish_branch_docs: bool = False


class PublishConfig(BaseModel):
    """Controls where documentation gets published after generation.

    You can enable one or both publishers. The local Markdown files are
    always generated regardless of these settings — publishing is additive.
    """
    confluence: ConfluenceConfig = Field(default_factory=ConfluenceConfig)
    google_docs: GoogleDocsConfig = Field(default_factory=GoogleDocsConfig)


class ServerConfig(BaseSettings):
    """Top-level server configuration, combines all sub-configs.

    This is the single entry point for all settings. It loads from:
    1. Environment variables (REPO_DOC_LLM__PROVIDER, etc.)
    2. A config file if specified
    3. Sensible defaults
    """
    llm: LLMConfig = Field(default_factory=LLMConfig)
    repo: RepoConfig = Field(default_factory=RepoConfig)
    doc: DocConfig = Field(default_factory=DocConfig)
    publish: PublishConfig = Field(default_factory=PublishConfig)
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)

    # Server-level settings
    log_level: str = "INFO"
    server_name: str = "repo-doc-mcp"
    server_version: str = "0.1.0"

    class Config:
        env_prefix = "REPO_DOC_"
        env_nested_delimiter = "__"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ServerConfig":
        """Load configuration from a YAML file with environment variable overrides."""
        path = Path(path)
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "ServerConfig":
        """Smart config loading: tries config file, then env vars, then defaults.

        Priority order (highest to lowest):
        1. Environment variables
        2. Config file values
        3. Default values
        """
        if config_path:
            return cls.from_yaml(config_path)

        # Check standard locations for config file
        standard_paths = [
            Path("repo-doc-mcp.yaml"),
            Path("repo-doc-mcp.yml"),
            Path.home() / ".config" / "repo-doc-mcp" / "config.yaml",
        ]
        for p in standard_paths:
            if p.exists():
                return cls.from_yaml(p)

        # Fall back to pure env vars / defaults
        return cls()
