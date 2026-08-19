# Repo Doc Generator — VS Code Extension

**Generate AI-powered documentation for your branch changes, published directly to Confluence.**

One click: see what your branch changed vs main — as both a technical doc (for engineers) and a non-technical summary (for PMs/stakeholders). Run again on the same branch and the same Confluence pages get updated.

---

## Quick Start

1. Install the extension
2. Open a git repository in VS Code
3. On first launch, the setup wizard will ask for:
   - **LLM Provider** — Anthropic Claude, OpenAI, or AWS Bedrock
   - **API Key** — your LLM provider's API key (stored securely in VS Code's SecretStorage)
   - **Confluence** — base URL, email, API token, space key, parent page ID
4. Switch to a feature branch
5. Run `Cmd+Shift+G` (or Command Palette → "Repo Doc: Run")
6. Two docs appear in Confluence under your configured parent page

## How It Works

```
You click "Run"
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ 1. Git: detect branch, compute diff vs main             │
│ 2. Scanner: walk repo for structural context            │
│ 3. LLM: generate technical + non-technical docs         │
│ 4. Confluence: create pages (or update if run before)   │
└─────────────────────────────────────────────────────────┘
     │
     ▼
Two Confluence pages, always up-to-date with your branch
```

### The "Update, Don't Duplicate" Guarantee

The extension tracks which Confluence page IDs belong to which branch. If you run it twice on `feature/auth-refactor`, it updates the same two pages — incrementing their version — rather than creating duplicates.

## Configuration

All settings are under `repoDoc.*` in VS Code settings:

| Setting | Description | Default |
|---------|-------------|---------|
| `repoDoc.llm.provider` | LLM provider (anthropic, openai, bedrock) | `anthropic` |
| `repoDoc.llm.model` | Model ID | `claude-sonnet-4-20250514` |
| `repoDoc.confluence.baseUrl` | Your Confluence URL | — |
| `repoDoc.confluence.spaceKey` | Space key for doc pages | — |
| `repoDoc.confluence.parentPageId` | Parent page ID | — |
| `repoDoc.baseBranch` | Branch to compare against | `main` |
| `repoDoc.bedrock.region` | AWS region (Bedrock only) | `us-west-2` |
| `repoDoc.bedrock.profile` | AWS profile (Bedrock only) | — |

Sensitive values (API keys, Confluence token, email) are stored in VS Code's SecretStorage — never in settings.json.

## Commands

| Command | Shortcut | Description |
|---------|----------|-------------|
| Repo Doc: Run | `Cmd+Shift+G` | Generate/update branch docs |
| Repo Doc: Setup | — | Re-run the configuration wizard |
| Repo Doc: View Docs | — | Open previously generated docs |

## Development

```bash
cd vscode-extension
npm install
npm run compile

# Press F5 in VS Code to launch Extension Development Host
```

## Architecture

```
src/
├── extension.ts       — Entry point, command registration
├── config/            — Setup wizard, settings, secret storage
├── git/               — Branch detection, diff computation
├── scanner/           — Repo structure analysis
├── llm/               — Provider abstraction (Anthropic, OpenAI, Bedrock)
├── generator/         — Prompt templates, doc generation orchestration
├── publisher/         — Confluence API client
└── tracker/           — Branch → page ID mapping
```

## Supported LLM Providers

| Provider | Auth | Model Examples |
|----------|------|----------------|
| Anthropic | API Key | claude-sonnet-4-20250514, claude-opus-4-20250514 |
| OpenAI | API Key | gpt-4o, gpt-4-turbo |
| AWS Bedrock | IAM/SSO (profile) | us.anthropic.claude-sonnet-4-20250514-v1:0 |

## Finding Your Confluence Parent Page ID

1. Navigate to the page you want docs created under
2. Click "..." → "Page Information"
3. The page ID is in the URL: `.../pages/viewinfo.action?pageId=12345`

Or use the Confluence REST API:
```bash
curl -u email:token "https://yoursite.atlassian.net/wiki/rest/api/content?spaceKey=YOUR_SPACE&title=Your+Page+Title" | jq '.results[0].id'
```
