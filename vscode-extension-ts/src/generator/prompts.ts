import type { BranchDiff } from '../git/diff';
import type { RepoContext } from '../scanner/scanner';

export const SYSTEM_PROMPT = `You are a senior technical writer specializing in software documentation. You produce clear, structured, and actionable documentation from code changes. Your output is always in Markdown format with proper headings, lists, and code blocks. Be specific — reference actual file names, function names, and architectural patterns. Never pad with generic filler.`;

export function buildTechnicalPrompt(diff: BranchDiff, context: RepoContext): string {
  const languageBreakdown = Object.entries(context.languages)
    .sort(([, a], [, b]) => b - a)
    .map(([lang, count]) => `  - ${lang}: ${count} files`)
    .join('\n');

  return `Generate a **Technical Documentation** page for the changes in branch \`${diff.currentBranch}\` compared to \`${diff.baseBranch}\`.

## Repository Context

- **Project:** ${context.name}
- **Total files:** ${context.totalFiles} (${context.totalLines} lines)
- **Languages:**
${languageBreakdown}
- **Key files:** ${context.keyFiles.join(', ')}
- **Structure:**
\`\`\`
${context.structure}
\`\`\`

## Branch Changes

**Changed files (${diff.changedFiles.length}):**
${diff.changedFiles.map(f => `- ${f}`).join('\n')}

**Commit messages:**
${diff.commitMessages.map(m => `- ${m}`).join('\n')}

**Diff summary:**
${diff.diffSummary}

**Full diff:**
\`\`\`diff
${diff.diffContent}
\`\`\`

## Required Sections

Write the documentation with these sections:

### 1. Summary
What does this branch do? One paragraph overview.

### 2. Files Changed
For each changed file, explain what was modified and why it matters.

### 3. Architecture & Data Flow Impact
How do these changes affect the system's architecture or data flow? Include a mermaid diagram if the changes are structural.

### 4. API Changes
List any new, modified, or removed endpoints/interfaces/contracts. If none, state "No API changes."

### 5. Testing Considerations
What should be tested? What edge cases exist? What regression risks are there?

### 6. Deployment Notes
Any migration steps, environment variable changes, feature flags, or rollback considerations.`;
}

export function buildNonTechnicalPrompt(diff: BranchDiff, context: RepoContext): string {
  return `Generate a **Non-Technical Summary** of the changes in branch \`${diff.currentBranch}\` compared to \`${diff.baseBranch}\`.

This document is for product managers, leadership, and non-engineering stakeholders. Use plain English, no jargon, and explain with analogies where helpful.

## Context

- **Project:** ${context.name}
- **Branch:** ${diff.currentBranch}
- **Files changed:** ${diff.changedFiles.length}

**Commit messages:**
${diff.commitMessages.map(m => `- ${m}`).join('\n')}

**Changed files:**
${diff.changedFiles.map(f => `- ${f}`).join('\n')}

**Diff summary:**
${diff.diffSummary}

**Full diff:**
\`\`\`diff
${diff.diffContent}
\`\`\`

## Required Sections

Write the summary with these sections:

### 1. What's Changing (Plain English)
Explain what this branch does as if talking to someone with no coding background. Use analogies.

### 2. What Problem Does This Solve?
Why is this work being done? What was broken or missing before?

### 3. User-Facing Impact
Will users notice anything different? Is this a visible change or behind-the-scenes?

### 4. Risks & Considerations
What could go wrong? What should stakeholders be aware of?

### 5. Effort & Scope
How big is this change? (Small tweak, medium feature, large restructure)`;
}
