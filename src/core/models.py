"""
Core data models for the Repo Doc MCP Server.

These Pydantic models define the shape of data as it flows through the system:

    Repository Scanning          Code Analysis            Doc Generation
    ┌──────────┐     ┌────────────────┐     ┌─────────────────┐
    │ RepoFile │ ──> │ AnalyzedFile   │ ──> │ Documentation   │
    │ RepoTree │     │ RepoAnalysis   │     │ (tech + simple) │
    └──────────┘     └────────────────┘     └─────────────────┘

Each stage enriches the data from the previous stage.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Stage 1: Repository Scanning — Raw file data from the repo
# ──────────────────────────────────────────────────────────────────────

class FileType(str, Enum):
    """Broad categorization of file types.
    This helps us decide HOW to parse each file and what documentation
    strategy to use. A Python file needs different handling than a config file."""
    SOURCE_CODE = "source_code"
    CONFIG = "config"
    DOCUMENTATION = "documentation"
    DATA = "data"
    TEST = "test"
    BUILD = "build"
    OTHER = "other"


class RepoFile(BaseModel):
    """Represents a single file discovered during repository scanning.

    This is the raw, un-analyzed representation. We store the content as a string
    because we only process text files (binary files are filtered out during scanning).
    """
    path: str                           # Relative path from repo root (e.g., "src/main.py")
    absolute_path: str                  # Full filesystem path
    content: str                        # Raw file content
    extension: str                      # File extension without dot (e.g., "py", "ts")
    size_bytes: int                     # File size — used to decide chunking strategy
    file_type: FileType                 # Categorization (source, config, test, etc.)
    language: Optional[str] = None      # Detected programming language (e.g., "python")

    @property
    def size_kb(self) -> float:
        return self.size_bytes / 1024

    @property
    def line_count(self) -> int:
        return len(self.content.splitlines())


class RepoTree(BaseModel):
    """The complete scanned repository — all files plus metadata.

    This is what the scanner produces. It contains every file we want to analyze
    plus metadata about the repo itself (name, branch, etc.)
    """
    name: str                           # Repository name (from directory name or git)
    root_path: str                      # Absolute path to the repo root
    branch: Optional[str] = None        # Current git branch
    commit_hash: Optional[str] = None   # Current HEAD commit
    files: list[RepoFile] = Field(default_factory=list)
    scanned_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_lines(self) -> int:
        return sum(f.line_count for f in self.files)

    @property
    def languages(self) -> dict[str, int]:
        """Count files per language — useful for the 'Tech Stack' section of docs."""
        lang_count: dict[str, int] = {}
        for f in self.files:
            if f.language:
                lang_count[f.language] = lang_count.get(f.language, 0) + 1
        return dict(sorted(lang_count.items(), key=lambda x: x[1], reverse=True))

    def files_by_type(self, file_type: FileType) -> list[RepoFile]:
        return [f for f in self.files if f.file_type == file_type]


# ──────────────────────────────────────────────────────────────────────
# Stage 2: Code Analysis — Enriched understanding of the codebase
# ──────────────────────────────────────────────────────────────────────

class FunctionInfo(BaseModel):
    """Extracted information about a function/method in the codebase."""
    name: str
    file_path: str
    line_start: int
    line_end: int
    docstring: Optional[str] = None
    parameters: list[str] = Field(default_factory=list)
    return_type: Optional[str] = None
    is_public: bool = True              # False if starts with _ (Python convention)


class ClassInfo(BaseModel):
    """Extracted information about a class."""
    name: str
    file_path: str
    line_start: int
    line_end: int
    docstring: Optional[str] = None
    base_classes: list[str] = Field(default_factory=list)
    methods: list[FunctionInfo] = Field(default_factory=list)


class ImportInfo(BaseModel):
    """Tracks what a file imports — essential for understanding dependencies."""
    module: str                         # e.g., "flask" or "src.core.models"
    names: list[str] = Field(default_factory=list)  # e.g., ["Flask", "request"]
    is_external: bool = True            # True if it's a third-party package


class AnalyzedFile(BaseModel):
    """A file after code analysis — we now understand its structure.

    This is a RepoFile enriched with parsed information: what classes it defines,
    what functions it has, what it imports, and a brief LLM-generated summary.
    """
    repo_file: RepoFile
    classes: list[ClassInfo] = Field(default_factory=list)
    functions: list[FunctionInfo] = Field(default_factory=list)
    imports: list[ImportInfo] = Field(default_factory=list)
    summary: Optional[str] = None       # Brief LLM-generated summary of what this file does


class DependencyEdge(BaseModel):
    """Represents a dependency relationship between two files.
    Used to build the dependency graph and architecture diagram."""
    source: str     # File that imports
    target: str     # File being imported
    imports: list[str] = Field(default_factory=list)  # Specific names imported


class RepoAnalysis(BaseModel):
    """Complete analysis of the entire repository.

    This is the rich, structured understanding that gets fed to the doc generators.
    It contains everything needed to write both technical and non-technical docs.
    """
    repo_tree: RepoTree
    analyzed_files: list[AnalyzedFile] = Field(default_factory=list)
    dependencies: list[DependencyEdge] = Field(default_factory=list)

    # High-level LLM-generated insights
    project_purpose: Optional[str] = None       # What does this project do?
    architecture_summary: Optional[str] = None   # How is it structured?
    tech_stack: dict[str, str] = Field(default_factory=dict)  # tech -> role
    key_components: list[str] = Field(default_factory=list)    # Main modules/packages
    entry_points: list[str] = Field(default_factory=list)      # Main files/scripts


# ──────────────────────────────────────────────────────────────────────
# Stage 3: Documentation Output
# ──────────────────────────────────────────────────────────────────────

class DocType(str, Enum):
    """The two flavors of documentation we generate."""
    TECHNICAL = "technical"
    NON_TECHNICAL = "non_technical"


class DocumentSection(BaseModel):
    """A single section within a generated document.
    Documents are built as a list of sections, making them easy to
    render in different formats (markdown, docx, HTML)."""
    title: str
    content: str
    order: int = 0
    subsections: list["DocumentSection"] = Field(default_factory=list)


class GeneratedDoc(BaseModel):
    """A complete generated document — the final output of the pipeline."""
    doc_type: DocType
    title: str
    sections: list[DocumentSection] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    repo_name: str = ""
    branch: Optional[str] = None
    commit_hash: Optional[str] = None

    # Mermaid diagram source (rendered by the consumer)
    architecture_diagram: Optional[str] = None

    def to_markdown(self) -> str:
        """Render the document as a single markdown string."""
        parts = [f"# {self.title}\n"]
        parts.append(f"*Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}*")
        if self.branch:
            parts.append(f"*Branch: `{self.branch}`*")
        if self.commit_hash:
            parts.append(f"*Commit: `{self.commit_hash[:8]}`*")
        parts.append("")

        for section in sorted(self.sections, key=lambda s: s.order):
            parts.append(self._render_section(section, level=2))

        if self.architecture_diagram:
            parts.append("\n## Architecture Diagram\n")
            parts.append(f"```mermaid\n{self.architecture_diagram}\n```\n")

        return "\n".join(parts)

    def _render_section(self, section: DocumentSection, level: int) -> str:
        """Recursively render a section and its subsections."""
        prefix = "#" * level
        lines = [f"{prefix} {section.title}\n", section.content, ""]
        for sub in sorted(section.subsections, key=lambda s: s.order):
            lines.append(self._render_section(sub, level + 1))
        return "\n".join(lines)
