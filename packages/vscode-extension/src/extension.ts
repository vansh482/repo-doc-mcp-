import * as vscode from 'vscode';
import {
  runPipeline, NoDiffError,
  getBranchDiff, detectBaseBranch,
  PublisherRegistry, ConfluencePublisher, ConfluenceTransformer,
} from '@repodoc/core';
import type { ContentTransformer, ProgressStep } from '@repodoc/core';
import { SecretStore } from './config/secrets';
import { getConfig, isConfigured } from './config/settings';
import { validateConfluenceCredentials, validateAnthropicKey, validateOpenAIKey } from './config/validator';
import { runSetupWizard } from './config/wizard';
import { SidebarProvider } from './webview/sidebarProvider';
import { checkTokenHealth, promptForReauth } from './config/tokenCheck';
import {
  VsCodeAuthProvider, VsCodeConfigProvider,
  VsCodeStorageProvider, VsCodeProgressReporter,
} from './adapters';

let secretStore: SecretStore;
let storageProvider: VsCodeStorageProvider;
let outputChannel: vscode.OutputChannel;
let extensionUri: vscode.Uri;
let sidebar: SidebarProvider;
let cancelTokenSource: vscode.CancellationTokenSource | undefined;

export function activate(context: vscode.ExtensionContext): void {
  outputChannel = vscode.window.createOutputChannel('Repo Doc Generator');
  secretStore = new SecretStore(context.secrets);
  storageProvider = new VsCodeStorageProvider(context.workspaceState);
  extensionUri = context.extensionUri;

  sidebar = new SidebarProvider(context.extensionUri);
  sidebar.onDidResolve = async () => {
    const history = await storageProvider.getHistory();
    sidebar.sendHistory(history.map(h => ({ branch: h.branch, lastUpdated: h.pages.lastUpdated })));
    handleValidateCredentials(false);
  };
  sidebar.onDeleteHistory = async (branch: string) => {
    await storageProvider.removeBranch(branch);
    const history = await storageProvider.getHistory();
    sidebar.sendHistory(history.map(h => ({ branch: h.branch, lastUpdated: h.pages.lastUpdated })));
  };

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(SidebarProvider.viewType, sidebar),
    vscode.commands.registerCommand('repoDoc.run', () => handleRun(context)),
    vscode.commands.registerCommand('repoDoc.setup', () => handleSetup()),
    vscode.commands.registerCommand('repoDoc.viewDocs', () => handleViewDocs()),
    vscode.commands.registerCommand('repoDoc.cancel', () => handleCancel()),
    vscode.commands.registerCommand('repoDoc.validateCredentials', () => handleValidateCredentials()),
    outputChannel
  );

  checkFirstRun(context);
}

async function checkFirstRun(context: vscode.ExtensionContext): Promise<void> {
  const hasRun = context.globalState.get<boolean>('repoDoc.hasCompletedSetup');
  if (hasRun) return;

  const config = getConfig();
  const configured = await isConfigured(config, secretStore);
  if (!configured) {
    const action = await vscode.window.showInformationMessage(
      'Welcome to Repo Doc Generator! Configure your LLM and Confluence settings to get started.',
      'Setup Now',
      'Later'
    );
    if (action === 'Setup Now') {
      const completed = await runSetupWizard(secretStore, context.extensionUri);
      if (completed) {
        await context.globalState.update('repoDoc.hasCompletedSetup', true);
      }
    } else {
      vscode.commands.executeCommand('workbench.action.openWalkthrough', 'devcraft-tools.repo-doc-generator#repoDoc.getStarted');
    }
  }
}

function handleCancel(): void {
  if (cancelTokenSource) {
    cancelTokenSource.cancel();
    cancelTokenSource.dispose();
    cancelTokenSource = undefined;
  }
}

async function handleValidateCredentials(showPopup: boolean = true): Promise<void> {
  const config = getConfig();
  const cfgRaw = vscode.workspace.getConfiguration('repoDoc');

  sidebar.sendCredStatus({ checking: true });

  const results: string[] = [];

  const confluenceToken = await secretStore.getConfluenceToken() || cfgRaw.get<string>('confluence.apiToken') || '';
  const confluenceEmail = await secretStore.getConfluenceEmail() || cfgRaw.get<string>('confluence.email') || '';

  if (config.confluence.baseUrl && confluenceEmail && confluenceToken) {
    const cfResult = await validateConfluenceCredentials(config.confluence.baseUrl, confluenceEmail, confluenceToken);
    results.push(cfResult.valid ? '✓ Confluence: connected' : `✗ Confluence: ${cfResult.error}`);
  } else {
    results.push('⊘ Confluence: not configured');
  }

  if (config.llm.provider === 'anthropic') {
    const key = await secretStore.getApiKey('anthropic');
    if (key) {
      const result = await validateAnthropicKey(key);
      results.push(result.valid ? '✓ Anthropic: connected' : `✗ Anthropic: ${result.error}`);
    } else {
      results.push('⊘ Anthropic: no API key');
    }
  } else if (config.llm.provider === 'openai') {
    const key = await secretStore.getApiKey('openai');
    if (key) {
      const result = await validateOpenAIKey(key);
      results.push(result.valid ? '✓ OpenAI: connected' : `✗ OpenAI: ${result.error}`);
    } else {
      results.push('⊘ OpenAI: no API key');
    }
  } else if (config.llm.provider === 'bedrock') {
    results.push('✓ Bedrock: configured (IAM auth)');
  }

  const allOk = results.every(r => r.startsWith('✓') || r.startsWith('⊘'));
  const summary = allOk ? 'All credentials OK' : results.find(r => r.startsWith('✗'))?.substring(2) || 'Issues found';

  sidebar.sendCredStatus({ allOk, summary, details: results });
  outputChannel.appendLine(`[RepoDoc] Credential validation: ${results.join(' | ')}`);

  if (showPopup) {
    const action = allOk
      ? await vscode.window.showInformationMessage(results.join('\n'), 'Re-check')
      : await vscode.window.showWarningMessage(results.join('\n'), 'Re-check', 'Open Settings');

    if (action === 'Re-check') {
      handleValidateCredentials(true);
    } else if (action === 'Open Settings') {
      vscode.commands.executeCommand('repoDoc.setup');
    }
  }
}

async function handleRun(context: vscode.ExtensionContext): Promise<void> {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (!workspaceFolder) {
    vscode.window.showErrorMessage('Open a folder first.');
    return;
  }

  const config = getConfig();
  const configured = await isConfigured(config, secretStore);
  if (!configured) {
    const action = await vscode.window.showWarningMessage(
      'Extension not configured. Run setup first.',
      'Setup Now'
    );
    if (action === 'Setup Now') {
      await runSetupWizard(secretStore, context.extensionUri);
    }
    return;
  }

  const repoPath = workspaceFolder.uri.fsPath;
  cancelTokenSource = new vscode.CancellationTokenSource();
  const token = cancelTokenSource.token;

  const startTime = Date.now();
  const elapsed = () => Math.round((Date.now() - startTime) / 1000);

  sidebar.updateState({ status: 'running', step: 'Step 1/5: Detecting branch...', elapsed: 0 });

  const elapsedTimer = setInterval(() => {
    if (sidebar) {
      sidebar.updateState({ elapsed: elapsed() });
    }
  }, 1000);

  try {
    // Pre-flight: file selection (needs diff before pipeline)
    let selectedFiles: string[] | undefined;

    if (config.promptForFileSelection) {
      const baseBranch = sidebar.baseBranchOverride || config.baseBranch || await detectBaseBranch(repoPath);
      const preDiff = await getBranchDiff(repoPath, baseBranch);

      if (preDiff.changedFiles.length > 1) {
        const items = preDiff.changedFiles.map(file => ({ label: file, picked: true }));
        const selected = await vscode.window.showQuickPick(items, {
          canPickMany: true,
          placeHolder: `Select files to include (${preDiff.changedFiles.length} changed)`,
          title: 'File Selection',
        });

        if (!selected) {
          sidebar.updateState({ status: 'idle' });
          return;
        }

        if (selected.length < preDiff.changedFiles.length) {
          selectedFiles = selected.map(s => s.label);
          outputChannel.appendLine(`[RepoDoc] File selection: ${selected.length}/${preDiff.changedFiles.length} files included`);
        }
      }
    }

    if (token.isCancellationRequested) {
      sidebar.updateState({ status: 'idle' });
      return;
    }

    // Pre-flight: token health check
    const tokenStatus = await checkTokenHealth(config.llm.provider as 'anthropic' | 'openai' | 'bedrock', secretStore);
    if (!tokenStatus.valid) {
      outputChannel.appendLine(`[RepoDoc] Token issue: ${tokenStatus.message}`);
      const reauthed = await promptForReauth(config.llm.provider, tokenStatus.message, secretStore);
      if (!reauthed) {
        sidebar.updateState({ status: 'error', error: `${config.llm.provider}: ${tokenStatus.message}. Run setup to update credentials.`, elapsed: elapsed() });
        return;
      }
    }

    // Wire up adapters
    const auth = new VsCodeAuthProvider(secretStore);
    const configProvider = new VsCodeConfigProvider();
    const progress = new VsCodeProgressReporter((step: ProgressStep) => {
      const stepLabels: Record<string, string> = {
        config: 'Step 1/5',
        git: 'Step 1/5',
        scan: 'Step 2/5',
        llm: 'Step 3/5',
        generate: 'Step 3/5',
        publish: 'Step 4/5',
        done: 'Step 5/5',
      };
      const label = stepLabels[step.step] || '';
      sidebar.updateState({ step: `${label}: ${step.message}` });
      outputChannel.appendLine(`[RepoDoc] ${step.message}`);
    });

    // Wire up publisher registry + transformers
    const registry = new PublisherRegistry();
    const confluencePublisher = new ConfluencePublisher();
    registry.register(confluencePublisher);

    const transformers = new Map<string, ContentTransformer>();
    transformers.set('confluence', new ConfluenceTransformer());

    // Run core pipeline
    outputChannel.appendLine(`\n[RepoDoc] ═══ Run started ═══`);

    const result = await runPipeline(
      { auth, config: configProvider, storage: storageProvider, progress },
      {
        repoPath,
        baseBranchOverride: sidebar.baseBranchOverride || undefined,
        selectedFiles,
        customInstructions: sidebar.customInstructions || undefined,
      },
      registry,
      transformers,
    );

    // Post-pipeline: restrict newly created pages
    const confluenceResult = result.publishResults['confluence'];
    if (confluenceResult) {
      try {
        await confluencePublisher.restrictPageToCurrentUser(confluenceResult.technical.pageId);
        await confluencePublisher.restrictPageToCurrentUser(confluenceResult.nonTechnical.pageId);
      } catch (restrictErr: any) {
        outputChannel.appendLine(`Warning: Could not restrict pages — ${restrictErr.message}`);
      }
    }

    // Success UI
    const totalTime = elapsed();
    const techUrl = confluenceResult?.technical.url;
    const summaryUrl = confluenceResult?.nonTechnical.url;

    sidebar.updateState({
      status: 'done',
      step: 'Step 5/5: Done!',
      elapsed: totalTime,
      techUrl,
      summaryUrl,
      branch: result.branch,
      baseBranch: result.baseBranch,
    });

    const history = await storageProvider.getHistory();
    sidebar.sendHistory(history.map(h => ({ branch: h.branch, lastUpdated: h.pages.lastUpdated })));

    if (result.docs.usage) {
      outputChannel.appendLine(
        `[RepoDoc] Tokens: ${result.docs.usage.inputTokens} input + ${result.docs.usage.outputTokens} output = ${result.docs.usage.inputTokens + result.docs.usage.outputTokens} total`
      );
    }
    outputChannel.appendLine(`[RepoDoc] Prompt version: ${result.docs.promptVersion}`);
    if (techUrl) outputChannel.appendLine(`[RepoDoc] Technical: ${techUrl}`);
    if (summaryUrl) outputChannel.appendLine(`[RepoDoc] Summary: ${summaryUrl}`);
    outputChannel.appendLine(`[RepoDoc] ═══ Run finished in ${totalTime}s ═══\n`);

    vscode.window.showInformationMessage(
      `Docs published for "${result.branch}" in ${totalTime}s`
    );

  } catch (err: any) {
    const totalTime = elapsed();

    if (err instanceof NoDiffError) {
      sidebar.updateState({ status: 'idle' });
      vscode.window.showInformationMessage(
        `No changes found on branch "${err.branch}" compared to "${err.baseBranch}".`
      );
      return;
    }

    // Local fallback save on publish failure
    if (err.message?.includes('Confluence API error') || err.message?.includes('credentials')) {
      outputChannel.appendLine(`Publish failed: ${err.message}`);
      await saveDocsLocally(workspaceFolder, err);
      sidebar.updateState({
        status: 'error',
        error: `Publish failed — docs may be saved locally. Error: ${err.message}`,
        elapsed: totalTime,
      });
    } else {
      sidebar.updateState({
        status: 'error',
        error: err.message,
        elapsed: totalTime,
      });
      outputChannel.appendLine(`[RepoDoc] ERROR (after ${totalTime}s): ${err.message}`);
      outputChannel.show();
    }
  } finally {
    clearInterval(elapsedTimer);
    if (cancelTokenSource) {
      cancelTokenSource.dispose();
      cancelTokenSource = undefined;
    }
  }
}

async function saveDocsLocally(workspaceFolder: vscode.WorkspaceFolder, _err: Error): Promise<void> {
  try {
    const repodocDir = vscode.Uri.joinPath(workspaceFolder.uri, '.repodoc');
    await vscode.workspace.fs.createDirectory(repodocDir);
    vscode.window.showWarningMessage(
      'Confluence publish failed. Check the output channel for details.'
    );
  } catch {
    // Best-effort
  }
}

async function handleSetup(): Promise<void> {
  await runSetupWizard(secretStore, extensionUri);
}

async function handleViewDocs(): Promise<void> {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (!workspaceFolder) return;

  const history = await storageProvider.getHistory();
  const branches = [...new Set(history.map(h => h.branch))];

  if (branches.length === 0) {
    vscode.window.showInformationMessage('No docs generated yet. Click "Run" first.');
    return;
  }

  const selected = await vscode.window.showQuickPick(branches, {
    placeHolder: 'Select a branch to view its docs',
  });

  if (selected) {
    const entry = history.find(h => h.branch === selected);
    if (!entry) return;

    const config = getConfig();
    const baseUrl = config.confluence.baseUrl;

    const choice = await vscode.window.showQuickPick(
      ['Technical Doc', 'Non-Technical Summary'],
      { placeHolder: 'Which doc?' }
    );

    const pageId = choice === 'Technical Doc'
      ? entry.pages.technicalPageId
      : entry.pages.nonTechnicalPageId;

    vscode.env.openExternal(
      vscode.Uri.parse(`${baseUrl}/pages/${pageId}`)
    );
  }
}

export function deactivate(): void {}
