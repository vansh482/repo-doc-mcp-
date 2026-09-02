export interface PublishResult {
  pageId: string;
  url: string;
  version?: number;
}

export interface PublisherConfig {
  [key: string]: unknown;
}

export interface DocPublisher {
  readonly id: string;
  readonly displayName: string;
  initialize(credential: { value: string; metadata?: Record<string, string> }, config: PublisherConfig): void;
  createPage(title: string, content: string): Promise<PublishResult>;
  updatePage(pageId: string, title: string, content: string, currentVersion?: number): Promise<PublishResult>;
  getPageVersion?(pageId: string): Promise<number>;
  pageExists?(pageId: string): Promise<boolean>;
  afterPublish?(pageId: string): Promise<void>;
}
