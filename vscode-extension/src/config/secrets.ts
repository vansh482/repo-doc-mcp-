import * as vscode from "vscode";

const KEYS = {
  anthropicApiKey: "repoDoc.apiKey.anthropic",
  openaiApiKey: "repoDoc.apiKey.openai",
  confluenceToken: "repoDoc.confluence.token",
  confluenceEmail: "repoDoc.confluence.email",
};

export class SecretStore {
  constructor(private secretStorage: vscode.SecretStorage) {}

  async getApiKey(provider: "anthropic" | "openai"): Promise<string | undefined> {
    const key = provider === "anthropic" ? KEYS.anthropicApiKey : KEYS.openaiApiKey;
    return this.secretStorage.get(key);
  }

  async setApiKey(provider: "anthropic" | "openai", value: string): Promise<void> {
    const key = provider === "anthropic" ? KEYS.anthropicApiKey : KEYS.openaiApiKey;
    await this.secretStorage.store(key, value);
  }

  async getConfluenceToken(): Promise<string | undefined> {
    return this.secretStorage.get(KEYS.confluenceToken);
  }

  async setConfluenceToken(token: string): Promise<void> {
    await this.secretStorage.store(KEYS.confluenceToken, token);
  }

  async getConfluenceEmail(): Promise<string | undefined> {
    return this.secretStorage.get(KEYS.confluenceEmail);
  }

  async setConfluenceEmail(email: string): Promise<void> {
    await this.secretStorage.store(KEYS.confluenceEmail, email);
  }

  async clearAll(): Promise<void> {
    await Promise.all(
      Object.values(KEYS).map((k) => this.secretStorage.delete(k))
    );
  }
}
