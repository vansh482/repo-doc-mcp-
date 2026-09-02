import type { DocPublisher } from './types';

export class PublisherRegistry {
  private publishers = new Map<string, DocPublisher>();

  register(publisher: DocPublisher): void {
    this.publishers.set(publisher.id, publisher);
  }

  get(id: string): DocPublisher | undefined {
    return this.publishers.get(id);
  }

  has(id: string): boolean {
    return this.publishers.has(id);
  }

  list(): DocPublisher[] {
    return Array.from(this.publishers.values());
  }

  ids(): string[] {
    return Array.from(this.publishers.keys());
  }
}
