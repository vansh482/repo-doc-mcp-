/**
 * Webview Panel — renders generated documentation inside VS Code.
 *
 * VS Code webviews are essentially embedded browsers (Chromium) that can
 * display custom HTML/CSS/JS. We use this to create a polished reading
 * experience for the generated documentation, complete with:
 *
 * - Syntax-highlighted code blocks
 * - Mermaid diagram rendering
 * - Tab switching between Technical and Non-Technical docs
 * - A table of contents sidebar
 * - Dark/light theme matching VS Code's current theme
 *
 * ARCHITECTURE:
 * ┌───────────────────────────────────────────────┐
 * │ VS Code Window                                │
 * │  ┌─────────────┐ ┌─────────────────────────┐  │
 * │  │  Explorer   │ │  Webview Panel           │  │
 * │  │  Sidebar    │ │  ┌──────┬──────────────┐ │  │
 * │  │             │ │  │ TOC  │ Doc Content   │ │  │
 * │  │             │ │  │      │               │ │  │
 * │  │             │ │  │      │ (rendered MD) │ │  │
 * │  │             │ │  │      │               │ │  │
 * │  │             │ │  └──────┴──────────────┘ │  │
 * │  └─────────────┘ └─────────────────────────┘  │
 * └───────────────────────────────────────────────┘
 */

import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";

/**
 * Manages the documentation viewer webview panel.
 *
 * This class follows VS Code's recommended pattern of a singleton panel
 * that persists across multiple doc generations. If the user generates
 * new docs while the panel is open, it updates in-place rather than
 * opening a new panel.
 */
export class DocViewerPanel {
  public static readonly viewType = "repoDoc.docViewer";
  private static currentPanel: DocViewerPanel | undefined;

  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];

  /**
   * Show the documentation viewer. Creates a new panel or reveals
   * an existing one if it's already open.
   */
  public static show(
    extensionUri: vscode.Uri,
    techDocContent: string,
    nonTechDocContent: string,
    repoName: string,
  ): DocViewerPanel {
    const column = vscode.ViewColumn.Beside;

    // If we already have a panel, update its content instead of creating a new one
    if (DocViewerPanel.currentPanel) {
      DocViewerPanel.currentPanel.panel.reveal(column);
      DocViewerPanel.currentPanel.updateContent(
        techDocContent,
        nonTechDocContent,
        repoName,
      );
      return DocViewerPanel.currentPanel;
    }

    // Create a new panel
    const panel = vscode.window.createWebviewPanel(
      DocViewerPanel.viewType,
      `📄 ${repoName} — Documentation`,
      column,
      {
        enableScripts: true, // Needed for Mermaid rendering and tab switching
        retainContextWhenHidden: true, // Keep content when panel is hidden
        localResourceRoots: [extensionUri],
      },
    );

    DocViewerPanel.currentPanel = new DocViewerPanel(panel, extensionUri);
    DocViewerPanel.currentPanel.updateContent(
      techDocContent,
      nonTechDocContent,
      repoName,
    );

    return DocViewerPanel.currentPanel;
  }

  /**
   * Show a loading state while docs are being generated.
   */
  public static showLoading(
    extensionUri: vscode.Uri,
    repoName: string,
  ): DocViewerPanel {
    return DocViewerPanel.show(extensionUri, "", "", repoName);
  }

  private constructor(
    panel: vscode.WebviewPanel,
    private readonly extensionUri: vscode.Uri,
  ) {
    this.panel = panel;

    // Clean up when the panel is closed
    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

    // Handle messages from the webview (e.g., user clicks "Copy to clipboard")
    this.panel.webview.onDidReceiveMessage(
      (message) => this.handleWebviewMessage(message),
      null,
      this.disposables,
    );
  }

  /**
   * Update the webview content with new documentation.
   */
  public updateContent(
    techDoc: string,
    nonTechDoc: string,
    repoName: string,
  ): void {
    this.panel.title = `📄 ${repoName} — Documentation`;
    this.panel.webview.html = this.buildHTML(techDoc, nonTechDoc, repoName);
  }

  /**
   * Show a progress/loading state in the webview.
   */
  public showProgress(message: string): void {
    this.panel.webview.postMessage({
      type: "progress",
      message,
    });
  }

  private handleWebviewMessage(message: any): void {
    switch (message.type) {
      case "copyToClipboard":
        vscode.env.clipboard.writeText(message.text);
        vscode.window.showInformationMessage("Copied to clipboard!");
        break;
      case "openFile":
        const uri = vscode.Uri.file(message.path);
        vscode.commands.executeCommand("vscode.open", uri);
        break;
      case "exportMarkdown":
        this.exportAsMarkdown(message.content, message.filename);
        break;
    }
  }

  private async exportAsMarkdown(content: string, filename: string): Promise<void> {
    const uri = await vscode.window.showSaveDialog({
      defaultUri: vscode.Uri.file(filename),
      filters: { Markdown: ["md"], "All files": ["*"] },
    });
    if (uri) {
      fs.writeFileSync(uri.fsPath, content, "utf-8");
      vscode.window.showInformationMessage(`Saved to ${uri.fsPath}`);
    }
  }

  private dispose(): void {
    DocViewerPanel.currentPanel = undefined;
    this.panel.dispose();
    while (this.disposables.length) {
      const d = this.disposables.pop();
      if (d) {
        d.dispose();
      }
    }
  }

  /**
   * Build the complete HTML for the documentation viewer.
   *
   * This is a self-contained HTML page with embedded CSS and JS.
   * It includes:
   * - A tab bar to switch between Technical and Non-Technical docs
   * - A table of contents extracted from headings
   * - Markdown rendering (we parse ## and ### headings)
   * - Mermaid diagram rendering via CDN
   * - Theme-aware styling that follows VS Code's color theme
   */
  private buildHTML(
    techDoc: string,
    nonTechDoc: string,
    repoName: string,
  ): string {
    // Escape the markdown content for safe embedding in HTML
    const escapedTech = this.escapeForHTML(techDoc);
    const escapedNonTech = this.escapeForHTML(nonTechDoc);

    const isLoading = !techDoc && !nonTechDoc;

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none';
      style-src 'unsafe-inline' https://fonts.googleapis.com;
      font-src https://fonts.gstatic.com;
      script-src 'unsafe-inline' https://cdn.jsdelivr.net;
      img-src data: https:;">
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Source+Serif+4:ital,wght@0,400;0,600;0,700;1,400&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <title>${repoName} — Documentation</title>
  <style>
    /* ════════════════════════════════════════════════
       CSS Variables — inherits from VS Code's theme
       ════════════════════════════════════════════════ */
    :root {
      --bg-primary: var(--vscode-editor-background, #1a1b26);
      --bg-secondary: var(--vscode-sideBar-background, #16161e);
      --bg-tertiary: var(--vscode-editorGroupHeader-tabsBackground, #1f2035);
      --text-primary: var(--vscode-editor-foreground, #c0caf5);
      --text-secondary: var(--vscode-descriptionForeground, #787c99);
      --text-muted: var(--vscode-disabledForeground, #565a6e);
      --accent: var(--vscode-textLink-foreground, #7aa2f7);
      --accent-hover: var(--vscode-textLink-activeForeground, #89b4fa);
      --border: var(--vscode-panel-border, #292e42);
      --code-bg: var(--vscode-textCodeBlock-background, #1a1b26);
      --success: #9ece6a;
      --warning: #e0af68;
      --tab-active-border: var(--vscode-tab-activeBorderTop, #7aa2f7);
      --scrollbar: var(--vscode-scrollbarSlider-background, #292e4266);
    }

    /* ════════════════════════════════════════════════
       Reset & Base
       ════════════════════════════════════════════════ */
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: 'DM Sans', -apple-system, sans-serif;
      background: var(--bg-primary);
      color: var(--text-primary);
      line-height: 1.7;
      font-size: 14px;
      overflow: hidden;
      height: 100vh;
    }

    /* ════════════════════════════════════════════════
       Layout — Header + Main (TOC sidebar + Content)
       ════════════════════════════════════════════════ */
    .app {
      display: flex;
      flex-direction: column;
      height: 100vh;
    }

    .header {
      background: var(--bg-secondary);
      border-bottom: 1px solid var(--border);
      padding: 0;
      flex-shrink: 0;
    }

    .header-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 20px 0;
    }

    .header-title {
      font-family: 'Source Serif 4', Georgia, serif;
      font-size: 18px;
      font-weight: 700;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .header-title .icon { font-size: 20px; }

    .header-actions {
      display: flex;
      gap: 6px;
    }

    .header-btn {
      background: var(--bg-tertiary);
      border: 1px solid var(--border);
      color: var(--text-secondary);
      padding: 5px 12px;
      border-radius: 4px;
      font-size: 12px;
      cursor: pointer;
      font-family: 'DM Sans', sans-serif;
      transition: all 0.15s ease;
    }

    .header-btn:hover {
      color: var(--text-primary);
      border-color: var(--accent);
    }

    /* ════════════════════════════════════════════════
       Tab Bar
       ════════════════════════════════════════════════ */
    .tabs {
      display: flex;
      padding: 0 20px;
      margin-top: 12px;
    }

    .tab {
      padding: 8px 16px;
      font-size: 13px;
      font-weight: 500;
      color: var(--text-muted);
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.2s ease;
      user-select: none;
      font-family: 'DM Sans', sans-serif;
      background: none;
      border-top: none;
      border-left: none;
      border-right: none;
    }

    .tab:hover { color: var(--text-secondary); }

    .tab.active {
      color: var(--accent);
      border-bottom-color: var(--tab-active-border);
    }

    .tab .tab-badge {
      display: inline-block;
      padding: 1px 6px;
      border-radius: 3px;
      font-size: 10px;
      margin-left: 6px;
      background: var(--bg-tertiary);
      color: var(--text-muted);
    }

    .tab.active .tab-badge {
      background: color-mix(in srgb, var(--accent) 15%, transparent);
      color: var(--accent);
    }

    /* ════════════════════════════════════════════════
       Main Content Area (TOC + Doc)
       ════════════════════════════════════════════════ */
    .main {
      display: flex;
      flex: 1;
      overflow: hidden;
    }

    /* Table of Contents sidebar */
    .toc {
      width: 240px;
      min-width: 200px;
      background: var(--bg-secondary);
      border-right: 1px solid var(--border);
      overflow-y: auto;
      padding: 16px 0;
      flex-shrink: 0;
    }

    .toc-title {
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 1.2px;
      color: var(--text-muted);
      padding: 0 16px 8px;
    }

    .toc-item {
      display: block;
      padding: 5px 16px;
      font-size: 12px;
      color: var(--text-secondary);
      text-decoration: none;
      cursor: pointer;
      transition: all 0.1s ease;
      border-left: 2px solid transparent;
    }

    .toc-item:hover {
      color: var(--text-primary);
      background: var(--bg-tertiary);
    }

    .toc-item.active {
      color: var(--accent);
      border-left-color: var(--accent);
      background: color-mix(in srgb, var(--accent) 5%, transparent);
    }

    .toc-item.sub { padding-left: 28px; font-size: 11px; }

    /* Document content area */
    .content {
      flex: 1;
      overflow-y: auto;
      padding: 32px 48px 80px;
      max-width: 900px;
    }

    .content::-webkit-scrollbar { width: 8px; }
    .content::-webkit-scrollbar-track { background: transparent; }
    .content::-webkit-scrollbar-thumb {
      background: var(--scrollbar);
      border-radius: 4px;
    }

    /* ════════════════════════════════════════════════
       Markdown Rendered Content
       ════════════════════════════════════════════════ */
    .doc-content { display: none; }
    .doc-content.active { display: block; }

    .doc-content h1 {
      font-family: 'Source Serif 4', Georgia, serif;
      font-size: 28px;
      font-weight: 700;
      margin-bottom: 8px;
      color: var(--text-primary);
    }

    .doc-content h2 {
      font-family: 'Source Serif 4', Georgia, serif;
      font-size: 22px;
      font-weight: 600;
      margin-top: 40px;
      margin-bottom: 16px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
      color: var(--text-primary);
    }

    .doc-content h3 {
      font-family: 'DM Sans', sans-serif;
      font-size: 16px;
      font-weight: 600;
      margin-top: 28px;
      margin-bottom: 10px;
      color: var(--text-primary);
    }

    .doc-content p {
      margin-bottom: 14px;
      color: var(--text-primary);
      line-height: 1.8;
    }

    .doc-content ul, .doc-content ol {
      margin-bottom: 14px;
      padding-left: 24px;
    }

    .doc-content li {
      margin-bottom: 4px;
      line-height: 1.7;
    }

    .doc-content strong {
      font-weight: 600;
      color: var(--text-primary);
    }

    .doc-content em { font-style: italic; }

    .doc-content a {
      color: var(--accent);
      text-decoration: none;
    }

    .doc-content a:hover { text-decoration: underline; }

    /* Code blocks */
    .doc-content code {
      font-family: 'JetBrains Mono', 'Fira Code', monospace;
      font-size: 12.5px;
      background: var(--code-bg);
      padding: 2px 6px;
      border-radius: 3px;
      border: 1px solid var(--border);
    }

    .doc-content pre {
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 16px;
      overflow-x: auto;
      margin-bottom: 16px;
      position: relative;
    }

    .doc-content pre code {
      background: none;
      border: none;
      padding: 0;
      font-size: 12.5px;
      line-height: 1.6;
    }

    /* Mermaid diagrams */
    .mermaid {
      background: var(--bg-secondary);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 24px;
      margin: 20px 0;
      text-align: center;
    }

    /* Blockquotes (used for notes/callouts) */
    .doc-content blockquote {
      border-left: 3px solid var(--accent);
      padding: 8px 16px;
      margin: 16px 0;
      background: color-mix(in srgb, var(--accent) 5%, transparent);
      border-radius: 0 4px 4px 0;
    }

    /* Tables */
    .doc-content table {
      width: 100%;
      border-collapse: collapse;
      margin: 16px 0;
      font-size: 13px;
    }

    .doc-content th, .doc-content td {
      padding: 8px 12px;
      border: 1px solid var(--border);
      text-align: left;
    }

    .doc-content th {
      background: var(--bg-secondary);
      font-weight: 600;
    }

    /* ════════════════════════════════════════════════
       Loading State
       ════════════════════════════════════════════════ */
    .loading {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 60vh;
      gap: 20px;
    }

    .loading-spinner {
      width: 40px;
      height: 40px;
      border: 3px solid var(--border);
      border-top: 3px solid var(--accent);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .loading-text {
      font-size: 14px;
      color: var(--text-secondary);
    }

    .loading-steps {
      list-style: none;
      font-size: 12px;
      color: var(--text-muted);
      text-align: center;
      line-height: 2;
    }

    .loading-steps .done { color: var(--success); }
    .loading-steps .active { color: var(--accent); }

    /* ════════════════════════════════════════════════
       Responsive
       ════════════════════════════════════════════════ */
    @media (max-width: 600px) {
      .toc { display: none; }
      .content { padding: 20px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <!-- Header with title, tabs, and action buttons -->
    <div class="header">
      <div class="header-top">
        <div class="header-title">
          <span class="icon">📄</span>
          ${repoName}
        </div>
        <div class="header-actions">
          <button class="header-btn" onclick="exportDoc('technical')" title="Export technical doc">
            ↓ Export Tech
          </button>
          <button class="header-btn" onclick="exportDoc('non-technical')" title="Export non-technical guide">
            ↓ Export Guide
          </button>
        </div>
      </div>

      <!-- Tab bar for switching between doc types -->
      <div class="tabs">
        <button class="tab active" data-tab="technical" onclick="switchTab('technical')">
          Technical Doc
          <span class="tab-badge">Engineers</span>
        </button>
        <button class="tab" data-tab="non-technical" onclick="switchTab('non-technical')">
          Non-Technical Guide
          <span class="tab-badge">Everyone</span>
        </button>
      </div>
    </div>

    <!-- Main area: TOC sidebar + document content -->
    <div class="main">
      <div class="toc" id="toc">
        <div class="toc-title">On This Page</div>
        <!-- TOC items are generated dynamically by JS -->
      </div>

      <div class="content" id="contentArea">
        ${isLoading ? `
          <div class="loading" id="loadingState">
            <div class="loading-spinner"></div>
            <div class="loading-text">Generating documentation...</div>
            <div class="loading-steps">
              <div class="active">⏳ Scanning repository files</div>
              <div>⏳ Analyzing code structure</div>
              <div>⏳ Understanding architecture (LLM)</div>
              <div>⏳ Writing technical documentation</div>
              <div>⏳ Writing non-technical guide</div>
            </div>
          </div>
        ` : `
          <div class="doc-content active" id="doc-technical">
            ${this.markdownToHTML(techDoc)}
          </div>
          <div class="doc-content" id="doc-non-technical">
            ${this.markdownToHTML(nonTechDoc)}
          </div>
        `}
      </div>
    </div>
  </div>

  <!-- Mermaid for diagram rendering -->
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>

  <script>
    // Initialize Mermaid with VS Code theme awareness
    const isDark = document.body.classList.contains('vscode-dark') ||
                   getComputedStyle(document.body).getPropertyValue('--vscode-editor-background').trim().startsWith('#1') ||
                   getComputedStyle(document.body).getPropertyValue('--vscode-editor-background').trim().startsWith('#0') ||
                   getComputedStyle(document.body).getPropertyValue('--vscode-editor-background').trim().startsWith('#2');

    mermaid.initialize({
      startOnLoad: true,
      theme: isDark ? 'dark' : 'default',
      securityLevel: 'loose',
    });

    // ── Raw markdown content (for export) ──
    const rawContent = {
      technical: ${JSON.stringify(escapedTech)},
      'non-technical': ${JSON.stringify(escapedNonTech)},
    };

    // ── Tab Switching ──
    let activeTab = 'technical';

    function switchTab(tab) {
      activeTab = tab;

      // Update tab buttons
      document.querySelectorAll('.tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === tab);
      });

      // Update doc content visibility
      document.querySelectorAll('.doc-content').forEach(d => {
        d.classList.toggle('active', d.id === 'doc-' + tab);
      });

      // Update TOC
      buildTOC(tab);
    }

    // ── Table of Contents ──
    function buildTOC(tab) {
      const toc = document.getElementById('toc');
      const doc = document.getElementById('doc-' + tab);
      if (!doc) return;

      const headings = doc.querySelectorAll('h2, h3');
      let html = '<div class="toc-title">On This Page</div>';

      headings.forEach((h, i) => {
        const id = 'heading-' + tab + '-' + i;
        h.id = id;
        const isH3 = h.tagName === 'H3';
        html += '<div class="toc-item' + (isH3 ? ' sub' : '') + '" '
              + 'onclick="scrollToHeading(\\'' + id + '\\')">'
              + h.textContent
              + '</div>';
      });

      toc.innerHTML = html;
    }

    function scrollToHeading(id) {
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }

      // Update active TOC item
      document.querySelectorAll('.toc-item').forEach(item => {
        item.classList.remove('active');
      });
      event.target.classList.add('active');
    }

    // ── Export ──
    const vscodeApi = acquireVsCodeApi();

    function exportDoc(type) {
      vscodeApi.postMessage({
        type: 'exportMarkdown',
        content: rawContent[type],
        filename: type === 'technical' ? 'TECHNICAL_DOC.md' : 'NON_TECHNICAL_GUIDE.md',
      });
    }

    // ── Handle progress messages from the extension ──
    window.addEventListener('message', event => {
      const msg = event.data;
      if (msg.type === 'progress') {
        const steps = document.querySelectorAll('.loading-steps div');
        if (steps.length > 0) {
          // Update step statuses based on the message
          const stepMap = {
            'scanning': 0,
            'analyzing': 1,
            'understanding': 2,
            'technical': 3,
            'non-technical': 4,
          };
          // Mark completed steps
          for (const [key, idx] of Object.entries(stepMap)) {
            if (msg.message.toLowerCase().includes(key)) {
              for (let i = 0; i < idx; i++) {
                steps[i].classList.remove('active');
                steps[i].classList.add('done');
                steps[i].textContent = '✓ ' + steps[i].textContent.replace(/^[⏳✓] /, '');
              }
              steps[idx].classList.add('active');
              steps[idx].textContent = '⏳ ' + steps[idx].textContent.replace(/^[⏳✓] /, '');
              break;
            }
          }
        }
      }
    });

    // ── Initialize TOC on load ──
    buildTOC('technical');

    // ── Scroll spy — highlight current section in TOC ──
    const contentArea = document.getElementById('contentArea');
    if (contentArea) {
      contentArea.addEventListener('scroll', () => {
        const headings = document.querySelectorAll('.doc-content.active h2, .doc-content.active h3');
        let activeId = '';

        headings.forEach(h => {
          const rect = h.getBoundingClientRect();
          if (rect.top <= 120) {
            activeId = h.id;
          }
        });

        if (activeId) {
          document.querySelectorAll('.toc-item').forEach(item => {
            const onclick = item.getAttribute('onclick') || '';
            item.classList.toggle('active', onclick.includes(activeId));
          });
        }
      });
    }
  </script>
</body>
</html>`;
  }

  /**
   * Convert markdown to basic HTML.
   *
   * This is a lightweight markdown parser — just enough to render
   * the documentation nicely. For a production extension, you'd use
   * a proper library like marked.js, but keeping it self-contained
   * avoids extra dependencies.
   */
  private markdownToHTML(markdown: string): string {
    if (!markdown) {
      return '<div class="loading"><div class="loading-spinner"></div><div class="loading-text">Generating...</div></div>';
    }

    let html = markdown
      // Escape HTML entities first (but preserve our own tags)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")

      // Mermaid code blocks — render as mermaid divs
      .replace(
        /```mermaid\n([\s\S]*?)```/g,
        '<div class="mermaid">$1</div>',
      )

      // Regular code blocks
      .replace(
        /```(\w*)\n([\s\S]*?)```/g,
        '<pre><code class="language-$1">$2</code></pre>',
      )

      // Inline code
      .replace(/`([^`]+)`/g, "<code>$1</code>")

      // Headers
      .replace(/^### (.+)$/gm, "<h3>$1</h3>")
      .replace(/^## (.+)$/gm, "<h2>$1</h2>")
      .replace(/^# (.+)$/gm, "<h1>$1</h1>")

      // Bold and italic
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/_(.+?)_/g, "<em>$1</em>")

      // Links
      .replace(
        /\[([^\]]+)\]\(([^)]+)\)/g,
        '<a href="$2">$1</a>',
      )

      // Unordered lists
      .replace(/^- (.+)$/gm, "<li>$1</li>")

      // Blockquotes
      .replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>")

      // Horizontal rules
      .replace(/^---$/gm, "<hr>")

      // Paragraphs (wrap remaining text lines)
      .replace(/^(?!<[hluobpd]|<\/|<li|<hr|<pre|<code|<div)(.*\S.*)$/gm, "<p>$1</p>");

    // Wrap consecutive <li> elements in <ul>
    html = html.replace(
      /(<li>[\s\S]*?<\/li>\n?)+/g,
      "<ul>$&</ul>",
    );

    return html;
  }

  private escapeForHTML(text: string): string {
    return text
      .replace(/\\/g, "\\\\")
      .replace(/'/g, "\\'")
      .replace(/"/g, '\\"')
      .replace(/\n/g, "\\n")
      .replace(/\r/g, "\\r");
  }
}
