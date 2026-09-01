# @repodoc/core Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract a shared `@repodoc/core` package from the VS Code extension monolith so CLI, MCP server, and IntelliJ can consume the same pipeline engine.

**Architecture:** Monorepo with npm workspaces. Core defines adapter interfaces (auth, config, storage, progress) that consumers implement. Framework-independent modules (git, scanner, llm, generator, publisher) move into core unchanged. VS Code extension becomes a thin shell that creates adapters and calls `runPipeline()`.

**Tech Stack:** TypeScript 5.3+, Node 22, npm workspaces, vitest (new — for core tests)

**Spec:** `docs/CORE-EXTRACTION-ARCHITECTURE.md`

## Global Constraints

- npm workspaces (not pnpm — pnpm not installed via Volta)
- `@repodoc/core` must have ZERO `vscode` imports — enforced by tsconfig excluding vscode types
- VS Code extension module format stays `commonjs` (VS Code requirement)
- Core package uses `Node16` module resolution for future ESM compat
- All existing VS Code extension functionality must keep working after each task
- No new publishers during extraction — just Confluence migrated to the new interface

---

### Task 1: Create Monorepo Scaffold

**Files:**
- Create: `package.json` (root workspace)
- Create: `packages/core/package.json`
- Create: `packages/core/tsconfig.json`
- Create: `packages/core/src/index.ts` (empty barrel)
- Create: `tsconfig.base.json` (root)
- Modify: `vscode-extension/package.json` (move under packages/)
- Modify: `vscode-extension/tsconfig.json` (extend base)

**Interfaces:**
- Consumes: nothing
- Produces: working monorepo where `npm run build` compiles both packages

- [ ] **Step 1: Create root package.json with workspaces**

```jsonc
// repo-doc-mcp/package.json
{
  "name": "repodoc",
  "private": true,
  "workspaces": ["packages/*"],
  "scripts": {
    "build": "npm run build --workspaces",
    "build:core": "npm run build --workspace=@repodoc/core",
    "build:vscode": "npm run build --workspace=repo-doc-generator",
    "test": "npm run test --workspaces --if-present"
  }
}
```

- [ ] **Step 2: Create tsconfig.base.json at repo root**

```jsonc
// repo-doc-mcp/tsconfig.base.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "Node16",
    "moduleResolution": "Node16",
    "strict": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true
  }
}
```

- [ ] **Step 3: Move vscode-extension into packages/**

```bash
# From repo-doc-mcp/
mkdir -p packages
git mv vscode-extension packages/vscode-extension
```

- [ ] **Step 4: Update vscode-extension tsconfig to extend base**

Modify `packages/vscode-extension/tsconfig.json`:
```jsonc
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "module": "commonjs",
    "target": "ES2020",
    "outDir": "out",
    "rootDir": "src",
    "lib": ["ES2020"]
  },
  "exclude": ["node_modules", ".vscode-test", "out"]
}
```

Note: VS Code requires `commonjs` module format, so we override the base config's `Node16` module setting.

- [ ] **Step 5: Create packages/core/package.json**

```jsonc
{
  "name": "@repodoc/core",
  "version": "0.1.0",
  "description": "Shared core engine for Repo Doc Generator — git diff → scan → LLM → publish pipeline",
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "scripts": {
    "build": "tsc",
    "test": "echo \"no tests yet\""
  },
  "license": "MIT"
}
```

- [ ] **Step 6: Create packages/core/tsconfig.json**

```jsonc
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./dist",
    "rootDir": "./src",
    "composite": true
  },
  "include": ["src/**/*"]
}
```

- [ ] **Step 7: Create empty barrel packages/core/src/index.ts**

```typescript
// Public API — will be populated as modules are extracted
```

- [ ] **Step 8: Install workspace dependencies and verify build**

```bash
cd /Users/vgupta/Downloads/extension/repo-doc-mcp
npm install
npm run build:core
npm run build:vscode
```

Expected: both packages compile without errors.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: create monorepo scaffold with npm workspaces

Move vscode-extension into packages/, add @repodoc/core package skeleton,
shared tsconfig.base.json, and root workspace configuration."
```

---

### Task 2: Define Core Adapter Interfaces

**Files:**
- Create: `packages/core/src/auth/types.ts`
- Create: `packages/core/src/config/types.ts`
- Create: `packages/core/src/storage/types.ts`
- Create: `packages/core/src/progress/types.ts`
- Create: `packages/core/src/publisher/types.ts`
- Create: `packages/core/src/transformer/types.ts`
- Modify: `packages/core/src/index.ts` (re-export all types)

**Interfaces:**
- Consumes: nothing
- Produces: `AuthProvider`, `Credential`, `CredentialScope`, `ConfigProvider`, `RepoDocConfig`, `DocLength`, `LLMProviderType`, `StorageProvider`, `BranchPages`, `ProgressReporter`, `ProgressStep`, `DocPublisher`, `PublishResult`, `PublisherConfig`, `ContentTransformer`, `ContentFormat`

- [ ] **Step 1: Create packages/core/src/auth/types.ts**

```typescript
export type CredentialScope = 'llm' | 'publisher';

export interface Credential {
  value: string;
  expiresAt?: Date;
  metadata?: Record<string, string>;
}

export interface AuthProvider {
  getCredential(scope: CredentialScope, providerId: string): Promise<Credential | undefined>;
  setCredential?(scope: CredentialScope, providerId: string, credential: Credential): Promise<void>;
  validateCredential?(scope: CredentialScope, providerId: string): Promise<boolean>;
  refreshCredential?(scope: CredentialScope, providerId: string): Promise<Credential | undefined>;
}
```

- [ ] **Step 2: Create packages/core/src/config/types.ts**

```typescript
export type DocLength = 'concise' | 'standard' | 'detailed';
export type LLMProviderType = 'anthropic' | 'openai' | 'bedrock';

export interface RepoDocConfig {
  llm: {
    provider: LLMProviderType;
    model: string;
  };
  baseBranch: string;
  docLength: DocLength;
  publishers: string[];
  publisherConfigs: Record<string, Record<string, unknown>>;
  bedrock?: {
    region: string;
    profile: string;
  };
}

export interface ConfigProvider {
  getConfig(): Promise<RepoDocConfig>;
}
```

- [ ] **Step 3: Create packages/core/src/storage/types.ts**

```typescript
export interface BranchPages {
  technicalPageId: string;
  nonTechnicalPageId: string;
  lastUpdated: string;
}

export interface StorageProvider {
  getPages(branch: string, publisherId: string): Promise<BranchPages | undefined>;
  setPages(branch: string, publisherId: string, pages: BranchPages): Promise<void>;
  removeBranch(branch: string): Promise<void>;
  getHistory(): Promise<Array<{ branch: string; publisherId: string; pages: BranchPages }>>;
}
```

- [ ] **Step 4: Create packages/core/src/progress/types.ts**

```typescript
export interface ProgressStep {
  step: 'config' | 'git' | 'scan' | 'llm' | 'generate' | 'publish' | 'done' | 'error';
  message: string;
  data?: Record<string, unknown>;
  percentage?: number;
}

export interface ProgressReporter {
  report(step: ProgressStep): void;
}

export const nullProgress: ProgressReporter = {
  report() {},
};
```

- [ ] **Step 5: Create packages/core/src/publisher/types.ts**

```typescript
export interface PublishResult {
  pageId: string;
  url: string;
  version?: number;
}

export interface PublisherConfig {
  [key: string]: unknown;
}

export interface DocPublisher {
  readonly id: string;
  readonly displayName: string;
  initialize(credential: { value: string; metadata?: Record<string, string> }, config: PublisherConfig): void;
  createPage(title: string, content: string): Promise<PublishResult>;
  updatePage(pageId: string, title: string, content: string, currentVersion?: number): Promise<PublishResult>;
  getPageVersion?(pageId: string): Promise<number>;
  pageExists?(pageId: string): Promise<boolean>;
  afterPublish?(pageId: string): Promise<void>;
}
```

- [ ] **Step 6: Create packages/core/src/transformer/types.ts**

```typescript
export type ContentFormat = 'html' | 'confluence-storage' | 'notion-blocks' | 'google-ops' | 'markdown';

export interface ContentTransformer {
  readonly inputFormat: 'markdown';
  readonly outputFormat: ContentFormat;
  transform(markdown: string): string;
}
```

- [ ] **Step 7: Update packages/core/src/index.ts barrel**

```typescript
export type { AuthProvider, Credential, CredentialScope } from './auth/types';
export type { ConfigProvider, RepoDocConfig, DocLength, LLMProviderType } from './config/types';
export type { StorageProvider, BranchPages } from './storage/types';
export type { ProgressReporter, ProgressStep } from './progress/types';
export { nullProgress } from './progress/types';
export type { DocPublisher, PublishResult, PublisherConfig } from './publisher/types';
export type { ContentTransformer, ContentFormat } from './transformer/types';
```

- [ ] **Step 8: Build and verify**

```bash
cd /Users/vgupta/Downloads/extension/repo-doc-mcp
npm run build:core
```

Expected: compiles, generates `.d.ts` files in `packages/core/dist/`.

- [ ] **Step 9: Commit**

```bash
git add packages/core/src/
git commit -m "feat(core): define adapter interfaces — auth, config, storage, progress, publisher, transformer"
```

---

### Task 3: Move Framework-Independent Modules to Core

**Files:**
- Move: `packages/vscode-extension/src/git/diff.ts` → `packages/core/src/git/diff.ts`
- Move: `packages/vscode-extension/src/scanner/scanner.ts` → `packages/core/src/scanner/scanner.ts`
- Move: `packages/vscode-extension/src/llm/provider.ts` → `packages/core/src/llm/provider.ts`
- Move: `packages/vscode-extension/src/llm/anthropic.ts` → `packages/core/src/llm/anthropic.ts`
- Move: `packages/vscode-extension/src/llm/openai.ts` → `packages/core/src/llm/openai.ts`
- Move: `packages/vscode-extension/src/llm/bedrock.ts` → `packages/core/src/llm/bedrock.ts`
- Move: `packages/vscode-extension/src/generator/generator.ts` → `packages/core/src/generator/generator.ts`
- Move: `packages/vscode-extension/src/generator/prompts.ts` → `packages/core/src/generator/prompts.ts`
- Modify: `packages/core/src/generator/prompts.ts:4` — change `DocLength` import from `../config/settings` to `../config/types`
- Modify: `packages/core/package.json` — add dependencies (`@anthropic-ai/sdk`, `openai`, `@aws-sdk/client-bedrock-runtime`, `@aws-sdk/credential-providers`)
- Modify: `packages/core/src/index.ts` — add re-exports for moved modules
- Modify: `packages/vscode-extension/package.json` — add `@repodoc/core` as dependency, remove moved SDK deps
- Modify: `packages/vscode-extension/src/extension.ts` — update imports to use `@repodoc/core`
- Modify: `packages/vscode-extension/src/config/settings.ts` — import `DocLength` from `@repodoc/core`

**Interfaces:**
- Consumes: Task 2 types (`DocLength` from `config/types`)
- Produces: `getBranchDiff`, `detectBaseBranch`, `filterDiffByFiles`, `BranchDiff`, `scanRepo`, `RepoContext`, `createProvider`, `LLMProvider`, `LLMResponse`, `TokenUsage`, `ProviderType`, `ProviderConfig`, `generateDocs`, `GeneratedDocs`

- [ ] **Step 1: Move git module**

```bash
cd /Users/vgupta/Downloads/extension/repo-doc-mcp
mkdir -p packages/core/src/git
git mv packages/vscode-extension/src/git/diff.ts packages/core/src/git/diff.ts
```

No changes needed — `diff.ts` has zero VS Code imports (uses `child_process` and `util`).

- [ ] **Step 2: Move scanner module**

```bash
mkdir -p packages/core/src/scanner
git mv packages/vscode-extension/src/scanner/scanner.ts packages/core/src/scanner/scanner.ts
```

No changes needed — uses `fs/promises` and `path` only.

- [ ] **Step 3: Move LLM module**

```bash
mkdir -p packages/core/src/llm
git mv packages/vscode-extension/src/llm/provider.ts packages/core/src/llm/provider.ts
git mv packages/vscode-extension/src/llm/anthropic.ts packages/core/src/llm/anthropic.ts
git mv packages/vscode-extension/src/llm/openai.ts packages/core/src/llm/openai.ts
git mv packages/vscode-extension/src/llm/bedrock.ts packages/core/src/llm/bedrock.ts
```

No changes needed — these use their SDKs and `fetch` only.

- [ ] **Step 4: Move generator module and fix import**

```bash
mkdir -p packages/core/src/generator
git mv packages/vscode-extension/src/generator/generator.ts packages/core/src/generator/generator.ts
git mv packages/vscode-extension/src/generator/prompts.ts packages/core/src/generator/prompts.ts
```

Then fix the `DocLength` import in `packages/core/src/generator/prompts.ts` line 3:

```typescript
// Before:
import type { DocLength } from '../config/settings';

// After:
import type { DocLength } from '../config/types';
```

And fix `packages/core/src/generator/generator.ts` line 4:

```typescript
// Before:
import type { DocLength } from '../config/settings';

// After:
import type { DocLength } from '../config/types';
```

- [ ] **Step 5: Add SDK dependencies to core package.json**

Update `packages/core/package.json` to add:

```jsonc
{
  "dependencies": {
    "@anthropic-ai/sdk": "^0.30.0",
    "@aws-sdk/client-bedrock-runtime": "^3.400.0",
    "@aws-sdk/credential-providers": "^3.1113.0",
    "openai": "^4.20.0"
  }
}
```

- [ ] **Step 6: Update core index.ts with all re-exports**

```typescript
// Adapter interfaces
export type { AuthProvider, Credential, CredentialScope } from './auth/types';
export type { ConfigProvider, RepoDocConfig, DocLength, LLMProviderType } from './config/types';
export type { StorageProvider, BranchPages } from './storage/types';
export type { ProgressReporter, ProgressStep } from './progress/types';
export { nullProgress } from './progress/types';
export type { DocPublisher, PublishResult, PublisherConfig } from './publisher/types';
export type { ContentTransformer, ContentFormat } from './transformer/types';

// Git
export { getBranchDiff, detectBaseBranch, filterDiffByFiles } from './git/diff';
export type { BranchDiff } from './git/diff';

// Scanner
export { scanRepo } from './scanner/scanner';
export type { RepoContext } from './scanner/scanner';

// LLM
export { createProvider } from './llm/provider';
export type { LLMProvider, LLMResponse, TokenUsage, ProviderType, ProviderConfig } from './llm/provider';

// Generator
export { generateDocs } from './generator/generator';
export type { GeneratedDocs } from './generator/generator';
```

- [ ] **Step 7: Add @repodoc/core dependency to vscode-extension**

In `packages/vscode-extension/package.json`, add to dependencies:

```jsonc
"@repodoc/core": "*"
```

And remove the SDK deps that moved to core (they'll be resolved transitively):

```jsonc
// Remove these from vscode-extension dependencies:
// "@anthropic-ai/sdk": "^0.30.0",
// "@aws-sdk/client-bedrock-runtime": "^3.400.0",
// "@aws-sdk/credential-providers": "^3.1113.0",
// "openai": "^4.20.0"
```

- [ ] **Step 8: Update extension.ts imports**

In `packages/vscode-extension/src/extension.ts`, change:

```typescript
// Before:
import { getBranchDiff, detectBaseBranch, filterDiffByFiles } from './git/diff';
import { scanRepo } from './scanner/scanner';
import { createProvider } from './llm/provider';
import { generateDocs } from './generator/generator';

// After:
import { getBranchDiff, detectBaseBranch, filterDiffByFiles, scanRepo, createProvider, generateDocs } from '@repodoc/core';
```

Keep the existing VS Code-specific imports unchanged (`SecretStore`, `getConfig`, `isConfigured`, etc.).

- [ ] **Step 9: Update config/settings.ts DocLength import**

In `packages/vscode-extension/src/config/settings.ts` line 4, change:

```typescript
// Before: (DocLength defined locally)
export type DocLength = "concise" | "standard" | "detailed";

// After: re-export from core
import type { DocLength } from '@repodoc/core';
export type { DocLength };
```

Remove the local `DocLength` type definition from this file.

- [ ] **Step 10: Install dependencies and build**

```bash
cd /Users/vgupta/Downloads/extension/repo-doc-mcp
npm install
npm run build:core
npm run build:vscode
```

Expected: both compile. The VS Code extension uses `@repodoc/core` for git/scanner/llm/generator modules.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "refactor: move framework-independent modules (git, scanner, llm, generator) to @repodoc/core

Modules moved unchanged — zero logic modifications. VS Code extension now
imports these from @repodoc/core instead of local relative paths."
```

---

### Task 4: Extract Confluence Publisher + Transformer

**Files:**
- Create: `packages/core/src/publisher/confluence.ts` (refactored from vscode-extension version)
- Create: `packages/core/src/publisher/registry.ts`
- Create: `packages/core/src/transformer/html.ts` (extracted `markdownToConfluenceStorage` function)
- Create: `packages/core/src/transformer/identity.ts`
- Delete: `packages/vscode-extension/src/publisher/confluence.ts`
- Modify: `packages/core/src/index.ts` — add new exports
- Modify: `packages/vscode-extension/src/extension.ts` — import from core

**Interfaces:**
- Consumes: `DocPublisher`, `PublishResult`, `PublisherConfig`, `ContentTransformer` from Task 2
- Produces: `ConfluencePublisher` (class implementing `DocPublisher`), `PublisherRegistry`, `MarkdownToHtmlTransformer`, `IdentityTransformer`

- [ ] **Step 1: Create packages/core/src/transformer/html.ts**

Extract `markdownToConfluenceStorage`, `convertNestedList`, and `escapeXml` from the current `packages/vscode-extension/src/publisher/confluence.ts` (lines 135-270). Place them in this file:

```typescript
import type { ContentTransformer } from './types';

export class MarkdownToHtmlTransformer implements ContentTransformer {
  readonly inputFormat = 'markdown' as const;
  readonly outputFormat = 'confluence-storage' as const;

  transform(markdown: string): string {
    return markdownToConfluenceStorage(markdown);
  }
}

function markdownToConfluenceStorage(markdown: string): string {
  // ... exact copy of existing function from confluence.ts lines 135-227
}

function convertNestedList(block: string): string {
  // ... exact copy from confluence.ts lines 229-261
}

function escapeXml(str: string): string {
  // ... exact copy from confluence.ts lines 263-270
}
```

Copy all three functions verbatim from the existing `confluence.ts`.

- [ ] **Step 2: Create packages/core/src/transformer/identity.ts**

```typescript
import type { ContentTransformer } from './types';

export class IdentityTransformer implements ContentTransformer {
  readonly inputFormat = 'markdown' as const;
  readonly outputFormat = 'markdown' as const;

  transform(markdown: string): string {
    return markdown;
  }
}
```

- [ ] **Step 3: Refactor ConfluencePublisher to implement DocPublisher interface**

Create `packages/core/src/publisher/confluence.ts`:

```typescript
import type { DocPublisher, PublishResult, PublisherConfig } from './types';

export interface ConfluenceConfig {
  baseUrl: string;
  spaceKey: string;
  parentPageId: string;
}

export class ConfluencePublisher implements DocPublisher {
  readonly id = 'confluence';
  readonly displayName = 'Confluence';

  private authHeader = '';
  private config: ConfluenceConfig = { baseUrl: '', spaceKey: '', parentPageId: '' };

  initialize(credential: { value: string; metadata?: Record<string, string> }, config: PublisherConfig): void {
    const email = credential.metadata?.email || '';
    this.authHeader = 'Basic ' + Buffer.from(`${email}:${credential.value}`).toString('base64');
    this.config = {
      baseUrl: config.baseUrl as string,
      spaceKey: config.spaceKey as string,
      parentPageId: config.parentPageId as string,
    };
  }

  async createPage(title: string, content: string): Promise<PublishResult> {
    const body = {
      type: 'page',
      title,
      space: { key: this.config.spaceKey },
      ancestors: [{ id: this.config.parentPageId }],
      body: { storage: { value: content, representation: 'storage' } },
    };

    const response = await this.request('/rest/api/content', {
      method: 'POST',
      body: JSON.stringify(body),
    });

    return {
      pageId: response.id,
      url: `${this.config.baseUrl}${response._links.webui}`,
      version: response.version.number,
    };
  }

  async updatePage(pageId: string, title: string, content: string, currentVersion?: number): Promise<PublishResult> {
    const version = currentVersion ?? await this.getPageVersion(pageId);
    const body = {
      type: 'page',
      title,
      version: { number: version + 1 },
      body: { storage: { value: content, representation: 'storage' } },
    };

    const response = await this.request(`/rest/api/content/${pageId}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    });

    return {
      pageId: response.id,
      url: `${this.config.baseUrl}${response._links.webui}`,
      version: response.version.number,
    };
  }

  async getPageVersion(pageId: string): Promise<number> {
    const response = await this.request(`/rest/api/content/${pageId}?expand=version`);
    return response.version.number;
  }

  async pageExists(pageId: string): Promise<boolean> {
    try {
      await this.request(`/rest/api/content/${pageId}`);
      return true;
    } catch {
      return false;
    }
  }

  async afterPublish(pageId: string): Promise<void> {
    const currentUser = await this.request('/rest/api/user/current');
    const accountId = currentUser.accountId;

    const restrictions = [
      {
        operation: 'read',
        restrictions: { user: { results: [{ type: 'known', accountId }] }, group: { results: [] } },
      },
      {
        operation: 'update',
        restrictions: { user: { results: [{ type: 'known', accountId }] }, group: { results: [] } },
      },
    ];

    await this.request(`/rest/api/content/${pageId}/restriction`, {
      method: 'PUT',
      body: JSON.stringify(restrictions),
    });
  }

  private async request(path: string, options: RequestInit = {}): Promise<any> {
    const url = `${this.config.baseUrl}${path}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Authorization': this.authHeader,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        ...(options.headers || {}),
      },
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(`Confluence API error (${response.status}): ${errorBody}`);
    }

    return response.json();
  }
}
```

- [ ] **Step 4: Create packages/core/src/publisher/registry.ts**

```typescript
import type { DocPublisher } from './types';
import type { ContentTransformer } from '../transformer/types';

interface RegisteredPublisher {
  publisher: DocPublisher;
  transformer: ContentTransformer;
}

export class PublisherRegistry {
  private publishers = new Map<string, RegisteredPublisher>();

  register(publisher: DocPublisher, transformer: ContentTransformer): void {
    this.publishers.set(publisher.id, { publisher, transformer });
  }

  get(id: string): RegisteredPublisher | undefined {
    return this.publishers.get(id);
  }

  getAll(): RegisteredPublisher[] {
    return Array.from(this.publishers.values());
  }

  has(id: string): boolean {
    return this.publishers.has(id);
  }

  getIds(): string[] {
    return Array.from(this.publishers.keys());
  }
}
```

- [ ] **Step 5: Update core index.ts**

Add to `packages/core/src/index.ts`:

```typescript
// Publisher
export { ConfluencePublisher } from './publisher/confluence';
export type { ConfluenceConfig } from './publisher/confluence';
export { PublisherRegistry } from './publisher/registry';

// Transformers
export { MarkdownToHtmlTransformer } from './transformer/html';
export { IdentityTransformer } from './transformer/identity';
```

- [ ] **Step 6: Delete old confluence.ts from vscode-extension**

```bash
git rm packages/vscode-extension/src/publisher/confluence.ts
rmdir packages/vscode-extension/src/publisher 2>/dev/null || true
```

- [ ] **Step 7: Update extension.ts Confluence import**

In `packages/vscode-extension/src/extension.ts`, change:

```typescript
// Before:
import { ConfluencePublisher } from './publisher/confluence';

// After:
import { ConfluencePublisher } from '@repodoc/core';
```

- [ ] **Step 8: Build and verify**

```bash
npm run build:core
npm run build:vscode
```

Expected: both compile. The extension now uses `ConfluencePublisher` from core.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: extract publisher + transformer to @repodoc/core

- ConfluencePublisher refactored to implement DocPublisher interface
- markdownToConfluenceStorage extracted into MarkdownToHtmlTransformer
- Added PublisherRegistry and IdentityTransformer
- Removed old confluence.ts from vscode-extension"
```

---

### Task 5: Create Pipeline Orchestrator

**Files:**
- Create: `packages/core/src/pipeline.ts`
- Modify: `packages/core/src/index.ts` — add pipeline exports

**Interfaces:**
- Consumes: All modules from Tasks 2-4 (`AuthProvider`, `ConfigProvider`, `StorageProvider`, `ProgressReporter`, `DocPublisher`, `ContentTransformer`, `getBranchDiff`, `detectBaseBranch`, `filterDiffByFiles`, `scanRepo`, `createProvider`, `generateDocs`, `PublisherRegistry`)
- Produces: `runPipeline(adapters, options, registry, cancellation?) → PipelineResult`, `PipelineAdapters`, `PipelineOptions`, `PipelineResult`, `PublisherResult`

- [ ] **Step 1: Create packages/core/src/pipeline.ts**

```typescript
import { getBranchDiff, detectBaseBranch, filterDiffByFiles } from './git/diff';
import { scanRepo } from './scanner/scanner';
import { createProvider } from './llm/provider';
import { generateDocs } from './generator/generator';
import type { GeneratedDocs } from './generator/generator';
import type { AuthProvider } from './auth/types';
import type { ConfigProvider } from './config/types';
import type { StorageProvider } from './storage/types';
import type { ProgressReporter } from './progress/types';
import type { PublishResult } from './publisher/types';
import type { PublisherRegistry } from './publisher/registry';

export interface PipelineAdapters {
  auth: AuthProvider;
  config: ConfigProvider;
  storage: StorageProvider;
  progress: ProgressReporter;
}

export interface PipelineOptions {
  repoPath: string;
  baseBranchOverride?: string;
  selectedFiles?: string[];
  instructions?: string;
  publishers?: string[];
  dryRun?: boolean;
}

export interface PublisherResultEntry {
  publisherId: string;
  technical: PublishResult;
  nonTechnical: PublishResult;
}

export interface PipelineResult {
  docs: GeneratedDocs;
  published: PublisherResultEntry[];
  localFallback?: string;
}

export async function runPipeline(
  adapters: PipelineAdapters,
  options: PipelineOptions,
  registry: PublisherRegistry,
  cancellation?: { isCancelled: () => boolean }
): Promise<PipelineResult> {
  const { auth, config, storage, progress } = adapters;

  progress.report({ step: 'config', message: 'Loading configuration...' });
  const cfg = await config.getConfig();

  progress.report({ step: 'git', message: 'Detecting base branch...' });
  const baseBranch = options.baseBranchOverride || cfg.baseBranch ||
    await detectBaseBranch(options.repoPath);

  progress.report({ step: 'git', message: `Getting diff against ${baseBranch}...` });
  let diff = await getBranchDiff(options.repoPath, baseBranch);

  if (options.selectedFiles) {
    diff = filterDiffByFiles(diff, options.selectedFiles);
  }

  if (cancellation?.isCancelled()) throw new Error('Cancelled');

  if (diff.changedFiles.length === 0) {
    throw new Error(`No changes found between ${diff.currentBranch} and ${baseBranch}`);
  }

  progress.report({ step: 'scan', message: 'Scanning repository...' });
  const repoContext = await scanRepo(options.repoPath);

  progress.report({ step: 'llm', message: 'Connecting to LLM...' });
  const llmCredential = await auth.getCredential('llm', cfg.llm.provider);
  const llmProvider = createProvider(cfg.llm.provider, {
    apiKey: llmCredential?.value,
    model: cfg.llm.model,
    region: cfg.bedrock?.region,
    profile: cfg.bedrock?.profile,
  });

  progress.report({ step: 'generate', message: 'Generating documentation...' });
  const docs = await generateDocs(llmProvider, diff, repoContext, cfg.docLength, options.instructions);

  if (cancellation?.isCancelled()) throw new Error('Cancelled');

  if (options.dryRun) {
    return { docs, published: [] };
  }

  progress.report({ step: 'publish', message: 'Publishing...' });
  const targetIds = options.publishers || cfg.publishers || ['confluence'];
  const published: PublisherResultEntry[] = [];

  for (const publisherId of targetIds) {
    const entry = registry.get(publisherId);
    if (!entry) {
      progress.report({ step: 'publish', message: `Unknown publisher: ${publisherId}, skipping` });
      continue;
    }

    const { publisher, transformer } = entry;

    const credential = await auth.getCredential('publisher', publisherId);
    if (credential) {
      const pubConfig = cfg.publisherConfigs[publisherId] || {};
      publisher.initialize(credential, pubConfig);
    }

    const techContent = transformer.transform(docs.technical);
    const nonTechContent = transformer.transform(docs.nonTechnical);

    const branch = diff.currentBranch;
    const existing = await storage.getPages(branch, publisherId);

    let techResult: PublishResult;
    let nonTechResult: PublishResult;

    const techTitle = `${branch} — Technical`;
    const nonTechTitle = `${branch} — Summary`;

    if (existing) {
      const version = await publisher.getPageVersion?.(existing.technicalPageId);
      techResult = await publisher.updatePage(existing.technicalPageId, techTitle, techContent, version);
      nonTechResult = await publisher.updatePage(
        existing.nonTechnicalPageId, nonTechTitle, nonTechContent,
        await publisher.getPageVersion?.(existing.nonTechnicalPageId)
      );
    } else {
      techResult = await publisher.createPage(techTitle, techContent);
      nonTechResult = await publisher.createPage(nonTechTitle, nonTechContent);
      await publisher.afterPublish?.(techResult.pageId);
      await publisher.afterPublish?.(nonTechResult.pageId);
    }

    await storage.setPages(branch, publisherId, {
      technicalPageId: techResult.pageId,
      nonTechnicalPageId: nonTechResult.pageId,
      lastUpdated: new Date().toISOString(),
    });

    published.push({ publisherId, technical: techResult, nonTechnical: nonTechResult });
  }

  progress.report({ step: 'done', message: 'Complete', data: { published } });
  return { docs, published };
}
```

- [ ] **Step 2: Add pipeline exports to index.ts**

Add to `packages/core/src/index.ts`:

```typescript
// Pipeline
export { runPipeline } from './pipeline';
export type { PipelineAdapters, PipelineOptions, PipelineResult, PublisherResultEntry } from './pipeline';
```

- [ ] **Step 3: Build and verify**

```bash
npm run build:core
```

Expected: compiles without errors.

- [ ] **Step 4: Commit**

```bash
git add packages/core/src/pipeline.ts packages/core/src/index.ts
git commit -m "feat(core): add pipeline orchestrator — runPipeline() function"
```

---

### Task 6: Create VS Code Adapter Implementations

**Files:**
- Create: `packages/vscode-extension/src/adapters/vscodeAuth.ts`
- Create: `packages/vscode-extension/src/adapters/vscodeConfig.ts`
- Create: `packages/vscode-extension/src/adapters/vscodeStorage.ts`
- Create: `packages/vscode-extension/src/adapters/vscodeProgress.ts`

**Interfaces:**
- Consumes: `AuthProvider`, `Credential`, `CredentialScope` (Task 2), `ConfigProvider`, `RepoDocConfig` (Task 2), `StorageProvider`, `BranchPages` (Task 2), `ProgressReporter`, `ProgressStep` (Task 2), existing VS Code classes `SecretStore`, `SidebarProvider`
- Produces: `VsCodeAuthProvider`, `VsCodeConfigProvider`, `VsCodeStorageProvider`, `VsCodeProgressReporter`

- [ ] **Step 1: Create packages/vscode-extension/src/adapters/vscodeAuth.ts**

```typescript
import * as vscode from 'vscode';
import type { AuthProvider, Credential, CredentialScope } from '@repodoc/core';

const LLM_KEY_MAP: Record<string, string> = {
  anthropic: 'repoDoc.apiKey.anthropic',
  openai: 'repoDoc.apiKey.openai',
};

export class VsCodeAuthProvider implements AuthProvider {
  constructor(private secrets: vscode.SecretStorage) {}

  async getCredential(scope: CredentialScope, providerId: string): Promise<Credential | undefined> {
    if (scope === 'llm') {
      if (providerId === 'bedrock') {
        return { value: '' };
      }
      const key = LLM_KEY_MAP[providerId];
      if (!key) return undefined;
      const value = await this.secrets.get(key);
      return value ? { value } : undefined;
    }

    if (scope === 'publisher' && providerId === 'confluence') {
      const token = await this.secrets.get('repoDoc.confluence.token')
        || vscode.workspace.getConfiguration('repoDoc').get<string>('confluence.apiToken')
        || '';
      const email = await this.secrets.get('repoDoc.confluence.email')
        || vscode.workspace.getConfiguration('repoDoc').get<string>('confluence.email')
        || '';
      if (!token || !email) return undefined;
      return { value: token, metadata: { email } };
    }

    return undefined;
  }

  async setCredential(scope: CredentialScope, providerId: string, credential: Credential): Promise<void> {
    if (scope === 'llm') {
      const key = LLM_KEY_MAP[providerId];
      if (key) await this.secrets.store(key, credential.value);
    }
    if (scope === 'publisher' && providerId === 'confluence') {
      await this.secrets.store('repoDoc.confluence.token', credential.value);
      if (credential.metadata?.email) {
        await this.secrets.store('repoDoc.confluence.email', credential.metadata.email);
      }
    }
  }
}
```

- [ ] **Step 2: Create packages/vscode-extension/src/adapters/vscodeConfig.ts**

```typescript
import * as vscode from 'vscode';
import type { ConfigProvider, RepoDocConfig } from '@repodoc/core';

export class VsCodeConfigProvider implements ConfigProvider {
  async getConfig(): Promise<RepoDocConfig> {
    const cfg = vscode.workspace.getConfiguration('repoDoc');

    return {
      llm: {
        provider: cfg.get<'anthropic' | 'openai' | 'bedrock'>('llm.provider') || 'anthropic',
        model: cfg.get<string>('llm.model') || 'claude-sonnet-4-20250514',
      },
      baseBranch: cfg.get<string>('baseBranch') || 'main',
      docLength: cfg.get<'concise' | 'standard' | 'detailed'>('docLength') || 'concise',
      publishers: ['confluence'],
      publisherConfigs: {
        confluence: {
          baseUrl: cfg.get<string>('confluence.baseUrl') || '',
          spaceKey: cfg.get<string>('confluence.spaceKey') || '',
          parentPageId: cfg.get<string>('confluence.parentPageId') || '',
        },
      },
      bedrock: {
        region: cfg.get<string>('bedrock.region') || 'us-west-2',
        profile: cfg.get<string>('bedrock.profile') || '',
      },
    };
  }
}
```

- [ ] **Step 3: Create packages/vscode-extension/src/adapters/vscodeStorage.ts**

```typescript
import type * as vscode from 'vscode';
import type { StorageProvider, BranchPages } from '@repodoc/core';

const STORAGE_KEY = 'repoDoc.branchPages';

interface StorageFormat {
  [branch: string]: {
    [publisherId: string]: BranchPages;
  };
}

export class VsCodeStorageProvider implements StorageProvider {
  constructor(private state: vscode.Memento) {}

  async getPages(branch: string, publisherId: string): Promise<BranchPages | undefined> {
    const all = this.getAll();

    // Migration: old format had pages directly on the branch key
    const branchData = all[branch] as any;
    if (branchData?.technicalPageId && !branchData[publisherId]) {
      return publisherId === 'confluence' ? branchData as BranchPages : undefined;
    }

    return branchData?.[publisherId];
  }

  async setPages(branch: string, publisherId: string, pages: BranchPages): Promise<void> {
    const all = this.getAll();

    // Migrate old format if needed
    const branchData = all[branch] as any;
    if (branchData?.technicalPageId) {
      all[branch] = { confluence: branchData } as any;
    }

    if (!all[branch]) all[branch] = {};
    (all[branch] as Record<string, BranchPages>)[publisherId] = pages;
    this.state.update(STORAGE_KEY, all);
  }

  async removeBranch(branch: string): Promise<void> {
    const all = this.getAll();
    delete all[branch];
    this.state.update(STORAGE_KEY, all);
  }

  async getHistory(): Promise<Array<{ branch: string; publisherId: string; pages: BranchPages }>> {
    const all = this.getAll();
    const result: Array<{ branch: string; publisherId: string; pages: BranchPages }> = [];

    for (const [branch, publishers] of Object.entries(all)) {
      const pubData = publishers as any;
      if (pubData.technicalPageId) {
        result.push({ branch, publisherId: 'confluence', pages: pubData as BranchPages });
      } else {
        for (const [pubId, pages] of Object.entries(pubData)) {
          result.push({ branch, publisherId: pubId, pages: pages as BranchPages });
        }
      }
    }

    return result.sort((a, b) =>
      new Date(b.pages.lastUpdated).getTime() - new Date(a.pages.lastUpdated).getTime()
    );
  }

  private getAll(): StorageFormat {
    return this.state.get<StorageFormat>(STORAGE_KEY) || {};
  }
}
```

- [ ] **Step 4: Create packages/vscode-extension/src/adapters/vscodeProgress.ts**

```typescript
import type { ProgressReporter, ProgressStep } from '@repodoc/core';
import type { SidebarProvider } from '../webview/sidebarProvider';
import type * as vscode from 'vscode';

export class VsCodeProgressReporter implements ProgressReporter {
  constructor(
    private sidebar: SidebarProvider,
    private outputChannel: vscode.OutputChannel
  ) {}

  report(step: ProgressStep): void {
    this.sidebar.updateState({ step: step.message });
    this.outputChannel.appendLine(`[RepoDoc] ${step.step}: ${step.message}`);
  }
}
```

- [ ] **Step 5: Build and verify**

```bash
npm run build:vscode
```

Expected: compiles — all adapter classes correctly implement the core interfaces.

- [ ] **Step 6: Commit**

```bash
git add packages/vscode-extension/src/adapters/
git commit -m "feat(vscode): create adapter implementations for core interfaces

- VsCodeAuthProvider: wraps SecretStorage + workspace config
- VsCodeConfigProvider: wraps vscode.workspace.getConfiguration
- VsCodeStorageProvider: wraps vscode.Memento with old-format migration
- VsCodeProgressReporter: wraps sidebar + output channel"
```

---

### Task 7: Rewire extension.ts to Use Core Pipeline

**Files:**
- Modify: `packages/vscode-extension/src/extension.ts` — replace `handleRun` orchestration with `runPipeline()` call
- Modify: `packages/vscode-extension/src/webview/sidebarProvider.ts` — no changes needed (adapter wraps it)

**Interfaces:**
- Consumes: `runPipeline`, `PipelineAdapters`, `PipelineOptions`, `PublisherRegistry`, `ConfluencePublisher`, `MarkdownToHtmlTransformer` from core; `VsCodeAuthProvider`, `VsCodeConfigProvider`, `VsCodeStorageProvider`, `VsCodeProgressReporter` from Task 6
- Produces: Same user-facing behavior as before. Extension now delegates to core pipeline.

- [ ] **Step 1: Rewrite handleRun function**

Replace the body of `handleRun` in `packages/vscode-extension/src/extension.ts` (lines 144-419). The new version:

1. Creates adapters
2. Sets up publisher registry
3. Handles file selection UI (VS Code-specific — stays in extension)
4. Calls `runPipeline()`
5. Handles the result (updates sidebar, shows notifications)
6. Handles publish failure with local fallback (stays in extension)

```typescript
async function handleRun(context: vscode.ExtensionContext): Promise<void> {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (!workspaceFolder) {
    vscode.window.showErrorMessage('Open a folder first.');
    return;
  }

  const config = getConfig();
  const configured = await isConfigured(config, secretStore);
  if (!configured) {
    const action = await vscode.window.showWarningMessage(
      'Extension not configured. Run setup first.',
      'Setup Now'
    );
    if (action === 'Setup Now') {
      await runSetupWizard(secretStore, context.extensionUri);
    }
    return;
  }

  const repoPath = workspaceFolder.uri.fsPath;
  cancelTokenSource = new vscode.CancellationTokenSource();
  const token = cancelTokenSource.token;

  const startTime = Date.now();
  const elapsed = () => Math.round((Date.now() - startTime) / 1000);

  sidebar.updateState({ status: 'running', step: 'Starting...', elapsed: 0 });

  const elapsedTimer = setInterval(() => {
    if (sidebar) sidebar.updateState({ elapsed: elapsed() });
  }, 1000);

  try {
    // Pre-flight: file selection (VS Code-specific UI)
    let selectedFiles: string[] | undefined;
    if (config.promptForFileSelection) {
      const { getBranchDiff: getDiff, detectBaseBranch: detectBase } = await import('@repodoc/core');
      const baseBranch = sidebar.baseBranchOverride || config.baseBranch || await detectBase(repoPath);
      const diff = await getDiff(repoPath, baseBranch);
      if (diff.changedFiles.length > 1) {
        const items = diff.changedFiles.map(file => ({ label: file, picked: true }));
        const selected = await vscode.window.showQuickPick(items, {
          canPickMany: true,
          placeHolder: `Select files to include (${diff.changedFiles.length} changed)`,
          title: 'File Selection',
        });
        if (!selected) {
          sidebar.updateState({ status: 'idle' });
          return;
        }
        if (selected.length < diff.changedFiles.length) {
          selectedFiles = selected.map(s => s.label);
        }
      }
    }

    // Pre-flight: token health check
    const tokenStatus = await checkTokenHealth(config.llm.provider as 'anthropic' | 'openai' | 'bedrock', secretStore);
    if (!tokenStatus.valid) {
      outputChannel.appendLine(`[RepoDoc] Token issue: ${tokenStatus.message}`);
      const reauthed = await promptForReauth(config.llm.provider, tokenStatus.message, secretStore);
      if (!reauthed) {
        sidebar.updateState({ status: 'error', error: `${config.llm.provider}: ${tokenStatus.message}`, elapsed: elapsed() });
        return;
      }
    }

    // Create adapters
    const adapters: import('@repodoc/core').PipelineAdapters = {
      auth: new (await import('./adapters/vscodeAuth')).VsCodeAuthProvider(context.secrets),
      config: new (await import('./adapters/vscodeConfig')).VsCodeConfigProvider(),
      storage: new (await import('./adapters/vscodeStorage')).VsCodeStorageProvider(context.workspaceState),
      progress: new (await import('./adapters/vscodeProgress')).VsCodeProgressReporter(sidebar, outputChannel),
    };

    // Set up publisher registry
    const { PublisherRegistry, ConfluencePublisher, MarkdownToHtmlTransformer, runPipeline } = await import('@repodoc/core');
    const registry = new PublisherRegistry();
    registry.register(new ConfluencePublisher(), new MarkdownToHtmlTransformer());

    // Run the pipeline
    const result = await runPipeline(
      adapters,
      {
        repoPath,
        baseBranchOverride: sidebar.baseBranchOverride || undefined,
        selectedFiles,
        instructions: sidebar.customInstructions || undefined,
      },
      registry,
      { isCancelled: () => token.isCancellationRequested }
    );

    // Handle result
    const totalTime = elapsed();
    const techUrl = result.published[0]?.technical.url;
    const summaryUrl = result.published[0]?.nonTechnical.url;

    sidebar.updateState({
      status: 'done',
      step: 'Done!',
      elapsed: totalTime,
      techUrl,
      summaryUrl,
      branch: result.docs.branch,
    });

    const history = await adapters.storage.getHistory();
    sidebar.sendHistory(history.map(h => ({ branch: h.branch, lastUpdated: h.pages.lastUpdated })));

    outputChannel.appendLine(`[RepoDoc] Done in ${totalTime}s`);
    if (techUrl) outputChannel.appendLine(`[RepoDoc] Technical: ${techUrl}`);
    if (summaryUrl) outputChannel.appendLine(`[RepoDoc] Summary: ${summaryUrl}`);
    if (result.docs.usage) {
      outputChannel.appendLine(`[RepoDoc] Tokens: ${result.docs.usage.inputTokens} in + ${result.docs.usage.outputTokens} out`);
    }

    vscode.window.showInformationMessage(`Docs published for "${result.docs.branch}" in ${totalTime}s`);

  } catch (err: any) {
    const totalTime = elapsed();

    // Local fallback on publish failure
    if (err.message?.includes('Confluence API error')) {
      try {
        const safeBranch = (err.branch || 'unknown').replace(/\//g, '-');
        const repodocDir = vscode.Uri.joinPath(workspaceFolder.uri, '.repodoc');
        await vscode.workspace.fs.createDirectory(repodocDir);
        sidebar.updateState({
          status: 'error',
          error: `Publish failed — ${err.message}`,
          elapsed: totalTime,
        });
      } catch {}
    }

    sidebar.updateState({ status: 'error', error: err.message, elapsed: totalTime });
    outputChannel.appendLine(`[RepoDoc] ERROR (${totalTime}s): ${err.message}`);
    outputChannel.show();
  } finally {
    clearInterval(elapsedTimer);
    if (cancelTokenSource) {
      cancelTokenSource.dispose();
      cancelTokenSource = undefined;
    }
  }
}
```

- [ ] **Step 2: Update imports at top of extension.ts**

```typescript
// Before (remove these):
import { getBranchDiff, detectBaseBranch, filterDiffByFiles } from '@repodoc/core';
import { scanRepo, createProvider, generateDocs } from '@repodoc/core';
import { ConfluencePublisher } from '@repodoc/core';

// After (only keep what's still used at top level):
import type { PipelineAdapters } from '@repodoc/core';
```

Keep the existing VS Code imports: `SecretStore`, `getConfig`, `isConfigured`, `runSetupWizard`, `checkTokenHealth`, `promptForReauth`, `SidebarProvider`.

- [ ] **Step 3: Remove old DocTracker usage**

Remove from top of extension.ts:
```typescript
// Remove:
import { DocTracker } from './tracker/tracker';
// Remove:
let docTracker: DocTracker;
// Remove from activate():
docTracker = new DocTracker(context.workspaceState);
```

Update `handleViewDocs` to use the new storage adapter, and update `sidebar.onDidResolve` and `sidebar.onDeleteHistory` to use `VsCodeStorageProvider`.

- [ ] **Step 4: Build and verify**

```bash
npm run build:core
npm run build:vscode
```

Expected: compiles without errors. The extension's orchestration now routes through `runPipeline()`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rewire extension.ts to use core pipeline

handleRun now creates adapters and calls runPipeline() instead of
manually orchestrating each step. All VS Code-specific UI (file picker,
token health check, sidebar updates, local fallback) stays in extension."
```

---

### Task 8: Cleanup + Delete Dead Code

**Files:**
- Delete: `packages/vscode-extension/src/tracker/tracker.ts` (replaced by StorageProvider)
- Delete: `packages/vscode-extension/src/config/secrets.ts` (replaced by VsCodeAuthProvider — but keep if wizard/tokenCheck still imports it)
- Modify: `packages/vscode-extension/src/config/settings.ts` — remove `isConfigured` if moved, or keep as thin wrapper
- Modify: `packages/core/src/index.ts` — final cleanup of exports
- Modify: `packages/vscode-extension/package.json` — verify `bundledDependencies` includes `@repodoc/core`

**Interfaces:**
- Consumes: everything from Tasks 1-7
- Produces: clean, minimal vscode-extension with no dead code

- [ ] **Step 1: Audit remaining imports in vscode-extension**

```bash
cd /Users/vgupta/Downloads/extension/repo-doc-mcp
grep -r "from '\./git/" packages/vscode-extension/src/ || echo "clean"
grep -r "from '\./scanner/" packages/vscode-extension/src/ || echo "clean"
grep -r "from '\./llm/" packages/vscode-extension/src/ || echo "clean"
grep -r "from '\./generator/" packages/vscode-extension/src/ || echo "clean"
grep -r "from '\./publisher/" packages/vscode-extension/src/ || echo "clean"
grep -r "from '\./tracker/" packages/vscode-extension/src/ || echo "clean"
```

Any remaining references to old local paths must be updated to `@repodoc/core` imports or to the new adapters.

- [ ] **Step 2: Check if SecretStore and settings.ts are still needed**

`wizard.ts` and `tokenCheck.ts` still import `SecretStore`. These stay in the vscode-extension package (they're VS Code-specific). Keep `secrets.ts` and `settings.ts` for now — they're used by the wizard and credential validation UI.

The `isConfigured` function in `settings.ts` uses `SecretStore` and `vscode.workspace` — keep it in the VS Code package.

- [ ] **Step 3: Delete tracker/tracker.ts if no longer imported**

```bash
grep -r "tracker" packages/vscode-extension/src/ --include="*.ts"
```

If only `extension.ts` imported it and we've removed that import in Task 7, delete it:

```bash
git rm packages/vscode-extension/src/tracker/tracker.ts
rmdir packages/vscode-extension/src/tracker 2>/dev/null || true
```

- [ ] **Step 4: Add bundledDependencies for VSIX packaging**

In `packages/vscode-extension/package.json`, add:

```jsonc
"bundledDependencies": ["@repodoc/core"]
```

This ensures `vsce package` includes core in the VSIX.

- [ ] **Step 5: Final build + test VSIX packaging**

```bash
npm run build
cd packages/vscode-extension
npx vsce package --no-dependencies 2>&1 | tail -5
```

Expected: VSIX packages successfully.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: cleanup dead code and configure VSIX bundling

Removed old tracker module (replaced by StorageProvider adapter).
Added bundledDependencies for @repodoc/core in VSIX packaging."
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] `npm run build` from repo root compiles both packages
- [ ] `packages/core/dist/` contains `.js` and `.d.ts` files for all modules
- [ ] `grep -r "vscode" packages/core/src/` returns zero hits (no VS Code coupling)
- [ ] `cd packages/vscode-extension && npx vsce package` succeeds
- [ ] Install the VSIX in VS Code and test: generate docs on a feature branch → publishes to Confluence correctly
