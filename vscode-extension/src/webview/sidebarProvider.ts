import * as vscode from 'vscode';

export interface SidebarState {
  status: 'idle' | 'running' | 'done' | 'error';
  step?: string;
  elapsed?: number;
  branch?: string;
  baseBranch?: string;
  error?: string;
  techUrl?: string;
  summaryUrl?: string;
}

export class SidebarProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = 'repoDocSidebar';
  private view?: vscode.WebviewView;
  private state: SidebarState = { status: 'idle' };
  public customInstructions: string = '';
  public baseBranchOverride: string = '';
  public onDidResolve: (() => void) | undefined;

  constructor(private readonly extensionUri: vscode.Uri) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this.view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = this.getHtml();

    const currentBaseBranch = vscode.workspace.getConfiguration('repoDoc').get<string>('baseBranch') || '';
    this.baseBranchOverride = currentBaseBranch;
    webviewView.webview.postMessage({ type: 'initBaseBranch', value: currentBaseBranch });

    if (this.onDidResolve) {
      this.onDidResolve();
    }

    webviewView.webview.onDidReceiveMessage((message) => {
      switch (message.command) {
        case 'run':
          this.customInstructions = message.instructions || '';
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
        case 'setBaseBranch':
          this.baseBranchOverride = message.value || '';
          vscode.workspace.getConfiguration('repoDoc').update('baseBranch', message.value || undefined, vscode.ConfigurationTarget.Workspace);
          break;
        case 'openHistory':
          vscode.commands.executeCommand('repoDoc.viewDocs');
          break;
        case 'checkCredentials':
          vscode.commands.executeCommand('repoDoc.validateCredentials');
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

  sendHistory(history: Array<{ branch: string; lastUpdated: string }>): void {
    if (this.view) {
      this.view.webview.postMessage({ type: 'historyUpdate', history });
    }
  }

  sendCredStatus(status: { checking?: boolean; allOk?: boolean; summary?: string; details?: string[] }): void {
    if (this.view) {
      this.view.webview.postMessage({ type: 'credStatus', ...status });
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

  .instructions-textarea {
    width: 100%;
    min-height: 48px;
    max-height: 100px;
    padding: 8px;
    margin-top: 8px;
    border: 1px solid var(--vscode-input-border);
    background: var(--vscode-input-background);
    color: var(--vscode-input-foreground);
    font-family: var(--vscode-font-family);
    font-size: 12px;
    border-radius: 4px;
    resize: vertical;
  }
  .instructions-textarea::placeholder {
    color: var(--vscode-input-placeholderForeground);
  }
  .instructions-textarea:focus {
    outline: 1px solid var(--vscode-focusBorder);
    border-color: var(--vscode-focusBorder);
  }

  .base-branch-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 10px;
  }
  .base-branch-label {
    font-size: 11px;
    color: var(--vscode-descriptionForeground);
    white-space: nowrap;
  }
  .base-branch-input {
    flex: 1;
    padding: 4px 8px;
    border: 1px solid var(--vscode-input-border);
    background: var(--vscode-input-background);
    color: var(--vscode-input-foreground);
    font-family: var(--vscode-font-family);
    font-size: 12px;
    border-radius: 4px;
  }
  .base-branch-input::placeholder {
    color: var(--vscode-input-placeholderForeground);
  }
  .base-branch-input:focus {
    outline: 1px solid var(--vscode-focusBorder);
    border-color: var(--vscode-focusBorder);
  }

  .cred-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border: 1px solid var(--vscode-widget-border);
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.15s;
    margin-bottom: 8px;
  }
  .cred-indicator:hover { background: var(--vscode-list-hoverBackground); }
  .cred-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .cred-dot-green { background: #4caf50; }
  .cred-dot-red { background: var(--vscode-errorForeground); }
  .cred-dot-checking { background: #f0b400; animation: pulse 1s infinite; }
  .cred-dot-unknown { background: var(--vscode-descriptionForeground); }
  .cred-label { font-size: 11px; color: var(--vscode-descriptionForeground); }
  .cred-label-ok { color: #4caf50; }
  .cred-label-bad { color: var(--vscode-errorForeground); }

  .history-list { max-height: 200px; overflow-y: auto; }
  .history-item {
    padding: 8px;
    border: 1px solid var(--vscode-widget-border);
    border-radius: 4px;
    margin-bottom: 6px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .history-item:hover { background: var(--vscode-list-hoverBackground); }
  .history-branch { font-size: 12px; font-weight: 500; }
  .history-date { font-size: 10px; color: var(--vscode-descriptionForeground); margin-top: 2px; }

  .hidden { display: none; }
  .mt-8 { margin-top: 8px; }
  .mt-12 { margin-top: 12px; }
</style>
</head>
<body>
  <div class="section">
    <div class="section-title" style="display:flex;align-items:center;justify-content:space-between;">
      <span>Generate Docs</span>
      <span style="display:flex;align-items:center;gap:8px;">
        <span class="cred-dot cred-dot-unknown" id="credDot" onclick="handleCredCheck()" title="Click to check credentials" style="cursor:pointer;"></span>
        <span onclick="handleSetup()" style="cursor:pointer;font-size:14px;" title="Settings">&#9881;</span>
      </span>
    </div>
    <button class="btn btn-primary" id="runBtn" onclick="handleRun()">
      <span id="runIcon">&#9654;</span>
      <span id="runText">Generate Branch Docs</span>
    </button>
    <button class="btn btn-danger mt-8 hidden" id="cancelBtn" onclick="handleCancel()">
      &#9632; Cancel
    </button>
    <textarea
      id="instructions"
      class="instructions-textarea"
      placeholder="Optional: focus or formatting instructions (e.g. 'focus on API changes', 'use bullet points only')"
      maxlength="500"
      rows="2"
    ></textarea>
    <div class="base-branch-row">
      <span class="base-branch-label">Compare against:</span>
      <input
        type="text"
        id="baseBranch"
        class="base-branch-input"
        placeholder="detecting..."
        onchange="handleBaseBranchChange(this.value)"
      />
    </div>
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

  <div class="section" id="historySection">
    <div class="section-title">History</div>
    <div id="historyList" class="history-list"></div>
  </div>


<script>
  const vscode = acquireVsCodeApi();
  let currentState = { status: 'idle' };

  function handleRun() {
    const instructions = document.getElementById('instructions').value.trim();
    vscode.postMessage({ command: 'run', instructions });
  }
  function handleCancel() { vscode.postMessage({ command: 'cancel' }); }
  function handleSetup() { vscode.postMessage({ command: 'setup' }); }
  function handleBaseBranchChange(value) {
    vscode.postMessage({ command: 'setBaseBranch', value: value.trim() });
  }
  function openTech() { vscode.postMessage({ command: 'openUrl', url: currentState.techUrl }); }
  function openSummary() { vscode.postMessage({ command: 'openUrl', url: currentState.summaryUrl }); }

  function renderHistory(history) {
    const list = document.getElementById('historyList');
    if (!history || history.length === 0) {
      list.innerHTML = '<p style="font-size:11px;color:var(--vscode-descriptionForeground)">No docs generated yet</p>';
      return;
    }
    list.innerHTML = history.map(item => {
      const date = new Date(item.lastUpdated).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
      return '<div class="history-item" onclick="openHistory(\\'' + item.branch + '\\')">' +
        '<div class="history-branch">' + item.branch + '</div>' +
        '<div class="history-date">' + date + '</div>' +
      '</div>';
    }).join('');
  }
  function openHistory(branch) { vscode.postMessage({ command: 'openHistory', branch }); }

  function handleCredCheck() { vscode.postMessage({ command: 'checkCredentials' }); }

  function renderCredStatus(credStatus) {
    const dot = document.getElementById('credDot');
    dot.className = 'cred-dot';

    if (credStatus.checking) {
      dot.classList.add('cred-dot-checking');
      dot.title = 'Checking credentials...';
      return;
    }

    if (credStatus.allOk) {
      dot.classList.add('cred-dot-green');
    } else {
      dot.classList.add('cred-dot-red');
    }
    dot.title = (credStatus.details || []).join('\\n');
  }

  function show(id) { document.getElementById(id).classList.remove('hidden'); }
  function hide(id) { document.getElementById(id).classList.add('hidden'); }

  window.addEventListener('message', (event) => {
    const msg = event.data;
    if (msg.type === 'stateUpdate') {
      currentState = msg.state;
      render(currentState);
    }
    if (msg.type === 'historyUpdate') {
      renderHistory(msg.history);
    }
    if (msg.type === 'credStatus') {
      renderCredStatus(msg);
    }
    if (msg.type === 'initBaseBranch' && msg.value) {
      document.getElementById('baseBranch').value = msg.value;
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
    const baseBranchInput = document.getElementById('baseBranch');

    if (state.baseBranch && baseBranchInput) {
      baseBranchInput.placeholder = state.baseBranch;
    }

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
