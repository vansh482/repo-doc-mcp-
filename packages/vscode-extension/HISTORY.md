# Project History & Design Decisions

This file tracks the evolution of this VS Code extension — what was decided, why, and what's left. Any agent or developer picking this up should read this first.

---

## 2026-08-20 — Initial Architecture Decision

### Context
The parent project (`repo-doc-mcp`) is a Python-based MCP server that generates AI-powered documentation for codebases. It supports full repo scanning, branch-aware docs, Confluence/Google Docs publishing, and had prototype VS Code/IntelliJ extensions. This folder (`vscode-extension/`) is the canonical TypeScript rewrite that replaced those prototypes.

### Decision: Rewrite in TypeScript (not bundle Python)
**Why:**
- Target is VS Code Marketplace — anyone should be able to install with zero external dependencies
- Python dependency (3.10+) is a barrier for many users
- The core workflow is: git diff → LLM API call → Confluence API call — all straightforward in TS
- VS Code's native APIs (file watchers, git integration, SecretStorage) are TS-first
- Future plans include real-time monitoring, monetization — all easier without subprocess overhead

**Trade-off accepted:** More upfront work vs. reusing tested Python code. Worth it for distribution and future extensibility.

### Decision: Confluence only (not Google Docs)
**Why:** Scope reduction for v1. Google Docs can be added later as a separate publisher module.

### Decision: VS Code only (not IntelliJ)
**Why:** Focus on one platform, ship faster. IntelliJ plugin remains in `../mcp/mcp5/` for future reference.

### Decision: API Token auth for Confluence (OAuth later)
**Why:** OAuth requires Atlassian app registration, callback URLs, and significantly more complexity. API token auth works today and covers most use cases. OAuth will be added as a future enhancement.

### Decision: Support Anthropic + OpenAI + AWS Bedrock
**Why:** Covers the three main enterprise LLM providers. Ollama (local) excluded from v1 for simplicity.

---

## Architecture

```
src/
├── extension.ts          — VS Code activation, command registration
├── config/
│   ├── wizard.ts         — First-run setup wizard (webview)
│   ├── settings.ts       — Settings management, defaults
│   └── secrets.ts        — VS Code SecretStorage wrapper for API keys
├── git/
│   └── diff.ts           — Branch detection, diff extraction vs main
├── scanner/
│   └── scanner.ts        — Repo file walking, language detection, structure mapping
├── llm/
│   ├── provider.ts       — Abstract provider interface
│   ├── anthropic.ts      — Anthropic Claude implementation
│   ├── openai.ts         — OpenAI implementation
│   └── bedrock.ts        — AWS Bedrock implementation
├── generator/
│   ├── prompts.ts        — Prompt templates for tech/non-tech docs
│   └── generator.ts      — Orchestrates scanning + LLM calls → docs
├── publisher/
│   └── confluence.ts     — Confluence REST API (create/update pages)
├── tracker/
│   └── tracker.ts        — Maps branch → Confluence page IDs (workspace state)
└── webview/
    └── sidebar.ts        — Activity bar sidebar panel
```

### Data Flow
```
User clicks "Run"
    │
    ▼
Git module: detect current branch, compute diff vs main/master
    │
    ▼
Scanner: walk repo for structural context (languages, key files, architecture)
    │
    ▼
Generator: build prompts with diff + context, call LLM
    │
    ├── Technical doc (for engineers)
    └── Non-technical doc (for PMs/stakeholders)
    │
    ▼
Tracker: check if this branch already has Confluence pages
    │
    ├── YES → Publisher: update existing pages
    └── NO  → Publisher: create new pages, save IDs to tracker
```

---

## Scope — What's IN for v1

- [x] Setup wizard on first run (LLM provider, API key, Confluence credentials)
- [x] "Run" command that generates 2 docs from branch diff
- [x] Confluence publishing (create + update)
- [x] Branch → page ID tracking (same branch = update, not duplicate)
- [x] Activity bar sidebar with status
- [x] Support for Anthropic, OpenAI, Bedrock
- [x] SecretStorage for sensitive credentials
- [x] Progress indicator during generation

## Scope — What's OUT for v1 (future)

- [ ] OAuth for Confluence
- [ ] Google Docs publisher
- [ ] Real-time file watching (auto-regen on save)
- [ ] Monetization / usage tracking
- [ ] IntelliJ plugin
- [ ] Ollama (local LLM) support
- [ ] Custom prompt templates
- [ ] Streaming LLM output in UI
- [ ] Multi-workspace support
- [ ] VS Code Marketplace publishing automation

---

## 2026-08-20 — UX Improvements (same day)

### Changes
1. **Setup wizard → Webview form** — Replaced sequential `showInputBox` calls with a persistent webview panel. All fields visible at once, stays open when switching windows.
2. **Progress indicator** — Added step numbering (Step 1/5 through 5/5), elapsed time display, visual progress bar, and cancel button.
3. **Doc quality** — Rewrote prompts to be concise (500-800 words technical, 200-400 words non-technical). Focus on WHY/decisions/risks, not per-file listings.
4. **Confluence formatting** — Improved markdown→XHTML converter: proper tables, mermaid diagram handling, nested/ordered lists, links, horizontal rules.

### Why
- Input boxes disappear on focus loss — unacceptable for 7-step setup
- Users couldn't tell if generation was stuck or working
- Initial doc output was 3000+ words with per-file breakdowns nobody reads
- Tables/diagrams rendered broken in Confluence

---

## 2026-08-20 — Folder Rename & Cleanup

### Changes
- Deleted old `vscode-extension/` (the Python-dependent prototype from 2 months ago)
- Renamed `vscode-extension-ts/` → `vscode-extension/` (now the canonical location)
- Merged everything to `main`

### Why
Having two extension folders was confusing. The old prototype is fully superseded — the new TypeScript version is self-contained and working.

---

## 2026-08-20 — Legacy Cleanup

### Changes
- Removed entire Python backend (`src/`, `tests/`, `pyproject.toml`, `requirements.txt`)
- Removed IntelliJ plugin (`intellij-plugin/`)
- Removed legacy docs (`docs/`, `PROJECT_GUIDE.md`, `TESTING.md`, `repo-doc-mcp.example.yaml`)
- Moved `repo-doc-mcp.yaml` (contains real API keys) to `.local-secrets/` (gitignored)
- Cleaned up `.gitignore` — removed Python/IntelliJ rules, added `.local-secrets/`
- Added `TODO.md` with comprehensive future roadmap
- Updated root `README.md` with current state and visual elements
- Removed stray root-level `package-lock.json`

### Why
The Python backend, IntelliJ plugin, and MCP server are fully superseded by the TypeScript VS Code extension. Keeping them around was confusing (gave the impression they were active code) and added noise to the repo. The extension is self-contained — all functionality lives in `vscode-extension/`.

### What's Left in the Repo
```
repo-doc-mcp/
├── .gitignore
├── README.md                    ← Project overview (points to extension)
└── vscode-extension/            ← The entire product
    ├── src/                     ← All source code
    ├── package.json             ← Extension manifest
    ├── tsconfig.json            ← TypeScript config
    ├── HISTORY.md               ← This file
    ├── TODO.md                  ← Future roadmap
    └── README.md                ← Developer docs
```

### Local-only (not in git)
- `.local-secrets/repo-doc-mcp.yaml` — Contains real API keys for local testing

---

## How to Continue This Project

1. Read this file for context
2. Check `README.md` for setup/development instructions
3. The extension is TypeScript — `npm install`, `npm run compile`, F5 to debug
4. Key design principle: each module is independent and testable in isolation
5. Confluence page IDs are stored in VS Code's `workspaceState` — they persist per-workspace but don't sync across machines
