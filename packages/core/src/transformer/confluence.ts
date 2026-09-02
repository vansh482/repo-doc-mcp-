import type { ContentTransformer } from './types';

export class ConfluenceTransformer implements ContentTransformer {
  readonly inputFormat = 'markdown' as const;
  readonly outputFormat = 'confluence-storage' as const;

  transform(markdown: string): string {
    return markdownToConfluenceStorage(markdown);
  }
}

function markdownToConfluenceStorage(markdown: string): string {
  let html = markdown;

  html = html.replace(/```mermaid\n([\s\S]*?)```/g, (_match, diagram) => {
    const escaped = escapeXml(diagram.trimEnd());
    return `<ac:structured-macro ac:name="expand"><ac:parameter ac:name="title">Mermaid Diagram (paste into mermaid.live to view)</ac:parameter><ac:rich-text-body><ac:structured-macro ac:name="code"><ac:parameter ac:name="language">none</ac:parameter><ac:plain-text-body><![CDATA[${escaped}]]></ac:plain-text-body></ac:structured-macro></ac:rich-text-body></ac:structured-macro>`;
  });

  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, lang, code) => {
    const language = lang || 'none';
    const escaped = escapeXml(code.trimEnd());
    return `<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">${language}</ac:parameter><ac:plain-text-body><![CDATA[${escaped}]]></ac:plain-text-body></ac:structured-macro>`;
  });

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

  html = html.replace(/^---+$/gm, '<hr />');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  html = html.replace(/((?:^\d+\. .+\n?)+)/gm, (block) => {
    const items = block.trim().split('\n').map(line =>
      `<li>${line.replace(/^\d+\.\s+/, '')}</li>`
    );
    return `<ol>${items.join('')}</ol>`;
  });

  html = html.replace(/((?:^[\t ]*- .+\n?)+)/gm, (block) => {
    return convertNestedList(block.trim());
  });

  html = html.replace(/^(?!<[a-z/!])(.+)$/gm, '<p>$1</p>');
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
