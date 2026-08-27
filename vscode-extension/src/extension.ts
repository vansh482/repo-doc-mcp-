import * as vscode from 'vscode';
import { SecretStore } from './config/secrets';
import { getConfig, isConfigured } from './config/settings';
import { validateConfluenceCredentials, validateAnthropicKey, validateOpenAIKey } from './config/validator';
import { runSetupWizard } from './config/wizard';
import { getBranchDiff, detectBaseBranch, filterDiffByFiles } from './git/diff';
import { scanRepo } from './scanner/scanner';
import { createProvider } from './llm/provider';
import { generateDocs } from './generator/generator';
import { ConfluencePublisher } from './publisher/confluence';
import { DocTracker } from './tracker/tracker';
import { SidebarProvider } from './webview/sidebarProvider';
import { checkTokenHealth, promptForReauth } from './config/tokenCheck';

let secretStore: SecretStore;
let docTracker: DocTracker;
let outputChannel: vscode.OutputChannel;
let extensionUri: vscode.Uri;
let sidebar: SidebarProvider;
let cancelTokenSource: vscode.CancellationTokenSource | undefined;

export function activate(context: vscode.ExtensionContext): void {
  outputChannel = vscode.window.createOutputChannel('Repo Doc Generator');
  secretStore = new SecretStore(context.secrets);
  docTracker = new DocTracker(context.workspaceState);
  extensionUri = context.extensionUri;

  sidebar = new SidebarProvider(context.extensionUri);
  sidebar.onDidResolve = () => {
    const history = docTracker.getHistory().map(h => ({ branch: h.branch, lastUpdated: h.pages.lastUpdated }));
    sidebar.sendHistory(history);
    handleValidateCredentials(false);
  };
  sidebar.onDeleteHistory = (branch: string) => {
    docTracker.removeBranch(branch);
    const history = docTracker.getHistory().map(h => ({ branch: h.branch, lastUpdated: h.pages.lastUpdated }));
    sidebar.sendHistory(history);
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
      // Show walkthrough for users who click "Later"
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

  // Validate Confluence
  const confluenceToken = await secretStore.getConfluenceToken() || cfgRaw.get<string>('confluence.apiToken') || '';
  const confluenceEmail = await secretStore.getConfluenceEmail() || cfgRaw.get<string>('confluence.email') || '';

  if (config.confluence.baseUrl && confluenceEmail && confluenceToken) {
    const cfResult = await validateConfluenceCredentials(config.confluence.baseUrl, confluenceEmail, confluenceToken);
    results.push(cfResult.valid ? '✓ Confluence: connected' : `✗ Confluence: ${cfResult.error}`);
  } else {
    results.push('⊘ Confluence: not configured');
  }

  // Validate LLM provider
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
    // Step 1: Git diff
    sidebar.updateState({ step: 'Step 1/5: Detecting branch & computing diff...' });
    const baseBranch = sidebar.baseBranchOverride || config.baseBranch || await detectBaseBranch(repoPath);
    const diff = await getBranchDiff(repoPath, baseBranch);

    if (token.isCancellationRequested) {
      sidebar.updateState({ status: 'idle' });
      return;
    }

    // File selection (if enabled)
    let activeDiff = diff;

    if (config.promptForFileSelection && diff.changedFiles.length > 1) {
      const items = diff.changedFiles.map(file => ({
        label: file,
        picked: true,
      }));

      const selected = await vscode.window.showQuickPick(items, {
        canPickMany: true,
        placeHolder: `Select files to include (${diff.changedFiles.length} changed)`,
        title: 'File Selection',
      });

      if (!selected) {
        sidebar.updateState({ status: 'idle' });
        return; // User cancelled
      }

      if (selected.length < diff.changedFiles.length) {
        activeDiff = filterDiffByFiles(diff, selected.map(s => s.label));
        outputChannel.appendLine(`[RepoDoc] File selection: ${selected.length}/${diff.changedFiles.length} files included`);
      }
    }

    if (!activeDiff.diffContent && activeDiff.changedFiles.length === 0) {
      sidebar.updateState({ status: 'idle' });
      vscode.window.showInformationMessage(
        `No changes found on branch "${diff.currentBranch}" compared to "${baseBranch}".`
      );
      return;
    }

    sidebar.updateState({ branch: diff.currentBranch, baseBranch });
    outputChannel.appendLine(`\n[RepoDoc] ═══ Run started: ${diff.currentBranch} vs ${baseBranch} ═══`);
    outputChannel.appendLine(`[RepoDoc] Step 1: ${activeDiff.changedFiles.length} files changed, ${diff.commitMessages.length} commits`);

    if (diff.truncated) {
      outputChannel.appendLine(`[RepoDoc] Warning: Diff truncated (${Math.round(diff.originalSize / 1024)}KB). Some files may not appear in generated docs.`);
      vscode.window.showWarningMessage(
        `Large diff (${diff.changedFiles.length} files, ${Math.round(diff.originalSize / 1024)}KB). Doc quality may be reduced for skipped files.`
      );
    }

    // Step 2: Scan repo
    sidebar.updateState({ step: 'Step 2/5: Scanning repo structure...' });
    const repoContext = await scanRepo(repoPath);
    outputChannel.appendLine(`[RepoDoc] Step 2: Scanned ${repoContext.totalFiles} files across ${Object.keys(repoContext.languages).length} languages`);
    sidebar.updateState({ step: `Step 2/5: Scanned ${repoContext.totalFiles} files` });

    if (token.isCancellationRequested) {
      sidebar.updateState({ status: 'idle' });
      return;
    }

    // Step 3: LLM generation
    sidebar.updateState({ step: 'Step 3/5: Generating docs with AI (30-60s)...' });

    // Pre-flight token check
    const tokenStatus = await checkTokenHealth(config.llm.provider as 'anthropic' | 'openai' | 'bedrock', secretStore);
    if (!tokenStatus.valid) {
      outputChannel.appendLine(`[RepoDoc] Token issue: ${tokenStatus.message}`);
      const reauthed = await promptForReauth(config.llm.provider, tokenStatus.message, secretStore);
      if (!reauthed) {
        sidebar.updateState({ status: 'error', error: `${config.llm.provider}: ${tokenStatus.message}. Run setup to update credentials.`, elapsed: elapsed() });
        return;
      }
    }

    const apiKey = await secretStore.getApiKey(config.llm.provider as 'anthropic' | 'openai');
    const provider = createProvider(config.llm.provider as any, {
      apiKey: apiKey || undefined,
      model: config.llm.model,
      region: config.bedrock.region,
      profile: config.bedrock.profile,
    });

    const instructions = sidebar.customInstructions || undefined;
    const docs = await generateDocs(provider, activeDiff, repoContext, config.docLength, instructions);
    sidebar.updateState({ step: 'Step 3/5: AI generation complete' });

    outputChannel.appendLine(`[RepoDoc] Step 3: AI generation complete (${docs.technical.length + docs.nonTechnical.length} chars output)`);
    if (docs.usage) {
      outputChannel.appendLine(
        `[RepoDoc] Tokens: ${docs.usage.inputTokens} input + ${docs.usage.outputTokens} output = ${docs.usage.inputTokens + docs.usage.outputTokens} total`
      );
    }
    outputChannel.appendLine(`[RepoDoc] Prompt version: ${docs.promptVersion}`);

    if (token.isCancellationRequested) {
      sidebar.updateState({ status: 'idle' });
      return;
    }

    // Step 4: Publish to Confluence
    sidebar.updateState({ step: 'Step 4/5: Publishing to Confluence...' });

    const existingPages = docTracker.getPages(diff.currentBranch);
    let techResult: { pageId: string; url: string } | undefined;
    let nonTechResult: { pageId: string; url: string } | undefined;

    try {
      const cfgRaw = vscode.workspace.getConfiguration('repoDoc');
      const confluenceToken = await secretStore.getConfluenceToken() || cfgRaw.get<string>('confluence.apiToken') || '';
      const confluenceEmail = await secretStore.getConfluenceEmail() || cfgRaw.get<string>('confluence.email') || '';

      if (!confluenceToken || !confluenceEmail) {
        throw new Error('Confluence credentials not found. Run setup again.');
      }

      const publisher = new ConfluencePublisher({
        baseUrl: config.confluence.baseUrl,
        email: confluenceEmail,
        apiToken: confluenceToken,
        spaceKey: config.confluence.spaceKey,
        parentPageId: config.confluence.parentPageId,
      });

      const techTitle = `${diff.currentBranch} — Technical`;
      const nonTechTitle = `${diff.currentBranch} — Summary`;

      if (existingPages) {
        const techVersion = await publisher.getPageVersion(existingPages.technicalPageId);
        techResult = await publisher.updatePage(
          existingPages.technicalPageId, techTitle, docs.technical, techVersion
        );

        const nonTechVersion = await publisher.getPageVersion(existingPages.nonTechnicalPageId);
        nonTechResult = await publisher.updatePage(
          existingPages.nonTechnicalPageId, nonTechTitle, docs.nonTechnical, nonTechVersion
        );

        outputChannel.appendLine(`[RepoDoc] Step 4: Updated existing pages for branch: ${diff.currentBranch}`);
      } else {
        techResult = await publisher.createPage(techTitle, docs.technical);
        nonTechResult = await publisher.createPage(nonTechTitle, docs.nonTechnical);

        try {
          await publisher.restrictPageToCurrentUser(techResult.pageId);
          await publisher.restrictPageToCurrentUser(nonTechResult.pageId);
        } catch (restrictErr: any) {
          outputChannel.appendLine(`Warning: Could not restrict pages — ${restrictErr.message}`);
        }

        docTracker.setPages(diff.currentBranch, {
          technicalPageId: techResult.pageId,
          nonTechnicalPageId: nonTechResult.pageId,
          lastUpdated: new Date().toISOString(),
        });

        outputChannel.appendLine(`[RepoDoc] Step 4: Created new pages for branch: ${diff.currentBranch}`);
      }
    } catch (publishErr: any) {
      outputChannel.appendLine(`Publish failed: ${publishErr.message}`);

      const safeBranch = diff.currentBranch.replace(/\//g, '-');
      const repodocDir = vscode.Uri.joinPath(workspaceFolder.uri, '.repodoc');
      const techFile = vscode.Uri.joinPath(repodocDir, `${safeBranch}-technical.md`);
      const summaryFile = vscode.Uri.joinPath(repodocDir, `${safeBranch}-summary.md`);

      try {
        await vscode.workspace.fs.createDirectory(repodocDir);
        const metaHeader = `<!-- Generated by RepoDoc | Prompt: ${docs.promptVersion} | ${new Date().toISOString()} -->\n\n`;
        await vscode.workspace.fs.writeFile(techFile, Buffer.from(metaHeader + docs.technical, 'utf-8'));
        await vscode.workspace.fs.writeFile(summaryFile, Buffer.from(metaHeader + docs.nonTechnical, 'utf-8'));

        sidebar.updateState({
          status: 'error',
          error: `Publish failed — docs saved locally to .repodoc/. Error: ${publishErr.message}`,
          elapsed: elapsed(),
        });
        vscode.window.showWarningMessage(
          `Confluence publish failed. Docs saved to .repodoc/${safeBranch}-technical.md and .repodoc/${safeBranch}-summary.md`
        );
      } catch (saveErr: any) {
        sidebar.updateState({
          status: 'error',
          error: `Publish failed and local save failed: ${publishErr.message}`,
          elapsed: elapsed(),
        });
      }
      return;
    }

    if (token.isCancellationRequested) {
      sidebar.updateState({ status: 'idle' });
      return;
    }

    // Step 5: Done
    const totalTime = elapsed();
    sidebar.updateState({
      status: 'done',
      step: 'Step 5/5: Done!',
      elapsed: totalTime,
      techUrl: techResult!.url,
      summaryUrl: nonTechResult!.url,
      branch: diff.currentBranch,
    });

    sidebar.sendHistory(
      docTracker.getHistory().map(h => ({ branch: h.branch, lastUpdated: h.pages.lastUpdated }))
    );

    outputChannel.appendLine(`[RepoDoc] Step 5: Done!`);
    outputChannel.appendLine(`[RepoDoc] Technical: ${techResult!.url}`);
    outputChannel.appendLine(`[RepoDoc] Summary: ${nonTechResult!.url}`);
    outputChannel.appendLine(`[RepoDoc] ═══ Run finished in ${totalTime}s ═══\n`);

    vscode.window.showInformationMessage(
      `Docs ${existingPages ? 'updated' : 'published'} for "${diff.currentBranch}" in ${totalTime}s`
    );

  } catch (err: any) {
    const totalTime = elapsed();
    sidebar.updateState({
      status: 'error',
      error: err.message,
      elapsed: totalTime,
    });
    outputChannel.appendLine(`[RepoDoc] ERROR (after ${totalTime}s): ${err.message}`);
    outputChannel.show();
  } finally {
    clearInterval(elapsedTimer);
    if (cancelTokenSource) {
      cancelTokenSource.dispose();
      cancelTokenSource = undefined;
    }
  }
}

async function handleSetup(): Promise<void> {
  await runSetupWizard(secretStore, extensionUri);
}

async function handleViewDocs(): Promise<void> {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (!workspaceFolder) return;

  const allTracked = docTracker.getAllTracked();
  const branches = Object.keys(allTracked);

  if (branches.length === 0) {
    vscode.window.showInformationMessage('No docs generated yet. Click "Run" first.');
    return;
  }

  const selected = await vscode.window.showQuickPick(branches, {
    placeHolder: 'Select a branch to view its docs',
  });

  if (selected) {
    const pages = allTracked[selected];
    const config = getConfig();
    const baseUrl = config.confluence.baseUrl;

    const choice = await vscode.window.showQuickPick(
      ['Technical Doc', 'Non-Technical Summary'],
      { placeHolder: 'Which doc?' }
    );

    const pageId = choice === 'Technical Doc'
      ? pages.technicalPageId
      : pages.nonTechnicalPageId;

    vscode.env.openExternal(
      vscode.Uri.parse(`${baseUrl}/pages/${pageId}`)
    );
  }
}

export function deactivate(): void {}
