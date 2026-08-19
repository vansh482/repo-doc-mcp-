import { AnthropicProvider } from './anthropic';
import { OpenAIProvider } from './openai';
import { BedrockProvider } from './bedrock';

export interface LLMProvider {
  generate(prompt: string, systemPrompt?: string): Promise<string>;
}

export type ProviderType = 'anthropic' | 'openai' | 'bedrock';

export interface ProviderConfig {
  apiKey?: string;
  model: string;
  region?: string;
  profile?: string;
}

export function createProvider(type: ProviderType, config: ProviderConfig): LLMProvider {
  switch (type) {
    case 'anthropic':
      if (!config.apiKey) {
        throw new Error('Anthropic API key is required. Run "Repo Doc: Setup" to configure.');
      }
      return new AnthropicProvider(config.apiKey, config.model);

    case 'openai':
      if (!config.apiKey) {
        throw new Error('OpenAI API key is required. Run "Repo Doc: Setup" to configure.');
      }
      return new OpenAIProvider(config.apiKey, config.model);

    case 'bedrock':
      if (!config.region) {
        throw new Error('AWS region is required for Bedrock. Run "Repo Doc: Setup" to configure.');
      }
      return new BedrockProvider(config.model, config.region, config.profile);

    default:
      throw new Error(`Unknown LLM provider: ${type}`);
  }
}
