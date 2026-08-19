import * as vscode from "vscode";
import { SecretStore } from "./secrets";

export interface RepoDocConfig {
  llm: {
    provider: "anthropic" | "openai" | "bedrock";
    model: string;
  };
  confluence: {
    baseUrl: string;
    spaceKey: string;
    parentPageId: string;
  };
  baseBranch: string;
  bedrock: {
    region: string;
    profile: string;
  };
}

export function getConfig(): RepoDocConfig {
  const cfg = vscode.workspace.getConfiguration("repoDoc");

  return {
    llm: {
      provider: cfg.get<"anthropic" | "openai" | "bedrock">("llm.provider") || "anthropic",
      model: cfg.get<string>("llm.model") || "claude-sonnet-4-20250514",
    },
    confluence: {
      baseUrl: cfg.get<string>("confluence.baseUrl") || "",
      spaceKey: cfg.get<string>("confluence.spaceKey") || "",
      parentPageId: cfg.get<string>("confluence.parentPageId") || "",
    },
    baseBranch: cfg.get<string>("baseBranch") || "main",
    bedrock: {
      region: cfg.get<string>("bedrock.region") || "us-west-2",
      profile: cfg.get<string>("bedrock.profile") || "",
    },
  };
}

export async function isConfigured(config: RepoDocConfig, secrets: SecretStore): Promise<boolean> {
  const cfg = vscode.workspace.getConfiguration("repoDoc");
  const hasConfluence =
    !!config.confluence.baseUrl &&
    !!config.confluence.spaceKey &&
    !!config.confluence.parentPageId &&
    !!((await secrets.getConfluenceToken()) || cfg.get<string>("confluence.apiToken")) &&
    !!((await secrets.getConfluenceEmail()) || cfg.get<string>("confluence.email"));

  if (!hasConfluence) {
    return false;
  }

  if (config.llm.provider === "bedrock") {
    return !!config.bedrock.profile;
  }

  const apiKey = await secrets.getApiKey(config.llm.provider);
  return !!apiKey;
}
