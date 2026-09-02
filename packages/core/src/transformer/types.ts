export type ContentFormat = 'html' | 'confluence-storage' | 'notion-blocks' | 'google-ops' | 'markdown';

export interface ContentTransformer {
  readonly inputFormat: 'markdown';
  readonly outputFormat: ContentFormat;
  transform(markdown: string): string;
}
