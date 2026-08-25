# Repo Doc Generator — Future Scope & Roadmap

All possible improvements, features, and enhancements. Organized by priority and category.

---

## High Priority (Should Do Next)

### Functionality
- [x] **Smart base branch detection** — Detects via tracking config, expanded candidates (main/master/develop/development/mainline), remote fallback (origin/*), clear error message with settings instructions
- [x] **Wire up `docLength` setting** — Prompts vary based on concise/standard/detailed selection; setting registered in package.json, threaded through config → generator → prompts
- [x] **Page-level restrictions** — `restrictPageToCurrentUser()` method calls Confluence restriction API to lock view/edit to authenticated user
- [x] **Error recovery** — If Confluence publish fails, docs saved locally to `.repodoc/` directory with user-facing warning
- [x] **Diff too large handling** — `truncateDiffAtFileBoundaries()` cuts at file boundaries, lists skipped files, shows user warning
- [x] **Cover non-code artifacts in docs** — Prompts explicitly instruct LLM to cover documentation, licenses, configs, CI/CD, package metadata, icons

### UX
- [x] **Custom instructions text field** — Textarea in sidebar captures user instructions, passed through generator → prompts. Appended as "Additional Instructions" section to both technical and non-technical prompts.
- [x] **Fix page title naming** — Now `branchName — Technical/Summary` (repo name removed since pages live under repo-scoped parent)
- [x] **Output channel logging** — Detailed logging: branch info, token usage, timing, truncation warnings, error details
- [x] **Success notification with links** — After publish, show clickable links to both Confluence pages
- [x] **Status bar item** — Persistent status bar showing last generation time and branch name

### Quality
- [ ] **Unit tests** — Add tests for git/diff.ts, scanner, markdown converter, tracker
- [ ] **Integration tests** — VS Code extension test framework with mocked APIs
- [ ] **Prompt versioning** — Track prompt template versions so docs note which prompt generated them

---

## Medium Priority (Will Do)

### Features

- [ ] **Selective file exclusion** — Let users pick which changed files to inot nclude in the diff (via quick pick)

- [ ] **Auto-detect Confluence space** — Query user's spaces and let them pick from a dropdown
- [ ] **Commit-level docs** — Option to generate docs for a single commit instead of full branch diff
- [ ] **Draft mode** — Publish as Confluence draft (unpublished) for review before making visible

### UX Improvements
-
- [ ] **History panel** — Show list of previously generated docs with links, timestamps, branches
- [ ] **Quick pick for common actions** — Cmd+Shift+P menu with "Generate", "View Last", "Open in Confluence"
-
- [ ] **Onboarding walkthrough** — VS Code native walkthrough API (contributes.walkthroughs) for first-time setup

### Auth & Security
- [ ] **OAuth for Confluence** — Atlassian OAuth 2.0 (3LO) flow for more secure authentication
- [ ] **Token refresh/rotation** — Detect expired tokens and prompt for re-auth
- [ ] **Credential validation on save** — Test API key / Confluence token when user saves settings

---

## Lower Priority (Could Do)

### Publishers

#### Architecture prerequisite (build in this order) — see [`docs/PUBLISHER-ARCHITECTURE.md`](docs/PUBLISHER-ARCHITECTURE.md) for full design
- [ ] **DocPublisher interface + factory** — Extract common interface (`createPage`, `updatePage`, `getPageVersion`) and a factory that picks implementation from settings. Currently `ConfluencePublisher` is hardcoded in `extension.ts`. Effort: ~2-3 hours.
- [ ] **ContentTransformer pipeline** — LLM always outputs markdown. Each publisher needs different format. Centralize: `MarkdownToHtml` (Confluence/SharePoint), `MarkdownToNotionBlocks`, `MarkdownToGoogleOps`, `Identity` (GitHub Wiki/Markdown files). Fix a conversion bug once → all publishers benefit. Effort: ~3-4 hours.
- [ ] **VS Code AuthenticationProvider adoption** — Use VS Code's built-in auth framework instead of custom SecretStorage logic. Benefits: tokens in native Accounts menu, automatic refresh, OAuth redirect handling, multi-account support. Each publisher registers its auth provider; code just calls `vscode.authentication.getSession('notion', scopes)`. Effort: ~half day to migrate Confluence, then each new provider is 2-3 hours.
- [ ] **Multi-publisher simultaneous output** — After multiple publishers are onboarded, let users select multiple targets per run (e.g. Confluence + Slack + Markdown file). UI: multi-select checkboxes in sidebar or settings. Run loop calls `Promise.all(selectedPublishers.map(p => p.createPage(...)))`. Track page IDs per-publisher in the tracker. Effort: ~half day (once the interface layer exists).

#### Publisher implementations (ordered by effort)
- [ ] **Markdown file publisher** — Save docs as `.md` files in repo (e.g. `.repodoc/` folder). Effort: **2-3 hours**. No API, no auth. Good fallback for teams without any wiki. Could auto-commit.
- [ ] **GitHub Wiki publisher** — Wiki is just a git repo (`repo.wiki.git`). Push a `.md` file. Effort: **0.5-1 day**. Zero auth overhead (reuses existing git creds). Great for open source teams.
- [ ] **Slack integration** — Post non-technical summary to a channel after generation. Effort: **0.5-1 day**. Webhook = just a URL (no OAuth). Complement to a doc publisher, not a replacement.
- [ ] **Notion publisher** — Block-based JSON content model (not HTML). Use `@notionhq/client` SDK. Auth: simple integration token (similar to Confluence). Effort: **1-2 days**. Main work is markdown → Notion blocks conversion. Most requested alternative by dev teams.
- [ ] **Google Docs publisher** — Structured JSON manipulation API (not HTML). Auth: OAuth 2.0 + Google Cloud project + consent screen. Effort: **3-5 days**. Hardest content model — need `insertText`/`updateParagraphStyle` request sequences. High value for mixed teams.
- [ ] **SharePoint/OneNote publisher** — Microsoft Graph API. Auth: Azure AD OAuth. Effort: **3-5 days**. HTML for SharePoint pages, custom markup for OneNote. High value for Microsoft-heavy enterprises (banks, consulting).

### LLM Providers
- [ ] **Ollama (local LLM)** — Support local models for offline/air-gapped environments
- [ ] **Azure OpenAI** — Enterprise Azure OpenAI Service endpoint support
- [ ] **Google Vertex AI** — Gemini models via Vertex
- [ ] **Custom endpoint** — Let users point to any OpenAI-compatible API

### Advanced Features
- [ ] **Real-time file watching** — Auto-regenerate docs on file save (debounced, configurable)
- [ ] **Scheduled generation** — Auto-run on git push or at configured intervals
- [ ] **Diff changelog mode** — Append to a running changelog instead of replacing the full doc
- [ ] **PR description generation** — Generate a GitHub/GitLab PR description from the same diff
- [ ] **Team knowledge base** — Aggregate docs across branches into a team-wide knowledge base
- [ ] **Doc comparison** — Show what changed between two doc generations on the same branch
- [ ] **Diagram generation** — Auto-generate Mermaid architecture diagrams from code structure changes

### Platform — Three Interfaces, One Engine (see [`docs/DISTRIBUTION-STRATEGY.md`](docs/DISTRIBUTION-STRATEGY.md))

The core logic (git diff → scan → LLM → publish) is already framework-independent. These are just different entry points to the same engine.

- [ ] **CLI tool** — Standalone CLI for CI/CD pipelines. Effort: **~1 day**. Import existing modules, add argument parsing (yargs/commander), read config from env vars or `.repodocrc`. Unlocks: auto-generate docs on every PR merge without human intervention. GitHub Action wraps this.
- [ ] **MCP Server** — Expose `generate_branch_docs`, `get_last_docs`, `list_documented_branches` as MCP tools. Effort: **~1-2 days**. Wrap existing pipeline in `@modelcontextprotocol/sdk`. Unlocks: AI assistants can compose doc generation with other tools (Slack, PR updates, etc.)
- [ ] **GitHub Action** — Wraps the CLI tool. Auto-generate docs on PR open/merge. Effort: **~half day** (after CLI exists). Just a `Dockerfile` + `action.yml` that calls the CLI.
- [ ] **GitLab CI integration** — Same as GitHub Action but for GitLab. Effort: **~half day** (after CLI exists).
- [ ] **IntelliJ plugin** — Port to JetBrains IDE platform (Kotlin/Java). Effort: **2-7 days** depending on Kotlin familiarity. Can reuse sidebar HTML via JCEF.
- [ ] **Extract shared core package** — Before CLI/MCP, extract `git/`, `scanner/`, `llm/`, `generator/`, `publisher/`, `tracker/` into a shared `@repodoc/core` package with no VS Code imports. Extension, CLI, and MCP all import from this. Effort: **~half day**.

---

## Monetization Ideas (Future)

- [x] **Token usage tracking** — All three providers return usage in LLMResponse. Generator accumulates input+output tokens. Logged to output channel per-run. Foundation for per-doc/per-char pricing.
- [ ] **Usage-based pricing** — Track tokens used, offer free tier + paid for heavy usage
- [ ] **Team/org licenses** — Shared configuration, team spaces, admin controls
- [ ] **Custom model fine-tuning** — Premium feature: fine-tune on org's doc style
- [ ] **Priority LLM routing** — Faster generation for paid users
- [ ] **Analytics dashboard** — Show doc generation stats, most documented repos, team activity

---

## Observability & Error Monitoring

- [ ] **Telemetry (Application Insights)** — Use `@vscode/extension-telemetry` (Microsoft's official package). Respects user's telemetry settings. Free tier: 5GB/month. Shows: errors, event counts, performance.
- [ ] **Sentry integration** — Real-time error alerts, stack traces, number of users affected. Better UX for debugging than App Insights. Free tier: 5K events/month.
- [ ] **Simple webhook on error** — POST error details (message, step, elapsed time) to a Slack/Discord webhook. Lowest effort, no SDK needed.
- [ ] **In-extension error report button** — After an error, show "Report Issue" button that opens a pre-filled GitHub issue with sanitized error context.
- [ ] **Usage analytics** — Track: which LLM provider used, generation time, doc length, success/fail rate. Helps prioritize improvements.

### Current Error Handling (v0.1.0)
Errors are logged to VS Code Output Channel ("Repo Doc Generator"). Users must manually copy logs if reporting bugs. No publisher-side visibility.

---

## Tech Debt & Housekeeping

- [ ] **DocPublisher interface** — Abstract publisher behind `DocPublisher { createPage(), updatePage(), getPageVersion() }` + factory pattern. Prerequisite for multi-publisher support. See Publishers section.
- [ ] **Strict TypeScript** — Enable strict mode, fix any resulting errors
- [ ] **Bundle with esbuild** — Reduce extension size and load time (currently just tsc)
- [ ] **CI/CD pipeline** — GitHub Actions for lint, test, package, publish
- [ ] **Changelog** — Maintain CHANGELOG.md following Keep a Changelog format
- [ ] **Screenshots for marketplace** — Generate demo screenshots/GIFs for the listing

---

## Completed

- [x] TypeScript rewrite (zero Python dependency)
- [x] Setup wizard (webview form)
- [x] Git diff extraction (three-dot, parallel commands)
- [x] Repo scanning (languages, structure, key files)
- [x] LLM integration (Anthropic, OpenAI, Bedrock)
- [x] Confluence publishing (create + update)
- [x] Branch-to-page tracking (update-not-duplicate)
- [x] Progress indicator (step-based, elapsed time, cancel)
- [x] Concise doc prompts (technical + non-technical)
- [x] SecretStorage for credentials
- [x] Settings.json fallback for testing
- [x] Personal space security constraint
- [x] Sidebar panel with Run button, live status, progress bar, cancel, result links
- [x] Extension icon (128x128 PNG)
- [x] .vscodeignore for smaller package (1.78 MB)
- [x] LICENSE (MIT)
- [x] VS Code Marketplace publishing (devcraft-tools.repo-doc-generator)
- [x] Legacy code cleanup (removed Python, IntelliJ, dead docs)
- [x] Publisher account setup (DevCraft Tools)

---

## Separate Product Idea: AI Rules Manager Extension

> Not part of Repo Doc Generator — a standalone extension under the same publisher (devcraft-tools).

**Concept:** A unified VS Code extension that manages AI instruction files across ALL coding tools from one place.

### The Problem
Every AI coding tool has its own instruction file format. Teams using multiple tools (Claude + Cursor + Copilot) duplicate rules across files. No templates, no sharing, no sync.

### Target Files

| Tool | File | Format |
|------|------|--------|
| Claude Code | `CLAUDE.md`, `.claude/CLAUDE.md` | Markdown (freeform) |
| Cursor | `.cursorrules` | Markdown (freeform) |
| GitHub Copilot | `.github/copilot-instructions.md` | Markdown (freeform) |
| Windsurf | `.windsurfrules` | Markdown (freeform) |
| Aider | `.aider.conf.yml` | YAML (structured) |

### Features
- [ ] **Unified editor** — sidebar panel showing all AI instruction files in current repo, create/edit from one place
- [ ] **Write once, sync to all** — write a rule once, extension generates/updates all target files (Claude, Cursor, Copilot, etc.)
- [ ] **Rule templates** — pre-built rule sets: "TypeScript project", "Python ML", "React frontend", "Go backend", "Monorepo". One-click apply.
- [ ] **Team sharing** — shared rule sets via git (a `.ai-rules/` folder) or a registry. Team lead defines rules, devs inherit.
- [ ] **Toggle rules** — enable/disable individual rules per-tool without deleting them (commented out with metadata)
- [ ] **Global vs repo** — manage both global (`~/.claude/CLAUDE.md`) and per-repo files from the same UI
- [ ] **Diff view** — show what's different between your tools' instruction files (find gaps)
- [ ] **Import/export** — share rule sets as gists or packages

### Why This Has Potential
- Audience: anyone using ANY AI coding tool (millions, growing fast)
- Pain point grows with tool count — and developers use 2-3 AI tools simultaneously
- No competition (nobody has built this yet)
- Low effort to MVP (~3-5 days: sidebar + file read/write + basic sync)
- Pairs well with devcraft-tools publisher (same brand, dev productivity niche)

### Effort Estimate
- MVP (editor + sync across 3 tools): **3-5 days**
- Templates marketplace: **+1-2 weeks**
- Team sharing registry: **+2-3 weeks**
