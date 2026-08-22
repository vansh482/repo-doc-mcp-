import * as vscode from 'vscode';

export interface SidebarState {
  status: 'idle' | 'running' | 'done' | 'error';
  step?: string;
  elapsed?: number;
  branch?: string;
  error?: string;
  techUrl?: string;
  summaryUrl?: string;
}

export class SidebarProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = 'repoDocSidebar';
  private view?: vscode.WebviewView;
  private state: SidebarState = { status: 'idle' };

  constructor(private readonly extensionUri: vscode.Uri) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this.view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = this.getHtml();

    webviewView.webview.onDidReceiveMessage((message) => {
      switch (message.command) {
        case 'run':
          vscode.commands.executeCommand('repoDoc.run');
          break;
        case 'cancel':
          vscode.commands.executeCommand('repoDoc.cancel');
          break;
        case 'setup':
          vscode.commands.executeCommand('repoDoc.setup');
          break;
        case 'openUrl':
          vscode.env.openExternal(vscode.Uri.parse(message.url));
          break;
      }
    });
  }

  updateState(state: Partial<SidebarState>): void {
    this.state = { ...this.state, ...state };
    if (this.view) {
      this.view.webview.postMessage({ type: 'stateUpdate', state: this.state });
    }
  }

  private getHtml(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: var(--vscode-font-family);
    font-size: var(--vscode-font-size);
    color: var(--vscode-foreground);
    padding: 12px;
  }

  .section { margin-bottom: 16px; }
  .section-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--vscode-descriptionForeground);
    margin-bottom: 8px;
  }

  .btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    width: 100%;
    padding: 8px 12px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    transition: opacity 0.15s;
  }
  .btn:hover { opacity: 0.9; }
  .btn:active { opacity: 0.7; }

  .btn-primary {
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
  }
  .btn-secondary {
    background: var(--vscode-button-secondaryBackground);
    color: var(--vscode-button-secondaryForeground);
  }
  .btn-danger {
    background: var(--vscode-errorForeground);
    color: white;
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .status-card {
    background: var(--vscode-editor-background);
    border: 1px solid var(--vscode-widget-border);
    border-radius: 6px;
    padding: 12px;
  }

  .status-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }
  .status-row:last-child { margin-bottom: 0; }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .dot-idle { background: var(--vscode-descriptionForeground); }
  .dot-running { background: #f0b400; animation: pulse 1s infinite; }
  .dot-done { background: #4caf50; }
  .dot-error { background: var(--vscode-errorForeground); }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .progress-bar {
    width: 100%;
    height: 4px;
    background: var(--vscode-progressBar-background);
    border-radius: 2px;
    margin-top: 8px;
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    background: var(--vscode-button-background);
    border-radius: 2px;
    transition: width 0.3s ease;
  }

  .step-text {
    font-size: 12px;
    color: var(--vscode-descriptionForeground);
  }

  .elapsed {
    font-size: 11px;
    color: var(--vscode-descriptionForeground);
    margin-left: auto;
  }

  .links { margin-top: 8px; }
  .link-btn {
    display: block;
    padding: 6px 10px;
    margin-bottom: 4px;
    background: var(--vscode-textLink-foreground);
    color: var(--vscode-editor-background);
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    text-align: left;
    width: 100%;
  }
  .link-btn:hover { opacity: 0.85; }

  .error-text {
    font-size: 12px;
    color: var(--vscode-errorForeground);
    margin-top: 6px;
    word-break: break-word;
  }

  .branch-badge {
    display: inline-block;
    padding: 2px 8px;
    background: var(--vscode-badge-background);
    color: var(--vscode-badge-foreground);
    border-radius: 10px;
    font-size: 11px;
    font-weight: 500;
  }

  .hidden { display: none; }
  .mt-8 { margin-top: 8px; }
  .mt-12 { margin-top: 12px; }
</style>
</head>
<body>
  <div class="section">
    <div class="section-title">Generate Docs</div>
    <button class="btn btn-primary" id="runBtn" onclick="handleRun()">
      <span id="runIcon">&#9654;</span>
      <span id="runText">Generate Branch Docs</span>
    </button>
    <button class="btn btn-danger mt-8 hidden" id="cancelBtn" onclick="handleCancel()">
      &#9632; Cancel
    </button>
  </div>

  <div class="section">
    <div class="section-title">Status</div>
    <div class="status-card">
      <div class="status-row">
        <span class="status-dot dot-idle" id="statusDot"></span>
        <span id="statusLabel">Ready</span>
        <span class="elapsed hidden" id="elapsedTime"></span>
      </div>
      <div class="step-text hidden" id="stepText"></div>
      <div class="progress-bar hidden" id="progressBar">
        <div class="progress-fill" id="progressFill" style="width: 0%"></div>
      </div>
      <div class="error-text hidden" id="errorText"></div>
    </div>
  </div>

  <div class="section hidden" id="resultSection">
    <div class="section-title">Last Generated</div>
    <div class="status-card">
      <div class="status-row">
        <span id="branchBadge" class="branch-badge"></span>
      </div>
      <div class="links">
        <button class="link-btn" id="techLink" onclick="openTech()">Open Technical Doc</button>
        <button class="link-btn" id="summaryLink" onclick="openSummary()">Open Summary Doc</button>
      </div>
    </div>
  </div>

  <div class="section mt-12">
    <button class="btn btn-secondary" onclick="handleSetup()">
      &#9881; Settings
    </button>
  </div>

<script>
  const vscode = acquireVsCodeApi();
  let currentState = { status: 'idle' };

  function handleRun() { vscode.postMessage({ command: 'run' }); }
  function handleCancel() { vscode.postMessage({ command: 'cancel' }); }
  function handleSetup() { vscode.postMessage({ command: 'setup' }); }
  function openTech() { vscode.postMessage({ command: 'openUrl', url: currentState.techUrl }); }
  function openSummary() { vscode.postMessage({ command: 'openUrl', url: currentState.summaryUrl }); }

  function show(id) { document.getElementById(id).classList.remove('hidden'); }
  function hide(id) { document.getElementById(id).classList.add('hidden'); }

  window.addEventListener('message', (event) => {
    const msg = event.data;
    if (msg.type === 'stateUpdate') {
      currentState = msg.state;
      render(currentState);
    }
  });

  function render(state) {
    const runBtn = document.getElementById('runBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const statusDot = document.getElementById('statusDot');
    const statusLabel = document.getElementById('statusLabel');
    const elapsedTime = document.getElementById('elapsedTime');
    const stepText = document.getElementById('stepText');
    const progressBar = document.getElementById('progressBar');
    const progressFill = document.getElementById('progressFill');
    const errorText = document.getElementById('errorText');
    const resultSection = document.getElementById('resultSection');
    const branchBadge = document.getElementById('branchBadge');

    // Reset
    statusDot.className = 'status-dot';
    hide('errorText');

    switch (state.status) {
      case 'idle':
        statusDot.classList.add('dot-idle');
        statusLabel.textContent = 'Ready';
        runBtn.disabled = false;
        document.getElementById('runText').textContent = 'Generate Branch Docs';
        document.getElementById('runIcon').innerHTML = '&#9654;';
        cancelBtn.classList.add('hidden');
        hide('elapsedTime');
        hide('stepText');
        hide('progressBar');
        break;

      case 'running':
        statusDot.classList.add('dot-running');
        statusLabel.textContent = 'Generating...';
        runBtn.disabled = true;
        document.getElementById('runText').textContent = 'Running...';
        cancelBtn.classList.remove('hidden');
        if (state.step) {
          stepText.textContent = state.step;
          show('stepText');
        }
        if (state.elapsed !== undefined) {
          elapsedTime.textContent = state.elapsed + 's';
          show('elapsedTime');
        }
        show('progressBar');
        const stepNum = parseInt(state.step) || 0;
        const pct = Math.min(stepNum * 20, 95);
        progressFill.style.width = pct + '%';
        break;

      case 'done':
        statusDot.classList.add('dot-done');
        statusLabel.textContent = 'Complete!';
        runBtn.disabled = false;
        document.getElementById('runText').textContent = 'Re-generate Docs';
        document.getElementById('runIcon').innerHTML = '&#8635;';
        cancelBtn.classList.add('hidden');
        hide('stepText');
        if (state.elapsed !== undefined) {
          elapsedTime.textContent = state.elapsed + 's';
          show('elapsedTime');
        }
        progressFill.style.width = '100%';
        show('progressBar');
        if (state.techUrl || state.summaryUrl) {
          branchBadge.textContent = state.branch || 'branch';
          resultSection.classList.remove('hidden');
        }
        break;

      case 'error':
        statusDot.classList.add('dot-error');
        statusLabel.textContent = 'Failed';
        runBtn.disabled = false;
        document.getElementById('runText').textContent = 'Retry';
        document.getElementById('runIcon').innerHTML = '&#9654;';
        cancelBtn.classList.add('hidden');
        hide('progressBar');
        if (state.error) {
          errorText.textContent = state.error;
          show('errorText');
        }
        if (state.elapsed !== undefined) {
          elapsedTime.textContent = state.elapsed + 's';
          show('elapsedTime');
        }
        break;
    }
  }
</script>
</body>
</html>`;
  }
}
