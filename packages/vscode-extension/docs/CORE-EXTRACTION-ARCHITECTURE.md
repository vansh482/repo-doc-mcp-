# @repodoc/core — Architecture Design Document

> Full HLD + LLD for extracting a shared core package from the VS Code extension monolith.
> This enables: VS Code extension, IntelliJ plugin, CLI tool, and MCP server — all consuming the same engine.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Goals & Non-Goals](#goals--non-goals)
3. [High-Level Design (HLD)](#high-level-design-hld)
4. [Monorepo Structure](#monorepo-structure)
5. [Low-Level Design (LLD)](#low-level-design-lld)
   - [Core Package Modules](#core-package-modules)
   - [Auth Abstraction Layer](#auth-abstraction-layer)
   - [Publisher Interface & Registry](#publisher-interface--registry)
   - [Content Transformer Pipeline](#content-transformer-pipeline)
   - [Configuration Contract](#configuration-contract)
   - [Progress & Event System](#progress--event-system)
   - [Storage Abstraction (Tracker)](#storage-abstraction-tracker)
6. [Dependency Injection Pattern](#dependency-injection-pattern)
7. [Consumer Integration Patterns](#consumer-integration-patterns)
   - [VS Code Extension](#vs-code-extension)
   - [CLI Tool](#cli-tool)
   - [MCP Server](#mcp-server)
   - [IntelliJ Plugin](#intellij-plugin)
8. [Migration Strategy](#migration-strategy)
9. [Testing Strategy](#testing-strategy)
10. [Build & Publish](#build--publish)
11. [Appendix: Interface Contracts (Full TypeScript)](#appendix-interface-contracts)

---

## Problem Statement

The current VS Code extension is a monolith where:

- **Auth** is coupled to VS Code's `SecretStorage` API
- **Config** reads from `vscode.workspace.getConfiguration()`
- **Tracker** depends on `vscode.Memento` (workspace state)
- **Publisher** is a single hardcoded `ConfluencePublisher` wired directly in `extension.ts`
- **Progress reporting** uses VS Code's `window.withProgress` and custom webview messages

This makes it impossible to reuse the core pipeline (git diff → scan → LLM → format → publish) in any other context — CLI, MCP server, or IntelliJ — without rewriting everything.

### Current Coupling Map

```
extension.ts (orchestrator)
├── config/secrets.ts      → vscode.SecretStorage
├── config/settings.ts     → vscode.workspace.getConfiguration()
├── config/tokenCheck.ts   → vscode.window (UI prompts)
├── config/wizard.ts       → vscode.Webview
├── tracker/tracker.ts     → vscode.Memento
├── webview/sidebarProvider.ts → vscode.WebviewViewProvider
├── git/diff.ts            → ✅ framework-independent (child_process)
├── scanner/scanner.ts     → ✅ framework-independent (fs/path)
├── llm/provider.ts        → ✅ framework-independent
├── generator/generator.ts → ✅ framework-independent
└── publisher/confluence.ts→ ✅ framework-independent (fetch)
```

**Key insight:** 5 of 10 modules are already VS Code-free. The extraction is about creating proper boundaries around the 5 coupled modules and defining contracts they implement.

---

## Goals & Non-Goals

### Goals

1. Extract a `@repodoc/core` package with zero VS Code (or any IDE) imports
2. Define clean interfaces that any consumer can implement (auth, config, storage, progress)
3. Preserve all existing functionality — this is a refactor, not a rewrite
4. Enable multi-publisher support via the `DocPublisher` interface + registry
5. Enable content format transformation via a pipeline
6. Make adding a new consumer (CLI, MCP, IntelliJ) a matter of implementing 3-4 thin adapter interfaces
7. Keep the IntelliJ integration path open (Node sidecar OR Kotlin rewrite — clean contracts support both)

### Non-Goals

- Implementing the CLI, MCP server, or IntelliJ plugin (those come after)
- Adding new publishers (Notion, Slack, etc.) during extraction
- OAuth 2.0 flows (future work — but auth interface must support it)
- Breaking changes to the VS Code UX (sidebar, wizard, etc.)
- Publishing `@repodoc/core` to npm (monorepo workspace linking for now)

---

## High-Level Design (HLD)

### Architecture Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CONSUMERS (Entry Points)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────────┐   │
│  │ VS Code  │  │   CLI    │  │   MCP    │  │ IntelliJ (future)  │   │
│  │Extension │  │   Tool   │  │  Server  │  │  Node sidecar OR   │   │
│  │          │  │          │  │          │  │  Kotlin via JSON   │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬───────────┘   │
│       │             │             │                 │               │
├───────┼─────────────┼─────────────┼─────────────────┼─────────---───┤
│       │             │             │                 │               │
│       ▼             ▼             ▼                 ▼               │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     @repodoc/core                            │   │
│  │                                                              │   │
│  │  ┌─────────────────────────────────────────────────────────┐ │   │
│  │  │              Pipeline Orchestrator                      │ │   │
│  │  │  (receives adapters via DI, runs the full pipeline)     │ │   │
│  │  └───────┬──────────┬──────────┬──────────┬────────────────┘ │   │
│  │          │          │          │          │                  │   │
│  │  ┌───────▼──┐ ┌─────▼────┐ ┌─-─▼─────┐ ┌--▼────────────┐     │   │
│  │  │   Git    │ │ Scanner  │ │   LLM   │ │  Generator    │     │   │
│  │  │  Module  │ │  Module  │ │ Module  │ │   Module      │     │   │
│  │  └──────────┘ └──────────┘ └─────────┘ └───────────────┘     │   │
│  │                                                              │   │
│  │  ┌───────────────────────────────────────────────────────┐   │   │
│  │  │           Publisher Subsystem                         │   │   │
│  │  │  ┌──────────┐  ┌────────────────┐  ┌──────────────┐   │   │   │
│  │  │  │Publisher │  │  Content       │  │  Publisher   │   │   │   │
│  │  │  │Interface │  │  Transformer   │  │  Registry    │   │   │   │
│  │  │  └──────────┘  └────────────────┘  └──────────────┘   │   │   │
│  │  └───────────────────────────────────────────────────────┘   │   │
│  │                                                              │   │
│  │  ┌───────────────────────────────────────────────────────┐   │   │
│  │  │           Adapter Interfaces (contracts)              │   │   │
│  │  │  ┌─────────┐ ┌────────┐ ┌──────────┐ ┌────────────┐   │   │   │
│  │  │  │  Auth   │ │ Config │ │ Storage  │ │  Progress  │   │   │   │
│  │  │  │Provider │ │Provider│ │ Provider │ │  Reporter  │   │   │   │
│  │  │  └─────────┘ └────────┘ └──────────┘ └────────────┘   │   │   │
│  │  └───────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
User triggers "Generate" (via VS Code command / CLI flag / MCP tool call)
    │
    ▼
Consumer creates adapters (auth, config, storage, progress)
    │
    ▼
Consumer calls core.pipeline.run({ adapters, options })
    │
    ├─── 1. progress.report('Resolving configuration...')
    ├─── 2. config.getConfig() → RepoDocConfig
    ├─── 3. git.detectBaseBranch(repoPath) OR use config.baseBranch
    ├─── 4. git.getBranchDiff(repoPath, baseBranch)
    ├─── 5. scanner.scanRepo(repoPath)
    ├─── 6. auth.getCredential('llm', provider) → apiKey
    ├─── 7. llm.createProvider(type, { apiKey, model })
    ├─── 8. generator.generateDocs(provider, diff, context, docLength, instructions)
    ├─── 9. For each publisher target:
    │    ├── auth.getCredential('publisher', publisherId)
    │    ├── contentTransformer.transform(markdown, targetFormat)
    │    └── publisher.publish(title, transformedContent)
    ├─── 10. storage.trackPages(branch, publisherResults)
    └─── 11. progress.report('Done', { results })
```

### Design Principles

1. **Inversion of Control** — Core never imports platform code. Consumers inject adapters.
2. **Interface segregation** — Small, focused interfaces. A CLI doesn't need progress UI.
3. **Registry pattern** (inspired by integration-auth-service) — Publishers and auth providers are registered, not hardcoded.
4. **Strategy pattern** — Different auth mechanisms (token paste, OAuth, AWS profile) are interchangeable strategies behind the same `AuthProvider` interface.
5. **Pipeline as value** — The pipeline is a pure function of (config + adapters) → results. No global state.

---

## Monorepo Structure

```
repo-doc-mcp/
├── package.json                  ← workspace root (pnpm workspaces)
├── pnpm-workspace.yaml
├── tsconfig.base.json            ← shared TypeScript config
│
├── packages/
│   ├── core/                     ← @repodoc/core
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── src/
│   │       ├── index.ts          ← public API barrel
│   │       ├── pipeline.ts       ← orchestrator
│   │       ├── git/
│   │       │   └── diff.ts       ← moved from vscode-extension (unchanged)
│   │       ├── scanner/
│   │       │   └── scanner.ts    ← moved (unchanged)
│   │       ├── llm/
│   │       │   ├── provider.ts   ← moved (unchanged)
│   │       │   ├── anthropic.ts
│   │       │   ├── openai.ts
│   │       │   └── bedrock.ts
│   │       ├── generator/
│   │       │   ├── generator.ts  ← moved (unchanged)
│   │       │   └── prompts.ts
│   │       ├── publisher/
│   │       │   ├── types.ts      ← DocPublisher interface
│   │       │   ├── registry.ts   ← PublisherRegistry
│   │       │   ├── confluence.ts ← moved (unchanged logic)
│   │       │   └── markdown.ts   ← new: file-based publisher (trivial)
│   │       ├── transformer/
│   │       │   ├── types.ts      ← ContentTransformer interface
│   │       │   ├── pipeline.ts   ← runs transformer chain
│   │       │   ├── html.ts       ← markdown→Confluence HTML (from current confluence.ts)
│   │       │   └── identity.ts   ← pass-through for markdown targets
│   │       ├── auth/
│   │       │   └── types.ts      ← AuthProvider interface
│   │       ├── config/
│   │       │   └── types.ts      ← ConfigProvider interface + RepoDocConfig
│   │       ├── storage/
│   │       │   └── types.ts      ← StorageProvider interface
│   │       └── progress/
│   │           └── types.ts      ← ProgressReporter interface
│   │
│   └── vscode-extension/         ← @repodoc/vscode (existing, refactored)
│       ├── package.json          ← depends on @repodoc/core
│       ├── tsconfig.json
│       └── src/
│           ├── extension.ts      ← thin orchestrator, creates adapters, calls core
│           ├── adapters/
│           │   ├── vscodeAuth.ts       ← implements AuthProvider via SecretStorage
│           │   ├── vscodeConfig.ts     ← implements ConfigProvider via workspace config
│           │   ├── vscodeStorage.ts    ← implements StorageProvider via Memento
│           │   └── vscodeProgress.ts   ← implements ProgressReporter via sidebar messages
│           ├── config/
│           │   ├── wizard.ts           ← VS Code-specific webview (unchanged)
│           │   ├── wizardHtml.ts
│           │   ├── tokenCheck.ts       ← uses AuthProvider adapter internally
│           │   └── validator.ts        ← uses AuthProvider adapter internally
│           └── webview/
│               └── sidebarProvider.ts  ← unchanged UI layer
│
├── packages/cli/                 ← @repodoc/cli (future)
│   └── ...
│
├── packages/mcp-server/          ← @repodoc/mcp (future)
│   └── ...
│
└── docs/
    ├── CORE-EXTRACTION-ARCHITECTURE.md  ← this file
    └── PUBLISHER-ARCHITECTURE.md        ← existing (will be superseded)
```

### Workspace Configuration

```yaml
# pnpm-workspace.yaml
packages:
  - 'packages/*'
```

```jsonc
// root package.json
{
  "name": "repodoc",
  "private": true,
  "scripts": {
    "build": "pnpm -r build",
    "build:core": "pnpm --filter @repodoc/core build",
    "build:vscode": "pnpm --filter @repodoc/vscode build",
    "test": "pnpm -r test",
    "lint": "pnpm -r lint"
  },
  "devDependencies": {
    "typescript": "^5.4.0",
    "pnpm": "^9.0.0"
  }
}
```

---

## Low-Level Design (LLD)

### Core Package Modules

#### `packages/core/src/index.ts` — Public API Surface

```typescript
// Re-export everything consumers need
export { runPipeline, type PipelineOptions, type PipelineResult } from './pipeline';

// Domain types
export type { BranchDiff } from './git/diff';
export type { RepoContext } from './scanner/scanner';
export type { LLMProvider, LLMResponse, TokenUsage, ProviderType, ProviderConfig } from './llm/provider';
export type { GeneratedDocs } from './generator/generator';
export type { DocLength } from './config/types';

// Publisher system
export type { DocPublisher, PublishResult, PublisherConfig } from './publisher/types';
export { PublisherRegistry } from './publisher/registry';
export { ConfluencePublisher } from './publisher/confluence';

// Transformer system
export type { ContentTransformer, ContentFormat } from './transformer/types';
export { TransformerPipeline } from './transformer/pipeline';
export { MarkdownToHtmlTransformer } from './transformer/html';
export { IdentityTransformer } from './transformer/identity';

// Adapter interfaces (consumers implement these)
export type { AuthProvider, Credential, CredentialType } from './auth/types';
export type { ConfigProvider, RepoDocConfig } from './config/types';
export type { StorageProvider, BranchPages, TrackedPage } from './storage/types';
export type { ProgressReporter, ProgressStep } from './progress/types';

// Utilities
export { getBranchDiff, detectBaseBranch, filterDiffByFiles } from './git/diff';
export { scanRepo } from './scanner/scanner';
export { createProvider } from './llm/provider';
export { generateDocs } from './generator/generator';
```

#### `packages/core/src/pipeline.ts` — Orchestrator

```typescript
import { getBranchDiff, detectBaseBranch, filterDiffByFiles } from './git/diff';
import { scanRepo } from './scanner/scanner';
import { createProvider } from './llm/provider';
import { generateDocs, GeneratedDocs } from './generator/generator';
import type { AuthProvider } from './auth/types';
import type { ConfigProvider, RepoDocConfig } from './config/types';
import type { StorageProvider } from './storage/types';
import type { ProgressReporter } from './progress/types';
import type { DocPublisher, PublishResult } from './publisher/types';
import type { ContentTransformer } from './transformer/types';

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
  publishers?: string[];           // publisher IDs to target (defaults to config)
  dryRun?: boolean;                // generate but don't publish
}

export interface PublisherResult {
  publisherId: string;
  technical: PublishResult;
  nonTechnical: PublishResult;
}

export interface PipelineResult {
  docs: GeneratedDocs;
  published: PublisherResult[];
  localFallback?: string;          // path if publish failed and saved locally
}

export async function runPipeline(
  adapters: PipelineAdapters,
  options: PipelineOptions,
  publisherRegistry: Map<string, { publisher: DocPublisher; transformer: ContentTransformer }>,
  cancellation?: { isCancelled: () => boolean }
): Promise<PipelineResult> {

  const { auth, config, storage, progress } = adapters;

  // Step 1: Load config
  progress.report({ step: 'config', message: 'Loading configuration...' });
  const cfg = await config.getConfig();

  // Step 2: Resolve base branch
  progress.report({ step: 'git', message: 'Detecting base branch...' });
  const baseBranch = options.baseBranchOverride || cfg.baseBranch ||
    await detectBaseBranch(options.repoPath);

  // Step 3: Get diff
  progress.report({ step: 'git', message: `Getting diff against ${baseBranch}...` });
  let diff = await getBranchDiff(options.repoPath, baseBranch);

  if (options.selectedFiles) {
    diff = filterDiffByFiles(diff, options.selectedFiles);
  }

  if (cancellation?.isCancelled()) throw new Error('Cancelled');

  if (diff.changedFiles.length === 0) {
    throw new Error(`No changes found between ${diff.currentBranch} and ${baseBranch}`);
  }

  // Step 4: Scan repo
  progress.report({ step: 'scan', message: 'Scanning repository...' });
  const repoContext = await scanRepo(options.repoPath);

  // Step 5: Get LLM credentials and create provider
  progress.report({ step: 'llm', message: 'Connecting to LLM...' });
  const llmCredential = await auth.getCredential('llm', cfg.llm.provider);
  const llmProvider = createProvider(cfg.llm.provider, {
    apiKey: llmCredential?.value,
    model: cfg.llm.model,
    region: cfg.bedrock?.region,
    profile: cfg.bedrock?.profile,
  });

  // Step 6: Generate docs
  progress.report({ step: 'generate', message: 'Generating documentation...' });
  const docs = await generateDocs(llmProvider, diff, repoContext, cfg.docLength, options.instructions);

  if (cancellation?.isCancelled()) throw new Error('Cancelled');

  if (options.dryRun) {
    return { docs, published: [] };
  }

  // Step 7: Publish to all targets
  progress.report({ step: 'publish', message: 'Publishing...' });
  const targetIds = options.publishers || cfg.publishers || ['confluence'];
  const published: PublisherResult[] = [];

  for (const publisherId of targetIds) {
    const entry = publisherRegistry.get(publisherId);
    if (!entry) {
      progress.report({ step: 'publish', message: `Unknown publisher: ${publisherId}, skipping` });
      continue;
    }

    const { publisher, transformer } = entry;
    const credential = await auth.getCredential('publisher', publisherId);

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
      const nonTechVersion = await publisher.getPageVersion?.(existing.nonTechnicalPageId);
      nonTechResult = await publisher.updatePage(existing.nonTechnicalPageId, nonTechTitle, nonTechContent, nonTechVersion);
    } else {
      techResult = await publisher.createPage(techTitle, techContent);
      nonTechResult = await publisher.createPage(nonTechTitle, nonTechContent);
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

---

### Auth Abstraction Layer

Inspired by integration-auth-service's `CredentialResolver` + `ValueResolver` strategy pattern — but adapted for our client-side context (no database, no Spring DI).

#### `packages/core/src/auth/types.ts`

```typescript
/**
 * Credential types the system needs.
 * 'llm' = API keys for LLM providers
 * 'publisher' = tokens/credentials for doc publishers
 */
export type CredentialScope = 'llm' | 'publisher';

export interface Credential {
  value: string;
  expiresAt?: Date;
  metadata?: Record<string, string>;  // e.g. { email: '...' } for Confluence basic auth
}

/**
 * AuthProvider — the contract consumers implement.
 *
 * VS Code adapter: reads from SecretStorage
 * CLI adapter: reads from env vars or ~/.repodocrc
 * IntelliJ adapter: reads from IDE credential store or calls Node sidecar
 *
 * Inspired by integration-auth-service's ValueResolver pattern:
 * each consumer resolves credentials from its own "source" (ENV, IDE, USER-INPUT).
 */
export interface AuthProvider {
  /**
   * Get a credential for a given scope and provider.
   * @param scope - 'llm' or 'publisher'
   * @param providerId - e.g. 'anthropic', 'openai', 'confluence', 'notion'
   * @returns The credential, or undefined if not configured
   */
  getCredential(scope: CredentialScope, providerId: string): Promise<Credential | undefined>;

  /**
   * Store a credential (used by setup wizards).
   * Optional — CLI may not support interactive storage.
   */
  setCredential?(scope: CredentialScope, providerId: string, credential: Credential): Promise<void>;

  /**
   * Validate that a credential is still usable (not expired, API responds).
   * Optional — not all consumers need health checks.
   */
  validateCredential?(scope: CredentialScope, providerId: string): Promise<boolean>;

  /**
   * Refresh an expired credential.
   * Required for OAuth flows (future).
   */
  refreshCredential?(scope: CredentialScope, providerId: string): Promise<Credential | undefined>;
}
```

#### How Each Consumer Implements AuthProvider

| Consumer | `getCredential('llm', 'anthropic')` | `getCredential('publisher', 'confluence')` |
|----------|-------|------|
| **VS Code** | `secretStorage.get('repoDoc.apiKey.anthropic')` → `{ value: apiKey }` | `secretStorage.get('repoDoc.confluence.token')` + `get('...email')` → `{ value: token, metadata: { email } }` |
| **CLI** | `process.env.ANTHROPIC_API_KEY` or read `~/.repodocrc` | `process.env.CONFLUENCE_TOKEN` + `CONFLUENCE_EMAIL` |
| **MCP Server** | Same as CLI (env vars) | Same as CLI |
| **IntelliJ** | Call Node sidecar with `--get-credential llm anthropic` (JSON response) | Same pattern |

---

### Publisher Interface & Registry

#### `packages/core/src/publisher/types.ts`

```typescript
export interface PublishResult {
  pageId: string;
  url: string;
  version?: number;
}

export interface PublisherConfig {
  [key: string]: unknown;  // publisher-specific config (baseUrl, spaceKey, etc.)
}

/**
 * DocPublisher — the universal interface for any documentation target.
 *
 * Inspired by integration-auth-service's IntegrationAuthConnector interface:
 * each publisher is a self-contained unit with a unique ID that's registered
 * at startup and looked up by ID when needed.
 */
export interface DocPublisher {
  readonly id: string;
  readonly displayName: string;

  /**
   * Initialize the publisher with credentials and config.
   * Called once before any publish operation.
   */
  initialize(credential: { value: string; metadata?: Record<string, string> }, config: PublisherConfig): void;

  createPage(title: string, content: string): Promise<PublishResult>;
  updatePage(pageId: string, title: string, content: string, currentVersion?: number): Promise<PublishResult>;
  getPageVersion?(pageId: string): Promise<number>;
  pageExists?(pageId: string): Promise<boolean>;

  /**
   * Publisher-specific post-publish actions (e.g. restrict page access).
   * Optional.
   */
  afterPublish?(pageId: string): Promise<void>;
}
```

#### `packages/core/src/publisher/registry.ts`

```typescript
import type { DocPublisher } from './types';
import type { ContentTransformer } from '../transformer/types';

interface RegisteredPublisher {
  publisher: DocPublisher;
  transformer: ContentTransformer;
}

/**
 * PublisherRegistry — manages available publishers.
 *
 * Mirrors integration-auth-service's IntegrationAuthConnectorRegistry:
 * - Publishers register at startup
 * - Looked up by ID when needed
 * - Generic: doesn't know about specific publisher implementations
 */
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

---

### Content Transformer Pipeline

#### `packages/core/src/transformer/types.ts`

```typescript
export type ContentFormat = 'html' | 'confluence-storage' | 'notion-blocks' | 'google-ops' | 'markdown';

export interface ContentTransformer {
  readonly inputFormat: 'markdown';
  readonly outputFormat: ContentFormat;

  /**
   * Transform markdown to the target format.
   * Returns string for text-based formats, object for structured formats.
   */
  transform(markdown: string): string;
}
```

#### `packages/core/src/transformer/html.ts`

The existing `markdownToConfluenceStorage()` function from `publisher/confluence.ts` gets extracted here:

```typescript
import type { ContentTransformer } from './types';

export class MarkdownToHtmlTransformer implements ContentTransformer {
  readonly inputFormat = 'markdown' as const;
  readonly outputFormat = 'confluence-storage' as const;

  transform(markdown: string): string {
    return markdownToConfluenceStorage(markdown);
  }
}

// Existing function, moved from publisher/confluence.ts — no logic changes
function markdownToConfluenceStorage(markdown: string): string {
  // ... exact same implementation as current confluence.ts lines 135-270
}
```

#### `packages/core/src/transformer/identity.ts`

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

---

### Configuration Contract

#### `packages/core/src/config/types.ts`

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
  publishers: string[];          // ['confluence'] — which publishers to target

  // Publisher-specific configs (keyed by publisher ID)
  publisherConfigs: Record<string, Record<string, unknown>>;
  // e.g. { confluence: { baseUrl, spaceKey, parentPageId }, notion: { databaseId } }

  // Provider-specific
  bedrock?: {
    region: string;
    profile: string;
  };
}

/**
 * ConfigProvider — reads configuration from wherever the consumer stores it.
 *
 * VS Code: vscode.workspace.getConfiguration('repoDoc')
 * CLI: env vars + ~/.repodocrc file + CLI flags (merged with precedence)
 * MCP: env vars or passed as tool parameters
 */
export interface ConfigProvider {
  getConfig(): Promise<RepoDocConfig>;
}
```

---

### Progress & Event System

#### `packages/core/src/progress/types.ts`

```typescript
export interface ProgressStep {
  step: 'config' | 'git' | 'scan' | 'llm' | 'generate' | 'publish' | 'done' | 'error';
  message: string;
  data?: Record<string, unknown>;
  percentage?: number;
}

/**
 * ProgressReporter — receives pipeline progress updates.
 *
 * VS Code: sends messages to sidebar webview
 * CLI: prints to stdout/stderr with spinners
 * MCP: may buffer and return as part of tool response
 * IntelliJ: sends to IDE's progress indicator
 */
export interface ProgressReporter {
  report(step: ProgressStep): void;
}

/**
 * Null reporter for contexts that don't need progress (tests, batch mode).
 */
export const nullProgress: ProgressReporter = {
  report() {},
};
```

---

### Storage Abstraction (Tracker)

#### `packages/core/src/storage/types.ts`

```typescript
export interface BranchPages {
  technicalPageId: string;
  nonTechnicalPageId: string;
  lastUpdated: string;
}

/**
 * StorageProvider — persists branch→page mappings.
 *
 * VS Code: uses vscode.Memento (workspaceState)
 * CLI: uses a JSON file in .repodoc/tracker.json
 * MCP: same as CLI
 *
 * Multi-publisher support: keyed by (branch, publisherId)
 */
export interface StorageProvider {
  getPages(branch: string, publisherId: string): Promise<BranchPages | undefined>;
  setPages(branch: string, publisherId: string, pages: BranchPages): Promise<void>;
  removeBranch(branch: string): Promise<void>;
  getHistory(): Promise<Array<{ branch: string; publisherId: string; pages: BranchPages }>>;
}
```

---

## Dependency Injection Pattern

We use **constructor injection via a context object** — not a DI framework. The core defines what it needs; consumers build the context and pass it in.

```typescript
// Consumer (e.g. VS Code extension.ts) builds the context:
import { runPipeline, PublisherRegistry, ConfluencePublisher, MarkdownToHtmlTransformer } from '@repodoc/core';
import { VsCodeAuthProvider } from './adapters/vscodeAuth';
import { VsCodeConfigProvider } from './adapters/vscodeConfig';
import { VsCodeStorageProvider } from './adapters/vscodeStorage';
import { VsCodeProgressReporter } from './adapters/vscodeProgress';

// 1. Create adapters
const adapters = {
  auth: new VsCodeAuthProvider(context.secrets),
  config: new VsCodeConfigProvider(),
  storage: new VsCodeStorageProvider(context.workspaceState),
  progress: new VsCodeProgressReporter(sidebar),
};

// 2. Set up publisher registry
const registry = new PublisherRegistry();
registry.register(new ConfluencePublisher(), new MarkdownToHtmlTransformer());
// Future: registry.register(new NotionPublisher(), new MarkdownToNotionTransformer());

// 3. Run the pipeline
const result = await runPipeline(adapters, { repoPath, instructions }, registry);
```

### Why Not a DI Framework?

- The project is small — 4 interfaces is not enough to justify a container
- Explicit wiring is easier to follow and debug
- Zero runtime dependency
- TypeScript's type system enforces the contract at compile time
- Each consumer's adapter creation is ~20 lines — a framework would add more code than it saves

---

## Consumer Integration Patterns

### VS Code Extension

The existing extension becomes a **thin shell** that:
1. Creates VS Code-specific adapters
2. Calls `runPipeline()` from core
3. Handles VS Code-specific UI (sidebar, wizard, commands)

```typescript
// packages/vscode-extension/src/adapters/vscodeAuth.ts
import type { AuthProvider, Credential, CredentialScope } from '@repodoc/core';
import * as vscode from 'vscode';

export class VsCodeAuthProvider implements AuthProvider {
  constructor(private secrets: vscode.SecretStorage) {}

  async getCredential(scope: CredentialScope, providerId: string): Promise<Credential | undefined> {
    if (scope === 'llm') {
      const key = `repoDoc.apiKey.${providerId}`;
      const value = await this.secrets.get(key);
      return value ? { value } : undefined;
    }

    if (scope === 'publisher' && providerId === 'confluence') {
      const token = await this.secrets.get('repoDoc.confluence.token');
      const email = await this.secrets.get('repoDoc.confluence.email');
      if (!token || !email) return undefined;
      return { value: token, metadata: { email } };
    }

    return undefined;
  }

  async setCredential(scope: CredentialScope, providerId: string, credential: Credential): Promise<void> {
    if (scope === 'llm') {
      await this.secrets.store(`repoDoc.apiKey.${providerId}`, credential.value);
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

### CLI Tool

```typescript
// packages/cli/src/main.ts (future — illustrative)
import { runPipeline, PublisherRegistry, ConfluencePublisher, MarkdownToHtmlTransformer } from '@repodoc/core';
import { EnvAuthProvider } from './adapters/envAuth';
import { FileConfigProvider } from './adapters/fileConfig';
import { JsonStorageProvider } from './adapters/jsonStorage';
import { ConsoleProgressReporter } from './adapters/consoleProgress';

const adapters = {
  auth: new EnvAuthProvider(),                   // reads ANTHROPIC_API_KEY, CONFLUENCE_TOKEN, etc.
  config: new FileConfigProvider(cliFlags),     // merges .repodocrc + CLI flags
  storage: new JsonStorageProvider('.repodoc/tracker.json'),
  progress: new ConsoleProgressReporter(),      // ora spinners
};

const registry = new PublisherRegistry();
registry.register(new ConfluencePublisher(), new MarkdownToHtmlTransformer());

const result = await runPipeline(adapters, { repoPath: process.cwd() }, registry);
```

### MCP Server

```typescript
// packages/mcp-server/src/tools/generateDocs.ts (future — illustrative)
import { runPipeline, PublisherRegistry, ... } from '@repodoc/core';

server.tool('generate_branch_docs', schema, async (params) => {
  const adapters = {
    auth: new EnvAuthProvider(),
    config: new ParamConfigProvider(params),  // config from tool params + env
    storage: new JsonStorageProvider('.repodoc/tracker.json'),
    progress: nullProgress,                   // MCP doesn't stream progress
  };

  const result = await runPipeline(adapters, { repoPath: params.repoPath }, registry);
  return { content: [{ type: 'text', text: JSON.stringify(result.published) }] };
});
```

### IntelliJ Plugin

Two paths remain open:

**Option A: Node Sidecar**
```
IntelliJ Plugin (Kotlin)
  └── spawns: node packages/cli/dist/main.js --json --repo-path /path
      └── returns JSON result
```

**Option B: Kotlin Rewrite**
```
IntelliJ Plugin (Kotlin)
  └── implements same interfaces (AuthProvider, ConfigProvider, etc.) in Kotlin
  └── reimplements git/scanner/llm/generator/publisher (reading from same JSON contracts)
```

The interface contracts serve as the spec regardless of implementation language.

---

## Migration Strategy

### Phase 1: Create Monorepo Structure (no logic changes)

1. Create `pnpm-workspace.yaml` and root `package.json`
2. Move `vscode-extension/` into `packages/vscode-extension/`
3. Create empty `packages/core/` with `package.json` and `tsconfig.json`
4. Verify VS Code extension still builds and works identically

### Phase 2: Extract Framework-Independent Modules (copy, don't move yet)

1. Copy `git/diff.ts`, `scanner/scanner.ts`, `llm/*.ts`, `generator/*.ts` into `packages/core/src/`
2. These files have ZERO VS Code imports — they move unchanged
3. Update `packages/core/tsconfig.json` to compile them
4. Add `packages/core/src/index.ts` barrel export
5. Make `packages/vscode-extension` depend on `@repodoc/core` in its `package.json`
6. Update VS Code extension imports to use `@repodoc/core` instead of relative paths
7. Delete the duplicates from `packages/vscode-extension/src/`
8. Verify extension still works

### Phase 3: Define and Implement Interfaces

1. Create `auth/types.ts`, `config/types.ts`, `storage/types.ts`, `progress/types.ts` in core
2. Create `packages/vscode-extension/src/adapters/` with VS Code implementations
3. Extract `markdownToConfluenceStorage()` from `confluence.ts` into `packages/core/src/transformer/html.ts`
4. Refactor `ConfluencePublisher` to implement `DocPublisher` interface (adds `initialize()`, removes constructor config coupling)
5. Create `PublisherRegistry`
6. Create `packages/core/src/pipeline.ts` orchestrator

### Phase 4: Rewire VS Code Extension

1. Refactor `extension.ts` to:
   - Create adapters
   - Set up publisher registry
   - Call `runPipeline()` instead of manually orchestrating
2. Remove old orchestration logic from `extension.ts`
3. Keep all VS Code-specific code (sidebar, wizard, commands) in `packages/vscode-extension/`
4. Full regression test — every feature must still work

### Phase 5: Cleanup & Documentation

1. Remove `docs/PUBLISHER-ARCHITECTURE.md` (superseded by this doc + actual code)
2. Update `TODO.md` — mark architecture items as done
3. Update `package.json` scripts for monorepo
4. Update CI/CD pipeline for workspace build

### Migration Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Extension breaks mid-migration | Each phase ends with a working extension. Git tag between phases. |
| Import path confusion | IDE auto-import + `@repodoc/core` re-exports make it mechanical |
| Circular dependencies | Core NEVER imports from any consumer package. Enforced by `tsconfig` paths. |
| VSIX packaging breaks | Test `vsce package` after every phase. Workspaces need `bundledDependencies` or esbuild. |
| Performance regression | Core modules are the same code — no new allocations or abstractions in hot paths |

---

## Testing Strategy

### Core Package Tests

```
packages/core/
├── src/
└── tests/
    ├── unit/
    │   ├── git/diff.test.ts          ← mock child_process
    │   ├── scanner/scanner.test.ts   ← mock fs
    │   ├── llm/provider.test.ts      ← mock fetch
    │   ├── generator/generator.test.ts ← mock LLMProvider
    │   ├── transformer/html.test.ts  ← pure function, snapshot tests
    │   └── publisher/registry.test.ts
    ├── integration/
    │   └── pipeline.test.ts          ← full pipeline with in-memory adapters
    └── fixtures/
        ├── diffs/                    ← sample diff outputs
        └── repos/                    ← minimal repo structures
```

### Test Adapters (for core's own tests)

```typescript
// packages/core/tests/helpers/mockAdapters.ts
export const mockAuth: AuthProvider = {
  async getCredential(scope, providerId) {
    return { value: 'test-key-123' };
  },
};

export const mockConfig: ConfigProvider = {
  async getConfig() {
    return { llm: { provider: 'anthropic', model: 'claude-sonnet-4-20250514' }, ... };
  },
};

export const mockStorage: StorageProvider = {
  private pages = new Map<string, BranchPages>();
  async getPages(branch, publisherId) { return this.pages.get(`${branch}:${publisherId}`); },
  async setPages(branch, publisherId, pages) { this.pages.set(`${branch}:${publisherId}`, pages); },
  ...
};
```

---

## Build & Publish

### Build Pipeline

```
pnpm build
  ├── packages/core:build         → tsc → packages/core/dist/
  └── packages/vscode-extension:build  → tsc (or esbuild) → packages/vscode-extension/out/
```

### VSIX Packaging

Two approaches for bundling `@repodoc/core` into the VS Code extension's VSIX:

**Option A: esbuild (recommended)**
- Bundle everything into a single `out/extension.js`
- Core code gets inlined — no runtime dependency resolution needed
- Already on the TODO as a performance improvement
- VSIX goes from 1789 files to ~5

**Option B: bundledDependencies**
- List `@repodoc/core` in `bundledDependencies` in the extension's `package.json`
- `vsce package` will include it in the VSIX's `node_modules/`
- Works but doesn't solve the existing file-count problem

**Recommendation:** Do Option B initially (simplest, gets us working), then Option A (esbuild) as the separate TODO item it already is.

### TypeScript Configuration

```jsonc
// tsconfig.base.json (root)
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
    "skipLibCheck": true
  }
}

// packages/core/tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./dist",
    "rootDir": "./src",
    "composite": true
  },
  "include": ["src/**/*"]
}

// packages/vscode-extension/tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./out",
    "rootDir": "./src"
  },
  "references": [
    { "path": "../core" }
  ],
  "include": ["src/**/*"]
}
```

---

## Appendix: Interface Contracts (Full TypeScript)

All interfaces in one place for quick reference. These are the **contracts** that define the system boundaries.

```typescript
// ═══════════════════════════════════════════════
// AUTH
// ═══════════════════════════════════════════════

type CredentialScope = 'llm' | 'publisher';

interface Credential {
  value: string;
  expiresAt?: Date;
  metadata?: Record<string, string>;
}

interface AuthProvider {
  getCredential(scope: CredentialScope, providerId: string): Promise<Credential | undefined>;
  setCredential?(scope: CredentialScope, providerId: string, credential: Credential): Promise<void>;
  validateCredential?(scope: CredentialScope, providerId: string): Promise<boolean>;
  refreshCredential?(scope: CredentialScope, providerId: string): Promise<Credential | undefined>;
}

// ═══════════════════════════════════════════════
// CONFIG
// ═══════════════════════════════════════════════

type DocLength = 'concise' | 'standard' | 'detailed';
type LLMProviderType = 'anthropic' | 'openai' | 'bedrock';

interface RepoDocConfig {
  llm: { provider: LLMProviderType; model: string };
  baseBranch: string;
  docLength: DocLength;
  publishers: string[];
  publisherConfigs: Record<string, Record<string, unknown>>;
  bedrock?: { region: string; profile: string };
}

interface ConfigProvider {
  getConfig(): Promise<RepoDocConfig>;
}

// ═══════════════════════════════════════════════
// STORAGE
// ═══════════════════════════════════════════════

interface BranchPages {
  technicalPageId: string;
  nonTechnicalPageId: string;
  lastUpdated: string;
}

interface StorageProvider {
  getPages(branch: string, publisherId: string): Promise<BranchPages | undefined>;
  setPages(branch: string, publisherId: string, pages: BranchPages): Promise<void>;
  removeBranch(branch: string): Promise<void>;
  getHistory(): Promise<Array<{ branch: string; publisherId: string; pages: BranchPages }>>;
}

// ═══════════════════════════════════════════════
// PROGRESS
// ═══════════════════════════════════════════════

interface ProgressStep {
  step: 'config' | 'git' | 'scan' | 'llm' | 'generate' | 'publish' | 'done' | 'error';
  message: string;
  data?: Record<string, unknown>;
  percentage?: number;
}

interface ProgressReporter {
  report(step: ProgressStep): void;
}

// ═══════════════════════════════════════════════
// PUBLISHER
// ═══════════════════════════════════════════════

interface PublishResult {
  pageId: string;
  url: string;
  version?: number;
}

interface DocPublisher {
  readonly id: string;
  readonly displayName: string;
  initialize(credential: Credential, config: Record<string, unknown>): void;
  createPage(title: string, content: string): Promise<PublishResult>;
  updatePage(pageId: string, title: string, content: string, currentVersion?: number): Promise<PublishResult>;
  getPageVersion?(pageId: string): Promise<number>;
  pageExists?(pageId: string): Promise<boolean>;
  afterPublish?(pageId: string): Promise<void>;
}

// ═══════════════════════════════════════════════
// TRANSFORMER
// ═══════════════════════════════════════════════

type ContentFormat = 'html' | 'confluence-storage' | 'notion-blocks' | 'google-ops' | 'markdown';

interface ContentTransformer {
  readonly inputFormat: 'markdown';
  readonly outputFormat: ContentFormat;
  transform(markdown: string): string;
}

// ═══════════════════════════════════════════════
// PIPELINE (the public API)
// ═══════════════════════════════════════════════

interface PipelineAdapters {
  auth: AuthProvider;
  config: ConfigProvider;
  storage: StorageProvider;
  progress: ProgressReporter;
}

interface PipelineOptions {
  repoPath: string;
  baseBranchOverride?: string;
  selectedFiles?: string[];
  instructions?: string;
  publishers?: string[];
  dryRun?: boolean;
}

interface PipelineResult {
  docs: GeneratedDocs;
  published: Array<{
    publisherId: string;
    technical: PublishResult;
    nonTechnical: PublishResult;
  }>;
  localFallback?: string;
}

function runPipeline(
  adapters: PipelineAdapters,
  options: PipelineOptions,
  publisherRegistry: PublisherRegistry,
  cancellation?: { isCancelled: () => boolean }
): Promise<PipelineResult>;
```

---

## Comparison with integration-auth-service Patterns

| Pattern in integration-auth-service | Our Adaptation |
|-------------------------------------|---------------|
| `IntegrationAuthConnector` interface | `DocPublisher` interface |
| `IntegrationAuthConnectorRegistry` (ConcurrentHashMap, `@PostConstruct` init) | `PublisherRegistry` (Map, explicit registration) |
| `ValueResolver` strategy (`getSourceType()` routing) | `AuthProvider.getCredential(scope, providerId)` routing |
| `CredentialResolver` dispatcher (maps source→resolver) | Consumers implement `AuthProvider` directly (simpler — no Spring context) |
| `Token` interface (value, type, expiresAt, isExpired) | `Credential` interface (value, expiresAt, metadata) |
| `TokenRefreshService.getValidToken()` | `AuthProvider.refreshCredential()` (optional) |
| `OAuth2TokenGrantFlowStrategy` (per-grant-type strategy) | Future: `OAuthFlowStrategy` per publisher when OAuth is added |
| YAML-based config loading (`IntegrationAuthConfigLoader`) | `ConfigProvider` interface (each consumer loads its own way) |
| `GenericIntegrationAuthConnector` (one class handles all) | We'll keep typed publishers (`ConfluencePublisher`, etc.) — they have genuinely different APIs |

### Key Difference

Integration-auth-service is a **server** that manages tokens on behalf of many users. We're a **client-side tool** where each installation has one user. So:
- No database for token storage (each platform has its own secure store)
- No multi-tenant routing
- No HTTP endpoints for auth callbacks (yet — OAuth will add this via VS Code's `asExternalUri`)
- Simpler lifecycle: create adapters → call pipeline → done

But the **structural patterns** (registry, strategy, interface segregation) translate directly.

---

## Decision Log

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| pnpm workspaces over separate repos | Atomic changes, local linking, single CI | Separate npm package (slow iteration), path imports (can't support CLI/MCP) |
| No DI framework | 4 interfaces isn't enough complexity; explicit wiring is clearer | InversifyJS, tsyringe — all add runtime deps and decorators |
| `initialize()` on DocPublisher instead of constructor | Publishers are registered before credentials are available; lazy init | Factory per publisher (more boilerplate), credential in constructor (breaks registry) |
| `Credential.metadata` for Confluence email | Avoids a Confluence-specific `getEmail()` on AuthProvider | Separate `getConfluenceAuth()` method (breaks interface segregation) |
| Pipeline as a function, not a class | Stateless, testable, composable. No lifecycle to manage. | `PipelineRunner` class with `run()` (unnecessary state) |
| Cancellation via callback, not AbortController | Works with any consumer (AbortController is a web/Node API, Kotlin wouldn't have it) | AbortController (tighter coupling to Node/Web APIs) |
| Keep transformer return as `string` (not `string | object`) | Confluence/HTML is string. Notion blocks would need JSON.stringify for the wire anyway. Future: add `transformToObject()` if needed. | Generic return (complicates simple publishers) |
| Multi-publisher storage key: `(branch, publisherId)` | Natural expansion of current `branch → pages`. No data migration needed for existing Confluence entries. | Nested object `{ branch: { publisher: pages } }` (harder to migrate) |

---

## Open Questions (To Resolve During Implementation)

1. **VSIX bundling approach** — esbuild now or `bundledDependencies` first? (Recommendation: bundledDeps first, esbuild later as separate task)
2. **Error recovery (local .repodoc/ save)** — Should this be in core's pipeline or in the consumer? (Leaning: core, with a hook for consumers to customize the save path)
3. **Diff pagination** (splitting large diffs across multiple LLM calls) — Belongs in generator module? Or a pipeline middleware? (Defer — current truncation works fine)
4. **Page title format** — Currently hardcoded `${branch} — Technical/Summary`. Should pipeline accept a title template? (Probably yes — add to PipelineOptions)

---

## Next Steps

After this design is approved:

1. **Create implementation plan** (via writing-plans skill) breaking this into atomic, testable phases
2. **Phase 1** first — monorepo structure with zero logic changes, verify everything builds
3. Iterate through phases, verifying the extension works after each one
