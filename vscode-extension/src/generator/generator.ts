import type { LLMProvider, TokenUsage } from '../llm/provider';
import type { BranchDiff } from '../git/diff';
import type { RepoContext } from '../scanner/scanner';
import type { DocLength } from '../config/settings';
import { SYSTEM_PROMPT, buildTechnicalPrompt, buildNonTechnicalPrompt } from './prompts';

export interface GeneratedDocs {
  technical: string;
  nonTechnical: string;
  branch: string;
  generatedAt: string;
  usage?: TokenUsage;
}

export async function generateDocs(
  provider: LLMProvider,
  diff: BranchDiff,
  context: RepoContext,
  docLength: DocLength = 'concise',
  instructions?: string
): Promise<GeneratedDocs> {
  const [techResponse, nonTechResponse] = await Promise.all([
    provider.generate(buildTechnicalPrompt(diff, context, docLength, instructions), SYSTEM_PROMPT),
    provider.generate(buildNonTechnicalPrompt(diff, context, docLength, instructions), SYSTEM_PROMPT),
  ]);

  const totalUsage: TokenUsage | undefined =
    techResponse.usage || nonTechResponse.usage
      ? {
          inputTokens: (techResponse.usage?.inputTokens ?? 0) + (nonTechResponse.usage?.inputTokens ?? 0),
          outputTokens: (techResponse.usage?.outputTokens ?? 0) + (nonTechResponse.usage?.outputTokens ?? 0),
        }
      : undefined;

  return {
    technical: techResponse.content,
    nonTechnical: nonTechResponse.content,
    branch: diff.currentBranch,
    generatedAt: new Date().toISOString(),
    usage: totalUsage,
  };
}
