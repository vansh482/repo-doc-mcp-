import * as vscode from "vscode";
import { SecretStore } from "./secrets";
import { getWizardHtml } from "./wizardHtml";

export async function runSetupWizard(secrets: SecretStore, extensionUri: vscode.Uri): Promise<boolean> {
  const panel = vscode.window.createWebviewPanel(
    "repoDocSetup",
    "Repo Doc Generator — Setup",
    vscode.ViewColumn.One,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  const cfg = vscode.workspace.getConfiguration("repoDoc");

  const hasApiKey = !!(await secrets.getApiKey((cfg.get<string>("llm.provider") || "anthropic") as "anthropic" | "openai"));
  const hasConfluenceToken = !!(await secrets.getConfluenceToken());

  const currentConfig = {
    provider: cfg.get<string>("llm.provider") || "anthropic",
    model: cfg.get<string>("llm.model") || "claude-sonnet-4-20250514",
    apiKey: "",
    hasApiKey,
    bedrockRegion: cfg.get<string>("bedrock.region") || "us-west-2",
    bedrockProfile: cfg.get<string>("bedrock.profile") || "",
    confluenceBaseUrl: cfg.get<string>("confluence.baseUrl") || "",
    confluenceEmail: cfg.get<string>("confluence.email") || "",
    confluenceApiToken: "",
    hasConfluenceToken,
    confluenceSpaceKey: cfg.get<string>("confluence.spaceKey") || "",
    confluenceParentPageId: cfg.get<string>("confluence.parentPageId") || "",
  };

  panel.webview.html = getWizardHtml(currentConfig);

  return new Promise<boolean>((resolve) => {
    let resolved = false;

    panel.onDidDispose(() => {
      if (!resolved) {
        resolved = true;
        resolve(false);
      }
    });

    panel.webview.onDidReceiveMessage(async (msg) => {
      if (msg.type === "cancel") {
        resolved = true;
        panel.dispose();
        resolve(false);
        return;
      }

      if (msg.type === "save") {
        const d = msg.data;

        try {
          await cfg.update("llm.provider", d.provider, vscode.ConfigurationTarget.Global);
          await cfg.update("llm.model", d.model, vscode.ConfigurationTarget.Global);
          await cfg.update("confluence.baseUrl", d.confluenceBaseUrl.replace(/\/$/, ""), vscode.ConfigurationTarget.Global);
          await cfg.update("confluence.spaceKey", d.confluenceSpaceKey, vscode.ConfigurationTarget.Global);
          await cfg.update("confluence.parentPageId", d.confluenceParentPageId, vscode.ConfigurationTarget.Global);

          if (d.confluenceEmail) {
            await cfg.update("confluence.email", d.confluenceEmail, vscode.ConfigurationTarget.Global);
            await secrets.setConfluenceEmail(d.confluenceEmail);
          }
          if (d.confluenceApiToken) {
            await secrets.setConfluenceToken(d.confluenceApiToken);
          }

          if (d.provider === "bedrock") {
            await cfg.update("bedrock.profile", d.bedrockProfile, vscode.ConfigurationTarget.Global);
            await cfg.update("bedrock.region", d.bedrockRegion, vscode.ConfigurationTarget.Global);
          } else if (d.apiKey) {
            await secrets.setApiKey(d.provider as "anthropic" | "openai", d.apiKey);
          }

          panel.webview.postMessage({ type: "saved" });
          vscode.window.showInformationMessage("Repo Doc Generator configured successfully!");
          resolved = true;
          setTimeout(() => panel.dispose(), 1500);
          resolve(true);
        } catch (err: any) {
          const errMsg = err?.message || String(err);
          panel.webview.postMessage({ type: "error", message: errMsg });
          vscode.window.showErrorMessage(`Failed to save configuration: ${errMsg}`);
        }
      }
    });
  });
}
