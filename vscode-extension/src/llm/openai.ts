import OpenAI from 'openai';
import { LLMProvider } from './provider';

export class OpenAIProvider implements LLMProvider {
  private client: OpenAI;
  private model: string;

  constructor(apiKey: string, model: string) {
    this.client = new OpenAI({ apiKey });
    this.model = model;
  }

  async generate(prompt: string, systemPrompt?: string): Promise<string> {
    try {
      const messages: OpenAI.ChatCompletionMessageParam[] = [];
      if (systemPrompt) {
        messages.push({ role: 'system', content: systemPrompt });
      }
      messages.push({ role: 'user', content: prompt });

      const response = await this.client.chat.completions.create({
        model: this.model,
        max_tokens: 4096,
        messages,
      });

      const content = response.choices[0]?.message?.content;
      if (!content) {
        throw new Error('No content in OpenAI response');
      }
      return content;
    } catch (err: any) {
      if (err?.status === 401) {
        throw new Error('Invalid OpenAI API key. Check your configuration.');
      }
      if (err?.status === 429) {
        throw new Error('OpenAI rate limit exceeded. Please wait and try again.');
      }
      throw new Error(`OpenAI API error: ${err.message || err}`);
    }
  }
}
