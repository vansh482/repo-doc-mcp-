/**
 * MCP Client — communicates with the repo-doc-mcp Python server.
 *
 * HOW MCP COMMUNICATION WORKS:
 * ┌────────────┐  stdin (JSON-RPC)  ┌──────────────┐
 * │  VS Code   │ ─────────────────> │  Python MCP  │
 * │  Extension │ <───────────────── │  Server      │
 * └────────────┘  stdout (JSON-RPC) └──────────────┘
 *
 * The extension spawns the Python server as a child process.
 * Communication happens via JSON-RPC 2.0 over stdin/stdout.
 * Each tool call is a JSON-RPC request; the response contains the result.
 *
 * We also support a "direct mode" where the extension calls the Python
 * CLI directly (no persistent server process) for simpler setups.
 */

import * as vscode from "vscode";
import * as cp from "child_process";
import * as path from "path";

// ──────────────────────────────────────────────────────────────────────
// Types for MCP communication
// ──────────────────────────────────────────────────────────────────────

export interface MCPToolResult {
  success: boolean;
  content: string;
  error?: string;
}

export interface MCPServerConfig {
  pythonPath: string;
  serverPath: string;
  env: Record<string, string>;
}

// ──────────────────────────────────────────────────────────────────────
// MCP Client Implementation
// ──────────────────────────────────────────────────────────────────────

export class MCPClient {
  private config: MCPServerConfig;
  private outputChannel: vscode.OutputChannel;

  constructor(
    config: MCPServerConfig,
    outputChannel: vscode.OutputChannel,
  ) {
    this.config = config;
    this.outputChannel = outputChannel;
  }

  /**
   * Call an MCP tool by executing the Python CLI directly.
   *
   * WHY CLI MODE INSTEAD OF PERSISTENT SERVER?
   * For Phase 2, we use a simpler approach: each tool call spawns a Python
   * process, runs the operation, and exits. This is easier to debug, doesn't
   * require managing a long-running server process, and works reliably across
   * all platforms. The tradeoff is ~1-2s startup overhead per call, which is
   * negligible compared to the LLM API call time (10-60s).
   *
   * In a future phase, we could switch to a persistent MCP server connection
   * for faster back-to-back operations.
   */
  async callTool(
    toolName: string,
    args: Record<string, string>,
    cancellationToken?: vscode.CancellationToken,
  ): Promise<MCPToolResult> {
    return new Promise((resolve, reject) => {
      // Build the Python command. We use the CLI module which accepts
      // arguments and runs the same pipeline as the MCP server tools.
      const cliArgs = this.buildCliArgs(toolName, args);

      this.outputChannel.appendLine(
        `[MCP] Calling tool: ${toolName} with args: ${JSON.stringify(args)}`,
      );
      this.outputChannel.appendLine(
        `[MCP] Command: ${this.config.pythonPath} ${cliArgs.join(" ")}`,
      );

      const process = cp.spawn(this.config.pythonPath, cliArgs, {
        cwd: this.config.serverPath,
        env: { ...global.process.env, ...this.config.env },
        stdio: ["pipe", "pipe", "pipe"],
      });

      let stdout = "";
      let stderr = "";

      process.stdout.on("data", (data: Buffer) => {
        const chunk = data.toString();
        stdout += chunk;
        // Stream progress to the output channel in real-time
        this.outputChannel.append(chunk);
      });

      process.stderr.on("data", (data: Buffer) => {
        const chunk = data.toString();
        stderr += chunk;
        this.outputChannel.append(`[STDERR] ${chunk}`);
      });

      // Handle cancellation — kill the Python process if user cancels
      if (cancellationToken) {
        cancellationToken.onCancellationRequested(() => {
          process.kill("SIGTERM");
          resolve({
            success: false,
            content: "",
            error: "Operation cancelled by user",
          });
        });
      }

      process.on("close", (code: number | null) => {
        if (code === 0) {
          resolve({ success: true, content: stdout.trim() });
        } else {
          resolve({
            success: false,
            content: stdout.trim(),
            error: stderr.trim() || `Process exited with code ${code}`,
          });
        }
      });

      process.on("error", (err: Error) => {
        this.outputChannel.appendLine(`[MCP] Process error: ${err.message}`);
        resolve({
          success: false,
          content: "",
          error: `Failed to start MCP server: ${err.message}`,
        });
      });
    });
  }

  /**
   * Build CLI arguments based on the tool being called.
   *
   * We map MCP tool names to CLI arguments:
   *   generate_docs          → python -m src.cli <path> --type both
   *   generate_technical_doc → python -m src.cli <path> --type technical
   *   generate_non_technical_doc → python -m src.cli <path> --type non-technical
   *   get_repo_summary       → python -m src.cli <path> --summary-only
   */
  private buildCliArgs(
    toolName: string,
    args: Record<string, string>,
  ): string[] {
    const repoPath = args.repo_path || args.repoPath || ".";
    const baseArgs = ["-m", "src.cli", repoPath];

    // Add provider/model from VS Code settings
    const config = vscode.workspace.getConfiguration("repoDoc");
    const provider = config.get<string>("llm.provider");
    const model = config.get<string>("llm.model");
    const apiKey = config.get<string>("llm.apiKey");
    const outputDir = config.get<string>("output.directory");

    if (provider) {
      baseArgs.push("--provider", provider);
    }
    if (model) {
      baseArgs.push("--model", model);
    }
    if (apiKey) {
      baseArgs.push("--api-key", apiKey);
    }
    if (outputDir) {
      baseArgs.push("--output", outputDir);
    }

    // Map tool names to CLI flags
    switch (toolName) {
      case "generate_docs":
        return [...baseArgs, "--type", "both"];
      case "generate_technical_doc":
        return [...baseArgs, "--type", "technical"];
      case "generate_non_technical_doc":
        return [...baseArgs, "--type", "non-technical"];
      case "get_repo_summary":
        return [...baseArgs, "--summary-only"];
      case "check_and_update_docs": {
        const watcherArgs = ["-m", "src.watcher.cli", "check", "--repo-path", repoPath];
        if (provider) { watcherArgs.push("--provider", provider); }
        if (model) { watcherArgs.push("--model", model); }
        return watcherArgs;
      }
      case "generate_branch_docs": {
        const branch = args.branch || "";
        const branchArgs = [
          "-m", "src.watcher.cli", "branch-docs", branch,
          "--repo-path", repoPath,
        ];
        if (args.base_branch) { branchArgs.push("--base", args.base_branch); }
        if (provider) { branchArgs.push("--provider", provider); }
        if (model) { branchArgs.push("--model", model); }
        return branchArgs;
      }
      default:
        return baseArgs;
    }
  }

  /**
   * Check if the MCP server is installed and accessible.
   * Returns a helpful error message if something is wrong.
   */
  async healthCheck(): Promise<{ ok: boolean; message: string }> {
    try {
      // Check if Python is available
      const pythonCheck = cp.spawnSync(this.config.pythonPath, ["--version"], {
        timeout: 5000,
      });
      if (pythonCheck.status !== 0) {
        return {
          ok: false,
          message: `Python not found at '${this.config.pythonPath}'. Please install Python 3.10+ or update the 'repoDoc.pythonPath' setting.`,
        };
      }

      // Check if the MCP server module is importable
      const importCheck = cp.spawnSync(
        this.config.pythonPath,
        ["-c", "from src.config.settings import ServerConfig; print('OK')"],
        { cwd: this.config.serverPath, timeout: 10000 },
      );
      if (importCheck.status !== 0) {
        const error = importCheck.stderr?.toString() || "Unknown error";
        return {
          ok: false,
          message: `MCP server not properly installed at '${this.config.serverPath}'. Run 'pip install -e .' in the server directory.\n\nError: ${error}`,
        };
      }

      return { ok: true, message: "MCP server is ready" };
    } catch (err: any) {
      return {
        ok: false,
        message: `Health check failed: ${err.message}`,
      };
    }
  }
}

/**
 * Create an MCPClient from VS Code settings.
 *
 * This reads the user's configuration and constructs the client
 * with the right paths and environment variables.
 */
export function createMCPClient(
  outputChannel: vscode.OutputChannel,
): MCPClient {
  const config = vscode.workspace.getConfiguration("repoDoc");

  const pythonPath = config.get<string>("pythonPath") || "python3";
  const serverPath = config.get<string>("mcpServerPath") || "";

  // Build environment variables for the Python process
  const env: Record<string, string> = {};
  const apiKey = config.get<string>("llm.apiKey");
  const provider = config.get<string>("llm.provider") || "anthropic";

  if (apiKey) {
    // Set the appropriate env var based on provider
    if (provider === "anthropic") {
      env["ANTHROPIC_API_KEY"] = apiKey;
    } else if (provider === "openai") {
      env["OPENAI_API_KEY"] = apiKey;
    }
  }

  return new MCPClient(
    { pythonPath, serverPath, env },
    outputChannel,
  );
}
