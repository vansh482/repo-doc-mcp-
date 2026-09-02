import type { DocPublisher, PublishResult, PublisherConfig } from './types';

export class ConfluencePublisher implements DocPublisher {
  readonly id = 'confluence';
  readonly displayName = 'Confluence';

  private baseUrl = '';
  private spaceKey = '';
  private parentPageId = '';
  private authHeader = '';

  initialize(credential: { value: string; metadata?: Record<string, string> }, config: PublisherConfig): void {
    this.baseUrl = config.baseUrl as string;
    this.spaceKey = config.spaceKey as string;
    this.parentPageId = config.parentPageId as string;
    const email = credential.metadata?.email ?? '';
    this.authHeader = 'Basic ' + Buffer.from(`${email}:${credential.value}`).toString('base64');
  }

  async createPage(title: string, content: string): Promise<PublishResult> {
    const body = {
      type: 'page',
      title,
      space: { key: this.spaceKey },
      ancestors: [{ id: this.parentPageId }],
      body: {
        storage: {
          value: content,
          representation: 'storage',
        },
      },
    };

    const response = await this.request('/rest/api/content', {
      method: 'POST',
      body: JSON.stringify(body),
    });

    return {
      pageId: response.id,
      url: `${this.baseUrl}${response._links.webui}`,
      version: response.version.number,
    };
  }

  async updatePage(pageId: string, title: string, content: string, currentVersion?: number): Promise<PublishResult> {
    const version = currentVersion ?? await this.getPageVersion(pageId);

    const body = {
      type: 'page',
      title,
      version: { number: version + 1 },
      body: {
        storage: {
          value: content,
          representation: 'storage',
        },
      },
    };

    const response = await this.request(`/rest/api/content/${pageId}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    });

    return {
      pageId: response.id,
      url: `${this.baseUrl}${response._links.webui}`,
      version: response.version.number,
    };
  }

  async getPageVersion(pageId: string): Promise<number> {
    const response = await this.request(`/rest/api/content/${pageId}?expand=version`);
    return response.version.number;
  }

  async pageExists(pageId: string): Promise<boolean> {
    try {
      await this.request(`/rest/api/content/${pageId}`);
      return true;
    } catch {
      return false;
    }
  }

  async restrictPageToCurrentUser(pageId: string): Promise<void> {
    const currentUser = await this.request('/rest/api/user/current');
    const accountId = currentUser.accountId;

    const restrictions = [
      {
        operation: 'read',
        restrictions: {
          user: { results: [{ type: 'known', accountId }] },
          group: { results: [] },
        },
      },
      {
        operation: 'update',
        restrictions: {
          user: { results: [{ type: 'known', accountId }] },
          group: { results: [] },
        },
      },
    ];

    await this.request(`/rest/api/content/${pageId}/restriction`, {
      method: 'PUT',
      body: JSON.stringify(restrictions),
    });
  }

  private async request(path: string, options: RequestInit = {}): Promise<any> {
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Authorization': this.authHeader,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        ...(options.headers as Record<string, string> || {}),
      },
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(`Confluence API error (${response.status}): ${errorBody}`);
    }

    return response.json();
  }
}
