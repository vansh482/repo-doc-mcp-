import * as vscode from 'vscode';
import { SecretStore } from './config/secrets';
import { getConfig, isConfigured } from './config/settings';
import { runSetupWizard } from './config/wizard';
import { getBranchDiff, detectBaseBranch } from './git/diff';
import { scanRepo } from './scanner/scanner';
import { createProvider } from './llm/provider';
import { generateDocs } from './generator/generator';
import { ConfluencePublisher } from './publisher/confluence';
import { DocTracker } from './tracker/tracker';

let secretStore: SecretStore;
let docTracker: DocTracker;
let outputChannel: vscode.OutputChannel;
let extensionUri: vscode.Uri;

export function activate(context: vscode.ExtensionContext): void {
  outputChannel = vscode.window.createOutputChannel('Repo Doc Generator');
  secretStore = new SecretStore(context.secrets);
  docTracker = new DocTracker(context.workspaceState);
  extensionUri = context.extensionUri;

  context.subscriptions.push(
    vscode.commands.registerCommand('repoDoc.run', () => handleRun(context)),
    vscode.commands.registerCommand('repoDoc.setup', () => handleSetup()),
    vscode.commands.registerCommand('repoDoc.viewDocs', () => handleViewDocs()),
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

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: 'Repo Doc',
      cancellable: true,
    },
    async (progress, token) => {
      const startTime = Date.now();
      const elapsed = () => Math.round((Date.now() - startTime) / 1000);

      try {
        // Step 1: Git diff
        progress.report({ message: `Step 1/5: Detecting branch and computing diff... (${elapsed()}s)`, increment: 0 });
        const baseBranch = config.baseBranch || await detectBaseBranch(repoPath);
        const diff = await getBranchDiff(repoPath, baseBranch);
        progress.report({ increment: 10 });

        if (token.isCancellationRequested) {
          vscode.window.showWarningMessage('Doc generation cancelled.');
          return;
        }

        if (!diff.diffContent && diff.changedFiles.length === 0) {
          vscode.window.showInformationMessage(
            `No changes found on branch "${diff.currentBranch}" compared to "${baseBranch}".`
          );
          return;
        }

        outputChannel.appendLine(`Branch: ${diff.currentBranch} (${diff.changedFiles.length} files changed vs ${baseBranch})`);

        // Step 2: Scan repo
        progress.report({ message: `Step 2/5: Scanning repository structure... (${elapsed()}s)`, increment: 0 });
        const repoContext = await scanRepo(repoPath);
        progress.report({ message: `Step 2/5: Scanned ${repoContext.totalFiles} files across ${Object.keys(repoContext.languages).length} languages (${elapsed()}s)`, increment: 15 });

        if (token.isCancellationRequested) {
          vscode.window.showWarningMessage('Doc generation cancelled.');
          return;
        }

        // Step 3: LLM generation (the slow step)
        progress.report({ message: `Step 3/5: Generating docs with AI — this takes 30-60s... (${elapsed()}s)`, increment: 0 });
        const apiKey = await secretStore.getApiKey(config.llm.provider as 'anthropic' | 'openai');
        const provider = createProvider(config.llm.provider as any, {
          apiKey: apiKey || undefined,
          model: config.llm.model,
          region: config.bedrock.region,
          profile: config.bedrock.profile,
        });

        const docs = await generateDocs(provider, diff, repoContext);
        progress.report({ message: `Step 3/5: AI generation complete (${elapsed()}s)`, increment: 50 });

        if (token.isCancellationRequested) {
          vscode.window.showWarningMessage('Doc generation cancelled.');
          return;
        }

        // Step 4: Publish to Confluence
        progress.report({ message: `Step 4/5: Publishing to Confluence... (${elapsed()}s)`, increment: 0 });
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

        const existingPages = docTracker.getPages(diff.currentBranch);
        const repoName = repoContext.name;
        const techTitle = `${repoName} — ${diff.currentBranch} — Technical`;
        const nonTechTitle = `${repoName} — ${diff.currentBranch} — Summary`;

        let techResult;
        let nonTechResult;

        if (existingPages) {
          const techVersion = await publisher.getPageVersion(existingPages.technicalPageId);
          techResult = await publisher.updatePage(
            existingPages.technicalPageId, techTitle, docs.technical, techVersion
          );

          const nonTechVersion = await publisher.getPageVersion(existingPages.nonTechnicalPageId);
          nonTechResult = await publisher.updatePage(
            existingPages.nonTechnicalPageId, nonTechTitle, docs.nonTechnical, nonTechVersion
          );

          outputChannel.appendLine(`Updated existing pages for branch: ${diff.currentBranch}`);
        } else {
          techResult = await publisher.createPage(techTitle, docs.technical);
          nonTechResult = await publisher.createPage(nonTechTitle, docs.nonTechnical);

          docTracker.setPages(diff.currentBranch, {
            technicalPageId: techResult.pageId,
            nonTechnicalPageId: nonTechResult.pageId,
            lastUpdated: new Date().toISOString(),
          });

          outputChannel.appendLine(`Created new pages for branch: ${diff.currentBranch}`);
        }

        progress.report({ increment: 20 });

        if (token.isCancellationRequested) {
          vscode.window.showWarningMessage('Doc generation cancelled (pages may have been partially published).');
          return;
        }

        // Step 5: Done
        const totalTime = elapsed();
        progress.report({ message: `Step 5/5: Done! Completed in ${totalTime}s`, increment: 5 });

        outputChannel.appendLine(`Technical: ${techResult.url}`);
        outputChannel.appendLine(`Non-Technical: ${nonTechResult.url}`);
        outputChannel.appendLine(`Total time: ${totalTime}s`);

        const action = await vscode.window.showInformationMessage(
          `Docs ${existingPages ? 'updated' : 'published'} for "${diff.currentBranch}" in ${totalTime}s`,
          'Open Technical',
          'Open Summary'
        );

        if (action === 'Open Technical') {
          vscode.env.openExternal(vscode.Uri.parse(techResult.url));
        } else if (action === 'Open Summary') {
          vscode.env.openExternal(vscode.Uri.parse(nonTechResult.url));
        }
      } catch (err: any) {
        outputChannel.appendLine(`ERROR (after ${elapsed()}s): ${err.message}`);
        outputChannel.show();
        vscode.window.showErrorMessage(`Doc generation failed after ${elapsed()}s: ${err.message}`);
      }
    }
  );
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
