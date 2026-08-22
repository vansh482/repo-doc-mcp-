# Repo Doc Generator — VS Code Extension

**One click: generate AI-powered branch documentation, published to Confluence.**

Switch to a feature branch → hit `Cmd+Shift+G` → get a technical review doc AND a non-technical summary in Confluence. Run again on the same branch and the same pages get updated.

---

## Quick Start

1. Install the extension (or F5 from source)
2. Open a git repository in VS Code
3. Setup wizard walks you through LLM + Confluence configuration
4. Switch to a feature branch
5. `Cmd+Shift+G` (or Command Palette → "Repo Doc: Run")
6. Two docs appear in Confluence under your parent page

## How It Works

```
You click "Run"
     │
     ├── Step 1: Detect branch, compute diff vs main
     ├── Step 2: Scan repo structure (languages, key files)
     ├── Step 3: Generate technical + non-technical docs via LLM
     ├── Step 4: Publish to Confluence (create or update)
     └── Step 5: Done — links shown in notification
```

The extension tracks branch → page ID mapping. Same branch = same pages updated (version incremented), never duplicated.

## Configuration

All settings under `repoDoc.*`:

| Setting | Default | Description |
|---------|---------|-------------|
| `llm.provider` | `anthropic` | anthropic, openai, or bedrock |
| `llm.model` | `claude-sonnet-4-20250514` | Model ID for your provider |
| `confluence.baseUrl` | — | Your Confluence URL |
| `confluence.spaceKey` | — | Target space key |
| `confluence.parentPageId` | — | Parent page for generated docs |
| `baseBranch` | `main` | Branch to compare against |
| `docLength` | `concise` | concise / standard / detailed |
| `bedrock.region` | `us-west-2` | AWS region (Bedrock only) |
| `bedrock.profile` | — | AWS SSO profile (Bedrock only) |

Secrets (API keys, Confluence token, email) are stored in VS Code's SecretStorage (OS keychain).

## Commands

| Command | Shortcut | Description |
|---------|----------|-------------|
| Repo Doc: Run | `Cmd+Shift+G` | Generate/update branch docs |
| Repo Doc: Setup | — | Re-run setup wizard |
| Repo Doc: View Docs | — | Open last generated docs |

## Development

```bash
npm install
npm run compile
# F5 to launch Extension Development Host

npm run watch  # continuous compilation
```

## Architecture

```
src/
├── extension.ts       — Entry point, command registration, orchestration
├── config/            — Setup wizard (webview), settings, SecretStorage
├── git/               — Branch detection, three-dot diff
├── scanner/           — Repo file walker, language detection
├── llm/               — Provider factory (Anthropic, OpenAI, Bedrock)
├── generator/         — Prompt templates, parallel doc generation
├── publisher/         — Confluence REST API (create/update/version)
└── tracker/           — Branch → page ID mapping (workspaceState)
```

## Supported Providers

| Provider | Auth | Models |
|----------|------|--------|
| Anthropic | API Key | claude-sonnet-4-20250514, claude-opus-4 |
| OpenAI | API Key | gpt-4o, gpt-4-turbo |
| AWS Bedrock | IAM/SSO | Any Bedrock-hosted model (ARN) |

## Finding Your Confluence Parent Page ID

1. Navigate to the target parent page
2. Click "..." → "Page Information"
3. The page ID is in the URL: `.../pages/viewinfo.action?pageId=12345`

## Security

- All credentials in OS keychain (SecretStorage) — never in settings.json
- Publishes only to your configured space + parent page
- Git commands use `execFile` (immune to shell injection)
- No telemetry or external reporting
