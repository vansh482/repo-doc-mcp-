# Repo Doc Generator — Complete Project Guide

## What This Project Does

Repo Doc Generator is an AI-powered tool that scans any code repository and automatically generates two types of documentation:

1. **Technical Documentation** — For engineers: architecture diagrams, API references, data flow, setup guides
2. **Non-Technical Guide** — For PMs/stakeholders: plain English explanations with analogies, no jargon

It can publish the generated docs to **Confluence** and/or **Google Docs**, or save them locally as Markdown files.

The system is built as an **MCP server** (Model Context Protocol — Anthropic's standard for tool-based AI integrations) with IDE extensions for **VS Code** and **IntelliJ/JetBrains IDEs**.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        IDE Extensions                           │
│                                                                 │
│   ┌──────────────────┐          ┌──────────────────────┐       │
│   │  VS Code Extension│          │  IntelliJ Plugin     │       │
│   │  (TypeScript)     │          │  (Kotlin)            │       │
│   │                   │          │                      │       │
│   │  - 6 commands     │          │  - 7 actions         │       │
│   │  - Sidebar panel  │          │  - Tool window       │       │
│   │  - Doc viewer     │          │  - Doc viewer        │       │
│   │  - Settings UI    │          │  - Settings page     │       │
│   └────────┬──────────┘          └──────────┬───────────┘       │
│            │                                │                   │
│            │         JSON-RPC / stdin-stdout │                   │
│            └────────────────┬───────────────┘                   │
│                             ▼                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              Python MCP Server (subprocess)              │   │
│   │                                                          │   │
│   │  Scanner ──→ Analyzer ──→ Generator ──→ Publisher        │   │
│   │  (regex)     (LLM)       (LLM)         (Confluence/     │   │
│   │                                          Google Docs)    │   │
│   │                                                          │   │
│   │  11 MCP Tools:                                           │   │
│   │  - generate_docs, generate_technical_doc                 │   │
│   │  - generate_non_technical_doc, get_repo_summary          │   │
│   │  - list_config, update_config                            │   │
│   │  - check_and_update_docs, install_git_hooks              │   │
│   │  - generate_ci_workflow                                  │   │
│   │  - generate_mr_docs, generate_mr_docs_from_commits       │   │
│   └─────────────────────────────────────────────────────────┘   │
│                             │                                   │
│                    ┌────────┴────────┐                          │
│                    ▼                 ▼                          │
│            ┌──────────────┐  ┌──────────────┐                  │
│            │  Confluence   │  │  Google Docs  │                  │
│            │  (REST API)   │  │  (Batch API)  │                  │
│            └──────────────┘  └──────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
repo-doc-mcp/
├── src/
│   ├── config/settings.py          # Pydantic config (LLM, repo, doc, publish settings)
│   ├── core/models.py              # Data models (RepoTree, RepoFile, GeneratedDoc)
│   ├── parsers/
│   │   ├── scanner.py              # Scans repo files (65+ language extensions)
│   │   └── analyzer.py             # Code analysis (regex patterns + LLM summarization)
│   ├── llm/providers.py            # LLM abstraction (Anthropic, OpenAI, Ollama)
│   ├── generators/
│   │   ├── prompts.py              # LLM prompt templates for doc generation
│   │   └── doc_generator.py        # Orchestrates doc generation pipeline
│   ├── mcp_server/server.py        # MCP server with all 11 tools
│   ├── publishers/
│   │   ├── confluence.py           # Confluence publisher (markdown → XHTML storage format)
│   │   ├── google_docs.py          # Google Docs publisher (markdown → batch update API)
│   │   └── cli.py                  # Publish orchestrator CLI
│   ├── watcher/
│   │   ├── git_diff.py             # Git diff engine, ChangeScope detection
│   │   ├── incremental.py          # Incremental doc updates (3-tier: cosmetic/content/structural)
│   │   ├── watcher.py              # Branch watcher, git hook installer
│   │   └── cli.py                  # Watcher CLI
│   ├── mr_docs/
│   │   ├── mr_analyzer.py          # MR diff analysis, risk levels, feature grouping
│   │   ├── mr_generator.py         # Per-MR documentation generator
│   │   └── cli.py                  # MR docs CLI
│   └── cli.py                      # Main CLI entry point
│
├── tests/                          # 60 tests (all passing)
│   ├── test_scanner.py
│   ├── test_providers.py
│   ├── test_watcher.py
│   └── test_mr_docs.py
│
├── vscode-extension/               # VS Code extension (TypeScript)
│   ├── package.json                # Extension manifest, commands, settings
│   ├── tsconfig.json
│   └── src/
│       ├── extension.ts            # Entry point, registers 6 commands
│       ├── mcpClient.ts            # Spawns Python subprocess, JSON-RPC
│       └── webview/
│           ├── docViewer.ts        # Webview panel with tabs, TOC, Mermaid diagrams
│           └── sidebarProvider.ts  # Activity bar sidebar with action buttons
│
├── intellij-plugin/                # IntelliJ/JetBrains plugin (Kotlin)
│   ├── build.gradle.kts
│   ├── settings.gradle.kts
│   └── src/main/
│       ├── kotlin/com/repodoc/
│       │   ├── actions/            # 7 action classes (GenerateDocs, MRDocs, etc.)
│       │   ├── mcp/MCPClient.kt   # Same subprocess pattern as VS Code
│       │   ├── ui/                 # DocViewerPanel, SettingsConfigurable
│       │   └── services/           # RepoDocService (project-level singleton)
│       └── resources/
│           ├── META-INF/plugin.xml # Plugin manifest
│           └── icons/repodoc.svg
│
├── pyproject.toml                  # Python package config, entry points
├── repo-doc-mcp.yaml              # Your local config (DO NOT commit — has API keys)
├── repo-doc-mcp.example.yaml      # Example config template
└── TESTING.md                      # Step-by-step testing guide
```

---

## What Was Built (Phase by Phase)

| Phase | What It Does | Key Files |
|-------|-------------|-----------|
| **Phase 1** — MCP Server Core | Scan repos, analyze code with LLM, generate docs as Markdown | `src/parsers/`, `src/llm/`, `src/generators/`, `src/mcp_server/` |
| **Phase 2** — VS Code Extension | TypeScript extension with commands, sidebar, doc viewer webview | `vscode-extension/` |
| **Phase 3** — Auto-Update System | Git hooks, branch watcher, incremental doc updates (3-tier) | `src/watcher/` |
| **Phase 4** — Per-MR Documentation | Generate focused docs for merge requests, risk analysis | `src/mr_docs/` |
| **Phase 5** — IntelliJ Plugin | Kotlin plugin with actions, tool window, settings page | `intellij-plugin/` |
| **Phase 6** — Publishing | Publish docs to Confluence and/or Google Docs | `src/publishers/` |

---

## How to Run

### Prerequisites

- Python 3.10+
- Node.js 18+ (for VS Code extension)
- An LLM API key (Anthropic, OpenAI) OR Ollama installed locally

### 1. Python Backend Setup

```bash
cd repo-doc-mcp

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package with all dependencies
pip install -e ".[publish]"     # includes Google Docs deps
# OR
pip install -e .                 # without Google Docs deps

# Copy and edit config
cp repo-doc-mcp.example.yaml repo-doc-mcp.yaml
# Edit repo-doc-mcp.yaml — add your LLM API key and publisher config
```

### 2. Run from CLI (no IDE needed)

```bash
# Quick repo summary (no LLM needed)
python -m src.cli /path/to/any/repo --summary-only

# Generate docs (needs LLM API key or Ollama)
python -m src.cli /path/to/any/repo --type both

# Generate and publish to Confluence
python -m src.publishers.cli /path/to/any/repo --confluence-only

# Generate and publish to Google Docs
python -m src.publishers.cli /path/to/any/repo --google-docs-only

# Publish already-generated docs (skip re-generation)
python -m src.publishers.cli /path/to/any/repo --publish-only

# Use a different LLM provider
python -m src.publishers.cli /path/to/repo --provider ollama --model llama3.1
python -m src.publishers.cli /path/to/repo --provider openai --model gpt-4o
```

### 3. Run Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
# Expected: 60 passed
```

### 4. VS Code Extension (local dev)

```bash
cd vscode-extension
npm install
npm run compile

# Then press F5 in VS Code to launch the extension in a dev host
# Commands available via Cmd+Shift+P → "Repo Doc: ..."
```

### 5. IntelliJ Plugin (local dev)

```bash
cd intellij-plugin
./gradlew runIde
# This opens a sandboxed IntelliJ instance with the plugin loaded
# Actions available via Tools → Repo Doc
```

---

## Configuration

All settings go in `repo-doc-mcp.yaml` (see `repo-doc-mcp.example.yaml` for the full template).

```yaml
llm:
  provider: "anthropic"          # or "openai" or "ollama"
  api_key: "sk-ant-..."          # or use env var ANTHROPIC_API_KEY
  model: "claude-sonnet-4-20250514"

repo:
  max_files: 500
  max_file_size_kb: 500

doc:
  output_dir: "./docs/generated"
  include_architecture_diagram: true

publish:
  confluence:
    enabled: true
    url: "https://yourcompany.atlassian.net"
    email: "you@company.com"
    api_token: "your-atlassian-api-token"
    space_key: "ENG"
  google_docs:
    enabled: false
    credentials_file: "/path/to/service-account.json"
    folder_id: "google-drive-folder-id"
```

---

## Publishing the VS Code Extension to the Marketplace

### Step 1: Create a Publisher Account

1. Go to https://marketplace.visualstudio.com/manage
2. Sign in with a Microsoft account (or create one)
3. Create a **publisher** — this is your unique publisher ID (e.g., `vansh-gupta` or `repo-doc`)
4. Update `package.json` → `"publisher"` field to match your publisher ID

### Step 2: Get a Personal Access Token (PAT)

1. Go to https://dev.azure.com
2. Sign in with the same Microsoft account
3. Click your profile icon → **Personal Access Tokens**
4. Create a new token:
   - **Organization**: Select "All accessible organizations"
   - **Scopes**: Select "Custom defined" → check **Marketplace → Manage**
   - **Expiration**: Set a reasonable expiry
5. Copy the token (you won't see it again)

### Step 3: Prepare the Extension

```bash
cd vscode-extension

# Update package.json:
#   - "publisher": "your-publisher-id"
#   - "repository": { "type": "git", "url": "https://github.com/you/repo-doc-mcp" }
#   - Add an icon: "icon": "media/icon.png" (128x128 PNG)

# Install the packaging tool
npm install -g @vscode/vsce

# Login with your PAT
vsce login your-publisher-id

# Package (creates a .vsix file)
vsce package

# Test locally first:
code --install-extension repo-doc-generator-0.1.0.vsix
```

### Step 4: Publish

```bash
# Publish to the marketplace
vsce publish

# Or publish a specific version
vsce publish 0.1.0
```

### Step 5: Post-Publish Checklist

- [ ] Add a `README.md` inside `vscode-extension/` (this becomes the marketplace listing page)
- [ ] Add a `CHANGELOG.md` for version history
- [ ] Add a `LICENSE` file
- [ ] Add an icon (128x128 PNG) at `vscode-extension/media/icon.png`
- [ ] Add screenshots/GIFs showing the extension in action
- [ ] Set up CI/CD (GitHub Actions) to auto-publish on git tags

### Marketplace Listing Tips

- The `README.md` in the extension folder becomes your marketplace page
- Include screenshots/GIFs — they dramatically improve install rates
- Add badges (build status, version, installs)
- Write clear "Getting Started" instructions
- List features with screenshots

---

## Making It a Paid Product

### Option A: VS Code Extension Marketplace (No Built-In Payments)

The VS Code Marketplace does **not** support paid extensions natively. You need to handle payments yourself. Common approaches:

#### A1. License Key Model

```
User buys license on your website
    → Gets a license key
    → Enters key in VS Code extension settings
    → Extension validates key against your server
    → Unlocks full functionality
```

**What you need to build:**

1. **License server** (API that validates keys):
   - `POST /api/licenses/validate` — checks if a key is valid
   - `POST /api/licenses/create` — creates a key after payment
   - Store: license key, email, plan type, expiry, usage count

2. **Payment integration** (pick one):
   - **Stripe** — best for SaaS/subscriptions. Use Stripe Checkout for a hosted payment page
   - **Lemonsqueezy** — simpler than Stripe, built for software products, handles VAT/tax
   - **Gumroad** — simplest, but higher fees

3. **Landing page / website** where users:
   - See pricing
   - Click "Buy" → redirect to Stripe/Lemonsqueezy checkout
   - After payment → webhook fires → your server generates a license key → emails it

4. **Extension changes**:
   - Add a `repoDoc.licenseKey` setting
   - On activation, validate the key against your server
   - Free tier: allow `--summary-only` (no LLM calls, no publishing)
   - Paid tier: unlock full generation + publishing

#### A2. Per-Page/Per-Generation Payment (Usage-Based)

```
User generates docs
    → Extension calls your server to check credits
    → If credits > 0: generate docs, deduct 1 credit
    → If credits = 0: show "Buy more credits" prompt
```

**What you need to build:**

1. **Credits/usage server**:
   - `GET /api/usage/{user_id}` — check remaining credits
   - `POST /api/usage/{user_id}/deduct` — deduct after generation
   - `POST /api/webhooks/stripe` — add credits after payment

2. **User account system**:
   - Users sign in via GitHub OAuth or email
   - Extension stores auth token in VS Code's `SecretStorage`
   - Each generation checks credits before proceeding

3. **Pricing page** with credit packs:
   - 10 generations — $9
   - 50 generations — $29
   - Unlimited (monthly) — $19/mo

4. **Extension changes**:
   - Add sign-in flow (OAuth redirect or token input)
   - Before each generation: `GET /api/usage` to check credits
   - After generation: `POST /api/usage/deduct`
   - Show remaining credits in the status bar

### Option B: Enterprise Licensing (Per-Seat / Per-Org)

For enterprise customers who want to deploy it across their org:

```
Company admin buys N seats
    → Gets an org API key or SSO integration
    → Each developer's extension validates via org key
    → Central billing, usage dashboard for admin
```

**What you need to build:**

1. **Organization management API**:
   - `POST /api/orgs` — create org after enterprise purchase
   - `GET /api/orgs/{id}/seats` — list seats, usage
   - `POST /api/orgs/{id}/seats` — add/remove developers
   - `GET /api/orgs/{id}/usage` — usage dashboard data

2. **Admin dashboard** (web app):
   - See total generations across the org
   - Add/remove developer seats
   - Billing management (upgrade seats, invoices)
   - Set org-wide LLM provider config

3. **SSO integration** (for enterprise):
   - SAML or OpenID Connect integration
   - Map company domains to orgs automatically

4. **Pricing model**:
   - **Per-seat**: $15/developer/month (min 5 seats)
   - **Per-org unlimited**: $299/month (unlimited developers)
   - **Enterprise custom**: Contact sales (includes SSO, SLA, dedicated support)

### Recommended Approach for Starting

**Start simple. Iterate.**

1. **Phase 1** — Free extension, open source. Get users and feedback.
2. **Phase 2** — Add a "Pro" tier with license keys via Lemonsqueezy:
   - Free: summary-only, max 20 files
   - Pro ($9/mo): unlimited generation + Confluence/Google Docs publishing
3. **Phase 3** — Add usage-based credits for per-page billing
4. **Phase 4** — Add enterprise tier with org management

### Minimum Tech Stack for Monetization

| Component | Recommended Tool | Why |
|-----------|-----------------|-----|
| Payments | Lemonsqueezy or Stripe | Handles checkout, subscriptions, tax |
| License server | Simple Express/FastAPI app | Validate keys, track usage |
| Hosting | Vercel (website) + Railway/Fly.io (API) | Cheap, easy deployment |
| Database | PostgreSQL (via Supabase or Neon) | Free tier is enough to start |
| Auth | GitHub OAuth | Your users are developers |
| Email | Resend | Sends license keys after purchase |

---

## Additional Things to Build for a Production-Ready Product

### Must-Haves Before Going Live

- [ ] **Error handling in the extension** — friendly error messages, not stack traces
- [ ] **Loading indicators** — progress bar during doc generation (can take 30-120 seconds)
- [ ] **Telemetry/analytics** — track how many users, generations per day, which LLM provider is popular
- [ ] **Rate limiting** — prevent abuse of your LLM API keys
- [ ] **Extension icon** — 128x128 PNG for the marketplace
- [ ] **Screenshots/GIFs** — show the extension in action on the marketplace listing
- [ ] **README for marketplace** — clear "Getting Started" guide
- [ ] **BYOK (Bring Your Own Key)** — let users use their own LLM API keys instead of yours
- [ ] **Bundling** — use esbuild/webpack to bundle the extension (faster load, smaller size)

### Nice-to-Haves

- [ ] **Caching** — don't re-scan unchanged files on subsequent generations
- [ ] **Streaming output** — show docs being generated in real-time instead of waiting
- [ ] **Custom templates** — let users customize the doc format/structure
- [ ] **Multi-language support** — generate docs in Spanish, French, etc.
- [ ] **GitHub Actions integration** — auto-generate docs on every PR
- [ ] **Diff-aware updates** — only regenerate sections that changed (Phase 3's watcher does this partially)

---

## Quick Reference — All CLI Commands

```bash
# Repo scanning (no LLM needed)
python -m src.cli /path/to/repo --summary-only

# Full doc generation
python -m src.cli /path/to/repo --type both
python -m src.cli /path/to/repo --type technical
python -m src.cli /path/to/repo --type non-technical

# Generate + publish
python -m src.publishers.cli /path/to/repo
python -m src.publishers.cli /path/to/repo --confluence-only
python -m src.publishers.cli /path/to/repo --google-docs-only
python -m src.publishers.cli /path/to/repo --publish-only

# MR documentation
python -m src.mr_docs.cli /path/to/repo --base main --head feature-branch

# Watch for changes
python -m src.watcher.cli /path/to/repo --branch main

# Run as MCP server (for IDE extensions)
python -m src.mcp_server.server

# Run tests
python -m pytest tests/ -v
```

---

## Auto-Scan & Branch-Aware Documentation (Core Vision)

The original vision for this extension is:

> **Automatically keep mainline docs up-to-date, and generate a separate doc for the current working branch — all without manual triggers.**

### What Already Exists (Phase 3 — Watcher System)

The auto-update infrastructure is **already built**:

| Component | File | What It Does |
|-----------|------|-------------|
| `BranchWatcher` | `src/watcher/watcher.py` | Polls a branch every N minutes for new commits, triggers updates |
| `IncrementalUpdater` | `src/watcher/incremental.py` | 3-tier smart updates: cosmetic (skip), content (partial regen), structural (full regen) |
| `GitDiffEngine` | `src/watcher/git_diff.py` | Computes diffs between commits, classifies change scope |
| `DocState` | `src/watcher/incremental.py` | Tracks which commit was last documented (persisted as `.repo-doc-state.json`) |
| `GitHookInstaller` | `src/watcher/watcher.py` | Installs `post-merge` / `post-receive` git hooks for event-driven updates |
| GitHub Actions generator | `src/watcher/watcher.py` | Generates a CI/CD workflow YAML for auto-updating docs on merge |

### How It Works Today

```bash
# MODE 1: Polling — runs as a background daemon, checks every 5 minutes
python -m src.watcher.cli /path/to/repo --branch main --interval 5

# MODE 2: Git hooks — fires immediately when commits land on main
python -m src.watcher.cli install-hooks /path/to/repo --branch main

# MODE 3: CI/CD — single-shot check (run in GitHub Actions / GitLab CI)
python -m src.watcher.cli check --repo-path /path/to/repo
```

The watcher detects what changed and picks the cheapest update strategy:

```
Small changes (formatting, comments)  → COSMETIC  → Just update metadata, skip LLM
Code changes (modified functions)      → CONTENT   → Re-analyze ONLY changed files, update affected sections
Architecture changes (new modules)     → STRUCTURAL → Full regeneration from scratch
```

### What Still Needs to Be Built

To achieve the full vision of **"auto-scan mainline + separate branch doc"**, these features need to be added:

#### 1. Auto-Scan Mainline + Publish (wire watcher → publisher)

The watcher currently saves docs locally but doesn't publish. This needs to be connected:

```
BranchWatcher detects new commits on main
    → IncrementalUpdater generates/updates docs
    → ConfluencePublisher publishes updated docs      ← NEW: wire this
    → GoogleDocsPublisher publishes updated docs       ← NEW: wire this
```

**What to build:**
- In `BranchWatcher.check_and_update()`, after the updater runs, call the publishers
- Add a `publish_after_update: true` config flag
- The watcher already has an `on_update` callback — hook the publishers into it

**Estimated effort:** ~50 lines of code in `watcher.py` + config change.

#### 2. Working Branch Documentation (separate doc per branch)

Currently, docs are generated for whatever branch you specify. The vision is:

```
Mainline (main/master):
    → docs/generated/main/TECHNICAL_DOC.md          ← always up-to-date
    → Published to Confluence page: "MyApp — Technical Documentation"

Working branch (feature/xyz):
    → docs/generated/feature-xyz/TECHNICAL_DOC.md    ← shows what's different
    → Published to Confluence page: "MyApp — feature/xyz Documentation"
    → Includes a "What Changed" section comparing to main
```

**What to build:**
- Branch-namespaced output directories (`docs/generated/{branch-name}/`)
- A "branch diff doc" generator that shows what the branch adds/changes vs main
- Separate Confluence pages per branch (auto-cleaned when branch is merged/deleted)
- Extension UI: dropdown to select which branch's docs to view

**Estimated effort:** ~200-300 lines of new code + extension UI changes.

#### 3. Extension Integration (auto-trigger from IDE)

The VS Code extension should automatically:
- Start the watcher when a workspace is opened
- Show a status bar item: "Docs: up-to-date" or "Docs: updating..."
- Auto-generate working branch docs when you switch branches
- Notify when mainline docs are updated

**What to build in `extension.ts`:**
- `onDidChangeActiveTextEditor` → detect branch switches
- Background task that runs the watcher
- Status bar item showing doc freshness
- Auto-publish toggle in settings

**Estimated effort:** ~150 lines in the VS Code extension.

#### 4. IDE-Level Auto-Trigger Flow (Complete Vision)

```
Developer opens project in VS Code / IntelliJ
    │
    ├── Extension starts background watcher for main branch
    │   └── Every 5 min: check main for new commits
    │       └── If changed: update mainline docs → publish to Confluence
    │
    ├── Developer switches to feature/xyz branch
    │   └── Extension detects branch change
    │       └── Generate "branch diff doc" (what's new vs main)
    │       └── Publish to separate Confluence page
    │
    ├── Developer makes commits on feature/xyz
    │   └── Extension detects new commits (post-commit hook or polling)
    │       └── Incrementally update branch doc
    │
    └── Developer merges feature/xyz into main
        └── Post-merge hook fires
            └── Full mainline doc update → publish to Confluence
            └── Delete the feature/xyz branch doc page
```

### Config for Auto-Scan (Planned)

```yaml
# repo-doc-mcp.yaml (planned additions)
watcher:
  enabled: true
  branch: "main"                    # Branch to auto-track
  interval_minutes: 5               # Polling interval
  publish_after_update: true        # Auto-publish after each update
  branch_docs:
    enabled: true                   # Generate separate docs per working branch
    auto_cleanup: true              # Delete branch docs when branch is merged
    publish_branch_docs: true       # Also publish branch docs to Confluence
```

---

## Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| Python MCP Server | Working | All 12 tools, 60/60 tests pass |
| CLI (scan + generate) | Working | Needs LLM API key with credits |
| Confluence Publisher | Working | Tested — connected to your space |
| Google Docs Publisher | Code complete | Needs Google Cloud service account setup |
| VS Code Extension | Compiles clean | Needs F5 testing with a running MCP server |
| IntelliJ Plugin | Code complete | Needs `./gradlew runIde` testing |
| Auto-scan mainline + publish | Code complete | Watcher now wired to publishers via `publish_after_update` config |
| Branch-aware docs | Code complete | Branch-namespaced output, diff vs main, CLI + MCP tool |
| Auto-trigger from IDE | Code complete | VS Code: .git/HEAD watcher + status bar; IntelliJ: polling + StatusBarWidget |
| Paid/Enterprise features | Not started | See monetization section above |

---

*Last updated: 2026-04-04*
