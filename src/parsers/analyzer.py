"""
Code Analyzer — enriches raw RepoFiles with structural understanding.

This module bridges the gap between "raw files" and "understood codebase."
It performs two types of analysis:

1. STATIC ANALYSIS (fast, no LLM needed):
   - Extract classes, functions, methods
   - Extract imports and dependencies
   - Detect entry points
   - Build a dependency graph between files

2. LLM-POWERED ANALYSIS (slower, requires API calls):
   - Summarize what each file does
   - Identify the project's overall purpose
   - Understand the architecture
   - Detect the tech stack and how each tech is used

The static analysis uses regex patterns rather than tree-sitter AST parsing.
This is a deliberate tradeoff: regex is less accurate but works for ALL languages
without needing language-specific grammars. Since we're generating documentation
(not refactoring code), slight inaccuracies in extraction are acceptable.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Optional

from src.config.settings import LLMConfig
from src.core.models import (
    AnalyzedFile,
    ClassInfo,
    DependencyEdge,
    FileType,
    FunctionInfo,
    ImportInfo,
    RepoAnalysis,
    RepoFile,
    RepoTree,
)
from src.llm.providers import BaseLLMProvider, create_llm_provider


# ──────────────────────────────────────────────────────────────────────
# Static Code Extractors — language-aware regex patterns
# ──────────────────────────────────────────────────────────────────────

class StaticAnalyzer:
    """Extracts structural information from source code using regex patterns.

    Why regex instead of proper AST parsing?
    - Works across ALL languages with a single codebase
    - No need to install tree-sitter grammars for every language
    - Fast and lightweight
    - "Good enough" for documentation purposes (we don't need perfect accuracy)

    The tradeoff is that nested/complex constructs might not parse correctly,
    but for generating docs, this level of accuracy is sufficient.
    """

    # Regex patterns per language for extracting functions
    FUNCTION_PATTERNS: dict[str, re.Pattern] = {
        "python": re.compile(
            r'(?:^|\n)([ \t]*)(async\s+)?def\s+(\w+)\s*\((.*?)\)(?:\s*->\s*(.+?))?\s*:',
            re.DOTALL
        ),
        "javascript": re.compile(
            r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\((.*?)\)',
            re.DOTALL
        ),
        "typescript": re.compile(
            r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\((.*?)\)(?:\s*:\s*(.+?))?(?:\s*\{)',
            re.DOTALL
        ),
        "java": re.compile(
            r'(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\((.*?)\)',
            re.DOTALL
        ),
        "go": re.compile(
            r'func\s+(?:\(\s*\w+\s+\*?\w+\s*\)\s+)?(\w+)\s*\((.*?)\)',
            re.DOTALL
        ),
        "rust": re.compile(
            r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\((.*?)\)',
            re.DOTALL
        ),
    }

    # Regex patterns for class/struct/interface extraction
    CLASS_PATTERNS: dict[str, re.Pattern] = {
        "python": re.compile(
            r'^class\s+(\w+)(?:\((.*?)\))?\s*:', re.MULTILINE
        ),
        "javascript": re.compile(
            r'class\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{', re.MULTILINE
        ),
        "typescript": re.compile(
            r'(?:export\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+(.+?))?\s*\{',
            re.MULTILINE
        ),
        "java": re.compile(
            r'(?:public|private|protected|abstract|static|\s)*class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+(.+?))?\s*\{',
            re.MULTILINE
        ),
        "go": re.compile(
            r'type\s+(\w+)\s+struct\s*\{', re.MULTILINE
        ),
        "rust": re.compile(
            r'(?:pub\s+)?struct\s+(\w+)', re.MULTILINE
        ),
    }

    # Import patterns per language
    IMPORT_PATTERNS: dict[str, list[re.Pattern]] = {
        "python": [
            re.compile(r'^import\s+([\w.]+)', re.MULTILINE),
            re.compile(r'^from\s+([\w.]+)\s+import\s+(.+)', re.MULTILINE),
        ],
        "javascript": [
            re.compile(r'import\s+.*?from\s+[\'"](.+?)[\'"]', re.MULTILINE),
            re.compile(r'require\s*\(\s*[\'"](.+?)[\'"]\s*\)', re.MULTILINE),
        ],
        "typescript": [
            re.compile(r'import\s+.*?from\s+[\'"](.+?)[\'"]', re.MULTILINE),
        ],
        "java": [
            re.compile(r'^import\s+([\w.]+);', re.MULTILINE),
        ],
        "go": [
            re.compile(r'"([\w./]+)"', re.MULTILINE),
        ],
        "rust": [
            re.compile(r'use\s+([\w:]+)', re.MULTILINE),
        ],
    }

    def extract_functions(self, content: str, language: str) -> list[FunctionInfo]:
        """Extract function/method definitions from source code."""
        functions = []
        pattern = self.FUNCTION_PATTERNS.get(language)
        if not pattern:
            return functions

        lines = content.splitlines()

        for match in pattern.finditer(content):
            # Calculate line number from match position
            line_start = content[:match.start()].count('\n') + 1

            if language == "python":
                # Python pattern has indent, async, name, params, return_type groups
                indent, is_async, name, params, return_type = match.groups()
                param_list = [p.strip().split(":")[0].strip()
                              for p in params.split(",") if p.strip()]
            else:
                groups = match.groups()
                name = groups[0]
                params = groups[1] if len(groups) > 1 else ""
                return_type = groups[2] if len(groups) > 2 else None
                param_list = [p.strip().split(":")[0].strip().split(" ")[-1]
                              for p in params.split(",") if p.strip()]

            # Try to extract docstring (Python-specific for now)
            docstring = None
            if language == "python":
                docstring = self._extract_python_docstring(content, match.end())

            functions.append(FunctionInfo(
                name=name,
                file_path="",  # Filled in later
                line_start=line_start,
                line_end=line_start + 10,  # Rough estimate
                docstring=docstring,
                parameters=param_list,
                return_type=return_type,
                is_public=not name.startswith("_"),
            ))

        return functions

    def extract_classes(self, content: str, language: str) -> list[ClassInfo]:
        """Extract class/struct definitions from source code."""
        classes = []
        pattern = self.CLASS_PATTERNS.get(language)
        if not pattern:
            return classes

        for match in pattern.finditer(content):
            line_start = content[:match.start()].count('\n') + 1
            groups = match.groups()
            name = groups[0]
            base_classes = []
            if len(groups) > 1 and groups[1]:
                base_classes = [b.strip() for b in groups[1].split(",")]

            # Extract docstring for Python classes
            docstring = None
            if language == "python":
                docstring = self._extract_python_docstring(content, match.end())

            classes.append(ClassInfo(
                name=name,
                file_path="",  # Filled in later
                line_start=line_start,
                line_end=line_start + 20,  # Rough estimate
                docstring=docstring,
                base_classes=base_classes,
            ))

        return classes

    def extract_imports(self, content: str, language: str, repo_root: str = "") -> list[ImportInfo]:
        """Extract import statements and classify them as internal vs external."""
        imports = []
        patterns = self.IMPORT_PATTERNS.get(language, [])

        for pattern in patterns:
            for match in pattern.finditer(content):
                module = match.group(1)
                names = []
                if match.lastindex and match.lastindex > 1:
                    names_str = match.group(2)
                    names = [n.strip() for n in names_str.split(",")]

                # Heuristic: relative imports and imports starting with "src", "app",
                # or the repo name are internal. Everything else is external.
                is_external = not (
                    module.startswith(".")
                    or module.startswith("src")
                    or module.startswith("app")
                    or module.startswith("internal")
                    or module.startswith("./")
                    or module.startswith("../")
                )

                imports.append(ImportInfo(
                    module=module,
                    names=names,
                    is_external=is_external,
                ))

        return imports

    def _extract_python_docstring(self, content: str, pos: int) -> Optional[str]:
        """Extract a Python docstring that follows a class/function definition."""
        # Look for triple-quoted string after the colon
        remaining = content[pos:pos + 500]  # Look ahead up to 500 chars
        match = re.search(r'^\s*"""(.*?)"""', remaining, re.DOTALL)
        if match:
            return match.group(1).strip()
        match = re.search(r"^\s*'''(.*?)'''", remaining, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None


# ──────────────────────────────────────────────────────────────────────
# LLM-Powered Analyzer — uses AI for higher-level understanding
# ──────────────────────────────────────────────────────────────────────

class CodeAnalyzer:
    """Orchestrates both static and LLM-powered analysis of a repository.

    This is the main class that consumers use. It:
    1. Runs static analysis on every file (fast, no API calls)
    2. Groups files into chunks for LLM processing
    3. Sends chunks to the LLM for summarization and understanding
    4. Builds the complete RepoAnalysis object

    Usage:
        analyzer = CodeAnalyzer(llm_config)
        analysis = await analyzer.analyze(repo_tree)
    """

    def __init__(self, llm_provider: BaseLLMProvider):
        self.llm = llm_provider
        self.static = StaticAnalyzer()

    async def analyze(self, repo_tree: RepoTree) -> RepoAnalysis:
        """Run complete analysis on a scanned repository.

        This is the main entry point. It returns a RepoAnalysis containing
        both static structure AND LLM-generated insights.
        """
        # Step 1: Static analysis on all source files
        analyzed_files = []
        for repo_file in repo_tree.files:
            analyzed = self._analyze_file_static(repo_file)
            analyzed_files.append(analyzed)

        # Step 2: Build dependency graph from import analysis
        dependencies = self._build_dependency_graph(analyzed_files)

        # Step 3: LLM-powered analysis (runs API calls)
        # We batch files together to minimize API calls
        await self._enrich_with_llm(analyzed_files, repo_tree)

        # Step 4: Generate high-level project insights
        project_purpose, architecture, tech_stack, key_components, entry_points = (
            await self._analyze_project_level(repo_tree, analyzed_files)
        )

        return RepoAnalysis(
            repo_tree=repo_tree,
            analyzed_files=analyzed_files,
            dependencies=dependencies,
            project_purpose=project_purpose,
            architecture_summary=architecture,
            tech_stack=tech_stack,
            key_components=key_components,
            entry_points=entry_points,
        )

    def _analyze_file_static(self, repo_file: RepoFile) -> AnalyzedFile:
        """Run static analysis on a single file — no LLM calls needed."""
        language = repo_file.language or ""
        content = repo_file.content

        functions = self.static.extract_functions(content, language)
        classes = self.static.extract_classes(content, language)
        imports = self.static.extract_imports(content, language)

        # Set file_path on all extracted items
        for f in functions:
            f.file_path = repo_file.path
        for c in classes:
            c.file_path = repo_file.path

        return AnalyzedFile(
            repo_file=repo_file,
            classes=classes,
            functions=functions,
            imports=imports,
        )

    def _build_dependency_graph(self, files: list[AnalyzedFile]) -> list[DependencyEdge]:
        """Build a dependency graph by connecting import statements to files.

        For each file's imports, we try to find which other file in the repo
        provides that import. External imports (third-party packages) create
        edges to virtual nodes representing the package.
        """
        edges: list[DependencyEdge] = []
        file_paths = {f.repo_file.path for f in files}

        for analyzed in files:
            for imp in analyzed.imports:
                if not imp.is_external:
                    # Try to resolve internal import to a file path
                    # e.g., "src.core.models" -> "src/core/models.py"
                    possible_path = imp.module.replace(".", "/")
                    for ext in [".py", ".ts", ".js", ".go", ".rs", ".java"]:
                        candidate = possible_path + ext
                        if candidate in file_paths:
                            edges.append(DependencyEdge(
                                source=analyzed.repo_file.path,
                                target=candidate,
                                imports=imp.names,
                            ))
                            break

        return edges

    async def _enrich_with_llm(
        self, files: list[AnalyzedFile], repo_tree: RepoTree,
    ) -> None:
        """Use the LLM to generate summaries for files.

        We batch files together to reduce API calls. Each batch gets a single
        prompt asking the LLM to summarize multiple files at once.
        """
        # Only summarize source code and important config files
        files_to_summarize = [
            f for f in files
            if f.repo_file.file_type in {FileType.SOURCE_CODE, FileType.CONFIG}
            and f.repo_file.line_count > 5  # Skip tiny files
        ]

        # Process in batches of 5-8 files to stay within token limits
        batch_size = 6
        for i in range(0, len(files_to_summarize), batch_size):
            batch = files_to_summarize[i:i + batch_size]
            await self._summarize_batch(batch)

    async def _summarize_batch(self, files: list[AnalyzedFile]) -> None:
        """Send a batch of files to the LLM for summarization."""
        # Build a prompt that includes all files in the batch
        file_sections = []
        for f in files:
            # Truncate very long files to avoid token limits
            content = f.repo_file.content
            if len(content) > 8000:
                content = content[:8000] + "\n... [truncated for analysis]"

            file_sections.append(
                f"### File: {f.repo_file.path}\n"
                f"Language: {f.repo_file.language or 'unknown'}\n"
                f"```\n{content}\n```"
            )

        prompt = f"""Analyze these source code files and provide a brief 2-3 sentence summary
for each file explaining what it does and its role in the project.

{chr(10).join(file_sections)}

Respond in this exact format for each file:
FILE: <filepath>
SUMMARY: <2-3 sentence summary>

Be specific about what the code does, not generic descriptions."""

        system_prompt = (
            "You are a senior software engineer analyzing a codebase. "
            "Be precise, technical, and concise in your summaries."
        )

        try:
            response = await self.llm.generate(prompt, system_prompt)

            # Parse the response and assign summaries back to files
            file_map = {f.repo_file.path: f for f in files}
            current_file = None

            for line in response.splitlines():
                if line.startswith("FILE:"):
                    current_file = line.replace("FILE:", "").strip()
                elif line.startswith("SUMMARY:") and current_file:
                    summary = line.replace("SUMMARY:", "").strip()
                    if current_file in file_map:
                        file_map[current_file].summary = summary
                    current_file = None

        except Exception as e:
            # LLM failure shouldn't break the whole analysis
            # Files just won't have summaries
            print(f"Warning: LLM summarization failed for batch: {e}")

    async def _analyze_project_level(
        self,
        repo_tree: RepoTree,
        files: list[AnalyzedFile],
    ) -> tuple[str, str, dict, list, list]:
        """Generate high-level project understanding using the LLM.

        This asks the LLM to look at the overall repo structure and provide:
        - What the project does (purpose)
        - How it's architectured
        - What technologies are used and why
        - What the key components/modules are
        - Where the entry points are
        """
        # Build a structural overview for the LLM
        tree_overview = self._build_tree_overview(repo_tree)
        lang_summary = ", ".join(
            f"{lang} ({count} files)" for lang, count in repo_tree.languages.items()
        )

        # Include summaries of the most important files
        key_summaries = []
        for f in files:
            if f.summary and f.repo_file.file_type == FileType.SOURCE_CODE:
                key_summaries.append(f"- {f.repo_file.path}: {f.summary}")

        # Check for common framework indicators
        framework_files = []
        for f in repo_tree.files:
            if f.path in {
                "package.json", "requirements.txt", "Cargo.toml", "go.mod",
                "pom.xml", "build.gradle", "Gemfile", "pyproject.toml",
                "composer.json", "mix.exs",
            }:
                framework_files.append(f"### {f.path}\n{f.content[:2000]}")

        prompt = f"""Analyze this repository and provide a comprehensive understanding.

## Repository: {repo_tree.name}
## Branch: {repo_tree.branch or 'unknown'}
## Languages: {lang_summary}
## Total files: {repo_tree.total_files}, Total lines: {repo_tree.total_lines}

## Directory Structure:
{tree_overview}

## Dependency/Build Files:
{chr(10).join(framework_files) if framework_files else "None found"}

## File Summaries:
{chr(10).join(key_summaries[:30]) if key_summaries else "No summaries available"}

Please respond in this EXACT format:

PURPOSE: <1-2 paragraph description of what this project does>
ARCHITECTURE: <1-2 paragraph description of the architecture and how components interact>
TECH_STACK: <comma-separated list of "technology: role" pairs, e.g. "Flask: web framework, PostgreSQL: database">
KEY_COMPONENTS: <comma-separated list of main modules/packages>
ENTRY_POINTS: <comma-separated list of main files/scripts that serve as entry points>
"""

        system_prompt = (
            "You are a principal software architect analyzing a codebase. "
            "Be thorough but concise. Focus on the big picture."
        )

        try:
            response = await self.llm.generate(prompt, system_prompt)
            return self._parse_project_analysis(response)
        except Exception as e:
            print(f"Warning: Project-level analysis failed: {e}")
            return (
                "Could not determine project purpose.",
                "Architecture analysis unavailable.",
                {},
                [],
                [],
            )

    def _parse_project_analysis(
        self, response: str,
    ) -> tuple[str, str, dict, list, list]:
        """Parse the structured response from the project-level LLM call."""
        purpose = ""
        architecture = ""
        tech_stack = {}
        key_components = []
        entry_points = []

        current_field = None
        current_content = []

        for line in response.splitlines():
            if line.startswith("PURPOSE:"):
                if current_field:
                    self._assign_parsed_field(
                        current_field, "\n".join(current_content).strip(),
                        locals()
                    )
                current_field = "purpose"
                current_content = [line.replace("PURPOSE:", "").strip()]
            elif line.startswith("ARCHITECTURE:"):
                if current_field:
                    purpose = "\n".join(current_content).strip()
                current_field = "architecture"
                current_content = [line.replace("ARCHITECTURE:", "").strip()]
            elif line.startswith("TECH_STACK:"):
                if current_field == "architecture":
                    architecture = "\n".join(current_content).strip()
                current_field = "tech_stack"
                stack_str = line.replace("TECH_STACK:", "").strip()
                for item in stack_str.split(","):
                    if ":" in item:
                        tech, role = item.split(":", 1)
                        tech_stack[tech.strip()] = role.strip()
                current_content = []
            elif line.startswith("KEY_COMPONENTS:"):
                current_field = "key_components"
                components_str = line.replace("KEY_COMPONENTS:", "").strip()
                key_components = [c.strip() for c in components_str.split(",") if c.strip()]
                current_content = []
            elif line.startswith("ENTRY_POINTS:"):
                current_field = "entry_points"
                entries_str = line.replace("ENTRY_POINTS:", "").strip()
                entry_points = [e.strip() for e in entries_str.split(",") if e.strip()]
                current_content = []
            elif current_field in ("purpose", "architecture"):
                current_content.append(line)

        # Handle the last field
        if current_field == "purpose":
            purpose = "\n".join(current_content).strip()
        elif current_field == "architecture":
            architecture = "\n".join(current_content).strip()

        return purpose, architecture, tech_stack, key_components, entry_points

    def _build_tree_overview(self, repo_tree: RepoTree, max_depth: int = 3) -> str:
        """Build a text-based directory tree for the LLM to understand the structure."""
        dirs: dict[str, list[str]] = {}
        for f in repo_tree.files:
            parts = Path(f.path).parts
            if len(parts) <= max_depth:
                dir_key = "/".join(parts[:-1]) if len(parts) > 1 else "."
                dirs.setdefault(dir_key, []).append(parts[-1])

        lines = []
        for dir_path in sorted(dirs.keys()):
            if dir_path == ".":
                lines.append(f"  (root)/")
            else:
                indent = "  " * (dir_path.count("/") + 1)
                lines.append(f"{indent}{dir_path}/")
            for fname in sorted(dirs[dir_path])[:10]:  # Limit files shown per dir
                indent = "  " * (dir_path.count("/") + 2)
                lines.append(f"{indent}{fname}")
            remaining = len(dirs[dir_path]) - 10
            if remaining > 0:
                indent = "  " * (dir_path.count("/") + 2)
                lines.append(f"{indent}... and {remaining} more files")

        return "\n".join(lines)

    def _assign_parsed_field(self, field: str, value: str, local_vars: dict) -> None:
        """Helper to assign parsed values — used during response parsing."""
        pass  # Handled inline in _parse_project_analysis
