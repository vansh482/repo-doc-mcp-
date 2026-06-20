/**
 * Extension Entry Point — the "main()" of the VS Code extension.
 *
 * When VS Code loads this extension, it calls the `activate()` function below.
 * That function registers all commands, sets up the sidebar, creates the MCP client,
 * and wires everything together.
 *
 * ARCHITECTURE:
 *
 *   User Action (command palette / keyboard shortcut / sidebar button)
 *        │
 *        ▼
 *   Command Handler (this file)
 *        │
 *        ├─→ MCPClient.callTool()  ──→  Python MCP Server (subprocess)
 *        │                                    │
 *        │                              Scans repo, analyzes code,
 *        │                              generates docs via LLM
 *        │                                    │
 *        ├─← Result (markdown docs)  ◄────────┘
 *        │
 *        ▼
 *   DocViewerPanel.show()  ──→  Webview (rendered HTML with tabs, TOC, etc.)
 *
 *
 * COMMANDS REGISTERED:
 *   repoDoc.generateDocs         — Generate both tech and non-tech docs
 *   repoDoc.generateTechnicalDoc — Generate only the technical doc
 *   repoDoc.generateNonTechnicalDoc — Generate only the non-technical guide
 *   repoDoc.showRepoSummary      — Quick scan (no LLM calls)
 *   repoDoc.openSettings         — Open the extension's settings page
 *   repoDoc.viewLastDoc          — Re-open previously generated docs
 */

import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import * as cp from "child_process";
import { MCPClient, createMCPClient } from "./mcpClient";
import { DocViewerPanel } from "./webview/docViewer";
import { SidebarProvider } from "./webview/sidebarProvider";

// ──────────────────────────────────────────────────────────────────────
// Extension State — persists across command invocations within a session
// ──────────────────────────────────────────────────────────────────────

let mcpClient: MCPClient;
let outputChannel: vscode.OutputChannel;
let sidebarProvider: SidebarProvider;
let statusBarItem: vscode.StatusBarItem;
let currentBranch: string = "";
let watcherInterval: ReturnType<typeof setInterval> | undefined;
let branchDebounceTimer: ReturnType<typeof setTimeout> | undefined;

// ──────────────────────────────────────────────────────────────────────
// Activation — called once when the extension first loads
// ──────────────────────────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext): void {
  // Create an output channel for logging (visible in VS Code's Output panel)
  outputChannel = vscode.window.createOutputChannel("Repo Doc Generator");
  outputChannel.appendLine("Repo Doc Generator extension activated");

  // Create the MCP client that communicates with our Python server
  mcpClient = createMCPClient(outputChannel);

  // Register the sidebar provider (activity bar icon + sidebar panel)
  sidebarProvider = new SidebarProvider(context.extensionUri);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      SidebarProvider.viewType,
      sidebarProvider,
    ),
  );

  // ── Register Commands ──
  // Each command corresponds to a button in the sidebar or a command palette entry.
  // The pattern is: register the command, link it to a handler function.

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "repoDoc.generateDocs",
      () => handleGenerateDocs(context, "both"),
    ),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "repoDoc.generateTechnicalDoc",
      () => handleGenerateDocs(context, "technical"),
    ),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "repoDoc.generateNonTechnicalDoc",
      () => handleGenerateDocs(context, "non-technical"),
    ),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "repoDoc.showRepoSummary",
      () => handleRepoSummary(),
    ),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "repoDoc.openSettings",
      () => {
        // Open VS Code settings, pre-filtered to our extension's settings
        vscode.commands.executeCommand(
          "workbench.action.openSettings",
          "repoDoc",
        );
      },
    ),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "repoDoc.viewLastDoc",
      () => handleViewLastDoc(context),
    ),
  );

  // Also push the output channel so it gets disposed on deactivation
  context.subscriptions.push(outputChannel);

  // ── Status Bar Item ──
  // Shows doc freshness: "$(book) Docs: up-to-date" or "$(sync~spin) Docs: updating..."
  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    50,
  );
  statusBarItem.command = "repoDoc.viewLastDoc";
  statusBarItem.tooltip = "Repo Doc Generator — click to view docs";
  updateStatusBar("idle");
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // ── Branch Detection ──
  // Watch .git/HEAD for changes (indicates branch switch)
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (workspaceFolder) {
    const repoPath = workspaceFolder.uri.fsPath;
    currentBranch = detectBranch(repoPath);
    updateStatusBar("idle", currentBranch);

    const gitHeadPattern = new vscode.RelativePattern(
      workspaceFolder,
      ".git/HEAD",
    );
    const gitHeadWatcher = vscode.workspace.createFileSystemWatcher(gitHeadPattern);

    gitHeadWatcher.onDidChange(() => {
      const newBranch = detectBranch(repoPath);
      if (newBranch && newBranch !== currentBranch) {
        const previousBranch = currentBranch;
        currentBranch = newBranch;
        outputChannel.appendLine(
          `Branch switched: ${previousBranch} → ${currentBranch}`,
        );
        updateStatusBar("idle", currentBranch);

        // Auto-generate branch docs if enabled (debounced)
        const config = vscode.workspace.getConfiguration("repoDoc");
        if (config.get<boolean>("watcher.autoGenerateBranchDocs")) {
          if (branchDebounceTimer) {
            clearTimeout(branchDebounceTimer);
          }
          branchDebounceTimer = setTimeout(() => {
            handleBranchDocsGeneration(context, currentBranch);
          }, 3000); // 3-second debounce to let git operations settle
        }
      }
    });

    context.subscriptions.push(gitHeadWatcher);

    // ── Background Watcher ──
    // Periodically check if main branch docs need updating
    const watcherConfig = vscode.workspace.getConfiguration("repoDoc");
    if (watcherConfig.get<boolean>("watcher.enabled")) {
      const intervalMinutes = watcherConfig.get<number>("watcher.intervalMinutes") || 5;
      startBackgroundWatcher(context, repoPath, intervalMinutes);
    }
  }
}

// ──────────────────────────────────────────────────────────────────────
// Command Handlers — the business logic for each command
// ──────────────────────────────────────────────────────────────────────

/**
 * Handle the main "Generate Documentation" command.
 *
 * This is the primary flow:
 * 1. Get the workspace folder path
 * 2. Run health check on the MCP server
 * 3. Show a progress notification with cancel support
 * 4. Call the MCP server to generate docs
 * 5. Read the generated markdown files
 * 6. Display them in the DocViewer webview panel
 *
 * The `docType` parameter controls which doc(s) to generate.
 */
async function handleGenerateDocs(
  context: vscode.ExtensionContext,
  docType: "both" | "technical" | "non-technical",
): Promise<void> {
  // ── Step 1: Get workspace path ──
  const workspaceFolder = getWorkspaceFolder();
  if (!workspaceFolder) {
    return; // getWorkspaceFolder shows an error message if no workspace
  }

  const repoPath = workspaceFolder.uri.fsPath;
  const repoName = workspaceFolder.name;

  outputChannel.appendLine(`\n${"=".repeat(60)}`);
  outputChannel.appendLine(
    `Generating ${docType} docs for: ${repoName} (${repoPath})`,
  );

  // ── Step 2: Health check ──
  const health = await mcpClient.healthCheck();
  if (!health.ok) {
    const action = await vscode.window.showErrorMessage(
      `MCP Server Error: ${health.message}`,
      "Open Settings",
      "View Output",
    );
    if (action === "Open Settings") {
      vscode.commands.executeCommand(
        "workbench.action.openSettings",
        "repoDoc",
      );
    } else if (action === "View Output") {
      outputChannel.show();
    }
    return;
  }

  // ── Step 3: Generate with progress ──
  // Update sidebar status
  sidebarProvider.updateStatus({
    state: "generating",
    message: "Generating documentation...",
  });

  // Map our docType to the MCP tool name
  const toolName =
    docType === "both"
      ? "generate_docs"
      : docType === "technical"
        ? "generate_technical_doc"
        : "generate_non_technical_doc";

  // Use VS Code's built-in progress notification.
  // This shows a progress bar in the notification area with a cancel button.
  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: `Generating ${docType} documentation for ${repoName}...`,
      cancellable: true,
    },
    async (progress, token) => {
      progress.report({ message: "Starting MCP server..." });

      try {
        // Call the MCP server (this spawns the Python process)
        const result = await mcpClient.callTool(
          toolName,
          { repo_path: repoPath },
          token,
        );

        if (!result.success) {
          throw new Error(result.error || "Unknown error during doc generation");
        }

        outputChannel.appendLine(`Generation complete: ${result.content}`);

        // ── Step 4: Read generated files ──
        const config = vscode.workspace.getConfiguration("repoDoc");
        const outputDir = config.get<string>("output.directory") || "./docs/generated";
        const fullOutputDir = path.isAbsolute(outputDir)
          ? outputDir
          : path.join(repoPath, outputDir);

        const techDocPath = path.join(fullOutputDir, "TECHNICAL_DOC.md");
        const nonTechDocPath = path.join(fullOutputDir, "NON_TECHNICAL_GUIDE.md");

        let techContent = "";
        let nonTechContent = "";

        if (fs.existsSync(techDocPath)) {
          techContent = fs.readFileSync(techDocPath, "utf-8");
        }
        if (fs.existsSync(nonTechDocPath)) {
          nonTechContent = fs.readFileSync(nonTechDocPath, "utf-8");
        }

        // ── Step 5: Show in webview ──
        const shouldAutoOpen = config.get<boolean>("autoOpen") ?? true;
        if (shouldAutoOpen && (techContent || nonTechContent)) {
          DocViewerPanel.show(
            context.extensionUri,
            techContent,
            nonTechContent,
            repoName,
          );
        }

        // Update sidebar status
        sidebarProvider.updateStatus({
          state: "done",
          message: "Documentation generated!",
          lastGenerated: new Date().toLocaleTimeString(),
        });

        // Show a success notification
        const openAction = await vscode.window.showInformationMessage(
          `Documentation generated for ${repoName}!`,
          "View Docs",
          "Open Folder",
        );

        if (openAction === "View Docs") {
          DocViewerPanel.show(
            context.extensionUri,
            techContent,
            nonTechContent,
            repoName,
          );
        } else if (openAction === "Open Folder") {
          vscode.commands.executeCommand(
            "revealFileInOS",
            vscode.Uri.file(fullOutputDir),
          );
        }
      } catch (err: any) {
        // Handle errors gracefully
        outputChannel.appendLine(`ERROR: ${err.message}`);

        sidebarProvider.updateStatus({
          state: "error",
          message: err.message?.substring(0, 100),
        });

        const action = await vscode.window.showErrorMessage(
          `Doc generation failed: ${err.message}`,
          "View Output",
          "Retry",
        );

        if (action === "View Output") {
          outputChannel.show();
        } else if (action === "Retry") {
          handleGenerateDocs(context, docType);
        }
      }
    },
  );
}

/**
 * Handle the "Show Repository Summary" command.
 *
 * This is a quick scan that does NOT call the LLM — it just reads the
 * file tree and shows basic statistics. Useful for a quick overview
 * or for verifying the scanner is working before spending money on LLM calls.
 */
async function handleRepoSummary(): Promise<void> {
  const workspaceFolder = getWorkspaceFolder();
  if (!workspaceFolder) {
    return;
  }

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "Scanning repository...",
      cancellable: false,
    },
    async () => {
      try {
        const result = await mcpClient.callTool("get_repo_summary", {
          repo_path: workspaceFolder.uri.fsPath,
        });

        if (result.success) {
          // Show the summary in an output channel (simple text)
          outputChannel.appendLine("\n" + result.content);
          outputChannel.show();

          // Also show a quick notification
          vscode.window.showInformationMessage(
            `Repo scan complete! Check the Output panel for details.`,
            "Show Output",
          ).then((action) => {
            if (action === "Show Output") {
              outputChannel.show();
            }
          });
        } else {
          vscode.window.showErrorMessage(
            `Scan failed: ${result.error}`,
          );
        }
      } catch (err: any) {
        vscode.window.showErrorMessage(
          `Scan error: ${err.message}`,
        );
      }
    },
  );
}

/**
 * Handle the "View Last Generated Documentation" command.
 *
 * Reads previously generated docs from disk and displays them in the viewer.
 * This is useful when you want to re-open docs without regenerating them.
 */
async function handleViewLastDoc(
  context: vscode.ExtensionContext,
): Promise<void> {
  const workspaceFolder = getWorkspaceFolder();
  if (!workspaceFolder) {
    return;
  }

  const config = vscode.workspace.getConfiguration("repoDoc");
  const outputDir = config.get<string>("output.directory") || "./docs/generated";
  const repoPath = workspaceFolder.uri.fsPath;
  const fullOutputDir = path.isAbsolute(outputDir)
    ? outputDir
    : path.join(repoPath, outputDir);

  const techDocPath = path.join(fullOutputDir, "TECHNICAL_DOC.md");
  const nonTechDocPath = path.join(fullOutputDir, "NON_TECHNICAL_GUIDE.md");

  let techContent = "";
  let nonTechContent = "";

  if (fs.existsSync(techDocPath)) {
    techContent = fs.readFileSync(techDocPath, "utf-8");
  }
  if (fs.existsSync(nonTechDocPath)) {
    nonTechContent = fs.readFileSync(nonTechDocPath, "utf-8");
  }

  if (!techContent && !nonTechContent) {
    const action = await vscode.window.showWarningMessage(
      "No generated docs found. Generate documentation first?",
      "Generate Now",
    );
    if (action === "Generate Now") {
      handleGenerateDocs(context, "both");
    }
    return;
  }

  DocViewerPanel.show(
    context.extensionUri,
    techContent,
    nonTechContent,
    workspaceFolder.name,
  );
}

// ──────────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────────

/**
 * Get the current workspace folder, showing an error if none is open.
 *
 * If multiple workspace folders are open (multi-root workspace),
 * we let the user pick which one to document.
 */
function getWorkspaceFolder(): vscode.WorkspaceFolder | undefined {
  const folders = vscode.workspace.workspaceFolders;

  if (!folders || folders.length === 0) {
    vscode.window.showErrorMessage(
      "No workspace folder open. Open a repository folder first.",
    );
    return undefined;
  }

  // For single-folder workspaces, use it directly
  if (folders.length === 1) {
    return folders[0];
  }

  // For multi-root workspaces, we'd ideally show a quick pick.
  // For now, use the first folder. (Enhancement for later.)
  return folders[0];
}

// ──────────────────────────────────────────────────────────────────────
// Branch Detection & Auto-Trigger
// ──────────────────────────────────────────────────────────────────────

/**
 * Detect the current git branch for a workspace.
 * Uses execFileSync (not exec) to avoid shell injection.
 * Returns empty string if git is unavailable or not a repo.
 */
function detectBranch(repoPath: string): string {
  try {
    const result = cp.execFileSync(
      "git",
      ["rev-parse", "--abbrev-ref", "HEAD"],
      { cwd: repoPath, timeout: 5000, encoding: "utf-8" },
    );
    return result.trim();
  } catch {
    return "";
  }
}

/**
 * Update the status bar item with the current doc state.
 */
function updateStatusBar(
  state: "idle" | "updating" | "done" | "error",
  branch?: string,
): void {
  if (!statusBarItem) {
    return;
  }

  const branchLabel = branch ? ` [${branch}]` : "";

  switch (state) {
    case "idle":
      statusBarItem.text = `$(book) Docs${branchLabel}`;
      statusBarItem.backgroundColor = undefined;
      break;
    case "updating":
      statusBarItem.text = `$(sync~spin) Docs: updating...${branchLabel}`;
      statusBarItem.backgroundColor = undefined;
      break;
    case "done":
      statusBarItem.text = `$(check) Docs: updated${branchLabel}`;
      statusBarItem.backgroundColor = undefined;
      // Reset to idle after 10 seconds
      setTimeout(() => updateStatusBar("idle", branch), 10000);
      break;
    case "error":
      statusBarItem.text = `$(warning) Docs: error${branchLabel}`;
      statusBarItem.backgroundColor = new vscode.ThemeColor(
        "statusBarItem.warningBackground",
      );
      break;
  }
}

/**
 * Handle auto-generation of branch docs when switching branches.
 */
async function handleBranchDocsGeneration(
  context: vscode.ExtensionContext,
  branch: string,
): Promise<void> {
  const workspaceFolder = getWorkspaceFolder();
  if (!workspaceFolder) {
    return;
  }

  const repoPath = workspaceFolder.uri.fsPath;

  outputChannel.appendLine(`Auto-generating branch docs for: ${branch}`);
  updateStatusBar("updating", branch);

  try {
    const result = await mcpClient.callTool("generate_branch_docs", {
      repo_path: repoPath,
      branch: branch,
    });

    if (result.success) {
      updateStatusBar("done", branch);
      sidebarProvider.updateStatus({
        state: "done",
        message: `Branch docs generated for ${branch}`,
        lastGenerated: new Date().toLocaleTimeString(),
      });
    } else {
      updateStatusBar("error", branch);
      outputChannel.appendLine(`Branch docs failed: ${result.error}`);
    }
  } catch (err: any) {
    updateStatusBar("error", branch);
    outputChannel.appendLine(`Branch docs error: ${err.message}`);
  }
}

/**
 * Start a background watcher that periodically checks main branch for updates.
 */
function startBackgroundWatcher(
  context: vscode.ExtensionContext,
  repoPath: string,
  intervalMinutes: number,
): void {
  outputChannel.appendLine(
    `Starting background watcher (every ${intervalMinutes} min)`,
  );

  const checkForUpdates = async () => {
    try {
      updateStatusBar("updating", currentBranch);
      const result = await mcpClient.callTool("check_and_update_docs", {
        repo_path: repoPath,
      });

      if (result.success && !result.content.includes("No new commits")) {
        updateStatusBar("done", currentBranch);
        vscode.window.showInformationMessage(
          "Repo Doc: Main branch docs updated!",
          "View Docs",
        ).then((action) => {
          if (action === "View Docs") {
            vscode.commands.executeCommand("repoDoc.viewLastDoc");
          }
        });
      } else {
        updateStatusBar("idle", currentBranch);
      }
    } catch (err: any) {
      outputChannel.appendLine(`Watcher error: ${err.message}`);
      updateStatusBar("idle", currentBranch);
    }
  };

  // Run first check after a short delay (let IDE finish loading)
  setTimeout(checkForUpdates, 30000);

  // Schedule periodic checks
  watcherInterval = setInterval(
    checkForUpdates,
    intervalMinutes * 60 * 1000,
  );
}

// ──────────────────────────────────────────────────────────────────────
// Deactivation — cleanup when the extension is unloaded
// ──────────────────────────────────────────────────────────────────────

export function deactivate(): void {
  if (watcherInterval) {
    clearInterval(watcherInterval);
  }
  if (branchDebounceTimer) {
    clearTimeout(branchDebounceTimer);
  }
  outputChannel?.appendLine("Repo Doc Generator extension deactivated");
}
