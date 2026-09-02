import type { AuthProvider } from '../auth/types';
import type { ConfigProvider, RepoDocConfig } from '../config/types';
import type { StorageProvider } from '../storage/types';
import type { ProgressReporter } from '../progress/types';
import { nullProgress } from '../progress/types';
import type { DocPublisher, PublishResult, PublisherConfig } from '../publisher/types';
import type { ContentTransformer } from '../transformer/types';
import type { PublisherRegistry } from '../publisher/registry';
import type { BranchDiff } from '../git/diff';
import { getBranchDiff, detectBaseBranch, filterDiffByFiles } from '../git/diff';
import { scanRepo } from '../scanner/scanner';
import { createProvider } from '../llm/provider';
import type { GeneratedDocs } from '../generator/generator';
import { generateDocs } from '../generator/generator';

export interface PipelineAdapters {
  auth: AuthProvider;
  config: ConfigProvider;
  storage: StorageProvider;
  progress?: ProgressReporter;
}

export interface PipelineOptions {
  repoPath: string;
  baseBranchOverride?: string;
  selectedFiles?: string[];
  customInstructions?: string;
}

export interface PipelineResult {
  branch: string;
  baseBranch: string;
  docs: GeneratedDocs;
  publishResults: Record<string, { technical: PublishResult; nonTechnical: PublishResult }>;
}

export async function runPipeline(
  adapters: PipelineAdapters,
  options: PipelineOptions,
  registry: PublisherRegistry,
  transformers: Map<string, ContentTransformer>,
): Promise<PipelineResult> {
  const progress = adapters.progress ?? nullProgress;

  // Step 1: Load config
  progress.report({ step: 'config', message: 'Loading configuration...' });
  const config = await adapters.config.getConfig();

  // Step 2: Git diff
  progress.report({ step: 'git', message: 'Computing branch diff...' });
  const baseBranch = options.baseBranchOverride || config.baseBranch || await detectBaseBranch(options.repoPath);
  let diff = await getBranchDiff(options.repoPath, baseBranch);

  if (options.selectedFiles && options.selectedFiles.length > 0) {
    diff = filterDiffByFiles(diff, options.selectedFiles);
  }

  if (!diff.diffContent && diff.changedFiles.length === 0) {
    throw new NoDiffError(diff.currentBranch, baseBranch);
  }

  progress.report({
    step: 'git',
    message: `Found ${diff.changedFiles.length} changed files`,
    data: { files: diff.changedFiles.length, truncated: diff.truncated },
  });

  // Step 3: Scan repo
  progress.report({ step: 'scan', message: 'Scanning repository...' });
  const repoContext = await scanRepo(options.repoPath);

  progress.report({
    step: 'scan',
    message: `Scanned ${repoContext.totalFiles} files`,
    data: { totalFiles: repoContext.totalFiles },
  });

  // Step 4: Generate docs via LLM
  progress.report({ step: 'llm', message: 'Generating docs with AI...' });
  const llmCredential = await adapters.auth.getCredential('llm', config.llm.provider);
  const provider = createProvider(config.llm.provider, {
    apiKey: llmCredential?.value,
    model: config.llm.model,
    region: config.bedrock?.region,
    profile: config.bedrock?.profile,
  });

  const docs = await generateDocs(provider, diff, repoContext, config.docLength, options.customInstructions);

  progress.report({
    step: 'generate',
    message: 'AI generation complete',
    data: { usage: docs.usage },
  });

  // Step 5: Publish to each configured publisher
  progress.report({ step: 'publish', message: 'Publishing docs...' });
  const publishResults: Record<string, { technical: PublishResult; nonTechnical: PublishResult }> = {};

  for (const publisherId of config.publishers) {
    const publisher = registry.get(publisherId);
    if (!publisher) {
      throw new Error(`Publisher "${publisherId}" not registered`);
    }

    const credential = await adapters.auth.getCredential('publisher', publisherId);
    if (!credential) {
      throw new Error(`No credentials for publisher "${publisherId}"`);
    }

    const pubConfig: PublisherConfig = config.publisherConfigs[publisherId] ?? {};
    publisher.initialize(credential, pubConfig);

    const transformer = transformers.get(publisherId);
    const techContent = transformer ? transformer.transform(docs.technical) : docs.technical;
    const nonTechContent = transformer ? transformer.transform(docs.nonTechnical) : docs.nonTechnical;

    const techTitle = `${diff.currentBranch} — Technical`;
    const nonTechTitle = `${diff.currentBranch} — Summary`;

    const existingPages = await adapters.storage.getPages(diff.currentBranch, publisherId);

    let techResult: PublishResult;
    let nonTechResult: PublishResult;

    if (existingPages) {
      techResult = await publisher.updatePage(existingPages.technicalPageId, techTitle, techContent);
      nonTechResult = await publisher.updatePage(existingPages.nonTechnicalPageId, nonTechTitle, nonTechContent);
    } else {
      techResult = await publisher.createPage(techTitle, techContent);
      nonTechResult = await publisher.createPage(nonTechTitle, nonTechContent);

      await adapters.storage.setPages(diff.currentBranch, publisherId, {
        technicalPageId: techResult.pageId,
        nonTechnicalPageId: nonTechResult.pageId,
        lastUpdated: new Date().toISOString(),
      });
    }

    if (publisher.afterPublish) {
      await publisher.afterPublish(techResult.pageId);
      await publisher.afterPublish(nonTechResult.pageId);
    }

    publishResults[publisherId] = { technical: techResult, nonTechnical: nonTechResult };
  }

  progress.report({ step: 'done', message: 'Pipeline complete' });

  return {
    branch: diff.currentBranch,
    baseBranch,
    docs,
    publishResults,
  };
}

export class NoDiffError extends Error {
  constructor(public readonly branch: string, public readonly baseBranch: string) {
    super(`No changes found on branch "${branch}" compared to "${baseBranch}"`);
    this.name = 'NoDiffError';
  }
}
