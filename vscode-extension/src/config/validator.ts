export interface ValidationResult {
  valid: boolean;
  error?: string;
}

export async function validateConfluenceCredentials(
  baseUrl: string,
  email: string,
  apiToken: string
): Promise<ValidationResult> {
  try {
    const auth = 'Basic ' + Buffer.from(`${email}:${apiToken}`).toString('base64');
    const response = await fetch(`${baseUrl}/rest/api/user/current`, {
      headers: {
        'Authorization': auth,
        'Accept': 'application/json',
      },
    });

    if (response.ok) {
      return { valid: true };
    }

    if (response.status === 401) {
      return { valid: false, error: 'Invalid credentials — check email and API token' };
    }

    return { valid: false, error: `Confluence returned status ${response.status}` };
  } catch (err: any) {
    return { valid: false, error: `Cannot reach Confluence: ${err.message}` };
  }
}

export async function validateAnthropicKey(apiKey: string): Promise<ValidationResult> {
  try {
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
        messages: [{ role: 'user', content: 'hi' }],
      }),
    });

    if (response.ok || response.status === 200) {
      return { valid: true };
    }
    if (response.status === 401) {
      return { valid: false, error: 'Invalid Anthropic API key' };
    }
    // 400 means key is valid but request was bad (which is fine for validation)
    if (response.status === 400) {
      return { valid: true };
    }
    return { valid: false, error: `Anthropic API returned status ${response.status}` };
  } catch (err: any) {
    return { valid: false, error: `Cannot reach Anthropic API: ${err.message}` };
  }
}

export async function validateOpenAIKey(apiKey: string): Promise<ValidationResult> {
  try {
    const response = await fetch('https://api.openai.com/v1/models', {
      headers: {
        'Authorization': `Bearer ${apiKey}`,
      },
    });

    if (response.ok) {
      return { valid: true };
    }
    if (response.status === 401) {
      return { valid: false, error: 'Invalid OpenAI API key' };
    }
    return { valid: false, error: `OpenAI API returned status ${response.status}` };
  } catch (err: any) {
    return { valid: false, error: `Cannot reach OpenAI API: ${err.message}` };
  }
}
