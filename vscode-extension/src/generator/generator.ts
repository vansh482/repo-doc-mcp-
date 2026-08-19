import type { LLMProvider } from '../llm/provider';
import type { BranchDiff } from '../git/diff';
import type { RepoContext } from '../scanner/scanner';
import { SYSTEM_PROMPT, buildTechnicalPrompt, buildNonTechnicalPrompt } from './prompts';

export interface GeneratedDocs {
  technical: string;
  nonTechnical: string;
  branch: string;
  generatedAt: string;
}

export async function generateDocs(
  provider: LLMProvider,
  diff: BranchDiff,
  context: RepoContext
): Promise<GeneratedDocs> {
  const [technical, nonTechnical] = await Promise.all([
    provider.generate(buildTechnicalPrompt(diff, context), SYSTEM_PROMPT),
    provider.generate(buildNonTechnicalPrompt(diff, context), SYSTEM_PROMPT),
  ]);

  return {
    technical,
    nonTechnical,
    branch: diff.currentBranch,
    generatedAt: new Date().toISOString(),
  };
}
