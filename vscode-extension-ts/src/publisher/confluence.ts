export interface ConfluenceConfig {
  baseUrl: string;
  email: string;
  apiToken: string;
  spaceKey: string;
  parentPageId: string;
}

export interface PublishResult {
  pageId: string;
  url: string;
  version: number;
}

export class ConfluencePublisher {
  private authHeader: string;

  constructor(private config: ConfluenceConfig) {
    this.authHeader = 'Basic ' + Buffer.from(`${config.email}:${config.apiToken}`).toString('base64');
  }

  async createPage(title: string, content: string): Promise<PublishResult> {
    const body = {
      type: 'page',
      title,
      space: { key: this.config.spaceKey },
      ancestors: [{ id: this.config.parentPageId }],
      body: {
        storage: {
          value: markdownToConfluenceStorage(content),
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
      url: `${this.config.baseUrl}${response._links.webui}`,
      version: response.version.number,
    };
  }

  async updatePage(pageId: string, title: string, content: string, currentVersion: number): Promise<PublishResult> {
    const body = {
      type: 'page',
      title,
      version: { number: currentVersion + 1 },
      body: {
        storage: {
          value: markdownToConfluenceStorage(content),
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
      url: `${this.config.baseUrl}${response._links.webui}`,
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

  private async request(path: string, options: RequestInit = {}): Promise<any> {
    const url = `${this.config.baseUrl}${path}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Authorization': this.authHeader,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        ...(options.headers || {}),
      },
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(`Confluence API error (${response.status}): ${errorBody}`);
    }

    return response.json();
  }
}

function markdownToConfluenceStorage(markdown: string): string {
  let html = markdown;

  // Code blocks → Confluence code macro
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, lang, code) => {
    const language = lang || 'none';
    const escaped = escapeXml(code.trimEnd());
    return `<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">${language}</ac:parameter><ac:plain-text-body><![CDATA[${escaped}]]></ac:plain-text-body></ac:structured-macro>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Headers
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Bold and italic
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // Unordered lists
  html = html.replace(/^(\s*)- (.+)$/gm, '$1<li>$2</li>');
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

  // Paragraphs: lines that aren't already wrapped in HTML tags
  html = html.replace(/^(?!<[a-z/])(.+)$/gm, '<p>$1</p>');

  // Clean up empty paragraphs
  html = html.replace(/<p>\s*<\/p>/g, '');

  return html;
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}
