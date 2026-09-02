// Adapter interfaces
export type { AuthProvider, Credential, CredentialScope } from './auth/types';
export type { ConfigProvider, RepoDocConfig, DocLength, LLMProviderType } from './config/types';
export type { StorageProvider, BranchPages } from './storage/types';
export type { ProgressReporter, ProgressStep } from './progress/types';
export { nullProgress } from './progress/types';
export type { DocPublisher, PublishResult, PublisherConfig } from './publisher/types';
export type { ContentTransformer, ContentFormat } from './transformer/types';

// Git
export type { BranchDiff } from './git/diff';
export { getBranchDiff, detectBaseBranch, filterDiffByFiles } from './git/diff';

// Scanner
export type { RepoContext } from './scanner/scanner';
export { scanRepo } from './scanner/scanner';

// LLM
export type { LLMProvider, LLMResponse, TokenUsage, ProviderType, ProviderConfig } from './llm/provider';
export { createProvider } from './llm/provider';

// Generator
export type { GeneratedDocs } from './generator/generator';
export { generateDocs } from './generator/generator';
