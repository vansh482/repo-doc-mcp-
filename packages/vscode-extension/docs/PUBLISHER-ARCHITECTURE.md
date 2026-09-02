# Publisher Architecture — Multi-Target Design

> Reference doc for the unified publisher system. This describes the target architecture
> that enables adding any new doc publisher (Notion, Google Docs, SharePoint, etc.) as a
> plug-in module without touching core extension logic.

---

## The Problem Today

Adding a new publisher currently means touching 4+ places:

1. New publisher class (bespoke)
2. New auth logic (different for each: token, OAuth, git creds)
3. Wire into `extension.ts` directly
4. New settings in `package.json`
5. New setup wizard fields
6. New content format conversion (HTML for Confluence, blocks for Notion, JSON for Google)

Each publisher is a snowflake. The goal is to make it a plug-in.

---

## Target Architecture — Three Layers

```
┌─────────────────────────────────────────────────┐
│  1. AUTH LAYER (VS Code AuthenticationProvider)  │
├─────────────────────────────────────────────────┤
│  2. CONTENT LAYER (Markdown → target format)    │
├─────────────────────────────────────────────────┤
│  3. PUBLISHER LAYER (DocPublisher interface)     │
└─────────────────────────────────────────────────┘
```

---

## Layer 1: Unified Auth — VS Code `AuthenticationProvider` API

The single biggest architectural win. VS Code has a built-in auth framework that handles:

- **Token storage** — secure, automatic
- **Token refresh** — automatic, no manual expiry handling
- **Sign-in/sign-out** — native Accounts menu (bottom-left in VS Code)
- **Multi-account** — personal Confluence + work Google + Notion all at once
- **OAuth redirect** — opens browser, captures callback

### Usage Pattern

```typescript
// Each publisher registers its auth provider ONCE (in activate())
vscode.authentication.registerAuthenticationProvider(
  'confluence',                    // provider ID
  'Confluence',                   // display name
  new ConfluenceAuthProvider()    // handles the flow
);

// Then ANY code can request a session:
const session = await vscode.authentication.getSession('confluence', ['read', 'write']);
// session.accessToken is ready to use — no manual storage needed
```

### Auth Type Per Provider

| Provider | Auth Type | How AuthProvider handles it |
|----------|-----------|---------------------------|
| Confluence | API token | Simple input → store in SecretStorage (degenerate OAuth) |
| Notion | Integration token | Same — token input, bearer auth |
| Google Docs | OAuth 2.0 + PKCE | Opens browser → consent → callback → stores + auto-refreshes |
| SharePoint | Azure AD OAuth | Same as Google, different endpoint |
| GitHub Wiki | Built-in | VS Code already has `github` auth provider — reuse directly |
| Slack | Webhook URL or Bot token | URL as config setting, token via simple input |

### Key Benefit

You write the auth flow once per provider, and it lives *outside* your publisher logic. The publisher just calls `getSession()` — it never knows whether that token came from OAuth, a user paste, or an automatic refresh.

### OAuth Redirect Handling

For Google/Microsoft OAuth, VS Code needs to handle the browser callback:

1. **`vscode.env.asExternalUri`** — VS Code generates a redirect URI automatically. Works in desktop VS Code.
2. **Device code flow** — User gets a code, pastes it in browser. Works everywhere (Remote SSH, Codespaces, web).

Both are well-documented patterns supported by the `AuthenticationProvider` API.

---

## Layer 2: Content Transformer Pipeline

The LLM always outputs markdown. Each publisher needs a different format. Instead of converting inside each publisher, centralize the transformation:

### Interface

```typescript
interface ContentTransformer {
  format: 'html' | 'notion-blocks' | 'google-ops' | 'markdown';
  transform(markdown: string): string | object;
}
```

### Implementations

| Target | Transformer | Notes |
|--------|-------------|-------|
| Confluence, SharePoint | `MarkdownToHtml` | Already built (existing converter in `publisher/`) |
| Notion | `MarkdownToNotionBlocks` | Libraries exist (`notion-md-converter`, `@tryfabric/martian`) |
| Google Docs | `MarkdownToGoogleOps` | Hardest — JSON batch update operations |
| GitHub Wiki, Markdown files | `Identity` | Pass-through — they accept markdown natively |

### Benefits

- Fix a markdown rendering bug once → all HTML-based publishers get the fix
- Add a new markdown feature (mermaid diagrams, tables) → all publishers benefit
- Test transformers in isolation (pure functions, no side effects)

---

## Layer 3: Publisher Interface

```typescript
interface PublishResult {
  pageId: string;
  url: string;
}

interface DocPublisher {
  id: string;                       // e.g. 'confluence', 'notion'
  displayName: string;              // e.g. 'Confluence', 'Notion'
  authProviderId: string;           // links to Layer 1
  contentFormat: ContentFormat;      // links to Layer 2

  createPage(title: string, content: string): Promise<PublishResult>;
  updatePage(pageId: string, title: string, content: string): Promise<PublishResult>;
  getPageVersion?(pageId: string): Promise<number>;  // optional — not all platforms version
}
```

### Publisher Registry

```typescript
// publishers/index.ts
const PUBLISHERS: Record<string, () => DocPublisher> = {
  confluence: () => new ConfluencePublisher(),
  notion: () => new NotionPublisher(),
  github_wiki: () => new GitHubWikiPublisher(),
  markdown: () => new MarkdownFilePublisher(),
};

export function getPublisher(id: string): DocPublisher {
  const factory = PUBLISHERS[id];
  if (!factory) throw new Error(`Unknown publisher: ${id}`);
  return factory();
}
```

---

## Multi-Publisher Simultaneous Output

After multiple publishers are onboarded, users can select multiple targets per run:

### UI

- Sidebar: multi-select checkboxes or a settings array `repoDoc.publishers: ["confluence", "slack"]`
- Per-run override possible via quick pick

### Implementation

```typescript
const selectedPublishers = getSelectedPublishers(); // from settings
const transformer = getTransformer(publisher.contentFormat);
const content = transformer.transform(markdown);

// Publish to all targets in parallel
const results = await Promise.all(
  selectedPublishers.map(async (publisher) => {
    const content = getTransformer(publisher.contentFormat).transform(markdown);
    const existing = tracker.getPage(branch, publisher.id);
    if (existing) {
      return publisher.updatePage(existing.pageId, title, content);
    }
    return publisher.createPage(title, content);
  })
);

// Track all results
results.forEach((result, i) => {
  tracker.setPage(branch, selectedPublishers[i].id, result.pageId);
});
```

### Tracker Changes

Current tracker maps `branch → { technicalPageId, nonTechnicalPageId }`. Needs to become:

```typescript
// Before:
{ "feature/login": { technicalPageId: "123", nonTechnicalPageId: "456" } }

// After:
{ "feature/login": {
    confluence: { technicalPageId: "123", nonTechnicalPageId: "456" },
    notion: { technicalPageId: "abc", nonTechnicalPageId: "def" },
    markdown: { technicalPath: ".repodoc/login-tech.md", nonTechnicalPath: ".repodoc/login-summary.md" }
  }
}
```

---

## How to Onboard a New Publisher (After Foundation)

Example: Adding **Notion**

1. **Auth** — Write `NotionAuthProvider implements AuthenticationProvider` (~20 lines: prompt for token, store it)
2. **Transformer** — Write `MarkdownToNotionBlocks` (or wrap `@tryfabric/martian` library)
3. **Publisher** — Write `NotionPublisher implements DocPublisher` (create/update via `@notionhq/client`)
4. **Register** — Add to `publishers/index.ts` registry

That's it. No touching `extension.ts`, no new setup wizard screens, no settings wiring. The framework handles:

- Showing Notion in the Accounts menu
- Asking for auth when user picks Notion as target
- Converting content automatically via the transformer
- Tracking page IDs generically

---

## Build Order & Effort

| # | Task | Effort | Depends On |
|---|------|--------|------------|
| 1 | `DocPublisher` interface + factory | 2-3 hours | — |
| 2 | `ContentTransformer` pipeline | 3-4 hours | — |
| 3 | Migrate existing Confluence to new pattern | Half day | #1, #2 |
| 4 | `AuthenticationProvider` for Confluence | 2-3 hours | #3 |
| 5 | Multi-publisher support (parallel publish) | Half day | #1, #3 |
| | **Total foundation** | **~1.5-2 days** | |

After foundation, each new publisher:

| Publisher | Effort | Why |
|-----------|--------|-----|
| Markdown files | 2-3 hours | No API, no auth, Identity transformer |
| GitHub Wiki | 0.5-1 day | Uses built-in git/github auth, Identity transformer |
| Slack | 0.5-1 day | Webhook (no auth) or bot token, just POST a message |
| Notion | 1-2 days | Simple auth, but block conversion is the main work |
| Google Docs | 3-5 days | OAuth setup + hardest content model (batch JSON ops) |
| SharePoint | 3-5 days | Azure AD OAuth + Microsoft Graph API |

---

## Data Security Principle

This extension is a **pipe, not a platform**. The architecture deliberately avoids any intermediary:

```
User's machine (git diff) → LLM API (user's creds) → User's machine → Publisher API (user's creds)
```

- No data passes through any server we control
- No telemetry capturing code content
- No persistent storage of diffs or docs locally
- The user's existing trust relationships (with their LLM provider and their doc platform) are the only ones that matter

**When evaluating new publishers:** each publisher only needs the user's own credentials for that platform. We never proxy, cache, or relay content through a third party. This principle must hold for any new publisher added.

**For maximum isolation:** AWS Bedrock keeps LLM calls within the user's own AWS account boundary.

---

## Key References

- [VS Code AuthenticationProvider API](https://code.visualstudio.com/api/references/vscode-api#AuthenticationProvider)
- [VS Code Accounts menu](https://code.visualstudio.com/api/extension-guides/authentication)
- [`vscode.env.asExternalUri`](https://code.visualstudio.com/api/references/vscode-api#env.asExternalUri) — for OAuth redirects
- [Notion SDK](https://github.com/makenotion/notion-sdk-js)
- [Google Docs API](https://developers.google.com/docs/api/reference/rest)
- [Microsoft Graph - OneNote](https://learn.microsoft.com/en-us/graph/onenote-concept-overview)
