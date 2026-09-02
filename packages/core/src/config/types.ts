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
