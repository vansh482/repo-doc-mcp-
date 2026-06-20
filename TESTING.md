# Testing Guide — Repo Doc MCP Server

This guide walks you through testing the complete documentation pipeline end-to-end, from installation to seeing your docs live in Confluence and Google Docs.

## Step 0: Prerequisites

Before you begin, make sure you have Python 3.10 or newer installed. You can check by running `python3 --version` in your terminal. You also need `pip` (Python's package manager) and `git` installed.

## Step 1: Install the MCP Server

Clone or download the `repo-doc-mcp` directory, then install it in development mode. Open your terminal and run:

```bash
cd repo-doc-mcp
pip install -e . --break-system-packages
```

The `--break-system-packages` flag is needed on some Linux systems (Ubuntu 24+). On Mac, you can usually omit it.

Now install the additional packages needed for publishing:

```bash
pip install httpx google-api-python-client google-auth google-auth-httplib2 --break-system-packages
```

Verify the installation worked:

```bash
python3 -c "from src.config.settings import ServerConfig; print('Installation OK')"
```

If this prints "Installation OK", you're good to go.

## Step 2: Get Your LLM API Key

The easiest option is Anthropic Claude. Go to **console.anthropic.com**, create an account if you don't have one, and generate an API key under API Keys. Then set it as an environment variable:

```bash
# On Mac/Linux — add this to your ~/.bashrc or ~/.zshrc to make it permanent
export ANTHROPIC_API_KEY="sk-ant-api03-your-key-here"

# On Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-api03-your-key-here"
```

**Cost estimate**: A typical doc generation run for a medium-sized repo (100-300 files) costs about $0.30-0.80 with Claude Sonnet.

## Step 3: Test the Quick Scan (Free — No LLM Calls)

Before spending any API credits, verify the scanner works by running a summary-only scan against your repo:

```bash
python3 -m src.cli /path/to/your/repo --summary-only
```

This reads your repo's file tree and prints statistics like file counts, detected languages, and file types. It makes ZERO API calls, so it's completely free and instant.

You should see output like:

```
📂 Scanning repository: /path/to/your/repo
   Found 127 files, 18432 lines
   Languages: python, typescript, yaml
   Branch: main

Repository Summary: your-repo
==================================================
Branch: main
Commit: a1b2c3d4
Total Files: 127
Total Lines: 18432

Languages:
  python: 45 files
  typescript: 62 files
  yaml: 20 files
```

If this works, your installation is correct and the scanner can read your repo.

## Step 4: Generate Documentation (Uses LLM — Costs ~$0.50)

Now run the full pipeline. This scans, analyzes, and generates both technical and non-technical docs:

```bash
python3 -m src.cli /path/to/your/repo
```

This takes 1-3 minutes depending on repo size. You'll see progress output showing each stage (scanning, analyzing, generating). When it's done, you'll find two files:

```
/path/to/your/repo/docs/generated/TECHNICAL_DOC.md
/path/to/your/repo/docs/generated/NON_TECHNICAL_GUIDE.md
```

Open these files in any Markdown viewer (VS Code, GitHub, etc.) and verify they make sense for your codebase. The technical doc should have architecture details, API references, and component breakdowns. The non-technical guide should explain what the software does in plain English with analogies.

**If something looks wrong**: The most common issue is the LLM not having enough context for very large repos. Try limiting file count: add `--max-files 200` to the command, or tweak the `repo.ignore_patterns` in the config to skip irrelevant directories.

## Step 5: Set Up Confluence Publishing

### 5a: Get Your Confluence API Token

Go to **id.atlassian.com/manage-profile/security/api-tokens** and click "Create API token." Give it a name like "repo-doc-mcp" and copy the token. You'll also need your Atlassian account email and your Confluence instance URL (e.g., `https://yourcompany.atlassian.net`).

### 5b: Find Your Space Key

Open Confluence in your browser, navigate to the space where you want docs published, and look at the URL. It will look like `https://yourcompany.atlassian.net/wiki/spaces/ENG/overview`. The space key is the part after `/spaces/` — in this example, it's **ENG**.

### 5c: Create the Config File

Create a file called `repo-doc-mcp.yaml` in your repo root (or in the repo-doc-mcp directory):

```yaml
llm:
  provider: "anthropic"
  model: "claude-sonnet-4-20250514"

publish:
  confluence:
    enabled: true
    url: "https://yourcompany.atlassian.net"
    email: "you@company.com"
    api_token: "your-api-token-here"
    space_key: "ENG"
    # Optional: nest docs under a specific parent page
    # parent_page_id: "123456789"
```

**Security note**: Don't commit this file with your API token in it! Either use environment variables or add `repo-doc-mcp.yaml` to your `.gitignore`.

### 5d: Publish to Confluence

```bash
# Generate docs AND publish in one command
python3 -m src.publishers.cli /path/to/your/repo

# Or, if you already generated docs and just want to publish
python3 -m src.publishers.cli /path/to/your/repo --publish-only --confluence-only
```

You should see output like:

```
☁️  Publishing to Confluence (https://yourcompany.atlassian.net)...
  ✅ Technical Doc: https://yourcompany.atlassian.net/wiki/spaces/ENG/pages/12345/...
  ✅ Non-Technical Guide: https://yourcompany.atlassian.net/wiki/spaces/ENG/pages/12346/...
```

Click the URLs to verify the pages look correct in Confluence.

**Subsequent runs**: Running the same command again will UPDATE the existing pages (incrementing the version number) rather than creating duplicates. Your Confluence URLs stay stable.

## Step 6: Set Up Google Docs Publishing

### 6a: Create a Google Cloud Service Account

This is a one-time setup that takes about 5 minutes.

Go to **console.cloud.google.com** and either create a new project or select an existing one. Then enable the required APIs by searching for "Google Docs API" and "Google Drive API" in the API library and clicking Enable on each.

Next, create a service account by navigating to IAM & Admin → Service Accounts → Create Service Account. Give it a name like "repo-doc-publisher" and click through the wizard (you don't need to grant it any project-level roles). After creating it, click on the service account, go to the Keys tab, click Add Key → Create new key → JSON. This downloads a JSON file — save it somewhere safe (e.g., `~/.config/repo-doc-mcp/google-credentials.json`).

### 6b: Share Your Drive Folder

Create a folder in Google Drive where you want the docs to go (or use an existing one). Open the service account JSON file you downloaded and find the `client_email` field — it looks like `repo-doc-publisher@your-project.iam.gserviceaccount.com`. Right-click your Google Drive folder, click Share, and add this email address with Editor access.

Find the folder ID from the URL: when you open the folder in Google Drive, the URL looks like `https://drive.google.com/drive/folders/1ABCdefGhIjKlMnOpQrStUvWxYz`. The folder ID is the long string after `/folders/`.

### 6c: Update Your Config

Add the Google Docs section to your `repo-doc-mcp.yaml`:

```yaml
publish:
  confluence:
    enabled: true
    # ... your Confluence settings ...

  google_docs:
    enabled: true
    credentials_file: "/path/to/google-credentials.json"
    folder_id: "1ABCdefGhIjKlMnOpQrStUvWxYz"
```

### 6d: Publish to Google Docs

```bash
# Generate and publish to Google Docs
python3 -m src.publishers.cli /path/to/your/repo --google-docs-only

# Or publish existing docs
python3 -m src.publishers.cli /path/to/your/repo --publish-only --google-docs-only
```

You should see output like:

```
📄 Publishing to Google Docs...
  ✅ Technical Doc: https://docs.google.com/document/d/1ABC.../edit
  ✅ Non-Technical Guide: https://docs.google.com/document/d/1DEF.../edit
```

### 6e: Update Mode (Keep Same URLs)

After the first publish, note the document IDs from the URLs. Add them to your config to make future runs update the SAME documents instead of creating new ones:

```yaml
  google_docs:
    enabled: true
    credentials_file: "/path/to/google-credentials.json"
    folder_id: "1ABCdefGhIjKlMnOpQrStUvWxYz"
    technical_doc_id: "1ABC..."      # From the first publish URL
    non_technical_doc_id: "1DEF..."  # From the first publish URL
```

## Step 7: Test Per-MR Documentation

If you have a feature branch, you can generate MR-specific docs:

```bash
# Generate docs for a branch compared to main
python3 -m src.mr_docs.cli feature/your-branch-name

# Just see the analysis without generating docs (free, no LLM calls)
python3 -m src.mr_docs.cli feature/your-branch-name --analyze-only
```

## Troubleshooting

**"No module named 'src'"**: Make sure you're running commands from the `repo-doc-mcp` directory, or that you ran `pip install -e .` from there.

**"ANTHROPIC_API_KEY not set"**: Export the environment variable in your current terminal session. On Mac/Linux: `export ANTHROPIC_API_KEY="your-key"`. Remember that environment variables don't persist across terminal sessions unless you add them to your shell profile.

**Confluence 401 Unauthorized**: Double-check that you're using an API token (not your password), and that the email matches the account that owns the token.

**Confluence 404 Not Found**: Verify the space_key exists. Try browsing to `https://yourcompany.atlassian.net/wiki/spaces/YOUR_KEY/overview` to confirm.

**Google Docs "Service account not found"**: Make sure the credentials JSON file path is correct and the file is readable.

**Google Docs "Insufficient permissions"**: Make sure you shared the Drive folder with the service account's email address with Editor access.

**Docs are too short or generic**: This usually means the LLM didn't get enough context. Try running against a smaller repo first, or increase `llm.max_tokens` in the config to 16384.

**Generation takes too long**: For large repos (500+ files), the analysis can take 5+ minutes because of multiple LLM API calls. You can speed things up by restricting which files are analyzed — add `include_extensions: ["py", "ts"]` to the `repo` section of your config to only analyze Python and TypeScript files, for example.
