export interface ProgressStep {
  step: 'config' | 'git' | 'scan' | 'llm' | 'generate' | 'publish' | 'done' | 'error';
  message: string;
  data?: Record<string, unknown>;
  percentage?: number;
}

export interface ProgressReporter {
  report(step: ProgressStep): void;
}

export const nullProgress: ProgressReporter = {
  report() {},
};
