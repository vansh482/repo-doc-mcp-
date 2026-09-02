# CI/CD Pipeline — GitHub Actions Explained

> Everything about our automated build, test, and release pipeline.

---

## What is GitHub Actions?

GitHub Actions is GitHub's built-in automation system. It runs code **on GitHub's servers** (not your machine) in response to events (push, PR, tag, schedule, etc.). Think of it as: "when X happens in my repo, automatically do Y."

Each automation is called a **workflow** — a YAML file in `.github/workflows/`.

---

## Our Two Workflows

### Workflow 1: `ci.yml` (Quality Gate)

```yaml
name: CI

on:
  pull_request:
    branches: [main]     # runs when someone opens a PR to main
  push:
    branches: [main]     # runs when code is merged into main
```

**Purpose:** Catch broken code before it reaches users. If compile fails, the PR shows a red X and you know not to merge.

**Steps explained:**

| Step | What it does | Why |
|------|-------------|-----|
| `actions/checkout@v4` | Downloads your repo code onto the GitHub server | The server starts empty — it needs your code |
| `actions/setup-node@v4` | Installs Node.js 20 on the server | Your extension needs Node to compile |
| `npm ci` | Installs dependencies (exact versions from lockfile) | Faster and reproducible — no "works on my machine" issues |
| `npm run compile` | Runs TypeScript compiler | If any type error exists, this fails and PR shows red X |
| `npx vsce package --no-dependencies` | Tries to build the .vsix | Verifies extension metadata (package.json) is valid for marketplace |

---

### Workflow 2: `release.yml` (Publish to World)

```yaml
name: Release Extension

on:
  push:
    tags:
      - 'v*'     # only runs when you push a tag starting with "v" (v0.2.0, v1.0.0, etc.)
```

**Purpose:** When you're ready to release, this compiles, packages, publishes to marketplace, AND creates a GitHub release page — all automatically.

**Steps explained:**

| Step | What it does | Why |
|------|-------------|-----|
| `actions/checkout@v4` | Gets code | Same as CI |
| `actions/setup-node@v4` | Installs Node | Same as CI |
| `npm ci` | Installs deps | Same as CI |
| `npm run compile` | Compile check | Safety net — don't publish broken code |
| `npx vsce package -o repo-doc-generator.vsix` | Creates the .vsix file | `-o` gives predictable filename for the release attachment |
| `npx vsce publish` | Pushes to VS Code Marketplace | Users who have the extension get the update |
| `softprops/action-gh-release@v2` | Creates a Release page on GitHub with .vsix attached | Users can also download from GitHub directly |

---

## Key Concepts Explained

### `runs-on: ubuntu-latest`

GitHub gives you a fresh virtual machine (VM) for each run. Options:
- `ubuntu-latest` — Linux (fastest, cheapest, most common)
- `windows-latest` — if you need Windows-specific testing
- `macos-latest` — if you need macOS (slowest, limited free minutes)

We use Ubuntu because our code is pure TypeScript — compiles identically on any OS.

### `defaults: run: working-directory: vscode-extension`

Our repo has the extension in a subfolder. This tells all `run:` steps to `cd` into that folder first. Without this, every step would need `cd vscode-extension && ...`.

### `${{ secrets.VSCE_PAT }}`

A **secret** stored in GitHub (Settings > Secrets > Actions). It's your Personal Access Token for the VS Code Marketplace. GitHub injects it at runtime — never appears in logs or code. Forks can't access your secrets.

### `uses: actions/checkout@v4`

"Uses" means "run someone else's pre-built action." `actions/checkout` is official from GitHub — clones your repo. `@v4` is the version.

### `uses: softprops/action-gh-release@v2`

Community action that creates GitHub Releases. It:
- Creates the release page (like v1.0.0.0 you made manually before)
- Attaches the .vsix file as downloadable
- `generate_release_notes: true` auto-generates changelog from commits since last tag

---

## The Full Flow (What Happens When You Release)

```
You (locally):
  1. Make changes, commit, push to main
  2. Decide it's release time
  3. Run: git tag v0.2.0
  4. Run: git push origin v0.2.0

GitHub (automatically, ~2-3 minutes):
  5. Detects tag push starting with "v"
  6. Spins up a fresh Ubuntu VM
  7. Clones your repo at that exact tag/commit
  8. Installs Node 20
  9. Runs npm ci (installs deps)
  10. Runs npm run compile (TypeScript check)
  11. Runs vsce package (builds .vsix)
  12. Runs vsce publish (pushes to marketplace)
  13. Creates GitHub Release page with .vsix attached
  14. VM is destroyed (clean every time)

Users:
  15. VS Code shows "Update available" for the extension
  16. One-click update
```

---

## Git Tags Explained

### What is a tag?

A tag is a **permanent label pointing to a specific commit**. Think of it as a bookmark that says "this commit is version 0.2.0."

```
commit abc123 ← tag: v0.2.0 (points here forever)
commit def456
commit ghi789 ← tag: v0.1.0 (points here forever)
```

Unlike branches (which move forward as you commit), tags are **frozen** — they always point to the same commit.

### Tags vs Branches

| Concept | Moves? | Purpose |
|---------|--------|---------|
| **Branch** | Yes — advances with each commit | Work in progress |
| **Tag** | No — frozen on one commit forever | "This commit is a release" |

### How tags work (step by step)

```bash
# 1. You're on main, everything is ready
git checkout main
git pull

# 2. Create a tag (lightweight — just a label)
git tag v0.2.0

# 3. Push the tag to GitHub
git push origin v0.2.0

# That's it. GitHub Actions sees the tag push and runs release.yml
```

### It's the same concept as GitLab tags

Yes — **identical concept**. In GitLab:
- You create a tag (UI or CLI)
- `.gitlab-ci.yml` has `rules: - if: $CI_COMMIT_TAG` to trigger on tags
- Pipeline runs and deploys

In GitHub:
- You create a tag (UI or CLI)
- `.github/workflows/release.yml` has `on: push: tags: ['v*']` to trigger on tags
- Pipeline runs and publishes

**Same idea, different YAML syntax.**

### Comparison: GitLab vs GitHub tag triggers

```yaml
# GitLab (.gitlab-ci.yml)
deploy:
  stage: deploy
  script:
    - npm run publish
  rules:
    - if: $CI_COMMIT_TAG =~ /^v/

# GitHub (.github/workflows/release.yml)
on:
  push:
    tags:
      - 'v*'
```

Both say: "when a tag starting with `v` is pushed, run this."

### Creating tags from GitHub UI (alternative to CLI)

1. Go to your repo on GitHub
2. Click **Releases** (right sidebar)
3. Click **Draft a new release**
4. In "Choose a tag" → type `v0.2.0` → click "Create new tag on publish"
5. Select target branch: `main`
6. Fill title: `v0.2.0`
7. Click **Publish release**

This creates the tag AND triggers the pipeline. Same as `git tag` + `git push origin tag`.

### Annotated vs Lightweight tags

```bash
# Lightweight (what we use) — just a pointer
git tag v0.2.0

# Annotated — includes message, author, date (like a commit)
git tag -a v0.2.0 -m "Release 0.2.0: 10 TODO implementations + base branch UI"
```

For triggering pipelines, both work. Annotated tags are better practice for releases because they carry metadata (who tagged it, when, why).

### Useful tag commands

```bash
# List all tags
git tag

# List tags matching a pattern
git tag -l "v0.*"

# See what commit a tag points to
git show v0.2.0

# Delete a local tag (if you made a mistake)
git tag -d v0.2.0

# Delete a remote tag (if you pushed it by accident)
git push origin --delete v0.2.0

# Tag a PAST commit (not the current one)
git tag v0.1.5 abc123    # abc123 is the commit hash

# Push ALL local tags at once
git push origin --tags
```

---

## Semantic Versioning (How to Pick Version Numbers)

Format: `MAJOR.MINOR.PATCH` (e.g., `0.2.0`)

| Bump | When | Example |
|------|------|---------|
| **PATCH** (0.2.0 → 0.2.1) | Bug fixes only, no new features | Fixed a typo in prompts |
| **MINOR** (0.2.0 → 0.3.0) | New features, backwards compatible | Added custom instructions field |
| **MAJOR** (0.2.0 → 1.0.0) | Breaking changes OR "it's production-ready" | Changed settings format, users need to reconfigure |

**Our versioning so far:**
- `0.1.0` — Initial release (basic functionality)
- `0.2.0` — 10 TODO implementations + base branch UI + CI pipeline

**Leading `0.x.x`** means "pre-1.0, things might change." Once you're confident in stability → bump to `1.0.0`.

---

## One-Time Setup (Required Before First Release)

### Step 1: Get a VSCE Personal Access Token

1. Go to https://dev.azure.com
2. Sign in with the same Microsoft account you used for `devcraft-tools` publisher
3. Profile icon (top right) → **Personal Access Tokens**
4. **New Token**
5. Name: `vsce-publish`
6. Organization: **All accessible organizations**
7. Expiration: Custom → **1 year**
8. Scopes: Custom defined → find **Marketplace** → check **Manage**
9. Create → **copy the token** (won't be shown again)

### Step 2: Add as GitHub Secret

1. Go to https://github.com/vansh482/repo-doc-mcp-/settings/secrets/actions
2. **New repository secret**
3. Name: `VSCE_PAT`
4. Value: paste token
5. Add secret

### Step 3: Push workflow files to main

The `.github/workflows/` files must be on `main` for GitHub to recognize them.

---

## What `npm ci` Does vs `npm install`

| Command | Behavior |
|---------|----------|
| `npm install` | Reads package.json, resolves "best" versions, may update lockfile |
| `npm ci` | Reads package-lock.json EXACTLY, fails if lockfile is out of sync |

In CI you always use `npm ci` because:
- Faster (no resolution step)
- Deterministic (exact same versions every time)
- Catches when lockfile is out of date

---

## What `npx vsce publish` Does Internally

1. Reads `package.json` for metadata (name, version, publisher)
2. Runs prepublish script (compiles TypeScript)
3. Packages into .vsix
4. Authenticates with marketplace using `VSCE_PAT` env var
5. Uploads to `marketplace.visualstudio.com`
6. Marketplace validates package structure
7. Extension goes live (~1-2 minutes after upload)

---

## Security of This Setup

| Concern | How it's handled |
|---------|-----------------|
| Someone forks repo — can they publish as you? | No — they don't have your `VSCE_PAT` secret |
| Can someone trigger release via a PR? | No — release only triggers on tag push, only repo owners can push tags |
| Is the PAT visible in logs? | No — GitHub auto-masks secrets in output |
| What if PAT expires? | Pipeline fails with auth error. Generate new one, update secret. |
| What if someone pushes a bad tag? | Compile step fails → publish never happens |

---

## What the Pipeline Does NOT Do (and why)

| Missing thing | Why we skip it |
|--------------|---------------|
| Run tests | No tests yet (TODO). Add `npm test` step when tests exist. |
| Lint | No linter configured. Can add ESLint step later. |
| Version bump automation | You control versions manually. Auto-bump adds complexity. |
| Deploy to Open VSX | For non-Microsoft VS Code forks (Gitpod). Low priority. |
| Slack notification | Could post to Slack on release. Nice-to-have. |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Pipeline not triggering | Make sure `.github/workflows/` is on `main`, not just a branch |
| "No matching tag" | Tag must start with `v` (lowercase): `v0.2.0` not `V0.2.0` |
| `vsce publish` auth error | VSCE_PAT expired or wrong. Regenerate and update secret. |
| Release created but marketplace not updated | Check the "Publish to VS Code Marketplace" step logs in Actions tab |
| CI passes but extension is broken | CI only checks compilation. Add tests for logic verification. |

---

## Future Improvements

When we add tests:
```yaml
- name: Run tests
  run: npm test
```

When we add linting:
```yaml
- name: Lint
  run: npx eslint src/ --ext .ts
```

When we want Slack notifications:
```yaml
- name: Notify Slack
  uses: slackapi/slack-github-action@v1
  with:
    payload: '{"text": "v${{ github.ref_name }} released!"}'
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```
