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

  // Mermaid code blocks → Confluence expand macro with raw text
  html = html.replace(/```mermaid\n([\s\S]*?)```/g, (_match, diagram) => {
    const escaped = escapeXml(diagram.trimEnd());
    return `<ac:structured-macro ac:name="expand"><ac:parameter ac:name="title">Mermaid Diagram (paste into mermaid.live to view)</ac:parameter><ac:rich-text-body><ac:structured-macro ac:name="code"><ac:parameter ac:name="language">none</ac:parameter><ac:plain-text-body><![CDATA[${escaped}]]></ac:plain-text-body></ac:structured-macro></ac:rich-text-body></ac:structured-macro>`;
  });

  // Regular code blocks → Confluence code macro
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, lang, code) => {
    const language = lang || 'none';
    const escaped = escapeXml(code.trimEnd());
    return `<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">${language}</ac:parameter><ac:plain-text-body><![CDATA[${escaped}]]></ac:plain-text-body></ac:structured-macro>`;
  });

  // Tables
  html = html.replace(/((?:\|[^\n]+\|\n)+)/g, (tableBlock) => {
    const rows = tableBlock.trim().split('\n');
    const isSeparator = (row: string) => /^\|[\s\-:|]+\|$/.test(row);

    let tableHtml = '<table><tbody>';
    let isHeader = true;

    for (const row of rows) {
      if (isSeparator(row)) {
        isHeader = false;
        continue;
      }

      const cells = row
        .replace(/^\|/, '')
        .replace(/\|$/, '')
        .split('|')
        .map(c => c.trim());

      const tag = isHeader ? 'th' : 'td';
      tableHtml += '<tr>';
      for (const cell of cells) {
        tableHtml += `<${tag}>${cell}</${tag}>`;
      }
      tableHtml += '</tr>';

      if (isHeader && rows.length > 1 && !isSeparator(rows[1])) {
        isHeader = false;
      }
    }

    tableHtml += '</tbody></table>';
    return tableHtml;
  });

  // Horizontal rules
  html = html.replace(/^---+$/gm, '<hr />');

  // Inline code (before links to avoid conflicts)
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

  // Headers
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Bold and italic
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // Ordered lists (must come before unordered)
  html = html.replace(/((?:^\d+\. .+\n?)+)/gm, (block) => {
    const items = block.trim().split('\n').map(line =>
      `<li>${line.replace(/^\d+\.\s+/, '')}</li>`
    );
    return `<ol>${items.join('')}</ol>`;
  });

  // Unordered lists (handle nesting with indentation)
  html = html.replace(/((?:^[\t ]*- .+\n?)+)/gm, (block) => {
    return convertNestedList(block.trim());
  });

  // Paragraphs: lines that aren't already wrapped in HTML tags
  html = html.replace(/^(?!<[a-z/!])(.+)$/gm, '<p>$1</p>');

  // Clean up empty paragraphs and extra whitespace
  html = html.replace(/<p>\s*<\/p>/g, '');
  html = html.replace(/\n{2,}/g, '\n');

  return html;
}

function convertNestedList(block: string): string {
  const lines = block.split('\n');
  let result = '<ul>';
  let currentDepth = 0;

  for (const line of lines) {
    const match = line.match(/^([\t ]*)- (.+)$/);
    if (!match) continue;

    const indent = match[1].length;
    const content = match[2];
    const depth = indent >= 4 ? 2 : indent >= 2 ? 1 : 0;

    while (depth > currentDepth) {
      result += '<ul>';
      currentDepth++;
    }
    while (depth < currentDepth) {
      result += '</li></ul>';
      currentDepth--;
    }

    result += `<li>${content}`;
  }

  while (currentDepth > 0) {
    result += '</li></ul>';
    currentDepth--;
  }
  result += '</li></ul>';

  return result;
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}
