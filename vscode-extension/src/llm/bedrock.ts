import {
  BedrockRuntimeClient,
  InvokeModelCommand,
} from '@aws-sdk/client-bedrock-runtime';
import { fromIni } from '@aws-sdk/credential-providers';
import { LLMProvider, LLMResponse } from './provider';

export class BedrockProvider implements LLMProvider {
  private client: BedrockRuntimeClient;
  private model: string;

  constructor(model: string, region: string, profile?: string) {
    this.model = model;
    this.client = new BedrockRuntimeClient({
      region,
      ...(profile ? { credentials: fromIni({ profile }) } : {}),
    });
  }

  async generate(prompt: string, systemPrompt?: string): Promise<LLMResponse> {
    const body = JSON.stringify({
      anthropic_version: 'bedrock-2023-05-31',
      max_tokens: 4096,
      system: systemPrompt || '',
      messages: [{ role: 'user', content: prompt }],
    });

    try {
      const command = new InvokeModelCommand({
        modelId: this.model,
        contentType: 'application/json',
        accept: 'application/json',
        body: new TextEncoder().encode(body),
      });

      const response = await this.client.send(command);
      const responseBody = JSON.parse(new TextDecoder().decode(response.body));

      const textBlock = responseBody.content?.find(
        (block: any) => block.type === 'text'
      );
      if (!textBlock?.text) {
        throw new Error('No text content in Bedrock response');
      }
      return {
        content: textBlock.text,
        usage: {
          inputTokens: responseBody.usage?.input_tokens ?? 0,
          outputTokens: responseBody.usage?.output_tokens ?? 0,
        },
      };
    } catch (err: any) {
      if (err.name === 'AccessDeniedException') {
        throw new Error(
          'AWS Bedrock access denied. Check your IAM permissions and model access.'
        );
      }
      if (err.name === 'ResourceNotFoundException') {
        throw new Error(
          `Bedrock model not found: ${this.model}. Verify the model ID and region.`
        );
      }
      throw new Error(`Bedrock API error: ${err.message || err}`);
    }
  }
}
