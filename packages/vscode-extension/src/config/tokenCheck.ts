import * as vscode from 'vscode';
import { SecretStore } from './secrets';

export interface TokenStatus {
  provider: string;
  valid: boolean;
  message: string;
}

export async function checkTokenHealth(
  provider: 'anthropic' | 'openai' | 'bedrock',
  secretStore: SecretStore
): Promise<TokenStatus> {
  if (provider === 'bedrock') {
    return { provider: 'bedrock', valid: true, message: 'Uses IAM — no token to check' };
  }

  const apiKey = await secretStore.getApiKey(provider);
  if (!apiKey) {
    return { provider, valid: false, message: 'No API key stored' };
  }

  try {
    if (provider === 'anthropic') {
      const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01',
          'content-type': 'application/json',
        },
        body: JSON.stringify({
          model: 'claude-sonnet-4-20250514',
          max_tokens: 1,
          messages: [{ role: 'user', content: 'test' }],
        }),
      });

      if (response.status === 401) {
        return { provider, valid: false, message: 'API key expired or revoked' };
      }
      if (response.status === 403) {
        return { provider, valid: false, message: 'API key lacks required permissions' };
      }
      return { provider, valid: true, message: 'OK' };
    }

    if (provider === 'openai') {
      const response = await fetch('https://api.openai.com/v1/models', {
        headers: { 'Authorization': `Bearer ${apiKey}` },
      });

      if (response.status === 401) {
        return { provider, valid: false, message: 'API key expired or revoked' };
      }
      return { provider, valid: true, message: 'OK' };
    }

    return { provider, valid: true, message: 'Unknown provider' };
  } catch (err: any) {
    return { provider, valid: true, message: `Cannot reach API (network issue): ${err.message}` };
  }
}

export async function promptForReauth(
  provider: string,
  message: string,
  secretStore: SecretStore
): Promise<boolean> {
  const action = await vscode.window.showWarningMessage(
    `${provider} credential issue: ${message}`,
    'Update Key',
    'Ignore'
  );

  if (action === 'Update Key') {
    const newKey = await vscode.window.showInputBox({
      prompt: `Enter your new ${provider} API key`,
      password: true,
      placeHolder: 'sk-...',
    });

    if (newKey) {
      await secretStore.setApiKey(provider as 'anthropic' | 'openai', newKey);
      vscode.window.showInformationMessage(`${provider} API key updated.`);
      return true;
    }
  }

  return false;
}
