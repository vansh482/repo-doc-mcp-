import Anthropic from '@anthropic-ai/sdk';
import { LLMProvider, LLMResponse } from './provider';

export class AnthropicProvider implements LLMProvider {
  private client: Anthropic;
  private model: string;

  constructor(apiKey: string, model: string) {
    this.client = new Anthropic({ apiKey });
    this.model = model;
  }

  async generate(prompt: string, systemPrompt?: string): Promise<LLMResponse> {
    try {
      const response = await this.client.messages.create({
        model: this.model,
        max_tokens: 4096,
        system: systemPrompt || '',
        messages: [{ role: 'user', content: prompt }],
      });

      const textBlock = response.content.find(block => block.type === 'text');
      if (!textBlock || textBlock.type !== 'text') {
        throw new Error('No text content in Anthropic response');
      }
      return {
        content: textBlock.text,
        usage: {
          inputTokens: response.usage?.input_tokens ?? 0,
          outputTokens: response.usage?.output_tokens ?? 0,
        },
      };
    } catch (err: any) {
      if (err?.status === 401) {
        throw new Error('Invalid Anthropic API key. Check your configuration.');
      }
      if (err?.status === 429) {
        throw new Error('Anthropic rate limit exceeded. Please wait and try again.');
      }
      throw new Error(`Anthropic API error: ${err.message || err}`);
    }
  }
}
