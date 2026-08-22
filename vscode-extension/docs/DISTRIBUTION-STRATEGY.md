# Distribution Strategy — Three Interfaces, One Engine

> Why we built a VS Code extension (not just an AI prompt), and how the same core
> extends to CLI, MCP Server, and CI/CD — reaching different audiences with zero
> logic duplication.

---

## Why Not Just Use Claude Code / AI Prompts?

A user could type into Claude Code:

> "Analyze the diff between my current branch and mainline. Generate a technical
> doc and a summary doc. Push both to my Confluence page."

This works. So why build an extension?

### The Honest Comparison

| Aspect | Claude Code / AI Prompt | This Extension |
|--------|------------------------|----------------|
| **Fixed cost** | $20-200/mo (Claude subscription) | $0 (extension is free to install) |
| **Per-run token cost** | ~50-100K tokens ($0.15-0.60) | ~10-15K tokens ($0.03-0.08) |
| **Why more tokens?** | AI thinks, plans, runs git commands, formats, retries, calls APIs | Only 1 focused LLM call. Everything else is deterministic code. |
| **Speed** | 2-5 minutes (multiple tool calls) | ~39 seconds (optimized pipeline) |
| **Consistency** | Different format/structure each run | Same structure every time |
| **Reliability** | AI might hallucinate a git flag or misformat an API call | Deterministic pipeline — only doc generation is AI |
| **Who can use it** | People who know how to prompt AI | Anyone who can click a button |
| **Credential security** | Token pasted into chat (stored in conversation history) | OS keychain encryption (never visible) |
| **Team scale** | Each person needs AI subscription + knows the prompt | Install extension → click Run |
| **Works without AI client** | No — needs Claude/GPT running | Yes — standalone |
| **Discoverable** | Nobody can find your prompt | 35M VS Code users search "doc generator" |
| **Monetizable** | Can't sell a prompt | Can sell/license an extension |

### Token Cost Breakdown

Why 5x cheaper:

```
Claude Code approach (per run):
  - Read prompt, think about approach        ~2K tokens
  - Run git commands (3-4 tool calls)        ~5K tokens
  - Read and process diff                    ~15K tokens
  - Think about doc structure                ~3K tokens
  - Generate technical doc                   ~8K tokens
  - Generate summary doc                     ~5K tokens
  - Format Confluence API call               ~3K tokens
  - Execute API calls (2 tool calls)         ~5K tokens
  - Summarize result to user                 ~2K tokens
  Total: ~48-100K tokens

Extension approach (per run):
  - Git diff extraction                      0 tokens (code)
  - Repo scanning                            0 tokens (code)
  - Generate both docs (1 LLM call)          ~10-15K tokens
  - Publish to Confluence                    0 tokens (code)
  Total: ~10-15K tokens
```

The extension only uses AI for what AI is good at (writing). Everything else is deterministic code that runs instantly and never fails randomly.

### Monthly Cost Example

Developer generating docs 5x/day, 22 working days:

| Approach | Monthly Cost |
|----------|-------------|
| Claude Code | $20 subscription + ~$15-90 in tokens = **$35-110/mo** |
| Extension + Anthropic API | ~$3-9 in tokens = **$3-9/mo** |
| Extension + Bedrock | Similar, via AWS billing |
| Extension + Ollama (future) | **$0/mo** (local model, no API) |

### The Restaurant Analogy

**What you built is the difference between knowing how to cook and opening a restaurant.**

- Capability (Claude prompt): "I can do this thing"
- Product (Extension): "This does it for you, reliably, every time, for anyone, at scale"

Excel can do what most SaaS analytics tools do. But people pay for Tableau because it's a *product* — consistent, shareable, no expertise required.

---

## What's Already Built vs What's VS Code-Specific

```
src/
├── extension.ts          ← VS Code specific (orchestration)
├── webview/              ← VS Code specific (sidebar UI)
├── config/wizard.ts      ← VS Code specific (setup webview)
├── config/secrets.ts     ← VS Code specific (SecretStorage)
│
│   ──── everything below is PURE TypeScript, no VS Code import ────
│
├── git/diff.ts           ← just execFile("git", ...)
├── scanner/scanner.ts    ← just fs/path operations
├── llm/provider.ts       ← just HTTP calls
├── generator/generator.ts← just string templates + LLM call
├── publisher/confluence.ts← just HTTP calls
└── tracker/tracker.ts    ← just key-value read/write
```

~70% of the codebase is already portable. The "engine" doesn't know it's inside VS Code.

---

## The Three Interfaces

```
                    ┌─── VS Code Extension (button click → sidebar UI)
                    │    WHO: Developers in VS Code
                    │    WHEN: Daily, during development
                    │
Same core engine ───┼─── CLI Tool (terminal command → stdout)
(already built)     │    WHO: CI/CD pipelines, automation scripts
                    │    WHEN: On every PR merge, scheduled, scripted
                    │
                    └─── MCP Server (AI tool call → structured return)
                         WHO: AI assistants (Claude, Cursor, Copilot)
                         WHEN: As part of larger AI-orchestrated workflows
```

### Interface 1: VS Code Extension (DONE)

**Audience:** Individual developers who want a GUI

**Experience:**
1. Install from marketplace (one click)
2. Setup wizard (one time)
3. Click "Run" → see progress → get links to docs

**Unique value:** Visual feedback, cancel button, result links, keyboard shortcuts, settings UI, marketplace distribution.

### Interface 2: CLI Tool (FUTURE — ~1 day effort)

**Audience:** CI/CD pipelines, DevOps, automation

**Experience:**
```bash
# In a GitHub Action:
npx @repodoc/cli generate \
  --provider anthropic \
  --api-key ${{ secrets.ANTHROPIC_KEY }} \
  --confluence-url https://company.atlassian.net/wiki \
  --confluence-token ${{ secrets.CONFLUENCE_TOKEN }} \
  --space-key ENG
```

**Unique value:** No human in the loop. Docs are always up to date. Every merged PR gets documented automatically.

**Real-world CI example:**
```yaml
# .github/workflows/auto-docs.yml
name: Auto-generate branch docs
on:
  pull_request:
    types: [closed]
    branches: [main, mainline]

jobs:
  docs:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # need full history for diff
      - run: npx @repodoc/cli generate --branch ${{ github.head_ref }}
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_KEY }}
          CONFLUENCE_TOKEN: ${{ secrets.CONFLUENCE_TOKEN }}
```

### Interface 3: MCP Server (FUTURE — ~1-2 days effort)

**Audience:** AI assistants and their users

**Experience:**
```
User to Claude: "Generate docs for my feature branch, post a summary to 
#engineering in Slack, and update the PR description with a link."

Claude: [calls generate_branch_docs tool] → [calls slack_post_message] → [calls gh_pr_edit]
```

**Unique value:** Composability. Your doc generator becomes one tool in a larger AI-orchestrated workflow. The AI handles the "glue" between tools.

**MCP tool definitions:**
```typescript
// Tools exposed:
"generate_branch_docs"  — generates and publishes docs, returns URLs
"get_last_docs"         — returns URLs of last generated docs for a branch
"list_documented_branches" — shows all branches with existing docs
"update_docs"           — re-generates docs for an already-documented branch
```

---

## Build Order

| # | Step | Effort | Depends On |
|---|------|--------|------------|
| 1 | Extract `@repodoc/core` package (move pure modules out) | Half day | — |
| 2 | CLI tool (wraps core + arg parsing + env var config) | 1 day | #1 |
| 3 | GitHub Action (wraps CLI in a container) | Half day | #2 |
| 4 | MCP Server (wraps core + MCP SDK + tool schemas) | 1-2 days | #1 |
| 5 | GitLab CI template | Half day | #2 |

Total: ~3-4 days to have all three interfaces + CI integrations.

---

## When to Use Which

| Situation | Best Interface |
|-----------|---------------|
| "I want to document my branch right now" | Extension (click Run) |
| "Every merged PR should auto-generate docs" | CLI in GitHub Action |
| "Generate docs AND do 3 other things" | MCP Server (AI composes) |
| "New dev on team, never used AI tools" | Extension (one-click install, GUI) |
| "I want docs in my terminal without opening VS Code" | CLI |
| "Document all branches from the last sprint" | CLI in a loop / MCP batch |
| "Company policy: no external AI subscriptions" | Extension + Ollama (future) |

---

## Summary

The extension is not "just a wrapper around a prompt." It's a **product** that:

1. **Costs 5x less per run** than doing it via AI prompt (fewer tokens)
2. **Works without AI subscription** (just an API key, or Ollama for free)
3. **Scales to teams** without per-person AI subscriptions
4. **Is consistent** — same output structure every time
5. **Is distributable** — marketplace, one-click install, ratings/reviews
6. **Is monetizable** — you can't charge for a prompt
7. **Is composable** — same engine powers GUI, CLI, and AI tool interfaces
8. **Is secure** — OS keychain, no tokens in chat history

The three-interface strategy means you reach every audience:
- Developers who want a button → Extension
- Pipelines that want automation → CLI
- AI assistants that want tools → MCP Server

All sharing one codebase, one set of tests, one set of bug fixes.
