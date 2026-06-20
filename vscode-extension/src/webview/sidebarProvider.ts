/**
 * Sidebar View Provider — creates the sidebar panel in VS Code's activity bar.
 *
 * This provides a persistent "home base" for the extension in the sidebar.
 * Users can see their repo info, trigger doc generation, and check status
 * without needing to remember command palette commands.
 *
 * The sidebar shows:
 * - Current workspace/repo info
 * - Action buttons (Generate Docs, Summary, etc.)
 * - Current LLM configuration
 * - Links to generated docs
 */

import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";

export class SidebarProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "repoDocActions";

  private view?: vscode.WebviewView;
  private extensionUri: vscode.Uri;

  constructor(extensionUri: vscode.Uri) {
    this.extensionUri = extensionUri;
  }

  /**
   * Called by VS Code when the sidebar view needs to be created/shown.
   * This is the entry point — VS Code gives us a WebviewView and we
   * fill it with our HTML content.
   */
  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken,
  ): void {
    this.view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };

    webviewView.webview.html = this.getHTML();

    // Handle messages from the sidebar webview
    webviewView.webview.onDidReceiveMessage((message) => {
      switch (message.command) {
        case "generateDocs":
          vscode.commands.executeCommand("repoDoc.generateDocs");
          break;
        case "generateTechnical":
          vscode.commands.executeCommand("repoDoc.generateTechnicalDoc");
          break;
        case "generateNonTechnical":
          vscode.commands.executeCommand("repoDoc.generateNonTechnicalDoc");
          break;
        case "showSummary":
          vscode.commands.executeCommand("repoDoc.showRepoSummary");
          break;
        case "openSettings":
          vscode.commands.executeCommand("repoDoc.openSettings");
          break;
        case "viewLastDoc":
          vscode.commands.executeCommand("repoDoc.viewLastDoc");
          break;
      }
    });
  }

  /**
   * Update the sidebar to show new status information.
   * Called after doc generation completes, for example.
   */
  public updateStatus(status: {
    state: "idle" | "generating" | "done" | "error";
    message?: string;
    lastGenerated?: string;
  }): void {
    if (this.view) {
      this.view.webview.postMessage({
        type: "statusUpdate",
        ...status,
      });
    }
  }

  /**
   * Build the sidebar HTML.
   *
   * The sidebar is intentionally simple — just action buttons and status.
   * All the heavy rendering happens in the main DocViewer panel.
   */
  private getHTML(): string {
    const config = vscode.workspace.getConfiguration("repoDoc");
    const provider = config.get<string>("llm.provider") || "anthropic";
    const model = config.get<string>("llm.model") || "claude-sonnet-4-20250514";

    // Get workspace name
    const workspaceName =
      vscode.workspace.workspaceFolders?.[0]?.name || "No workspace";

    // Check if docs already exist
    const workspacePath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    const outputDir = config.get<string>("output.directory") || "./docs/generated";
    let docsExist = false;
    if (workspacePath) {
      const fullOutputPath = path.isAbsolute(outputDir)
        ? outputDir
        : path.join(workspacePath, outputDir);
      docsExist = fs.existsSync(path.join(fullOutputPath, "TECHNICAL_DOC.md"));
    }

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: var(--vscode-font-family, -apple-system, sans-serif);
      font-size: 12px;
      color: var(--vscode-foreground);
      padding: 12px;
    }

    .section {
      margin-bottom: 20px;
    }

    .section-title {
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--vscode-descriptionForeground);
      margin-bottom: 8px;
    }

    .info-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 0;
      font-size: 11px;
    }

    .info-label { color: var(--vscode-descriptionForeground); }
    .info-value { color: var(--vscode-foreground); font-weight: 500; }

    .btn {
      display: flex;
      align-items: center;
      gap: 6px;
      width: 100%;
      padding: 8px 12px;
      margin-bottom: 4px;
      border: none;
      border-radius: 4px;
      font-size: 12px;
      font-family: var(--vscode-font-family);
      cursor: pointer;
      transition: opacity 0.15s ease;
    }

    .btn:hover { opacity: 0.85; }

    .btn-primary {
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
    }

    .btn-secondary {
      background: var(--vscode-button-secondaryBackground);
      color: var(--vscode-button-secondaryForeground);
    }

    .btn-icon { font-size: 14px; }

    .status-bar {
      padding: 8px;
      border-radius: 4px;
      font-size: 11px;
      margin-bottom: 8px;
    }

    .status-idle {
      background: color-mix(in srgb, var(--vscode-descriptionForeground) 10%, transparent);
      color: var(--vscode-descriptionForeground);
    }

    .status-generating {
      background: color-mix(in srgb, var(--vscode-textLink-foreground) 15%, transparent);
      color: var(--vscode-textLink-foreground);
    }

    .status-done {
      background: color-mix(in srgb, var(--vscode-testing-iconPassed) 15%, transparent);
      color: var(--vscode-testing-iconPassed, #89d185);
    }

    .status-error {
      background: color-mix(in srgb, var(--vscode-errorForeground) 15%, transparent);
      color: var(--vscode-errorForeground);
    }

    .divider {
      border: none;
      border-top: 1px solid var(--vscode-panel-border);
      margin: 16px 0;
    }

    .kbd {
      background: var(--vscode-keybindingLabel-background, #333);
      border: 1px solid var(--vscode-keybindingLabel-border, #555);
      border-radius: 3px;
      padding: 1px 4px;
      font-size: 10px;
      font-family: var(--vscode-editor-font-family, monospace);
    }
  </style>
</head>
<body>
  <!-- Status indicator -->
  <div class="section">
    <div class="status-bar status-idle" id="statusBar">
      ${docsExist ? "✓ Documentation available" : "Ready to generate"}
    </div>
  </div>

  <!-- Workspace info -->
  <div class="section">
    <div class="section-title">Workspace</div>
    <div class="info-row">
      <span class="info-label">Repository</span>
      <span class="info-value">${workspaceName}</span>
    </div>
    <div class="info-row">
      <span class="info-label">LLM</span>
      <span class="info-value">${provider}</span>
    </div>
    <div class="info-row">
      <span class="info-label">Model</span>
      <span class="info-value" style="font-size:10px">${model}</span>
    </div>
  </div>

  <hr class="divider">

  <!-- Action buttons -->
  <div class="section">
    <div class="section-title">Generate</div>
    <button class="btn btn-primary" onclick="send('generateDocs')">
      <span class="btn-icon">📄</span>
      Generate Both Docs
      <span style="margin-left:auto"><span class="kbd">⌘⇧D</span></span>
    </button>
    <button class="btn btn-secondary" onclick="send('generateTechnical')">
      <span class="btn-icon">⚙️</span>
      Technical Doc Only
    </button>
    <button class="btn btn-secondary" onclick="send('generateNonTechnical')">
      <span class="btn-icon">👤</span>
      Non-Technical Guide Only
    </button>
  </div>

  <hr class="divider">

  <!-- Quick actions -->
  <div class="section">
    <div class="section-title">Quick Actions</div>
    <button class="btn btn-secondary" onclick="send('showSummary')">
      <span class="btn-icon">📊</span>
      Repo Summary (No AI)
    </button>
    ${docsExist ? `
    <button class="btn btn-secondary" onclick="send('viewLastDoc')">
      <span class="btn-icon">👁️</span>
      View Last Generated Docs
    </button>
    ` : ""}
    <button class="btn btn-secondary" onclick="send('openSettings')">
      <span class="btn-icon">⚙️</span>
      Settings
    </button>
  </div>

  <script>
    const vscodeApi = acquireVsCodeApi();

    function send(command) {
      vscodeApi.postMessage({ command });
    }

    // Handle status updates from the extension
    window.addEventListener('message', event => {
      const msg = event.data;
      if (msg.type === 'statusUpdate') {
        const bar = document.getElementById('statusBar');
        bar.className = 'status-bar status-' + msg.state;

        switch(msg.state) {
          case 'generating':
            bar.textContent = '⏳ ' + (msg.message || 'Generating documentation...');
            break;
          case 'done':
            bar.textContent = '✓ ' + (msg.message || 'Documentation generated!');
            break;
          case 'error':
            bar.textContent = '✗ ' + (msg.message || 'Generation failed');
            break;
          default:
            bar.textContent = 'Ready to generate';
        }
      }
    });
  </script>
</body>
</html>`;
  }
}
