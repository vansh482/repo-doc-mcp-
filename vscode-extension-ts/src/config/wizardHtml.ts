export interface WizardConfig {
  provider: string;
  model: string;
  apiKey: string;
  bedrockRegion: string;
  bedrockProfile: string;
  confluenceBaseUrl: string;
  confluenceEmail: string;
  confluenceApiToken: string;
  confluenceSpaceKey: string;
  confluenceParentPageId: string;
}

export function getWizardHtml(current: Partial<WizardConfig>): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Repo Doc Generator — Setup</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: var(--vscode-font-family, -apple-system, BlinkMacSystemFont, sans-serif);
    font-size: var(--vscode-font-size, 13px);
    color: var(--vscode-foreground, #ccc);
    background: var(--vscode-editor-background, #1e1e1e);
    padding: 24px 32px;
    line-height: 1.5;
  }
  h1 {
    font-size: 1.4em;
    font-weight: 600;
    margin-bottom: 4px;
    color: var(--vscode-foreground, #eee);
  }
  .subtitle {
    color: var(--vscode-descriptionForeground, #888);
    margin-bottom: 24px;
  }
  .section {
    margin-bottom: 28px;
    border: 1px solid var(--vscode-panel-border, #333);
    border-radius: 6px;
    padding: 20px;
    background: var(--vscode-editor-background, #1e1e1e);
  }
  .section-title {
    font-size: 1.1em;
    font-weight: 600;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--vscode-panel-border, #333);
  }
  .field {
    margin-bottom: 16px;
  }
  .field:last-child { margin-bottom: 0; }
  label {
    display: block;
    font-weight: 500;
    margin-bottom: 4px;
    color: var(--vscode-foreground, #ccc);
  }
  .hint {
    font-size: 0.9em;
    color: var(--vscode-descriptionForeground, #888);
    margin-bottom: 6px;
  }
  input, select {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid var(--vscode-input-border, #444);
    background: var(--vscode-input-background, #2d2d2d);
    color: var(--vscode-input-foreground, #eee);
    border-radius: 4px;
    font-size: 13px;
    font-family: inherit;
    outline: none;
  }
  input:focus, select:focus {
    border-color: var(--vscode-focusBorder, #007acc);
  }
  input::placeholder {
    color: var(--vscode-input-placeholderForeground, #666);
  }
  .row {
    display: flex;
    gap: 12px;
  }
  .row .field { flex: 1; }
  .hidden { display: none; }
  .actions {
    display: flex;
    gap: 12px;
    margin-top: 24px;
  }
  button {
    padding: 10px 24px;
    border: none;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
  }
  .btn-primary {
    background: var(--vscode-button-background, #007acc);
    color: var(--vscode-button-foreground, #fff);
  }
  .btn-primary:hover {
    background: var(--vscode-button-hoverBackground, #005a9e);
  }
  .btn-secondary {
    background: var(--vscode-button-secondaryBackground, #3a3d41);
    color: var(--vscode-button-secondaryForeground, #ccc);
  }
  .btn-secondary:hover {
    background: var(--vscode-button-secondaryHoverBackground, #4a4d51);
  }
  .error {
    color: var(--vscode-errorForeground, #f44);
    font-size: 0.9em;
    margin-top: 8px;
    display: none;
  }
  .error.visible { display: block; }
  .success-msg {
    background: var(--vscode-testing-iconPassed, #28a745);
    color: #fff;
    padding: 12px 16px;
    border-radius: 4px;
    margin-top: 16px;
    display: none;
    font-weight: 500;
  }
  .success-msg.visible { display: block; }
</style>
</head>
<body>
  <h1>Repo Doc Generator — Setup</h1>
  <p class="subtitle">Configure your LLM provider and Confluence publishing. All fields stay visible — switch windows freely to look up values.</p>

  <div class="section">
    <div class="section-title">LLM Provider</div>

    <div class="field">
      <label for="provider">Provider</label>
      <select id="provider">
        <option value="anthropic" ${current.provider === 'anthropic' ? 'selected' : ''}>Anthropic (Claude)</option>
        <option value="openai" ${current.provider === 'openai' ? 'selected' : ''}>OpenAI (GPT)</option>
        <option value="bedrock" ${current.provider === 'bedrock' ? 'selected' : ''}>AWS Bedrock</option>
      </select>
    </div>

    <div class="field">
      <label for="model">Model</label>
      <div class="hint">e.g., claude-sonnet-4-20250514, gpt-4o, or a Bedrock ARN</div>
      <input type="text" id="model" value="${escapeHtml(current.model || 'claude-sonnet-4-20250514')}" placeholder="claude-sonnet-4-20250514" />
    </div>

    <div class="field" id="apiKeyField">
      <label for="apiKey">API Key</label>
      <div class="hint" id="apiKeyHint">Your Anthropic API key (starts with sk-ant-...)</div>
      <input type="password" id="apiKey" value="${escapeHtml(current.apiKey || '')}" placeholder="sk-ant-..." />
    </div>

    <div class="row hidden" id="bedrockFields">
      <div class="field">
        <label for="bedrockProfile">AWS Profile</label>
        <div class="hint">From ~/.aws/config</div>
        <input type="text" id="bedrockProfile" value="${escapeHtml(current.bedrockProfile || '')}" placeholder="my-sso-profile" />
      </div>
      <div class="field">
        <label for="bedrockRegion">AWS Region</label>
        <input type="text" id="bedrockRegion" value="${escapeHtml(current.bedrockRegion || 'us-west-2')}" placeholder="us-west-2" />
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Confluence Publishing</div>

    <div class="field">
      <label for="confluenceBaseUrl">Base URL</label>
      <div class="hint">Your Confluence instance URL</div>
      <input type="text" id="confluenceBaseUrl" value="${escapeHtml(current.confluenceBaseUrl || '')}" placeholder="https://yourcompany.atlassian.net/wiki" />
    </div>

    <div class="row">
      <div class="field">
        <label for="confluenceEmail">Email</label>
        <input type="email" id="confluenceEmail" value="${escapeHtml(current.confluenceEmail || '')}" placeholder="you@company.com" />
      </div>
      <div class="field">
        <label for="confluenceApiToken">API Token</label>
        <div class="hint"><a href="https://id.atlassian.com/manage-profile/security/api-tokens" style="color:var(--vscode-textLink-foreground,#3794ff)">Generate one here</a></div>
        <input type="password" id="confluenceApiToken" value="${escapeHtml(current.confluenceApiToken || '')}" placeholder="Your Confluence API token" />
      </div>
    </div>

    <div class="row">
      <div class="field">
        <label for="confluenceSpaceKey">Space Key</label>
        <div class="hint">Found in space settings or the URL</div>
        <input type="text" id="confluenceSpaceKey" value="${escapeHtml(current.confluenceSpaceKey || '')}" placeholder="ENG or ~personalkey" />
      </div>
      <div class="field">
        <label for="confluenceParentPageId">Parent Page ID</label>
        <div class="hint">ID from the page URL: /pages/&lt;ID&gt;/title</div>
        <input type="text" id="confluenceParentPageId" value="${escapeHtml(current.confluenceParentPageId || '')}" placeholder="123456789" />
      </div>
    </div>
  </div>

  <div class="error" id="errorMsg"></div>
  <div class="success-msg" id="successMsg">Configuration saved successfully!</div>

  <div class="actions">
    <button class="btn-primary" id="saveBtn">Save Configuration</button>
    <button class="btn-secondary" id="cancelBtn">Cancel</button>
  </div>

  <script>
    const vscode = acquireVsCodeApi();

    const providerSelect = document.getElementById('provider');
    const apiKeyField = document.getElementById('apiKeyField');
    const apiKeyHint = document.getElementById('apiKeyHint');
    const apiKeyInput = document.getElementById('apiKey');
    const bedrockFields = document.getElementById('bedrockFields');
    const errorMsg = document.getElementById('errorMsg');
    const successMsg = document.getElementById('successMsg');

    function updateProviderFields() {
      const provider = providerSelect.value;
      if (provider === 'bedrock') {
        apiKeyField.classList.add('hidden');
        bedrockFields.classList.remove('hidden');
      } else {
        apiKeyField.classList.remove('hidden');
        bedrockFields.classList.add('hidden');
        if (provider === 'anthropic') {
          apiKeyHint.textContent = 'Your Anthropic API key (starts with sk-ant-...)';
          apiKeyInput.placeholder = 'sk-ant-...';
        } else {
          apiKeyHint.textContent = 'Your OpenAI API key (starts with sk-...)';
          apiKeyInput.placeholder = 'sk-...';
        }
      }
    }

    providerSelect.addEventListener('change', updateProviderFields);
    updateProviderFields();

    document.getElementById('saveBtn').addEventListener('click', () => {
      const provider = providerSelect.value;
      const model = document.getElementById('model').value.trim();
      const apiKey = document.getElementById('apiKey').value.trim();
      const bedrockProfile = document.getElementById('bedrockProfile').value.trim();
      const bedrockRegion = document.getElementById('bedrockRegion').value.trim();
      const confluenceBaseUrl = document.getElementById('confluenceBaseUrl').value.trim();
      const confluenceEmail = document.getElementById('confluenceEmail').value.trim();
      const confluenceApiToken = document.getElementById('confluenceApiToken').value.trim();
      const confluenceSpaceKey = document.getElementById('confluenceSpaceKey').value.trim();
      const confluenceParentPageId = document.getElementById('confluenceParentPageId').value.trim();

      // Validate
      const errors = [];
      if (!model) errors.push('Model is required');
      if (provider !== 'bedrock' && !apiKey) errors.push('API key is required');
      if (provider === 'bedrock' && !bedrockProfile) errors.push('AWS profile is required');
      if (provider === 'bedrock' && !bedrockRegion) errors.push('AWS region is required');
      if (!confluenceBaseUrl) errors.push('Confluence base URL is required');
      if (!confluenceEmail) errors.push('Confluence email is required');
      if (!confluenceApiToken) errors.push('Confluence API token is required');
      if (!confluenceSpaceKey) errors.push('Confluence space key is required');
      if (!confluenceParentPageId) errors.push('Parent page ID is required');

      if (errors.length > 0) {
        errorMsg.textContent = errors.join('. ');
        errorMsg.classList.add('visible');
        successMsg.classList.remove('visible');
        return;
      }

      errorMsg.classList.remove('visible');

      vscode.postMessage({
        type: 'save',
        data: {
          provider,
          model,
          apiKey,
          bedrockProfile,
          bedrockRegion,
          confluenceBaseUrl,
          confluenceEmail,
          confluenceApiToken,
          confluenceSpaceKey,
          confluenceParentPageId,
        }
      });
    });

    document.getElementById('cancelBtn').addEventListener('click', () => {
      vscode.postMessage({ type: 'cancel' });
    });

    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg.type === 'saved') {
        successMsg.classList.add('visible');
        errorMsg.classList.remove('visible');
      }
    });
  </script>
</body>
</html>`;
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
