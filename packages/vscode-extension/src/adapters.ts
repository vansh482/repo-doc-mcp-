import * as vscode from 'vscode';
import type { AuthProvider, Credential, CredentialScope } from '@repodoc/core';
import type { ConfigProvider, RepoDocConfig } from '@repodoc/core';
import type { StorageProvider, BranchPages } from '@repodoc/core';
import type { ProgressReporter, ProgressStep } from '@repodoc/core';
import { SecretStore } from './config/secrets';

export class VsCodeAuthProvider implements AuthProvider {
  constructor(private secrets: SecretStore) {}

  async getCredential(scope: CredentialScope, providerId: string): Promise<Credential | undefined> {
    if (scope === 'llm') {
      if (providerId === 'bedrock') return undefined;
      const key = await this.secrets.getApiKey(providerId as 'anthropic' | 'openai');
      return key ? { value: key } : undefined;
    }

    if (scope === 'publisher' && providerId === 'confluence') {
      const cfgRaw = vscode.workspace.getConfiguration('repoDoc');
      const token = await this.secrets.getConfluenceToken() || cfgRaw.get<string>('confluence.apiToken') || '';
      const email = await this.secrets.getConfluenceEmail() || cfgRaw.get<string>('confluence.email') || '';
      if (!token || !email) return undefined;
      return { value: token, metadata: { email } };
    }

    return undefined;
  }
}

export class VsCodeConfigProvider implements ConfigProvider {
  async getConfig(): Promise<RepoDocConfig> {
    const cfg = vscode.workspace.getConfiguration('repoDoc');
    return {
      llm: {
        provider: cfg.get('llm.provider') || 'anthropic',
        model: cfg.get('llm.model') || 'claude-sonnet-4-20250514',
      },
      baseBranch: cfg.get('baseBranch') || 'main',
      docLength: cfg.get('docLength') || 'concise',
      publishers: ['confluence'],
      publisherConfigs: {
        confluence: {
          baseUrl: cfg.get('confluence.baseUrl') || '',
          spaceKey: cfg.get('confluence.spaceKey') || '',
          parentPageId: cfg.get('confluence.parentPageId') || '',
        },
      },
      bedrock: {
        region: cfg.get('bedrock.region') || 'us-west-2',
        profile: cfg.get('bedrock.profile') || '',
      },
    };
  }
}

const STORAGE_KEY = 'repoDoc.branchPages';

export class VsCodeStorageProvider implements StorageProvider {
  constructor(private state: vscode.Memento) {}

  async getPages(branch: string, publisherId: string): Promise<BranchPages | undefined> {
    const all = this.getAllTracked();
    const key = `${branch}::${publisherId}`;
    if (all[key]) return all[key];
    // Fallback: legacy entries stored without publisherId
    return all[branch];
  }

  async setPages(branch: string, publisherId: string, pages: BranchPages): Promise<void> {
    const all = this.getAllTracked();
    all[`${branch}::${publisherId}`] = pages;
    await this.state.update(STORAGE_KEY, all);
  }

  async removeBranch(branch: string): Promise<void> {
    const all = this.getAllTracked();
    for (const key of Object.keys(all)) {
      if (key === branch || key.startsWith(`${branch}::`)) {
        delete all[key];
      }
    }
    await this.state.update(STORAGE_KEY, all);
  }

  async getHistory(): Promise<Array<{ branch: string; publisherId: string; pages: BranchPages }>> {
    const all = this.getAllTracked();
    return Object.entries(all)
      .map(([key, pages]) => {
        const [branch, publisherId] = key.includes('::') ? key.split('::') : [key, 'confluence'];
        return { branch, publisherId, pages };
      })
      .sort((a, b) => new Date(b.pages.lastUpdated).getTime() - new Date(a.pages.lastUpdated).getTime());
  }

  private getAllTracked(): Record<string, BranchPages> {
    return this.state.get<Record<string, BranchPages>>(STORAGE_KEY) || {};
  }
}

export class VsCodeProgressReporter implements ProgressReporter {
  constructor(private onReport: (step: ProgressStep) => void) {}

  report(step: ProgressStep): void {
    this.onReport(step);
  }
}
