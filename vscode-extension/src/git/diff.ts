import { execFile } from "child_process";
import { promisify } from "util";

const exec = promisify(execFile);

const MAX_DIFF_CHARS = 50000;

export interface BranchDiff {
  currentBranch: string;
  baseBranch: string;
  diffSummary: string;
  diffContent: string;
  changedFiles: string[];
  commitMessages: string[];
  truncated: boolean;
  originalSize: number;
}

async function git(repoPath: string, args: string[]): Promise<string> {
  const { stdout } = await exec("git", args, {
    cwd: repoPath,
    maxBuffer: 10 * 1024 * 1024,
  });
  return stdout.trim();
}

export async function detectBaseBranch(repoPath: string): Promise<string> {
  const currentBranch = await git(repoPath, ["rev-parse", "--abbrev-ref", "HEAD"]).catch(() => "");

  if (currentBranch) {
    try {
      const merge = await git(repoPath, ["config", `branch.${currentBranch}.merge`]);
      const tracked = merge.replace("refs/heads/", "");
      if (tracked && tracked !== currentBranch) {
        await git(repoPath, ["rev-parse", "--verify", tracked]);
        return tracked;
      }
    } catch {
      // no tracking config or tracked branch doesn't exist locally
    }
  }

  const candidates = ["main", "master", "develop", "development", "mainline"];
  for (const branch of candidates) {
    if (branch === currentBranch) continue;
    try {
      await git(repoPath, ["rev-parse", "--verify", branch]);
      return branch;
    } catch {
      // branch doesn't exist, try next
    }
  }

  const remoteCandidates = ["origin/main", "origin/master", "origin/develop", "origin/mainline"];
  for (const branch of remoteCandidates) {
    try {
      await git(repoPath, ["rev-parse", "--verify", branch]);
      return branch;
    } catch {
      // doesn't exist, try next
    }
  }

  throw new Error(
    'Could not detect base branch. Set repoDoc.baseBranch in VS Code settings (Cmd+, → search "repoDoc.baseBranch").',
  );
}

function truncateDiffAtFileBoundaries(
  rawDiff: string,
  maxChars: number,
  changedFiles: string[],
): { content: string; truncated: boolean } {
  if (rawDiff.length <= maxChars) {
    return { content: rawDiff, truncated: false };
  }

  const fileDiffs = rawDiff.split(/(?=^diff --git )/m).filter(s => s.trim());

  if (fileDiffs.length === 0) {
    return { content: rawDiff.slice(0, maxChars) + "\n\n[... truncated]", truncated: true };
  }

  const SOURCE_EXTS = /\.(ts|tsx|js|jsx|py|java|go|rs|rb|cs|cpp|c|h|swift|kt)$/i;
  const CONFIG_EXTS = /\.(json|yaml|yml|toml|xml|conf|env|ini)$/i;

  const scored = fileDiffs.map(chunk => {
    const fileMatch = chunk.match(/^diff --git a\/(.+?) b\//);
    const file = fileMatch ? fileMatch[1] : "";
    let priority = 2;
    if (SOURCE_EXTS.test(file)) priority = 0;
    else if (CONFIG_EXTS.test(file)) priority = 1;
    return { chunk, file, priority };
  });

  scored.sort((a, b) => a.priority - b.priority);

  const footerReserve = 300;
  let used = 0;
  const included: string[] = [];
  const omitted: string[] = [];

  for (const { chunk, file } of scored) {
    if (used + chunk.length <= maxChars - footerReserve) {
      included.push(chunk);
      used += chunk.length;
    } else if (included.length === 0) {
      included.push(chunk.slice(0, maxChars - footerReserve) + "\n[... file truncated]");
      used = maxChars - footerReserve;
    } else {
      omitted.push(file);
    }
  }

  let result = included.join("");
  if (omitted.length > 0) {
    const shown = omitted.slice(0, 5).join(", ");
    const extra = omitted.length > 5 ? ` and ${omitted.length - 5} more` : "";
    result += `\n\n[Diff truncated — ${included.length}/${changedFiles.length} files shown (source code prioritized). Omitted: ${shown}${extra}]`;
  }

  return { content: result, truncated: true };
}

export async function getBranchDiff(
  repoPath: string,
  baseBranch: string,
): Promise<BranchDiff> {
  const currentBranch = await git(repoPath, [
    "rev-parse",
    "--abbrev-ref",
    "HEAD",
  ]);

  if (currentBranch === baseBranch) {
    return {
      currentBranch,
      baseBranch,
      diffSummary: "",
      diffContent: "",
      changedFiles: [],
      commitMessages: [],
      truncated: false,
      originalSize: 0,
    };
  }

  // Run all git commands in parallel
  const [diffSummary, rawDiff, changedFilesRaw, commitsRaw] =
    await Promise.all([
      git(repoPath, ["diff", `${baseBranch}...HEAD`, "--stat"]).catch(
        () => "",
      ),
      git(repoPath, ["diff", `${baseBranch}...HEAD`]).catch(() => ""),
      git(repoPath, ["diff", `${baseBranch}...HEAD`, "--name-only"]).catch(
        () => "",
      ),
      git(repoPath, ["log", `${baseBranch}..HEAD`, "--oneline"]).catch(
        () => "",
      ),
    ]);

  const changedFiles = changedFilesRaw
    .split("\n")
    .filter((f) => f.length > 0);

  const commitMessages = commitsRaw
    .split("\n")
    .filter((m) => m.length > 0);

  const { content: diffContent, truncated } = truncateDiffAtFileBoundaries(rawDiff, MAX_DIFF_CHARS, changedFiles);

  return {
    currentBranch,
    baseBranch,
    diffSummary,
    diffContent,
    changedFiles,
    commitMessages,
    truncated,
    originalSize: rawDiff.length,
  };
}
