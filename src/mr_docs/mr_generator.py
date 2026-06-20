"""
MR Document Generator — produces per-MR documentation from an MRAnalysis.

This module generates two types of MR-specific documents:

TECHNICAL MR DOC (for reviewers and engineers):
    - What changed and why
    - Per-file diff with annotations
    - Architecture impact analysis
    - Risk assessment with specific concerns
    - Testing coverage analysis
    - Deployment considerations

NON-TECHNICAL MR DOC (for PMs, stakeholders, release notes):
    - What this change means for users
    - Which features are affected
    - Any visible behavior changes
    - Timeline and next steps
    - Plain English explanations of technical changes

The documents are self-contained — someone reading them should understand
the MR completely without needing to look at the actual code diff.

DESIGN PHILOSOPHY:
The key difference between MR docs and repo-level docs (Phase 1) is FOCUS.
Repo docs describe the entire system; MR docs describe a SPECIFIC CHANGE.
MR docs answer "what happened and why" rather than "what exists and how."
The writing style is more like a changelog or release note than a manual.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.models import DocType, DocumentSection, GeneratedDoc
from src.llm.providers import BaseLLMProvider
from src.mr_docs.mr_analyzer import (
    ChangeNature,
    MRAnalysis,
    RiskLevel,
)


# ──────────────────────────────────────────────────────────────────────
# System Prompts — set the LLM persona for MR documentation
# ──────────────────────────────────────────────────────────────────────

TECHNICAL_MR_SYSTEM = """You are a senior engineer writing a merge request review document.

Your audience is other engineers who need to:
- Understand what this MR changes and why
- Review the changes effectively
- Know what to test before approving
- Understand deployment implications

Writing guidelines:
- Be direct and concise — this is a focused change document, not a book
- Reference specific files, functions, and line changes
- Highlight anything surprising, risky, or non-obvious
- Call out areas that need extra review attention
- Include deployment and rollback considerations
- Note any technical debt introduced or resolved
- Be honest about the risk level and explain why"""

NON_TECHNICAL_MR_SYSTEM = """You are a product communicator explaining code changes to non-technical team members.

Your audience is product managers, designers, QA, marketing, and leadership who need to:
- Understand what changed in plain English
- Know which features or user experiences are affected
- Assess whether this needs special communication to customers
- Understand the timeline and any risks

Writing guidelines:
- Absolutely NO code, NO technical jargon, NO file paths
- Explain everything in terms of what USERS will experience
- Use the format: "Before this change... After this change..."
- Be concise — busy stakeholders need quick summaries
- Flag anything that affects user-facing behavior
- Note if any documentation, help articles, or support scripts need updating
- Include a one-sentence summary at the very top"""


# ──────────────────────────────────────────────────────────────────────
# Technical MR Prompt
# ──────────────────────────────────────────────────────────────────────

TECHNICAL_MR_PROMPT = """Generate a technical review document for this merge request.

## MR Information
- **Title**: {mr_title}
- **Branch**: {source_branch} → {target_branch}
- **Author**: {author}
- **Nature**: {change_nature}
- **Risk Level**: {risk_level}
- **Files Changed**: {total_files}

## MR Description
{mr_description}

## Commit Messages
{commit_messages}

## Change Groups (by feature area)
{change_groups}

## Flags
- Breaking Changes: {has_breaking}
- Database Migration: {has_migration}
- New Dependencies: {has_new_deps}
- Config Changes: {has_config}
- Test Changes: {has_tests}

## File Diffs
{file_diffs}

---

Write a complete MR review document with these sections:

1. **Summary** — 2-3 sentences explaining what this MR does and why. Include the risk level.

2. **What Changed** — For each feature area affected, explain:
   - What was changed
   - Why it was changed
   - How the new implementation works
   - Any notable design decisions

3. **Architecture Impact** — Does this change the system architecture? New components? 
   Changed data flow? Modified APIs? If there's no architectural impact, say so briefly.

4. **Risk Analysis** — Specific risks and how they're mitigated:
   - What could go wrong?
   - What areas need extra testing?
   - Are there edge cases to watch for?

5. **Testing** — What tests were added/modified? What should be manually tested?
   Is there adequate test coverage for the changes?

6. **Deployment Notes** — Configuration changes, feature flags, migration steps,
   rollback plan, monitoring to watch.

7. **Review Checklist** — Key areas reviewers should focus on.

Be specific and reference actual file names and function names."""


# ──────────────────────────────────────────────────────────────────────
# Non-Technical MR Prompt
# ──────────────────────────────────────────────────────────────────────

NON_TECHNICAL_MR_PROMPT = """Write a plain-English summary of this code change for non-technical team members.

## What happened
- **Title**: {mr_title}
- **Type of change**: {change_nature_friendly}
- **Risk Level**: {risk_level_friendly}
- **Areas affected**: {affected_areas}

## Description from the developer
{mr_description}

## Change summary
{commit_messages}

## Flags
- User-facing behavior changes: {has_breaking}
- Database changes needed: {has_migration}
- New external services added: {has_new_deps}
- Settings/configuration changes: {has_config}

---

Write a brief, clear summary document with these sections:

1. **One-Line Summary** — A single sentence anyone can understand. 
   Example: "This change adds Google login to the sign-up page."

2. **What Changed (For Users)** — In 2-3 paragraphs, explain:
   - What users will experience differently after this change
   - If nothing is visibly different, explain what improved behind the scenes
   - Use "Before this change... After this change..." format

3. **Which Features Are Affected** — List the feature areas that were touched,
   with a brief explanation of what changed in each. Use friendly names, not
   technical terms.

4. **Do We Need To Do Anything?** — Flag action items for the team:
   - Does marketing need to know about this?
   - Do help docs need updating?
   - Does customer support need a heads-up?
   - Are there any feature flags to toggle?

5. **Risk & Timeline** — In simple terms:
   - How confident are we this won't cause issues?
   - Is this change reversible if something goes wrong?
   - When will this be live?

Keep it SHORT. This should take 2 minutes to read. No code. No jargon."""


# ──────────────────────────────────────────────────────────────────────
# The Generator
# ──────────────────────────────────────────────────────────────────────

class MRDocGenerator:
    """Generates MR-specific documentation from an MRAnalysis.
    
    Usage:
        generator = MRDocGenerator(llm_provider)
        tech_doc, simple_doc = await generator.generate(mr_analysis)
    """
    
    def __init__(self, llm_provider: BaseLLMProvider):
        self.llm = llm_provider
    
    async def generate(
        self, analysis: MRAnalysis,
    ) -> tuple[GeneratedDoc, GeneratedDoc]:
        """Generate both technical and non-technical MR documents."""
        context = self._prepare_context(analysis)
        
        tech_doc = await self._generate_technical(context, analysis)
        simple_doc = await self._generate_non_technical(context, analysis)
        
        return tech_doc, simple_doc
    
    async def generate_technical_only(
        self, analysis: MRAnalysis,
    ) -> GeneratedDoc:
        """Generate just the technical MR review document."""
        context = self._prepare_context(analysis)
        return await self._generate_technical(context, analysis)
    
    async def generate_non_technical_only(
        self, analysis: MRAnalysis,
    ) -> GeneratedDoc:
        """Generate just the non-technical MR summary."""
        context = self._prepare_context(analysis)
        return await self._generate_non_technical(context, analysis)
    
    def _prepare_context(self, analysis: MRAnalysis) -> dict:
        """Transform MRAnalysis into template variables."""
        
        # Format change groups with file details
        groups_text = ""
        for group in analysis.change_groups:
            file_list = "\n".join(
                f"  - `{f.path}` ({f.change_type.value}"
                + (f", +{f.diff_stats.lines_added}/-{f.diff_stats.lines_removed}" 
                   if f.diff_stats else "")
                + ")"
                for f in group.files
            )
            groups_text += f"\n### {group.name}\n{file_list}\n"
        
        # Format file diffs (truncated for token efficiency)
        diffs_text = ""
        for filepath, diff_content in list(analysis.file_diffs.items())[:15]:
            # Only include the most relevant parts of each diff
            truncated = diff_content[:2000]
            if len(diff_content) > 2000:
                truncated += "\n... [truncated]"
            diffs_text += f"\n### {filepath}\n```diff\n{truncated}\n```\n"
        
        if not diffs_text:
            diffs_text = "No detailed diffs available."
        
        # Friendly names for the non-technical doc
        nature_friendly = {
            ChangeNature.NEW_FEATURE: "New feature being added",
            ChangeNature.BUG_FIX: "Bug fix",
            ChangeNature.REFACTOR: "Code improvement (no visible changes to users)",
            ChangeNature.PERFORMANCE: "Speed and performance improvement",
            ChangeNature.SECURITY: "Security update",
            ChangeNature.DOCUMENTATION: "Documentation update only",
            ChangeNature.TESTING: "Test improvements (no visible changes to users)",
            ChangeNature.DEPENDENCY_UPDATE: "Third-party software update",
            ChangeNature.CONFIGURATION: "Settings/configuration change",
            ChangeNature.INFRASTRUCTURE: "Infrastructure/deployment change",
            ChangeNature.MIXED: "Multiple types of changes",
        }
        
        risk_friendly = {
            RiskLevel.LOW: "Low — very safe change with minimal risk",
            RiskLevel.MEDIUM: "Medium — standard change with normal testing required",
            RiskLevel.HIGH: "High — touches critical systems, needs thorough testing",
            RiskLevel.CRITICAL: "Critical — potentially breaking change, needs careful review",
        }
        
        affected_areas = ", ".join(g.name for g in analysis.change_groups) or "General"
        
        return {
            "mr_title": analysis.mr_title,
            "source_branch": analysis.source_branch,
            "target_branch": analysis.target_branch,
            "author": analysis.author or "Unknown",
            "change_nature": analysis.change_nature.value.replace("_", " ").title(),
            "change_nature_friendly": nature_friendly.get(
                analysis.change_nature, "Code changes"
            ),
            "risk_level": analysis.risk_level.value.upper(),
            "risk_level_friendly": risk_friendly.get(
                analysis.risk_level, "Unknown risk level"
            ),
            "total_files": analysis.total_files_changed,
            "mr_description": analysis.mr_description or "No description provided.",
            "commit_messages": "\n".join(
                f"- {msg}" for msg in analysis.commit_messages[:15]
            ) or "No commit messages.",
            "change_groups": groups_text or "No change groups detected.",
            "file_diffs": diffs_text,
            "has_breaking": "⚠️ YES" if analysis.has_breaking_changes else "No",
            "has_migration": "⚠️ YES" if analysis.has_migration else "No",
            "has_new_deps": "Yes" if analysis.has_new_dependencies else "No",
            "has_config": "Yes" if analysis.has_config_changes else "No",
            "has_tests": "Yes" if analysis.has_test_changes else "No",
            "affected_areas": affected_areas,
        }
    
    async def _generate_technical(
        self, context: dict, analysis: MRAnalysis,
    ) -> GeneratedDoc:
        """Generate the technical MR review document."""
        prompt = TECHNICAL_MR_PROMPT.format(**context)
        response = await self.llm.generate(prompt, TECHNICAL_MR_SYSTEM)
        
        sections = self._parse_sections(response)
        
        # Add risk badge to the title
        risk_badge = {
            RiskLevel.LOW: "🟢",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.HIGH: "🟠",
            RiskLevel.CRITICAL: "🔴",
        }.get(analysis.risk_level, "")
        
        return GeneratedDoc(
            doc_type=DocType.TECHNICAL,
            title=(
                f"MR Review: {analysis.mr_title} "
                f"{risk_badge} [{analysis.risk_level.value.upper()} RISK]"
            ),
            sections=sections,
            repo_name=analysis.mr_title,
            branch=f"{analysis.source_branch} → {analysis.target_branch}",
            commit_hash=analysis.diff.to_commit if analysis.diff else None,
        )
    
    async def _generate_non_technical(
        self, context: dict, analysis: MRAnalysis,
    ) -> GeneratedDoc:
        """Generate the non-technical MR summary."""
        prompt = NON_TECHNICAL_MR_PROMPT.format(**context)
        response = await self.llm.generate(prompt, NON_TECHNICAL_MR_SYSTEM)
        
        sections = self._parse_sections(response)
        
        nature_emoji = {
            ChangeNature.NEW_FEATURE: "✨",
            ChangeNature.BUG_FIX: "🐛",
            ChangeNature.REFACTOR: "🔧",
            ChangeNature.PERFORMANCE: "⚡",
            ChangeNature.SECURITY: "🔒",
        }.get(analysis.change_nature, "📝")
        
        return GeneratedDoc(
            doc_type=DocType.NON_TECHNICAL,
            title=f"{nature_emoji} Change Summary: {analysis.mr_title}",
            sections=sections,
            repo_name=analysis.mr_title,
            branch=f"{analysis.source_branch} → {analysis.target_branch}",
        )
    
    def _parse_sections(self, markdown: str) -> list[DocumentSection]:
        """Parse LLM markdown response into DocumentSection objects."""
        sections: list[DocumentSection] = []
        current: Optional[DocumentSection] = None
        content_lines: list[str] = []
        order = 0
        
        for line in markdown.splitlines():
            h2 = re.match(r'^##\s+(.+)', line)
            if h2:
                if current:
                    current.content = "\n".join(content_lines).strip()
                    sections.append(current)
                order += 1
                current = DocumentSection(
                    title=h2.group(1).strip().strip("*"),
                    content="",
                    order=order,
                )
                content_lines = []
            else:
                content_lines.append(line)
        
        if current:
            current.content = "\n".join(content_lines).strip()
            sections.append(current)
        
        if not sections:
            sections.append(DocumentSection(
                title="Summary",
                content=markdown.strip(),
                order=0,
            ))
        
        return sections


def save_mr_docs(
    tech_doc: GeneratedDoc,
    simple_doc: GeneratedDoc,
    output_dir: str | Path,
    branch_name: str = "",
) -> tuple[Path, Path]:
    """Save MR documents to disk with branch-based filenames.
    
    MR docs are saved with the branch name in the filename so multiple
    MR docs can coexist in the same directory without overwriting each other.
    
    Example filenames:
        MR_REVIEW_feature_add-oauth.md
        MR_SUMMARY_feature_add-oauth.md
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    
    # Sanitize branch name for use in filename
    safe_name = re.sub(r'[^\w\-.]', '_', branch_name.replace("/", "_"))
    if not safe_name:
        safe_name = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    
    tech_path = out / f"MR_REVIEW_{safe_name}.md"
    simple_path = out / f"MR_SUMMARY_{safe_name}.md"
    
    tech_path.write_text(tech_doc.to_markdown(), encoding="utf-8")
    simple_path.write_text(simple_doc.to_markdown(), encoding="utf-8")
    
    return tech_path, simple_path
