import * as vscode from "vscode";
import { SecretStore } from "./secrets";

export async function runSetupWizard(secrets: SecretStore): Promise<boolean> {
  // Step 1: LLM provider
  const provider = await vscode.window.showQuickPick(
    [
      { label: "Anthropic (Claude)", value: "anthropic" },
      { label: "OpenAI (GPT)", value: "openai" },
      { label: "AWS Bedrock", value: "bedrock" },
    ],
    { title: "Repo Doc Setup (1/7): Choose LLM Provider", placeHolder: "Select your LLM provider" }
  );
  if (!provider) { return false; }

  const cfg = vscode.workspace.getConfiguration("repoDoc");
  await cfg.update("llm.provider", provider.value, vscode.ConfigurationTarget.Global);

  // Step 2: LLM auth
  if (provider.value === "bedrock") {
    const profile = await vscode.window.showInputBox({
      title: "Repo Doc Setup (2/7): AWS Profile",
      prompt: "Enter your AWS SSO profile name (from ~/.aws/config)",
      placeHolder: "e.g., my-sso-profile",
    });
    if (profile === undefined) { return false; }
    await cfg.update("bedrock.profile", profile, vscode.ConfigurationTarget.Global);

    const region = await vscode.window.showInputBox({
      title: "Repo Doc Setup (2/7): AWS Region",
      prompt: "Enter the AWS region for Bedrock",
      value: "us-west-2",
    });
    if (region === undefined) { return false; }
    await cfg.update("bedrock.region", region, vscode.ConfigurationTarget.Global);
  } else {
    const keyPrompt = provider.value === "anthropic"
      ? "Enter your Anthropic API key (starts with sk-ant-...)"
      : "Enter your OpenAI API key (starts with sk-...)";

    const apiKey = await vscode.window.showInputBox({
      title: `Repo Doc Setup (2/7): ${provider.label} API Key`,
      prompt: keyPrompt,
      password: true,
      validateInput: (v) => v.trim() ? null : "API key cannot be empty",
    });
    if (apiKey === undefined) { return false; }
    await secrets.setApiKey(provider.value as "anthropic" | "openai", apiKey.trim());
  }

  // Step 3: Confluence base URL
  const baseUrl = await vscode.window.showInputBox({
    title: "Repo Doc Setup (3/7): Confluence Base URL",
    prompt: "Your Confluence instance URL",
    placeHolder: "https://yourcompany.atlassian.net/wiki",
    validateInput: (v) => {
      if (!v.trim()) { return "URL cannot be empty"; }
      if (!v.startsWith("http")) { return "URL must start with http:// or https://"; }
      return null;
    },
  });
  if (baseUrl === undefined) { return false; }
  await cfg.update("confluence.baseUrl", baseUrl.trim().replace(/\/$/, ""), vscode.ConfigurationTarget.Global);

  // Step 4: Confluence email
  const email = await vscode.window.showInputBox({
    title: "Repo Doc Setup (4/7): Confluence Email",
    prompt: "The email associated with your Atlassian account",
    placeHolder: "you@company.com",
    validateInput: (v) => v.includes("@") ? null : "Enter a valid email address",
  });
  if (email === undefined) { return false; }
  await secrets.setConfluenceEmail(email.trim());

  // Step 5: Confluence API token
  const token = await vscode.window.showInputBox({
    title: "Repo Doc Setup (5/7): Confluence API Token",
    prompt: "Generate one at https://id.atlassian.com/manage-profile/security/api-tokens",
    password: true,
    validateInput: (v) => v.trim() ? null : "Token cannot be empty",
  });
  if (token === undefined) { return false; }
  await secrets.setConfluenceToken(token.trim());

  // Step 6: Confluence space key
  const spaceKey = await vscode.window.showInputBox({
    title: "Repo Doc Setup (6/7): Confluence Space Key",
    prompt: "The space key where docs will be published (found in space settings or the URL)",
    placeHolder: "e.g., ENG, DOCS, TEAM",
    validateInput: (v) => v.trim() ? null : "Space key cannot be empty",
  });
  if (spaceKey === undefined) { return false; }
  await cfg.update("confluence.spaceKey", spaceKey.trim().toUpperCase(), vscode.ConfigurationTarget.Global);

  // Step 7: Parent page ID
  const parentPageId = await vscode.window.showInputBox({
    title: "Repo Doc Setup (7/7): Parent Page ID",
    prompt: "ID of the Confluence page under which docs will be created. Find it in the page URL: /pages/<ID>/page-title",
    placeHolder: "e.g., 123456789",
    validateInput: (v) => /^\d+$/.test(v.trim()) ? null : "Page ID must be a number",
  });
  if (parentPageId === undefined) { return false; }
  await cfg.update("confluence.parentPageId", parentPageId.trim(), vscode.ConfigurationTarget.Global);

  vscode.window.showInformationMessage("Repo Doc Generator configured successfully! Click 'Run' to generate docs.");
  return true;
}
