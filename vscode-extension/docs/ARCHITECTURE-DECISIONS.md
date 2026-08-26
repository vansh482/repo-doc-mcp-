# Architecture Decisions — Why This, Not That

> Every major technical decision in this project, what alternatives exist, and why we chose this path.
> Written so you can explain any decision to a team, interviewer, or yourself in 6 months.

---

## 1. CI/CD Pipeline

### What we chose: GitHub Actions + tag-based release

### Other options:

| Option | What it is | Why we didn't pick it |
|--------|-----------|----------------------|
| **GitHub Actions** (ours) | Built into GitHub, free for public repos | We picked this — it's where our code lives |
| **CircleCI** | Separate CI service, connects to GitHub | Extra account, extra config, no benefit at our scale |
| **Jenkins** | Self-hosted CI server | Overkill — you'd need to run a server 24/7 for a solo project |
| **GitLab CI** | GitLab's built-in CI | Our code isn't on GitLab |
| **Azure Pipelines** | Microsoft's CI (same company as VS Code) | Works, but heavier config, no real advantage over Actions |
| **Manual publish** | Run `npx vsce publish` locally | Error-prone, requires your machine, no audit trail |
| **Husky pre-push hooks** | Run checks locally before push | Only checks YOUR machine, not a clean environment |

### Why tag-based release (not every push to main):

| Trigger | Behavior | Problem |
|---------|----------|---------|
| Every push to main | Auto-publishes to marketplace | Can't control WHEN a release goes out. Merge 3 things → 3 marketplace updates in 10 minutes. |
| Manual dispatch | Click a button in GitHub to release | Forgettable. You'll skip it. |
| **Tag-based** (ours) | `git tag v0.3.0 && git push origin v0.3.0` | Full control. Push 10 commits, release when YOU'RE ready. Semantic versioning. |

### Why two workflows (ci.yml + release.yml):

- `ci.yml` = **safety net** — catches broken code BEFORE it reaches main. Runs on every PR.
- `release.yml` = **delivery** — only runs when you deliberately tag a release.

If you only had release.yml, broken code could sit in main for weeks, then you'd discover it at release time.

### How to trigger a release:

```bash
# 1. Bump version in package.json
# 2. Commit and push to main
# 3. Tag and push:
git tag v0.2.0
git push origin v0.2.0
# Pipeline does the rest: compile → package → publish to marketplace → GitHub release
```

---

## 2. VS Code Extension Architecture

### What we chose: WebviewViewProvider (sidebar panel)

### All VS Code UI options:

| Pattern | What it is | Why we chose/didn't |
|---------|-----------|---------------------|
| **WebviewViewProvider** (ours) | Custom HTML panel in the sidebar | Full control over UI, persistent, always visible while coding |
| **TreeView** | File-explorer-style tree (like git panel) | Good for lists, bad for forms/buttons/progress bars |
| **QuickPick** | Dropdown that appears on `Cmd+Shift+P` | Good for one-time actions, bad for showing ongoing state |
| **Notifications only** | Toast messages | No persistent UI, user can't check status after dismissing |
| **StatusBar item** | One line at the bottom | Too small for our info (branch, progress, links, instructions) |
| **Webview Panel** (editor tab) | HTML page as an editor tab | Takes up editor space, user has to switch away from code |
| **Output Channel only** | Log output | No interactivity, just text dump |

We use the sidebar because it's **always visible without taking editor space** — you see progress while continuing to code.

### Why TypeScript (not JavaScript):

| Choice | Trade-off |
|--------|-----------|
| **TypeScript** (ours) | Catches bugs at compile time. The `LLMResponse` refactor across 5 files simultaneously would've been a nightmare without types telling you every callsite that needs updating. |
| **JavaScript** | Faster to start, but every typo is a runtime error you discover in production. Refactoring is scary because nothing tells you what broke. |

### Why no framework (React/Svelte) in the webview:

The sidebar HTML is ~400 lines of vanilla HTML/JS. A framework would add:
- Separate build step for the webview (webpack/vite config for the webview only)
- 50KB+ bundle size for React
- Complexity for what's essentially one form + one status card

**Rule:** If your webview is < 1000 lines, vanilla is simpler. Cross that threshold → consider Svelte (smallest bundle) or Preact.

---

## 3. LLM Provider Architecture

### What we chose: Factory pattern with a shared interface

```
LLMProvider interface
  ├── AnthropicProvider
  ├── OpenAIProvider
  └── BedrockProvider
```

### Other approaches:

| Approach | What it means | Why not |
|----------|--------------|---------|
| **Factory pattern** (ours) | One interface, swap implementations | Clean, testable, adding a 4th provider is one new file |
| **If/else in one file** | `if (provider === 'anthropic') { ... } else if ...` | Works at 2 providers, becomes 200-line spaghetti at 5 |
| **LangChain** | Community abstraction over all LLMs | Adds 50MB dependency, abstracts away control we need (token tracking, error messages, retry logic) |
| **LiteLLM proxy** | Run a local proxy that normalizes all LLM APIs | Extra process to manage, adds latency, another failure point |
| **Vercel AI SDK** | React-focused LLM abstraction | Designed for Next.js web apps, not VS Code extensions |

### Why `LLMResponse { content, usage }` instead of returning a string:

Without this, you'd need separate logic to get token counts from each provider, or lose them. The typed return means **every future provider automatically reports tokens** — the interface enforces it. If someone adds `OllamaProvider` later, TypeScript will error until they include `usage` in the return.

### Why parallel doc generation (`Promise.all`):

```typescript
const [tech, nonTech] = await Promise.all([
  provider.generate(technicalPrompt),
  provider.generate(nonTechnicalPrompt),
]);
```

Both docs use the same diff/context but different prompts. They don't depend on each other. Running them in parallel cuts generation time from ~60s to ~35s. No downside.

---

## 4. Security Architecture ("Pipe, Not Platform")

### What we chose: Direct API calls from user's machine, no intermediary

```
User's machine → LLM API → back to user → Confluence
      (nothing passes through us)
```

### Other architectures:

| Architecture | How it works | Security trade-off |
|-------------|-------------|-------------------|
| **Pipe** (ours) | User's machine → LLM → User → Confluence | Zero trust required beyond user's own API keys |
| **Backend proxy** | User → Your server → LLM → Your server → Confluence | You see all their code. Liable for breaches. Need servers. |
| **SaaS platform** | User uploads code to your cloud | You store their code. GDPR/SOC2 required. Massive liability. |
| **Browser extension** | Runs in browser | CORS issues, can't access git, limited capabilities |

### Why "pipe" wins for THIS product:

1. **Zero liability** — you never touch their code, so you can't leak it
2. **Zero infrastructure cost** — no servers to run or pay for
3. **Enterprise adoption** — security teams approve instantly because data never leaves user's control
4. **Compliance** — no SOC2, GDPR compliance, data processing agreements needed
5. **Scaling** — 1000 users don't increase your costs at all (they each use their own API keys)

### If we'd built a backend proxy, we'd need:
- Servers ($50-500/month)
- SSL certificates
- Data retention policies
- Privacy policy + Terms of Service
- GDPR compliance (if any EU users)
- SOC2 audit ($50K+ for the first one)
- Every enterprise would block us pending security review

### Why SecretStorage (not plain text config):

| Storage | Where secrets go | Risk |
|---------|-----------------|------|
| **SecretStorage** (ours) | OS keychain (macOS Keychain, Windows Credential Manager) | Encrypted at rest, process-isolated, never in plain text |
| **settings.json** | Plain text JSON in `.vscode/` folder | Accidentally committed to git = leaked API keys |
| **Environment variables** | Shell env | Better than file, but visible in `ps aux`, child processes inherit |
| **`.env` file** | Plain text, gitignored | Works locally, but frequently accidentally committed despite gitignore |

---

## 5. Confluence Integration

### What we chose: Raw `fetch()` calls to REST API

### Other options:

| Approach | Trade-off |
|----------|-----------|
| **Raw fetch** (ours) | Full control, zero dependencies, we only call 4 endpoints |
| **Atlassian SDK** (`@atlaskit/`) | Designed for Atlassian apps embedded in Confluence, not standalone tools |
| **confluence.js** npm package | 400 downloads/week, could go unmaintained, we only need 4 API calls |
| **GraphQL** | Confluence doesn't have a GraphQL API |

**Rule:** If you're calling < 5 endpoints on an API, raw fetch is simpler than an SDK. SDKs earn their place at 20+ endpoints.

### Why API token auth (not OAuth yet):

| Auth type | UX | Complexity |
|-----------|-----|-----------|
| **API token** (ours, current) | User pastes token once in setup wizard | 10 lines of code. Works immediately. |
| **OAuth 2.0 (3LO)** | User clicks "Sign in", browser opens, redirects back | 200+ lines. Need OAuth app registered with Atlassian. Refresh token logic. Redirect URI handling. |

API token is the right v1 choice — gets users running in 30 seconds. OAuth is a later upgrade for UX polish (no need to generate/paste tokens).

---

## 6. Git Diff Strategy

### What we chose: Three-dot diff (`git diff main...HEAD`)

### All options:

| Strategy | What it shows | When it's wrong |
|----------|-------------|-----------------|
| **Three-dot** (ours) `main...HEAD` | Only what YOUR branch changed since it diverged from main | Never wrong for "what did this branch introduce" |
| **Two-dot** `main..HEAD` | Commits in HEAD not in main | Includes unrelated main commits if main moved forward after branching |
| **Simple diff** `git diff main HEAD` | Raw file differences between the two branch tips | If main got new commits, shows changes you didn't make |
| **PR diff** (GitHub API) | What GitHub shows on the PR page | Requires GitHub API access, only works if a PR exists, not for local branches |

Three-dot is the semantically correct choice for "show me what THIS branch introduced" regardless of what happened on main since branching.

### Why `execFile` not `exec`:

```typescript
// We use:
execFile('git', ['diff', 'main...HEAD'])  // ← safe

// NOT:
exec(`git diff ${baseBranch}...HEAD`)  // ← command injection risk
```

With `exec`, if `baseBranch` contained `; rm -rf /`, it would execute. `execFile` passes arguments as an array — the shell never interprets them. This is a standard security practice (OWASP command injection prevention).

---

## 7. State Management (Branch → Page Tracking)

### What we chose: VS Code `workspaceState`

### Other options:

| Storage | Persistence | Shared? | Trade-off |
|---------|------------|---------|-----------|
| **workspaceState** (ours) | Per-workspace, survives restarts | No — each workspace is isolated | Zero config, VS Code manages it, no file to gitignore |
| **globalState** | Per-extension, across all workspaces | Across workspaces | Wrong — branch "feature/login" in repo A ≠ in repo B |
| **JSON file in repo** | Until deleted | Via git | Risk of committing tracking data. Gitignore complexity. |
| **SQLite** | Until deleted | No | Overkill for key-value pairs. Adds native dependency. |
| **File in `~/.repodoc/`** | Until deleted | Across machines if synced | Non-standard location, user has to clean up |

`workspaceState` is perfect because tracking is **per-repo** (you don't want repo A's page IDs mixed with repo B's) and **automatic** (no file management, no gitignore, no cleanup).

---

## 8. Diff Truncation Strategy

### What we chose: File-boundary truncation with source code priority

### Other approaches:

| Strategy | Problem |
|----------|---------|
| **Hard character cut** (old approach) | Cuts mid-file. LLM sees half a file — worse than not seeing it at all. |
| **File-boundary cut** (our new approach) | Includes complete files until budget runs out. Remaining files listed by name. |
| **Summary-only for large diffs** | Throws away all actual code. LLM writes generic docs. |
| **Split into multiple LLM calls** | More tokens, more cost, need to merge outputs coherently. Complexity. |
| **Let LLM handle it** | Send 200K tokens. Expensive ($0.60/run). Most LLMs lose quality with very long context. |

Our approach prioritizes **source code files** over configs/lock files (which are often large but less informative), so the LLM always sees the most important changes.

---

## 9. Extension Distribution

### What we chose: VS Code Marketplace (free listing)

### Other options:

| Channel | Reach | Control | Trade-off |
|---------|-------|---------|-----------|
| **Marketplace** (ours) | 35M VS Code users can search/install | Limited (Microsoft's rules) | Maximum discoverability, one-click install |
| **GitHub Releases only** | Only people who find your repo | Full | Manual install (`code --install-extension file.vsix`). Low discoverability. |
| **Open VSX** | Eclipse/Gitpod/Theia users | Same as marketplace | Additional listing for non-Microsoft VS Code forks |
| **npm package** | JavaScript devs | Full | Not standard for extensions, confusing UX |
| **Direct download (website)** | Anyone | Full | You need a website, hosting, and users have to trust you |

Marketplace is non-negotiable for reach. GitHub Release is good as backup + for versioned artifacts.

---

## 10. Why VS Code Extension (Not Just a Script/MCP/CLI)

### The core question: "Why did I build all this instead of just writing a prompt?"

| Form factor | Audience | UX | Monthly cost per user |
|-------------|----------|----|-----------------------|
| **Claude Code prompt** | You (one person who knows the prompt) | Type prompt, wait, paste result | $20 subscription + $15-90 tokens |
| **VS Code Extension** (ours) | Anyone with VS Code (35M people) | Click one button | $3-9 API tokens only |
| **CLI tool** | CI/CD pipelines, automation | `npx repodoc generate` | Same as extension |
| **MCP Server** | AI assistants composing workflows | AI calls your tool | Same as extension |
| **SaaS web app** | Browser users | Upload code / connect repo | You pay for servers + LLM |

### Why the extension wins as v1:

1. **5x cheaper per run** — only uses AI for what AI is good at (writing). Everything else is deterministic code.
2. **Distributable** — can't sell a prompt; can sell an extension
3. **Consistent** — same output structure every time (prompts drift)
4. **Accessible** — anyone can click a button; not everyone can write a good prompt
5. **Secure** — secrets in keychain, not pasted into chat history
6. **Scalable** — team of 50 installs it, no per-seat AI subscription needed

---

## 11. Publisher Architecture (Future — DocPublisher Interface)

### What we're planning: Plug-in publisher pattern

### Why not just add Notion support directly:

| Approach | What happens when you add publisher #5 |
|----------|---------------------------------------|
| **Direct integration** (spaghetti) | Touch extension.ts, add new auth logic, new settings, new wizard fields, new converter. 4+ files per publisher. |
| **DocPublisher interface** (planned) | Write ONE file implementing `createPage()`/`updatePage()`. Register it. Done. |

The interface pays for itself at publisher #2. By publisher #5, it's saved weeks of work and prevented cross-publisher bugs.

### The three-layer design:

```
Auth Layer      → "How do I get a valid token for this service?"
Content Layer   → "How do I convert markdown to this service's format?"
Publisher Layer → "How do I create/update a page on this service?"
```

Each layer is independent. Fix a markdown→HTML bug → all HTML-based publishers (Confluence, SharePoint) get the fix. Add OAuth → all OAuth-based publishers (Google, Microsoft) benefit.

---

## 12. Error Recovery Pattern

### What we chose: Save locally on publish failure

### The key insight:

The expensive part is LLM generation (30-60s, real token cost). Publishing is cheap (2 API calls, < 1s). If publishing fails, you've already spent the money and time on generation. Throwing away the result would be terrible UX.

### Alternative approaches:

| Approach | Problem |
|----------|---------|
| **Just show error, lose docs** (old behavior) | User wasted 40s + tokens. Has to re-run. |
| **Save to `.repodoc/`** (ours) | Docs preserved. User can manually publish later or re-run. |
| **Retry automatically** | If it's an auth error, retrying won't help. If it's a rate limit, immediate retry makes it worse. |
| **Queue for later** | Complexity. Need background job system. Overkill for v1. |

---

## Summary: Decision Framework

When choosing between options, we consistently applied these principles:

1. **Minimize dependencies** — fewer deps = fewer breaking changes, smaller bundle, less supply chain risk
2. **Pipe > Platform** — never be the middleman for user data
3. **Deterministic > AI** — only use AI for what REQUIRES AI (creative writing). Everything else should be code.
4. **Interface > Implementation** — design for the 2nd use case, not just the 1st
5. **OS-level security** — keychain, not config files
6. **User controls timing** — tag-based releases, not auto-publish on merge
7. **Graceful degradation** — publish fails? Save locally. Restrictions fail? Log warning. Never lose user's work.
