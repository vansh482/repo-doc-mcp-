<div align="center">

# 🚀 Repo Doc Generator

### AI-Powered Documentation That Never Goes Stale

<br/>

```
 ┌─────────────────────────────────────────────────────────────┐
 │                                                             │
 │   📂 Your Code  ──→  🧠 AI Analysis  ──→  📄 Live Docs    │
 │                                                             │
 │   Scans repo         Understands        Auto-publishes      │
 │   structure          architecture       to Confluence        │
 │                                         & Google Docs        │
 └─────────────────────────────────────────────────────────────┘
```

<br/>

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-VS_Code-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Kotlin](https://img.shields.io/badge/Kotlin-IntelliJ-7F52FF?style=for-the-badge&logo=kotlin&logoColor=white)](https://kotlinlang.org/)
[![Claude](https://img.shields.io/badge/Claude-Anthropic-D97757?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PC9zdmc+&logoColor=white)](https://anthropic.com)
[![MCP](https://img.shields.io/badge/MCP-Protocol-000000?style=for-the-badge)](https://modelcontextprotocol.io)

<br/>

**Stop writing docs manually. Let AI keep them alive.**

[Get Started](#-quick-start) · [Features](#-features) · [How It Works](#-how-it-works) · [IDE Extensions](#-ide-extensions) · [Publishing](#-publishing)

<br/>

---

</div>

<br/>

## 🎬 Demo

```
$ repo-doc generate ./my-project

📂 Scanning repository...
   Found 142 files, 28,439 lines across 6 languages

🔍 Analyzing architecture...
   Detected: FastAPI + SQLAlchemy + React frontend
   Key patterns: Repository pattern, Event sourcing

📝 Generating documentation...
   ✅ Technical Documentation    (12,847 words)
   ✅ Non-Technical Guide        (4,231 words)
   ✅ Architecture Diagram       (Mermaid)

☁️  Publishing to Confluence...
   ✅ Technical Doc  → https://wiki.company.com/pages/12345
   ✅ Project Guide  → https://wiki.company.com/pages/12346

🎉 Done in 2m 34s
```

<br/>

## ✨ Features

<table>
<tr>
<td width="50%">

### 🧠 AI-Powered Understanding
Not just file listing — actually **understands** your code. Identifies patterns, traces data flow, maps dependencies, and explains architectural decisions.

</td>
<td width="50%">

### 📄 Dual Documentation
Generates **two docs** from one scan:
- **Technical** → For engineers (architecture, APIs, data flow)
- **Non-Technical** → For PMs & leadership (plain English, analogies)

</td>
</tr>
<tr>
<td width="50%">

### 🔄 Auto-Updates
Watches your main branch. When code changes, docs update automatically. Uses smart 3-tier detection:
- `Cosmetic` → Skip (comments, formatting)
- `Content` → Partial regen (modified functions)
- `Structural` → Full regen (new modules)

</td>
<td width="50%">

### 🌿 Branch-Aware Docs
Each feature branch gets its own documentation showing **what changed vs main**. Auto-cleaned when merged.

```
main        → "MyApp — Technical Docs"
feature/auth → "MyApp — feature/auth Docs"
                (includes diff summary)
```

</td>
</tr>
<tr>
<td width="50%">

### 🔌 IDE Integration
Works where you work — VS Code sidebar and IntelliJ tool window. One-click doc generation without leaving your editor.

</td>
<td width="50%">

### ☁️ Auto-Publish
Pushes docs to **Confluence** and **Google Docs** automatically. Your wiki stays current without anyone lifting a finger.

</td>
</tr>
</table>

<br/>

## 🏗 How It Works

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           REPO DOC GENERATOR                             │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐  │
│  │          │    │              │    │              │    │          │  │
│  │ SCANNER  │───▶│   ANALYZER   │───▶│  GENERATOR   │───▶│ PUBLISHER│  │
│  │          │    │              │    │              │    │          │  │
│  │ Walks    │    │ Regex +      │    │ Per-section  │    │ Conflu-  │  │
│  │ file tree│    │ LLM-powered  │    │ LLM calls    │    │ ence &   │  │
│  │ 65+ langs│    │ understanding│    │ for depth    │    │ GDocs    │  │
│  │          │    │              │    │              │    │          │  │
│  └──────────┘    └──────────────┘    └──────────────┘    └──────────┘  │
│       │                                                       │          │
│       │              ┌──────────────┐                         │          │
│       └─────────────▶│   WATCHER    │◀────────────────────────┘          │
│                      │              │                                    │
│                      │ Polls branch │                                    │
│                      │ Detects diffs│                                    │
│                      │ Triggers     │                                    │
│                      │ regen        │                                    │
│                      └──────────────┘                                    │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│  LLM PROVIDERS:  Anthropic │ OpenAI │ AWS Bedrock │ Ollama (local)      │
├──────────────────────────────────────────────────────────────────────────┤
│  IDE EXTENSIONS: VS Code │ IntelliJ/JetBrains                           │
└──────────────────────────────────────────────────────────────────────────┘
```

<br/>

## ⚡ Quick Start

### CLI (No IDE needed)

```bash
# Clone & setup
git clone https://github.com/vansh482/repo-doc-mcp-.git
cd repo-doc-mcp-
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Copy config
cp repo-doc-mcp.example.yaml repo-doc-mcp.yaml
# Edit repo-doc-mcp.yaml with your LLM API key

# Generate docs for any repo
python -m src.cli /path/to/any/repo --type both

# Just scan (no LLM needed)
python -m src.cli /path/to/any/repo --summary-only
```

### With AWS Bedrock (No API key needed — uses SSO)

```bash
AWS_PROFILE=your-profile AWS_REGION=us-west-2 \
python -m src.cli /path/to/repo \
  --provider bedrock \
  --model "arn:aws:bedrock:us-west-2:ACCOUNT:inference-profile/ID"
```

### Publish to Confluence

```bash
python -m src.publishers.cli /path/to/repo --confluence-only
```

### Publish to Google Docs

```bash
python -m src.publishers.cli /path/to/repo --google-docs-only
```

<br/>

## 🖥 IDE Extensions

<table>
<tr>
<td width="50%" align="center">

### VS Code

```
Cmd+Shift+P → "Repo Doc: Generate"
```

Features:
- Sidebar with action buttons
- Doc viewer with tabbed interface
- Mermaid diagram rendering
- Real-time generation progress

</td>
<td width="50%" align="center">

### IntelliJ / JetBrains

```
Tools → Repo Doc → Generate
```

Features:
- Tool window panel
- Settings page integration
- Branch watcher with status bar widget
- Auto-trigger on branch switch

</td>
</tr>
</table>

<br/>

## ☁️ Publishing

| Destination | Format | Auth | Auto-Update |
|-------------|--------|------|-------------|
| **Confluence** | XHTML Storage Format | Email + API Token | ✅ On commit |
| **Google Docs** | Batch Update API | Service Account | ✅ On commit |
| **Local Markdown** | `.md` files | None | ✅ Always |

Docs are published as **living pages** — subsequent runs update the same page (version incremented) rather than creating duplicates.

<br/>

## 🔄 Auto-Update Modes

```bash
# MODE 1: Background polling (checks every 5 min)
python -m src.watcher.cli /path/to/repo --branch main --interval 5

# MODE 2: Git hooks (fires on commit/merge)
python -m src.watcher.cli install-hooks /path/to/repo

# MODE 3: CI/CD (runs in GitHub Actions / GitLab CI)
python -m src.watcher.cli check --repo-path .
```

### Smart Change Detection

```
Small changes (formatting, comments)  → COSMETIC   → Skip regen
Code changes (modified functions)     → CONTENT    → Partial update
New modules or restructure            → STRUCTURAL → Full regen
```

<br/>

## 🧩 MCP Server Tools

The system exposes **11 MCP tools** that any MCP client can call:

| Tool | Description |
|------|-------------|
| `generate_docs` | Generate both doc types |
| `generate_technical_doc` | Technical only |
| `generate_non_technical_doc` | Non-technical only |
| `get_repo_summary` | Quick scan (no LLM) |
| `list_config` | Show current configuration |
| `update_config` | Modify settings |
| `check_and_update_docs` | Smart incremental update |
| `install_git_hooks` | Set up auto-triggers |
| `generate_ci_workflow` | Create GitHub Actions YAML |
| `generate_mr_docs` | Docs for a merge request |
| `generate_mr_docs_from_commits` | Docs from commit range |

<br/>

## 🛠 LLM Providers

```yaml
# Anthropic Claude (recommended)
llm:
  provider: "anthropic"
  model: "claude-sonnet-4-20250514"
  api_key: "sk-ant-..."

# OpenAI GPT
llm:
  provider: "openai"
  model: "gpt-4o"
  api_key: "sk-..."

# AWS Bedrock (uses SSO/IAM — no API key)
llm:
  provider: "bedrock"
  model: "arn:aws:bedrock:us-west-2:..."
  aws_profile: "your-sso-profile"

# Ollama (free, runs locally)
llm:
  provider: "ollama"
  model: "llama3.1"
  base_url: "http://localhost:11434"
```

<br/>

## 📁 Project Structure

```
repo-doc-mcp/
├── src/
│   ├── parsers/          # Scanner + Analyzer (reads & understands code)
│   ├── llm/              # Provider abstraction (Anthropic/OpenAI/Bedrock/Ollama)
│   ├── generators/       # Doc generation (section-by-section LLM calls)
│   ├── publishers/       # Confluence + Google Docs integration
│   ├── watcher/          # Branch watcher, git hooks, incremental updates
│   ├── mr_docs/          # Merge request documentation
│   ├── mcp_server/       # MCP protocol server (11 tools)
│   └── cli.py            # Command-line interface
├── vscode-extension/     # VS Code extension (TypeScript)
├── intellij-plugin/      # IntelliJ plugin (Kotlin)
├── tests/                # 60 tests
└── repo-doc-mcp.example.yaml
```

<br/>

## 🧪 Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
python -m pytest tests/ -v

# Expected: 60 passed ✅
```

<br/>

## 📋 Roadmap

- [x] Multi-LLM support (Anthropic, OpenAI, Bedrock, Ollama)
- [x] Section-by-section generation (no more truncated docs)
- [x] Confluence publisher with personal space support
- [x] Google Docs publisher
- [x] VS Code extension with sidebar + doc viewer
- [x] IntelliJ plugin with tool window
- [x] Branch watcher with 3-tier smart updates
- [x] MR/PR documentation generator
- [x] Git hooks for auto-trigger
- [ ] VS Code Marketplace publishing
- [ ] Streaming output during generation
- [ ] Custom doc templates
- [ ] Multi-language doc generation (i18n)
- [ ] GitHub Actions marketplace action

<br/>

---

<div align="center">

**Built with 🧠 by [vansh482](https://github.com/vansh482)**

*Because documentation should write itself.*

<br/>

```
     ___           ___           ___           ___
    /\  \         /\  \         /\  \         /\  \
   /::\  \       /::\  \       /::\  \       /::\  \
  /:/\:\  \     /:/\:\  \     /:/\:\  \     /:/\:\  \
 /::\~\:\  \   /::\~\:\  \   /::\~\:\  \   /:/  \:\  \
/:/\:\ \:\__\ /:/\:\ \:\__\ /:/\:\ \:\__\ /:/__/ \:\__\
\/_|::\/:/  / \:\~\:\ \/__/ \/__\:\/:/  / \:\  \ /:/  /
   |:|::/  /   \:\ \:\__\        \::/  /   \:\  /:/  /
   |:|\/__/     \:\ \/__/         \/__/     \:\/:/  /
   |:|  |        \:\__\                      \::/  /
    \|__|         \/__/                       \/__/

    R E P O   D O C   G E N E R A T O R
```

</div>
