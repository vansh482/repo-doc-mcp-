"""
Documentation Generator — produces final documents from analyzed code.

Architecture: section-by-section generation. Instead of asking the LLM to write
an entire document in one call (which truncates), each section gets its own
focused prompt with only the relevant context. This produces complete, detailed
content for every section.

Pipeline position:
    RepoAnalysis → DocGenerator → GeneratedDoc (tech) + GeneratedDoc (non-tech)
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config.settings import DocConfig
from src.core.models import (
    DocType,
    DocumentSection,
    FileType,
    GeneratedDoc,
    RepoAnalysis,
)
from src.generators.prompts import (
    ARCHITECTURE_DIAGRAM_PROMPT,
    NON_TECH_SECTIONS,
    NON_TECHNICAL_SYSTEM_PROMPT,
    TECH_SECTIONS,
    TECHNICAL_SYSTEM_PROMPT,
)
from src.llm.providers import BaseLLMProvider


class DocGenerator:
    """Generates technical and non-technical documentation from analyzed code.

    Usage:
        generator = DocGenerator(llm_provider, config)
        tech_doc, simple_doc = await generator.generate(analysis)
    """

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        config: DocConfig | None = None,
    ):
        self.llm = llm_provider
        self.config = config or DocConfig()

    async def generate(
        self, analysis: RepoAnalysis,
    ) -> tuple[GeneratedDoc, GeneratedDoc]:
        """Generate both technical and non-technical docs from a RepoAnalysis."""
        context = self._prepare_context(analysis)

        tech_doc = await self._generate_sectioned_doc(
            context, analysis, DocType.TECHNICAL,
            TECH_SECTIONS, TECHNICAL_SYSTEM_PROMPT,
        )
        simple_doc = await self._generate_sectioned_doc(
            context, analysis, DocType.NON_TECHNICAL,
            NON_TECH_SECTIONS, NON_TECHNICAL_SYSTEM_PROMPT,
        )

        if self.config.include_architecture_diagram:
            diagram = await self._generate_diagram(context)
            tech_doc.architecture_diagram = diagram

        return tech_doc, simple_doc

    async def _generate_sectioned_doc(
        self,
        context: dict,
        analysis: RepoAnalysis,
        doc_type: DocType,
        sections_config: list[dict],
        system_prompt: str,
    ) -> GeneratedDoc:
        """Generate a document section by section, each with its own LLM call."""
        sections: list[DocumentSection] = []

        for i, section_def in enumerate(sections_config):
            title = section_def["title"]
            prompt_template = section_def["prompt"]

            prompt = self._fill_prompt(prompt_template, context)

            print(f"      [{i+1}/{len(sections_config)}] Generating: {title}")
            content = await self.llm.generate(prompt, system_prompt)

            content = self._clean_response(content, title)

            section = DocumentSection(
                title=title,
                content=content,
                order=i + 1,
            )
            sections.append(section)

        type_label = "Technical Documentation" if doc_type == DocType.TECHNICAL else "Project Guide (Non-Technical)"
        return GeneratedDoc(
            doc_type=doc_type,
            title=f"{context['repo_name']} — {type_label}",
            sections=sections,
            repo_name=context["repo_name"],
            branch=context["branch"],
            commit_hash=context["commit"],
        )

    def _fill_prompt(self, template: str, context: dict) -> str:
        """Fill a prompt template with available context, leaving missing keys as 'Not available'."""
        try:
            return template.format(**context)
        except KeyError as e:
            safe_context = {k: context.get(k, "Not available") for k in
                          re.findall(r'\{(\w+)\}', template)}
            return template.format(**safe_context)

    def _clean_response(self, content: str, expected_title: str) -> str:
        """Remove redundant section headings the LLM might have included."""
        lines = content.strip().splitlines()
        cleaned = []
        for line in lines:
            if re.match(r'^#{1,3}\s*\d*\.?\s*' + re.escape(expected_title), line, re.IGNORECASE):
                continue
            if re.match(r'^#{1,3}\s*$', line):
                continue
            cleaned.append(line)
        return "\n".join(cleaned).strip()

    def _prepare_context(self, analysis: RepoAnalysis) -> dict:
        """Transform RepoAnalysis into template variables."""
        repo = analysis.repo_tree

        languages = ", ".join(
            f"{lang} ({count} files)"
            for lang, count in repo.languages.items()
        )

        tech_stack = "\n".join(
            f"- {tech}: {role}"
            for tech, role in analysis.tech_stack.items()
        ) or "Not determined"

        key_components = "\n".join(
            f"- {comp}" for comp in analysis.key_components
        ) or "Not determined"

        entry_points = "\n".join(
            f"- {ep}" for ep in analysis.entry_points
        ) or "Not determined"

        file_details = self._format_file_details(analysis)
        dependencies = self._format_dependencies(analysis)
        directory_tree = self._format_directory_tree(analysis)

        return {
            "repo_name": repo.name,
            "branch": repo.branch or "unknown",
            "commit": repo.commit_hash or "unknown",
            "languages": languages,
            "total_files": repo.total_files,
            "total_lines": repo.total_lines,
            "project_purpose": analysis.project_purpose or "Not yet analyzed",
            "architecture_summary": analysis.architecture_summary or "Not yet analyzed",
            "tech_stack": tech_stack,
            "key_components": key_components,
            "entry_points": entry_points,
            "file_details": file_details,
            "dependencies": dependencies,
            "directory_tree": directory_tree,
        }

    def _format_file_details(self, analysis: RepoAnalysis) -> str:
        """Format per-file analysis for prompts."""
        sections = []
        for af in analysis.analyzed_files:
            if af.repo_file.file_type not in {FileType.SOURCE_CODE, FileType.CONFIG}:
                continue

            parts = [f"### `{af.repo_file.path}` ({af.repo_file.language or 'unknown'})"]

            if af.summary:
                parts.append(f"Summary: {af.summary}")

            if af.classes:
                class_names = ", ".join(f"`{c.name}`" for c in af.classes)
                parts.append(f"Classes: {class_names}")

            if af.functions:
                public_fns = [f for f in af.functions if f.is_public]
                if public_fns:
                    fn_names = ", ".join(f"`{fn.name}()`" for fn in public_fns[:10])
                    parts.append(f"Public Functions: {fn_names}")
                    if len(public_fns) > 10:
                        parts.append(f"  (and {len(public_fns) - 10} more)")

            if af.imports:
                external = [i for i in af.imports if i.is_external]
                if external:
                    ext_names = ", ".join(f"`{i.module}`" for i in external[:8])
                    parts.append(f"External Deps: {ext_names}")

            sections.append("\n".join(parts))

        return "\n\n".join(sections) or "No detailed file analysis available."

    def _format_dependencies(self, analysis: RepoAnalysis) -> str:
        """Format the dependency graph."""
        if not analysis.dependencies:
            return "No internal dependencies mapped."

        lines = []
        for dep in analysis.dependencies[:30]:
            imports_str = ", ".join(dep.imports) if dep.imports else "module"
            lines.append(f"- `{dep.source}` → `{dep.target}` (imports: {imports_str})")

        result = "\n".join(lines)
        remaining = len(analysis.dependencies) - 30
        if remaining > 0:
            result += f"\n\n(and {remaining} more dependency edges)"
        return result

    def _format_directory_tree(self, analysis: RepoAnalysis) -> str:
        """Build a visual directory tree string."""
        paths = sorted(set(
            str(Path(f.repo_file.path).parent) for f in analysis.analyzed_files
        ))

        lines = [f"{analysis.repo_tree.name}/"]
        seen_dirs: set[str] = set()

        for p in paths:
            if p == ".":
                continue
            parts = Path(p).parts
            for i, part in enumerate(parts):
                dir_path = "/".join(parts[:i + 1])
                if dir_path not in seen_dirs:
                    seen_dirs.add(dir_path)
                    indent = "  " * (i + 1)
                    lines.append(f"{indent}├── {part}/")

        return "\n".join(lines[:50])

    async def _generate_diagram(self, context: dict) -> Optional[str]:
        """Generate a Mermaid architecture diagram."""
        prompt = ARCHITECTURE_DIAGRAM_PROMPT.format(
            key_components=context["key_components"],
            dependencies=context["dependencies"],
            tech_stack=context["tech_stack"],
        )

        try:
            response = await self.llm.generate(prompt)

            mermaid_match = re.search(
                r'```mermaid\s*\n(.*?)\n\s*```',
                response,
                re.DOTALL,
            )
            if mermaid_match:
                return mermaid_match.group(1).strip()

            if response.strip().startswith(("graph ", "flowchart ", "sequenceDiagram")):
                return response.strip()

            return None

        except Exception as e:
            print(f"Warning: Diagram generation failed: {e}")
            return None
