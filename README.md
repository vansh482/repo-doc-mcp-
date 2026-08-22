<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=28&duration=3000&pause=1000&color=6C63FF&center=true&vCenter=true&multiline=true&repeat=true&width=600&height=80&lines=Repo+Doc+Generator;AI-Powered+Branch+Documentation" alt="Typing SVG" />

<br/>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/vansh482/repo-doc-mcp-/main/.github/assets/flow-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/vansh482/repo-doc-mcp-/main/.github/assets/flow-light.svg">
  <img alt="Data Flow" width="650">
</picture>

```
     ╔══════════════╗         ╔══════════════╗         ╔══════════════╗
     ║   GIT DIFF   ║────────▶║    AI LLM    ║────────▶║  CONFLUENCE  ║
     ║              ║         ║              ║         ║              ║
     ║ branch vs    ║         ║ understands  ║         ║ auto-publish ║
     ║ main/master  ║         ║ & explains   ║         ║ & update     ║
     ╚══════════════╝         ╚══════════════╝         ╚══════════════╝
            │                        │                        │
            ▼                        ▼                        ▼
     What changed?            Why it matters          Living docs
```

<br/>

[![VS Code](https://img.shields.io/badge/VS_Code-Extension-007ACC?style=for-the-badge&logo=visualstudiocode&logoColor=white)](https://marketplace.visualstudio.com)
[![TypeScript](https://img.shields.io/badge/TypeScript-100%25-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Zero Dependencies](https://img.shields.io/badge/External_Deps-Zero-success?style=for-the-badge)](#)
[![Confluence](https://img.shields.io/badge/Confluence-Auto_Publish-172B4D?style=for-the-badge&logo=confluence&logoColor=white)](https://www.atlassian.com/software/confluence)

<br/>

**One click. Two docs. Always in sync.**

Your branch changes → explained for engineers AND stakeholders → published to Confluence.

[Install](#-install) · [How It Works](#-how-it-works) · [Features](#-features) · [Roadmap](#-roadmap) · [Develop](#-development)

---

</div>

<br/>

## The Problem

You finish a feature branch. Now you need to:
1. Write a technical doc explaining the changes
2. Write a non-technical summary for PMs/stakeholders
3. Publish both somewhere findable
4. Update them when the branch changes

**That's 30-60 minutes of context-switching per branch.** This extension does it in 30 seconds.

<br/>

## How It Works

```
  You click "Run" (Cmd+Shift+G)
       │
       │  ┌─────────────────────────────────────────────────────────────┐
       ├──│ Step 1/5  Detecting branch & computing diff vs main...     │
       │  └─────────────────────────────────────────────────────────────┘
       │  ┌─────────────────────────────────────────────────────────────┐
       ├──│ Step 2/5  Scanning repo structure (languages, key files)    │
       │  └─────────────────────────────────────────────────────────────┘
       │  ┌─────────────────────────────────────────────────────────────┐
       ├──│ Step 3/5  Generating docs with AI (30-60s)                  │
       │  └─────────────────────────────────────────────────────────────┘
       │  ┌─────────────────────────────────────────────────────────────┐
       ├──│ Step 4/5  Publishing to Confluence...                       │
       │  └─────────────────────────────────────────────────────────────┘
       │  ┌─────────────────────────────────────────────────────────────┐
       └──│ Step 5/5  Done! Pages created/updated.                      │
          └─────────────────────────────────────────────────────────────┘
       │
       ▼
  Two Confluence pages — always current with your branch
```

<br/>

## Features

<table>
<tr>
<td width="50%" valign="top">

### Branch-Aware Diff Docs

Compares your current branch against `main`/`master`/`mainline` using three-dot diff. Only documents what YOUR branch changed — not the entire repo history.

</td>
<td width="50%" valign="top">

### Dual-Audience Output

Every run produces two docs:
- **Technical Review** — for engineers (architecture decisions, risks, how to test)
- **Non-Technical Summary** — for PMs (what, why, impact in plain language)

</td>
</tr>
<tr>
<td width="50%" valign="top">

### Update, Never Duplicate

Run it 10 times on the same branch — same two Confluence pages get updated (version incremented). Branch-to-page tracking is automatic.

</td>
<td width="50%" valign="top">

### Multi-Provider LLM

Works with your existing AI provider:
- **Anthropic Claude** (API key)
- **OpenAI GPT-4** (API key)
- **AWS Bedrock** (IAM/SSO — no key needed)

</td>
</tr>
<tr>
<td width="50%" valign="top">

### Secure by Design

- API keys in OS keychain (VS Code SecretStorage)
- Publishes only to YOUR configured personal space
- No telemetry, no external calls except your LLM + Confluence

</td>
<td width="50%" valign="top">

### Real-Time Progress

Step-by-step progress indicator with:
- Current step (1/5 through 5/5)
- Elapsed time counter
- Cancel button to abort at any point

</td>
</tr>
</table>

<br/>

## Install

### From VS Code Marketplace (coming soon)

```
ext install vansh482.repo-doc-generator
```

### From Source (now)

```bash
git clone https://github.com/vansh482/repo-doc-mcp-.git
cd repo-doc-mcp-/vscode-extension
npm install
npm run compile
# Press F5 in VS Code to launch Extension Development Host
```

<br/>

## Setup

On first install, a webview wizard walks you through configuration:

| Step | What | Where it's stored |
|------|------|-------------------|
| LLM Provider | Anthropic / OpenAI / Bedrock | VS Code settings |
| API Key | Your provider's key | OS Keychain (SecretStorage) |
| Confluence URL | `https://yoursite.atlassian.net/wiki` | VS Code settings |
| Space Key | Your personal space key | VS Code settings |
| Parent Page ID | Page under which docs are created | VS Code settings |
| Email | Atlassian account email | OS Keychain (SecretStorage) |
| API Token | Confluence API token | OS Keychain (SecretStorage) |

All secrets stay in your OS keychain — never in plain text files.

<br/>

## Configuration

All settings under `repoDoc.*` in VS Code:

| Setting | Description | Default |
|---------|-------------|---------|
| `repoDoc.llm.provider` | LLM provider | `anthropic` |
| `repoDoc.llm.model` | Model ID | `claude-sonnet-4-20250514` |
| `repoDoc.confluence.baseUrl` | Confluence instance URL | — |
| `repoDoc.confluence.spaceKey` | Space key for docs | — |
| `repoDoc.confluence.parentPageId` | Parent page for docs | — |
| `repoDoc.baseBranch` | Branch to compare against | `main` |
| `repoDoc.docLength` | Output verbosity (concise/standard/detailed) | `concise` |
| `repoDoc.bedrock.region` | AWS region (Bedrock only) | `us-west-2` |
| `repoDoc.bedrock.profile` | AWS SSO profile (Bedrock only) | — |

<br/>

## Commands

| Command | Shortcut | Description |
|---------|----------|-------------|
| `Repo Doc: Run` | `Cmd+Shift+G` | Generate/update branch docs |
| `Repo Doc: Setup` | — | Re-run configuration wizard |
| `Repo Doc: View Docs` | — | Open last generated docs |

<br/>

## Example Output

### Non-Technical Summary
> **What's Happening:** This change adds user authentication to the API, requiring valid tokens for protected endpoints.
>
> **Why It Matters:** Without auth, anyone with the URL could access or modify data. This closes that security gap before launch.
>
> **What to Expect:** Users will need to log in. The login flow adds ~2 seconds to first request. No other behavior changes.

### Technical Review
> **What & Why:** Adds JWT-based auth middleware to all `/api/*` routes. Motivated by pre-launch security audit finding AUTH-001.
>
> **Key Changes:** New `middleware/auth.ts` validates Bearer tokens, extracts claims, attaches user context to request. Token refresh handled via `/auth/refresh` endpoint.
>
> **Risks & Rollback:** If token validation is too strict, legitimate requests may 401. Feature-flag `AUTH_ENABLED=false` bypasses. Revert: single commit, no migrations.

<br/>

## Architecture

```
vscode-extension/src/
├── extension.ts           Entry point — registers commands, orchestrates flow
├── config/
│   ├── wizard.ts          Webview setup wizard (persistent form)
│   ├── settings.ts        Typed config reader with defaults
│   └── secrets.ts         OS keychain wrapper (SecretStorage)
├── git/
│   └── diff.ts            Branch detection, three-dot diff, parallel git ops
├── scanner/
│   └── scanner.ts         Fast repo walker — 25+ languages, structure mapping
├── llm/
│   ├── provider.ts        Factory pattern — createProvider(type, config)
│   ├── anthropic.ts       Anthropic Claude SDK
│   ├── openai.ts          OpenAI SDK
│   └── bedrock.ts         AWS Bedrock (InvokeModelCommand)
├── generator/
│   ├── prompts.ts         Prompt templates — concise, decision-focused
│   └── generator.ts       Parallel LLM calls for both doc types
├── publisher/
│   └── confluence.ts      REST API client — create/update/version pages
└── tracker/
    └── tracker.ts         Branch → Confluence page ID mapping (workspaceState)
```

<br/>

## Roadmap

### Done

- [x] Full TypeScript rewrite — zero external dependencies for users
- [x] Webview setup wizard (no disappearing popups)
- [x] Git diff extraction (three-dot, parallel, safe from injection)
- [x] Repo scanning (languages, structure, key files)
- [x] LLM integration — Anthropic, OpenAI, AWS Bedrock
- [x] Confluence publishing — create + update with version tracking
- [x] Branch-to-page tracking (update, never duplicate)
- [x] Step-based progress with elapsed time + cancel
- [x] Concise prompts (decisions & risks, not file listings)
- [x] Markdown → Confluence XHTML converter (tables, code blocks, lists)
- [x] SecretStorage for all credentials
- [x] Personal space security constraint

### Next Up

- [ ] Wire `docLength` setting into prompt templates
- [ ] Page-level restrictions (lock docs to creator only)
- [ ] Doc preview before publish
- [ ] Success notifications with clickable Confluence links
- [ ] Output channel for debug logging
- [ ] Unit + integration tests
- [ ] VS Code Marketplace publishing
- [ ] Extension icon and screenshots

### Future

- [ ] OAuth for Confluence (replace API tokens)
- [ ] Streaming LLM output in webview
- [ ] Real-time file watching (auto-regen)
- [ ] Google Docs / Notion / Slack publishers
- [ ] Custom prompt templates
- [ ] PR description generation from same diff
- [ ] CLI for CI/CD pipelines
- [ ] IntelliJ plugin port
- [ ] GitHub Action for auto-docs on PR

<br/>

## Supported LLM Providers

| Provider | Auth Method | Example Model |
|----------|-------------|---------------|
| **Anthropic** | API Key | `claude-sonnet-4-20250514` |
| **OpenAI** | API Key | `gpt-4o` |
| **AWS Bedrock** | IAM/SSO Profile | `arn:aws:bedrock:us-west-2:...` |

<br/>

## Security

- All API keys and tokens stored in OS keychain via VS Code SecretStorage
- Extension only publishes to the configured space + parent page
- Git commands use `execFile` (not `exec`) — immune to shell injection
- No telemetry, analytics, or external reporting
- Diff content sent only to your chosen LLM provider

<br/>

## Development

```bash
cd vscode-extension
npm install
npm run compile

# Launch Extension Development Host
# Press F5 in VS Code (uses .vscode/launch.json)

# Watch mode for continuous compilation
npm run watch
```

<br/>

---

<div align="center">

```
    ┌─────────────────────────────────────────────────────┐
    │                                                     │
    │   Your code changes.                                │
    │   Your docs update.                                 │
    │   Your team stays informed.                         │
    │                                                     │
    │   Automatically.                                    │
    │                                                     │
    └─────────────────────────────────────────────────────┘
```

<br/>

**Built by [vansh482](https://github.com/vansh482)**

*Documentation should write itself.*

<br/>

<img src="https://capsule-render.vercel.app/api?type=waving&color=6C63FF&height=100&section=footer" width="100%"/>

</div>
