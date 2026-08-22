# Repo Doc Generator — Future Scope & Roadmap

All possible improvements, features, and enhancements. Organized by priority and category.

---

## High Priority (Should Do Next)

### Functionality
- [ ] **Wire up `docLength` setting** — Currently declared but not consumed. Make prompts vary based on concise/standard/detailed selection
- [ ] **Page-level restrictions** — After creating/updating pages, call Confluence restriction API to lock view/edit to the authenticated user only
- [ ] **Error recovery** — If LLM call succeeds but Confluence publish fails, save generated docs locally so user doesn't lose them
- [ ] **Diff too large handling** — When diff exceeds token limits, summarize by file groups instead of truncating mid-file

### UX
- [ ] **Output channel logging** — Write detailed logs to a dedicated VS Code Output Channel for debugging
- [ ] **Success notification with links** — After publish, show clickable links to both Confluence pages
- [ ] **Status bar item** — Persistent status bar showing last generation time and branch name
- [ ] **Sidebar webview** — Make the activity bar sidebar functional (currently registered but not implemented)

### Quality
- [ ] **Unit tests** — Add tests for git/diff.ts, scanner, markdown converter, tracker
- [ ] **Integration tests** — VS Code extension test framework with mocked APIs
- [ ] **Prompt versioning** — Track prompt template versions so docs note which prompt generated them

---

## Medium Priority (Will Do)

### Features
- [ ] **Custom prompt templates** — Let users provide their own prompt templates via settings or a .repodoc file
- [ ] **Multi-repo support** — Handle VS Code multi-root workspaces, generate docs per repo
- [ ] **Selective file inclusion** — Let users pick which changed files to include in the diff (via quick pick)
- [ ] **Doc preview before publish** — Show generated markdown in a webview tab before pushing to Confluence
- [ ] **Branch comparison picker** — Let users choose any two branches to compare, not just current vs main
- [ ] **Auto-detect Confluence space** — Query user's spaces and let them pick from a dropdown
- [ ] **Commit-level docs** — Option to generate docs for a single commit instead of full branch diff
- [ ] **Draft mode** — Publish as Confluence draft (unpublished) for review before making visible

### UX Improvements
- [ ] **Streaming LLM output** — Show doc content appearing in real-time in a webview as LLM generates
- [ ] **History panel** — Show list of previously generated docs with links, timestamps, branches
- [ ] **Quick pick for common actions** — Cmd+Shift+P menu with "Generate", "View Last", "Open in Confluence"
- [ ] **Keyboard shortcut customization** — Document and expose rebindable shortcuts
- [ ] **Onboarding walkthrough** — VS Code native walkthrough API (contributes.walkthroughs) for first-time setup

### Auth & Security
- [ ] **OAuth for Confluence** — Atlassian OAuth 2.0 (3LO) flow for more secure authentication
- [ ] **Token refresh/rotation** — Detect expired tokens and prompt for re-auth
- [ ] **Credential validation on save** — Test API key / Confluence token when user saves settings

---

## Lower Priority (Could Do)

### Publishers
- [ ] **Google Docs publisher** — Alternate output target using Google Docs API
- [ ] **Notion publisher** — Output to Notion pages via API
- [ ] **Markdown file publisher** — Save docs as .md files in the repo (for teams without Confluence)
- [ ] **GitHub Wiki publisher** — Push docs to the repo's GitHub wiki
- [ ] **Slack integration** — Post a summary to a configured Slack channel after generation

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

### Platform
- [ ] **IntelliJ plugin** — Port to JetBrains IDE platform (Kotlin/Java)
- [ ] **CLI tool** — Standalone CLI for CI/CD pipelines (generate docs on merge)
- [ ] **GitHub Action** — Auto-generate docs on PR open/update
- [ ] **GitLab CI integration** — Pipeline step for doc generation

---

## Monetization Ideas (Future)

- [ ] **Usage-based pricing** — Track tokens used, offer free tier + paid for heavy usage
- [ ] **Team/org licenses** — Shared configuration, team spaces, admin controls
- [ ] **Custom model fine-tuning** — Premium feature: fine-tune on org's doc style
- [ ] **Priority LLM routing** — Faster generation for paid users
- [ ] **Analytics dashboard** — Show doc generation stats, most documented repos, team activity

---

## Tech Debt & Housekeeping

- [ ] **Remove unused sidebar webview registration** — Or implement it properly
- [ ] **Strict TypeScript** — Enable strict mode, fix any resulting errors
- [ ] **Bundle with esbuild** — Reduce extension size and load time (currently just tsc)
- [ ] **CI/CD pipeline** — GitHub Actions for lint, test, package, publish
- [ ] **Changelog** — Maintain CHANGELOG.md following Keep a Changelog format
- [ ] **Extension icon** — Design and add a proper marketplace icon
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
