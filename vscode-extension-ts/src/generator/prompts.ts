import type { BranchDiff } from '../git/diff';
import type { RepoContext } from '../scanner/scanner';

export const SYSTEM_PROMPT = `You are a senior engineer writing documentation for code review. Be concise — every sentence must earn its place. Focus on WHY, not WHAT: the diff already shows what changed. Group changes by purpose, not by file. Never pad with filler or repeat information.`;

export function buildTechnicalPrompt(diff: BranchDiff, context: RepoContext): string {
  const languageBreakdown = Object.entries(context.languages)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5)
    .map(([lang, count]) => `${lang} (${count})`)
    .join(', ');

  return `Write a **Technical Review Doc** for branch \`${diff.currentBranch}\` (vs \`${diff.baseBranch}\`).

Target audience: a senior engineer doing code review.
Target length: 500-800 words. Do NOT exceed this.
Do NOT list every file individually. Group changes by purpose/area.
Focus on WHY decisions were made, not just WHAT code changed.

## Context

- **Project:** ${context.name} (${context.totalFiles} files, ${languageBreakdown})
- **Changed files:** ${diff.changedFiles.length}
- **Commits:** ${diff.commitMessages.length}

**Commit messages:**
${diff.commitMessages.map(m => `- ${m}`).join('\n')}

**Changed files:**
${diff.changedFiles.join(', ')}

**Diff:**
\`\`\`diff
${diff.diffContent}
\`\`\`

## Required Sections (use exactly these headings)

### What & Why
2-3 sentences: what this branch does and the motivation behind it.

### Key Changes
Group changes by area/concern (e.g., "Auth flow", "Database layer", "API surface"). For each group, explain what changed and WHY that approach was chosen. Skip trivial changes (gitignore, formatting). Use bullet points.

### Design Decisions
What tradeoffs were made? What alternatives were considered and rejected? What constraints shaped the approach? These are the things not obvious from reading the diff.

### How to Test
Concrete steps someone can follow to verify this works. Include setup steps if needed, specific commands to run, and what success looks like.

### Risks & Rollback
What could break? What's the blast radius? How to revert if something goes wrong? Any dependencies on external systems?`;
}

export function buildNonTechnicalPrompt(diff: BranchDiff, context: RepoContext): string {
  return `Write a **Non-Technical Summary** of branch \`${diff.currentBranch}\` for product managers and stakeholders.

Target audience: a product manager checking in on progress.
Target length: 200-400 words. Do NOT exceed this.
Use plain English. No jargon, no code references, no file names.
Use analogies where they help.

## Context

- **Project:** ${context.name}
- **Branch:** ${diff.currentBranch}
- **Size:** ${diff.changedFiles.length} files changed, ${diff.commitMessages.length} commits

**Commit messages:**
${diff.commitMessages.map(m => `- ${m}`).join('\n')}

**Changed files:**
${diff.changedFiles.join(', ')}

**Diff summary:**
${diff.diffSummary}

## Required Sections (use exactly these headings)

### What's Happening
One paragraph explaining what this work does. No technical terms — explain it like you're talking to a smart person who doesn't code.

### Why It Matters
Business impact. What does this enable? What problem goes away? What becomes possible that wasn't before?

### What to Expect
When will this land? Are there user-facing changes? Will anyone notice anything different? What's the rollout plan?

### Open Questions
Things that still need decision or input from stakeholders. If there are none, say "None — this is self-contained."`;
}
